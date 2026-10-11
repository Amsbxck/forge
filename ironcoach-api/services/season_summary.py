"""Langzeitkontext für die Planung — kompakt statt vollständig.

Der Coach sah bisher die letzten 14 Tage im Detail und sonst nichts. Für die
Frage „was mache ich nächste Woche" reicht das meistens, aber an drei Stellen
bricht es:

* **Nach einer Lücke.** Wer zwei Wochen krank war, hat ein leeres Fenster.
  Der Coach weiß dann nicht, ob der Athlet vorher 4 oder 12 Stunden pro Woche
  trainiert hat, und plant den Wiedereinstieg ins Blaue.
* **Bei der Progression.** „Der lange Lauf wird länger" braucht einen
  Bezugspunkt. Ohne die bisherige Bestmarke wird die nächste Steigerung
  geraten — mal zu klein, mal zu groß.
* **Bei der Formentwicklung.** Ob die Grundlage seit Wochen wächst oder
  abbaut, steht in CTL und TSB. Beides war im Prompt gar nicht enthalten,
  obwohl die App es berechnet und anzeigt.

Deshalb hier eine Zusammenfassung, die wenige hundert Token kostet: Formkurve
mit Trend, Wochenverlauf, Bestmarken der Saison, Ausfalltage. Die 14 Tage im
Detail bleiben daneben bestehen — das eine ersetzt das andere nicht.
"""

import logging
import math
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy.orm import Session

from core.training_types import EXTERN_GEPLANT, FUN_DISCIPLINES
from models import HealthEvent, PlannedSession, TrainingSession, User

logger = logging.getLogger(__name__)

# Zeitkonstanten der Formkurve, identisch zur Anzeige im Dashboard.
K_ATL = 1 - math.exp(-1 / 7)
K_CTL = 1 - math.exp(-1 / 42)

WOCHEN_IM_VERLAUF = 10


def _pmc(sessions: list[TrainingSession], bis: date) -> list[dict]:
    """Fitness, Ermüdung und Form je Tag."""
    tages_tss: dict[date, float] = defaultdict(float)
    for s in sessions:
        if s.tss and s.session_date:
            tages_tss[s.session_date] += s.tss
    if not tages_tss:
        return []

    tag = min(tages_tss)
    atl = ctl = 0.0
    verlauf = []
    while tag <= bis:
        # Die Form eines Tages ist der Stand von **gestern** — CTL minus ATL
        # vor dem heutigen Training. So ist sie definiert, und so muss sie
        # auch sein: Sie beantwortet "wie gehe ich in diesen Tag hinein".
        #
        # Vorher wurde sie nach der Aktualisierung gebildet, also
        # einschliesslich der Einheit dieses Tages. Damit zog jedes Training
        # die eigene Form herunter: Nach einer harten Einheit stand dort ein
        # tief negativer Wert, obwohl der Athlet ausgeruht in den Tag
        # gegangen war. Der Coach liest diese Zahl und hätte auf eine
        # Ermüdung reagiert, die erst durch das gerade absolvierte Training
        # entstand.
        tsb = ctl - atl

        tss = tages_tss.get(tag, 0.0)
        atl += (tss - atl) * K_ATL
        ctl += (tss - ctl) * K_CTL
        # CTL und ATL dagegen als Tagesende-Werte, wie üblich.
        verlauf.append({"datum": tag, "ctl": ctl, "atl": atl, "tsb": tsb})
        tag += timedelta(days=1)
    return verlauf


BLOCK_WOCHEN = 4
BLOECKE = 3


