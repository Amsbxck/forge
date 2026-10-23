"""Welcher Doppeltag diese Woche — gezogen aus einer Urne, nicht geraten.

Doppeltage kamen bisher nur auf zwei Wegen in den Plan: von selbst als
Schwimmen + Kraft, wenn die Grundbasis nicht in die freien Tage passt
(`core/phasenregeln.vorrang_block`), oder auf Wunsch über die Knöpfe. Wer die
Formen nicht kannte, bekam sie nie. Ein Zwischenentwurf schlug sie nach dem
Erstellen zum Annehmen vor — verworfen: Jede Annahme war ein zweiter
Claude-Aufruf, und angenommen fügte sie eine Einheit **hinzu** (aus zwei
Schwimmeinheiten wurden drei), statt die Woche umzubauen.

Deshalb entscheidet die App **vor** dem Erstellen, regelbasiert, und der
Baustein geht in den einen Erstell-Aufruf mit (rund hundert Eingabetokens,
kein weiterer Aufruf):

* **Urne statt fester Regel.** Kein Doppeltag ist nachweislich der beste,
  also soll gewechselt werden — wie bei den Intervallformaten
  (`services/intervall_format.rotation_block`). In der Urne liegen die
  Formen, die die Phase erlaubt, und eine Kugel „kein Doppeltag".
* **Gewichtet nach HRV und Vorwochen.** Unter der Spanne bleibt nur lockeres
  Schwimmen (das Laufdokument behält es dort ausdrücklich), die Doppelschwelle
  braucht eine normale HRV und vertragene lockere Doppeltage. Was letzte Woche
  dran war, ist diese Woche aus der Urne.
* **Gesät mit Athlet und Montag.** Wer dieselbe Woche neu erzeugt, bekommt
  dieselbe Ziehung — sonst würde der Doppeltag bei jedem Neuerzeugen
  springen, und was die Kachel vorher anzeigt, wäre nicht, was der Plan
  bekommt. Tests sind damit deterministisch.
* **Umlegen statt Hinzufügen** (`phasenregeln.UMLEGEN`): Der Doppeltag
  entsteht aus Einheiten, die ohnehin in der Woche stehen.

Wie `week_shape`: Dieses Modul berichtet und schlägt vor, es schreibt nichts.
"""

from __future__ import annotations

import logging
import random
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy.orm import Session

from core.einheiten_bibliothek import DOPPEL_FORMATE, DOPPEL_MIN_ABSTAND_H
from core.phasenregeln import QUALITAET_STRENG, UMLEGEN, regeln_fuer

logger = logging.getLogger(__name__)

KEIN = "kein"

# Die Namen, wie sie der Athlet in `utils/trainingsoptionen.js` liest — die
# Kachel und der Prompt sollen dieselbe Form gleich nennen.
TITEL = {
    "schwimmen_als_zweite": "Schwimmen als zweite Einheit",
    "locker_plus_qualitaet": "Locker morgens, Qualität abends",
    "langer_lauf_geteilt": "Langen Lauf teilen",
    "doppelschwelle_leicht": "Leichte Doppelschwelle",
}

# Grundgewichte. Schwimmen am schwersten: Es erzeugt keine Stoßbelastung und
# macht den Folgetag nach harten Intervallen besser (Lum 2010) — die Form mit
# dem geringsten Risiko soll am häufigsten kommen. Die Doppelschwelle am
# leichtesten: Ihre langfristige Wirkung ist ungeprüft (Talsnes 2024 ist ein
# akuter Vergleich). „Kein Doppeltag" liegt mit drin, damit nicht jede Woche
# einen bekommt — Doppeltage ohne Anlass hätten die Belastung aus eigenem
# Antrieb erhöht, das ist in CLAUDE.md verworfen.
GRUNDGEWICHT = {
    "schwimmen_als_zweite": 3.0,
    "locker_plus_qualitaet": 2.0,
    "langer_lauf_geteilt": 2.0,
    "doppelschwelle_leicht": 1.0,
    KEIN: 2.0,
}

# Im Taper ist „kein" der Normalfall, das lockere Schwimmen die Ausnahme.
TAPER_GEWICHT = {"schwimmen_als_zweite": 1.0, KEIN: 3.0}

# Was gerade dran war, kommt nicht gleich wieder; was vor zwei Wochen dran
# war, nur halb so oft. Länger zurück schaut die Rotation nicht — sonst wäre
# bei drei erlaubten Formen nach drei Wochen keine mehr übrig.
ROTATION_FAKTOR = {1: 0.0, 2: 0.5}

# Ab dieser Dauer ist ein Lauf lang genug, dass sich das Teilen lohnt. Das
# Laufdokument nennt 75–150 min für den langen Lauf; geteilt werden soll der
# lange, nicht jeder lockere.
LANGER_LAUF_MIN = 90

