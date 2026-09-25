"""Kontrolliertes Vokabular für Sportart und Trainingstyp.

Diese Enums sind der Vertrag zwischen drei Stellen, die sonst auseinanderdriften:
  1. Claude-Plangenerierung (Tool-Schema erzwingt die Werte)
  2. Klassifizierung der Ist-Daten aus Strava (actual_type)
  3. Obsidian-Notes (Frontmatter-Feld + Tag)

Nur wenn alle drei dasselbe Vokabular benutzen, lässt sich Soll gegen Ist
abgleichen. Deshalb leben die Listen hier und nicht verstreut in den Modulen.
"""

import re

# Sportart — entspricht dem bestehenden day["session_type"] im Plan-JSON
# und TrainingSession.discipline aus dem Strava-Mapping.
# "hike" ist keine Trainingsvorgabe, aber echte Belastung — und es darf auf
# keinen Fall als Lauf gezählt werden: eine vierstündige Wanderung bei HF 113
# erzeugt sonst mehr Lauf-TSS als eine 6-Stunden-Radausfahrt und verzerrt
# Wochenlast, Trends und jeden Coaching-Prompt.
# "other" ist die Auffangkategorie für alles, was die App nicht plant, aber
# mitzählen soll — StairMaster, Rudern, Crosstrainer, Skitouren. Ohne sie
# fällt jede fremde Sportart aus Auswertung und Anzeige heraus, obwohl die
# Einheit stattgefunden hat.
DISCIPLINES = ["bike", "run", "swim", "gym", "brick", "hike", "rest", "other"]

# Trainingstyp je Sportart — das neue day["training_type"].
TRAINING_TYPES: dict[str, list[str]] = {
    "bike": [
        "recovery",
        "z2_endurance",
        "sweet_spot",
        "threshold",
        "vo2max",
        "race_pace",
        "long_ride",
    ],
    "run": [
        "recovery",
        "walk_run",
        "z2_endurance",
        "tempo",
        "intervals",
        "threshold",
        "vo2max",
        "brick_run",
        "long_run",
    ],
    "swim": ["technique", "endurance", "intervals", "open_water"],
    "gym": ["strength", "mobility"],
    "brick": ["brick"],
    "hike": ["hike"],
    # Ersatztraining ohne eigene Planlogik: StairMaster, Crosstrainer,
    # Ruderergometer, Aquajogging. Wird gebraucht, sobald eine Disziplin
    # verletzungsbedingt ausfällt.
    "other": ["cross_training"],
    "rest": ["rest"],
}

# Flache Liste für das Tool-Schema — Claude bekommt ein einziges enum und die
# Zuordnung zur Sportart als Prompt-Regel. Ein verschachteltes Schema wäre
# strenger, aber die Anthropic-Tool-Validierung kennt kein oneOf-per-Feld.
ALL_TRAINING_TYPES = sorted({t for types in TRAINING_TYPES.values() for t in types})


# Pläne vor Schema v2 haben statt eines Enums oft deutschen Freitext in
# session_type ("laufen + optional Pass", "Rad Bergintervalle + Brick Lauf").
# Reihenfolge ist bewusst: brick vor allem anderen, weil solche Einträge
# beide Sportarten nennen; run vor bike, damit "Laufen + optional Pass"
# nicht am Wort "Pass" hängen bleibt.
_DISCIPLINE_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("brick", ("brick", "koppel")),
    ("swim", ("swim", "schwimm", "becken", "freiwasser")),
    ("hike", ("hike", "hiking", "wander")),
    ("run", ("run", "lauf", "jog")),
    ("bike", ("bike", "rad", "cycl", "ride", "zwift", "pass", "rolle")),
    ("gym", ("gym", "kraft", "strength", "mobility", "athletik", "stabi")),
    ("rest", ("rest", "ruhe", "off", "pause", "frei")),
]

