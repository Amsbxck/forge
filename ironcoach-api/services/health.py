"""Krankheit und Verletzung — und was daraus für den Plan folgt.

Die Regeln hier sind bewusst deterministisch und stehen nicht im Prompt zur
Disposition. Ein Sprachmodell, dem man "der Athlet war krank" hinschreibt,
kürzt mal um 20 % und plant mal Intervalle am zweiten Tag nach dem Fieber.
Was medizinisch nicht verhandelbar ist — kein Training mit Fieber, keine
Intensität direkt danach — wird hier ausgerechnet und als harte Vorgabe
übergeben.

Die zugrunde liegenden Regeln:

* **Hals-Check.** Beschwerden oberhalb des Halses (Schnupfen, Halskratzen,
  kein Fieber) erlauben lockeres Training in Z1/Z2. Alles darunter — Husten,
  Gliederschmerzen, Fieber — bedeutet Pause.
* **Fieber ist absolut.** Training mit Fieber kann eine Herzmuskelentzündung
  auslösen. Dafür gibt es keine Abwägung gegen einen Trainingsreiz.
* **Wiedereinstieg.** Pro Ausfalltag etwa ein Tag lockeres Training, bevor
  wieder Intensität ansteht; nach Fieber mindestens drei Tage, gedeckelt auf
  zwei Wochen, weil danach die Form ohnehin neu aufgebaut wird.
* **Krankheit im Taper.** Liegen die Ausfalltage in den letzten Wochen vor
  dem Rennen, ist die Erholung bereits erzwungen worden. Dann verlängert
  weiterer Taper die Formlosigkeit, statt sie zu beheben — der Taper wird
  gekürzt und bekommt kurze Reize statt zusätzlicher Ruhe.
"""

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy.orm import Session

from models import HealthEvent, User

logger = logging.getLogger(__name__)

KINDS = ("illness", "injury", "other")
SEVERITIES = ("mild", "moderate", "severe")

# Der Schweregrad bedeutet bei einer Verletzung etwas anderes als bei einem
# Infekt: dort entscheidet das Immunsystem, hier die Belastbarkeit.
SEVERITY_LABEL = {
    "illness": {
        "mild": "leicht (über dem Hals, kein Fieber)",
        "moderate": "mäßig (Husten, Gliederschmerzen)",
        "severe": "schwer (Fieber oder ärztliche Pause)",
    },
    "injury": {
        "mild": "leicht (schmerzfrei belastbar)",
        "moderate": "mäßig (Schmerz bei Belastung)",
        "severe": "schwer (nicht belastbar oder ärztliche Pause)",
    },
}


def severity_label(kind: str, severity: str) -> str:
    tabelle = SEVERITY_LABEL.get(kind) or SEVERITY_LABEL["illness"]
    return tabelle.get(severity, severity)
KIND_LABEL = {"illness": "Krankheit", "injury": "Verletzung", "other": "Ausfall"}


def _tage(anzahl: int) -> str:
    """"1 Tag" statt "1 Tage" — der Text landet im Prompt und in der Anzeige."""
    return f"{anzahl} Tag" if anzahl == 1 else f"{anzahl} Tage"

# Ersatz für eine ausgefallene Disziplin. Bewusst konkret: „Crosstraining"
# als Wort führt zu Vorschlägen wie „lockeres Radfahren", auch wenn das Knie
# genau daran scheitert. Die Auswahl deckt beide Fälle ab — stoßfrei bei
# Aufprallproblemen, beinfrei bei Verletzungen der unteren Extremität.
ERSATZ_HINWEIS = (
    "ERSATZTRAINING STATT AUSFALL: Plane die weggefallene Einheit als "
    "`session_type: other` mit `training_type: cross_training` und nenne das "
    "Gerät ausdrücklich — StairMaster, Crosstrainer, Ruderergometer, "
    "Aquajogging oder Radfahren als Laufersatz. Auswahlregel: Bei Problemen "
    "durch Aufprall (Schienbein, Achillessehne, Knie beim Laufen) sind "
    "StairMaster, Crosstrainer und Aquajogging geeignet, weil sie den Reiz "
    "ohne Stoßbelastung erzeugen; bei Verletzungen, die das Bein gar nicht "
    "belasten dürfen, bleiben Ruderergometer mit Armzug oder Schwimmen mit "
    "Pull-Buoy. Steuerung ausschließlich über Herzfrequenz, keine Watt- oder "
    "Pacevorgaben — die Geräte messen unterschiedlich. Jede Ersatzeinheit "
    "gilt nur, solange sie schmerzfrei bleibt."
)

