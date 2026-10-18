"""Gegenprobe zu Testwoche, Stornieren, E-Mail-Bestätigung und Migration 036/038.

Tests, die einen gefundenen Fehler belegen, sind `xfail(strict=True)`: Sie
beschreiben das erwartete Verhalten. Wird der Fehler behoben, schlagen sie als
XPASS fehl — dann die Markierung entfernen.
"""

import importlib.util
import pathlib
import threading
from datetime import date, datetime, timedelta

import pytest

from core.wochen import montag_von
from services.benchmark_timing import (
    TAGE_BIS_NEUTEST, letzte_testwoche, montag_ab, naechster_montag, pruefe,
)

VERSIONEN = pathlib.Path(__file__).resolve().parent.parent / "alembic" / "versions"


def _migration(name: str):
    pfad = next(VERSIONEN.glob(f"{name}_*.py"))
    spec = importlib.util.spec_from_file_location(f"pruefung_migration_{name}", pfad)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


# ── Hilfen ──────────────────────────────────────────────────────────────────

@pytest.fixture
def nutzer_fabrik(db):
    """Legt Nutzer an und räumt alles ab, was an ihnen hängt."""
    from models import AuthAction, PlannedSession, TrainingSession, User, WeeklyPlan

    angelegt: list[int] = []

    def neu(**felder):
        stempel = datetime.utcnow().timestamp()
        felder.setdefault("email", f"pruefung-{len(angelegt)}-{stempel}@test.local")
        felder.setdefault("name", "Pruefung")
        u = User(**felder)
        db.add(u)
        db.commit()
        angelegt.append(u.id)
        return u

    yield neu

    db.rollback()
    for uid in angelegt:
        db.query(TrainingSession).filter(TrainingSession.user_id == uid).update(
            {"planned_session_id": None}, synchronize_session=False)
        db.query(PlannedSession).filter(PlannedSession.user_id == uid).delete(
            synchronize_session=False)
        plan_ids = [p.id for p in db.query(WeeklyPlan.id).filter(WeeklyPlan.user_id == uid)]
        if plan_ids:
            db.query(PlannedSession).filter(PlannedSession.plan_id.in_(plan_ids)).delete(
                synchronize_session=False)
        db.query(WeeklyPlan).filter(WeeklyPlan.user_id == uid).delete(synchronize_session=False)
        db.query(TrainingSession).filter(TrainingSession.user_id == uid).delete(
            synchronize_session=False)
        db.query(AuthAction).filter(AuthAction.user_id == uid).delete(synchronize_session=False)
        db.query(User).filter(User.id == uid).delete(synchronize_session=False)
    db.commit()


def saisonziel(db, nutzer, sport="triathlon", distanz="middle"):
    """Ein aktives Saisonziel weit in der Zukunft.

    Ohne Ziel legt `create_benchmark_plan` keine Testwoche mehr an — die
    Testeinheiten richten sich nach der Sportart des Ziels.
    """
    from core.race_types import default_weeks, plan_start_for
    from models import RaceGoal

    renntag = date.today() + timedelta(days=400)
    wochen = default_weeks(sport, distanz)
    ziel = RaceGoal(user_id=nutzer.id, sport=sport, distance=distanz, race_date=renntag,
                    priority="A", plan_weeks=wochen,
                    plan_start_date=plan_start_for(renntag, wochen), is_active=True)
    db.add(ziel)
    db.commit()
    return ziel


def _mit_saisonziel(nutzer):
    """Saisonziel über eine eigene Sitzung — für die Tests mit Threads."""
    from tests.conftest import TestingSessionLocal

    sitzung = TestingSessionLocal()
    try:
        saisonziel(sitzung, nutzer)
    finally:
        sitzung.close()


