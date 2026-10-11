"""Intervallformate mit konkreten Zielwerten — der Ersatz für die Zwift-Bibliothek.

Die Zwift-Bibliothek stand als Pflichttext im Prompt und lieferte dort das, was
der Coach wirklich braucht: Struktur **und** Prozentwerte. Sie ist aus dem
Prompt entfernt, weil sie ihn zu einem Viertel belegte und jeder Woche ein
VO2max-Menü anbot, auch dem Taper. Entfernt man sie aber ohne Ersatz, bleibt
eine Lücke: „rotiere zwischen 30/15 und 4×8" sagt nicht, bei wie viel Prozent.

Diese Formate kommen aus den Studientabellen in
`researched_training_structures/`, nicht aus einer Workout-Sammlung. Sie sind
damit begründbar und tragen ihren Beleg mit.

Die Prozentwerte beim Laufen sind Anteile der **Schwellengeschwindigkeit** und
decken sich mit `services/zones.py LAUF_TEMPO_ZONEN`; beim Rad sind es Anteile
der FTP und decken sich mit `RAD_ZONEN`. Beide Tabellen sind die Quelle für die
Zonennamen, die hier in Klammern stehen.
"""

from __future__ import annotations

# Pausen zwischen Intervallen sind aktiv und locker, wenn nichts anderes
# dasteht (bike-training.md: Z1, ≤ 55 % FTP).
PAUSE_STANDARD_RAD = "aktiv in Z1, höchstens 55 % FTP"

RAD_FORMATE: dict[str, dict] = {
    "sweet_spot": {
        "struktur": "3×12–20 min oder 2×20 min",
        "ziel": "88–94 % FTP (oberes Z3)",
        "pause": "3–5 min",
        "beleg": "nur indirekt belegt — bewährt, aber nicht direkt untersucht",
    },
    "threshold_lang": {
        "struktur": "4×12–16 min",
        "ziel": "92–100 % FTP (Z3/Z4)",
        "pause": "3–4 min",
        "beleg": "Seiler 2013",
    },
    "4x8": {
        "struktur": "4×8 min, gleichmäßig und maximal durchhaltbar",
        "ziel": "100–108 % FTP (Z4/Z5)",
        "pause": "2–3 min",
        "beleg": "Seiler 2013 — VO2peak +11,4 %, besser als 4×4 und 4×16",
    },
    "4-6x5": {
        "struktur": "4–6×4–5 min",
        "ziel": "108–120 % FTP (Z5)",
        "pause": "2:30 min",
        "beleg": "Rønnestad 2015/2020",
    },
    "30/15": {
        "struktur": "3 Sätze × 13 × (30 s hart / 15 s locker)",
        "ziel": "hart 120–150 % FTP (maximal durchhaltbar), locker ~50 %",
        "pause": "3 min zwischen den Sätzen",
        "beleg": "Rønnestad 2015/2020/2021 — VO2max +8,7 % gegen +2,6 % bei 4×5",
    },
    "wettkampftempo_rad": {
        "struktur": "lange Blöcke im Renntempo, gleichmäßige Leistung",
        "ziel": "aus der Zielzeit; bei 70.3 etwa 80–85 % FTP (Z3)",
        "pause": "—",
        "beleg": "Renntempo-Studie 2024 (Sprintdistanz)",
    },
    "schaerfe": {
        "struktur": "3–4 × 2 min, volle Pause",
        "ziel": "Renntempo bis etwa 95 % FTP (oberes Z3 bis unteres Z4)",
        "pause": "volle Erholung",
        "beleg": "Bosquet 2007, Taper-Metaanalyse 2023",
    },
}