# Wie lange nach dem letzten Krankheitstag noch Rücksicht genommen wird.
LOOKBACK_DAYS = 28
MAX_EASY_DAYS = 14
FEVER_MIN_EASY_DAYS = 3


@dataclass
class Guidance:
    """Was der Gesundheitszustand für die Planung bedeutet."""

    status: str = "healthy"          # healthy | sick | returning
    event: HealthEvent | None = None
    days_out: int = 0                # Ausfalltage der laufenden/letzten Episode
    days_since_end: int | None = None
    easy_until: date | None = None   # bis dahin keine Intensität
    can_train: bool = True
    volume_factor: float = 1.0       # Empfehlung für das Wochenvolumen
    lines: list[str] = field(default_factory=list)   # Vorgaben für den Prompt

    @property
    def active(self) -> bool:
        return self.status != "healthy"

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "can_train": self.can_train,
            "days_out": self.days_out,
            "days_since_end": self.days_since_end,
            "easy_until": str(self.easy_until) if self.easy_until else None,
            "volume_factor": round(self.volume_factor, 2),
            "event": event_to_dict(self.event) if self.event else None,
            "lines": self.lines,
        }


def event_to_dict(event: HealthEvent) -> dict:
    return {
        "id": event.id,
        "kind": event.kind,
        "kind_label": KIND_LABEL.get(event.kind, event.kind),
        "severity": event.severity,
        "severity_label": severity_label(event.kind, event.severity),
        "fever": bool(event.fever),
        "start_date": str(event.start_date),
        "end_date": str(event.end_date) if event.end_date else None,
        "days": event.days,
        "note": event.note,
        "is_open": event.is_open,
    }


# --- Abfragen ----------------------------------------------------------------

def open_event(db: Session, user: User | None = None) -> HealthEvent | None:
    query = db.query(HealthEvent).filter(HealthEvent.end_date.is_(None))
    if user is not None:
        query = query.filter(HealthEvent.user_id == user.id)
    return query.order_by(HealthEvent.start_date.desc()).first()


def recent_events(db: Session, user: User | None = None, days: int = LOOKBACK_DAYS) -> list[HealthEvent]:
    cutoff = date.today() - timedelta(days=days)
    query = db.query(HealthEvent).filter(HealthEvent.start_date >= cutoff)
    if user is not None:
        query = query.filter(HealthEvent.user_id == user.id)
    return query.order_by(HealthEvent.start_date.desc()).all()


def days_lost_in(db: Session, start: date, end: date, user: User | None = None) -> int:
    """Ausfalltage in einem Zeitraum — für die Taper-Entscheidung.

    Gezählt wird die Überschneidung, nicht die Episodenlänge: eine Krankheit,
    die zwei Wochen vor dem Zeitraum begann, zählt nur mit ihrem Anteil.
    """
    query = db.query(HealthEvent).filter(HealthEvent.start_date <= end)
    if user is not None:
        query = query.filter(HealthEvent.user_id == user.id)

    tage = 0
    for event in query.all():
        event_ende = event.end_date or date.today()
        von, bis = max(event.start_date, start), min(event_ende, end)
        if bis >= von:
            tage += (bis - von).days + 1
    return tage


# --- Ableitung ---------------------------------------------------------------

