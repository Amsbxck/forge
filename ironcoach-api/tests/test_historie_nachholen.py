"""Beim ersten Verbinden mit Strava die Historie nachholen.

Die Fitness (CTL) ist ein Mittel über 42 Tage. Wer mit zwei Wochen Daten
startet, bekommt einen Wert, der zu niedrig ist und es wochenlang bleibt —
und der erste Plan entsteht auf dieser Grundlage.

Nachgeholt wird nur beim ersten Mal. Wer die Verbindung erneuert, hat seine
Historie bereits; ein zweiter Durchlauf über drei Monate kostete dann nur
Strava-Kontingent.
"""

from datetime import date

import pytest

from core.config import settings
from models import AthleteProfile, TrainingSession


def test_das_fenster_passt_zur_zeitkonstante():
    """42 Tage Zeitkonstante — zwei Wochen reichen dafür nicht."""
    assert settings.STRAVA_BACKFILL_DAYS >= 42
    assert settings.STRAVA_BACKFILL_DAYS > settings.RECONCILE_WINDOW_DAYS


def test_liste_blaettert_nur_wenn_gewuenscht():
    """Der stündliche Lauf soll nicht plötzlich vier Seiten holen."""
    import inspect
    from services.reconcile import reconcile_activities
    from services.strava_service import StravaService

    assert inspect.signature(reconcile_activities).parameters["max_seiten"].default == 1
    assert inspect.signature(StravaService.list_activities).parameters["max_seiten"].default == 1


@pytest.mark.asyncio
async def test_seiten_werden_zusammengefuehrt(monkeypatch):
    """Ohne Blättern fiele alles nach der ersten Seite stillschweigend weg."""
    from services.strava_service import StravaService

    seiten = {1: [{"id": i} for i in range(100)],
              2: [{"id": 100 + i} for i in range(30)]}

    class _Antwort:
        def __init__(self, daten): self._daten = daten
        def raise_for_status(self): pass
        def json(self): return self._daten

    class _Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url, params=None, headers=None):
            return _Antwort(seiten.get(params["page"], []))

    service = StravaService(None)
    monkeypatch.setattr(service, "refresh_token_if_needed", lambda *a, **k: _fertig("t"))
    monkeypatch.setattr("services.strava_service.httpx.AsyncClient", lambda **k: _Client())

    ergebnis = await service.list_activities(1, per_page=100, max_seiten=4)
    assert len(ergebnis) == 130, "beide Seiten, dann Abbruch bei unvollständiger"


async def _fertig(wert):
    return wert


def test_nur_beim_ersten_mal(client, db):
    """Wer schon Einheiten hat, löst kein Nachholen aus."""
    import pathlib
    quelle = pathlib.Path(__file__).parent.parent / "routers" / "strava_webhook.py"
    text = quelle.read_text()
    assert "if not hat_einheiten:" in text
    assert "background_tasks.add_task(_historie_nachholen, user_id)" in text


def test_die_hintergrundaufgabe_setzt_den_mandantenkontext():
    """Eine Hintergrundaufgabe startet nach dem Ende der Anfrage.

    Die ContextVar ist dann zurückgesetzt — ohne `acting_as` liefe der
    Abgleich ohne Nutzer und schriebe die Aktivitäten dem falschen Konto zu.
    Genau dieser Fehler hat die Neuplanung nach einer Krankmeldung
    monatelang stillgelegt.
    """
    import inspect
    from routers.strava_webhook import _historie_nachholen

    quelltext = inspect.getsource(_historie_nachholen)
    assert "acting_as(user_id)" in quelltext
    assert "SessionLocal()" in quelltext, "eigene Sitzung, nicht die der Anfrage"
