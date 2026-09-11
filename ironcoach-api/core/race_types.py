"""Wettkampfarten, Distanzen und die daraus folgende Planstruktur.

Bisher war die Saison fest verdrahtet: 33 Wochen, Phasengrenzen bei 4, 8, 12,
16, 20, 24, 28, 30 — passend für genau einen 70.3-Aufbau. Ein Halbmarathon
braucht 14 Wochen ohne Schwimmen und Rad, ein Sprint-Triathlon 12 mit allen
drei Disziplinen. Deshalb kommt beides aus dem gewählten Ziel statt aus
Konstanten im Code.
"""

from datetime import date, timedelta

SPORTS = ["triathlon", "running", "cycling"]

SPORT_LABEL = {
    "triathlon": "Triathlon",
    "running": "Laufen",
    "cycling": "Radsport",
}

# Distanzen je Sportart. `weeks` ist die empfohlene Aufbaudauer für jemanden
# mit Grundlage — Einsteiger bekommen über die Benchmark-Woche zusätzlich
# eine Testphase vorgeschaltet.
RACE_TYPES: dict[str, dict[str, dict]] = {
    "triathlon": {
        "sprint": {
            "label": "Sprint",
            "swim_km": 0.75, "bike_km": 20, "run_km": 5,
            "weeks": 12,
        },
        "olympic": {
            "label": "Olympisch",
            "swim_km": 1.5, "bike_km": 40, "run_km": 10,
            "weeks": 16,
        },
        "middle": {
            "label": "Mitteldistanz (70.3)",
            "swim_km": 1.9, "bike_km": 90, "run_km": 21.1,
            # 33 statt der sonst üblichen 24: bewusste Entscheidung aus der
            # eigenen Saison — die längere Grundlagenphase hat sich bewährt.
            # Wer weniger Zeit hat, kann die Dauer am Ziel überschreiben.
            "weeks": 33,
        },
        "full": {
            "label": "Langdistanz (140.6)",
            "swim_km": 3.8, "bike_km": 180, "run_km": 42.2,
            # 40 statt 33, seit die Mitteldistanz auf 33 steht: Sonst hätten
            # beide Distanzen dieselbe Vorbereitungsdauer, obwohl die
            # Langdistanz deutlich mehr Grundlage und lange Einheiten braucht.
            "weeks": 40,
        },
    },
    "running": {
        "10k": {"label": "10 km", "run_km": 10, "weeks": 10},
        "half_marathon": {"label": "Halbmarathon", "run_km": 21.1, "weeks": 14},
        "marathon": {"label": "Marathon", "run_km": 42.2, "weeks": 18},
    },
    # Drei Formate, die sich in der Vorbereitung deutlich unterscheiden: ein
    # Zeitfahren lebt von der Schwellenleistung, ein Radmarathon vom Umfang,
    # eine Langstrecke zusätzlich von Verpflegung und Sitzzeit. Die
    # Bezeichnungen lassen sich ändern, ohne dass sonst etwas davon abhängt.
    "cycling": {
        "time_trial": {"label": "Zeitfahren (~40 km)", "bike_km": 40, "weeks": 12},
        "gran_fondo": {"label": "Radmarathon (~120 km)", "bike_km": 120, "weeks": 16},
        "ultra": {"label": "Langstrecke (200 km+)", "bike_km": 200, "weeks": 24},
    },
}

# Welche Disziplinen ein Plan überhaupt enthalten darf.
SPORT_DISCIPLINES = {
    "triathlon": ["swim", "bike", "run", "brick", "gym", "rest"],
    "running": ["run", "gym", "bike", "rest"],  # Rad als Ausgleich, ohne Wettkampfbezug
    "cycling": ["bike", "gym", "rest"],         # Laufen belastet die Beine anders
}

# Welche gemessenen Werte für eine Sportart überhaupt eine Rolle spielen.
# Ein Läufer braucht keine FTP und keine CSS-Pace — sie im Profil als leere
# Kacheln zu zeigen oder in der Testwoche abzufragen, verlangt Arbeit für
# Zahlen, die nie in eine Vorgabe eingehen.
SPORT_WERTE = {
    "triathlon": ["ftp", "run_threshold", "css"],
    "running": ["run_threshold"],
    "cycling": ["ftp"],
}


def relevante_werte(sport: str | None) -> list[str]:
    """Die Schwellenwerte, die für diese Sportart zählen."""
    return SPORT_WERTE.get((sport or "").lower(), SPORT_WERTE["triathlon"])

# Anteil der Gesamtdauer je Phase. Entspricht ungefähr dem bisherigen
# 33-Wochen-Aufbau (Base 12, Build 12, Peak 6, Taper 3 Wochen).
PHASE_SHARES = [
    ("Base", 0.36),
    ("Build", 0.36),
    ("Peak", 0.19),
    ("Taper", 0.09),
]

MIN_TAPER_WEEKS = 1
MAX_TAPER_WEEKS = 3


