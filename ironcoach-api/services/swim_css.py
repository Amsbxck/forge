"""Critical Swim Speed aus dem Benchmark-Schwimmtest.

Der Test besteht aus zwei Strecken, je maximal. Aus der Differenz ergibt
sich die Pace, die über lange Strecken durchhaltbar ist:

    CSS (Sekunden je 100 m) = (t_lang − t_kurz) / ((d_lang − d_kurz) / 100)

Warum die Differenz und nicht einfach die 400-m-Zeit: Beide Strecken
enthalten dieselbe anaerobe Startreserve. Zieht man sie voneinander ab,
bleibt der rein aerobe Anteil übrig — genau der ist die Schwelle.

Zwei Wege führen zum Wert, und beide sind nötig:

* **Automatisch** aus den Runden der Uhr. Bequem, aber davon abhängig, dass
  überhaupt gelappt wurde und die Strecken erkennbar sind. Ein Ergebnis von
  hier ist ein Vorschlag, kein Messwert — es wird als solcher gekennzeichnet.
* **Von Hand**, indem die beiden Zeiten eingetragen werden. Immer verfügbar
  und immer richtig, weil der Athlet weiß, welche Bahn der Test war.
"""

import logging
from datetime import date

from sqlalchemy.orm import Session

from models import TrainingSession, User

logger = logging.getLogger(__name__)

# Wie stark eine Runde von 400 bzw. 200 m abweichen darf, um als Testabschnitt
# zu gelten. 10 % decken Bahnlängen von 25 m und 50 m sowie ungenaue
# Distanzmessung ab, ohne 300 m oder 500 m mitzunehmen.
TOLERANZ = 0.10


# Zulässige Streckenpaare, vom aussagekräftigsten zum anfängerfreundlichsten.
#
# Die Formel verlangt keine bestimmten Distanzen, nur eine Differenz. Je
# länger die beiden Strecken aber sind, desto kleiner ist der Anteil der
# anaeroben Startreserve am Ergebnis — und desto näher liegt der Wert an
# der tatsächlichen Schwelle.
#
# 400/200 bleibt deshalb das Protokoll der Wahl. 200/100 ist für alle
# gedacht, die 400 m nicht am Stück maximal schwimmen können: Dort entsteht
# sonst keine Messung, sondern eine Einbruchskurve. 100/50 ist die Variante
# für den Einstieg — grob, aber besser als eine geratene Zone.
PAARE = ((400, 200), (200, 100), (100, 50))


def css_from_times(
    t_lang_s: float | None,
    t_kurz_s: float | None,
    d_lang_m: int = 400,
    d_kurz_m: int = 200,
) -> float | None:
    """CSS-Pace in Sekunden je 100 m.

    Die Vorgabewerte halten die alte Signatur am Leben: Wer nur zwei Zeiten
    übergibt, rechnet weiter mit dem 400/200-Protokoll.
    """
    if not t_lang_s or not t_kurz_s:
        return None
    if d_lang_m <= d_kurz_m:
        return None
    if t_lang_s <= t_kurz_s:
        # Die längere Strecke muss länger dauern. Sonst sind die Zeiten
        # vertauscht oder eine davon gehört nicht zum Test.
        return None
    strecke_100m = (d_lang_m - d_kurz_m) / 100
    return round((t_lang_s - t_kurz_s) / strecke_100m, 1)


