import os
import sys
import pytest
from datetime import date

# Use a test database URL via env before any imports
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_ironcoach.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("STRAVA_CLIENT_ID", "test")
os.environ.setdefault("STRAVA_CLIENT_SECRET", "test")
os.environ.setdefault("STRAVA_VERIFY_TOKEN", "test_token")

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from database import Base, get_db
from main import app

SQLALCHEMY_TEST_URL = os.environ["DATABASE_URL"]
engine = create_engine(SQLALCHEMY_TEST_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="session", autouse=True)
def create_tables():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


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