def race_config(sport: str | None, distance: str | None) -> dict | None:
    return RACE_TYPES.get((sport or "").lower(), {}).get((distance or "").lower())


def race_label(sport: str | None, distance: str | None) -> str:
    config = race_config(sport, distance)
    sport_name = SPORT_LABEL.get((sport or "").lower(), sport or "?")
    return f"{sport_name} {config['label']}" if config else sport_name


def default_weeks(sport: str | None, distance: str | None) -> int:
    config = race_config(sport, distance)
    return config["weeks"] if config else 33


def disciplines_for(sport: str | None) -> list[str]:
    return SPORT_DISCIPLINES.get((sport or "").lower(), SPORT_DISCIPLINES["triathlon"])


def phase_boundaries(total_weeks: int) -> list[tuple[str, int, int]]:
    """Phasen als (Name, erste Woche, letzte Woche).

    Der Taper wird zuerst reserviert und auf 1–3 Wochen begrenzt: bei einem
    10-Wochen-Plan wären 9 % rechnerisch unter einer Woche, bei einem sehr
    langen Aufbau würden sonst vier Wochen Formerhalt entstehen.
    """
    total_weeks = max(4, int(total_weeks))
    taper = min(MAX_TAPER_WEEKS, max(MIN_TAPER_WEEKS, round(total_weeks * 0.09)))
    remaining = total_weeks - taper

    shares = [(name, share) for name, share in PHASE_SHARES if name != "Taper"]
    total_share = sum(share for _, share in shares)

    lengths: list[tuple[str, int]] = []
    assigned = 0
    for index, (name, share) in enumerate(shares):
        if index == len(shares) - 1:
            length = remaining - assigned  # Rundungsrest in die letzte Phase
        else:
            length = max(1, round(remaining * share / total_share))
        lengths.append((name, length))
        assigned += length
    lengths.append(("Taper", taper))

    boundaries = []
    week = 1
    for name, length in lengths:
        if length <= 0:
            continue
        boundaries.append((name, week, week + length - 1))
        week += length
    return boundaries


def phase_for_week(week: int, total_weeks: int = 33) -> str:
    """Phase einer Woche. Nach dem Renntag beginnt die Nachbereitung.

    Der Renntag liegt in der letzten Woche (siehe `plan_start_for`), die
    damit die Wettkampfwoche ist. Alles danach ist Off Season — vorher stand
    hier `total_weeks + 1`, wodurch nach dem Rennen noch eine Wettkampfwoche
    erschien, die es nicht gibt.
    """
    if week > total_weeks:
        return "Off Season"
    if week == total_weeks:
        return "Race Week"
    for name, start, end in phase_boundaries(total_weeks):
        if start <= week <= end:
            # Innerhalb langer Phasen weiter unterteilen (Base 1, Base 2, …),
            # damit die Progression im Prompt sichtbar bleibt.
            length = end - start + 1
            if length >= 6:
                block = (week - start) // max(1, round(length / 3)) + 1
                return f"{name} {min(block, 3)}"
            return name
    return "Base"


def plan_start_for(race_date: date, total_weeks: int) -> date:
    """Beginn der Vorbereitung, sodass der Renntag in die letzte Woche fällt."""
    return race_date - timedelta(weeks=total_weeks - 1)


def weeks_until_race(race_date: date, today: date | None = None) -> int:
    today = today or date.today()
    return max(0, (race_date - today).days // 7)


def season_state(
    race_date: date | None,
    today: date | None = None,
    plan_start: date | None = None,
) -> str:
    """Wo in der Saison der Athlet steht.

    `base_period` vor Beginn der Vorbereitung, `preparation` bis zur
    Wettkampfwoche, `race_week` in der Woche des Rennens, danach `off_season`.
    Ohne Ziel gilt Vorbereitung, weil die Wochenzählung dann am Profil hängt
    und kein Renntag existiert.

    Warum `base_period` ein eigener Zustand ist: Wer sich elf Monate vorher
    für eine Mitteldistanz anmeldet, hat sechs Monate vor sich, für die es
    keine spezifische Vorbereitung gibt — 24 Wochen sind die Aufbaudauer,
    nicht die Wartezeit. Ohne diesen Zustand galt die Zeit als „Woche 1 von
    24", und der Wochenkalender zeigte Tage aus dem nächsten Frühjahr als
    aktuelle Woche. Das war keine Lücke, sondern eine falsche Auskunft.
    """
    if race_date is None:
        return "preparation"
    today = today or date.today()
    if today > race_date:
        return "off_season"
    if (race_date - today).days < 7:
        return "race_week"
    # Der Aufbau hat noch nicht begonnen. Eine Woche Vorlauf wird nicht
    # gesondert behandelt — wer wenige Tage zu früh dran ist, steigt einfach
    # in Woche 1 ein.
    if plan_start is not None and today < plan_start:
        return "base_period"
    return "preparation"