def _progression(sessions: list[TrainingSession], heute: date) -> dict:
    """Die längste Einheit je Disziplin, je Vierwochenblock.

    Nicht ein einzelner Rekord, sondern eine Reihe. Ein Bestwert beantwortet
    nur „was ging einmal" — für die Planung zählt aber, ob die lange Einheit
    wächst, steht oder schrumpft. „12 → 15 → 18 km" ist eine Auskunft, aus
    der sich der nächste Schritt ableiten lässt; „18 km" allein ist keine.

    Nur Dauer und Strecke, also Umfang. Ein Leistungsbestwert ließe sich aus
    Trainingsschnitten nicht ehrlich bilden — der Schnitt über eine ganze
    Einheit belohnt kurze und bestraft lange. Wie schnell jemand ist, steht
    in den Schwellenwerten; ob die Vorgaben zu leicht sind, in der
    Übererfüllung weiter unten.

    Ohne Schwimmen (`EXTERN_GEPLANT`): dessen Aufbau steuert ein externer
    Plan, und eine Reihe daraus hätte der Coach als Auftrag zum Steigern
    gelesen.
    """
    reihen: dict[str, list] = {}
    for i in range(BLOECKE):
        # Block 0 ist der jüngste; rückwärts, damit die Reihe chronologisch endet.
        ende = heute - timedelta(weeks=BLOCK_WOCHEN * i)
        start = ende - timedelta(weeks=BLOCK_WOCHEN)
        for s in sessions:
            d = (s.discipline or "").lower()
            # Schwimmen bleibt draußen: sein Aufbau steht im externen Plan,
            # und eine Reihe daraus hätte der Coach als Progressionsauftrag
            # gelesen. Rest und Gym haben keinen Umfang, der sich steigert.
            # Wanderungen und Crosstraining ebenso: `FUN_DISCIPLINES` gibt es
            # genau dafür, und „hike: 14,2 km → – → –" las sich wie eine
            # eingebrochene Reihe, obwohl es nur ein Ausflug war.
            if d in ("rest", "gym") or d in EXTERN_GEPLANT or d in FUN_DISCIPLINES:
                continue
            # Arbeitswege sind kein Trainingsumfang. Als Maximum gewinnen sie
            # selten, aber eine lange Heimfahrt kann die Reihe verfälschen.
            if getattr(s, "is_commute", False):
                continue
            if not (start < s.session_date <= ende):
                continue
            reihe = reihen.setdefault(d, [None] * BLOECKE)
            eintrag = reihe[i] or {"min": 0, "km": 0.0}
            eintrag["min"] = max(eintrag["min"], s.duration_min or 0)
            eintrag["km"] = max(eintrag["km"], s.distance_km or 0.0)
            reihe[i] = eintrag
    # Chronologisch: ältester Block zuerst.
    return {d: list(reversed(r)) for d, r in reihen.items()}


# Eine Maßeinheit je Disziplin, über alle Blöcke dieselbe.
#
# Vorher wurde km genommen, wenn eine Strecke vorlag, und sonst Minuten. Bei
# einem Block voller Rollentraining ohne Strecke entstand daraus eine Reihe
# wie „160,7 km → 240 min → 150,0 km" — drei Zahlen, die nichts miteinander
# zu tun haben, unter einer Überschrift, die eine Richtung behauptet.
#
# Laufen in Kilometern, weil die Strecke die verletzungsrelevante Größe ist
# (dieselbe, auf die sich die Einzellauf-Grenze bezieht). Rad in Minuten, weil
# die Dauer drinnen und draußen vergleichbar bleibt.
PROGRESSION_EINHEIT = {
    "run": "km",
    "brick": "km",
    "bike": "min",
}


def progression_wert(disziplin: str, eintrag: dict | None) -> str:
    """Ein Blockwert der Reihe, in der Einheit dieser Disziplin."""
    if eintrag is None:
        return "–"
    einheit = PROGRESSION_EINHEIT.get(disziplin)
    if einheit == "km" and eintrag["km"]:
        return f"{eintrag['km']:.1f} km"
    if einheit == "min" and eintrag["min"]:
        return f"{eintrag['min']} min"
    # Keine feste Einheit oder der bevorzugte Wert fehlt: nehmen, was da ist.
    if eintrag["km"]:
        return f"{eintrag['km']:.1f} km"
    if eintrag["min"]:
        return f"{eintrag['min']} min"
    return "–"


# Ein einzelner Lauf mehr als 10 % länger als der längste der letzten 30 Tage
# erhöht das Verletzungsrisiko deutlich (Frandsen 2025, 5.205 Läufer, 588.000
# Läufe: +64 % bei 10–30 % darüber, +128 % oberhalb von 100 %).
SPRUNG_ANTEIL = 1.10
SPRUNG_FENSTER_TAGE = 30

# Zweite, schwächere Klammer: der **Wochen**umfang. Über zwei Wochen mehr als
# 30 % Zuwachs war bei 874 Laufanfängern mit einem Verletzungsrisiko von 1,59
# verbunden (Nielsen 2014) — grenzwertig (p = 0,07), und Frandsen fand für die
# Wochenstrecke gar keinen klaren Zusammenhang. Deshalb als Hinweis und nicht
# als zweite harte Decke.
#
# Nötig ist sie trotzdem: Die Einzellauf-Grenze wächst um 10 % pro Woche, wenn
# man sie ausnutzt. Täte der Coach das bei jedem Lauf, stiege der Wochenumfang
# ebenfalls um 10 % je Woche — also 21 % über zwei Wochen und damit knapp
# unter dieser Grenze. Ohne sie fehlte jede Begrenzung für den Fall, dass
# zusätzlich Einheiten dazukommen.
WOCHEN_ZUWACHS_GRENZE = 0.30
WOCHEN_IM_UMFANG = 4


