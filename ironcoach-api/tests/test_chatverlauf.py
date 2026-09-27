"""Der Chatverlauf muss einen Seitenwechsel überleben — und fremder bleibt fremd.

Der Verlauf lebt nicht im Browser: `/chat` lädt ihn beim Öffnen aus
`/api/chat/history`. Bleibt die Antwort leer, sieht es aus, als sei das
Gespräch verloren. Weil der Mandantenfilter nur auf SELECT wirkt und der
Verlauf ohne eigene `user_id`-Bedingung gelesen wird, hängt hier beides
zusammen: Ist der Filter zu streng, verschwindet der eigene Verlauf; ist er
zu lasch, steht dort der fremde.
"""

from datetime import datetime, timedelta

from models import ChatMessage, User


def _schreib(db, user_id, rolle, text, versatz_min=0):
    db.add(ChatMessage(
        user_id=user_id, role=rolle, content=text, context_week=12,
        created_at=datetime.utcnow() - timedelta(minutes=versatz_min),
    ))


def test_verlauf_kommt_zurueck(client, db):
    """Der Kern: Nach dem Seitenwechsel wird der Verlauf neu geladen."""
    eigner = db.query(User).first()
    _schreib(db, eigner.id, "user", "wie lange soll der lange Lauf werden?", 4)
    _schreib(db, eigner.id, "assistant", "90 Minuten, Walk-Run.", 3)
    db.commit()

    antwort = client.get("/api/chat/history")
    assert antwort.status_code == 200
    inhalte = [m["content"] for m in antwort.json()]
    assert "wie lange soll der lange Lauf werden?" in inhalte
    assert "90 Minuten, Walk-Run." in inhalte

    db.query(ChatMessage).delete()
    db.commit()


def test_verlauf_ist_chronologisch(client, db):
    """Älteste zuerst — sonst liest man das Gespräch von hinten."""
    eigner = db.query(User).first()
    _schreib(db, eigner.id, "user", "erste", 10)
    _schreib(db, eigner.id, "assistant", "zweite", 9)
    _schreib(db, eigner.id, "user", "dritte", 8)
    db.commit()

    inhalte = [m["content"] for m in client.get("/api/chat/history").json()]
    assert inhalte == ["erste", "zweite", "dritte"]

    db.query(ChatMessage).delete()
    db.commit()


def test_fremder_verlauf_bleibt_fremd(client, db):
    """Die andere Hälfte: Der Filter darf nichts durchlassen, was nicht gehört.

    Ohne ihn stünde im Chat des einen Athleten die Unterhaltung des anderen —
    inklusive dessen Beschwerden und Werten.
    """
    eigner = db.query(User).first()
    fremd = User(email="fremd@example.invalid", name="Fremd")
    db.add(fremd)
    db.commit()

    _schreib(db, eigner.id, "user", "meine Frage", 2)
    _schreib(db, fremd.id, "user", "fremde Frage", 1)
    db.commit()

    inhalte = [m["content"] for m in client.get("/api/chat/history").json()]
    assert "meine Frage" in inhalte
    assert "fremde Frage" not in inhalte

    db.query(ChatMessage).delete()
    db.query(User).filter(User.id == fremd.id).delete()
    db.commit()
