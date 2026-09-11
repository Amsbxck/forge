"""Verbrauchsabrechnung je Athlet auf einem gemeinsamen API-Schlüssel.

Der Betreiber zahlt die Anthropic-Rechnung und legt jedem Athleten ein
Guthaben an. Technisch läuft alles über einen einzigen Schlüssel — das
erspart jedem Nutzer die eigene Registrierung bei Anthropic und hält den
Code einfach. Damit dabei niemand das Guthaben eines anderen verbraucht,
wird jeder Aufruf einzeln zugeordnet und abgerechnet.

Zwei Regeln machen das verlässlich:

* **Vor jedem Aufruf wird geprüft.** Ist das Guthaben aufgebraucht, kommt
  der Aufruf gar nicht erst zustande. Ein nachträgliches Abrechnen würde
  jedem erlauben, sein Guthaben beliebig zu überziehen.
* **Nach jedem Aufruf wird gebucht**, mit den tatsächlichen Token aus der
  Antwort statt mit einer Schätzung. Nur so stimmt die Summe am Monatsende
  mit der Rechnung überein.

Die Preise stehen in der Konfiguration, nicht im Code: Sie ändern sich, und
eine falsche Zahl hier fällt niemandem auf — die Beträge blieben plausibel
und wären trotzdem falsch.
"""

import logging
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from core.config import settings
from models import ApiUsage, User

logger = logging.getLogger(__name__)


class NoBillingContext(RuntimeError):
    """Kein Nutzer zuordenbar — der Aufruf wäre nicht abrechenbar."""

    def __init__(self):
        super().__init__(
            "Kein Nutzerkontext für die Abrechnung — Aufruf abgebrochen"
        )


class BudgetExhausted(RuntimeError):
    """Guthaben aufgebraucht. Trägt die Zahlen für die Meldung an den Nutzer."""

    def __init__(self, verbraucht: float, guthaben: float):
        self.verbraucht = verbraucht
        self.guthaben = guthaben
        super().__init__(
            f"Guthaben aufgebraucht: {verbraucht:.2f} € von {guthaben:.2f} € verbraucht"
        )


def cost_eur(model: str, input_tokens: int, output_tokens: int) -> float:
    """Kosten eines Aufrufs in Euro.

    Anthropic rechnet in Dollar je Million Token, mit unterschiedlichen
    Preisen für Ein- und Ausgabe — Ausgabe ist etwa fünfmal so teuer. Ein
    gemeinsamer Mischpreis würde einen Wochenplan systematisch zu billig
    ansetzen, weil dort viel erzeugt und wenig gelesen wird.
    """
    preise = settings.model_prices(model)
    dollar = (
        input_tokens / 1_000_000 * preise["input"]
        + output_tokens / 1_000_000 * preise["output"]
    )
    return round(dollar * settings.USD_TO_EUR, 6)


def spent_eur(db: Session, user: User | None) -> float:
    """Bisher verbrauchtes Guthaben."""
    if user is None:
        return 0.0
    summe = (
        db.query(func.coalesce(func.sum(ApiUsage.cost_eur), 0.0))
        .filter(ApiUsage.user_id == user.id)
        .scalar()
    )
    return round(float(summe or 0.0), 4)


def budget_eur(user: User | None) -> float:
    """Zugeteiltes Guthaben. Ohne eigene Zuteilung gilt der Standardbetrag."""
    if user is None:
        return 0.0
    zugeteilt = getattr(user, "api_budget_eur", None)
    return float(zugeteilt if zugeteilt is not None else settings.API_BUDGET_EUR)


def top_up(db: Session, user: User, betrag_eur: float) -> dict:
    """Guthaben erhöhen.

    Der Verbrauch bleibt stehen — er ist die Historie. Erhöht wird das
    Guthaben, und die Warnmarke fällt weg, damit beim nächsten Mal wieder
    gewarnt wird.
    """
    user.api_budget_eur = round(budget_eur(user) + betrag_eur, 2)
    user.api_warned_at = None
    db.commit()
    return status(db, user)


def status(db: Session, user: User | None) -> dict:
    verbraucht = spent_eur(db, user)
    guthaben = budget_eur(user)
    return {
        "guthaben_eur": round(guthaben, 2),
        "verbraucht_eur": round(verbraucht, 4),
        "rest_eur": round(max(0.0, guthaben - verbraucht), 4),
        "aufgebraucht": verbraucht >= guthaben,
        "aufrufe": db.query(ApiUsage).filter(ApiUsage.user_id == user.id).count() if user else 0,
    }