# „Erst wenn lockere Doppeltage gut vertragen werden" (Laufdokument) — als
# Maß: ein absolvierter Doppeltag in den letzten sechs Wochen.
VERTRAGEN_TAGE = 42

# Die HRV gilt nur, wenn sie frisch ist. Ein Wert von vor einer Woche sagt
# über den Zustand beim Planen nichts mehr.
HRV_FRISCH_TAGE = 3

HRV_TEXT = {
    "green": "HRV normal",
    "yellow": "HRV leicht unter der Spanne",
    "red": "HRV unter der Spanne",
    None: "ohne aktuelle HRV",
}


def form_des_tages(einheiten: list, typen: tuple[str, ...] = QUALITAET_STRENG) -> str | None:
    """Welche Doppeltag-Form ein Tag trägt — oder keine.

    Eingeordnet nach Disziplin und Typ, so wie `plan_projection` die Einträge
    schreibt. Schwimmen + Kraft zählt bewusst **nicht**: Das ist das Mittel der
    Grundbasis-Regel, wenn die Woche voll ist, keine gezogene Form — sonst
    nähme eine volle Vorwoche der Urne das Schwimmen weg.
    """
    from services.week_shape import ist_hart

    belegt = [e for e in einheiten if (e.discipline or "").lower() != "rest"]
    if len(belegt) < 2:
        return None
    disziplinen = {(e.discipline or "").lower() for e in belegt}
    if "swim" in disziplinen and disziplinen & {"run", "bike", "brick"}:
        return "schwimmen_als_zweite"

    laeufe = [e for e in belegt if (e.discipline or "").lower() == "run"]
    if len(laeufe) >= 2:
        harte = sum(1 for e in laeufe if ist_hart(e, typen))
        if harte >= 2:
            return "doppelschwelle_leicht"
        if harte == 1:
            return "locker_plus_qualitaet"
        return "langer_lauf_geteilt"
    return None


def formen_im_zeitraum(db: Session, von: date, bis: date, user_id: int | None,
                       typen: tuple[str, ...] = QUALITAET_STRENG) -> set[str]:
    """Die Doppeltag-Formen, die in den **Vorgaben** eines Zeitraums stehen.

    Die Projektion ist die Quelle, nicht eine gespeicherte Ziehung: So zählt
    auch ein Doppeltag, den der Athlet selbst gewünscht oder von Hand
    zusammengeschoben hat.
    """
    from services.week_shape import einheiten_der_woche

    einheiten = einheiten_der_woche(db, von, bis, user_id) or []
    je_tag: dict[date, list] = defaultdict(list)
    for e in einheiten:
        je_tag[e.planned_date].append(e)
    return {f for tag in je_tag.values() if (f := form_des_tages(tag, typen))}


def _hrv_status(db: Session, user_id: int | None, heute: date) -> str | None:
    from models import HrvMeasurement

    abfrage = db.query(HrvMeasurement).filter(
        HrvMeasurement.measured_at >= heute - timedelta(days=HRV_FRISCH_TAGE),
        HrvMeasurement.measured_at <= heute,
    )
    if user_id is not None:
        abfrage = abfrage.filter(HrvMeasurement.user_id == user_id)
    letzte = abfrage.order_by(
        HrvMeasurement.measured_at.desc(), HrvMeasurement.id.desc()
    ).first()
    status = getattr(letzte, "hrv_status", None)
    return status if status in ("green", "yellow", "red") else None


def _doppeltag_vertragen(db: Session, user_id: int | None, montag: date) -> bool:
    """Gab es in den letzten Wochen einen **absolvierten** Doppeltag?

    Absolviert, nicht vorgegeben: „vertragen" heißt gemacht. Ein geplanter
    Doppeltag, der ausgefallen ist, ist kein Beleg.
    """
    from sqlalchemy import func

    from models import TrainingSession

    abfrage = db.query(TrainingSession.session_date).filter(
        TrainingSession.session_date >= montag - timedelta(days=VERTRAGEN_TAGE),
        TrainingSession.session_date < montag,
        TrainingSession.deleted_at.is_(None),
    )
    if user_id is not None:
        abfrage = abfrage.filter(TrainingSession.user_id == user_id)
    treffer = abfrage.group_by(TrainingSession.session_date).having(
        func.count(TrainingSession.id) >= 2
    ).first()
    return treffer is not None


