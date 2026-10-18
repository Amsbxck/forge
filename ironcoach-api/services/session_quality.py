"""Spitzeneinheiten und Ermüdung aus dem Soll/Ist-Vergleich erkennen.

Die Idee: Wer eine Vorgabe übertrifft, ohne die Intensitätskategorie zu
verlassen, hat Reserve — daraus lässt sich die nächste Steigerung ableiten.
Wer sie verfehlt, ist womöglich ermüdet.

Drei Dinge machen die Umsetzung anders als eine feste Prozentschwelle:

**Ein Prozentwert taugt nicht für alle Größen.** Die Zonen sind
unterschiedlich breit. Beim Rad umfasst Z4 rund 240–277 W, also etwa 15 % —
15 % über einer Sweet-Spot-Vorgabe von 232 W landen bei 267 W und bleiben in
der Kategorie. Beim Laufen umfasst Z4 nur 5:28–5:13, also gut 5 %; 15 %
schneller als die Schwellenpace wären 4:26/km und damit tief in Z5. Dieselbe
Zahl bedeutet je nach Disziplin „knapp drüber" oder „völlig anderes
Training". Gemessen wird deshalb der Abstand zum **Rand des Zielbands**, und
die Kategorie muss gehalten sein — beides zusammen, nicht das eine oder das
andere.

**Der Puls entscheidet, ob es Fortschritt war.** Schneller bei gleichem oder
niedrigerem Puls ist Formzuwachs. Schneller bei deutlich höherem Puls heißt
nur, dass jemand mehr hineingelegt hat — das ist kein Grund, künftig mehr zu
verlangen, sondern eher eines, den Tag als hart zu verbuchen. Ohne diese
Unterscheidung würde jede Einheit, in der sich jemand gequält hat, als
Fortschritt gewertet und die Progression schaukelte sich hoch.

**Eine verfehlte Vorgabe ist eine Frage, keine Diagnose.** Zu langsam kann
Ermüdung sein — oder Hitze, Wind, Profil, ein bewusst ruhiger Tag. Deshalb
wird das als Hinweis ausgegeben und zusammen mit der Reflexion gezeigt, statt
als Befund.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from sqlalchemy.orm import Session

from models import PlannedSession, TrainingSession

logger = logging.getLogger(__name__)

# Abstand zum Rand des Zielbands, ab dem es eine Aussage ist — je Größe eigen,
# weil die Zonen unterschiedlich breit sind: Beim Rad umfasst Z4 rund 15 %,
# beim Laufen nur gut 5 %. Ein gemeinsamer Wert wäre für die eine Disziplin
# belanglos und für die andere unerreichbar.
#
# Zusammen mit der Kategorieprüfung ergibt das ein Fenster, keinen offenen
# Bereich nach oben: „mindestens so weit drüber, aber noch in derselben Zone".
# Bei Vorgaben, die bereits am oberen Zonenrand liegen — ein Schwellenlauf auf
# Schwellenpace —, kann dieses Fenster leer sein. Das ist beabsichtigt: Eine
# Schwelleneinheit deutlich zu übertreffen ist kein Beleg für Reserve, sondern
# heißt, dass etwas anderes trainiert wurde als geplant.
#
# Die 5 % stammten aus der alten Zonentabelle, in der Z4 beim Laufen nur
# 5:28–5:13 umfasste, also gut fünf Prozent. Die korrigierten Bereiche sind
# breiter (Z4 Schwelle rund acht Prozent, Z5 rund neun), weshalb fünf Prozent
# dort auf Alltagsschwankung angesprungen wären.
SCHWELLE_PACE = 0.08
SCHWELLE_WATT = 0.15
# Ab wieviel Pulsabweichung „bei gleichem Puls" nicht mehr gilt. Fünf Schläge
# sind Alltagsschwankung, darüber wird es eine andere Belastung.
PULS_TOLERANZ = 5


def _zone_watt(watt: float, ftp: int | None) -> str | None:
    """Zone einer Leistung — Grenzen aus `services.zones`, nicht eigene.

    Die Einteilung stand hier ein zweites Mal. Zwei Kopien derselben Tabelle
    heißt: Wer die eine anpasst, urteilt anschließend nach anderen Grenzen,
    als die Oberfläche anzeigt — und merkt es nicht, weil beide für sich
    plausibel bleiben.
    """
    from services.zones import RAD_ZONEN

    if not ftp or not watt:
        return None
    anteil = watt / ftp
    # Über die Untergrenze der **nächsten** Zone, wie `classification`
    # („unter 0,95 ist noch Sweet Spot"). Über die eigene Obergrenze
    # gerechnet fiel 0,945 in Z4, während die Einstufung Z3 sagte.
    for (name, _unten, _oben), (_n, naechste_unten, _o) in zip(RAD_ZONEN, RAD_ZONEN[1:]):
        if anteil < naechste_unten:
            return name.split()[0]
    return RAD_ZONEN[-1][0].split()[0]


def _zone_pace(sekunden_pro_km: float, schwelle: int | None) -> str | None:
    """Zone einer Laufpace. Größere Sekundenzahl heißt langsamer."""
    from services.zones import LAUF_ZONEN

    if not schwelle or not sekunden_pro_km:
        return None
    anteil = sekunden_pro_km / schwelle
    # Von langsam nach schnell: die erste Zone, deren schnelle Grenze noch
    # nicht erreicht ist. Die Tabelle schließt jetzt lückenlos an, deshalb
    # genügt eine Grenze je Zone — vorher musste gegen die Nachbarzone
    # geprüft werden, weil zwischen den Bändern kleine Lücken lagen und ein
    # Wert darin je nach Richtung in einer anderen Zone landete.
    for name, schnell, _langsam in LAUF_ZONEN:
        if anteil > schnell:
            return name.split()[0]
    # Schneller als die schnellste Zone: dort gibt es keine Stufe mehr.
    return LAUF_ZONEN[-1][0].split()[0]


def bewerte(ist: TrainingSession, soll: PlannedSession, profile) -> dict | None:
    """Eine Einheit gegen ihre Vorgabe. None, wenn nichts Vergleichbares da ist."""
    ftp = getattr(profile, "ftp_watts", None)
    schwellenpace = getattr(profile, "threshold_pace_s_per_km", None)

    abweichung = None   # positiv = besser als vorgegeben
    groesse = None
    zone_soll = zone_ist = None

    # Der Hauptteil, wie in der Abweichungsnotiz (`classification`): Gegen
    # ein Intervallziel gehört der Schnitt der Intervalle, nicht der ganzen
    # Einheit mit Ein- und Ausfahren. Vorher urteilten beide verschieden —
    # die Notiz „im Band", das Urteil hier „verfehlt".
    haupt = None
    try:
        from services.segments import structure_from_laps, structure_from_power

        haupt = (structure_from_laps(ist) or {}).get("main")
        if not haupt and soll.target_watts_low and ist.discipline in ("bike", "brick"):
            haupt = (structure_from_power(ist, soll.target_watts_low * 0.95) or {}).get("main")
    except Exception:  # pragma: no cover - ohne Struktur gilt der Gesamtschnitt
        haupt = None

    # --- Rad: gegen das obere Ende des Wattbands ---
    if soll.target_watts_high and ((haupt or {}).get("avg_watts") or ist.normalized_power or ist.avg_watts):
        # Hauptteil zuerst, sonst normalisierte Leistung: Der reine Schnitt
        # zieht durch Rollphasen nach unten und ließe eine getroffene Einheit
        # zu niedrig aussehen.
        leistung = (haupt or {}).get("avg_watts") or ist.normalized_power or ist.avg_watts
        abweichung = (leistung - soll.target_watts_high) / soll.target_watts_high
        groesse = "watt"
        zone_soll = _zone_watt(soll.target_watts_high, ftp)
        zone_ist = _zone_watt(leistung, ftp)

    # --- Lauf: gegen das schnelle Ende des Pacebands ---
    elif soll.target_pace_low_s_per_km and ((haupt or {}).get("pace_s_per_km") or ist.avg_pace_min_km):
        ist_s = (haupt or {}).get("pace_s_per_km") or ist.avg_pace_min_km * 60
        ziel = soll.target_pace_low_s_per_km
        # Schneller heißt kleinere Sekundenzahl — Vorzeichen drehen, damit
        # „positiv = besser" über alle Größen hinweg dasselbe bedeutet.
        abweichung = (ziel - ist_s) / ziel
        groesse = "pace"
        zone_soll = _zone_pace(ziel, schwellenpace)
        zone_ist = _zone_pace(ist_s, schwellenpace)

    if abweichung is None:
        return None

    schwelle = SCHWELLE_WATT if groesse == "watt" else SCHWELLE_PACE

    # „Deutlich drüber" und „in derselben Zone geblieben" schließen sich
    # gegenseitig aus, sobald die Vorgabe am oberen Zonenrand liegt — und das
    # ist der Normalfall, weil eine Sweet-Spot-Vorgabe von 88 % FTP nur zwei
    # Prozent Luft bis zum Zonenende bei 90 % hat. Mit strenger Gleichheit war
    # keine einzige Einheit als Spitze erkennbar.
    #
    # Deshalb: höchstens eine Zone darüber. Das lässt den realistischen Fall zu
    # (Vorgabe nahe der Grenze, etwas darüber gefahren) und schließt weiter
    # aus, was ein anderes Training war — eine Z2-Ausfahrt, die in Z5 endete.
    #
    # Reicht bis Z7, weil die Laufbereiche am schnellen Ende zwei Stufen
    # dazubekommen haben (vVO2max, Steigerungen). Ein unbekanntes Etikett
    # ergab hier über `.get(…, 0)` einen **negativen** Abstand — ein
    # Steigerungslauf gegen eine Z2-Vorgabe wäre damit als Spitzeneinheit
    # gemeldet worden, also als Beleg für Reserve.
    ordnung = {f"Z{i}": i for i in range(1, 8)}
    unbekannt = [z for z in (zone_soll, zone_ist) if z and z not in ordnung]
    abstand = (
        ordnung[zone_ist] - ordnung[zone_soll]
        if zone_soll and zone_ist and not unbekannt else None
    )
    kategorie_gehalten = abstand is not None and abstand <= 1

    # Puls als Gegenprobe: Ohne ihn lässt sich Formzuwachs nicht von
    # „hat sich mehr gequält" unterscheiden.
    #
    # Für Zonen oberhalb der Schwelle gibt es keine Obergrenze im Profil, und
    # das ist richtig so: Z5 ist als „über dem Schwellenpuls" definiert, nach
    # oben offen. Eine Grenze dafür zu erfinden wäre falsch — bei kurzen
    # Intervallen hinkt der Puls ohnehin hinterher, in einem Vergleich zeigte
    # er sogar das Gegenteil des tatsächlichen Reizes.
    #
    # Nur: `grenzen.get()` lieferte dort None, `puls_hinweis` blieb None, und
    # im Urteil unten führt genau das in den letzten Zweig — jede übertroffene
    # Einheit über der Schwelle wurde damit zur Spitzeneinheit erklärt, ohne
    # dass die Gegenprobe stattgefunden hätte. Die Legende behauptete dem
    # Coach trotzdem „Puls nicht erhöht". Deshalb wird jetzt mitgeführt, ob
    # geprüft werden *konnte*.
    puls_hinweis = None
    puls_pruefbar = False
    if ist.avg_hr and soll.target_hr_zone and getattr(profile, "z2_hr_max", None):
        grenzen = {
            "Z1": profile.z1_hr_max, "Z2": profile.z2_hr_max,
            "Z3": profile.z3_hr_max, "Z4": profile.z4_hr_max,
        }
        obergrenze = grenzen.get(soll.target_hr_zone.upper())
        if obergrenze:
            puls_pruefbar = True
            puls_hinweis = ist.avg_hr - obergrenze

    urteil = "im_rahmen"
    if abweichung >= schwelle:
        if not kategorie_gehalten:
            # Deutlich drüber und die Kategorie verlassen: Das war eine andere
            # Einheit als die geplante, kein Beleg für Reserve.
            urteil = "anderes_training"
        elif puls_hinweis is not None and puls_hinweis > PULS_TOLERANZ:
            urteil = "hart_erkauft"
        else:
            urteil = "spitzeneinheit"
    elif abweichung <= -schwelle:
        urteil = "verfehlt"

    return {
        "datum": ist.session_date,
        "disziplin": ist.discipline,
        "groesse": groesse,
        "abweichung": round(abweichung * 100, 1),
        "zone_soll": zone_soll,
        "zone_ist": zone_ist,
        "puls_ueber_zone": puls_hinweis,
        # Ob die Gegenprobe möglich war. Nur bei einer Spitzeneinheit von
        # Belang, dort aber entscheidend: ohne sie ist „Puls nicht erhöht"
        # keine Feststellung, sondern eine Lücke.
        "puls_pruefbar": puls_pruefbar,
        "urteil": urteil,
        "reflexion": (ist.reflection or "").strip() or None,
    }


def analysiere(db: Session, beginn: date, heute: date | None = None,
               profile=None) -> list[dict]:
    """Alle zugeordneten Einheiten des Zeitraums bewerten."""
    heute = heute or date.today()
    if profile is None:
        return []

    paare = (
        db.query(TrainingSession, PlannedSession)
        .join(PlannedSession, TrainingSession.planned_session_id == PlannedSession.id)
        .filter(TrainingSession.session_date >= beginn,
                TrainingSession.session_date <= heute,
                TrainingSession.deleted_at.is_(None))
        .order_by(TrainingSession.session_date.asc())
        .all()
    )
    aus = []
    for ist, soll in paare:
        b = bewerte(ist, soll, profile)
        if b and b["urteil"] != "im_rahmen":
            aus.append(b)
    return aus


BESCHRIFTUNG = {
    "spitzeneinheit": "SPITZE",
    "hart_erkauft": "hart erkauft",
    "anderes_training": "Kategorie verlassen",
    "verfehlt": "verfehlt",
}


def prompt_block(db: Session, beginn: date, heute: date | None = None,
                 profile=None) -> str:
    """Die auffälligen Einheiten als Prompt-Abschnitt, mit Reflexion."""
    treffer = analysiere(db, beginn, heute, profile)
    if not treffer:
        return ""

    zeilen = []
    for t in treffer[-12:]:
        vorzeichen = "+" if t["abweichung"] > 0 else ""
        kern = (
            f"- {t['datum']} {t['disziplin']} · {BESCHRIFTUNG[t['urteil']]} · "
            f"{vorzeichen}{t['abweichung']} % {t['groesse']}"
        )
        if t["zone_soll"] and t["zone_ist"] and t["zone_soll"] != t["zone_ist"]:
            kern += f" ({t['zone_soll']} geplant, {t['zone_ist']} gefahren)"
        if t["puls_ueber_zone"] is not None and t["puls_ueber_zone"] > PULS_TOLERANZ:
            kern += f", Puls {t['puls_ueber_zone']} über der Zielzone"
        elif t["urteil"] == "spitzeneinheit" and not t.get("puls_pruefbar"):
            # Nicht verschweigen, dass die Gegenprobe ausgefallen ist. Sonst
            # liest der Coach „SPITZE" samt Legende („Puls nicht erhöht") als
            # Feststellung, wo gar nichts geprüft wurde.
            kern += ", Puls nicht beurteilbar (Zielzone über der Schwelle)"
        zeilen.append(kern)
        if t["reflexion"]:
            # Die eigene Notiz direkt darunter: Die Zahl sagt, dass etwas
            # abwich, die Reflexion sagt warum. Getrennt gelesen führt beides
            # in die Irre.
            zeilen.append(f'    Reflexion: „{t["reflexion"][:220]}“')

    spitzen = sum(1 for t in treffer if t["urteil"] == "spitzeneinheit")
    verfehlt = sum(1 for t in treffer if t["urteil"] == "verfehlt")

    return (
        "## AUFFÄLLIGE EINHEITEN (Soll gegen Ist, mit Reflexion)\n\n"
        + "\n".join(zeilen)
        + "\n\n**So ist das zu lesen:**\n"
        "- **SPITZE** = Vorgabe übertroffen und Intensitätskategorie gehalten, "
        "bei unauffälligem Puls. Das ist der Beleg für Reserve — steigere hier "
        "beim nächsten Mal die Vorgabe, statt eine Einheit zusätzlich "
        "einzuplanen. Steht in der Zeile, der Puls sei nicht beurteilbar, lag "
        "die Zielzone über der Schwelle: dann fehlt die Gegenprobe, und der "
        "Beleg ist schwächer.\n"
        "- **hart erkauft** = übertroffen, aber der Puls lag deutlich über der "
        "Zielzone. Kein Formzuwachs, sondern ein harter Tag. Vorgabe **nicht** "
        "anheben.\n"
        "- **Kategorie verlassen** = so weit drüber, dass es ein anderes "
        "Training war. Sagt nichts über die geplante Einheit aus.\n"
        "- **verfehlt** = deutlich unter der Vorgabe. Das ist eine Frage, kein "
        "Befund: Hitze, Wind, Profil oder ein bewusst ruhiger Tag erklären es "
        "genauso wie Ermüdung. Die Reflexion entscheidet — steht dort nichts, "
        "nimm es nicht als Ermüdung an.\n"
        f"\nIm Zeitraum: {spitzen} Spitzeneinheiten, {verfehlt} verfehlt.\n\n---"
    )
