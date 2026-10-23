"""Eine geplante Einheit in die Workout-Schreibweise von intervals.icu übersetzen.

Für Läufe und Radeinheiten. intervals.icu reicht sie an die Geräte weiter, die
der Athlet dort verbunden hat (Garmin, Wahoo). FORGE weiß davon nichts und
muss es auch nicht.

intervals.icu liest Workouts als Text: Abschnittsköpfe („Warmup", „4x") und
darunter Schritte, je eine Zeile mit Bindestrich, Dauer oder Strecke und Ziel:

    Warmup
    - 1.5km 6:33-7:00/km Pace

    3x
    - 10m 232-248w
    - 2m 120-140w

Quelle ist `details` der geplanten Einheit, so wie Claude es schreibt (siehe
`core/prompt_templates.py`): `warmup`, `blocks`, `cooldown`, beim Dauerlauf
nur `dauer` und `pace`, beim Benchmark nur `struktur` oder Blöcke ohne Zahl.
Die Formen in den echten Plänen sind freier als das Schema:

- Pace mal schnell–langsam, mal langsam–schnell („7:16–6:17/km"), mit
  Zusätzen („— nach Gefühl"), oder nur „langsamer als 7:16/km".
- Watt als „105–143 W", fallend beim Ausfahren („130-110 W"), oder als Wort
  („locker", „so hoch wie gleichmäßig durchhaltbar").
- Dauer als „10 min", „90 sek", „1.5 km", „400 m", „ca. 180 min", „15–20 min".
- Wiederholungen stehen ausgeschrieben Block für Block, das „4×" nur im Text.

**Eine Zielart je Workout.** intervals.icu führt alle Schritte eines Workouts
nach derselben Größe aus (Leistung, Pace oder Puls) und gibt gemischte Ziele
nicht sauber weiter. Beim Laufen Pace, sobald ein Schritt eine trägt, sonst
Pulszone. Beim Rad Watt, sobald ein Schritt welche trägt, sonst kein Ziel.

**Keine erfundenen Ziele.** „Langsamer als 7:16/km", „nach Gefühl" oder
„locker" haben keine Zahl. Solche Schritte laufen ohne Ziel, statt eine Grenze
zu raten (dieselbe Regel wie im Planer: keine geratene Pace).

**Keine Notizen im Text.** Jede Zeile in der Beschreibung liest intervals.icu
als Teil des Workouts. Ein Satz wie „4x pro Woche" würde zur Wiederholung.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import math

from core.training_types import _RECOVERY_LABELS, _pace_band, _watt_band
from services.zones import RAD_ZONEN

LAUF = "Run"
RAD = "Ride"

# "10 min", "90 sek", "45 sec", "1.5 km", "400 m", "2:30 min"
_DAUER = re.compile(
    r"(\d+(?:[.,]\d+)?)(?::(\d{2}))?\s*(km|min|sek|sec|s|m)\b",
    re.IGNORECASE,
)
_ZONE = re.compile(r"\bZ([1-7])\b")


@dataclass(frozen=True)
class Schritt:
    sekunden: int | None = None
    meter: int | None = None
    pace: tuple[int, int] | None = None   # Sekunden/km, schnell zuerst
    watt: tuple[int, int] | None = None   # niedrig zuerst
    zone: int | None = None

    @property
    def hat_laenge(self) -> bool:
        return bool(self.sekunden or self.meter)


@dataclass(frozen=True)
class Workout:
    sport: str   # "Run" | "Ride", wie intervals.icu den Typ nennt
    name: str
    text: str


def _laenge(text) -> tuple[int | None, int | None]:
    """(Sekunden, Meter) aus einem Dauertext. Beides None, wenn unlesbar."""
    if not isinstance(text, str):
        return None, None
    treffer = _DAUER.search(text)
    if not treffer:
        return None, None
    zahl = float(treffer.group(1).replace(",", "."))
    rest = int(treffer.group(2) or 0)
    einheit = treffer.group(3).lower()
    if einheit == "km":
        return None, int(round(zahl * 1000))
    if einheit == "m":
        return None, int(round(zahl))
    if einheit == "min":
        return int(zahl * 60) + rest, None
    return int(zahl), None


def _pace(text) -> tuple[int, int] | None:
    """Pace-Bereich, schnell zuerst. „Langsamer als …" zählt nicht."""
    if not isinstance(text, str) or "langsamer als" in text.lower():
        return None
    band = _pace_band(text)
    return (min(band), max(band)) if band else None


