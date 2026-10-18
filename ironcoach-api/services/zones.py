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

# Laufen: Anteile der **Schwellengeschwindigkeit**, nicht der Pace.
#
# Die Literatur beschreibt Laufbereiche durchgehend als Prozent der
# Schwellengeschwindigkeit; hier standen stattdessen Pace-Multiplikatoren, und
# der Unterschied war nicht kosmetisch:
#
# * „Z5 VO2max" lag bei 101–106 % der Schwellengeschwindigkeit — das ist
#   5-Kilometer-Tempo. Echtes vVO2max liegt bei 112–118 %. Bei einem
#   Schwellenpace von 4:46/km hieß die Vorgabe 4:29–4:43/km, während vVO2max
#   bei 4:02–4:15/km liegt: Eine als „VO2max" geplante Einheit konnte den
#   Reiz, nach dem sie benannt war, strukturell nicht erreichen.
# * „Z2 Grundlage" spannte über 78–88 % und damit über zwei verschiedene
#   Absichten — locker (70–80 %) und ruhig zügig (82–90 %). Ein als locker
#   gemeinter Dauerlauf am schnellen Ende erhöhte die Wochenintensität
#   unbemerkt.
#
# Deshalb jetzt in Prozent, mit zwei zusätzlichen Bereichen am schnellen Ende.
# Die Bänder schließen lückenlos aneinander an: die Zuordnung in
# `session_quality` greift über die Obergrenze, eine Lücke würde einen Wert
# stillschweigend in das nächsthöhere Band schieben.
# Z1 bis Z4 behalten ihre Bedeutung: „Z4 Schwelle" heißt weiter Schwelle, und
# jede historische Notiz bleibt lesbar. Neu sind Z5 bis Z7 am schnellen Ende
# und die Teilung von Z2, deren beide Hälften bewusst dieselbe Nummer tragen —
# es sind zwei Absichten innerhalb eines Bereichs, keine neue Stufe.
LAUF_TEMPO_ZONEN = [
    # (Name, langsame Grenze in % Schwellengeschwindigkeit, schnelle Grenze)
    ("Z1 Regeneration", None, 70),
    ("Z2 locker", 70, 81),
    ("Z2 ruhig zügig", 81, 90),
    ("Z3 Tempo", 90, 95),
    ("Z4 Schwelle", 95, 103),
    ("Z5 5K / Tempo hart", 103, 112),
    ("Z6 vVO2max", 112, 120),
    ("Z7 Steigerungen", 120, 130),
]

# Dieselben Bereiche als Pace-Multiplikatoren, wie der restliche Code sie
# erwartet: erst die schnelle, dann die langsame Grenze, `None` heißt offen
# nach langsam. Abgeleitet, nicht zweimal gepflegt — zwei Quellen für eine
# Grenze waren der Ursprung des Rad-Befunds.
#
# Weniger Prozent Geschwindigkeit heißt mehr Sekunden je Kilometer, die
# Grenzen tauschen beim Umrechnen also die Seite.
LAUF_ZONEN = [
    (
        name,
        round(100 / schnell, 4),                        # schnelle Grenze
        round(100 / langsam, 4) if langsam else None,   # langsame Grenze
    )
    for name, langsam, schnell in LAUF_TEMPO_ZONEN
]

# Schwimmen: Aufschlag auf die CSS-Pace in Sekunden je 100 m.
SCHWIMM_ZONEN = [
    ("Z1 Technik/locker", 10, None),
    ("Z2 Grundlage", 6, 10),
    ("Z3 Tempo", 3, 5),
    ("Z4 Schwelle (CSS)", 0, 2),
    # Nach schnell offen: Hier stand −4 als Grenze, und für alles darüber
    # gab es keine Zone. `None` heißt offen, wie bei Z1 nach langsam.
    ("Z5 schneller als CSS", None, -1),
]

# Rad: Anteile der FTP, nach Coggan.
#
# Die Grenze Z3/Z4 lag bei 0,90/0,91 und damit vier Prozentpunkte zu tief: Bei
# Coggan reicht das Tempoband bis 87 %, darüber liegt bis 94 % der Sweet Spot
# und erst ab 95 % die Schwelle. Eine Ausfahrt bei 92 % stand deshalb als
# „Z4 Schwelle" in der Anzeige, während `services/classification.py` sie
# gleichzeitig `sweet_spot` nannte — zwei Antworten im selben Prompt.
#
# Sweet Spot ist bewusst **keine** sechste Zone: Er ist das obere Ende von Z3
# und wird im Text benannt. Eine zusätzliche Zone hätte die Zonenordnung in
# `session_quality`, `ZONE_TO_INTENSITY` und das Schema mitverschoben, ohne
# dass dafür ein Reiz dazukäme.
RAD_ZONEN = [
    ("Z1 Regeneration", 0.00, 0.54),
    ("Z2 Grundlage", 0.55, 0.75),
    ("Z3 Tempo", 0.76, 0.94),
    ("Z4 Schwelle", 0.95, 1.05),
    ("Z5 VO2max", 1.06, 1.20),
    # Über 120 % gab es keine Zone, obwohl die 30/15-Intervalle im
    # Raddokument bei 121–150 % liegen — `session_quality` steckte sie in Z5.
    ("Z6 anaerob", 1.21, 1.50),
]

