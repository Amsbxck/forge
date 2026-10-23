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
            # 20 statt 16. Bei 16 Wochen fiel der Taper mit der Wettkampfwoche
            # zusammen — es gab keine einzige eigene Taperwoche. Gängig sind
            # 16–24 Wochen; 20 liegt in der Mitte und ergibt Base 1–7,
            # Build 8–14, Peak 15–18, Taper 19, Wettkampf 20.
            #
            # Gilt für neue Ziele. Bestehende tragen ihre Dauer im Ziel
            # (`plan_weeks`); welche davon umgestellt werden, entscheidet
            # Migration 038.
            "weeks": 20,
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

# Mindestens zwei: Die letzte Woche des Plans ist die Wettkampfwoche
# (`phase_for_week`), und die zählt in den Taperwochen mit. Mit nur einer
# reservierten Woche fiel der Taper bei Sprint, 10 km, Halbmarathon,
# Zeitfahren und Radmarathon vollständig mit dem Rennen zusammen — diese
# Pläne hatten keine einzige eigene Taperwoche, und ein 10-Wochen-Plan nur
# eine Peak-Woche. Ab 18 Wochen ergibt der Anteil ohnehin zwei oder mehr;
# dort ändert sich nichts.
MIN_TAPER_WEEKS = 2
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


def _taper_wochen(total_weeks: int) -> int:
    """Länge des Tapers samt Wettkampfwoche: 9 %, begrenzt auf 2–3 Wochen."""
    return min(MAX_TAPER_WEEKS, max(MIN_TAPER_WEEKS, round(total_weeks * 0.09)))


def _deload_raster(total_weeks: int) -> list[int]:
    """Die Deload-Wochen — eine Quelle für `deload_wochen` und die Grenzen.

    Jede vierte Woche, gezählt ab Woche 1, bis vor die Woche vor dem Taper.
    Hängt nur an der Taperlänge, nicht an den Grenzen zwischen Base, Build und
    Peak — sonst wären die Grenzen, die hier einrasten, von sich selbst
    abhängig.
    """
    taper_start = total_weeks - _taper_wochen(total_weeks) + 1
    return list(range(DELOAD_RHYTHMUS, taper_start - 1, DELOAD_RHYTHMUS))


def _anteilsgrenzen(total_weeks: int) -> list[tuple[str, int, int]]:
    """Base, Build, Peak und Taper nach `PHASE_SHARES`, ohne Rücksicht auf
    den Deload-Takt. Ausgangspunkt für `phase_boundaries`, und für Pläne,
    die für den Takt zu kurz sind, das Ergebnis."""
    taper = _taper_wochen(total_weeks)
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


# Ein Peak unter vier Wochen ist dünn: Er ist der rennspezifische Teil. Liegt
# die Grenze Build→Peak genau zwischen zwei Deload-Wochen, gewinnt deshalb die
# Seite, die dem Peak mindestens so viel lässt (Amir, 23.10.2026).
MIN_PEAK_IM_TAKT = 4


def phase_boundaries(total_weeks: int) -> list[tuple[str, int, int]]:
    """Phasen als (Name, erste Woche, letzte Woche).

    Der Taper wird zuerst reserviert und auf 2–3 Wochen begrenzt — die
    Wettkampfwoche eingeschlossen, also mindestens eine eigene Taperwoche
    davor. Bei einem 10-Wochen-Plan wären 9 % rechnerisch unter einer Woche,
    bei einem sehr langen Aufbau würden sonst vier Wochen Formerhalt entstehen.

    **Die Grenzen Base→Build und Build→Peak liegen auf einer Deload-Woche.**
    Vorher folgten sie nur den Anteilen, und der durchgehend gezählte Deload
    fiel, wohin er fiel: Bei 20 Wochen begann Build in W8 mit einem Deload,
    Build 3 in W12 ebenso, und die Blöcke waren 2, 2, 3, 2, 2, 3 Wochen lang.
    Jetzt endet jede Phase mit ihrem Deload, die nächste beginnt mit
    Belastung — drei Wochen Belastung, eine Entlastung, durch den ganzen Plan.

    Jede Grenze rastet auf die nächstgelegene Deload-Woche ein. Bei
    Gleichstand: Base→Build die spätere (Base zuerst), Build→Peak die, die
    dem Peak mindestens `MIN_PEAK_IM_TAKT` Wochen lässt, sonst die spätere.
    Taper und Deload-Wochen ändert das nicht — sie hängen nur an der
    Taperlänge (`_deload_raster`).

    Pläne mit weniger als zwei Deload-Wochen vor dem Taper (unter 11 Wochen)
    behalten die Anteile: Für drei Phasen auf dem Raster reicht es dort nicht.
    """
    total_weeks = max(4, int(total_weeks))
    alt = _anteilsgrenzen(total_weeks)
    raster = _deload_raster(total_weeks)
    if len(raster) < 2:
        return alt

    ende = {name: bis for name, _von, bis in alt}
    taper_start = next(von for name, von, _bis in alt if name == "Taper")
    letzte_vor_taper = taper_start - 1

    def einrasten(ziel: int, kandidaten: list[int], vorrang) -> int:
        return min(kandidaten, key=lambda d: (abs(d - ziel), vorrang(d)))

    # Base braucht danach noch Platz für Build: nicht die letzte Deload-Woche.
    base_ende = einrasten(ende["Base"], raster[:-1], lambda d: -d)
    build_ende = einrasten(
        ende["Build"], [d for d in raster if d > base_ende],
        lambda d: (letzte_vor_taper - d < MIN_PEAK_IM_TAKT, -d),
    )
    return [
        ("Base", 1, base_ende),
        ("Build", base_ende + 1, build_ende),
        ("Peak", build_ende + 1, letzte_vor_taper),
        ("Taper", taper_start, total_weeks),
    ]


