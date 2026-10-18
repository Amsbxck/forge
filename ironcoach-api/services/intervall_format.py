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

Erkannt wird bewusst wenig und sicher: `4×8min`, `3×3min`, `30/15`, `40/20`,
beim Laufen zusätzlich Streckenwiederholungen (`10×1000 m`, `20×400 m`) und
`10-20-30`. Was nicht sicher erkennbar ist, bleibt `None` und wird nicht
geraten.

Beim Laufen wird **nicht** gleichwertig rotiert wie beim Rad — siehe
`lauf_rotation`.
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

# "10×1000 m", "4–5×1200m", "20 x 400 m" — Laufwiederholungen über eine
# Strecke. Bahnformate stehen fast immer so, nicht in Minuten; ohne dieses
# Muster waren 1000er, 1200er und 400er für die Rotation unsichtbar. Drei bis
# vier Ziffern und ein alleinstehendes „m", damit „5×6 min" nicht passt.
STRECKE = re.compile(r"(\d+)\s*[×x]\s*(\d{3,4})\s*m\b(?!in)", re.IGNORECASE)

# „10-20-30" (Gunnarsson & Bangsbo) — ein benanntes Format, kein Wechselpaar.
ZEHN_ZWANZIG_DREISSIG = re.compile(r"\b10\s*[-–/]\s*20\s*[-–/]\s*30\b")

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
    # Laufen: Wiederholungen über eine Strecke statt über eine Dauer.
    strecke_m: int | None = None
    # Ein benanntes Format ohne Zahlenmuster, etwa „10-20-30".
    benannt: str | None = None

    @property
    def kennung(self) -> str | None:
        """Der kurze Name des Formats: „4x8", „30/15", „10x1000m"."""
        if self.benannt:
            return self.benannt
        if self.wechsel:
            return f"{self.wechsel[0]}/{self.wechsel[1]}"
        if self.wdh and self.strecke_m:
            return f"{self.wdh}x{self.strecke_m}m"
        if self.wdh and self.dauer_s:
            if self.dauer_s % 60 == 0:
                return f"{self.wdh}x{self.dauer_s // 60}"
            return f"{self.wdh}x{self.dauer_s // 60}:{self.dauer_s % 60:02d}"
        return None

    def __bool__(self) -> bool:
        return bool(self.benannt or self.wechsel
                    or (self.wdh and (self.dauer_s or self.strecke_m)))


def _sekunden(zahl: str, rest: str | None, einheit: str) -> int:
    wert = int(zahl) * 60 + int(rest or 0) if einheit.lower() == "min" else int(zahl)
    return wert


def aus_text(text: str | None) -> Struktur:
    """Format aus einer Freitextbeschreibung — Katalog oder Vorgabe."""
    if not text:
        return Struktur()

    if ZEHN_ZWANZIG_DREISSIG.search(text):
        return Struktur(benannt="10-20-30")

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

    # Streckenwiederholungen nur, wenn keine Minutenserie erkannt wurde — eine
    # Einheit hat ein Arbeitsformat, und „6×6 min" ist kein Bahnformat.
    strecke_m = None
    if not wdh and (treffer := STRECKE.search(text)):
        anzahl, meter = int(treffer.group(1)), int(treffer.group(2))
        # 200 m bis 3 km, 2 bis 30 Wiederholungen — sonst ist es eher eine
        # Jahreszahl oder eine Gesamtstrecke.
        if 2 <= anzahl <= 30 and 200 <= meter <= 3000:
            wdh, strecke_m = anzahl, meter

    p_min = p_max = None
    if treffer := PROZENT.search(text):
        p_min = int(treffer.group(1))
        p_max = int(treffer.group(2) or treffer.group(1))

    return Struktur(wdh=wdh, dauer_s=dauer_s, prozent_min=p_min,
                    prozent_max=p_max, wechsel=wechsel, strecke_m=strecke_m)


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
        typ = (e.training_type or "").lower()
        if typ not in ROTIERBAR:
            continue
        kennung = aus_vorgabe(e.details, ftp).kennung
        # Ein Tempolauf ist durchgehend und hat kein Wiederholungsmuster. Er
        # gehört beim Laufen aber in den Schwellentopf — ohne eigene Kennung
        # fiele er aus der Reihe, und die Rotation schlüge ihn nie vor.
        if not kennung and typ == "tempo" and e.discipline == "run":
            kennung = "Tempo"
        if kennung:
            aus.append((e.planned_date, e.discipline, e.training_type, kennung))
    return aus


