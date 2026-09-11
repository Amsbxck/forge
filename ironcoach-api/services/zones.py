"""Trainingsbereiche aus den gemessenen Schwellenwerten.

Bisher kannte der Plan nur zwei Größen: FTP fürs Rad und Herzfrequenzzonen
aus dem Maximalpuls. Schwellenpace, Schwellenpuls und CSS standen im Profil,
erreichten den Coach aber nie — wer seinen Schwellenlauf gemessen hatte,
bekam trotzdem Läufe ohne Paceangabe.

Warum Pace und Watt neben dem Puls stehen müssen: Die Herzfrequenz beschreibt
die Belastung mit Verzögerung und wandert mit Hitze, Schlaf, Koffein und
Höhe. Für ein kurzes Intervall ist sie unbrauchbar — sie steigt erst, wenn
das Intervall vorbei ist. Pace und Watt sind das, was der Athlet steuert;
der Puls ist, was der Körper daraus macht. Beides gehört in die Vorgabe.

Die Prozentsätze folgen der üblichen Einteilung nach Friel (Laufen, Schwimmen)
und Coggan (Rad). Sie sind Konvention, keine Messung — deshalb stehen sie hier
sichtbar und nicht verteilt im Prompt-Text.
"""

from __future__ import annotations

# Laufen: Anteile der Schwellenpace. Größer heißt langsamer, weil in
# Sekunden je Kilometer gerechnet wird — Z2 ist also 14–29 % langsamer.
LAUF_ZONEN = [
    ("Z1 Regeneration", 1.29, None),
    ("Z2 Grundlage", 1.14, 1.29),
    ("Z3 Tempo", 1.06, 1.13),
    ("Z4 Schwelle", 1.00, 1.05),
    ("Z5 VO2max", 0.94, 0.99),
]

# Schwimmen: Aufschlag auf die CSS-Pace in Sekunden je 100 m.
SCHWIMM_ZONEN = [
    ("Z1 Technik/locker", 10, None),
    ("Z2 Grundlage", 6, 10),
    ("Z3 Tempo", 3, 5),
    ("Z4 Schwelle (CSS)", 0, 2),
    ("Z5 schneller als CSS", -4, -1),
]

# Rad: Anteile der FTP.
RAD_ZONEN = [
    ("Z1 Regeneration", 0.00, 0.55),
    ("Z2 Grundlage", 0.56, 0.75),
    ("Z3 Tempo", 0.76, 0.90),
    ("Z4 Schwelle", 0.91, 1.05),
    ("Z5 VO2max", 1.06, 1.20),
]


def mmss(sekunden: float) -> str:
    """Sekunden als m:ss — die Schreibweise, in der Pace gelesen wird."""
    s = int(round(sekunden))
    return f"{s // 60}:{s % 60:02d}"


def lauf_zonen(schwellenpace_s_per_km: int | None) -> list[dict]:
    if not schwellenpace_s_per_km:
        return []
    t = schwellenpace_s_per_km
    aus = []
    for name, unten, oben in LAUF_ZONEN:
        # `oben is None` heißt offen nach langsam — eine Untergrenze für
        # Regeneration wäre erfunden.
        aus.append({
            "name": name,
            "von": mmss(t * (oben or unten)) if oben else None,
            "bis": mmss(t * unten),
            "text": (
                f"langsamer als {mmss(t * unten)}/km"
                if oben is None
                else f"{mmss(t * oben)}–{mmss(t * unten)}/km"
            ),
        })
    return aus


def schwimm_zonen(css_s_per_100m: float | None) -> list[dict]:
    if not css_s_per_100m:
        return []
    c = css_s_per_100m
    aus = []
    for name, unten, oben in SCHWIMM_ZONEN:
        aus.append({
            "name": name,
            "text": (
                f"langsamer als {mmss(c + unten)}/100m"
                if oben is None
                else f"{mmss(c + unten)}–{mmss(c + oben)}/100m"
            ),
        })
    return aus


def rad_zonen(ftp: int | None) -> list[dict]:
    if not ftp:
        return []
    return [
        {"name": name, "text": f"{int(ftp * unten)}–{int(ftp * oben)} W"}
        for name, unten, oben in RAD_ZONEN
    ]


