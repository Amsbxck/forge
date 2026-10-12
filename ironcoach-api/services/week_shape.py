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

from core.phasenregeln import (
    BLOCK_FENSTER_WOCHEN,
    MIN_ABSTAND_TAGE,
    QUALITAET_STRENG,
    regeln_fuer,
)

# Gezählt wird nach **Trainingstyp**, nicht nach Intensitätsstufe, und die
# Liste hängt an der **Phase**.
#
# Die Stufe ist zu grob: `sweet_spot`, `tempo` und `race_pace` fallen alle auf
# „sweet_spot". Zählt man darüber, zählt entweder alles drei mit (dann erscheint
# jede normale Aufbauwoche als Verstoß) oder keines (dann meldet die Peak-Phase
# null Qualitätseinheiten, obwohl ihre Qualitätseinheiten genau die
# Wettkampftempo-Blöcke sind).
#
# Und die Phase entscheidet mit: In der Grundlage **ist** der Sweet Spot die
# eine Qualitätseinheit, im Aufbau ist er die Brot-und-Butter-Einheit. Beide
# Male dieselbe Liste zu nehmen geht nicht — die Listen stehen deshalb in
# `core/phasenregeln.py` je Phase.
#
# Die strenge Liste bleibt hier als Standard: Wer `harte_einheiten` ohne Phase
# aufruft, soll nicht stillschweigend die laxere Variante bekommen.
QUALITAETS_TYPEN = QUALITAET_STRENG

# Fällt der Typ aus (Altbestand, freie Eingabe), entscheidet die Stufe.
HARTE_INTENSITAETEN = ("threshold", "vo2max")


def _ist_hart(einheit, typen: tuple[str, ...] = QUALITAETS_TYPEN) -> bool:
    """Qualitätseinheit? Erst über den Typ, dann über die Intensitätsstufe.

    `typen` kommt aus der Phase: In der Grundlage zählt der Sweet Spot mit,
    im Aufbau nicht. Ohne Angabe gilt die strenge Liste — ein fehlender Wert
    soll nicht stillschweigend die laxere Variante aktivieren.
    """
    disziplin = (einheit.discipline or "").lower()
    if disziplin == "swim":
        # Schwimmen hat keine Leistungsdaten und wird extern geplant; eine
        # Einstufung dort wäre geraten.
        return False

    typ = (einheit.training_type or "").lower()
    if typ in typen:
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


def _montag_von(tag: date) -> date:
    return tag - timedelta(days=tag.weekday())