def _bloecke(von: int, bis: int, deloads: set[int]) -> list[tuple[int, int]]:
    """Eine Phase in Blöcke, jeder endet mit seinem Deload.

    Was nach dem letzten Deload der Phase übrig bleibt (nur im Peak: vor dem
    Taper liegt nie ein Deload), ist ein eigener kurzer Block — bei 33
    Wochen Peak 1 = W25–28, Peak 2 = W29–30. Eine einzelne Restwoche hängt
    am Block davor; ein Block aus einer Woche wäre kein Block.
    """
    bloecke: list[tuple[int, int]] = []
    anfang = von
    for w in range(von, bis + 1):
        if w in deloads:
            bloecke.append((anfang, w))
            anfang = w + 1
    if anfang <= bis:
        if bis - anfang + 1 == 1 and bloecke:
            bloecke[-1] = (bloecke[-1][0], bis)
        else:
            bloecke.append((anfang, bis))
    return bloecke


def phase_for_week(week: int, total_weeks: int = 33) -> str:
    """Phase einer Woche. Nach dem Renntag beginnt die Nachbereitung.

    Der Renntag liegt in der letzten Woche (siehe `plan_start_for`), die
    damit die Wettkampfwoche ist. Alles danach ist Off Season — vorher stand
    hier `total_weeks + 1`, wodurch nach dem Rennen noch eine Wettkampfwoche
    erschien, die es nicht gibt.
    """
    if week < 1:
        # Vor Woche 1 hat die Vorbereitung noch nicht begonnen. Ohne diesen
        # Zweig fiel eine negative Woche durch die Phasengrenzen hindurch und
        # landete am Ende auf "Base" — als liefe der Aufbau bereits.
        return "Grundlage"
    if week > total_weeks:
        return "Off Season"
    if week == total_weeks:
        return "Race Week"
    raster = _deload_raster(total_weeks)
    for name, start, end in phase_boundaries(total_weeks):
        if start <= week <= end:
            # Blöcke (Base 1, Base 2, …) im 3+1-Takt, damit die Progression im
            # Prompt sichtbar bleibt. Vorher wurde jede Phase ab sechs Wochen
            # gedrittelt, unabhängig vom Deload — Blöcke von 2 bis 5 Wochen,
            # die mitten in der Belastung oder mit einem Deload begannen.
            # Pläne unter dem Takt (siehe `phase_boundaries`) nummerieren nicht.
            if name == "Taper" or len(raster) < 2:
                return name
            bloecke = _bloecke(start, end, set(raster))
            if len(bloecke) < 2:
                return name
            nummer = next(i for i, (a, b) in enumerate(bloecke, 1) if a <= week <= b)
            return f"{name} {nummer}"
    return "Base"


# Phasennamen, die nicht von `phase_for_week` stammen und deshalb durch die
# Nummernlogik unten unverändert hindurchfallen. Beide werden gespeichert und
# später wieder gelesen:
#
#   * `base_period.phase_label` schreibt „Vorbereitung auf den Aufbau" in die
#     Wochen vor dem Aufbau. `PHASENREGELN` hat dafür keinen Schlüssel, also
#     gab `regeln_fuer` dort `None` — keine Qualitätsvorgabe, keine
#     Kraftvorgabe, keine Doppeltage. Gemessen an echten Plänen: genau die
#     Wochen, in denen die Kraftvorgabe reihenweise verfehlt wurde.
#   * „Off Season · Formerhalt" sollte über `OHNE_PHASENTABELLE` ausgeschlossen
#     werden, traf dort aber nie zu, weil die Familie den Zusatz behielt. Das
#     Ergebnis war zufällig richtig (`PHASENREGELN.get` gab ebenfalls `None`) —
#     jetzt ist es die Regel, die es sein sollte.
#
# Das Frontend macht dieselbe Abbildung in `src/utils/phasen.js`.
PHASEN_ALIAS = {
    "Vorbereitung auf den Aufbau": "Grundlage",
    "Off Season · Formerhalt": "Off Season",
    # Der zweite Off-Season-Name (`offseason.phase_label`). Er fehlte, und
    # `vorrang_block` gab für „Übergang" eine Rangordnung aus, für
    # „Formerhalt" keine — derselbe Zustand, zwei Vorgaben.
    "Off Season · Übergang": "Off Season",
}