# Nach ungefähr drei Monaten sind die Bereiche überholt — bei einem Athleten
# im Aufbau nach unten, nach einer Pause nach oben. Beides ist schädlich: Zu
# niedrige Schwellen bremsen die Entwicklung, zu hohe erzeugen Einheiten, die
# nicht durchzuhalten sind, und werden als eigenes Versagen gelesen.
TAGE_BIS_NEUTEST = 90


def _alter_hinweis(profile) -> str:
    from datetime import datetime

    stand = getattr(profile, "zones_updated_at", None)
    if stand is None:
        return (
            "**Stand der Werte unbekannt** — es ist nicht hinterlegt, wann "
            "zuletzt gemessen wurde. Schlage eine Testwoche vor, wenn die "
            "Phase es zulässt.\n\n"
        )
    tage = (datetime.utcnow() - stand).days
    if tage < TAGE_BIS_NEUTEST:
        return f"Zuletzt gemessen vor {tage} Tagen.\n\n"
    return (
        f"**Die Werte sind {tage} Tage alt.** Plane eine Testwoche ein, sobald "
        "die Phase es zulässt — nicht in einer Deload- oder Wettkampfwoche. "
        "Bis dahin gelten die bisherigen Bereiche weiter; rechne sie nicht "
        "eigenmächtig hoch.\n\n"
    )


def prompt_block(profile, sport: str | None = None) -> str:
    """Die Bereiche als Prompt-Abschnitt.

    Leer, solange nichts gemessen ist: Erfundene Zonen wären schlimmer als
    keine, weil der Plan dann Vorgaben trägt, die nach Messung aussehen.

    `sport` blendet aus, was für das Saisonziel keine Rolle spielt. Ein
    Läufer, dem Wattbereiche und CSS-Pace im Prompt stehen, bekommt sonst
    Vorgaben für Disziplinen, die in seinem Plan gar nicht vorkommen — und
    das Modell greift sie erfahrungsgemäß auf.
    """
    from core.race_types import relevante_werte

    zaehlt = relevante_werte(sport)
    teile = []

    pace = getattr(profile, "threshold_pace_s_per_km", None)
    if pace and "run_threshold" in zaehlt:
        zeilen = "\n".join(f"| {z['name']} | {z['text']} |" for z in lauf_zonen(pace))
        teile.append(
            f"### Laufen — Schwellenpace {mmss(pace)}/km"
            + (f", Schwellenpuls {profile.threshold_hr} bpm" if getattr(profile, "threshold_hr", None) else "")
            + "\n| Bereich | Pace |\n|---|---|\n" + zeilen
        )

    css = getattr(profile, "css_pace_s_per_100m", None)
    if css and "css" in zaehlt:
        zeilen = "\n".join(f"| {z['name']} | {z['text']} |" for z in schwimm_zonen(css))
        teile.append(
            f"### Schwimmen — CSS {mmss(css)}/100m"
            "\n| Bereich | Pace |\n|---|---|\n" + zeilen
        )

    ftp = getattr(profile, "ftp_watts", None)
    if ftp and "ftp" in zaehlt:
        zeilen = "\n".join(f"| {z['name']} | {z['text']} |" for z in rad_zonen(ftp))
        teile.append(
            f"### Rad — FTP {ftp} W\n| Bereich | Leistung |\n|---|---|\n" + zeilen
        )

    if not teile:
        return ""

    return (
        "## TRAININGSBEREICHE (aus gemessenen Schwellenwerten)\n\n"
        + _alter_hinweis(profile)
        + "\n\n".join(teile)
        + "\n\nGib bei jeder Einheit die Vorgabe in Pace oder Watt an, nicht nur "
        "als Herzfrequenzzone. Der Puls hinkt der Belastung nach und schwankt mit "
        "Hitze, Schlaf und Erholung — für Intervalle unter etwa fünf Minuten ist "
        "er als Steuergröße unbrauchbar. Nenne den Puls als Kontrolle für lange "
        "Grundlageneinheiten, die Pace oder Watt als Vorgabe für alles Intensive."
        + "\n\n---"
    )