def _lauf_obergrenze(sessions: list[TrainingSession], heute: date) -> dict | None:
    """Wie lang der nächste Lauf höchstens sein darf.

    Bewusst nur Laufen. Die Regel stammt aus einer Laufkohorte und hat einen
    stoßbedingten Mechanismus; für das Rad gibt es keine Entsprechung, und sie
    dorthin zu übertragen wäre eine Behauptung ohne Grundlage.

    Gerechnet wird über die Strecke, nicht über die Dauer: ein langsamer langer
    Lauf und ein schneller kurzer können gleich lange dauern und belasten die
    Strukturen völlig verschieden.

    Das ist eine Leitplanke, keine Sperre. Sie steht neben der Umfangsreihe,
    damit Richtung und Obergrenze zusammen gelesen werden — die Reihe sagt, ob
    gesteigert werden soll, diese Zahl, wie viel auf einmal.
    """
    laeufe = [
        s for s in sessions
        if (s.discipline or "").lower() in ("run", "brick")
        and (s.distance_km or 0) > 0
    ]
    grenze = heute - timedelta(days=SPRUNG_FENSTER_TAGE)
    im_fenster = [s for s in laeufe if s.session_date > grenze]
    if not im_fenster:
        return None

    laengste = max(im_fenster, key=lambda s: s.distance_km)
    laengster = laengste.distance_km

    # War der Lauf, der die Grenze bestimmt, selbst ein Sprung?
    #
    # Ohne diese Prüfung belohnte die Regel ihren eigenen Verstoß: Amirs Lauf
    # am 05.07. über 21,2 km lag 99 % über der damals geltenden Grenze von
    # 10,7 km — und hob sie am Tag danach auf 23,4 km. Der Sprung wurde damit
    # zur neuen Normalität erklärt, obwohl die Studie nur sagt, dass er das
    # Risiko erhöht, nicht dass die Strecke jetzt sicher ist.
    #
    # Dasselbe passiert, wenn jemand einen Plantag durch einen langen Lauf
    # ersetzt: Die Regel steuert den **Plan**, nicht die Ausführung.
    vorher = [
        s.distance_km for s in laeufe
        if laengste.session_date - timedelta(days=SPRUNG_FENSTER_TAGE)
        < s.session_date < laengste.session_date
    ]
    sprung_anteil = None
    if vorher:
        damals_erlaubt = max(vorher) * SPRUNG_ANTEIL
        if laengster > damals_erlaubt:
            sprung_anteil = round((laengster / damals_erlaubt - 1) * 100)

    return {
        "laengster_km": round(laengster, 1),
        "laengster_am": laengste.session_date,
        "hoechstens_km": round(laengster * SPRUNG_ANTEIL, 1),
        # Wie weit der bestimmende Lauf selbst über seiner Grenze lag, oder
        # None, wenn er im Rahmen war.
        "war_selbst_sprung": sprung_anteil,
        "laeufe": len(im_fenster),
    }


def _lauf_wochenumfang(sessions: list[TrainingSession], heute: date) -> dict | None:
    """Laufkilometer je Woche und der Zuwachs über zwei Wochen.

    Die Einzellauf-Grenze begrenzt einen Lauf, nicht die Woche. Wächst sie um
    10 % je Woche und nutzt der Coach sie bei jedem Lauf aus, steigt der
    Wochenumfang mit — rund 21 % über zwei Wochen. Das liegt knapp unter der
    Grenze von Nielsen, aber es fehlte jede Rückmeldung darüber, und für den
    Fall, dass zusätzlich Einheiten dazukommen, gab es überhaupt keine
    Begrenzung.

    Montagsbasiert, damit die Zahlen zu den übrigen Wochentabellen passen.
    """
    montag = heute - timedelta(days=heute.weekday())
    wochen: list[float] = []
    for i in range(WOCHEN_IM_UMFANG, 0, -1):
        start = montag - timedelta(weeks=i)
        ende = start + timedelta(days=6)
        km = sum(
            s.distance_km or 0.0 for s in sessions
            if (s.discipline or "").lower() in ("run", "brick")
            and start <= s.session_date <= ende
            and not getattr(s, "is_commute", False)
        )
        wochen.append(round(km, 1))

    if not any(wochen):
        return None

    # Zuwachs der letzten gegen die vorletzte abgeschlossene Woche, über zwei
    # Wochen gerechnet wie bei Nielsen.
    zuwachs = None
    if len(wochen) >= 3 and wochen[-3] > 0:
        zuwachs = round((wochen[-1] / wochen[-3] - 1) * 100)

    return {
        "wochen_km": wochen,
        "zuwachs_zwei_wochen": zuwachs,
        "grenze_prozent": int(WOCHEN_ZUWACHS_GRENZE * 100),
    }