LAUF_FORMATE: dict[str, dict] = {
    "steigerungen": {
        "struktur": "6–10 × 15–20 s, volle Erholung, am Ende eines lockeren Laufs",
        "ziel": "120–130 % der Schwellengeschwindigkeit (Z7), locker gelaufen",
        "pause": "volle Erholung",
        "beleg": "Haugen 2022 — Schnelligkeit in kleinen Dosen",
    },
    "tempo": {
        "struktur": "20–40 min durchgehend",
        "ziel": "92–97 % (Z3)",
        "pause": "—",
        "beleg": "Casado 2022",
    },
    "schwelle_intervalle": {
        "struktur": "5×6 min, 6×1600 m, 10×1000 m oder 20–25×400 m",
        "ziel": "95–102 % (Z4)",
        "pause": "30–60 s",
        "beleg": "Casado 2022/2023",
    },
    "1000er": {
        "struktur": "5–6×1000 m",
        "ziel": "107–110 % (Z5)",
        "pause": "2–3 min Trabpause",
        "beleg": "Seiler & Sjursen 2002, Fleckenstein 2025",
    },
    "4x4": {
        "struktur": "4×4 min",
        "ziel": "106–112 % (Z5) — etwa 95 % von vVO2max, nicht vVO2max selbst",
        "pause": "3 min Trabpause",
        "beleg": "Helgerud 2007 (+8,1 % VO2max), Fleckenstein 2025",
    },
    "15/15": {
        "struktur": "2–3 × 10 min aus 15 s schnell / 15 s locker",
        "ziel": (
            "schnell 112–118 % (Z6), locker 85–90 % — der Unterschied zwischen "
            "beiden muss **klein** bleiben"
        ),
        "pause": "volle Erholung zwischen den Serien",
        "beleg": (
            "Billat 2001 — kleiner Unterschied ergab 14 min bei VO2max, ein "
            "extremes 110-%-Format nur 7 min. Nur als Abwechslung: bei Läufern "
            "schlagen Wiederholungen ab drei Minuten die kurzen deutlich"
        ),
    },
    "langer_lauf": {
        "struktur": "75–150 min, höchstens 10 % über dem längsten Lauf der letzten 30 Tage",
        "ziel": "70–80 % (Z2 locker)",
        "pause": "—",
        "beleg": "Haugen 2022, Frandsen 2025",
    },
    "wettkampftempo_lauf": {
        "struktur": "etwa 3×3 km im Wettkampftempo, ausgeruht",
        "ziel": "aus der Zielzeit — ohne Zielzeit keine Pacevorgabe, nach Zone laufen",
        "pause": "—",
        "beleg": "Haugen 2022",
    },
}

# Beim Laufen schlagen lange Wiederholungen die kurzen deutlich: 4×3 min
# ergaben 328 s über 90 % VO2max gegen 201 s bei 24×30 s (Fleckenstein 2025).
# Beim Rad gilt das Gegenteil — dort schneidet 30/15 sehr gut ab.
#
# `15/15` steht trotzdem in der Liste, aber als Abwechslung und mit der
# Bedingung aus Billat 2001: der Unterschied zwischen schnell und locker muss
# klein bleiben. Ohne dieses Format hätte Z6 keine einzige Einheit — eine Zone,
# die nichts vorschreibt, wäre eine Zone zu viel.
LAUF_MIN_WIEDERHOLUNG = "drei Minuten"


def formate_text(rad: tuple[str, ...], lauf: tuple[str, ...]) -> str:
    """Die erlaubten Formate einer Phase als Tabelle."""
    zeilen = []
    if rad:
        zeilen.append("**Rad:**")
        zeilen.append("| Format | Struktur | Ziel | Pause |")
        zeilen.append("|---|---|---|---|")
        for schluessel in rad:
            f = RAD_FORMATE[schluessel]
            zeilen.append(
                f"| {schluessel} | {f['struktur']} | {f['ziel']} | {f['pause']} |"
            )
        zeilen.append(f"\nPausen ohne eigene Angabe: {PAUSE_STANDARD_RAD}.")
    if lauf:
        if zeilen:
            zeilen.append("")
        zeilen.append("**Lauf:**")
        zeilen.append("| Format | Struktur | Ziel | Pause |")
        zeilen.append("|---|---|---|---|")
        for schluessel in lauf:
            f = LAUF_FORMATE[schluessel]
            zeilen.append(
                f"| {schluessel} | {f['struktur']} | {f['ziel']} | {f['pause']} |"
            )
    return "\n".join(zeilen)