def _einheiten(db: Session, von: date, bis: date,
               user_id: int | None = None) -> list | None:
    """Die Vorgaben eines Zeitraums — je Woche nur der jüngste Plan.

    Gelesen wird die Projektion, nicht der Plan-JSON: dort steht je Woche nur
    der jüngste Plan, also das, was am Ende gegolten hat.

    Der Zeitraum darf mehrere Wochen umfassen. Das war er vorher nicht:
    Gefiltert wurde auf den **einen** jüngsten `plan_id` über den ganzen
    Bereich. Bei einer Woche stimmt das — nach der Projektion gibt es dort nur
    einen Plan. Über vier Wochen hätte es drei Wochen stillschweigend
    weggeworfen, weil jede Woche ihren eigenen Plan hat. Deshalb der jüngste
    Plan **je Woche**, so wie `season_summary._einhaltung` es macht.

    `None` heißt „nicht lesbar" (keine Projektionstabelle) und ist von einer
    leeren Liste zu unterscheiden: Die eine bedeutet „keine Auskunft möglich",
    die andere „die Woche ist leer".

    Gemeinsam genutzt von `harte_einheiten` und `grundbasis`. Zwei Kopien
    dieses Filters gäbe es damit immer noch (`season_summary`), eine dritte
    wäre die nächste Abweichung.
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
        return None

    jung: dict[date, int] = {}
    for e in einheiten:
        m = _montag_von(e.planned_date)
        if (e.plan_id or 0) > jung.get(m, -1):
            jung[m] = e.plan_id or 0
    return [
        e for e in einheiten
        if (e.plan_id or 0) == jung[_montag_von(e.planned_date)]
    ]


def harte_einheiten(db: Session, von: date, bis: date,
                    user_id: int | None = None,
                    phase: str | None = None) -> dict:
    """Harte Einheiten eines Zeitraums aus den **Vorgaben**."""
    einheiten = _einheiten(db, von, bis, user_id)
    if einheiten is None:
        return {"anzahl": 0, "tage": [], "min_abstand": None, "vorhanden": False}

    # Welche Typen zählen, entscheidet die Phase — siehe `_ist_hart`.
    regeln = regeln_fuer(phase) if phase else None
    typen = (regeln or {}).get("zaehlt_als_qualitaet", QUALITAET_STRENG)
    harte = sorted({
        e.planned_date for e in einheiten if _ist_hart(e, typen)
    })
    abstand = None
    if len(harte) >= 2:
        abstand = min((b - a).days for a, b in zip(harte, harte[1:]))

    return {
        "anzahl": len(harte),
        "tage": harte,
        "min_abstand": abstand,
        "vorhanden": bool(einheiten),
    }


def grundbasis(db: Session, von: date, bis: date,
               user_id: int | None = None,
               phase: str | None = None) -> dict:
    """Trägt die Woche die Grundbasis der Phase — und ist überhaupt Platz?

    Gezählt wird, was bisher **nichts** gezählt hat: Krafteinheiten.
    `PHASENREGELN[...]["gym"]` wurde an genau einer Stelle gelesen und dort nur
    als Prompt-Text gerendert. An acht echten Wochen gemessen verfehlten sieben
    die Kraftvorgabe, und nur **eine** davon war wirklich voll — in den anderen
    gab es freie Tage. Es fehlte also nicht Platz, sondern ein Zähler.

    Zwei Entscheidungen, die den Unterschied machen:

      * **Krafteinheiten werden als Zeilen gezählt, nicht als Tage.** Anders
        als harte Einheiten, bei denen der 48-Stunden-Abstand nach *Tagen*
        fragt. Ein Doppeltag Schwimmen + Kraft wäre über Tage gezählt eine
        Einheit, und genau dieser Doppeltag ist das Mittel, mit dem die
        Kraftvorgabe gehalten werden soll — der Zähler hätte sein eigenes
        Mittel nicht gesehen.
      * **Trainingstage und Ruhetage getrennt.** Nur so lässt sich „die Woche
        ist voll, es braucht einen Doppeltag" von „es war Platz, die Einheit
        ist schlicht ausgefallen" unterscheiden. Das sind verschiedene
        Probleme mit verschiedenen Antworten, und sieben von acht Wochen waren
        der zweite Fall.

    Berichtet, lehnt nichts ab — wie das ganze Modul. `vorhanden` ist falsch,
    wenn es nichts zu sagen gibt: keine Projektion, keine Woche, oder eine
    Phase ohne Kraftvorgabe (Taper, Wettkampfwoche). Ohne diese letzte
    Bedingung meldete jede Taperwoche „0 von 0 Krafteinheiten".
    """
    regeln = regeln_fuer(phase) if phase else None
    gym_soll = (regeln or {}).get("gym")

    einheiten = _einheiten(db, von, bis, user_id)
    if not einheiten:
        return {
            "gym": 0, "gym_soll": gym_soll, "trainingstage": 0, "ruhetage": 0,
            "einheiten": 0, "freie_tage": [], "vorhanden": False,
        }

    # Ruhetage werden als Zeile projiziert, zählen hier also mit. Ein Tag ohne
    # jede Zeile wäre ebenfalls frei — deshalb über die Daten des Zeitraums,
    # nicht über die Ruhetagszeilen.
    belegt = {e.planned_date for e in einheiten
              if (e.discipline or "").lower() != "rest"}
    alle_tage = [von + timedelta(days=i) for i in range((bis - von).days + 1)]
    frei = [t for t in alle_tage if t not in belegt]

    gym = sum(1 for e in einheiten if (e.discipline or "").lower() == "gym")

    return {
        "gym": gym,
        "gym_soll": gym_soll,
        "trainingstage": len(belegt),
        "ruhetage": len(frei),
        # Einheiten, nicht Zeilen: ein Ruhetag ist keine Einheit.
        "einheiten": sum(1 for e in einheiten
                         if (e.discipline or "").lower() != "rest"),
        "freie_tage": frei,
        "vorhanden": bool(gym_soll),
    }


WOCHENTAG = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


def _kraftluecke(gb: dict) -> str | None:
    """Die verfehlte Kraftvorgabe als Satz. `None`, wenn sie gehalten wurde.

    Ein Satz, zwei Leser (`prompt_block` und `bericht`) — zwei Formulierungen
    desselben Befunds wären zwei Wahrheiten über dieselbe Woche.

    Der Satz **unterscheidet** die beiden Lagen, weil sie verschiedene
    Antworten haben: War die Woche voll, ist der Doppeltag die Lösung; war Platz
    frei, ist die Einheit einfach ausgefallen und braucht keinen Doppeltag,
    sondern einen Tag.

    Wichtig dabei: **Ein** freier Tag ist der Ruhetag, nicht Platz. Die
    Rangordnung in `core/phasenregeln.vorrang_block` schützt ihn ausdrücklich.
    Ihn hier als freie Fläche zu melden hieße, dem Coach genau das
    vorzuschlagen, was zwei Abschnitte weiter oben verboten ist. Erst ab zwei
    freien Tagen war wirklich Platz.
    """
    if not gb.get("vorhanden"):
        return None
    soll = gb["gym_soll"]
    ist = gb["gym"]
    if ist >= soll:
        return None

    kern = (
        f"Krafttraining: **{ist} von {soll}** — die Vorgabe dieser Phase ist "
        f"nicht erfüllt."
    )
    frei = gb.get("freie_tage") or []
    if len(frei) >= 2:
        tage = ", ".join(WOCHENTAG[t.weekday()] for t in frei)
        return (
            f"{kern} Dabei war Platz: {tage} ohne Einheit — einer davon ist der "
            f"Ruhetag, die übrigen waren frei. Es brauchte also keinen "
            f"Doppeltag, nur einen Tag."
        )
    return (
        f"{kern} Die Woche war voll (ein Ruhetag, sonst alles belegt) — "
        f"**das** ist der Fall für einen Doppeltag (Schwimmen + Kraft), nicht "
        f"für das Streichen der Einheit."
    )


def prompt_block(db: Session, woche_ab: date, phase: str | None,
                 user_id: int | None = None) -> str:
    """Die Vorwoche als Satz für den Prompt. Leer, wenn es nichts zu sagen gibt."""
    vorwoche = woche_ab - timedelta(days=7)
    form = harte_einheiten(db, vorwoche, vorwoche + timedelta(days=6),
                           user_id, phase)
    if not form["vorhanden"]:
        return ""

    regeln = regeln_fuer(phase)
    n = form["anzahl"]
    teile = [
        f"**Vorwoche ({vorwoche}):** {n} harte "
        f"{'Einheit' if n == 1 else 'Einheiten'}"
    ]
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
            db, fenster_start, woche_ab - timedelta(days=1), user_id, phase
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

    # Die Kraftvorgabe der Vorwoche. Der Teil, der die stillen Fälle sichtbar
    # macht: An acht echten Wochen verfehlten sieben sie, und niemandem fiel es
    # auf, weil nichts sie gezählt hat.
    luecke = _kraftluecke(
        grundbasis(db, vorwoche, vorwoche + timedelta(days=6), user_id, phase)
    )
    if luecke:
        hinweise.append(luecke)

    return "\n## RÜCKSCHAU AUF DIE WOCHENFORM\n" + satz + (
        " " + " ".join(hinweise) if hinweise else ""
    ) + "\n"


def bericht(db: Session, woche_ab: date, phase: str | None,
            user_id: int | None = None) -> str | None:
    """Ein Satz über die **eben erzeugte** Woche, für `adjustments_applied`.

    Bewusst ohne Werturteil, wenn alles passt: Eine Zeile „alles in Ordnung"
    in jeder Plananpassung wäre Rauschen.

    Zwei Befunde, die unabhängig voneinander auftreten können: die harten
    Einheiten (Anzahl und Abstand) und die Kraftvorgabe. Deshalb werden sie
    getrennt erhoben und zusammengesetzt — die Kraftlücke darf nicht daran
    hängen, dass die Qualitätsprüfung nichts zu melden hatte.
    """
    kraft = _kraftluecke(
        grundbasis(db, woche_ab, woche_ab + timedelta(days=6), user_id, phase)
    )
    qualitaet = _qualitaetsbericht(db, woche_ab, phase, user_id)
    teile = [t for t in (qualitaet, kraft) if t]
    return " ".join(teile) if teile else None


def nach_anpassung(db: Session, von: date, bis: date, phase: str | None,
                   user_id: int | None = None,
                   heute: date | None = None) -> str | None:
    """Der Befund nach einer Tagesänderung — und **nur**, wenn er noch hilft.

    Unterschied zu `bericht`: Dort ist die ganze Woche neu erzeugt, hier wurden
    einzelne Tage geändert. `services/plan_merge.py` weist vergangene und
    absolvierte Tage ausdrücklich ab — am Samstag lässt sich an der Woche
    nichts mehr reparieren. „Krafttraining 1 von 2" wäre dann ein Vorwurf für
    etwas, das niemand mehr ändern kann.

    Deshalb schweigt diese Funktion, wenn in der Woche kein Tag mehr vor dem
    Athleten liegt. Dasselbe Muster wie die Blockunterdrückung in
    `prompt_block`: Das Urteil entfällt, wo das Mittel dagegen fehlt.
    """
    heute = heute or date.today()
    if bis < heute:
        return None

    kraft = _kraftluecke(grundbasis(db, von, bis, user_id, phase))
    qualitaet = _qualitaetsbericht(db, von, phase, user_id)
    teile = [t for t in (qualitaet, kraft) if t]
    return " ".join(teile) if teile else None


def _qualitaetsbericht(db: Session, woche_ab: date, phase: str | None,
                       user_id: int | None = None) -> str | None:
    """Anzahl und Abstand der harten Einheiten der erzeugten Woche."""
    form = harte_einheiten(db, woche_ab, woche_ab + timedelta(days=6),
                           user_id, phase)
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
            woche_ab + timedelta(days=6), user_id, phase,
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