def _plan(db, nutzer, montag, phase="Base 1", tage=2, status="planned",
          adjustments=None, inhalt=None):
    from models import PlannedSession, WeeklyPlan

    plan = WeeklyPlan(
        user_id=nutzer.id, week_number=5, week_start=montag,
        week_end=montag + timedelta(days=6), plan_phase=phase,
        plan_content=inhalt or {"days": []},
        adjustments_applied=adjustments if adjustments is not None
        else (["Benchmark-Woche"] if phase == "Benchmark" else []),
    )
    db.add(plan)
    db.commit()
    for i in range(tage):
        db.add(PlannedSession(
            user_id=nutzer.id, plan_id=plan.id, week_number=5,
            planned_date=montag + timedelta(days=i), day_name="Tag",
            discipline="run", training_type="z2_endurance", duration_min=45,
            day_index=i, status=status,
        ))
    db.commit()
    return plan


def _frei(monkeypatch):
    """`pruefe` liest Krankheiten und Rennen ohne Nutzerfilter — in der
    gemeinsamen Testdatenbank stehen dort fremde Einträge."""
    import services.benchmark_timing as bt

    def frei(db, ziel=None, heute=None, gemessen_am=None, testwoche_am=None):
        start = naechster_montag(heute)
        return {"moeglich": True, "start": start, "frueheste": start, "gruende": []}

    monkeypatch.setattr(bt, "pruefe", frei)


class _Tresor:
    """Nachgebauter Obsidian-Client."""

    def __init__(self, notizen=None, fehler=None):
        self.notizen = dict(notizen or {})
        self.fehler = fehler
        self.timeout, self.CONNECT_TIMEOUT_S = 15, 20
        self.enabled = True

    def get_note(self, pfad, retries=2):
        if self.fehler:
            raise self.fehler
        return self.notizen.get(pfad)

    def delete_note(self, pfad, retries=2):
        return self.notizen.pop(pfad, None) is not None

    def put_note(self, pfad, inhalt, retries=2):
        self.notizen[pfad] = inhalt


@pytest.fixture
def tresor(monkeypatch):
    import services.obsidian.client as c

    halter = {"client": _Tresor()}
    halter["client"].enabled = False
    monkeypatch.setattr(c, "client_for_profile", lambda profil: halter["client"])
    monkeypatch.setattr(c, "vault_subdir_for", lambda profil: "IronCoach")
    return halter


@pytest.fixture
def auth_an(monkeypatch):
    from core.config import settings

    monkeypatch.setattr(settings, "AUTH_REQUIRED", True)
    monkeypatch.setattr(settings, "MAIL_FROM", "coach@test.local")
    monkeypatch.setattr(settings, "MAIL_API_KEY", "test-key")
    return settings


def _kopf(nutzer):
    from core.security import create_access_token
    return {"Authorization": f"Bearer {create_access_token(nutzer.id, nutzer.email)}"}


# ── B. Nebenläufigkeit ──────────────────────────────────────────────────────