# Nur eindeutige Signale — im Zweifel lieber None und der Fallback greift.
_TYPE_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("walk_run", ("walk-run", "walk run", "gehpause")),
    ("sweet_spot", ("sweet spot", "sweetspot", "sst")),
    ("vo2max", ("vo2", "bergintervall")),
    ("threshold", ("threshold", "schwelle", "ftp-test", "ftp test")),
    ("race_pace", ("race pace", "race-pace", "wettkampfpace")),
    ("intervals", ("intervall", "interval")),
    ("recovery", ("recovery", "regeneration", "erholung", "locker")),
    ("open_water", ("freiwasser", "open water")),
    ("technique", ("technik", "technique", "drill")),
    ("z2_endurance", ("endurance", "grundlage", "z2", "dauerlauf")),
]


def normalize_discipline(raw: str | None) -> str | None:
    """Freitext-Sportart auf das Enum abbilden. None, wenn nichts passt."""
    if not raw:
        return None
    value = raw.strip().lower()
    if value in DISCIPLINES:
        return value
    for discipline, keywords in _DISCIPLINE_KEYWORDS:
        if any(k in value for k in keywords):
            return discipline
    return None


def infer_training_type(discipline: str | None, *texts: str | None) -> str | None:
    """Trainingstyp aus Freitext raten — nur bei eindeutigen Stichworten.

    Wird für Alt-Pläne benutzt, in denen der Typ nur im Namen der Einheit
    steckt. Ein Treffer zählt nur, wenn er zur Sportart passt.
    """
    blob = " ".join(t.lower() for t in texts if t)
    if not blob:
        return None
    for training_type, keywords in _TYPE_KEYWORDS:
        if any(k in blob for k in keywords) and is_valid_training_type(discipline, training_type):
            return training_type
    return None


# --- Intensitätsstufen -------------------------------------------------------
# Grobere Ebene über dem Trainingstyp, nach Zonen geschnitten. Sie ordnet den
# Trainingsplan und die Obsidian-Ordner, damit sich Einheiten gleicher Härte
# vergleichen lassen — auch über Sportarten hinweg.
#
# Nur für Rad und Lauf: Schwimmen läuft nach einem eigenen Plan und hat
# weder Leistungsdaten noch belastbare HF, die eine Einstufung trügen.

# Brick zählt mit: er besteht aus Rad und Lauf und hat damit sehr wohl eine
# Härte. Ohne ihn zeigte der Wochenplan bei Brick-Tagen nur die rohe Zielzone
# und sah neben den eingestuften Tagen inkonsistent aus.
INTENSITY_DISCIPLINES = ("bike", "run", "brick")

# Ordner für alles, was zu keiner Trainingsstruktur gehört — Wanderungen,
# Ausflüge, Einheiten ohne jede Messgröße.
FUN_FOLDER = "fun"
FUN_DISCIPLINES = ("hike", "other")

# Disziplinen, deren Inhalt aus einem externen Trainingsplan kommt. Der Coach
# setzt dafür nur den Termin; wie die Einheit aussieht, steht im Vereins- oder
# Schwimmtrainerplan. Deshalb darf aus ihnen auch kein Progressionssignal
# gelesen werden: Ob die lange Schwimmeinheit wächst oder schrumpft, entscheidet
# nicht dieser Plan — eine schrumpfende Reihe sähe hier nach Rückschritt aus und
# hätte den Coach dazu gebracht, gegen einen Plan zu steuern, den er nicht kennt.
# Freiwasser ist die Ausnahme (dafür gibt es keinen externen Plan), aber es hängt
# an derselben Disziplin und lässt sich an dieser Stelle nicht trennen.
EXTERN_GEPLANT = ("swim",)

INTENSITIES = ["base", "sweet_spot", "threshold", "vo2max"]

INTENSITY_LABEL = {
    "base": "Base / Endurance",
    "sweet_spot": "Sweet Spot",
    "threshold": "Threshold",
    "vo2max": "VO₂max",
}

INTENSITY_ZONE = {
    "base": "Z1–Z2",
    "sweet_spot": "Z3",
    "threshold": "Z4",
    "vo2max": "Z5",
}