# Das obere Ende von Z3, benannt statt als eigene Zone geführt.
RAD_SWEET_SPOT = (0.88, 0.94)


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
                f"langsamer als {mmss(c + unten)}/100m" if oben is None
                else f"schneller als {mmss(c + oben)}/100m" if unten is None
                else f"{mmss(c + unten)}–{mmss(c + oben)}/100m"
            ),
        })
    return aus


def _rad_watt(ftp: int) -> list[tuple[str, str]]:
    """Wattbereiche je Zone — lückenlos und an den Einstufungsgrenzen.

    Vorher schnitt `int()` beide Enden ab: Bei 250 W FTP stand ≤135, 137–187,
    190–235, 237–262 — 136, 188, 189 und 236 W gehörten zu keiner Zone. Jetzt
    beginnt jede Zone bei der ersten ganzen Wattzahl, die die Einstufung
    (`classification`: „unter der nächsten Grenze") ihr zuordnet, und endet
    eins darunter, wo die nächste beginnt.
    """
    import math

    aus = []
    for i, (name, unten, oben) in enumerate(RAD_ZONEN):
        von = math.ceil(ftp * unten)
        bis = (math.ceil(ftp * RAD_ZONEN[i + 1][1]) - 1
               if i + 1 < len(RAD_ZONEN) else math.floor(ftp * oben))
        wert = f"≤ {bis}" if unten == 0 else f"{von}–{bis}"
        aus.append((name, wert))
    return aus


def rad_zonen(ftp: int | None) -> list[dict]:
    if not ftp:
        return []
    return [
        {"name": name, "text": f"{wert.replace('≤ ', '0–')} W"}
        for name, wert in _rad_watt(ftp)
    ]


def _zeile(name: str, wert: str) -> dict:
    """„Z2 ruhig zügig" → Kennung, Zonennummer, Name, Wert ohne Einheit.

    Die Zonennummer steht getrennt, weil zwei Zeilen dieselbe tragen können:
    Z2 ist beim Laufen in „locker" und „ruhig zügig" geteilt — zwei Absichten
    in einem Bereich, beide grün. Nach der Zeilenposition gefärbt, bekäme die
    zweite Hälfte die Farbe von Z3.
    """
    kennung, _, rest = name.partition(" ")
    return {
        "label": kennung,
        "zone": int(kennung[1:]) if kennung[1:].isdigit() else None,
        "name": rest,
        "wert": wert,
    }


def anzeige(profile) -> dict:
    """Die Bereiche für die Profilseite — aus **derselben** Tabelle wie der Prompt.

    Vorher hielt das Frontend eine eigene Kopie der Grenzen und rechnete selbst.
    Die Kopie ist abgedriftet, genau wie ihr eigener Kommentar es vorhersagte:
    Beim Rad stand dort noch die Z3/Z4-Grenze bei 90/91 %, die hier längst auf
    Coggans 94/95 % korrigiert ist, und beim Laufen fehlten Z6 und Z7 sowie die
    Teilung von Z2. Der Athlet sah also andere Bereiche als die, nach denen der
    Coach plant.

    Die Einheit steht nicht im Wert: Sie steht einmal im Spaltenkopf.
    """
    pace = getattr(profile, "threshold_pace_s_per_km", None)
    ftp = getattr(profile, "ftp_watts", None)
    css = getattr(profile, "css_pace_s_per_100m", None)

    lauf = []
    if pace:
        for z in lauf_zonen(pace):
            wert = f"> {z['bis']}" if z["von"] is None else f"{z['von']}–{z['bis']}"
            lauf.append(_zeile(z["name"], wert))

    rad = []
    if ftp:
        for name, wert in _rad_watt(ftp):
            rad.append(_zeile(name, wert))

    schwimm = []
    if css:
        for name, unten, oben in SCHWIMM_ZONEN:
            wert = (
                f"> {mmss(css + unten)}" if oben is None
                else f"< {mmss(css + oben)}" if unten is None
                else f"{mmss(css + unten)}–{mmss(css + oben)}"
            )
            schwimm.append(_zeile(name, wert))

    ss_von, ss_bis = RAD_SWEET_SPOT
    return {
        "lauf": lauf,
        "rad": rad,
        "schwimm": schwimm,
        "sweet_spot": (
            f"{int(ftp * ss_von)}–{int(ftp * ss_bis)}" if ftp else None
        ),
    }


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
        # Sweet Spot ist das obere Ende von Z3 und keine eigene Zone. Ohne
        # diese Zeile wüsste der Coach nicht, wo er liegt — und „Sweet Spot"
        # steht in den Phasenregeln als Brot-und-Butter-Einheit.
        ss_von, ss_bis = RAD_SWEET_SPOT
        teile.append(
            f"### Rad — FTP {ftp} W\n| Bereich | Leistung |\n|---|---|\n" + zeilen
            + f"\n\nSweet Spot ist das obere Ende von Z3: "
              f"{int(ftp * ss_von)}–{int(ftp * ss_bis)} W "
              f"({ss_von * 100:.0f}–{ss_bis * 100:.0f} % FTP)."
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

