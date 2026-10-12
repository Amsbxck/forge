"""Was eine Woche je Phase tragen soll — als Leitlinie, nicht als Sperre.

Im Prompt stand dafür genau **eine** Wochenvorlage, „TYPISCHE BUILD 2 WOCHE",
und die nur fürs Rad. Für Grundlage, Build 1, Build 3, Peak und Taper gab es
keine Entsprechung, und die Zahl der harten Einheiten kam aus vier Textstellen,
die sich teils widersprachen („Sessions/Woche dynamisch 2–3", „Max 2
Intensitäts-Sessions/Woche", eine HRV-Tabelle, die Vorlage selbst).

Die Werte folgen den Phasentabellen aus `researched_training_structures/`:

* Qualitätseinheiten je Woche: Grundlage 1, Aufbau 2, Peak 2, Taper 1–2
  (Casado 2022, Haugen 2022, Filipas 2022 — polarisiert bzw. pyramidal mit
  rund 80 % lockerem Umfang).
* Mindestens 48 Stunden zwischen zwei harten Einheiten (harter Tag — leichter
  Tag, Casado 2022).
* Im Taper sinkt der Umfang um 41–60 %, **Intensität und Frequenz bleiben**
  (Bosquet 2007; Metaanalyse 2023). Harte Einheiten werden kürzer, nicht
  gestrichen — das war in der alten Fassung gar nicht ausdrückbar.
* Intervallformate im Aufbau rotieren, weil kein Format nachweislich überlegen
  ist (Norte 2023).
* Beim Laufen sind VO2max-Wiederholungen ab drei Minuten kurzen vorzuziehen
  (Fleckenstein 2025: 4×3 min ergaben 328 s über 90 % VO2max gegen 201 s bei
  24×30 s). Das gilt **nicht** übertragbar fürs Rad, wo 30/15 gut abschneidet.

Geschlüsselt wird über die Phasen**familie** (`race_types.phase_family`), nicht
über „Base 2" oder „Build 3". Pläne unter sechzehn Wochen erzeugen unnumerierte
Etiketten, und jede phasengebundene Regel griff dort bisher ins Leere.
"""

from __future__ import annotations

from core.einheiten_bibliothek import (
    LAUF_MIN_WIEDERHOLUNG,
    doppel_text,
    formate_text,
)

MIN_ABSTAND_TAGE = 2  # 48 Stunden zwischen zwei harten Einheiten

# Welche Trainingstypen als Qualitätseinheit zählen, **je Phase**.
#
# Das ist nicht überall dasselbe, und genau daran ist der Zähler zuerst
# gescheitert. In der Grundlage ist der Sweet Spot die eine Qualitätseinheit —
# das Dokument nennt dort ausdrücklich "sweet spot / threshold long, or a light
# 30/15". Im Aufbau ist er die Brot-und-Butter-Einheit; zählte er dort mit,
# erschiene jede normale Aufbauwoche als Verstoß gegen das Budget.
#
# Zuerst stand hier eine phasenblinde Liste ohne `sweet_spot`. Ein echter Plan
# hat es gezeigt: Eine Grundlagenwoche mit genau einer Sweet-Spot-Einheit wurde
# als "0 Qualitätseinheiten" gemeldet, und der Prompt hätte der Folgewoche
# geraten, die fehlende Qualität nachzuholen — eine zusätzliche harte Einheit
# auf eine Woche, die richtig war. Dieselbe Fehlerklasse wie beim
# Wettkampftempo im Peak, nur eine Phase weiter vorn.
QUALITAET_STRENG = ("threshold", "vo2max", "intervals", "race_pace")
QUALITAET_MIT_SWEET_SPOT = QUALITAET_STRENG + ("sweet_spot", "tempo")

# Im Aufbau nennt die Studientabelle die Menge über **vier Wochen**, nicht über
# eine: 2 pro Woche und 5+1+1+1 ergeben beide acht harte Einheiten, aber nur
# die Blockvariante brachte VO2max +4,6 % (Rønnestad 2014, 19 trainierte
# Radfahrer; die gleichmäßige Verteilung zeigte keine signifikante Änderung).
#
# Daraus folgt, dass die Wochenzahl allein die falsche Klammer ist. Ein
# Vierwochenfenster lässt beide Verteilungen zu — und hält die Blockvariante
# zugleich ehrlich: Wer in Woche 1 fünf harte Einheiten plant, hat für die
# restlichen drei Wochen nur noch drei übrig. Die Nachführung erzwingt sich
# damit selbst, ohne dass irgendwo ein Schalter gespeichert werden müsste.
#
# Nur im Aufbau. In Taper und Wettkampfwoche wäre ein Vierwochenfenster
# sinnlos, weil es über die Phasengrenze hinausreichen würde.
BLOCK_FENSTER_WOCHEN = 4