def _watt(text) -> tuple[int, int] | None:
    """Wattbereich, niedrig zuerst. Fallend („130-110 W", Ausfahren) wird
    zum Bereich: Eine Rampe kann nicht jedes Gerät, ein Bereich schon."""
    band = _watt_band(text) if isinstance(text, str) else None
    return (min(band), max(band)) if band else None


def _zone(*texte) -> int | None:
    for text in texte:
        if isinstance(text, str):
            treffer = _ZONE.search(text)
            if treffer:
                return int(treffer.group(1))
    return None


def _ist_pause(block: dict) -> bool:
    label = str(block.get("block") or "").lower()
    return any(k in label for k in _RECOVERY_LABELS)


def _schritt(teil: dict, rueckfall_zone: int | None = None) -> Schritt:
    sekunden, meter = _laenge(teil.get("dauer"))
    return Schritt(
        sekunden=sekunden,
        meter=meter,
        pace=_pace(teil.get("pace")),
        watt=_watt(teil.get("watt")),
        zone=_zone(teil.get("zone")) or rueckfall_zone,
    )


def _struktur_schritte(text: str) -> list[tuple[str, Schritt]] | None:
    """„15 min ein — 20 min maximal gleichmäßig — 10 min aus" (Benchmark)."""
    teile = [t.strip() for t in re.split(r"\s+[—–-]\s+", text or "") if t.strip()]
    if len(teile) < 2:
        return None
    ergebnis = []
    for teil in teile:
        sekunden, meter = _laenge(teil)
        if not (sekunden or meter):
            return None
        wort = teil.lower()
        abschnitt = "Warmup" if re.search(r"\bein\b|einlaufen|einfahren", wort) else (
            "Cooldown" if re.search(r"\baus\b|auslaufen|ausfahren", wort) else "Main Set")
        ergebnis.append((abschnitt, Schritt(sekunden=sekunden, meter=meter)))
    return ergebnis


def _ist_wettkampf(teil: dict | None) -> bool:
    """Ein Rennen ist kein Workout fürs Gerät: Wer dort ein Workout startet,
    fährt oder läuft mit Alarmen statt nach Gefühl, und die Aufzeichnung heißt
    danach wie das Workout statt wie das Rennen."""
    teil = teil or {}
    return any("wettkampf" in str(teil.get(f) or "").lower() for f in ("typ", "workout"))


def teile(einheit) -> list[tuple[str, dict | None]]:
    """Was von dieser Einheit aufs Gerät geht: (Sport, Teil der Details).

    Ein Brick wird zu zwei Workouts, erst Rad, dann Lauf. Ohne den jeweiligen
    Teil fehlt das Workout: Die Gesamtdauer eines Bricks als Lauf oder als
    Fahrt zu schicken hieße, die andere Hälfte mitzumachen.
    """
    details = einheit.details if isinstance(einheit.details, dict) else None
    if einheit.discipline == "run":
        return [(LAUF, details)]
    if einheit.discipline == "bike":
        return [(RAD, details)]
    if einheit.discipline == "brick":
        ergebnis = []
        for sport, schluessel in ((RAD, "bike"), (LAUF, "run")):
            teil = (details or {}).get(schluessel)
            if isinstance(teil, dict) and teil:
                ergebnis.append((sport, teil))
        return ergebnis
    return []


# Lockere Radtypen und ihre Zone, für Einheiten ganz ohne Watt (Claude
# schreibt bei „Z2 75 min" manchmal keine Details). Nur die lockeren: Bei
# Sweet Spot oder Schwelle ohne Watt fehlt die Struktur, und ein einziger
# Block über die ganze Dauer in der Zielzone wäre eine andere Einheit.
_RAD_ZONE_LOCKER = {"recovery": 0, "z2_endurance": 1, "long_ride": 1}


def _rad_zonenwatt(einheit, ftp: int | None) -> tuple[int, int] | None:
    """Wattbereich der Zone zum lockeren Radtyp, aus der FTP in FORGE.

    Warum überhaupt ein Ziel: Wahoo nimmt Workouts mit Schritten ohne Ziel
    nicht an (Berichte im Forum von intervals.icu). Die Grenzen wie in
    `zones._rad_watt`, lückenlos an den Einstufungsgrenzen.
    """
    i = _RAD_ZONE_LOCKER.get(einheit.training_type or "")
    if i is None or not ftp:
        return None
    unten = max(1, math.ceil(ftp * RAD_ZONEN[i][1]))
    oben = math.ceil(ftp * RAD_ZONEN[i + 1][1]) - 1
    return unten, oben