# Zuordnung Trainingstyp → Intensität. Für geplante Einheiten ist das die
# einzige Quelle; bei gefahrenen Einheiten schlagen die echten Messwerte diese
# Tabelle (siehe classification.intensity_from_session).
INTENSITY_BY_TYPE = {
    # Rad
    "recovery": "base",
    "z2_endurance": "base",
    "long_ride": "base",
    "sweet_spot": "sweet_spot",
    "race_pace": "sweet_spot",   # 70.3-Renntempo liegt bei ~80-85% FTP
    "threshold": "threshold",
    "vo2max": "vo2max",
    # Lauf
    "walk_run": "base",
    "long_run": "base",
    "brick_run": "base",
    "tempo": "sweet_spot",
    "intervals": "vo2max",       # wird von den Ist-Daten überschrieben, wenn Z4-lastig
}

# Für den Lauf gelten dieselben Stufen wie beim Rad — threshold und vo2max
# stehen in beiden Vokabularen und sind hier schon abgedeckt.


# Zielzone → Stufe. Nötig für Bricks: deren training_type ist "brick" und
# sagt nichts über die Härte, wohl aber die geplante HF-Zone.
ZONE_TO_INTENSITY = {
    "Z1": "base",
    "Z2": "base",
    "Z3": "sweet_spot",
    "Z4": "threshold",
    "Z5": "vo2max",
}


def intensity_for_type(
    discipline: str | None,
    training_type: str | None,
    hr_zone: str | None = None,
) -> str | None:
    """Intensitätsstufe einer geplanten Einheit.

    Erst über den Trainingstyp, ersatzweise über die geplante Zielzone.
    """
    if (discipline or "").lower() not in INTENSITY_DISCIPLINES:
        return None
    by_type = INTENSITY_BY_TYPE.get(training_type or "")
    if by_type:
        return by_type
    return ZONE_TO_INTENSITY.get((hr_zone or "").upper())


def intensity_label(intensity: str | None, with_zone: bool = True) -> str | None:
    """Anzeigename, z.B. 'Sweet Spot (Z3)'."""
    if not intensity:
        return None
    label = INTENSITY_LABEL.get(intensity, intensity)
    zone = INTENSITY_ZONE.get(intensity)
    return f"{label} ({zone})" if with_zone and zone else label


def is_valid_training_type(discipline: str | None, training_type: str | None) -> bool:
    """Passt der Trainingstyp zur Sportart?"""
    if not discipline or not training_type:
        return False
    return training_type in TRAINING_TYPES.get(discipline.lower(), [])


def default_training_type(discipline: str | None) -> str | None:
    """Fallback für Altpläne ohne training_type.

    Bewusst konservativ: der häufigste Typ je Sportart, damit der Abgleich
    etwas zum Vergleichen hat. Wird von der Klassifizierung später anhand der
    Ist-Daten überschrieben.
    """
    return {
        "bike": "z2_endurance",
        "run": "walk_run",
        "swim": "endurance",
        "gym": "strength",
        "brick": "brick",
        "rest": "rest",
    }.get((discipline or "").lower())


# --- Zielwerte aus Alt-Plänen extrahieren -------------------------------------
# Pläne vor Schema v2 haben Zielwerte nur als Freitext in details ("145-155 W",
# "6:00-6:50/km"). Für den Backfill holen wir heraus, was sich verlässlich
# parsen lässt — der Rest bleibt None statt geraten zu werden.

_WATT_RANGE = re.compile(r"(\d{2,3})\s*[-–]\s*(\d{2,3})\s*W", re.IGNORECASE)
_WATT_SINGLE = re.compile(r"(\d{2,3})\s*W", re.IGNORECASE)
_PACE_RANGE = re.compile(r"(\d):(\d{2})\s*[-–]\s*(\d):(\d{2})\s*/\s*km")
_PACE_SINGLE = re.compile(r"(\d):(\d{2})\s*/\s*km")
_HR_ZONE = re.compile(r"\b(Z[1-5])\b")