# ── Laufrotation ────────────────────────────────────────────────────────────
#
# Beim Rad ist kein Format nachweislich besser (Norte 2023), also wird
# gleichwertig gewechselt. Beim Laufen gilt das nur zur Hälfte, und genau das
# muss die Rotation abbilden:
#
#   * **Schwelle** — 5×6 min, 6×1600 m, 10×1000 m, 20–25×400 m und der
#     Tempolauf sind gleichwertige Wege zur selben Schwellenarbeit (Casado
#     2022/2023). Hier wird frei gewechselt wie beim Rad.
#   * **VO2max** — Wiederholungen ab drei Minuten sind der Standard: 4×3 min
#     ergaben 328 s über 90 % VO2max, 24×30 s nur 201 s (Fleckenstein 2025).
#     Gewechselt wird zwischen den **langen** Formaten. 15/15 und 30/30 stehen
#     im Dokument ausdrücklich „as variety" — also gelegentlich, nie zweimal
#     hintereinander, und im Peak gar nicht.
#
# Die Schlüssel sind kanonisch: „10x1000m" und „6x1000m" sind beide 1000er.
# Welcher Topf gilt, entscheidet der Trainingstyp der Einheit, nicht die
# Strecke — 10×1000 m bei 95–102 % ist Schwelle, 5×1000 m bei 107–110 % VO2max.

LAUF_SCHWELLE = {
    "6-min": "5×6 min",
    "1600er": "6×1600 m",
    "1000er": "10×1000 m",
    "400er": "20–25×400 m",
    "Tempo": "Tempolauf 20–40 min",
}
LAUF_VO2_LANG = {
    "1000er": "5–6×1000 m",
    "1200er": "4–5×1200 m",
    "4-min": "4×4 min",
}
LAUF_VO2_KURZ = {
    "15/15": "15/15",
    "30/30": "30/30",
}
LAUF_ZEITSPAREND = {"10-20-30": "10-20-30"}

TOPF_JE_TYP = {
    "threshold": "schwelle",
    "tempo": "schwelle",
    "vo2max": "vo2max",
    "intervals": "vo2max",
}


def lauf_kanon(kennung: str | None) -> str | None:
    """„10x1000m" → „1000er", „5x6" → „6-min", „15/15" bleibt. Sonst None."""
    if not kennung:
        return None
    if kennung in ("15/15", "30/30", "10-20-30", "Tempo"):
        return kennung
    if treffer := re.fullmatch(r"\d+x(\d+)m", kennung):
        return f"{treffer.group(1)}er"
    if treffer := re.fullmatch(r"\d+x(\d+)(?::\d+)?", kennung):
        return f"{treffer.group(1)}-min"
    return None


def _bezeichnung(schluessel: str, topf: str) -> str:
    """Der lesbare Name — **je Topf**. „1000er" heißt in der Schwelle
    „10×1000 m", bei VO2max „5–6×1000 m": dieselbe Strecke, eine andere
    Einheit. Ohne den Topf bekäme die VO2max-Einheit die Schwellenvorgabe."""
    if topf == "schwelle":
        return LAUF_SCHWELLE.get(schluessel, schluessel)
    for tabelle in (LAUF_VO2_LANG, LAUF_VO2_KURZ, LAUF_ZEITSPAREND):
        if schluessel in tabelle:
            return tabelle[schluessel]
    return schluessel


def _aufzaehlung(namen: list[str]) -> str:
    if not namen:
        return ""
    if len(namen) == 1:
        return namen[0]
    return ", ".join(namen[:-1]) + " oder " + namen[-1]