def _belastbarkeit(db: Session, beginn: date, heute: date) -> dict:
    """Wurde mehr oder weniger gemacht als vorgegeben?

    Das ist das eigentliche Progressionssignal. Wer eine Vorgabe regelmäßig
    übertrifft — länger, mehr Intervalle, schneller —, bekommt zu wenig
    vorgesetzt. Wer sie regelmäßig verfehlt, zu viel. Ein Rekord sagt dazu
    nichts: Er kann aus einem einzelnen guten Tag stammen und trotzdem an der
    Grenze gelegen haben.

    Gerechnet wird gegen die zugeordnete Planeinheit, nicht gegen den
    Freitext der Abweichungsnotiz — Zahlen aus einem Satz zurückzulesen wäre
    an jedem neuen Formulierungsdetail zerbrochen.
    """
    paare = (
        db.query(TrainingSession, PlannedSession)
        .join(PlannedSession, TrainingSession.planned_session_id == PlannedSession.id)
        .filter(TrainingSession.session_date >= beginn,
                TrainingSession.session_date <= heute)
        # Schwimmen zählt nicht: Die Vorgabe ist dort nur ein Termin mit
        # Dauer, der Inhalt kommt aus dem externen Plan. Wer eine 45-Minuten-
        # Vorgabe mit einem 70-Minuten-Vereinstraining füllt, hat nichts
        # übererfüllt — hier wäre daraus "verträgt mehr Umfang" geworden, und
        # der Coach hätte Rad und Lauf nachgeschärft.
        # Gym, Wanderungen und Crosstraining aus demselben Grund: Der Coach
        # gibt dort nur Termin und Dauer vor, nicht den Inhalt. Wer 110 statt
        # 60 Minuten im Kraftraum bleibt, hat nichts übererfüllt — und genau
        # das ist passiert: Bei Amir waren **alle vier** Beispiele unter
        # "zuletzt darüber" Gym-Einheiten. Aus ihnen hätte der Coach
        # geschlossen, die Schlüsseleinheiten in Rad und Lauf seien zu
        # niedrig angesetzt.
        .filter(TrainingSession.discipline.notin_(
            tuple(EXTERN_GEPLANT) + ("gym",) + tuple(FUN_DISCIPLINES)
        ))
        .all()
    )
    mehr, weniger, verworfen, beispiele = 0, 0, 0, []
    lauf_mehr = 0
    # Verworfene Paare nach Disziplin und Richtung. Ein einzelner Ausreißer ist
    # ein Zuordnungsfehler; drei in dieselbe Richtung sind eine Auskunft.
    weit_darueber: dict[str, list[float]] = {}
    for ist, soll in paare:
        if not soll.duration_min or not ist.duration_min:
            continue
        verhaeltnis = ist.duration_min / soll.duration_min
        # Wer das Dreifache der Vorgabe absolviert, hat nicht übererfüllt —
        # da wurde eine ungeplante lange Ausfahrt auf einen kurzen
        # Regenerationsslot gebucht. Solche Paare als Belastbarkeit zu zählen
        # hieße, aus einem Zuordnungsfehler eine Trainingsempfehlung zu machen.
        #
        # Diese Annahme bricht aber, sobald sie sich wiederholt. Bei Amir waren
        # **alle drei** Radeinheiten des Zeitraums so: 327 statt 75, 320 statt
        # 90, 244 statt 55 Minuten. Das ist kein Zuordnungsfehler dreimal
        # hintereinander, sondern ein systematisch zu kurz angesetzter
        # Radumfang — und ausgerechnet das Signal, das genau das melden soll,
        # war dafür blind. Deshalb werden sie weiter nicht mitgezählt, aber
        # festgehalten.
        if verhaeltnis > 3 or verhaeltnis < 0.25:
            verworfen += 1
            if verhaeltnis > 3:
                weit_darueber.setdefault(
                    (ist.discipline or "?").lower(), []
                ).append(verhaeltnis)
            continue
        diff = ist.duration_min - soll.duration_min
        # Zehn Prozent Toleranz: Darunter ist es Alltag, keine Aussage.
        if diff > soll.duration_min * 0.10:
            mehr += 1
            if (ist.discipline or "").lower() in ("run", "brick"):
                lauf_mehr += 1
            beispiele.append(
                f"{ist.session_date} {ist.discipline}: {ist.duration_min} statt "
                f"{soll.duration_min} min"
            )
        elif diff < -soll.duration_min * 0.10:
            weniger += 1
    return {
        "mehr": mehr,
        "weniger": weniger,
        # Getrennt ausgewiesen, weil daraus beim Laufen nicht "mehr vorgeben"
        # folgt: dieselbe Übererfüllung ist dort das Verletzungsmuster aus der
        # Einzellauf-Regel. Beide Schlüsse im selben Prompt wären ein
        # Widerspruch, und der Coach müsste raten, welcher gilt.
        "lauf_mehr": lauf_mehr,
        "verworfen": verworfen,
        # Disziplinen, in denen mindestens zwei Einheiten das Dreifache der
        # Vorgabe überschritten: {"bike": (3, 3.6)} heißt dreimal, im Schnitt
        # das 3,6-fache.
        "weit_darueber": {
            d: (len(v), round(sum(v) / len(v), 1))
            for d, v in weit_darueber.items() if len(v) >= 2
        },
        "gewertet": mehr + weniger,
        "zugeordnet": len(paare),
        "beispiele": beispiele[-4:],
    }