# Je Familie: Qualitätseinheiten (von, bis), Krafteinheiten, Leitsatz, Formate.
PHASENREGELN: dict[str, dict] = {
    "Grundlage": {
        "zaehlt_als_qualitaet": QUALITAET_MIT_SWEET_SPOT,
        "doppel": ("locker_plus_qualitaet", "langer_lauf_geteilt", "schwimmen_als_zweite"),
        "qualitaet": (1, 1),
        "gym": 2,
        "leitsatz": "Umfang aufbauen. Rund 80 % des Umfangs locker.",
        "rad": ("sweet_spot", "threshold_lang"),
        "lauf": ("tempo", "schwelle_intervalle", "steigerungen", "langer_lauf"),
        "zusatz": "Steigerungen 1–2× pro Woche, sie kosten keine Erholung.",
    },
    "Base": {
        "zaehlt_als_qualitaet": QUALITAET_MIT_SWEET_SPOT,
        "doppel": ("locker_plus_qualitaet", "langer_lauf_geteilt", "schwimmen_als_zweite"),
        "qualitaet": (1, 1),
        "gym": 2,
        "leitsatz": (
            "Umfang aufbauen. Rund 80 % des Umfangs locker, pyramidale "
            "Verteilung."
        ),
        "rad": ("sweet_spot", "threshold_lang"),
        "lauf": ("tempo", "schwelle_intervalle", "steigerungen", "langer_lauf"),
        "zusatz": "Steigerungen 1–2× pro Woche, sie kosten keine Erholung.",
    },
    "Build": {
        "zaehlt_als_qualitaet": QUALITAET_STRENG,
        "doppel": ("locker_plus_qualitaet", "langer_lauf_geteilt", "doppelschwelle_leicht", "schwimmen_als_zweite"),
        "qualitaet": (2, 2),
        # Das Vierwochenfenster gilt nur hier — siehe BLOCK_FENSTER_WOCHEN.
        "block_moeglich": True,
        "gym": 1,
        "leitsatz": "Sweet Spot bleibt die Brot-und-Butter-Einheit.",
        "rad": ("sweet_spot", "threshold_lang", "4x8", "4-6x5", "30/15"),
        "lauf": ("schwelle_intervalle", "1000er", "4x4", "15/15",
                 "steigerungen", "langer_lauf"),
        "zusatz": (
            "Die Rad-Formate über die Wochen **wechseln** — kein Format ist "
            "nachweislich besser als die anderen, Abwechslung ist deshalb kein "
            "Kompromiss. Beim **Laufen** gilt das Gegenteil: dort Wiederholungen "
            f"ab {LAUF_MIN_WIEDERHOLUNG} bevorzugen, lange Intervalle schlagen "
            "die kurzen deutlich."
        ),
    },
    "Peak": {
        "zaehlt_als_qualitaet": QUALITAET_STRENG,
        "doppel": ("locker_plus_qualitaet", "doppelschwelle_leicht", "schwimmen_als_zweite"),
        "qualitaet": (2, 2),
        "gym": 1,
        "leitsatz": (
            "Mindestens eine der beiden im Wettkampftempo. Spezifisch werden, "
            "nicht härter."
        ),
        "rad": ("wettkampftempo_rad", "threshold_lang", "4x8"),
        "lauf": ("wettkampftempo_lauf", "schwelle_intervalle", "langer_lauf"),
        "zusatz": "Ab hier eine der beiden Schwimmeinheiten im Freiwasser.",
    },
    "Taper": {
        "zaehlt_als_qualitaet": QUALITAET_STRENG,
        "doppel": (),
        "qualitaet": (1, 2),
        "gym": 0,
        "leitsatz": (
            "Umfang um 40–60 % senken, **Intensität und Frequenz halten**. "
            "Harte Einheiten werden kürzer, nicht gestrichen — wer die "
            "Intensität mit herausnimmt, verliert Spritzigkeit statt sie zu "
            "sammeln."
        ),
        "rad": ("schaerfe", "wettkampftempo_rad"),
        "lauf": ("wettkampftempo_lauf", "steigerungen"),
        "zusatz": "",
    },
    "Race Week": {
        "zaehlt_als_qualitaet": QUALITAET_STRENG,
        "doppel": (),
        "qualitaet": (1, 1),
        "gym": 0,
        "leitsatz": (
            "Eine kurze Schärfeeinheit, sonst locker. Kein Umfang, keine neue "
            "Intensität, nichts Schweres im Kraftraum."
        ),
        "rad": ("schaerfe",),
        "lauf": ("steigerungen",),
        "zusatz": "Die Schärfeeinheit zwei bis drei Tage vor dem Rennen.",
    },
}

# Off Season und die Grundlagenphase bringen ihre eigenen Blöcke mit
# (`services/offseason.py`, `services/base_period.py`). Für sie gibt es hier
# bewusst keinen Eintrag — zwei Quellen für dieselbe Vorgabe wären der nächste
# Widerspruch.
OHNE_PHASENTABELLE = ("Off Season",)


def regeln_fuer(phase: str | None) -> dict | None:
    """Die Regeln zur Phase — über die Familie, nicht über die Blocknummer."""
    from core.race_types import phase_family

    familie = phase_family(phase)
    if not familie or familie in OHNE_PHASENTABELLE:
        return None
    return PHASENREGELN.get(familie)


