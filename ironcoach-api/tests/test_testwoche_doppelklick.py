"""Testwoche: Doppelklick, 90-Tage-Sperre und die Bereinigung des Doppels.

Bei einem echten Onboarding wurde „Testwoche planen" zweimal gedrückt, und
es entstanden zwei Pläne für dieselbe Woche. Zwei Ursachen:

  * `create_benchmark_plan` prüfte auf einen bestehenden Plan und legte erst
    danach an, ohne Sperre dazwischen. Zwei gleichzeitige Anfragen lasen
    beide „noch keiner".
  * Die 90-Tage-Sperre zählte nur eine **Messung**. Ein neuer Athlet hat
    keine, also sperrte für ihn nichts.

Dazu die beiden Migrationen: 036 entfernt das bestehende Doppel, 038 stellt
noch nicht begonnene Olympisch-Ziele auf 20 Wochen um.
"""

import importlib.util
import pathlib
import threading
from datetime import date, datetime, timedelta

import pytest

from core.wochen import montag_von
from services.benchmark_timing import (
    TAGE_BIS_NEUTEST,
    letzte_testwoche,
    montag_ab,
    naechster_montag,
    pruefe,
)

VERSIONEN = pathlib.Path(__file__).resolve().parent.parent / "alembic" / "versions"


def _migration(name: str):
    pfad = next(VERSIONEN.glob(f"{name}_*.py"))
    spec = importlib.util.spec_from_file_location(f"migration_{name}", pfad)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


@pytest.fixture
def eigener_nutzer(db):
    """Ein frischer Athlet ohne Profil, Ziel oder Pläne — wie Justin am
    Onboarding-Tag. Räumt hinterher alles ab, was an ihm hängt."""
    from models import PlannedSession, User, WeeklyPlan

    nutzer = User(email=f"doppelklick-{datetime.utcnow().timestamp()}@test.local",
                  name="Doppelklick")
    db.add(nutzer)
    db.commit()
    yield nutzer
    plaene = db.query(WeeklyPlan).filter(WeeklyPlan.user_id == nutzer.id).all()
    for p in plaene:
        db.query(PlannedSession).filter(PlannedSession.plan_id == p.id).delete()
        db.delete(p)
    db.delete(nutzer)
    db.commit()


def _frei(monkeypatch):
    """`pruefe` liest Krankheiten und Rennen ohne Nutzerfilter — in der
    gemeinsamen Testdatenbank stünden dort Einträge anderer Tests. Für den
    Wettlauf ist die Prüfung nicht der Gegenstand; sie wird hier freigegeben."""
    import services.benchmark_timing as bt

    def frei(db, ziel=None, heute=None, gemessen_am=None, testwoche_am=None):
        start = naechster_montag(heute)
        return {"moeglich": True, "start": start, "frueheste": start, "gruende": []}

    monkeypatch.setattr(bt, "pruefe", frei)


# ── Der Doppelklick ─────────────────────────────────────────────────────────