def ziehung(db: Session, montag: date, phase: str | None,
            user_id: int | None, deload: bool = False,
            heute: date | None = None) -> dict:
    """Die Doppeltag-Form der Woche ab `montag`.

    Rückgabe: `{"form", "titel", "grund", "gewichte"}`. `form` ist `None` für
    „kein Doppeltag", `gewichte` die Urne nach allen Regeln — für Tests und
    für den, der nachvollziehen will, warum.
    """
    from core.race_types import phase_family
    from services.week_shape import einheiten_der_woche

    heute = heute or date.today()
    regeln = regeln_fuer(phase)
    familie = phase_family(phase)

    def ohne(grund: str, gewichte: dict | None = None) -> dict:
        return {"form": None, "titel": None, "grund": grund,
                "gewichte": gewichte or {KEIN: 1.0}}

    if not regeln:
        return ohne("Diese Phase hat keine Doppeltage.")
    if familie == "Race Week":
        return ohne("Rennwoche — kein Doppeltag.")
    if deload:
        # Eine Entlastungswoche senkt den Umfang um 40–50 %. Ein Doppeltag
        # wäre dort zwar ohne Zusatzumfang, aber er verdichtet den Tag — und
        # um Verdichtung geht es in dieser Woche gerade nicht.
        return ohne("Deload-Woche — kein Doppeltag.")

    if regeln.get("doppel"):
        gewichte = {f: GRUNDGEWICHT[f] for f in regeln["doppel"]}
        gewichte[KEIN] = GRUNDGEWICHT[KEIN]
    elif regeln.get("doppel_auf_wunsch"):
        gewichte = {f: TAPER_GEWICHT.get(f, 1.0) for f in regeln["doppel_auf_wunsch"]}
        gewichte[KEIN] = TAPER_GEWICHT[KEIN]
    else:
        return ohne("Diese Phase hat keine Doppeltage.")

    typen = regeln.get("zaehlt_als_qualitaet", QUALITAET_STRENG)
    gruende: list[str] = []

    # --- Gibt es überhaupt etwas umzulegen? ---------------------------------
    vorwoche = einheiten_der_woche(
        db, montag - timedelta(days=7), montag - timedelta(days=1), user_id
    ) or []
    # Ohne Vorwoche (erster Plan, Lücke im Kalender) ist nichts bekannt, und
    # Unbekanntes schließt nichts aus — sonst bekäme ein neuer Athlet nie das
    # Schwimmen gezogen. Ob es passt, prüft dann der Coach; der Baustein sagt
    # ihm ausdrücklich, den Doppeltag wegzulassen, wenn er nicht passt.
    if "schwimmen_als_zweite" in gewichte and vorwoche:
        schwimmen = sum(1 for e in vorwoche if (e.discipline or "").lower() == "swim")
        # Mit nur einer Schwimmeinheit gibt es nichts umzulegen, ohne einen
        # Schwimmtag zu verlieren oder eine Einheit dazuzunehmen.
        if schwimmen < 2:
            gewichte["schwimmen_als_zweite"] = 0.0
    if "langer_lauf_geteilt" in gewichte:
        drei_wochen = einheiten_der_woche(
            db, montag - timedelta(days=21), montag - timedelta(days=1), user_id
        ) or []
        lang = not drei_wochen or any(
            (e.discipline or "").lower() == "run" and (
                (e.duration_min or 0) >= LANGER_LAUF_MIN
                or (e.training_type or "").lower() == "long_run"
            )
            for e in drei_wochen
        )
        if not lang:
            gewichte["langer_lauf_geteilt"] = 0.0
    if "doppelschwelle_leicht" in gewichte and not _doppeltag_vertragen(db, user_id, montag):
        gewichte["doppelschwelle_leicht"] = 0.0

    # --- HRV ----------------------------------------------------------------
    status = _hrv_status(db, user_id, heute)
    gruende.append(HRV_TEXT[status])
    if status == "red":
        # Unter der Spanne: zweite Einheiten streichen, keine Doppelschwelle.
        # Lockeres Schwimmen darf bleiben (Laufdokument, HRV-Tabelle).
        for f in list(gewichte):
            if f not in (KEIN, "schwimmen_als_zweite"):
                gewichte[f] = 0.0
    elif status != "green":
        # Leicht darunter oder unbekannt: keine Doppelschwelle — sie verlangt
        # ausdrücklich eine normale HRV —, und „kein" wird wahrscheinlicher.
        if "doppelschwelle_leicht" in gewichte:
            gewichte["doppelschwelle_leicht"] = 0.0
        gewichte[KEIN] += 2.0

    # --- Rotation -----------------------------------------------------------
    for abstand, faktor in ROTATION_FAKTOR.items():
        von = montag - timedelta(days=7 * abstand)
        for f in formen_im_zeitraum(db, von, von + timedelta(days=6), user_id, typen):
            if f in gewichte:
                gewichte[f] *= faktor
                if abstand == 1:
                    gruende.append(f"{TITEL[f]} war letzte Woche dran")

    # --- Ziehen -------------------------------------------------------------
    # Feste Reihenfolge, damit dieselbe Saat auf jedem Rechner dasselbe zieht.
    kugeln = [(f, g) for f, g in sorted(gewichte.items()) if g > 0]
    if not kugeln or all(f == KEIN for f, _ in kugeln):
        return ohne(" · ".join(gruende + ["keine Form passt diese Woche"]), gewichte)

    zufall = random.Random(f"{user_id}:{montag.isoformat()}")
    form = zufall.choices([f for f, _ in kugeln], weights=[g for _, g in kugeln])[0]
    if form == KEIN:
        return ohne(" · ".join(gruende + ["diesmal ohne Doppeltag gezogen"]), gewichte)
    return {"form": form, "titel": TITEL[form], "grund": " · ".join(gruende),
            "gewichte": gewichte}


