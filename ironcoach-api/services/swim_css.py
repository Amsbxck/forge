"""Critical Swim Speed aus dem Benchmark-Schwimmtest.

Der Test besteht aus 400 m und 200 m je maximal. Aus der Differenz ergibt
sich die Pace, die über lange Strecken durchhaltbar ist:

    CSS (Sekunden je 100 m) = (t400 − t200) / 2

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


def css_from_times(t400_s: float | None, t200_s: float | None) -> float | None:
    """CSS-Pace in Sekunden je 100 m."""
    if not t400_s or not t200_s:
        return None
    if t400_s <= t200_s:
        # Die längere Strecke muss länger dauern. Sonst sind die Zeiten
        # vertauscht oder eine davon gehört nicht zum Test.
        return None
    return round((t400_s - t200_s) / 2, 1)


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


def detect_from_session(session: TrainingSession) -> dict | None:
    """CSS aus den Runden einer Schwimmeinheit ableiten.

    Gibt None zurück, wenn die Runden fehlen oder keine passenden Strecken
    enthalten — dann bleibt nur die Eingabe von Hand.
    """
    runden = ((session.streams or {}).get("laps")) or []
    if not runden:
        return None

    r400 = _passende_runde(runden, 400)
    r200 = _passende_runde(runden, 200)
    if not r400 or not r200:
        return None

    css = css_from_times(r400["t"], r200["t"])
    if css is None:
        return None

    return {
        "css_pace_s_per_100m": css,
        "t400_s": r400["t"],
        "t200_s": r200["t"],
        # Der Puls während der 400 m. Er ist das, was der CSS-Test an
        # Herzfrequenz überhaupt hergibt — brauchbar als Schätzung für die
        # Schwelle im Wasser, aber eher zu hoch: 400 m maximal liegen über
        # der Schwelle.
        "hr_400": r400.get("hr"),
        "session_id": session.id,
        "date": str(session.session_date),
        "distanzen": {"400": round(r400["d"] * 1000), "200": round(r200["d"] * 1000)},
    }


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