def ensure_budget(db: Session, user: User | None) -> None:
    """Vor dem Aufruf prüfen. Wirft, wenn nichts mehr übrig ist.

    Ohne Nutzerkontext (lokaler Einzelplatzbetrieb) wird nicht abgerechnet —
    dort gibt es niemanden, dessen Guthaben zu schützen wäre.
    """
    if not settings.API_BUDGET_ENFORCED:
        return
    if user is None:
        # Ohne erkennbaren Nutzer wird abgebrochen statt durchgewinkt. Vorher
        # kehrte die Prüfung still zurück und `record` buchte ebenfalls nichts:
        # Jeder Pfad, der den Mandantenkontext verlor, rief die API kostenlos
        # und ungezählt auf. Genau so lief die Neuplanung nach einer
        # Krankmeldung monatelang — nur dass sie zusätzlich abbrach und der
        # Fehler dadurch überhaupt auffiel.
        raise NoBillingContext()
    # Zeile des Kontos sperren, bis die Prüfung durch ist. Ohne die Sperre
    # passieren zwei gleichzeitige Anfragen desselben Athleten beide die
    # Prüfung, bevor eine von beiden gebucht hat — das Guthaben lässt sich
    # dann um die Zahl der parallelen Anfragen überziehen.
    try:
        db.query(User).filter(User.id == user.id).with_for_update().first()
    except Exception:  # pragma: no cover - SQLite im Test kennt kein FOR UPDATE
        pass

    verbraucht = spent_eur(db, user)
    guthaben = budget_eur(user)
    if verbraucht >= guthaben:
        raise BudgetExhausted(verbraucht, guthaben)


def record(
    db: Session,
    user: User | None,
    *,
    kind: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> float:
    """Verbrauch buchen. Gibt die Kosten des Aufrufs zurück."""
    if user is None:
        # Sollte nach der Prüfung in `ensure_budget` nicht mehr vorkommen —
        # tritt es doch ein, ist echtes Geld ungezählt geflossen. Das gehört
        # ins Log und nicht in ein stilles `return`.
        logger.error(
            "API-Aufruf (%s, %s ein / %s aus) ohne Nutzerkontext — nicht abgerechnet",
            kind, input_tokens, output_tokens,
        )
        return 0.0

    kosten = cost_eur(model, input_tokens, output_tokens)
    db.add(ApiUsage(
        user_id=user.id,
        kind=kind,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_eur=kosten,
        created_at=datetime.utcnow(),
    ))
    db.commit()
    logger.info(
        "API-Verbrauch Nutzer %s: %s, %s ein / %s aus, %.4f €",
        user.id, kind, input_tokens, output_tokens, kosten,
    )
    _pruefe_warnung(db, user)
    return kosten


# Schwellen, bei deren Unterschreiten gewarnt wird — als Anteil des
# Guthabens. Absteigend, damit die niedrigste zutreffende gewinnt.
WARNSCHWELLEN = (0.10, 0.0)


def _pruefe_warnung(db: Session, user: User) -> None:
    """Einmal je Schwelle eine Mail, nicht bei jedem Aufruf.

    Ohne die Marke am Konto ginge nach jedem Wochenplan eine Nachricht raus;
    beim tatsächlichen Ende würde sie dann niemand mehr lesen.
    """
    guthaben = budget_eur(user)
    if guthaben <= 0:
        return
    anteil_rest = max(0.0, guthaben - spent_eur(db, user)) / guthaben

    # Die niedrigste zutreffende Schwelle, nicht die erste: Bei 0 % Rest
    # passen beide, und `next()` hätte 10 % genommen — die Meldung
    # „aufgebraucht" wäre nie verschickt worden.
    zutreffend = [s for s in WARNSCHWELLEN if anteil_rest <= s]
    if not zutreffend:
        return
    faellig = min(zutreffend)
    bereits = user.api_warned_at
    if bereits is not None and bereits <= faellig:
        return  # für diese oder eine tiefere Schwelle wurde schon gewarnt

    user.api_warned_at = faellig
    db.commit()

    try:
        from services.account_mail import send_budget_warning

        send_budget_warning(
            user.email, user.name,
            rest=round(anteil_rest * guthaben, 2),
            guthaben=round(guthaben, 2),
            aufgebraucht=faellig == 0.0,
        )
    except Exception as e:  # pragma: no cover - Mail darf nie den Aufruf reißen
        logger.warning("Guthabenwarnung nicht verschickt: %s", e)