def _flatten_text(value, out: list[str]) -> None:
    if isinstance(value, dict):
        for v in value.values():
            _flatten_text(v, out)
    elif isinstance(value, list):
        for v in value:
            _flatten_text(v, out)
    elif isinstance(value, str):
        out.append(value)


# Blocklabels, die eine Erholung bezeichnen — der Rest ist Arbeit.
_RECOVERY_LABELS = ("erholung", "recovery", "pause", "trabpause", "locker")


def _watt_band(text: str | None) -> tuple[int, int] | None:
    """Wattbereich aus einem Textschnipsel wie "200–215 W" oder "264 W"."""
    if not text:
        return None
    ranges = _WATT_RANGE.findall(text)
    if ranges:
        low, high = ranges[0]
        return int(low), int(high)
    singles = _WATT_SINGLE.findall(text)
    if singles:
        value = int(singles[0])
        return value, value
    return None


def _pace_band(text: str | None) -> tuple[int, int] | None:
    """Pace-Bereich in Sekunden/km aus "4:10-4:30/km" oder "6:00/km"."""
    if not text:
        return None
    ranges = _PACE_RANGE.findall(text)
    if ranges:
        a, b, c, d = ranges[0]
        return int(a) * 60 + int(b), int(c) * 60 + int(d)
    singles = _PACE_SINGLE.findall(text)
    if singles:
        m, s = singles[0]
        value = int(m) * 60 + int(s)
        return value, value
    return None


def extract_segment_targets(details: dict | None, part: str | None = None) -> dict:
    """Zielwerte je Abschnitt aus der Blockstruktur des Plans.

    Der Plan gibt nicht nur die Intervallvorgabe, sondern auch die für
    Erholungen sowie Ein- und Ausfahren. Ohne diese Zuordnung stünde in der
    Note neben jedem Abschnitt außer dem Hauptteil ein Strich, obwohl die
    Vorgabe danebensteht.

    Liefert je Abschnitt beide Größen: ``{"main": {"watt": (200, 215)}}``
    beim Rad, ``{"main": {"pace": (250, 270)}}`` beim Laufen.
    """
    if not details:
        return {}

    # Bei Bricks liegen Rad- und Laufstruktur je eine Ebene tiefer.
    source = details
    if part and isinstance(details.get(part), dict):
        source = details[part]
    elif isinstance(details.get("bike"), dict) and part is None:
        source = details["bike"]
    if not isinstance(source, dict):
        return {}

    def _bands(text_or_dict, field: str) -> dict:
        """Watt und Pace aus einem Block oder einem Textfeld."""
        if isinstance(text_or_dict, dict):
            watt = _watt_band(text_or_dict.get("watt"))
            pace = _pace_band(text_or_dict.get("pace"))
        else:
            watt = _watt_band(text_or_dict)
            pace = _pace_band(text_or_dict)
        out = {}
        if watt:
            out["watt"] = watt
        if pace:
            out["pace"] = pace
        return out

    result: dict[str, dict] = {}

    # Ein-/Ausfahren liegt je nach Planalter als Objekt vor oder noch als
    # Fließtext. Beide Formen lesen, damit ältere Pläne keine Lücken zeigen.
    for key in ("warmup", "cooldown"):
        bands = _bands(source.get(key), key)
        if bands:
            result[key] = bands

    blocks = source.get("blocks")
    if isinstance(blocks, list):
        work, recovery = [], []
        for block in blocks:
            if not isinstance(block, dict):
                continue
            bands = _bands(block, "block")
            if not bands:
                continue
            label = str(block.get("block") or "").lower()
            (recovery if any(k in label for k in _RECOVERY_LABELS) else work).append(bands)

        # Der anspruchsvollste Arbeitsblock ist die Vorgabe: beim Rad die
        # höchste Leistung, beim Laufen die schnellste Pace.
        if work:
            watts = [b["watt"] for b in work if "watt" in b]
            paces = [b["pace"] for b in work if "pace" in b]
            main = {}
            if watts:
                main["watt"] = max(watts, key=lambda band: band[0])
            if paces:
                main["pace"] = min(paces, key=lambda band: band[0])
            if main:
                result["main"] = main
        if recovery:
            watts = [b["watt"] for b in recovery if "watt" in b]
            paces = [b["pace"] for b in recovery if "pace" in b]
            rec = {}
            if watts:
                rec["watt"] = min(watts, key=lambda band: band[0])
            if paces:
                rec["pace"] = max(paces, key=lambda band: band[0])
            if rec:
                result["recovery"] = rec

    return result


