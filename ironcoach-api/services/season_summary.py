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

from core.training_types import EXTERN_GEPLANT
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
            if d in ("rest", "gym") or d in EXTERN_GEPLANT:
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
        .filter(TrainingSession.discipline.notin_(EXTERN_GEPLANT))
        .all()
    )
    mehr, weniger, verworfen, beispiele = 0, 0, 0, []
    for ist, soll in paare:
        if not soll.duration_min or not ist.duration_min:
            continue
        verhaeltnis = ist.duration_min / soll.duration_min
        # Wer das Dreifache der Vorgabe absolviert, hat nicht übererfüllt —
        # da wurde eine ungeplante lange Ausfahrt auf einen kurzen
        # Regenerationsslot gebucht. Solche Paare als Belastbarkeit zu zählen
        # hieße, aus einem Zuordnungsfehler eine Trainingsempfehlung zu machen.
        if verhaeltnis > 3 or verhaeltnis < 0.25:
            verworfen += 1
            continue
        diff = ist.duration_min - soll.duration_min
        # Zehn Prozent Toleranz: Darunter ist es Alltag, keine Aussage.
        if diff > soll.duration_min * 0.10:
            mehr += 1
            beispiele.append(
                f"{ist.session_date} {ist.discipline}: {ist.duration_min} statt "
                f"{soll.duration_min} min"
            )
        elif diff < -soll.duration_min * 0.10:
            weniger += 1
    return {
        "mehr": mehr,
        "weniger": weniger,
        "verworfen": verworfen,
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
        wochen[m] = {"tss": 0.0, "min": 0, "anzahl": 0, "disziplinen": defaultdict(int)}
        m += timedelta(days=7)

    for s in alle:
        if s.session_date < beginn:
            continue
        montag = s.session_date - timedelta(days=s.session_date.weekday())
        w = wochen.setdefault(montag, {"tss": 0.0, "min": 0, "anzahl": 0, "disziplinen": defaultdict(int)})

        w["tss"] += s.tss or 0
        w["min"] += s.duration_min or 0
        w["anzahl"] += 1
        w["disziplinen"][(s.discipline or "?").lower()] += 1

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
                "disziplinen": dict(w["disziplinen"]),
                "grund": grund_je_woche.get(montag),
                "einhaltung": einhaltung.get(montag),
            }
            for montag, w in sorted(wochen.items())
        ],
        "progression": _progression(alle, heute),
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
            if w["anzahl"] >= e["geplant"] and e["erledigt"] < e["geplant"]:
                quote += " — Umfang erreicht, Ausführung abweichend"
        else:
            quote = "–"

        if not w["anzahl"]:
            anmerkung = w["grund"] or "**keine Einheit, kein Grund gemeldet**"
            tabelle.append(f"| {w['start']} | 0 | 0 | {quote} | {anmerkung} |")
            continue
        disz = " ".join(f"{k}×{v}" for k, v in sorted(w["disziplinen"].items()))
        anmerkung = w["grund"] or disz
        tabelle.append(
            f"| {w['start']} | {w['anzahl']} | {w['stunden']} | {quote} | {anmerkung} |"
        )

    # Verlaufsreihe je Disziplin: drei Vierwochenblöcke, ältester zuerst.
    reihen = []
    for disziplin, blocks in sorted(daten["progression"].items()):
        stuecke = []
        for b in blocks:
            if b is None:
                stuecke.append("–")
            elif b["km"]:
                stuecke.append(f"{b['km']:.1f} km")
            else:
                stuecke.append(f"{b['min']} min")
        reihen.append(f"- {disziplin}: {' → '.join(stuecke)}")

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
        "\n### Belastbarkeit — Vorgabe gegen tatsächlich absolviert\n"
        + "\n".join(belastung)
        + "\n"
        + form_zeile
        + "\n---"
    )