def doppel_block(phase: str | None) -> str:
    """Die Doppeltage einer Phase — als **eigener** Abschnitt.

    Getrennt von `prompt_block`, weil die Phasenvorgabe in der Grundlage
    unterdrückt wird (dort gilt `services/base_period.py`) und die Doppeltage
    dadurch unsichtbar waren. An einem echten Plan hat sich das gezeigt: Die
    Woche hatte alle sieben Tage belegt, für die zweite Krafteinheit war kein
    Tag frei — und der Coach konnte den Doppeltag nicht einsetzen, weil er
    nichts davon wusste. Das Dokument erlaubt Schwimmen + Kraft ausdrücklich.
    """
    regeln = regeln_fuer(phase)
    if not regeln:
        return ""
    erlaubt = regeln.get("doppel", ())
    if not erlaubt:
        return (
            "## DOPPELTAGE\nIn dieser Phase keine — zwei Einheiten an einem "
            "Tag erhöhen die Tageslast, und darum geht es hier nicht mehr.\n"
        )
    return (
        "## DOPPELTAGE\n\n"
        + doppel_text(erlaubt)
        + "\n\n**Wann ein Doppeltag die Antwort ist:** wenn die Einheiten der "
        "Woche nicht auf einzelne Tage passen. Ein Ruhetag ist kein Platz, der "
        "sich für eine weitere Einheit opfern lässt — dann gehören zwei "
        "Einheiten auf einen Tag. Schwimmen ist dafür der beste Partner: Es "
        "erzeugt keine Stoßbelastung, und Schwimmen + Kraft am selben Tag "
        "beansprucht verschiedene Muskeln. Ebenso, wenn die Einzellauf-Grenze "
        "bindet: ein langer Lauf auf zwei Einheiten geteilt bleibt je Einheit "
        "darunter.\n"
    )


def prompt_block(phase: str | None, deload: bool = False) -> str:
    """Die Phasenvorgabe als Prompt-Abschnitt."""
    regeln = regeln_fuer(phase)
    if not regeln:
        return ""

    von, bis = regeln["qualitaet"]
    anzahl = f"{von}" if von == bis else f"{von}–{bis}"
    zeilen = [
        f"## WOCHENVORGABE DIESER PHASE ({phase})",
        "",
        f"- **Qualitätseinheiten: {anzahl} pro Woche.** Gezählt werden harte "
        f"Einheiten über alle Disziplinen — Rad, Lauf und ein Brick im "
        f"Wettkampftempo zählen mit, nicht nur das Rad.",
        "- Mindestens **48 Stunden** zwischen zwei harten Einheiten.",
        f"- {regeln['leitsatz']}",
    ]
    if regeln.get("block_moeglich"):
        gesamt = bis * BLOCK_FENSTER_WOCHEN
        zeilen.append(
            f"- **Oder als Block:** Maßgeblich ist in dieser Phase die Summe "
            f"über {BLOCK_FENSTER_WOCHEN} Wochen, nämlich **{gesamt}**. Du "
            f"kannst sie gleichmäßig verteilen ({bis} pro Woche) oder als "
            f"Block: eine Woche mit **5** harten Einheiten, danach drei Wochen "
            f"mit je einer. Gleiche Summe, aber der Block brachte in der Studie "
            f"VO2max +4,6 %, die gleichmäßige Verteilung keine signifikante "
            f"Änderung. **Nur bei normaler HRV**, nicht in einer Deload-Woche "
            f"und nicht in der Woche vor einem Wettkampf. In der Blockwoche "
            f"gilt die 48-Stunden-Regel nicht — danach wieder."
        )
    if regeln.get("zusatz"):
        zeilen.append(f"- {regeln['zusatz']}")
    if regeln["gym"]:
        zeilen.append(
            f"- Krafttraining **{regeln['gym']}× pro Woche** — nur als Termin "
            f"mit Dauer, ohne Übungen und Sätze."
        )
    else:
        zeilen.append("- Kein schweres Krafttraining in dieser Phase.")

    if deload:
        zeilen.append(
            "- **Deload-Woche:** Umfang 40–50 % herunter, eine Qualitätseinheit "
            "weniger als sonst, keine neue Intensität."
        )

    # Die Formate mit ihren Prozentwerten. Ohne sie wäre „rotiere zwischen
    # 30/15 und 4×8" eine Anweisung ohne Zielwert — genau das, was die
    # entfernte Zwift-Bibliothek vorher geliefert hat.
    bibliothek = formate_text(regeln.get("rad", ()), regeln.get("lauf", ()))
    if bibliothek:
        zeilen.append("\n### Erlaubte Formate in dieser Phase\n" + bibliothek)

    # Die Doppeltage stehen in `doppel_block` und werden getrennt gerendert —
    # sie müssen auch die Grundlagenphase erreichen, in der diese Vorgabe hier
    # unterdrückt wird.

    zeilen.append(
        "\nDas sind Leitlinien, keine Sperren. Wenn du begründet abweichst, "
        "schreibe den Grund in den `coaching_comment` — dann steht er beim "
        "nächsten Plan mit in der Rückschau."
    )
    return "\n".join(zeilen)
