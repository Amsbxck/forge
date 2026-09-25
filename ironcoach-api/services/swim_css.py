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


def pace_je_100m(meter: float, sekunden: float) -> float | None:
    """Sekunden je 100 m, oder None bei unbrauchbaren Werten."""
    if not meter or not sekunden or meter <= 0 or sekunden <= 0:
        return None
    return sekunden / (meter / 100)


def paar_plausibel(
    t_lang_s: float, t_kurz_s: float, d_lang_m: int, d_kurz_m: int
) -> str | None:
    """Beschreibt, was gegen dieses Streckenpaar spricht — oder None.

    Der Test unterstellt **zwei maximale** Versuche. Ist das kürzere Stück
    nicht deutlich schneller als das längere, war es keiner: Dann steckt in
    beiden Zeiten derselbe Anteil Ausdauer, die Differenz wird zu klein und
    die CSS fällt viel zu schnell aus.

    Rechnerisch ist der Zusammenhang unmittelbar. Für 400/200 gilt

        CSS = 2 x Pace(400) - Pace(200)

    Sind beide Pace gleich, ist die CSS gleich der 400-m-Pace — die App
    behauptete dann, das Renntempo über 400 m sei dauerhaft haltbar.
    """
    p_lang = pace_je_100m(d_lang_m, t_lang_s)
    p_kurz = pace_je_100m(d_kurz_m, t_kurz_s)
    if p_lang is None or p_kurz is None:
        return "Zu einer der beiden Strecken fehlen Distanz oder Zeit."

    for name, pace in ((f"{d_lang_m} m", p_lang), (f"{d_kurz_m} m", p_kurz)):
        if pace < MIN_PACE_S_JE_100M:
            return f"Die Zeit über {name} ist für Schwimmen unmöglich schnell."
        if pace > MAX_PACE_S_JE_100M:
            return f"Die Zeit über {name} ist unplausibel langsam."

    if p_kurz >= p_lang:
        return (
            f"Über {d_kurz_m} m warst du je 100 m nicht schneller als über "
            f"{d_lang_m} m ({format_pace(p_kurz)} gegen {format_pace(p_lang)}). "
            f"Der Test setzt zwei maximale Versuche voraus — die kürzere "
            f"Strecke muss deutlich schneller sein. Meist fehlte die Erholung "
            f"dazwischen. Wiederhole sie mit mehr Pause, oder trag die CSS "
            f"direkt ein, wenn du sie kennst."
        )
    return None


def format_pace(sekunden_je_100m: float | None) -> str | None:
    """Pace als m:ss je 100 m.

    Zuerst auf ganze Sekunden runden, dann teilen. Umgekehrt entsteht bei
    119,5 Sekunden die Ausgabe "1:60": Die Minuten kommen aus der
    ungerundeten Zahl, die Sekunden aus dem gerundeten Rest.
    """
    if not sekunden_je_100m:
        return None
    ganz = int(round(sekunden_je_100m))
    return f"{ganz // 60}:{ganz % 60:02d}/100m"


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


# Gültigkeitsbereich des Modells hinter der CSS.
#
# Die Rechnung unterstellt, dass sich Strecke und Zeit im geprüften Bereich
# linear verhalten — das gilt für Belastungen von etwa zwei bis fünfzehn
# Minuten. Darunter dominiert die anaerobe Startreserve, und die Gerade
# kippt: Die CSS fällt zu schnell aus.
#
# Entscheidend ist damit die **Dauer**, nicht die Strecke. Das ist der
# Grund, warum die kurzen Paare für Anfänger taugen und für schnelle
# Schwimmer nicht: 100/50 m sind bei 1:20/100 m nur 75 und 35 Sekunden —
# weit unterhalb des Bereichs. Bei 2:30/100 m sind dieselben Strecken
# 2:20 und 1:06 und damit einwandfrei.
MIN_DAUER_LANG_S = 120
MIN_DAUER_KURZ_S = 60

