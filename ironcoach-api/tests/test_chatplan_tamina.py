"""Ein im Chat vereinbarter Wochenplan landet so im Kalender.

Taminas Woche vor dem Halbmarathon (18.10.2026): Im Gespräch abgemacht war
Montag Schwimmen, Dienstag Lauf, Mittwoch Ruhe … Sonntag Rennen. Im Kalender
stand alles einen Tag später, und das Rennen hieß „walk_run". Zwei Ursachen:
Der Chat kannte die Daten der kommenden Woche nicht, und `race_pace` war für
Läufe kein gültiger Typ — die Projektion setzte den Rückfall ein, Walk-Run.
"""

from datetime import date
from types import SimpleNamespace

from core.training_types import default_training_type, is_valid_training_type
from services.plan_projection import day_to_row


def _plan():
    return SimpleNamespace(id=1, user_id=1, week_number=-11, week_start=date(2026, 10, 19))


def test_rennen_bleibt_rennen():
    tag = {"day": "Sonntag", "date": "2026-10-25", "session_type": "run",
           "training_type": "race_pace", "duration_min": 105,
           "notes": "Sportscheckrun Nürnberg — Halbmarathon."}
    zeile = day_to_row(tag, _plan(), 6)
    assert zeile["training_type"] == "race_pace"


def test_rueckfall_fuer_laeufe_ist_kein_walk_run():
    assert default_training_type("run") == "z2_endurance"
    assert is_valid_training_type("run", "race_pace")


def test_chat_kennt_die_daten_der_kommenden_woche(monkeypatch):
    import services.claude_service as cs

    gesehen = {}

    class _Antwort:
        content = []
        usage = SimpleNamespace(input_tokens=0, output_tokens=0)
        stop_reason = "end_turn"

    class _Nachrichten:
        async def create(self, **kw):
            gesehen["system"] = kw["system"]
            return _Antwort()

    class _Client:
        messages = _Nachrichten()

    monkeypatch.setattr(cs, "client", _Client())
    monkeypatch.setattr("services.api_budget.reservieren", lambda *a, **k: None)
    monkeypatch.setattr("services.api_budget.abrechnen", lambda *a, **k: 0.0)

    import asyncio
    from datetime import timedelta

    asyncio.run(cs.chat_with_coach("Plan für nächste Woche?", [], {"name": "Tamina"}))
    heute = date.today()
    naechster_montag = heute - timedelta(days=heute.weekday()) + timedelta(days=7)
    sonntag = naechster_montag + timedelta(days=6)
    assert f"Kommende Woche: Montag {naechster_montag.isoformat()}" in gesehen["system"]
    assert f"Sonntag {sonntag.isoformat()}" in gesehen["system"]
