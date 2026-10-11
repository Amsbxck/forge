"""Intervallformate erkennen — aus einer Vorgabe und aus dem Zwift-Katalog.

Zwei Dinge brauchen dasselbe Wissen:

* Der **Nachschlag**: Der Katalog stand früher als Pflichtbibliothek im Prompt
  („Verwende für jede Bike-Session EINE dieser Strukturen als Basis") und belegte
  dort rund 27 % des Platzes — die studienbelegten Formatregeln hatten dagegen
  keine Chance. Jetzt baut der Coach die Struktur selbst, und hinterher sucht
  dieser Code den passenden Zwift-Namen, damit die Einheit im Trainer weiterhin
  zu finden ist. Findet sich keiner, bleibt die Notiz leer — ein falscher Name
  wäre schlimmer als keiner.

* Die **Rotation**: Kein Intervallformat ist nachweislich besser als das andere
  (Norte 2023), also soll über die Aufbauwochen gewechselt werden. Dafür muss
  man wissen, was in den Vorwochen *vorgegeben* war. Das steht in
  `planned_sessions.details` — bisher las das niemand; gelesen wurden nur die
  *absolvierten* Strukturen, und die nur 14 Tage weit.

Erkannt wird bewusst wenig und sicher: `4×8min`, `3×3min`, `30/15`, `40/20`.
Was nicht sicher erkennbar ist, bleibt `None` und wird nicht geraten.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


# Kurze Wechselformate stehen als Zahlenpaar. Sekunden, nicht Minuten:
# "30/15" ist 30 s hart und 15 s locker. Zwei Schreibweisen kommen vor —
# "30/15" und "40sec … + 20sec Pause" —, und bei einigen Einträgen steht das
# Format nur im Namen ("40/20's #1"), nicht in der Strukturbeschreibung.
WECHSEL = re.compile(
    r"\b(\d{2})\s*(?:sec|s)?\s*(?:/|\+)\s*(\d{2})\s*(?:sec|s)?\b",
    re.IGNORECASE,
)

# "3×5min", "4 x 8 min", "2x20min" — das Arbeitsintervall mit Wiederholungen.
WIEDERHOLUNG = re.compile(
    r"(\d+)\s*[×x]\s*(\d+)(?::(\d+))?\s*min",
    re.IGNORECASE,
)

# "@110-115% FTP", "@88% FTP"
PROZENT = re.compile(r"@\s*(\d+)(?:\s*[-–]\s*(\d+))?\s*%")

# "212-222 W", "250W"
WATT = re.compile(r"(\d+)\s*(?:[-–]\s*(\d+))?\s*W", re.IGNORECASE)

# "8 min", "2:30min", "45 sec"
DAUER = re.compile(r"(\d+)(?::(\d+))?\s*(min|sec|s)\b", re.IGNORECASE)


@dataclass(frozen=True)
class Struktur:
    """Ein Intervallformat, so weit es sicher erkannt wurde."""

    wdh: int | None = None
    dauer_s: int | None = None
    prozent_min: int | None = None
    prozent_max: int | None = None
    wechsel: tuple[int, int] | None = None

    @property
    def kennung(self) -> str | None:
        """Der kurze Name des Formats: „4x8", „30/15"."""
        if self.wechsel:
            return f"{self.wechsel[0]}/{self.wechsel[1]}"
        if self.wdh and self.dauer_s:
            if self.dauer_s % 60 == 0:
                return f"{self.wdh}x{self.dauer_s // 60}"
            return f"{self.wdh}x{self.dauer_s // 60}:{self.dauer_s % 60:02d}"
        return None

    def __bool__(self) -> bool:
        return bool(self.wechsel or (self.wdh and self.dauer_s))


def _sekunden(zahl: str, rest: str | None, einheit: str) -> int:
    wert = int(zahl) * 60 + int(rest or 0) if einheit.lower() == "min" else int(zahl)
    return wert


def aus_text(text: str | None) -> Struktur:
    """Format aus einer Freitextbeschreibung — Katalog oder Vorgabe."""
    if not text:
        return Struktur()

    wechsel = None
    if treffer := WECHSEL.search(text):
        hart, pause = int(treffer.group(1)), int(treffer.group(2))
        # Nur plausible Wechselformate: 15–60 s hart, Pause nicht länger als
        # das Doppelte. Sonst fängt die Regel Jahreszahlen und Wattwerte.
        if 15 <= hart <= 60 and 10 <= pause <= 2 * hart:
            wechsel = (hart, pause)

    wdh = dauer_s = None
    if treffer := WIEDERHOLUNG.search(text):
        wdh = int(treffer.group(1))
        dauer_s = _sekunden(treffer.group(2), treffer.group(3), "min")
        if not (1 <= wdh <= 30 and 30 <= dauer_s <= 60 * 40):
            wdh = dauer_s = None

    p_min = p_max = None
    if treffer := PROZENT.search(text):
        p_min = int(treffer.group(1))
        p_max = int(treffer.group(2) or treffer.group(1))

    return Struktur(wdh=wdh, dauer_s=dauer_s, prozent_min=p_min,
                    prozent_max=p_max, wechsel=wechsel)


def aus_vorgabe(details: dict | None, ftp: int | None = None) -> Struktur:
    """Format aus den `details` einer geplanten Einheit.

    Rad-Vorgaben stehen als `blocks`-Liste, in der die Arbeitsblöcke mit einer
    Nummer und die Pausen mit „Erholung" benannt sind. Läufe tragen den
    Hauptteil als Text in `struktur`.
    """
    if not details:
        return Struktur()

    # Lauf und alles andere mit Freitext.
    for schluessel in ("struktur", "workout", "typ"):
        if isinstance(details.get(schluessel), str):
            if (s := aus_text(details[schluessel])):
                return s

    blocks = details.get("blocks")
    if not isinstance(blocks, list):
        return Struktur()

    arbeit = []
    for b in blocks:
        if not isinstance(b, dict):
            continue
        name = str(b.get("block", "")).strip().lower()
        # Pausen und Erholungen zählen nicht als Arbeitsintervall.
        if not name or any(w in name for w in ("erholung", "pause", "recovery")):
            continue
        treffer = DAUER.search(str(b.get("dauer", "")))
        if not treffer:
            continue
        arbeit.append((
            _sekunden(treffer.group(1), treffer.group(2), treffer.group(3)),
            str(b.get("watt", "")),
        ))

    if not arbeit:
        return Struktur()

    # Nur gleichförmige Serien ergeben ein Format. Eine Pyramide
    # (2→4→6→8min) ist keine „4×8", und sie so zu nennen wäre falsch.
    dauern = {d for d, _ in arbeit}
    if len(dauern) != 1:
        return Struktur()
    dauer_s = dauern.pop()

    p_min = p_max = None
    if ftp:
        watt_werte = []
        for _d, watt in arbeit:
            if treffer := WATT.search(watt):
                watt_werte.append(int(treffer.group(1)))
                if treffer.group(2):
                    watt_werte.append(int(treffer.group(2)))
        if watt_werte:
            p_min = round(min(watt_werte) / ftp * 100)
            p_max = round(max(watt_werte) / ftp * 100)

    return Struktur(wdh=len(arbeit), dauer_s=dauer_s,
                    prozent_min=p_min, prozent_max=p_max)


# Welche Katalogkategorie zu welchem Trainingstyp gehört.
KATEGORIE_JE_TYP = {
    "sweet_spot": "sst_tempo",
    "tempo": "sst_tempo",
    "race_pace": "sst_tempo",
    "threshold": "threshold",
    "vo2max": "vo2max",
    "intervals": "vo2max",
    "z2_endurance": "endurance",
    "recovery": "endurance",
    "long_ride": "endurance",
}


def zwift_name(struktur: Struktur, training_type: str | None,
               dauer_min: int | None = None) -> str | None:
    """Der Zwift-Workoutname zu einer geplanten Struktur — oder nichts.

    Verlangt wird eine enge Übereinstimmung: gleiche Kategorie, gleiches
    Format und eine Gesamtdauer innerhalb von zehn Prozent. Alles darunter
    bekommt keinen Namen. Ein ungefähr passender Name wäre eine Behauptung
    über eine Einheit, die der Athlet dann im Trainer nicht wiedererkennt.
    """
    if not struktur:
        return None
    kategorie = KATEGORIE_JE_TYP.get((training_type or "").lower())
    if not kategorie:
        return None

    from core.zwift_catalog import ALL_CATALOGS

    kennung = struktur.kennung
    for eintrag in ALL_CATALOGS.get(kategorie, []):
        # Bei einigen Einträgen steht das Format nur im Namen ("40/20's #1",
        # "30/30 Anaerobic #1") und nicht in der Strukturbeschreibung.
        kandidaten = {
            aus_text(eintrag.get("key_blocks")).kennung,
            aus_text(eintrag.get("name")).kennung,
        }
        if kennung not in kandidaten:
            continue
        if dauer_min and eintrag.get("duration_min"):
            abweichung = abs(eintrag["duration_min"] - dauer_min) / dauer_min
            if abweichung > 0.10:
                continue
        # Gleiches Format ist nicht genug: 4×8min bei 85 % FTP und 4×8min bei
        # 105 % sind zwei verschiedene Einheiten. Wenn beide Seiten eine
        # Intensität nennen, muss sie sich überschneiden.
        if struktur.prozent_min and struktur.prozent_max:
            katalog = aus_text(eintrag.get("key_blocks"))
            if katalog.prozent_min and katalog.prozent_max:
                if (struktur.prozent_max < katalog.prozent_min - 5
                        or struktur.prozent_min > katalog.prozent_max + 5):
                    continue
        return eintrag["name"]
    return None


# Welche Trainingstypen überhaupt ein Format haben, über das sich rotieren
# lässt. Lockere Einheiten brauchen keine Abwechslung im Intervallschnitt.
ROTIERBAR = ("vo2max", "threshold", "sweet_spot", "intervals", "tempo")


def letzte_formate(db, bis, wochen: int = 6, user_id: int | None = None) -> list[tuple]:
    """Welche Intervallformate in den letzten Wochen **vorgegeben** waren.

    Gelesen wird die Vorgabe, nicht das Absolvierte. Bisher las nur
    `services/session_view.py` Strukturen, und zwar die absolvierten aus den
    Runden der Uhr — 14 Tage weit. Daraus ließ sich nicht erkennen, was der
    Plan *gewollt* hatte, und ohne das kann man nicht bewusst wechseln.
    """
    from datetime import timedelta

    from models import AthleteProfile, PlannedSession

    von = bis - timedelta(weeks=wochen)
    abfrage = db.query(PlannedSession).filter(
        PlannedSession.planned_date >= von,
        PlannedSession.planned_date < bis,
        PlannedSession.discipline.in_(("bike", "run", "brick")),
    )
    if user_id is not None:
        abfrage = abfrage.filter(PlannedSession.user_id == user_id)

    try:
        einheiten = abfrage.order_by(PlannedSession.planned_date).all()
        profil = db.query(AthleteProfile).filter(
            AthleteProfile.user_id == user_id
        ).first() if user_id else None
    except Exception:  # pragma: no cover - ohne Projektionstabelle gibt es nichts
        return []
    ftp = getattr(profil, "ftp_watts", None)

    aus = []
    for e in einheiten:
        if (e.training_type or "").lower() not in ROTIERBAR:
            continue
        kennung = aus_vorgabe(e.details, ftp).kennung
        if kennung:
            aus.append((e.planned_date, e.discipline, e.training_type, kennung))
    return aus


def rotation_block(db, bis, phase: str | None, wochen: int = 6,
                   user_id: int | None = None) -> str:
    """Die Formatreihe der Vorwochen als Rotationsanweisung.

    Kein Intervallformat ist nachweislich besser als die anderen (Norte 2023).
    Daraus folgt nicht Beliebigkeit, sondern Wechsel: Wenn die Wirkung gleich
    ist, entscheidet, was der Athlet durchhält — und dreimal dasselbe
    Programm hintereinander hält niemand gern durch.
    """
    from core.race_types import phase_family

    # In Grundlage und Off Season gibt es keine Formatrotation: dort steht
    # höchstens eine Qualitätseinheit pro Woche, und die soll stabil sein.
    if phase_family(phase) not in ("Build", "Peak"):
        return ""

    formate = letzte_formate(db, bis, wochen, user_id)
    if not formate:
        return ""

    je_disziplin: dict[str, list[str]] = {}
    for _tag, disziplin, _typ, kennung in formate:
        je_disziplin.setdefault(disziplin, []).append(kennung)

    zeilen = ["\n## ABWECHSLUNG DER INTERVALLFORMATE"]
    for disziplin, reihe in sorted(je_disziplin.items()):
        zeilen.append(f"- Zuletzt vorgegeben ({disziplin}): {' · '.join(reihe)}")

    rad = je_disziplin.get("bike", [])
    if rad:
        letztes = rad[-1]
        andere = [f for f in ("30/15", "4x8", "5x5") if f != letztes]
        auswahl = (
            ", ".join(andere[:-1]) + " oder " + andere[-1]
            if len(andere) > 1 else andere[0]
        )
        zeilen.append(
            f"- **Wähle fürs Rad diese Woche ein anderes Format als {letztes}** — "
            f"etwa {auswahl}. Kein Format ist nachweislich "
            f"überlegen, deshalb ist der Wechsel kein Kompromiss: Er hält die "
            f"Reize vollständig und die Einheiten erträglich."
        )
    if je_disziplin.get("run"):
        zeilen.append(
            "- **Beim Laufen gilt das nicht gleich:** dort sind "
            "VO2max-Wiederholungen ab drei Minuten den kurzen deutlich "
            "überlegen. Variiere die Streckenlänge und das Gelände, nicht die "
            "Intervalldauer nach unten."
        )
    return "\n".join(zeilen) + "\n"


def namen_nachtragen(db, plan) -> int:
    """Trägt passende Zwift-Namen in die Rad-Vorgaben eines Plans nach.

    Läuft nach der Projektion, nicht im Prompt. Der Coach baut die Struktur
    aus den Formatregeln; der Name ist eine Bequemlichkeit für den Trainer und
    hat die Planung früher dominiert, als er noch als Pflichtbibliothek im
    Prompt stand.

    Ein vorhandener Eintrag wird nicht überschrieben: dort steht manchmal eine
    Beschreibung, die der Coach bewusst gesetzt hat („Benchmark
    20-Minuten-FTP-Test"), und die ist mehr wert als ein Katalogname.
    """
    from models import AthleteProfile, PlannedSession

    try:
        profil = db.query(AthleteProfile).filter(
            AthleteProfile.user_id == plan.user_id
        ).first()
        ftp = getattr(profil, "ftp_watts", None)

        einheiten = db.query(PlannedSession).filter(
            PlannedSession.plan_id == plan.id,
            PlannedSession.discipline == "bike",
        ).all()
    except Exception:  # pragma: no cover - ohne Projektionstabelle gibt es nichts
        return 0

    getroffen = 0
    for einheit in einheiten:
        details = einheit.details or {}
        if details.get("workout"):
            continue
        name = zwift_name(
            aus_vorgabe(details, ftp),
            einheit.training_type,
            einheit.duration_min,
        )
        if not name:
            continue
        # Neu zuweisen, nicht in der Stelle ändern: SQLAlchemy erkennt eine
        # Änderung innerhalb eines JSONB-Dicts sonst nicht.
        einheit.details = {**details, "workout": name}
        getroffen += 1

    if getroffen:
        db.commit()
    return getroffen