# Ab welcher Streckenlänge aus dem Test ein Schwellenpuls abgeleitet wird.
#
# Nur aus dem 400-m-Protokoll, und das aus zwei Gründen. Es ist das
# einzige, für das die Literatur diesen Weg beschreibt — Puls der 400 m als
# Schwelle. Und je kürzer die Strecke, desto weiter liegt der Puls darüber:
# Ein 200-m-Sprint dauert zweieinhalb Minuten, dort ist der Wert keine
# Schwelle mehr, sondern fast das Maximum.
#
# Bei den kürzeren Paaren bleibt das Feld leer und wird von Hand gesetzt.
# Lieber kein Wert als einer, der die Schwelle systematisch zu hoch ansetzt.
MIN_STRECKE_FUER_HR_M = 400

# Grenzen, innerhalb derer eine Runde überhaupt als Schwimmen durchgeht.
# Der Weltrekord über 100 m Freistil liegt bei rund 46 Sekunden; alles
# Schnellere ist ein Aufzeichnungsfehler. Nach oben grosszügig, damit
# Anfänger nicht herausfallen.
#
# Anlass: In den Daten steckte eine Runde "600 m in 3 Sekunden" — ein
# Artefakt aus einer Pause. Als schnellste Runde ihrer Länge wäre sie
# ausgewählt worden.
MIN_PACE_S_JE_100M = 45
MAX_PACE_S_JE_100M = 300


def guete(t_lang_s: float | None, t_kurz_s: float | None) -> str | None:
    """Vorbehalt zum Ergebnis, oder None, wenn es keinen gibt.

    Bewertet die Zeiten, nicht die Strecken. Eine Bewertung nach Metern
    hätte den Anfänger gewarnt, für den das kurze Paar gerade richtig ist,
    und den schnellen Schwimmer durchgewinkt, bei dem es nicht trägt.
    """
    if not t_lang_s or not t_kurz_s:
        return None
    if t_lang_s >= MIN_DAUER_LANG_S and t_kurz_s >= MIN_DAUER_KURZ_S:
        return None

    def mmss(sek):
        return f"{int(sek // 60)}:{int(sek % 60):02d}"

    return (
        f"Die Testzeiten sind kurz ({mmss(t_lang_s)} und {mmss(t_kurz_s)}). "
        f"Die Rechnung setzt Belastungen ab etwa zwei Minuten voraus; darunter "
        f"schlägt die anaerobe Startreserve durch und der Wert fällt zu schnell "
        f"aus. Nimm längere Strecken, damit beide Zeiten darüber liegen."
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

    letzter_einwand = None
    for d_lang, d_kurz in PAARE:
        r_lang = _passende_runde(runden, d_lang)
        r_kurz = _passende_runde(runden, d_kurz)
        if not r_lang or not r_kurz:
            continue

        einwand = paar_plausibel(r_lang["t"], r_kurz["t"], d_lang, d_kurz)
        if einwand:
            # Nicht stillschweigend das nächstkürzere Paar nehmen: Das läge
            # dann ebenso daneben, nur unauffälliger. Der Grund wird
            # gemeldet, damit er behoben werden kann.
            letzter_einwand = einwand
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
            "guete": guete(r_lang["t"], r_kurz["t"]),
            # Der Puls während der längeren Strecke. Er ist das, was der Test
            # an Herzfrequenz hergibt — brauchbar als Schätzung für die
            # Schwelle im Wasser, aber eher zu hoch.
            #
            # Siehe MIN_STRECKE_FUER_HR_M — nur aus dem 400-m-Protokoll.
            "hr_400": r_lang.get("hr") if d_lang >= MIN_STRECKE_FUER_HR_M else None,
            "session_id": session.id,
            "date": str(session.session_date),
            "distanzen": {
                str(d_lang): round(r_lang["d"] * 1000),
                str(d_kurz): round(r_kurz["d"] * 1000),
            },
        }

    # Kein brauchbares Paar. Wenn es an der Plausibilität lag, wird der Grund
    # zurückgegeben statt nur "nichts gefunden" — sonst sucht der Athlet den
    # Fehler bei der App statt beim Test.
    if letzter_einwand:
        return {"einwand": letzter_einwand}
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
        if treffer and not treffer.get("einwand"):
            return treffer
    return None