def test_gleichzeitige_anfragen_legen_genau_eine_an(eigener_nutzer, monkeypatch):
    """Der eigentliche Fehler: zwei Anfragen zur selben Zeit.

    Ohne die Datenbanksperre lasen beide „noch kein Plan" und legten beide
    einen an. Jeder Thread bekommt eine eigene Verbindung, und die Schranke
    lässt beide gleichzeitig losgehen.
    """
    from models import User, WeeklyPlan
    from services.benchmark import create_benchmark_plan
    from tests.conftest import TestingSessionLocal

    _frei(monkeypatch)
    schranke = threading.Barrier(2)
    ergebnisse, fehler = [], []

    def anlegen():
        s = TestingSessionLocal()
        try:
            nutzer = s.get(User, eigener_nutzer.id)
            schranke.wait()
            plan, neu = create_benchmark_plan(s, nutzer)
            ergebnisse.append((plan.id, neu))
        except Exception as e:  # pragma: no cover - im Fehlerfall sichtbar machen
            fehler.append(e)
        finally:
            s.close()

    threads = [threading.Thread(target=anlegen) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert not fehler, fehler
    assert len(ergebnisse) == 2
    # Genau einer hat angelegt, der andere bekam denselben Plan zurück.
    assert sorted(neu for _, neu in ergebnisse) == [False, True]
    assert len({pid for pid, _ in ergebnisse}) == 1

    from tests.conftest import TestingSessionLocal as S
    pruef = S()
    try:
        anzahl = pruef.query(WeeklyPlan).filter(
            WeeklyPlan.user_id == eigener_nutzer.id,
            WeeklyPlan.week_start == naechster_montag(),
            WeeklyPlan.plan_phase == "Benchmark",
        ).count()
    finally:
        pruef.close()
    assert anzahl == 1


def test_zweiter_klick_liefert_dieselbe_woche(eigener_nutzer, db, monkeypatch):
    """Kein Fehler, sondern dieselbe Absicht: der bestehende Plan kommt zurück."""
    from services.benchmark import create_benchmark_plan

    _frei(monkeypatch)
    erster, neu1 = create_benchmark_plan(db, eigener_nutzer)
    zweiter, neu2 = create_benchmark_plan(db, eigener_nutzer)
    assert neu1 is True and neu2 is False
    assert erster.id == zweiter.id


# ── Die 90-Tage-Sperre zählt auch eine geplante Testwoche ──────────────────

def test_geplante_testwoche_sperrt():
    heute = date(2026, 10, 16)
    start = naechster_montag(heute)
    lage = pruefe(_KeinDB(), heute=heute, testwoche_am=start)
    assert lage["moeglich"] is False
    assert lage["frueheste"] == montag_ab(start + timedelta(days=TAGE_BIS_NEUTEST))
    assert any("bereits eine Testwoche geplant" in g for g in lage["gruende"])
    assert any("storniere" in g for g in lage["gruende"])


def test_vergangene_testwoche_nennt_ihren_beginn():
    heute = date(2026, 10, 16)
    vor_vier_wochen = montag_ab(heute) - timedelta(weeks=4)
    lage = pruefe(_KeinDB(), heute=heute, testwoche_am=vor_vier_wochen)
    assert lage["moeglich"] is False
    assert any("letzte Testwoche begann" in g for g in lage["gruende"])


def test_nach_neunzig_tagen_wieder_frei():
    heute = date(2026, 10, 16)
    lange_her = montag_ab(heute) - timedelta(days=TAGE_BIS_NEUTEST + 7)
    lage = pruefe(_KeinDB(), heute=heute, testwoche_am=lange_her)
    assert not any("Testwoche" in g for g in lage["gruende"])


class _KeinDB:
    """`pruefe` fragt Rennen und Krankheiten ab — hier ohne Treffer, damit nur
    die Testwochenregel wirkt."""

    class _Leer:
        def filter(self, *a, **k):
            return self

        def order_by(self, *a, **k):
            return self

        def first(self):
            return None

    def query(self, *a, **k):
        return self._Leer()


def _benchmark_plan(db, nutzer, montag, erledigt=False):
    from models import PlannedSession, WeeklyPlan

    plan = WeeklyPlan(
        user_id=nutzer.id, week_number=1, week_start=montag,
        week_end=montag + timedelta(days=6), plan_phase="Benchmark",
        plan_content={"days": []}, adjustments_applied=["Benchmark-Woche"],
    )
    db.add(plan)
    db.commit()
    p = PlannedSession(
        user_id=nutzer.id, plan_id=plan.id, week_number=1,
        planned_date=montag + timedelta(days=1), day_name="Dienstag",
        discipline="bike", training_type="threshold", duration_min=60,
        day_index=1, status="completed" if erledigt else "planned",
    )
    db.add(p)
    db.commit()
    return plan


def test_vergangene_testwoche_ohne_test_sperrt_nicht(eigener_nutzer, db):
    """Eine verstrichene, nie gelaufene Testwoche lässt sich nicht mehr
    stornieren — sie sperrte sonst 90 Tage, ohne dass etwas gemessen wurde."""
    vor_drei = montag_ab(date.today()) - timedelta(weeks=3)
    _benchmark_plan(db, eigener_nutzer, vor_drei, erledigt=False)
    assert letzte_testwoche(db, user_id=eigener_nutzer.id) is None


def test_vergangene_testwoche_mit_test_sperrt(eigener_nutzer, db):
    vor_drei = montag_ab(date.today()) - timedelta(weeks=3)
    _benchmark_plan(db, eigener_nutzer, vor_drei, erledigt=True)
    assert letzte_testwoche(db, user_id=eigener_nutzer.id) == vor_drei


def test_geplante_testwoche_zaehlt_immer(eigener_nutzer, db):
    naechste = naechster_montag()
    _benchmark_plan(db, eigener_nutzer, naechste, erledigt=False)
    assert letzte_testwoche(db, user_id=eigener_nutzer.id) == naechste


def test_anpassung_einer_testwoche_bleibt_moeglich(eigener_nutzer, db):
    """Warum es keine Datenbankregel „eine Testwoche je Woche" gibt: Eine
    Anpassung legt eine zweite Fassung mit derselben Phase an."""
    naechste = naechster_montag()
    _benchmark_plan(db, eigener_nutzer, naechste)
    _benchmark_plan(db, eigener_nutzer, naechste)  # keine Ausnahme


def test_timing_zeigt_geplant_ab(client, db):
    """Die Oberfläche zeigt „geplant ab …" statt eines Knopfs, der nur eine
    Sperre auslöst — und mahnt nicht „Testwoche steht an"."""
    from models import PlannedSession, User, WeeklyPlan

    nutzer = db.query(User).order_by(User.id).first()
    naechste = naechster_montag()
    vorher = db.query(WeeklyPlan).filter(
        WeeklyPlan.user_id == nutzer.id, WeeklyPlan.week_start == naechste,
    ).all()
    plan = _benchmark_plan(db, nutzer, naechste)
    try:
        daten = client.get("/api/benchmark/timing").json()
        assert daten["moeglich"] is False
        assert daten["geplant_ab"] == str(naechste)
        assert daten["vorwarnung"] is None
    finally:
        db.query(PlannedSession).filter(PlannedSession.plan_id == plan.id).delete()
        db.delete(plan)
        db.commit()
    assert len(vorher) == len(db.query(WeeklyPlan).filter(
        WeeklyPlan.user_id == nutzer.id, WeeklyPlan.week_start == naechste,
    ).all())


# ── Migration 036: das bestehende Doppel ────────────────────────────────────

def test_migration_036_entfernt_das_doppel(eigener_nutzer, db):
    """Das Exemplar mit Einheiten bleibt, die Zuordnung der echten Einheit
    bleibt erhalten, das leere Doppel verschwindet."""
    from models import PlannedSession, TrainingSession, WeeklyPlan

    m036 = _migration("036")
    naechste = naechster_montag()
    mit = _benchmark_plan(db, eigener_nutzer, naechste)
    ohne = WeeklyPlan(
        user_id=eigener_nutzer.id, week_number=1, week_start=naechste,
        week_end=naechste + timedelta(days=6), plan_phase="Benchmark",
        plan_content=mit.plan_content, adjustments_applied=["Benchmark-Woche"],
    )
    db.add(ohne)
    db.commit()

    zeile = db.query(PlannedSession).filter(PlannedSession.plan_id == mit.id).one()
    einheit = TrainingSession(
        user_id=eigener_nutzer.id, session_date=zeile.planned_date,
        discipline="bike", duration_min=60, planned_session_id=zeile.id,
        week_number=1,
    )
    db.add(einheit)
    db.commit()
    ohne_id, mit_id = ohne.id, mit.id
    try:
        entfernt = m036.bereinigen(db.connection())
        db.commit()
        assert entfernt >= 1
        assert db.query(WeeklyPlan).filter(WeeklyPlan.id == ohne_id).first() is None
        db.expire_all()
        uebrig = db.query(WeeklyPlan).filter(
            WeeklyPlan.user_id == eigener_nutzer.id,
            WeeklyPlan.week_start == naechste,
        ).all()
        assert [p.id for p in uebrig] == [mit_id]
        assert db.get(TrainingSession, einheit.id).planned_session_id == zeile.id
        # Ein zweiter Lauf findet nichts mehr.
        assert m036.bereinigen(db.connection()) == 0
    finally:
        db.delete(db.get(TrainingSession, einheit.id))
        db.commit()


def test_migration_036_laesst_angepasste_fassung_stehen(eigener_nutzer, db):
    """Eine angepasste Testwoche ist eine gewollte neue Fassung."""
    from models import WeeklyPlan

    m036 = _migration("036")
    naechste = naechster_montag()
    original = _benchmark_plan(db, eigener_nutzer, naechste)
    angepasst = WeeklyPlan(
        user_id=eigener_nutzer.id, week_number=1, week_start=naechste,
        week_end=naechste + timedelta(days=6), plan_phase="Benchmark",
        plan_content=original.plan_content,
        adjustments_applied=["Benchmark-Woche", "Dienstag tauschen"],
    )
    db.add(angepasst)
    db.commit()
    m036.bereinigen(db.connection())
    db.commit()
    # Die Migration durchsucht die ganze Datenbank; geprüft werden nur
    # die eigenen Pläne, nicht eine Gesamtzahl.
    db.expire_all()
    assert db.get(WeeklyPlan, original.id) is not None
    assert db.get(WeeklyPlan, angepasst.id) is not None


# ── Migration 038: Olympisch auf 20 Wochen ─────────────────────────────────

@pytest.fixture
def olympisch(db, eigener_nutzer):
    from models import RaceGoal

    angelegt = []

    def ziel(renntag: date, wochen: int = 16):
        z = RaceGoal(
            user_id=eigener_nutzer.id, sport="triathlon", distance="olympic",
            race_date=renntag, priority="A", is_active=True,
            plan_weeks=wochen,
            plan_start_date=montag_von(renntag) - timedelta(weeks=wochen - 1),
        )
        db.add(z)
        db.commit()
        angelegt.append(z)
        return z

    yield ziel
    for z in angelegt:
        db.delete(z)
    db.commit()


def test_migration_038_stellt_noch_nicht_begonnenes_ziel_um(olympisch, db):
    m038 = _migration("038")
    heute = date(2026, 10, 16)
    renntag = date(2027, 6, 27)          # weit genug weg
    z = olympisch(renntag)
    umgestellt = m038.olympisch_umstellen(db.connection(), heute=heute)
    db.commit()
    db.refresh(z)
    assert z.id in umgestellt
    assert z.plan_weeks == 20
    assert z.plan_start_date == montag_von(renntag) - timedelta(weeks=19)


def test_migration_038_laesst_laufende_vorbereitung_stehen(olympisch, db):
    """Neuer Start läge in der Vergangenheit — die Wochennummern verrutschten."""
    m038 = _migration("038")
    heute = date(2026, 10, 16)
    z = olympisch(date(2027, 2, 14))     # neuer Start läge vor heute
    assert z.id not in m038.olympisch_umstellen(db.connection(), heute=heute)
    db.commit()
    db.refresh(z)
    assert z.plan_weeks == 16


def test_migration_038_laesst_ziel_mit_plaenen_stehen(olympisch, db, eigener_nutzer):
    """Ein Wochenplan nach dem neuen Start verlöre seine Wochennummer."""
    from models import WeeklyPlan

    m038 = _migration("038")
    heute = date(2026, 10, 16)
    renntag = date(2027, 6, 27)
    z = olympisch(renntag)
    neu_start = montag_von(renntag) - timedelta(weeks=19)
    db.add(WeeklyPlan(
        user_id=eigener_nutzer.id, week_number=2, week_start=neu_start + timedelta(weeks=1),
        week_end=neu_start + timedelta(weeks=1, days=6), plan_phase="Base 1",
        plan_content={"days": []},
    ))
    db.commit()
    assert z.id not in m038.olympisch_umstellen(db.connection(), heute=heute)


def test_migration_038_testwoche_haelt_nicht_auf(olympisch, db, eigener_nutzer):
    """Eine Testwoche liegt vor dem Aufbau und trägt keine verschiebbare Phase."""
    m038 = _migration("038")
    heute = date(2026, 10, 16)
    z = olympisch(date(2027, 6, 27))
    _benchmark_plan(db, eigener_nutzer, naechster_montag(heute))
    assert z.id in m038.olympisch_umstellen(db.connection(), heute=heute)
    db.commit()


def test_migration_038_respektiert_bewusst_gesetzte_dauer(olympisch, db):
    m038 = _migration("038")
    z = olympisch(date(2027, 6, 27), wochen=18)
    assert z.id not in m038.olympisch_umstellen(db.connection(), heute=date(2026, 10, 16))


def test_neues_olympisch_ziel_hat_zwanzig_wochen():
    from core.race_types import default_weeks

    assert default_weeks("triathlon", "olympic") == 20