def schritte(einheit, teil: dict | None, ganz: bool = True, ftp: int | None = None) -> list[tuple[str, Schritt]]:
    """Die Schritte eines Teils als (Abschnitt, Schritt), in Reihenfolge.

    `ganz`: Der Teil ist die ganze Einheit, die Gesamtdauer und die Zielwerte
    der Projektion gelten also für ihn. Beim Teil eines Bricks nicht.
    `ftp`: nur für Radeinheiten ganz ohne Watt (`_rad_zonenwatt`).
    """
    zone_einheit = _zone(einheit.target_hr_zone) if ganz else None
    gesamt = Schritt(
        sekunden=((einheit.duration_min or 0) * 60 or None) if ganz else None,
        pace=(
            (min(einheit.target_pace_low_s_per_km, einheit.target_pace_high_s_per_km),
             max(einheit.target_pace_low_s_per_km, einheit.target_pace_high_s_per_km))
            if ganz and einheit.target_pace_low_s_per_km and einheit.target_pace_high_s_per_km else None
        ),
        watt=(
            (min(einheit.target_watts_low, einheit.target_watts_high),
             max(einheit.target_watts_low, einheit.target_watts_high))
            if ganz and getattr(einheit, "target_watts_low", None) and getattr(einheit, "target_watts_high", None)
            else (_rad_zonenwatt(einheit, ftp) if ganz and einheit.discipline == "bike" else None)
        ),
        zone=zone_einheit,
    )

    if not teil:
        return [("Main Set", gesamt)] if gesamt.hat_laenge else []

    ergebnis: list[tuple[str, Schritt]] = []
    if isinstance(teil.get("warmup"), dict):
        ergebnis.append(("Warmup", _schritt(teil["warmup"], 1)))
    blocks = [b for b in (teil.get("blocks") or []) if isinstance(b, dict)]
    for block in blocks:
        ergebnis.append(("Main Set", _schritt(block, 1 if _ist_pause(block) else zone_einheit)))
    if isinstance(teil.get("cooldown"), dict):
        ergebnis.append(("Cooldown", _schritt(teil["cooldown"], 1)))

    if not blocks:
        haupt = None
        if teil.get("dauer"):
            haupt = _schritt(
                {"dauer": teil.get("dauer"), "pace": teil.get("pace"), "watt": teil.get("watt")},
                zone_einheit,
            )
        elif teil.get("struktur") and not ergebnis:
            aus_struktur = _struktur_schritte(teil["struktur"])
            if aus_struktur:
                return aus_struktur
        if haupt is None or not haupt.hat_laenge:
            # Ohne eigene Dauer: die Gesamtdauer abzüglich Ein- und Auslaufen
            # wäre geraten (die stehen oft in km). Dann die Einheit als Ganzes,
            # mit dem Ziel aus dem Text, sonst den Zielwerten der Projektion.
            haupt = Schritt(
                sekunden=gesamt.sekunden,
                pace=_pace(teil.get("pace")) or gesamt.pace,
                watt=_watt(teil.get("watt")) or gesamt.watt,
                zone=zone_einheit,
            )
            if ergebnis:
                # Ein- und Auslaufen ohne Hauptteil, dessen Länge niemand
                # kennt: lieber die ganze Einheit als einen Schritt.
                ergebnis = []
        ergebnis.insert(1 if ergebnis and ergebnis[0][0] == "Warmup" else 0, ("Main Set", haupt))

    # Ein Schritt ohne Länge lässt intervals.icu das Workout verwerfen. Dann
    # die Einheit als Ganzes, das läuft immer.
    if any(not s.hat_laenge for _, s in ergebnis):
        return [("Main Set", gesamt)] if gesamt.hat_laenge else []
    return ergebnis


# --- Text -------------------------------------------------------------------

def _mmss(sekunden: int) -> str:
    return f"{sekunden // 60}:{sekunden % 60:02d}"


def _laenge_text(s: Schritt) -> str:
    if s.meter:
        # In intervals.icu heißt „m" Minuten. Meter deshalb als Kilometer.
        return f"{s.meter / 1000:g}km"
    sek = s.sekunden or 0
    if sek < 60:
        return f"{sek}s"
    if sek % 60 == 0:
        return f"{sek // 60}m"
    # intervals.icu schreibt „1m30" für anderthalb Minuten.
    return f"{sek // 60}m{sek % 60:02d}"


