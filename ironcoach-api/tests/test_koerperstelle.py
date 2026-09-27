"""Die Körperstelle entscheidet, welche Disziplin geschont wird.

Vorher stand das Schienbein-Protokoll fest im Prompt — für jeden Athleten,
immer, auch ohne Beschwerde. Eine Meldung trug Art, Schweregrad und Freitext,
aber nicht die Stelle; die Vorgabe konnte deshalb nur "die betroffene Struktur"
sagen und das Modell musste raten, welche Einheiten gemeint sind.

Jetzt wird die Stelle angeklickt, und daraus folgt eine konkrete Umverteilung:
Schienbein heisst Gehpausen im Lauf und lässt Rad und Schwimmen unberührt.
"""

from datetime import date

import pytest

from models import HealthEvent, User
from services.health import (
    KOERPERSTELLEN,
    koerperstelle_label,
    koerperstelle_vorgabe,
    guidance,
)


def _melde(db, stelle, severity="moderate"):
    nutzer = db.query(User).first()
    ereignis = HealthEvent(
        user_id=nutzer.id, kind="injury", severity=severity,
        body_part=stelle, start_date=date.today(),
    )
    db.add(ereignis)
    db.commit()
    return ereignis


# --- Die Tabelle -------------------------------------------------------------

def test_schienbein_trifft_nur_das_laufen():
    eintrag = KOERPERSTELLEN["schienbein"]
    assert eintrag["betroffen"] == ("run",)
    text = koerperstelle_vorgabe("schienbein")
    assert "Walk-Run" in text
    assert "Schwimmen und Radfahren sind nicht betroffen" in text


def test_schulter_trifft_nur_das_schwimmen():
    """Die Gegenprobe — sonst wäre die Stelle nur Dekoration."""
    assert KOERPERSTELLEN["schulter"]["betroffen"] == ("swim",)
    text = koerperstelle_vorgabe("schulter")
    assert "Schwimmen aussetzen" in text
    assert "Radfahren und Laufen sind nicht betroffen" in text


def test_jede_stelle_nennt_was_weiterlaeuft():
    """Ohne diesen Teil strich das Modell den ganzen Umfang statt umzulegen.

    Ausnahmen sind die Stellen, die alle drei Disziplinen betreffen — dort
    gibt es nichts, was weiterträgt.
    """
    for key, eintrag in KOERPERSTELLEN.items():
        text = koerperstelle_vorgabe(key)
        alle_betroffen = len(eintrag["betroffen"]) == 3
        assert ("nicht betroffen" in text) is not alle_betroffen, key


def test_unbekannte_stelle_gibt_nichts_zurueck():
    assert koerperstelle_vorgabe("ohr") is None
    assert koerperstelle_vorgabe(None) is None
    assert koerperstelle_label("ohr") is None


# --- Die Vorgabe an den Coach ------------------------------------------------

def test_die_stelle_steht_ganz_oben_in_der_vorgabe(db):
    """Zuerst wo, dann wie stark — die Reihenfolge ist die der Entscheidung."""
    ereignis = _melde(db, "schienbein")
    zeilen = guidance(db, db.query(User).first()).lines
    assert "Schienbein" in zeilen[0]
    assert "Walk-Run" in zeilen[0]

    db.delete(ereignis)
    db.commit()


def test_ohne_stelle_bleibt_die_allgemeine_vorgabe(db):
    """Die Angabe ist freiwillig: Wer nicht zeigen kann wo, meldet trotzdem."""
    ereignis = _melde(db, None)
    zeilen = guidance(db, db.query(User).first()).lines
    assert zeilen, "eine Verletzungsmeldung muss immer eine Vorgabe erzeugen"
    assert not any("Betroffene Stelle" in z for z in zeilen)

    db.delete(ereignis)
    db.commit()


# --- Der Weg durch die Schnittstelle ----------------------------------------

def test_meldung_speichert_die_stelle(client, db):
    antwort = client.post("/api/health/illness", json={
        "kind": "injury", "severity": "moderate",
        "body_part": "schienbein", "adjust_plan": False,
    })
    assert antwort.status_code == 200

    ereignis = db.query(HealthEvent).filter(HealthEvent.end_date.is_(None)).first()
    assert ereignis.body_part == "schienbein"

    gelistet = client.get("/api/health/events").json()
    assert gelistet[0]["body_part"] == "schienbein"
    assert gelistet[0]["body_part_label"] == "Schienbein"

    db.query(HealthEvent).delete()
    db.commit()


def test_unbekannte_stelle_wird_abgewiesen(client, db):
    """Kein stilles Verwerfen: Sonst bestätigt die Oberfläche eine Meldung,
    die im Plan nichts ändert."""
    antwort = client.post("/api/health/illness", json={
        "kind": "injury", "severity": "mild",
        "body_part": "ellenbogenspitze", "adjust_plan": False,
    })
    assert antwort.status_code == 422
    assert "Körperstelle" in antwort.json()["detail"]
    assert db.query(HealthEvent).count() == 0


def test_krankheit_traegt_keine_koerperstelle(client, db):
    """Ein Infekt hat keine Stelle — mitgeschickt wird sie verworfen."""
    antwort = client.post("/api/health/illness", json={
        "kind": "illness", "severity": "mild",
        "body_part": "schienbein", "adjust_plan": False,
    })
    assert antwort.status_code == 200
    ereignis = db.query(HealthEvent).filter(HealthEvent.end_date.is_(None)).first()
    assert ereignis.body_part is None

    db.query(HealthEvent).delete()
    db.commit()