def format_pace(sekunden_je_100m: float | None) -> str | None:
    if not sekunden_je_100m:
        return None
    minuten = int(sekunden_je_100m // 60)
    rest = int(round(sekunden_je_100m % 60))
    return f"{minuten}:{rest:02d}/100m"


def _passende_runde(runden: list[dict], meter: int) -> dict | None:
    """Die schnellste Runde, deren Distanz zur gesuchten passt.

    Die schnellste, nicht die erste: Wer den Test wiederholt oder sich
    vorher einschwimmt, hat mehrere Runden dieser Länge.

    Die gespeicherten Runden tragen `d` in Kilometern und `t` in Sekunden —
    so legt sie `compact_laps` ab. Ein Zugriff über `distance`/`moving_time`
    fände nie etwas.
    """
    kandidaten = []
    for r in runden:
        km, sekunden = r.get("d"), r.get("t")
        if not km or not sekunden:
            continue
        if abs(km * 1000 - meter) <= meter * TOLERANZ:
            kandidaten.append(r)
    if not kandidaten:
        return None
    return min(kandidaten, key=lambda r: r["t"])


def guete(d_lang_m: int) -> str | None:
    """Wie belastbar ein Ergebnis aus diesem Paar ist.

    Kein Urteil über den Schwimmer, sondern über das Protokoll: Je kürzer
    die Strecken, desto grösser der Anteil der anaeroben Startreserve am
    Ergebnis — und desto zu schnell fällt die CSS aus. Wer daraufhin seine
    Dauereinheiten schwimmt, liegt dauerhaft über der Schwelle.
    """
    if d_lang_m >= 400:
        return None
    if d_lang_m >= 200:
        return (
            "Aus 200/100 m gerechnet. Etwas grober als 400/200 m — der Wert "
            "fällt eher zu schnell aus. Wiederhole den Test über die längeren "
            "Strecken, sobald 400 m am Stück gehen."
        )
    return (
        "Aus 100/50 m gerechnet — die gröbste Variante. Der Wert fällt "
        "spürbar zu schnell aus und taugt als erster Anhaltspunkt, nicht als "
        "Schwelle. Wiederhole den Test über längere Strecken, sobald es geht."
    )


def detect_from_session(session: TrainingSession) -> dict | None:
    """CSS aus den Runden einer Schwimmeinheit ableiten.

    Probiert die Streckenpaare der Reihe nach, vom aussagekräftigsten zum
    kürzesten, und nimmt das erste, das in den Runden vorkommt. Gibt None
    zurück, wenn die Runden fehlen oder kein Paar passt — dann bleibt nur
    die Eingabe von Hand.
    """
    runden = ((session.streams or {}).get("laps")) or []
    if not runden:
        return None

    for d_lang, d_kurz in PAARE:
        r_lang = _passende_runde(runden, d_lang)
        r_kurz = _passende_runde(runden, d_kurz)
        if not r_lang or not r_kurz:
            continue

        css = css_from_times(r_lang["t"], r_kurz["t"], d_lang, d_kurz)
        if css is None:
            continue

        return {
            "css_pace_s_per_100m": css,
            "t400_s": r_lang["t"],
            "t200_s": r_kurz["t"],
            "d_lang_m": d_lang,
            "d_kurz_m": d_kurz,
            "guete": guete(d_lang),
            # Der Puls während der längeren Strecke. Er ist das, was der Test
            # an Herzfrequenz hergibt — brauchbar als Schätzung für die
            # Schwelle im Wasser, aber eher zu hoch.
            #
            # Nur ab 200 m: Über 100 m maximal liegt der Puls so weit über
            # der Schwelle, dass der übliche Abschlag von fünf Prozent ihn
            # nicht mehr einfängt. Lieber kein Wert als ein falscher.
            "hr_400": r_lang.get("hr") if d_lang >= 200 else None,
            "session_id": session.id,
            "date": str(session.session_date),
            "distanzen": {
                str(d_lang): round(r_lang["d"] * 1000),
                str(d_kurz): round(r_kurz["d"] * 1000),
            },
        }

    return None


def detect_recent(db: Session, user: User | None = None, days: int = 28) -> dict | None:
    """Jüngster auswertbarer Schwimmtest im Zeitraum."""
    from datetime import timedelta

    cutoff = date.today() - timedelta(days=days)
    query = db.query(TrainingSession).filter(
        TrainingSession.discipline == "swim",
        TrainingSession.session_date >= cutoff,
        TrainingSession.deleted_at.is_(None),
    )
    if user is not None:
        query = query.filter(TrainingSession.user_id == user.id)

    for session in query.order_by(TrainingSession.session_date.desc()).all():
        treffer = detect_from_session(session)
        if treffer:
            return treffer
    return None