def extract_pace_bands(details: dict | None) -> list[tuple[int, int]]:
    """Alle Pace-Bereiche aus dem Plantext, sortiert vom schnellsten an.

    Pläne nennen typischerweise zwei: die Ziel-Pace des Hauptteils und eine
    lockerere fürs Ein- und Auslaufen. Getrennt gehalten lassen sich beide
    gegen die tatsächlichen Abschnitte vergleichen.
    """
    if not details:
        return []
    parts: list[str] = []
    _flatten_text(details, parts)
    bands = [
        (int(a) * 60 + int(b), int(c) * 60 + int(d))
        for a, b, c, d in _PACE_RANGE.findall(" ".join(parts))
    ]
    return sorted(set(bands), key=lambda band: band[0])


def extract_targets_from_details(details: dict | None) -> dict:
    """Best-effort-Zielwerte aus dem Freitext eines Alt-Plans.

    Liefert nur Felder, die eindeutig gefunden wurden. Lieber None als eine
    erfundene Zahl — der Ist/Soll-Abgleich soll auf Lücken hinweisen können.
    """
    if not details:
        return {}

    parts: list[str] = []
    _flatten_text(details, parts)
    blob = " ".join(parts)

    targets: dict = {}

    # Gibt es eine Blockstruktur, ist der Arbeitsblock die Vorgabe. Ein
    # pauschaler Scan über den ganzen Text würde Aufwärm- und Erholungswatt
    # einschließen und das Zielband nach unten aufweichen — aus "145-155 W
    # Hauptteil" plus "100-140 W Einfahren" würde 100-155 W.
    segment_main = (extract_segment_targets(details).get("main") or {}).get("watt")
    if segment_main:
        targets["watts_low"], targets["watts_high"] = segment_main
    else:
        watt_ranges = _WATT_RANGE.findall(blob)
        if watt_ranges:
            lows = [int(a) for a, _ in watt_ranges]
            highs = [int(b) for _, b in watt_ranges]
            targets["watts_low"] = min(lows)
            targets["watts_high"] = max(highs)
        else:
            singles = [int(w) for w in _WATT_SINGLE.findall(blob)]
            if singles:
                targets["watts_low"] = min(singles)
                targets["watts_high"] = max(singles)

    pace_ranges = _PACE_RANGE.findall(blob)
    if pace_ranges:
        # Nicht alle gefundenen Bereiche verschmelzen: ein Plan nennt neben
        # der Ziel-Pace meist auch die fürs Ein- und Auslaufen. Aus
        # "5:00–5:15/km | WU/CD: 6:00–6:30/km" würde sonst ein Band von
        # 5:00 bis 6:30, in das praktisch jede Einheit fällt.
        # Der schnellste Bereich ist der Hauptteil — auf den kommt es an.
        bands = [
            (int(a) * 60 + int(b), int(c) * 60 + int(d))
            for a, b, c, d in pace_ranges
        ]
        low, high = min(bands, key=lambda band: band[0])
        targets["pace_low_s_per_km"] = low
        targets["pace_high_s_per_km"] = high
    else:
        singles = [int(m) * 60 + int(s) for m, s in _PACE_SINGLE.findall(blob)]
        if singles:
            targets["pace_low_s_per_km"] = min(singles)
            targets["pace_high_s_per_km"] = max(singles)

    zones = _HR_ZONE.findall(blob)
    if zones:
        # Häufigste genannte Zone gewinnt — bei Intervallen steht die Zielzone
        # meist öfter da als die Erholungszone.
        targets["hr_zone"] = max(set(zones), key=zones.count)

    return targets