def _einhaltung(db: Session, beginn: date, heute: date) -> dict[date, dict]:
    """Geplant gegen tatsächlich erledigt, je Woche.

    Nur die Einheiten des **jüngsten** Plans einer Woche zählen. Jede
    Neuerstellung projiziert erneut, ohne die alte Projektion zu entfernen —
    in den Daten stehen für manche Woche drei Pläne à sieben Einheiten. Über
    alle gezählt käme eine Einhaltung von einem Drittel des wahren Werts
    heraus, und der Coach würde einen Athleten zurückfahren, der in
    Wirklichkeit alles absolviert hat.
    """
    zeilen = (
        db.query(PlannedSession)
        .filter(PlannedSession.planned_date >= beginn, PlannedSession.planned_date <= heute)
        .all()
    )
    if not zeilen:
        return {}

    # Je Woche der höchste plan_id — die zuletzt erstellte Fassung.
    jung: dict[date, int] = {}
    for p in zeilen:
        montag = p.planned_date - timedelta(days=p.planned_date.weekday())
        if p.plan_id > jung.get(montag, 0):
            jung[montag] = p.plan_id

    aus: dict[date, dict] = {}
    for p in zeilen:
        montag = p.planned_date - timedelta(days=p.planned_date.weekday())
        if p.plan_id != jung[montag]:
            continue
        w = aus.setdefault(
            montag, {"geplant": 0, "erledigt": 0, "verschoben": 0, "ersetzt": []}
        )
        w["geplant"] += 1
        if p.status == "completed":
            w["erledigt"] += 1
        elif p.status == "moved":
            w["verschoben"] += 1
        elif p.status == "replaced" and p.replacement:
            dauer = f", {p.replacement_min} min" if p.replacement_min else ""
            w["ersetzt"].append(f"{p.discipline} → {p.replacement}{dauer}")
    return aus


def build(db: Session, user: User | None = None, heute: date | None = None) -> dict:
    """Zahlen für den Langzeitkontext."""
    heute = heute or date.today()
    beginn = heute - timedelta(weeks=WOCHEN_IM_VERLAUF)

    query = db.query(TrainingSession).filter(TrainingSession.deleted_at.is_(None))
    if user is not None:
        query = query.filter(TrainingSession.user_id == user.id)
    alle = query.order_by(TrainingSession.session_date.asc()).all()
    if not alle:
        return {"status": "keine_daten"}

    verlauf = _pmc(alle, heute)
    jetzt = verlauf[-1] if verlauf else None
    vor_vier = next(
        (p for p in reversed(verlauf) if p["datum"] <= heute - timedelta(weeks=4)),
        None,
    )

    # Wochenweise Summen — je Woche eine Zeile, nicht je Einheit.
    # Trainingsfreie Wochen bekommen ausdrücklich eine Nullzeile: Eine
    # fehlende Zeile liest sich als „keine Daten", eine Null als „nicht
    # trainiert". Der Unterschied entscheidet, ob der Coach den Wiedereinstieg
    # vorsichtig plant oder die Pause gar nicht bemerkt.
    wochen: dict[date, dict] = {}
    erster_montag = beginn - timedelta(days=beginn.weekday())
    letzter_montag = heute - timedelta(days=heute.weekday())
    m = erster_montag
    while m <= letzter_montag:
        wochen[m] = {"tss": 0.0, "min": 0, "anzahl": 0, "wege": 0, "wege_min": 0, "disziplinen": defaultdict(int)}
        m += timedelta(days=7)

    for s in alle:
        if s.session_date < beginn:
            continue
        montag = s.session_date - timedelta(days=s.session_date.weekday())
        w = wochen.setdefault(montag, {"tss": 0.0, "min": 0, "anzahl": 0, "wege": 0, "wege_min": 0, "disziplinen": defaultdict(int)})

        w["tss"] += s.tss or 0
        w["min"] += s.duration_min or 0
        w["anzahl"] += 1
        w["disziplinen"][(s.discipline or "?").lower()] += 1
        # Arbeitswege getrennt mitzählen. Sie bleiben in TSS und Stunden — es
        # ist echte Last —, dürfen aber nicht als Trainingseinheiten gelten.
        # Der Grund steht in `prompt_block`: Dort entscheidet die Anzahl, ob
        # dem Coach "Umfang erreicht" gemeldet wird.
        if getattr(s, "is_commute", False):
            w["wege"] += 1
            w["wege_min"] += s.duration_min or 0

    # Gesundheitsereignisse — und ihre Zuordnung zu den Wochen.
    hquery = db.query(HealthEvent).filter(
        (HealthEvent.end_date.is_(None)) | (HealthEvent.end_date >= beginn)
    )
    if user is not None:
        hquery = hquery.filter(HealthEvent.user_id == user.id)
    ereignisse = hquery.all()
    ausfalltage = sum(e.days for e in ereignisse)

    # Eine leere Woche mit gemeldeter Krankheit ist etwas anderes als eine
    # leere Woche ohne Grund: das eine ist eine Pause, aus der man
    # zurückkommt, das andere ein Formverlust, der benannt gehört. Ohne die
    # Zuordnung sehen beide gleich aus — und der Coach müsste raten.
    grund_je_woche: dict[date, str] = {}
    for e in ereignisse:
        ende = e.end_date or heute
        tag = e.start_date
        bezeichnung = "Verletzung" if e.kind == "injury" else "Krankheit"
        text = f"{bezeichnung} gemeldet ({e.severity}{', Fieber' if e.fever else ''})"
        while tag <= ende:
            grund_je_woche[tag - timedelta(days=tag.weekday())] = text
            tag += timedelta(days=1)

    einhaltung = _einhaltung(db, beginn, heute)

    return {
        "status": "ok",
        "form": {
            "ctl": round(jetzt["ctl"], 1) if jetzt else None,
            "atl": round(jetzt["atl"], 1) if jetzt else None,
            "tsb": round(jetzt["tsb"], 1) if jetzt else None,
            "ctl_vor_4_wochen": round(vor_vier["ctl"], 1) if vor_vier else None,
        },
        "wochen": [
            {
                "start": montag,
                "tss": round(w["tss"]),
                "stunden": round(w["min"] / 60, 1),
                "anzahl": w["anzahl"],
                "wege": w["wege"],
                "wege_stunden": round(w["wege_min"] / 60, 1),
                "disziplinen": dict(w["disziplinen"]),
                "grund": grund_je_woche.get(montag),
                "einhaltung": einhaltung.get(montag),
            }
            for montag, w in sorted(wochen.items())
        ],
        "progression": _progression(alle, heute),
        "lauf_obergrenze": _lauf_obergrenze(alle, heute),
        "lauf_wochenumfang": _lauf_wochenumfang(alle, heute),
        "belastbarkeit": _belastbarkeit(db, beginn, heute),
        "ausfalltage": ausfalltage,
        "einheiten_gesamt": len(alle),
    }


