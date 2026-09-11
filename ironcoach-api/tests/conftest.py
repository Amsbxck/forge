import os
import sys
import pytest
from datetime import date

# --- Testdatenbank festlegen, BEVOR irgendetwas importiert wird ---
#
# Hier stand `setdefault`. Im Container ist DATABASE_URL aber gesetzt — auf
# die echte Datenbank. Die Tests liefen damit gegen den Produktivbestand, und
# die Aufräumroutine unten ruft `drop_all`: Ein einziger pytest-Lauf hätte
# sämtliche Tabellen gelöscht. Dass es nie dazu kam, lag allein daran, dass
# die SQLite-Option `check_same_thread` psycopg2 vorher zum Absturz brachte.
#
# Deshalb jetzt ein **erzwungener** Wert, und zwar eine eigene Datenbank neben
# der echten: Die Modelle nutzen JSONB und ARRAY, das gibt es in SQLite nicht.
def _test_db_url() -> str:
    vorgabe = os.environ.get("TEST_DATABASE_URL")
    if vorgabe:
        return vorgabe
    laufend = os.environ.get("DATABASE_URL", "")
    if laufend.startswith("postgresql"):
        basis, _, name = laufend.rpartition("/")
        # Niemals denselben Namen: sonst wäre der Schutz oben wirkungslos.
        return f"{basis}/{name}_test"
    return "postgresql://amir:localdev@db/ironcoach_test"


TEST_URL = _test_db_url()
os.environ["DATABASE_URL"] = TEST_URL
# Ebenfalls erzwungen statt `setdefault`: Im Container stehen echte Werte in
# der Umgebung, und `setdefault` hätte sie stehen lassen. Beim Verify-Token
# war genau das die Ursache eines fehlschlagenden Webhook-Tests.
os.environ["ANTHROPIC_API_KEY"] = "test-key"
os.environ["STRAVA_CLIENT_ID"] = "test"
os.environ["STRAVA_CLIENT_SECRET"] = "test"
os.environ["STRAVA_VERIFY_TOKEN"] = "test_token"
# Die Tests stammen aus der Zeit vor der Anmeldung und schicken kein Token.
# Ohne diese Zeile antwortet jeder Endpunkt mit 401. Der Anmeldeweg selbst
# wird dadurch nicht abgedeckt — das ist eine bekannte Lücke, keine Absicht.
os.environ["AUTH_REQUIRED"] = "false"
# Seit dem Deploy-Umbau bricht die Anwendung ohne Geheimnis ab.
os.environ.setdefault("JWT_SECRET", "test-secret-nur-fuer-tests")

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from database import Base, get_db
from main import app

SQLALCHEMY_TEST_URL = TEST_URL


def _ensure_database(url: str) -> None:
    """Die Testdatenbank anlegen, falls sie noch nicht existiert."""
    if not url.startswith("postgresql"):
        return
    basis, _, name = url.rpartition("/")
    from sqlalchemy import text

    # Über die Wartungsdatenbank verbinden — in die eigene kann man sich nicht
    # einwählen, solange es sie nicht gibt.
    wartung = create_engine(f"{basis}/postgres", isolation_level="AUTOCOMMIT")
    with wartung.connect() as conn:
        da = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": name}
        ).first()
        if not da:
            conn.execute(text(f'CREATE DATABASE "{name}"'))
    wartung.dispose()


_ensure_database(SQLALCHEMY_TEST_URL)

# `check_same_thread` ist eine SQLite-Option. An psycopg2 gereicht bricht die
# Verbindung ab — das war die Ursache aller 22 Fehler.
_connect_args = (
    {"check_same_thread": False} if SQLALCHEMY_TEST_URL.startswith("sqlite") else {}
)
engine = create_engine(SQLALCHEMY_TEST_URL, connect_args=_connect_args)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _reset_schema() -> None:
    from sqlalchemy import text

    with engine.connect() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
        conn.commit()


def _seed_user() -> None:
    """Ein Nutzer, auf den die Auflösung ohne Anmeldung zurückfällt.

    Ohne ihn liefert `resolve_user` auch bei AUTH_REQUIRED=false nichts, und
    jeder Endpunkt antwortet mit 401.
    """
    from models import AthleteProfile, User

    session = TestingSessionLocal()
    try:
        nutzer = User(email="test@example.invalid", name="Testathlet")
        session.add(nutzer)
        session.commit()
        session.add(AthleteProfile(user_id=nutzer.id, name="Testathlet"))
        session.commit()
    finally:
        session.close()


@pytest.fixture(scope="session", autouse=True)
def create_tables():
    # Letzte Bremse vor `drop_all`: Zeigt die Adresse wider Erwarten nicht auf
    # eine Testdatenbank, wird abgebrochen statt gelöscht.
    if not SQLALCHEMY_TEST_URL.rstrip("/").endswith("_test"):
        raise RuntimeError(
            f"Testlauf abgebrochen: {SQLALCHEMY_TEST_URL} sieht nicht nach "
            "einer Testdatenbank aus. Der Name muss auf '_test' enden."
        )
    _reset_schema()
    Base.metadata.create_all(bind=engine)
    _seed_user()
    yield
    # Nicht `drop_all`: Der Fremdschlüssel zwischen planned_sessions und
    # training_sessions ist zyklisch und deshalb unbenannt (use_alter) —
    # SQLAlchemy kann ihn nicht einzeln ablegen und bricht ab. Das ganze
    # Schema zu leeren umgeht die Reihenfolge.
    _reset_schema()


@pytest.fixture
def db():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db):
    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def seed_athlete(db):
    from models import AthleteProfile
    existing = db.query(AthleteProfile).first()
    if not existing:
        profile = AthleteProfile(
            name="Amir",
            ftp_watts=238,
            max_hr=212,
            z1_hr_max=138,
            z2_hr_min=139,
            z2_hr_max=173,
            z3_hr_min=174,
            z3_hr_max=189,
            z4_hr_min=190,
            z4_hr_max=210,
            race_date=date(2026, 8, 31),
            race_goal="sub 5:30h 70.3",
            plan_start_date=date(2025, 12, 22),
        )
        db.add(profile)
        db.commit()