@pytest.mark.parametrize("anzahl", [3, 5])
def test_viele_gleichzeitige_testwochen_genau_eine(nutzer_fabrik, monkeypatch, anzahl):
    from core.tenancy import acting_as
    from models import User, WeeklyPlan
    from services.benchmark import create_benchmark_plan
    from tests.conftest import TestingSessionLocal

    _frei(monkeypatch)
    nutzer = nutzer_fabrik()
    _mit_saisonziel(nutzer)
    schranke = threading.Barrier(anzahl)
    ergebnisse, fehler = [], []

    def anlegen():
        s = TestingSessionLocal()
        try:
            with acting_as(nutzer.id):
                u = s.get(User, nutzer.id)
                schranke.wait()
                plan, neu = create_benchmark_plan(s, u)
                ergebnisse.append((plan.id, neu, plan.user_id))
        except Exception as e:  # pragma: no cover
            fehler.append(repr(e))
        finally:
            s.close()

    threads = [threading.Thread(target=anlegen) for _ in range(anzahl)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert not any(t.is_alive() for t in threads), "Deadlock/Timeout"
    assert not fehler, fehler
    assert sorted(n for _, n, _ in ergebnisse) == [False] * (anzahl - 1) + [True]
    assert {pid for pid, _, _ in ergebnisse} and len({pid for pid, _, _ in ergebnisse}) == 1
    assert {uid for _, _, uid in ergebnisse} == {nutzer.id}

    s = TestingSessionLocal()
    try:
        assert s.query(WeeklyPlan).filter(
            WeeklyPlan.user_id == nutzer.id, WeeklyPlan.plan_phase == "Benchmark",
        ).count() == 1
    finally:
        s.close()


def test_gleichzeitig_anlegen_und_stornieren_ohne_deadlock(nutzer_fabrik, monkeypatch, tresor):
    """Drei Anlagen und zwei Stornos gleichzeitig: kein Hänger, keine
    unerwarteten Fehler, am Ende höchstens eine Testwoche."""
    from core.tenancy import acting_as
    from models import User, WeeklyPlan
    from services.benchmark import create_benchmark_plan
    from services.plan_storno import plan_stornieren
    from tests.conftest import TestingSessionLocal

    _frei(monkeypatch)
    nutzer = nutzer_fabrik()
    _mit_saisonziel(nutzer)
    schranke = threading.Barrier(5)
    fehler = []

    def arbeit(art):
        s = TestingSessionLocal()
        try:
            with acting_as(nutzer.id):
                u = s.get(User, nutzer.id)
                schranke.wait()
                if art == "anlegen":
                    create_benchmark_plan(s, u)
                else:
                    try:
                        plan_stornieren(s, u, naechster_montag())
                    except LookupError:
                        pass
        except Exception as e:  # pragma: no cover
            fehler.append(repr(e))
        finally:
            s.close()

    threads = [threading.Thread(target=arbeit, args=(a,))
               for a in ("anlegen", "storno", "anlegen", "storno", "anlegen")]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert not any(t.is_alive() for t in threads), "Deadlock/Timeout"
    assert not fehler, fehler
    s = TestingSessionLocal()
    try:
        assert s.query(WeeklyPlan).filter(
            WeeklyPlan.user_id == nutzer.id, WeeklyPlan.plan_phase == "Benchmark",
        ).count() <= 1
    finally:
        s.close()


def test_storno_zwischen_commit_und_projektion(nutzer_fabrik, monkeypatch, tresor):
    from core.tenancy import acting_as
    from models import User
    import services.plan_projection as pp
    from services.benchmark import create_benchmark_plan
    from services.plan_storno import plan_stornieren
    from tests.conftest import TestingSessionLocal

    _frei(monkeypatch)
    nutzer = nutzer_fabrik()
    _mit_saisonziel(nutzer)
    angelegt, storniert = threading.Event(), threading.Event()
    original = pp.project_plan

    def langsam(db, plan, *a, **k):
        angelegt.set()
        storniert.wait(timeout=10)
        return original(db, plan, *a, **k)

    monkeypatch.setattr(pp, "project_plan", langsam)
    fehler = []

    def anlegen():
        s = TestingSessionLocal()
        try:
            with acting_as(nutzer.id):
                create_benchmark_plan(s, s.get(User, nutzer.id))
        except Exception as e:
            fehler.append(type(e).__name__)
        finally:
            s.close()

    t = threading.Thread(target=anlegen)
    t.start()
    assert angelegt.wait(timeout=10)
    s = TestingSessionLocal()
    try:
        with acting_as(nutzer.id):
            plan_stornieren(s, s.get(User, nutzer.id), naechster_montag())
    finally:
        s.close()
        storniert.set()
    t.join(timeout=20)
    assert not fehler, fehler


# ── C. Mandanten und Anmeldung ──────────────────────────────────────────────

def test_fremden_plan_nicht_per_endpunkt_stornieren(client, db, nutzer_fabrik, auth_an, tresor):
    from models import WeeklyPlan

    a = nutzer_fabrik(email_verified_at=datetime.utcnow())
    b = nutzer_fabrik(email_verified_at=datetime.utcnow())
    montag = montag_von(date.today()) + timedelta(weeks=4)
    fremd = _plan(db, b, montag)

    antwort = client.delete(f"/api/plan/am/{montag}", headers=_kopf(a))
    assert antwort.status_code == 404, antwort.text
    db.expire_all()
    assert db.get(WeeklyPlan, fremd.id) is not None

    eigen = _plan(db, a, montag)
    antwort = client.delete(f"/api/plan/am/{montag}", headers=_kopf(a))
    assert antwort.status_code == 200, antwort.text
    db.expire_all()
    assert db.get(WeeklyPlan, eigen.id) is None
    assert db.get(WeeklyPlan, fremd.id) is not None


def test_storno_ohne_token_401(client, auth_an):
    montag = montag_von(date.today()) + timedelta(weeks=4)
    assert client.delete(f"/api/plan/am/{montag}").status_code == 401


def test_admin_bestaetigen_nur_admin(client, db, nutzer_fabrik, auth_an):
    normal = nutzer_fabrik(email_verified_at=datetime.utcnow())
    admin = nutzer_fabrik(is_admin=True)
    ziel = nutzer_fabrik()

    r = client.post("/api/auth/admin/verify", json={"email": ziel.email}, headers=_kopf(normal))
    assert r.status_code == 403
    r = client.post("/api/auth/admin/verify", json={"email": ziel.email})
    assert r.status_code == 401
    r = client.post("/api/auth/admin/verify", json={"email": ziel.email.upper()},
                    headers=_kopf(admin))
    assert r.status_code == 200 and r.json()["status"] == "bestaetigt"
    db.expire_all()
    assert db.get(type(ziel), ziel.id).email_verified_at is not None


def test_admin_bestaetigen_platzhalter_trifft_falsches_konto(client, db, nutzer_fabrik, auth_an):
    stempel = int(datetime.utcnow().timestamp() * 1000)
    admin = nutzer_fabrik(is_admin=True)
    koeder = nutzer_fabrik(email=f"maxXm-{stempel}@test.local")
    ziel = nutzer_fabrik(email=f"max_m-{stempel}@test.local")

    r = client.post("/api/auth/admin/verify", json={"email": ziel.email}, headers=_kopf(admin))
    assert r.status_code == 200
    db.expire_all()
    assert db.get(type(ziel), ziel.id).email_verified_at is not None
    assert db.get(type(koeder), koeder.id).email_verified_at is None


def test_neusenden_sperre(client, db, nutzer_fabrik, auth_an, monkeypatch):
    import routers.auth as ra

    gesendet = []
    monkeypatch.setattr(ra, "send_verification", lambda *a, **k: gesendet.append(a) or True)
    u = nutzer_fabrik()

    r1 = client.post("/api/auth/resend-verification", headers=_kopf(u))
    assert r1.status_code == 200 and r1.json()["status"] == "verschickt", r1.text
    r2 = client.post("/api/auth/resend-verification", headers=_kopf(u))
    assert r2.status_code == 429
    assert len(gesendet) == 1


def test_neusenden_fehlschlag_sperrt_trotzdem_eine_minute(client, db, nutzer_fabrik,
                                                          auth_an, monkeypatch):
    """Nach einem abgelehnten Versand gilt die Sperre ebenfalls — dokumentiert,
    weil das Fenster dann „neu anfordern" anbietet."""
    import routers.auth as ra

    monkeypatch.setattr(ra, "send_verification", lambda *a, **k: False)
    u = nutzer_fabrik()
    r1 = client.post("/api/auth/resend-verification", headers=_kopf(u))
    assert r1.json()["status"] == "fehlgeschlagen"
    assert client.post("/api/auth/resend-verification", headers=_kopf(u)).status_code == 429


@pytest.mark.parametrize("art,erwartet", [
    ("admin", False), ("unbestaetigt", True), ("bestaetigt", False),
])
def test_login_und_me_melden_bestaetigung(client, db, nutzer_fabrik, auth_an, art, erwartet):
    from core.security import hash_password

    felder = {"password_hash": hash_password("Geheim-12345")}
    if art == "admin":
        felder["is_admin"] = True
    if art == "bestaetigt":
        felder["email_verified_at"] = datetime.utcnow()
    u = nutzer_fabrik(**felder)

    login = client.post("/api/auth/login", json={"email": u.email, "password": "Geheim-12345"})
    assert login.status_code == 200, login.text
    daten = login.json()
    assert daten["bestaetigung_noetig"] is erwartet
    assert daten["is_admin"] is (art == "admin")
    assert daten["email_verified"] is (art == "bestaetigt")

    me = client.get("/api/auth/me",
                    headers={"Authorization": f"Bearer {daten['access_token']}"}).json()
    assert me["bestaetigung_noetig"] is erwartet


def test_registrierung_haelt_versandstatus_fest(client, db, auth_an, monkeypatch):
    """Die Willkommensmail läuft im Hintergrund mit eigener Sitzung."""
    import routers.auth as ra
    from models import AthleteProfile, AuthAction, User

    monkeypatch.setattr(ra, "send_welcome", lambda *a, **k: False)
    adresse = f"reg-{datetime.utcnow().timestamp()}@test.local"
    r = client.post("/api/auth/register",
                    json={"email": adresse, "password": "Geheim-12345", "name": "Reg"})
    try:
        assert r.status_code == 200, r.text
        assert r.json()["bestaetigung_noetig"] is True
        db.expire_all()
        u = db.query(User).filter(User.email == adresse).one()
        assert u.verify_mail_status == "fehlgeschlagen"
        assert u.verify_mail_at is not None
    finally:
        u = db.query(User).filter(User.email == adresse).first()
        if u:
            db.query(AuthAction).filter(AuthAction.user_id == u.id).delete()
            db.query(AthleteProfile).filter(AthleteProfile.user_id == u.id).delete()
            db.delete(u)
            db.commit()


# ── D. Randfälle ────────────────────────────────────────────────────────────

def test_storno_unerwarteter_obsidian_fehler(db, nutzer_fabrik, tresor):
    from services.plan_storno import plan_stornieren

    u = nutzer_fabrik()
    montag = montag_von(date.today()) + timedelta(weeks=3)
    _plan(db, u, montag)
    tresor["client"] = _Tresor(fehler=RuntimeError("kaputt"))
    try:
        ergebnis = plan_stornieren(db, u, montag)
    finally:
        from models import WeeklyPlan
        db.expire_all()
        # Die Datenbank ist in jedem Fall schon bereinigt.
        assert db.query(WeeklyPlan).filter(
            WeeklyPlan.user_id == u.id, WeeklyPlan.week_start == montag).count() == 0
    assert ergebnis["obsidian"]["status"] == "fehler"


VORLAGE = (
    "---\nweek: 5\nphase: Base 1\n---\n\n# Woche 5 — Base 1\n\n"
    "<!-- ironcoach:start -->\n| Tag |\n<!-- ironcoach:end -->\n\n"
    "## Notizen\n\n"
    "<!-- Alles ab hier gehört dir. IronCoach fasst diesen Bereich nie an. -->\n\n"
)


@pytest.mark.parametrize("inhalt,erwartet", [
    ("---\nweek: 5\n---\n", False),                                  # nur Frontmatter
    ("---\nweek: 5\n---\n\n# Woche 5 — Base 1\n\n## Notizen\n", False),  # kein Block
    ("---\nweek: 5\n---\n\nMeine Zeile\n", True),                    # kein Block, eigener Text
    ("", False),
    (VORLAGE + "   \n\t\n", False),                                  # nur Leerraum
    (VORLAGE.replace("<!-- ironcoach:end -->", "") + "x\n", True),   # Block kaputt
])
def test_eigene_notizen_randfaelle(inhalt, erwartet):
    from services.obsidian.plan_note import hat_eigene_notizen
    assert hat_eigene_notizen(inhalt) is erwartet


@pytest.mark.xfail(strict=True, reason=(
    "Windows-Zeilenenden: die Frontmatter-Regex erwartet '\\n', also zählen "
    "'week: 5' usw. als eigene Notizen — die Notiz wird behalten statt gelöscht."))
def test_eigene_notizen_crlf():
    from services.obsidian.plan_note import hat_eigene_notizen
    assert hat_eigene_notizen(VORLAGE.replace("\n", "\r\n")) is False


def test_neuer_plan_nach_storno_mit_notizen_landet_in_obsidian(db, nutzer_fabrik, tresor):
    from models import PlannedSession
    from services.obsidian.plan_note import plan_note_path, render_plan_note, sync_plan_note
    from services.plan_storno import plan_stornieren

    u = nutzer_fabrik()
    montag = montag_von(date.today()) + timedelta(weeks=3)
    plan = _plan(db, u, montag)
    zeilen = db.query(PlannedSession).filter(PlannedSession.plan_id == plan.id).all()
    pfad = plan_note_path(plan, "IronCoach")
    tresor["client"] = _Tresor({pfad: render_plan_note(plan, zeilen) + "Eigene Zeile.\n"})

    from core.tenancy import acting_as
    with acting_as(u.id):
        assert plan_stornieren(db, u, montag)["obsidian"]["status"] == "behalten_eigene_notizen"
        neu = _plan(db, u, montag)
        ergebnis = sync_plan_note(db, neu, client=tresor["client"], ziele=[])
    assert ergebnis["status"] != "skipped_block_removed", ergebnis


def test_laufende_testwoche_sperrt_auch_am_mittwoch(db, nutzer_fabrik):
    u = nutzer_fabrik()
    mittwoch = montag_von(date.today()) + timedelta(weeks=1, days=2)
    montag = montag_von(mittwoch)
    _plan(db, u, montag, phase="Benchmark")
    assert letzte_testwoche(db, heute=mittwoch, user_id=u.id) == montag


def test_laufende_testwoche_am_montag_zaehlt(db, nutzer_fabrik):
    u = nutzer_fabrik()
    montag = montag_von(date.today()) + timedelta(weeks=1)
    _plan(db, u, montag, phase="Benchmark")
    assert letzte_testwoche(db, heute=montag, user_id=u.id) == montag


def test_letzte_testwoche_mehrere_plaene(db, nutzer_fabrik):
    u = nutzer_fabrik()
    heute = date.today()
    vor_sechs = montag_von(heute) - timedelta(weeks=6)
    vor_drei = montag_von(heute) - timedelta(weeks=3)
    _plan(db, u, vor_sechs, phase="Benchmark", status="completed")
    _plan(db, u, vor_drei, phase="Benchmark", status="planned")   # nie getestet
    assert letzte_testwoche(db, user_id=u.id) == vor_sechs
    naechste = naechster_montag(heute)
    _plan(db, u, naechste, phase="Benchmark")
    assert letzte_testwoche(db, user_id=u.id) == naechste
    # Fremde Testwochen zählen nicht.
    andere = nutzer_fabrik()
    _plan(db, andere, naechste + timedelta(weeks=1), phase="Benchmark")
    assert letzte_testwoche(db, user_id=u.id) == naechste


class _KeinDB:
    class _Leer:
        def filter(self, *a, **k):
            return self

        def order_by(self, *a, **k):
            return self

        def first(self):
            return None

    def query(self, *a, **k):
        return self._Leer()


def test_pruefe_frisch_und_geplant_spaetere_gewinnt():
    heute = date(2026, 10, 16)
    geplant = naechster_montag(heute)
    # geplante Testwoche sperrt länger als die Messung
    lage = pruefe(_KeinDB(), heute=heute, gemessen_am=heute - timedelta(days=10),
                  testwoche_am=geplant)
    assert lage["frueheste"] == montag_ab(geplant + timedelta(days=TAGE_BIS_NEUTEST))
    assert len(lage["gruende"]) == 2
    # Messung sperrt länger als eine vergangene Testwoche
    lage = pruefe(_KeinDB(), heute=heute, gemessen_am=heute - timedelta(days=1),
                  testwoche_am=montag_von(heute) - timedelta(weeks=4))
    assert lage["frueheste"] == montag_ab(heute - timedelta(days=1)
                                          + timedelta(days=TAGE_BIS_NEUTEST))


def test_pruefe_ziel_ueberschreibt_testwochen_sperre_nicht():
    heute = date(2026, 10, 16)
    geplant = naechster_montag(heute)
    lage = pruefe(_KeinDB(), ziel_datum=heute + timedelta(days=10), heute=heute,
                  testwoche_am=geplant)
    assert lage["frueheste"] >= montag_ab(geplant + timedelta(days=TAGE_BIS_NEUTEST))


@pytest.mark.parametrize("renntag", [
    date(2027, 3, 1), date(2027, 3, 7), date(2027, 3, 3), date(2027, 6, 27), date(2027, 6, 28),
])
def test_migration_038_rechnet_wie_plan_start_for(renntag):
    from core.race_types import plan_start_for

    m038 = _migration("038")
    assert m038._start(renntag, 20) == plan_start_for(renntag, 20)
    assert m038._start(renntag, 20).weekday() == 0


@pytest.mark.parametrize("heute", [date(2026, 10, 19), date(2026, 10, 18)])
def test_migration_038_sonntag_und_montag(db, nutzer_fabrik, heute):
    """Rennen am Montag 01.03. und Sonntag 07.03.2027 haben denselben neuen
    Start 19.10.2026. Umgestellt nur, wenn dieser Start ≥ kommender Montag."""
    from models import RaceGoal

    m038 = _migration("038")
    u1, u2 = nutzer_fabrik(), nutzer_fabrik()
    ziele = []
    for u, renntag in ((u1, date(2027, 3, 1)), (u2, date(2027, 3, 7))):
        z = RaceGoal(user_id=u.id, sport="triathlon", distance="olympic", race_date=renntag,
                     priority="A", is_active=True, plan_weeks=16,
                     plan_start_date=montag_von(renntag) - timedelta(weeks=15))
        db.add(z)
        ziele.append(z)
    db.commit()
    try:
        umgestellt = m038.olympisch_umstellen(db.connection(), heute=heute)
        db.commit()
        for z in ziele:
            db.refresh(z)
            if heute == date(2026, 10, 18):        # Sonntag → kommender Montag 19.10.
                assert z.id in umgestellt and z.plan_start_date == date(2026, 10, 19)
            else:                                   # Montag 19.10. → kommender 26.10.
                assert z.id not in umgestellt and z.plan_weeks == 16
    finally:
        for z in ziele:
            db.delete(z)
        db.commit()


def test_migration_036_verliert_keinen_test(db, nutzer_fabrik):
    from models import PlannedSession, TrainingSession, WeeklyPlan

    m036 = _migration("036")
    u = nutzer_fabrik()
    montag = naechster_montag() + timedelta(weeks=5)
    inhalt = {"pruefung": u.id}
    alt = _plan(db, u, montag, phase="Benchmark", tage=0, inhalt=inhalt)
    db.add(PlannedSession(user_id=u.id, plan_id=alt.id, week_number=5,
                          planned_date=montag + timedelta(days=6), discipline="bike",
                          day_index=6, status="completed"))
    db.commit()
    neu = _plan(db, u, montag, phase="Benchmark", tage=2, inhalt=inhalt)
    zeile = db.query(PlannedSession).filter(PlannedSession.plan_id == alt.id).one()
    echt = TrainingSession(user_id=u.id, session_date=zeile.planned_date, discipline="bike",
                           duration_min=60, week_number=5, planned_session_id=zeile.id)
    db.add(echt)
    db.commit()
    zeile.matched_session_id = echt.id
    db.commit()

    alt_id, neu_id, zeile_id = alt.id, neu.id, zeile.id
    m036.bereinigen(db.connection())
    db.commit()
    db.expire_all()
    # Das eigentliche Versprechen: kein absolvierter Test geht verloren.
    # Welches Exemplar bleibt, ist dafür nicht entscheidend — die Migration
    # behält das mit Fortschritt und hängt Fortschritt ohne passenden Platz um.
    uebrig = [pid for pid in (alt_id, neu_id)
              if db.query(WeeklyPlan.id).filter(WeeklyPlan.id == pid).first()]
    assert len(uebrig) == 1
    verweis = db.get(TrainingSession, echt.id).planned_session_id
    assert verweis is not None
    erledigt = db.get(PlannedSession, verweis)
    assert erledigt.plan_id == uebrig[0]
    assert erledigt.status == "completed"