def prompt_block(db: Session, user: User | None = None, heute: date | None = None) -> str:
    """Der Langzeitkontext als Prompt-Abschnitt."""
    daten = build(db, user, heute)
    if daten.get("status") != "ok":
        return ""

    f = daten["form"]

    tabelle = [
        "| Woche ab | Einheiten | Std. | Plan erfüllt | Anmerkung |",
        "|---|---|---|---|---|",
    ]
    for w in daten["wochen"]:
        e = w["einhaltung"]
        if e and e["geplant"]:
            quote = f"{e['erledigt']}/{e['geplant']}"
            if e["verschoben"]:
                quote += f" +{e['verschoben']} versch."
            if e["ersetzt"]:
                quote += f" +{len(e['ersetzt'])} ersetzt"
            # Die Zuordnung Plan→Ist ist eine Näherung: Sie trifft nicht, wenn
            # die Einheit verschoben oder anders ausgeführt wurde. Wer mehr
            # Einheiten absolviert hat als geplant waren, hat nicht ausgelassen
            # — ohne diesen Zusatz läse der Coach genau das und würde einen
            # Athleten zurückfahren, der zu viel statt zu wenig gemacht hat.
            #
            # Ohne Arbeitswege gerechnet. Sie zählten mit, und der Satz feuerte
            # dann nach Wochen, in denen die Hälfte des Plans liegen geblieben
            # war: vier geplant, zwei absolviert, drei Fahrten zur Arbeit — fünf
            # Einheiten, also "Umfang erreicht". Ausgerechnet der Zusatz, der
            # den Coach vom Zurückfahren abhalten soll, hielt ihn davon ab,
            # nachdem wirklich etwas gefehlt hatte.
            trainingseinheiten = w["anzahl"] - w.get("wege", 0)
            if trainingseinheiten >= e["geplant"] and e["erledigt"] < e["geplant"]:
                quote += " — Umfang erreicht, Ausführung abweichend"
        else:
            quote = "–"

        if not w["anzahl"]:
            anmerkung = w["grund"] or "**keine Einheit, kein Grund gemeldet**"
            tabelle.append(f"| {w['start']} | 0 | 0 | {quote} | {anmerkung} |")
            continue
        disz = " ".join(f"{k}×{v}" for k, v in sorted(w["disziplinen"].items()))
        anmerkung = w["grund"] or disz
        # Den Anteil der Arbeitswege ausschreiben: Die Last gehört in die
        # Summe, aber der Coach soll sehen, wie viel davon Pendeln war.
        wege = w.get("wege") or 0
        einheiten = f"{w['anzahl']} (davon {wege} Wege)" if wege else str(w["anzahl"])
        stunden = (
            f"{w['stunden']} ({w['wege_stunden']} Wege)"
            if wege and w.get("wege_stunden") else str(w["stunden"])
        )
        tabelle.append(
            f"| {w['start']} | {einheiten} | {stunden} | {quote} | {anmerkung} |"
        )

    # Verlaufsreihe je Disziplin: drei Vierwochenblöcke, ältester zuerst.
    reihen = []
    for disziplin, blocks in sorted(daten["progression"].items()):
        stuecke = [progression_wert(disziplin, b) for b in blocks]
        reihen.append(f"- {disziplin}: {' → '.join(stuecke)}")

    # Die Obergrenze steht direkt unter der Reihe: die Reihe sagt, ob
    # gesteigert werden soll, diese Zeile, wie viel auf einmal.
    obergrenze_zeile = ""
    if (grenze := daten.get("lauf_obergrenze")):
        obergrenze_zeile = (
            f"\nLängster Lauf der letzten {SPRUNG_FENSTER_TAGE} Tage: "
            f"**{grenze['laengster_km']} km** ({grenze['laengster_am']}). "
            f"Plane keinen einzelnen Lauf über **{grenze['hoechstens_km']} km** "
            f"— ein Lauf mehr als 10 % über diesem Wert erhöht das "
            f"Verletzungsrisiko deutlich, oberhalb des Doppelten stark. Gilt "
            f"nur fürs Laufen. Wenn ein größerer Schritt nötig ist, begründe "
            f"ihn im coaching_comment.\n"
        )
        # Wenn der bestimmende Lauf selbst ein Sprung war, darf die Grenze
        # nicht als verdientes Niveau gelesen werden.
        if (sprung := grenze.get("war_selbst_sprung")):
            obergrenze_zeile += (
                f"**Achtung:** Dieser längste Lauf lag selbst {sprung} % über "
                f"der Grenze, die damals galt — er war ein Sprung, nicht ein "
                f"erarbeitetes Niveau. Die Studie sagt, dass ein solcher Sprung "
                f"das Risiko erhöht, nicht dass die Strecke jetzt sicher ist. "
                f"Konsolidiere deshalb auf diesem Niveau statt noch 10 % "
                f"draufzulegen: Plane den langen Lauf höchstens so lang wie "
                f"diesen, bis er zweimal beschwerdefrei gelaufen wurde.\n"
            )

    if (umfang := daten.get("lauf_wochenumfang")):
        reihe = " → ".join(f"{k:.0f}" for k in umfang["wochen_km"])
        obergrenze_zeile += (
            f"Laufumfang der letzten {len(umfang['wochen_km'])} Wochen: "
            f"{reihe} km."
        )
        if umfang["zuwachs_zwei_wochen"] is not None:
            z = umfang["zuwachs_zwei_wochen"]
            obergrenze_zeile += (
                f" Zuwachs über zwei Wochen: {z:+d} %"
                + (
                    f" — über der Grenze von {umfang['grenze_prozent']} %, "
                    f"diese Woche nicht weiter steigern."
                    if z > umfang["grenze_prozent"] else
                    f" (Grenze {umfang['grenze_prozent']} %)."
                )
            )
        obergrenze_zeile += (
            " Die Einzellauf-Grenze oben begrenzt einen Lauf, diese Zeile die "
            "Woche — beide gelten.\n"
        )

    b = daten["belastbarkeit"]
    if b["zugeordnet"]:
        belastung = [
            f"Von {b['zugeordnet']} zugeordneten Einheiten lagen **{b['mehr']} "
            f"deutlich über** der Vorgabe und {b['weniger']} darunter"
            + (
                f" ({b['verworfen']} Paare als unplausibel verworfen)."
                if b["verworfen"] else "."
            )
        ]
        # Bewusst keine Handlungsanweisung: Verfehlte Vorgaben in Taper-,
        # Krankheits- oder Off-Season-Wochen sind kein Zeichen von
        # Überforderung. Die Phase steht weiter oben im Prompt — sie
        # zusammenzuführen ist die Aufgabe des Coaches, nicht dieser Zählung.
        belastung.append(
            "Werte das nur für Wochen ohne Taper, Krankheit oder Off-Season: "
            "Dort heißt regelmäßiges Übertreffen, dass der Umfang der "
            "Schlüsseleinheiten zu niedrig angesetzt ist, und regelmäßiges "
            "Verfehlen das Gegenteil. In allen anderen Wochen sagt die Zahl "
            "nichts über die Belastbarkeit aus."
        )
        for disziplin, (anzahl, faktor) in sorted(b.get("weit_darueber", {}).items()):
            belastung.append(
                f"**{disziplin}: {anzahl} Einheiten lagen beim {faktor}-fachen "
                f"der Vorgabe** und wurden oben als unplausibel verworfen. "
                f"Einmal wäre das ein Zuordnungsfehler — {anzahl}-mal in "
                f"dieselbe Richtung heißt, dass der Umfang dieser Disziplin "
                f"viel zu kurz angesetzt ist. Setze die Vorgabe dort an dem an, "
                f"was tatsächlich gefahren wird, nicht am Plan."
            )
        if b.get("lauf_mehr"):
            belastung.append(
                f"Davon {b['lauf_mehr']} beim Laufen — dort gilt dieser Schluss "
                "**nicht**. Für Läufe entscheidet die Obergrenze oben, nicht die "
                "Übererfüllung: ein überschrittener Vorgabeumfang ist beim Laufen "
                "kein Zeichen von Reserve, sondern genau das Muster, das die "
                "Verletzungsrate erhöht."
            )
        if b["beispiele"]:
            belastung.append("Zuletzt darüber: " + "; ".join(b["beispiele"]) + ".")
    else:
        belastung = [
            "Noch keine Einheit einer Planvorgabe zugeordnet — zur "
            "Belastbarkeit lässt sich nichts sagen."
        ]

    form_zeile = ""
    if f["ctl"] is not None:
        trend = ""
        if f["ctl_vor_4_wochen"] is not None:
            diff = f["ctl"] - f["ctl_vor_4_wochen"]
            richtung = "steigend" if diff > 2 else "fallend" if diff < -2 else "stabil"
            trend = f" ({richtung}, vor 4 Wochen {f['ctl_vor_4_wochen']})"
        form_zeile = (
            "\n### Rechenwerte (nachrangig)\n"
            f"Fitness (CTL) {f['ctl']}{trend} · Ermüdung (ATL) {f['atl']} · Form (TSB) {f['tsb']}\n"
            "Diese Werte sind aus TSS hochgerechnet und ersetzen kein Befinden. "
            "Eine negative Form allein ist **kein** Grund, die Woche zu kürzen — "
            "maßgeblich ist, ob die Einheiten zuletzt sauber durchgezogen wurden "
            "und was in den Reflexionen steht. Nutze sie nur zur Einordnung eines "
            "Bildes, das sich schon aus Einhaltung und Reflexion ergibt.\n"
        )

    ausfall = (
        f"\nAusfalltage durch Krankheit oder Verletzung: {daten['ausfalltage']}\n"
        if daten["ausfalltage"] else ""
    )

    # Ersatzeinheiten im Klartext. Als bloße Zahl in der Tabelle wären sie
    # nicht verwertbar: Ob jemand drei Stunden gewandert oder eine Stunde
    # locker mit Freunden gefahren ist, macht für die nächste Woche einen
    # Unterschied — und beides ist etwas anderes als eine ausgelassene Einheit.
    alle_ersatz = [
        f"- {w['start']}: {t}"
        for w in daten["wochen"]
        for t in (w["einhaltung"] or {}).get("ersetzt", [])
    ]
    ersatz_text = (
        "\n### Ersetzte Einheiten (bewusst durch anderes ersetzt, nicht ausgelassen)\n"
        + "\n".join(alle_ersatz)
        + "\nDas war Belastung, kein Ausfall — rechne sie als solche und "
        "kürze die Folgewoche deswegen nicht. Häufen sie sich an denselben "
        "Wochentagen, lege dort von vornherein die flexible Einheit hin.\n"
        if alle_ersatz else ""
    )

    return (
        f"## SAISONVERLAUF (letzte {WOCHEN_IM_VERLAUF} Wochen)\n\n"
        "Leitsignal für die Progression ist diese Tabelle: Wurde der Plan "
        "eingehalten, und was steht in den Reflexionen dazu? Wochen mit "
        "unerfülltem Plan ohne gemeldeten Grund sind ein Hinweis, dass der "
        "Umfang zu hoch angesetzt war.\n\n"
        + "\n".join(tabelle)
        + ersatz_text
        + ausfall
        + f"\n### Längste Einheit je {BLOCK_WOCHEN}-Wochen-Block (ältester zuerst)\n"
        + ("\n".join(reihen) if reihen else "- noch keine")
        + "\n\nDie Richtung dieser Reihe gibt den nächsten Schritt vor, nicht der "
        "höchste Einzelwert. Wächst sie, plane den nächsten Zuwachs in derselben "
        "Größenordnung. Steht sie, halte den Umfang, bevor du Intensität erhöhst. "
        "Fällt sie ohne gemeldeten Grund, geh zurück auf das zuletzt sicher "
        "erreichte Niveau.\n"
        + obergrenze_zeile
        + "\n### Belastbarkeit — Vorgabe gegen tatsächlich absolviert\n"
        + "\n".join(belastung)
        + "\n"
        + form_zeile
        + "\n---"
    )
