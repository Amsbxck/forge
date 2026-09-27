"""Endgültig gelöscht heißt auch im Vault gelöscht.

Der Anlass ist eine Doppelaufnahme: Wer eine Ausfahrt gleichzeitig mit Garmin
und Wahoo aufzeichnet — etwa um die FTP- und VO2max-Schätzung der Uhr zu
füttern —, bekommt zwei Strava-Aktivitäten mit verschiedenen IDs. Die
Entdopplung läuft über `strava_activity_id` und greift dort nicht. Löschte man
die überzählige Einheit in FORGE, blieb ihre Notiz im Vault stehen: Der Vault
behielt genau den Fehler, den man gerade beseitigt hatte.
"""

from datetime import date, datetime

import pytest

from models import TrainingSession, User
from services.obsidian import notes
from services.obsidian.sync import delete_session_note


class VaultDoppel:
    def __init__(self, dateien=None, kaputt=False):
        self.dateien = dict(dateien or {})
        self.geloescht = []
        self.enabled = True
        self.kaputt = kaputt

    def get_note(self, pfad):
        if self.kaputt:
            from services.obsidian.client import ObsidianUnavailable
            raise ObsidianUnavailable("Vault nicht erreichbar")
        return self.dateien.get(pfad)

    def delete_note(self, pfad):
        if pfad not in self.dateien:
            return False
        del self.dateien[pfad]
        self.geloescht.append(pfad)
        return True


GEPFLEGT = f"---\ndate: 2026-09-20\n---\n\n{notes.MARKER_START}\nx\n{notes.MARKER_END}\n"
PFAD = "Training/bike/Offseason 2026/base/2026-09-20--999.md"


def _einheit(db, pfad=PFAD):
    nutzer = db.query(User).first()
    s = TrainingSession(
        user_id=nutzer.id, session_date=date(2026, 9, 20), discipline="bike",
        duration_min=90, week_number=1, obsidian_path=pfad,
        obsidian_synced_at=datetime.utcnow(),
    )
    db.add(s)
    db.commit()
    return s


def test_note_wird_entfernt(db):
    s = _einheit(db)
    vault = VaultDoppel({PFAD: GEPFLEGT})

    ergebnis = delete_session_note(db, s, client=vault)

    assert ergebnis["status"] == "gelöscht"
    assert vault.geloescht == [PFAD]
    assert PFAD not in vault.dateien

    db.delete(s)
    db.commit()


def test_eigene_note_bleibt_stehen(db):
    """Ohne Managed Block gehört die Notiz dem Athleten.

    Dasselbe Prinzip wie im Sync: Wer den Block entfernt hat, hat die Notiz
    übernommen — dann ist sie mehr als die Abschrift einer Datenbankzeile.
    """
    s = _einheit(db)
    eigene = "---\ndate: 2026-09-20\n---\n\nAlles selbst geschrieben.\n"
    vault = VaultDoppel({PFAD: eigene})

    ergebnis = delete_session_note(db, s, client=vault)

    assert ergebnis["status"] == "behalten_eigene_note"
    assert vault.dateien[PFAD] == eigene
    assert vault.geloescht == []

    db.delete(s)
    db.commit()


def test_ohne_pfad_passiert_nichts(db):
    """Eine nie synchronisierte Einheit hat keine Notiz."""
    s = _einheit(db, pfad=None)
    vault = VaultDoppel()

    assert delete_session_note(db, s, client=vault)["status"] == "keine_note"
    assert vault.geloescht == []

    db.delete(s)
    db.commit()


def test_unerreichbarer_vault_wird_gemeldet_nicht_verschwiegen(db):
    """Eine stille Zusage wäre schlimmer als der Hinweis.

    Niemand sucht später eine Notiz, von der er glaubt, sie sei gelöscht.
    """
    s = _einheit(db)
    ergebnis = delete_session_note(db, s, client=VaultDoppel(kaputt=True))

    assert ergebnis["status"] == "unavailable"
    assert ergebnis["path"] == PFAD

    db.delete(s)
    db.commit()


def test_endpunkt_loescht_einheit_und_meldet_den_vault(client, db, monkeypatch):
    s = _einheit(db)
    sid = s.id
    vault = VaultDoppel({PFAD: GEPFLEGT})
    monkeypatch.setattr(
        "services.obsidian.client.client_for_profile", lambda profil: vault
    )

    antwort = client.delete(f"/api/history/sessions/{sid}/hard")
    assert antwort.status_code == 200
    daten = antwort.json()
    assert daten["vault"]["status"] == "gelöscht"
    assert "Notiz im Vault entfernt" in daten["message"]

    # Die Zeile ist weg, und die Notiz war vor dem Löschen noch lesbar —
    # `obsidian_path` hängt nur an der Zeile.
    assert db.query(TrainingSession).filter(TrainingSession.id == sid).first() is None
    assert vault.geloescht == [PFAD]


def test_weiches_loeschen_laesst_die_note_in_ruhe(client, db):
    """Wiederherstellbar heißt wiederherstellbar — auch im Vault.

    Die Notiz kann Freitext enthalten, der nur dort steht; ihn beim ersten
    Schritt zu entfernen wäre nicht umkehrbar.
    """
    s = _einheit(db)
    sid = s.id

    antwort = client.delete(f"/api/history/sessions/{sid}")
    assert antwort.status_code == 200
    assert "vault" not in antwort.json()

    db.expire_all()
    wieder = db.query(TrainingSession).filter(TrainingSession.id == sid).first()
    assert wieder.deleted_at is not None
    assert wieder.obsidian_path == PFAD

    db.delete(wieder)
    db.commit()