# Was je Form wohin wandert. Ohne diese Zeile wüsste der Coach, *welcher*
# Doppeltag gemeint ist, aber nicht, woraus er ihn baut — und die naheliegende
# Lesart wäre wieder eine Einheit mehr.
_UMLEGEN_JE_FORM = {
    "schwimmen_als_zweite": (
        "Lege eine Schwimmeinheit, die ohnehin in der Woche steht, als zweite "
        "Einheit auf den Tag einer harten Rad- oder Laufeinheit (abends). Es "
        "kommt **kein** zusätzliches Schwimmen dazu."
    ),
    "locker_plus_qualitaet": (
        "Ein lockerer Lauf von einem anderen Tag wird zur Morgeneinheit vor der "
        "Qualitätseinheit."
    ),
    "langer_lauf_geteilt": (
        "Teile den langen Lauf in zwei lockere Hälften am selben Tag — die "
        "Summe bleibt gleich."
    ),
    "doppelschwelle_leicht": (
        "Sie **ersetzt** die Schwelleneinheit der Woche und zählt als eine "
        "Qualitätseinheit — keine zusätzliche harte Einheit."
    ),
}


def prompt_block(z: dict | None, phase: str | None = None,
                 bedingt: bool = False) -> str:
    """Die gezogene Form als Prompt-Abschnitt. Leer ohne Doppeltag.

    `bedingt` für den Chat: Dort steht der Baustein in jeder Nachricht, auch
    bei einer Frage zur Ernährung. Unbedingt formuliert würde er den Coach
    drängen, einen Doppeltag einzubauen, um den niemand gebeten hat.
    """
    from core.race_types import phase_family

    if not z or not z.get("form"):
        return ""
    form = z["form"]
    f = DOPPEL_FORMATE[form]
    taper = " Im Taper kurz und locker (Z1–Z2)." if phase_family(phase) == "Taper" else ""
    auftrag = (
        "**Nur falls** du im Gespräch den Wochenplan dieser Woche schreibst, "
        "plane genau einen solchen Doppeltag — sonst erwähne ihn nicht von selbst."
        if bedingt else
        "Plane **genau einen** solchen Doppeltag."
    )
    return (
        f"\n## DOPPELTAG DIESER WOCHE: {z['titel']}\n"
        f"Die App hat für diese Woche diese Form gezogen ({z['grund']}). "
        f"{auftrag}\n"
        f"- {f['struktur']} — Ziel: {f['ziel']}.\n"
        f"- {_UMLEGEN_JE_FORM[form]}{taper}\n"
        f"- {UMLEGEN}\n"
        f"- Mindestens {DOPPEL_MIN_ABSTAND_H} Stunden zwischen den beiden "
        f"Einheiten.\n"
        f"- Passt er in dieser Woche nicht sinnvoll (Gesundheit, Termine, Wunsch "
        f"des Athleten), lass ihn weg und schreib es in `coaching_comment`.\n"
    )


def anpassungs_block(db: Session, von: date, bis: date, phase: str | None,
                     user_id: int | None) -> str:
    """Für die Tagesanpassung: Trägt die Woche schon einen Doppeltag?

    Sonst bekäme das Modell einen Wunsch „verschieb Dienstag" und würde den
    gezogenen Doppeltag nebenbei auflösen — oder für einen neuen Wunsch eine
    Einheit dazunehmen.
    """
    regeln = regeln_fuer(phase) or {}
    formen = formen_im_zeitraum(
        db, von, bis, user_id, regeln.get("zaehlt_als_qualitaet", QUALITAET_STRENG)
    )
    if not formen:
        return ""
    namen = ", ".join(TITEL[f] for f in sorted(formen))
    return (
        f"\n## DOPPELTAG DIESER WOCHE\nDie Woche enthält einen Doppeltag "
        f"({namen}). Beim Ändern erhalten, außer der Athlet will es anders. "
        f"{UMLEGEN}\n"
    )