def _easy_days_needed(event: HealthEvent) -> int:
    """Tage lockeres Training vor der ersten harten Einheit."""
    if event.kind == "injury":
        # Nach einer Verletzung entscheidet der Belastungsaufbau, nicht das
        # Immunsystem — deshalb großzügiger und ohne Fieberlogik.
        return min(MAX_EASY_DAYS, max(4, event.days))
    basis = event.days
    if event.fever or event.severity == "severe":
        basis = max(FEVER_MIN_EASY_DAYS, event.days)
    elif event.severity == "mild":
        basis = max(1, event.days // 2)
    return min(MAX_EASY_DAYS, basis)


def guidance(db: Session, user: User | None = None, today: date | None = None) -> Guidance:
    """Aktueller Zustand und die daraus folgenden Vorgaben."""
    today = today or date.today()

    laufend = open_event(db, user)
    if laufend is not None:
        tage = max(1, (today - laufend.start_date).days + 1)
        schwer = laufend.fever or laufend.severity == "severe"
        result = Guidance(
            status="sick",
            event=laufend,
            days_out=tage,
            can_train=not schwer,
            volume_factor=0.0 if schwer else (0.4 if laufend.severity == "moderate" else 0.6),
        )
        if laufend.kind == "injury":
            # Bei einer Verletzung ist Ausdauer nicht das Problem, sondern die
            # Belastung der betroffenen Struktur. Deshalb wird umverteilt statt
            # pauschal gekürzt — Schwimmen und Rad tragen weiter, wenn sie
            # schmerzfrei sind.
            if laufend.severity == "severe":
                result.lines.append(
                    "KEIN TRAINING an der betroffenen Struktur. Der Athlet ist verletzt "
                    "gemeldet (nicht belastbar). Plane nur, was nachweislich schmerzfrei "
                    "ist — im Zweifel Ruhetage und Mobilität."
                )
            elif laufend.severity == "moderate":
                result.lines.append(
                    "Der Athlet ist verletzt (Schmerz bei Belastung). Die betroffene "
                    "Disziplin wird ausgesetzt und durch Ersatztraining ersetzt, nicht "
                    "ersatzlos gestrichen — Umfang etwa 40 % der Norm. "
                    "Keine Intervalle, keine Sprünge, keine Bergläufe."
                )
                result.lines.append(ERSATZ_HINWEIS)
            else:
                result.lines.append(
                    "Der Athlet ist leicht verletzt, aber schmerzfrei belastbar. "
                    "Nur Z1/Z2, keine Intervalle, keine Steigerungsläufe, kein Bergtraining. "
                    "Umfang etwa 60 % der Norm."
                )
                result.lines.append(ERSATZ_HINWEIS)
            result.lines.append(
                "Regel für jede Einheit: Sie wird abgebrochen, sobald der Schmerz "
                "während der Belastung zunimmt. Schmerzfreiheit geht vor Umfang."
            )
        elif laufend.fever:
            result.lines.append(
                "KEIN TRAINING. Der Athlet hat Fieber. Plane ausschließlich Ruhetage, "
                "bis Fieberfreiheit gemeldet ist — Training mit Fieber kann eine "
                "Herzmuskelentzündung auslösen. Auch kein lockeres Ausrollen."
            )
        elif laufend.severity == "severe":
            result.lines.append(
                "KEIN TRAINING. Der Athlet ist krank gemeldet (schwer). "
                "Plane Ruhetage und optional Mobilität ohne Belastung."
            )
        elif laufend.severity == "moderate":
            result.lines.append(
                "Der Athlet ist krank (Husten/Gliederschmerzen). Höchstens 30–40 Minuten "
                "sehr locker in Z1, an höchstens drei Tagen. Keine Intervalle, kein Schwimmen "
                "im kalten Wasser, kein Krafttraining."
            )
        else:
            result.lines.append(
                "Der Athlet ist leicht erkältet (über dem Hals, kein Fieber). Nur Z1/Z2, "
                "höchstens 60 Minuten je Einheit, Umfang etwa 60 % der Norm. "
                "Keine Intervalle, keine Schwelle, kein VO2max."
            )

        # Die Notiz sagt, was betroffen ist — ohne sie kann der Plan bei einer
        # Verletzung nicht wissen, welche Disziplin er aussetzen soll.
        if laufend.note:
            result.lines.append(f"Angabe des Athleten: „{laufend.note}“")

        result.lines.append(
            f"{KIND_LABEL.get(laufend.kind, 'Ausfall')} seit {laufend.start_date} "
            f"({_tage(tage)}). Sobald Genesung gemeldet wird, gilt der Wiedereinstieg."
        )
        return result

    # Keine offene Meldung — aber vielleicht eine gerade beendete.
    letzte = None
    for event in recent_events(db, user):
        if event.end_date is not None:
            letzte = event
            break
    if letzte is None:
        return Guidance()

    seit = (today - letzte.end_date).days
    noetig = _easy_days_needed(letzte)
    easy_bis = letzte.end_date + timedelta(days=noetig)
    if today > easy_bis:
        return Guidance(status="healthy", days_since_end=seit)

    verbleibend = (easy_bis - today).days + 1
    result = Guidance(
        status="returning",
        event=letzte,
        days_out=letzte.days,
        days_since_end=seit,
        easy_until=easy_bis,
        can_train=True,
        # Nach langem Ausfall vorsichtiger: die ersten Tage tragen am wenigsten.
        volume_factor=min(1.0, 0.55 + 0.05 * seit),
    )
    result.lines.append(
        f"WIEDEREINSTIEG NACH {KIND_LABEL.get(letzte.kind, 'AUSFALL').upper()}: "
        f"{_tage(letzte.days)} Ausfall bis {letzte.end_date}, seit {_tage(seit)} wieder gesund. "
        f"Bis einschließlich {easy_bis} ({_tage(verbleibend)}) ausschließlich Z1/Z2 — "
        "keine Intervalle, keine Schwelle, kein VO2max, kein Wettkampftempo."
    )
    result.lines.append(
        f"Wochenumfang auf etwa {int(result.volume_factor * 100)} % der Norm. "
        "Die verpassten Einheiten werden NICHT nachgeholt — der Aufbau setzt dort an, "
        "wo der Athlet heute steht."
    )
    if letzte.kind == "injury":
        result.lines.append(ERSATZ_HINWEIS)

    if letzte.fever:
        result.lines.append(
            "Nach Fieber: die erste harte Einheit erst, wenn zwei lockere Einheiten "
            "ohne erhöhten Puls und ohne Nachwirkung absolviert wurden."
        )
    return result


def taper_adjustment(
    db: Session,
    race_date: date,
    total_weeks: int,
    user: User | None = None,
    today: date | None = None,
) -> dict:
    """Wie viel Taper nach den letzten Wochen noch sinnvoll ist.

    Krankheit in den letzten drei Wochen ist erzwungene Erholung. Wer danach
    noch die volle Taper-Woche mit halbiertem Umfang fährt, steht am Renntag
    nicht frisch, sondern platt da — die Form ist bereits abgebaut. Deshalb
    wird der Taper gekürzt und um kurze Reize ergänzt.
    """
    today = today or date.today()
    from core.race_types import MAX_TAPER_WEEKS, MIN_TAPER_WEEKS, phase_boundaries

    standard = next(
        (end - start + 1 for name, start, end in phase_boundaries(total_weeks) if name == "Taper"),
        MIN_TAPER_WEEKS,
    )
    fenster_start = min(today, race_date) - timedelta(days=21)
    verloren = days_lost_in(db, fenster_start, min(today, race_date), user)

    if verloren == 0:
        return {"taper_weeks": standard, "days_lost": 0, "lines": []}

    # Je angefangener Krankheitswoche eine Taper-Woche weniger, mindestens eine.
    gekuerzt = max(MIN_TAPER_WEEKS, standard - (verloren + 6) // 7)
    gekuerzt = min(gekuerzt, MAX_TAPER_WEEKS)

    lines = [
        f"TAPER ANGEPASST: {verloren} Ausfalltag{'e' if verloren != 1 else ''} in den letzten "
        "drei Wochen vor dem Rennen. "
        f"Diese Tage waren bereits Erholung. Taper deshalb auf {gekuerzt} statt {standard} "
        "Woche(n) verkürzen."
    ]
    if gekuerzt < standard:
        lines.append(
            "Statt weiterer Umfangsreduktion kurze Reize einplanen: 3–4 × 2 Minuten im "
            "Wettkampftempo mit voller Pause, alle zwei Tage. Ziel ist Spritzigkeit "
            "zurückzuholen, nicht zusätzliche Ruhe."
        )
    return {"taper_weeks": gekuerzt, "days_lost": verloren, "lines": lines}


def prompt_block(
    db: Session,
    user: User | None = None,
    race_date: date | None = None,
    total_weeks: int | None = None,
) -> str:
    """Die Gesundheitsvorgaben als Prompt-Abschnitt. Leer, wenn alles normal ist."""
    lines = list(guidance(db, user).lines)

    if race_date and total_weeks and race_date >= date.today():
        anpassung = taper_adjustment(db, race_date, total_weeks, user)
        lines.extend(anpassung["lines"])

    if not lines:
        return ""
    aufzaehlung = "\n".join(f"- {line}" for line in lines)
    return (
        "## GESUNDHEIT (KRITISCH — überschreibt Phasenvorgabe und Progression)\n\n"
        f"{aufzaehlung}\n\n"
        "Diese Vorgaben haben Vorrang vor der Saisonstruktur. Erkläre im "
        "coaching_comment kurz, was deshalb anders ist als geplant.\n\n---"
    )
