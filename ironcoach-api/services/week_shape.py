"""Wie viele harte Einheiten eine Woche trug — und wie weit auseinander.

Nichts im Code hat das je gezählt. „Max 2 Intensitäts-Sessions/Woche" und
„Wer einen harten Tag verschiebt, setzt nicht zwei harte hintereinander"
standen als Prosa im Prompt, und ob sich das Modell daran gehalten hat, sah
niemand nach.

Dieses Modul **berichtet**, es lehnt nichts ab. Es hat keinen Schreibpfad und
keine eigene Ausnahmebehandlung; drei Leser benutzen es:

1. der Prompt, mit der Vorwoche neben der Phasenvorgabe,
2. die Generierung, die das Ergebnis der eben erzeugten Woche in
   `adjustments_applied` schreibt — und zwar **nach** `project_plan`, nicht
   darin: diese Funktion schluckt jede Ausnahme, damit sie die Generierung
   nicht reißt, und ein Zähler dahinter wäre unsichtbar ausgefallen,
3. das Verschieben per Hand, wo sich der Abstand ändert, ohne dass die Anzahl
   sich ändert.
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.orm import Session

from core.phasenregeln import BLOCK_FENSTER_WOCHEN, MIN_ABSTAND_TAGE, regeln_fuer

# Was als Qualitätseinheit zählt — nach **Trainingstyp**, nicht nach
# Intensitätsstufe.
#
# Die Stufe ist dafür zu grob: `sweet_spot`, `tempo` und `race_pace` fallen
# alle auf die Stufe „sweet_spot". Zählt man darüber, zählt entweder alles
# drei mit (dann erscheint jede normale Aufbauwoche als Verstoß, weil Sweet
# Spot dort die Brot-und-Butter-Einheit ist) oder keines (dann meldet die
# Peak-Phase null Qualitätseinheiten, obwohl ihre Qualitätseinheiten genau die
# Wettkampftempo-Blöcke sind — und der Prompt verlangt dann zusätzliche
# Einheiten obendrauf).
#
# Deshalb: `race_pace` zählt, `sweet_spot` und `tempo` nicht. Eine lange
# Ausfahrt im Wettkampftempo kostet Erholung wie eine harte Einheit, ein
# 3×15-Minuten-Block bei 90 % nicht.
QUALITAETS_TYPEN = ("threshold", "vo2max", "intervals", "race_pace")

# Fällt der Typ aus (Altbestand, freie Eingabe), entscheidet die Stufe.
HARTE_INTENSITAETEN = ("threshold", "vo2max")


def _ist_hart(einheit) -> bool:
    """Qualitätseinheit? Erst über den Typ, dann über die Intensitätsstufe."""
    disziplin = (einheit.discipline or "").lower()
    if disziplin == "swim":
        # Schwimmen hat keine Leistungsdaten und wird extern geplant; eine
        # Einstufung dort wäre geraten.
        return False

    typ = (einheit.training_type or "").lower()
    if typ in QUALITAETS_TYPEN:
        return True

    # Ein Brick im Wettkampftempo oder härter zählt mit — die Laufdokumente
    # rechnen ihn ausdrücklich zur Qualitätseinheit, und er kostet Erholung
    # wie eine.
    if disziplin == "brick":
        zone = (getattr(einheit, "target_hr_zone", None) or "").upper()
        return zone in ("Z4", "Z5", "Z6", "Z7")

    # Kein bekannter Typ: über die Stufe, die aus der Zielzone kommt.
    if not typ:
        return einheit.intensity in HARTE_INTENSITAETEN
    return False


def harte_einheiten(db: Session, von: date, bis: date,
                    user_id: int | None = None) -> dict:
    """Harte Einheiten eines Zeitraums aus den **Vorgaben**.

    Gelesen wird die Projektion, nicht der Plan-JSON: dort steht je Woche nur
    der jüngste Plan, also das, was am Ende gegolten hat.

    Der Zeitraum darf mehrere Wochen umfassen. Das war er vorher nicht:
    Gefiltert wurde auf den **einen** jüngsten `plan_id` über den ganzen
    Bereich. Bei einer Woche stimmt das — nach der Projektion gibt es dort nur
    einen Plan. Über vier Wochen hätte es drei Wochen stillschweigend
    weggeworfen, weil jede Woche ihren eigenen Plan hat. Deshalb jetzt der
    jüngste Plan **je Woche**, so wie `season_summary._einhaltung` es macht.
    """
    from models import PlannedSession

    abfrage = db.query(PlannedSession).filter(
        PlannedSession.planned_date >= von,
        PlannedSession.planned_date <= bis,
    )
    if user_id is not None:
        abfrage = abfrage.filter(PlannedSession.user_id == user_id)

    try:
        einheiten = abfrage.all()
    except Exception:  # pragma: no cover - ohne Projektionstabelle gibt es nichts
        return {"anzahl": 0, "tage": [], "min_abstand": None, "vorhanden": False}

    def montag_von(tag: date) -> date:
        return tag - timedelta(days=tag.weekday())

    jung: dict[date, int] = {}
    for e in einheiten:
        m = montag_von(e.planned_date)
        if (e.plan_id or 0) > jung.get(m, -1):
            jung[m] = e.plan_id or 0
    einheiten = [
        e for e in einheiten
        if (e.plan_id or 0) == jung[montag_von(e.planned_date)]
    ]

    harte = sorted({e.planned_date for e in einheiten if _ist_hart(e)})
    abstand = None
    if len(harte) >= 2:
        abstand = min((b - a).days for a, b in zip(harte, harte[1:]))

    return {
        "anzahl": len(harte),
        "tage": harte,
        "min_abstand": abstand,
        "vorhanden": bool(einheiten),
    }


WOCHENTAG = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


def prompt_block(db: Session, woche_ab: date, phase: str | None,
                 user_id: int | None = None) -> str:
    """Die Vorwoche als Satz für den Prompt. Leer, wenn es nichts zu sagen gibt."""
    vorwoche = woche_ab - timedelta(days=7)
    form = harte_einheiten(db, vorwoche, vorwoche + timedelta(days=6), user_id)
    if not form["vorhanden"]:
        return ""

    regeln = regeln_fuer(phase)
    teile = [f"**Vorwoche ({vorwoche}):** {form['anzahl']} harte Einheiten"]
    if form["tage"]:
        teile.append("(" + ", ".join(WOCHENTAG[t.weekday()] for t in form["tage"]) + ")")
    if form["min_abstand"] is not None:
        tage = form["min_abstand"]
        teile.append(f", kürzester Abstand {tage} {'Tag' if tage == 1 else 'Tage'}")
    satz = " ".join(teile).replace(" ,", ",") + "."

    hinweise = []
    block_laeuft = False
    if regeln and regeln.get("block_moeglich"):
        # Im Aufbau zählt die Summe über vier Wochen, nicht die einzelne
        # Woche. Sonst hätte der Zähler die Blockvariante als Verstoß gemeldet
        # und der Prompt dem Coach gesagt, er solle zurücknehmen — gegen etwas,
        # das absichtlich so geplant war.
        _von, bis = regeln["qualitaet"]
        budget = bis * BLOCK_FENSTER_WOCHEN
        fenster_start = woche_ab - timedelta(weeks=BLOCK_FENSTER_WOCHEN)
        fenster = harte_einheiten(
            db, fenster_start, woche_ab - timedelta(days=1), user_id
        )
        verbraucht = fenster["anzahl"]
        offen = budget - verbraucht
        satz += (
            f" Im {BLOCK_FENSTER_WOCHEN}-Wochen-Fenster bisher "
            f"**{verbraucht} von {budget}**."
        )
        # Eine Blockwoche erkennt man daran, dass sie allein über der
        # Wochenvorgabe lag — dann sind die Folgewochen bewusst dünn.
        block_laeuft = form["anzahl"] > bis
        if offen <= 0:
            hinweise.append(
                "Das Fenster ist ausgeschöpft — diese Woche höchstens eine "
                "harte Einheit, besser keine."
            )
        elif block_laeuft:
            hinweise.append(
                f"Die Vorwoche war ein Block ({form['anzahl']} harte "
                f"Einheiten). Dann gehören die nächsten Wochen dünn: noch "
                f"{offen} im Fenster, also etwa eine pro Woche."
            )
        elif verbraucht < budget - bis * 2:
            hinweise.append(
                f"Noch {offen} im Fenster — hier wäre Platz für eine Blockwoche, "
                f"wenn die HRV normal ist."
            )
    elif regeln:
        von, bis = regeln["qualitaet"]
        if form["anzahl"] > bis:
            hinweise.append(
                f"Das waren mehr als die {bis} dieser Phase — plane diese Woche "
                f"nicht noch eine dazu."
            )
        elif form["anzahl"] < von:
            hinweise.append(
                f"Das war weniger als die {von} dieser Phase. Wenn kein Grund "
                f"dagegen stand, hol die Qualität diese Woche."
            )
    # Der Abstandshinweis entfällt in einer Blockwoche: fünf harte Einheiten in
    # sieben Tagen lassen sich nicht 48 Stunden auseinander legen, und das
    # Dokument nimmt das für diese eine Woche ausdrücklich in Kauf.
    if (not block_laeuft and form["min_abstand"] is not None
            and form["min_abstand"] < MIN_ABSTAND_TAGE):
        hinweise.append(
            "Zwei harte Tage lagen näher als 48 Stunden zusammen — diese Woche "
            "weiter auseinander legen."
        )

    return "\n## RÜCKSCHAU AUF DIE WOCHENFORM\n" + satz + (
        " " + " ".join(hinweise) if hinweise else ""
    ) + "\n"


def bericht(db: Session, woche_ab: date, phase: str | None,
            user_id: int | None = None) -> str | None:
    """Ein Satz über die **eben erzeugte** Woche, für `adjustments_applied`.

    Bewusst ohne Werturteil, wenn alles passt: Eine Zeile „alles in Ordnung"
    in jeder Plananpassung wäre Rauschen.
    """
    form = harte_einheiten(db, woche_ab, woche_ab + timedelta(days=6), user_id)
    if not form["vorhanden"]:
        return None
    regeln = regeln_fuer(phase)
    if not regeln:
        return None
    _von, bis = regeln["qualitaet"]

    if regeln.get("block_moeglich"):
        # Im Aufbau wird gegen das Vierwochenfenster gemessen, nicht gegen die
        # Woche. Sonst stünde über jeder bewusst geplanten Blockwoche
        # "5 harte Einheiten, Phasenvorgabe 2" — ein Vorwurf für etwas, das so
        # gewollt war.
        budget = bis * BLOCK_FENSTER_WOCHEN
        fenster = harte_einheiten(
            db, woche_ab - timedelta(weeks=BLOCK_FENSTER_WOCHEN - 1),
            woche_ab + timedelta(days=6), user_id,
        )
        if fenster["anzahl"] > budget:
            return (
                f"Wochenform: {fenster['anzahl']} harte Einheiten in "
                f"{BLOCK_FENSTER_WOCHEN} Wochen, Budget {budget}."
            )
        if form["anzahl"] > bis:
            # Über der Wochenzahl, aber im Fenster: das ist die Blockvariante.
            return (
                f"Wochenform: Blockwoche mit {form['anzahl']} harten Einheiten "
                f"({fenster['anzahl']} von {budget} im "
                f"{BLOCK_FENSTER_WOCHEN}-Wochen-Fenster) — die Folgewochen "
                f"entsprechend dünn halten."
            )
        return None

    if form["anzahl"] > bis:
        return (
            f"Wochenform: {form['anzahl']} harte Einheiten, Phasenvorgabe {bis}."
        )
    if form["min_abstand"] is not None and form["min_abstand"] < MIN_ABSTAND_TAGE:
        tage = form["min_abstand"]
        return (
            f"Wochenform: zwei harte Einheiten mit {tage} "
            f"{'Tag' if tage == 1 else 'Tagen'} Abstand, Vorgabe mindestens "
            f"{MIN_ABSTAND_TAGE}."
        )
    return None