def _zeile(s: Schritt, ziel: str | None) -> str:
    teile_ = [_laenge_text(s)]
    if ziel == "pace" and s.pace:
        schnell, langsam = s.pace
        band = _mmss(schnell) if schnell == langsam else f"{_mmss(schnell)}-{_mmss(langsam)}"
        teile_.append(f"{band}/km Pace")
    elif ziel == "watt" and s.watt:
        niedrig, hoch = s.watt
        teile_.append(f"{niedrig}w" if niedrig == hoch else f"{niedrig}-{hoch}w")
    elif ziel == "puls" and s.zone:
        teile_.append(f"Z{s.zone} HR")
    return "- " + " ".join(teile_)


def _falten(liste: list[Schritt]) -> list[tuple[int, list[Schritt]]]:
    """Gleiche Arbeit/Pause-Paare zu Wiederholungen zusammenfassen.

    Die Pläne schreiben „4×1 km" als sieben Blöcke aus. Auf dem Gerät liest
    sich das als „1/4, 2/4 …" besser. Ein letzter Arbeitsblock ohne Pause
    bleibt einzeln stehen, statt eine Pause anzuhängen, die der Plan nicht hat.
    """
    gruppen: list[tuple[int, list[Schritt]]] = []
    i = 0
    while i < len(liste):
        paar = liste[i:i + 2]
        anzahl = 1
        if len(paar) == 2:
            while liste[i + 2 * anzahl:i + 2 * anzahl + 2] == paar:
                anzahl += 1
        if anzahl >= 2:
            gruppen.append((anzahl, paar))
            i += 2 * anzahl
        else:
            gruppen.append((1, [liste[i]]))
            i += 1
    return gruppen


def _text(liste: list[tuple[str, Schritt]], sport: str) -> str | None:
    if sport == RAD:
        ziel = "watt" if any(s.watt for _, s in liste) else None
    else:
        ziel = "pace" if any(s.pace for _, s in liste) else "puls"

    # Jeder Block bekommt seinen eigenen Kopf: „Warmup", „Main Set" oder
    # „4x". So ist eindeutig, wo eine Wiederholung endet. Einzelne Schritte
    # nach einer Wiederholung stehen wieder unter „Main Set", sonst zählte
    # intervals.icu sie womöglich zur Wiederholung davor.
    bloecke: list[tuple[str, list[Schritt]]] = []
    for abschnitt in ("Warmup", "Main Set", "Cooldown"):
        teil = [s for a, s in liste if a == abschnitt]
        if not teil:
            continue
        if abschnitt != "Main Set":
            bloecke.append((abschnitt, teil))
            continue
        for anzahl, gruppe in _falten(teil):
            if anzahl > 1:
                bloecke.append((f"{anzahl}x", gruppe))
            elif bloecke and bloecke[-1][0] == "Main Set":
                bloecke[-1][1].extend(gruppe)
            else:
                bloecke.append(("Main Set", list(gruppe)))

    zeilen: list[str] = []
    for kopf, gruppe in bloecke:
        if zeilen:
            zeilen.append("")
        zeilen.append(kopf)
        zeilen.extend(_zeile(s, ziel) for s in gruppe)
    return "\n".join(zeilen) or None


def _name(einheit, teil: dict | None, sport: str, brick: bool) -> str:
    teil = teil or {}
    # Beim Rad trägt `workout` oft den Namen aus dem Zwift-Katalog, der ist
    # auf dem Gerät der verständlichste.
    titel = str(teil.get("workout") or teil.get("typ") or "").strip()
    if not titel:
        titel = (einheit.training_type or ("Lauf" if sport == LAUF else "Rad")).replace("_", " ").title()
    if brick:
        titel = f"Koppel {'Rad' if sport == RAD else 'Lauf'} · {titel}"
    return f"FORGE · {titel}"[:80]


def workouts(einheit, ftp: int | None = None) -> list[Workout]:
    """Die Workouts dieser Einheit für intervals.icu. Leer, wenn keines.

    `ftp` aus dem Profil, nur für lockere Radeinheiten ganz ohne Watt.
    """
    stuecke = teile(einheit)
    brick = einheit.discipline == "brick"
    ergebnis = []
    for sport, teil in stuecke:
        if _ist_wettkampf(teil):
            continue
        liste = schritte(einheit, teil, ganz=not brick, ftp=ftp)
        text = _text(liste, sport) if liste else None
        if text:
            ergebnis.append(Workout(sport=sport, name=_name(einheit, teil, sport, brick), text=text))
    return ergebnis