def lauf_rotation(formate: list[tuple], phase: str | None) -> list[str]:
    """Rotationszeilen fürs Laufen, getrennt nach Schwelle und VO2max.

    `formate` sind die Einträge aus `letzte_formate`, ältester zuerst.
    """
    from core.race_types import phase_family

    familie = phase_family(phase)
    schwelle, vo2 = [], []
    for _tag, disziplin, typ, kennung in formate:
        if disziplin != "run":
            continue
        topf = TOPF_JE_TYP.get((typ or "").lower())
        schluessel = lauf_kanon(kennung)
        if not topf or not schluessel:
            continue
        (schwelle if topf == "schwelle" else vo2).append(schluessel)

    zeilen = []
    if schwelle:
        zeilen.append(
            "- Zuletzt vorgegeben (Lauf, Schwelle): "
            + " · ".join(_bezeichnung(s, "schwelle") for s in schwelle)
        )
        letztes = schwelle[-1]
        # Die letzten **zwei** auslassen: Der Topf hat fünf gleichwertige
        # Formate, und nur das letzte auszuschließen hieße, dass zwei sich
        # abwechseln, während die übrigen drei nie drankommen.
        zuletzt = set(schwelle[-2:])
        andere = [n for k, n in LAUF_SCHWELLE.items() if k not in zuletzt]
        zeilen.append(
            f"- **Schwelle beim Laufen: diese Woche ein anderes Format als "
            f"{_bezeichnung(letztes, 'schwelle')}** — etwa "
            f"{_aufzaehlung(andere[:3])}. Alle bei 95–102 % mit 30–60 s Pause, "
            f"der Tempolauf durchgehend bei 92–97 %. Die Formate sind "
            f"gleichwertig (Casado 2022/2023), der Wechsel ist also wie beim Rad "
            f"kein Kompromiss."
        )

    if vo2:
        zeilen.append(
            "- Zuletzt vorgegeben (Lauf, VO2max): "
            + " · ".join(_bezeichnung(s, "vo2max") for s in vo2)
        )
        letztes = vo2[-1]
        lang = [n for k, n in LAUF_VO2_LANG.items() if k != letztes]
        beleg = (
            "Wiederholungen ab drei Minuten sind beim Laufen der Standard, "
            "anders als beim Rad: 4×3 min ergaben 328 s über 90 % VO2max, "
            "24×30 s nur 201 s (Fleckenstein 2025)."
        )
        if letztes in LAUF_VO2_KURZ:
            # War die letzte selbst kurz, gibt es kein „anderes langes" — es
            # geht einfach zurück zu den langen.
            zeilen.append(
                f"- **VO2max beim Laufen: diesmal wieder ein langes Format** "
                f"nach {letztes} — {_aufzaehlung(lang)}. {beleg}"
            )
        else:
            zeilen.append(
                f"- **VO2max beim Laufen: ein anderes langes Format als "
                f"{_bezeichnung(letztes, 'vo2max')}** — {_aufzaehlung(lang)}. "
                f"{beleg}"
            )
        # Kurz war die vorletzte, nicht die letzte — dann eigens sagen, dass
        # noch keine neue kurze dran ist. War es die letzte, steht das schon.
        kurz_zuletzt = [s for s in vo2[-2:] if s in LAUF_VO2_KURZ]
        if familie == "Peak":
            zeilen.append(
                "- Im Peak **keine** kurzen Formate (15/15, 30/30). Ist die "
                "Woche eng, ist 10-20-30 die zeitsparende Option (Gunnarsson & "
                "Bangsbo 2012: Fortschritt bei 54 % weniger Umfang)."
            )
        elif kurz_zuletzt:
            if letztes not in LAUF_VO2_KURZ:
                zeilen.append(
                    f"- Die vorletzte VO2max-Einheit war kurz "
                    f"({', '.join(kurz_zuletzt)}) — **noch keine neue kurze.** "
                    f"Die kurzen sind Abwechslung, kein Standard."
                )
        else:
            zeilen.append(
                "- Als gelegentliche Abwechslung ist auch 15/15 oder 30/30 "
                "möglich, mit **kleinem** Tempounterschied zwischen schnell und "
                "locker (Billat 2001: kleiner Unterschied 14 min bei VO2max, "
                "extremes Format nur 7 min). Nicht zweimal hintereinander."
            )
    return zeilen


# Was fürs Rad je Phase im Wechsel steht — dieselben Formate wie
# `core.phasenregeln.PHASENREGELN[...]["rad"]`, in der Schreibweise, die der
# Athlet im Plan liest.
RAD_ROTATION = {
    "Build": ("30/15", "4×8", "4–6×5"),
    "Peak": ("4×8", "lange Schwelle (etwa 2×20)", "Wettkampftempo am Stück"),
}


def _rad_familie(kennung: str | None) -> str | None:
    """„5x5", „6x5", „4x5" gehören zum selben Format „4–6×5"."""
    if not kennung:
        return None
    if re.fullmatch(r"[456]x5", kennung):
        return "4–6×5"
    if kennung == "4x8":
        return "4×8"
    return kennung


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
        # Laufen bekommt eigene Zeilen, getrennt nach Schwelle und VO2max —
        # eine gemeinsame Reihe würde 10×1000 m Schwelle und 5×1000 m VO2max
        # als dasselbe lesen.
        if disziplin == "run":
            continue
        zeilen.append(f"- Zuletzt vorgegeben ({disziplin}): {' · '.join(reihe)}")

    rad = je_disziplin.get("bike", [])
    if rad:
        letztes = rad[-1]
        # Nur Formate, die die Phase erlaubt (`PHASENREGELN[...]["rad"]`).
        # Vorher stand hier eine feste Liste, und im Peak kam „30/15 oder 5x5"
        # — zwei Formate, die der Peak gar nicht vorsieht. „5x5" hieß zudem
        # anders als der Bibliothekseintrag „4–6×5".
        familie = _rad_familie(letztes)
        andere = [f for f in RAD_ROTATION.get(phase_family(phase), ()) if f != familie]
        if not andere:
            andere = list(RAD_ROTATION.get(phase_family(phase), ()))
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
    zeilen.extend(lauf_rotation(formate, phase))
    if len(zeilen) == 1:
        return ""
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