def phase_family(phase: str | None) -> str:
    """Der Phasenname ohne Blocknummer: „Base 2" → „Base".

    Phasengebundene Regeln waren gegen die Etiketten eines 33-Wochen-Plans
    geschrieben („ab Build 2", „Base 1-2: 2×/Woche"). `phase_for_week`
    unterteilt aber nur Phasen ab sechs Wochen — ein 12-Wochen-Plan erzeugt
    „Base", „Build", „Peak" ohne Nummer, und keine dieser Regeln griff dort.
    Über die Familie greifen sie in jeder Planlänge.

    Zusätzlich die gespeicherten Namen aus `PHASEN_ALIAS` — siehe dort, warum.
    """
    roh = (phase or "").strip()
    if not roh:
        return ""
    if roh in PHASEN_ALIAS:
        return PHASEN_ALIAS[roh]
    teile = roh.rsplit(" ", 1)
    if len(teile) == 2 and teile[1].isdigit():
        return teile[0]
    return roh


# Belastungsmuster: drei Belastungswochen, eine Entlastungswoche. Das
# Raddokument nennt „2–3 load weeks + 1 recovery week" (Stöggl 2014: 2 + 1);
# drei Wochen sind die obere Grenze davon. Die Phasengrenzen rasten auf diese
# Deload-Wochen ein (`phase_boundaries`), die Blöcke (Base 1, Base 2 …) enden
# mit ihnen (`phase_for_week`) — vorher passte das nur bei 33 Wochen zufällig.
DELOAD_RHYTHMUS = 4


def deload_wochen(total_weeks: int = 33) -> set[int]:
    """Alle Entlastungswochen eines Plans: jede vierte Woche bis zum Taper.

    Durchgehend gezählt über Base, Build und Peak, nicht je Phase neu. Je
    Phase neu begonnen lagen bei 18 Wochen fünf Belastungswochen am Stück
    (W5–W9), weil die Phasen damals sechs Wochen lang waren. Heute rasten
    die Phasengrenzen auf diese Wochen ein (`phase_boundaries`). Vorher gab es überhaupt
    nur das Phasenende — bei 33 Wochen W12 und W24, mit elf Belastungswochen
    dazwischen.

    Keine Entlastung im Taper (der selbst Entlastung ist), in der
    Wettkampfwoche und in der Woche direkt vor dem Taper: zwei Entlastungen
    hintereinander nähmen dem Peak die Schärfe.
    """
    return set(_deload_raster(max(4, int(total_weeks))))


def is_deload(week: int, total_weeks: int = 33) -> bool:
    """Ist diese Woche eine Entlastungswoche? Siehe `deload_wochen`.

    Eine Quelle für Vorgabe und Saisonübersicht im Prompt. Früher entschied
    dort `week % 4 == 0`, was bei 12, 16, 24 und 40 Wochen die
    **Wettkampfwoche** zur Entlastungswoche machte; danach nur noch das
    Phasenende, was in Base und Build bis zu elf Belastungswochen ohne
    Erholung ergab.
    """
    if week < 1 or week > total_weeks:
        return False
    return week in deload_wochen(total_weeks)


def plan_start_for(race_date: date, total_weeks: int) -> date:
    """Beginn der Vorbereitung, sodass der Renntag in die letzte Woche fällt.

    Gerechnet wird ab dem **Montag der Rennwoche**, nicht ab dem Renntag.
    Vorher stand hier `race_date - timedelta(weeks=total_weeks - 1)`, was den
    Wochentag des Rennens übernahm: Ein Rennen am Sonntag ergab einen
    Planstart am Sonntag und damit Planwochen von Sonntag bis Samstag. Die
    Wochenansicht sucht ihren Plan aber über den Montag der Kalenderwoche und
    fand deshalb keinen einzigen.

    So fällt der Renntag weiterhin in die letzte Woche — bei einem Rennen am
    Sonntag sogar auf deren letzten Tag.
    """
    from core.wochen import montag_von

    return montag_von(race_date) - timedelta(weeks=total_weeks - 1)


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
    Wettkampfwoche, `race_week` in der Kalenderwoche des Rennens bis
    einschließlich Renntag, danach `off_season`.
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
    # Die **Kalenderwoche** des Rennens, wie in den Phasen (`phase_for_week`:
    # letzte Planwoche = Wettkampfwoche). Vorher „weniger als sieben Tage":
    # Bei einem Rennen am Samstag galt schon der Sonntag davor als
    # Wettkampfwoche, während Plan und Phase noch die Woche davor zeigten.
    from core.wochen import montag_von

    if montag_von(today) == montag_von(race_date):
        return "race_week"
    # Der Aufbau hat noch nicht begonnen. Eine Woche Vorlauf wird nicht
    # gesondert behandelt — wer wenige Tage zu früh dran ist, steigt einfach
    # in Woche 1 ein.
    if plan_start is not None and today < plan_start:
        return "base_period"
    return "preparation"
