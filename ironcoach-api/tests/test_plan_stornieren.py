"""Einen Wochenplan stornieren — Datenbank und Obsidian.

Bisher konnte nur der Admin einen falschen Plan entfernen. Jetzt storniert
der Athlet ihn selbst in der Plan-Kachel: alle Fassungen der Woche, ihre
geplanten Einheiten und die Notiz in Obsidian. Vergangene Wochen bleiben,
und die laufende nur, solange darin nichts erledigt ist.
"""

from datetime import date, datetime, timedelta

import pytest

from services.plan_storno import PlanNichtStornierbar, plan_stornieren

HEUTE = date(2026, 10, 14)                   # ein Mittwoch
DIESE = HEUTE - timedelta(days=HEUTE.weekday())
NAECHSTE = DIESE + timedelta(weeks=1)
LETZTE = DIESE - timedelta(weeks=1)


@pytest.fixture
def athlet(db):
    from models import PlannedSession, TrainingSession, User, WeeklyPlan

    nutzer = User(email=f"storno-{datetime.utcnow().timestamp()}@test.local", name="Storno")
    db.add(nutzer)
    db.commit()
    yield nutzer
    db.query(TrainingSession).filter(TrainingSession.user_id == nutzer.id).delete()
    for p in db.query(WeeklyPlan).filter(WeeklyPlan.user_id == nutzer.id).all():
        db.query(PlannedSession).filter(PlannedSession.plan_id == p.id).delete()
        db.delete(p)
    db.delete(nutzer)
    db.commit()


def _plan(db, nutzer, montag, phase="Base 1", tage=3, status="planned"):
    from models import PlannedSession, WeeklyPlan

    plan = WeeklyPlan(
        user_id=nutzer.id, week_number=5, week_start=montag,
        week_end=montag + timedelta(days=6), plan_phase=phase,
        plan_content={"days": []},
        adjustments_applied=["Benchmark-Woche"] if phase == "Benchmark" else [],
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


def _zaehle(db, nutzer, montag):
    from models import PlannedSession, WeeklyPlan

    plaene = db.query(WeeklyPlan).filter(
        WeeklyPlan.user_id == nutzer.id, WeeklyPlan.week_start == montag).all()
    einheiten = db.query(PlannedSession).filter(
        PlannedSession.plan_id.in_([p.id for p in plaene])).count() if plaene else 0
    return len(plaene), einheiten


class _Obsidian:
    """Nachgebauter Tresor: Notizen je Pfad, merkt sich, was passiert ist."""

    def __init__(self, notizen=None, aus=False, nicht_erreichbar=False):
        self.notizen = dict(notizen or {})
        self.aus = aus
        self.nicht_erreichbar = nicht_erreichbar
        self.geloescht, self.geschrieben, self.versuche = [], {}, []
        self.timeout, self.CONNECT_TIMEOUT_S = 15, 20

    @property
    def enabled(self):
        return not self.aus

    def _pruefe(self, retries):
        self.versuche.append(retries)
        if self.nicht_erreichbar:
            from services.obsidian.client import ObsidianUnavailable
            raise ObsidianUnavailable("nicht erreichbar")

    def get_note(self, pfad, retries=2):
        self._pruefe(retries)
        return self.notizen.get(pfad)

    def delete_note(self, pfad, retries=2):
        self._pruefe(retries)
        self.geloescht.append(pfad)
        return self.notizen.pop(pfad, None) is not None

    def put_note(self, pfad, inhalt, retries=2):
        self._pruefe(retries)
        self.geschrieben[pfad] = inhalt


@pytest.fixture
def tresor(monkeypatch):
    import services.obsidian.client as c

    halter = {"client": _Obsidian(aus=True)}
    monkeypatch.setattr(c, "client_for_profile", lambda profil: halter["client"])
    monkeypatch.setattr(c, "vault_subdir_for", lambda profil: "IronCoach")
    return halter


# ── Was entfernt wird ───────────────────────────────────────────────────────

def test_naechste_woche_mit_zwei_fassungen_wird_ganz_entfernt(athlet, db, tresor):
    """Alle Fassungen der Woche — eine Anpassung legt eine neue Zeile an.
    Nur die jüngste zu entfernen, ließe die vorige wieder erscheinen."""
    _plan(db, athlet, NAECHSTE)
    _plan(db, athlet, NAECHSTE)
    assert _zaehle(db, athlet, NAECHSTE) == (2, 6)

    ergebnis = plan_stornieren(db, athlet, NAECHSTE, heute=HEUTE)

    assert ergebnis["status"] == "storniert"
    assert ergebnis["plaene_entfernt"] == 2
    assert ergebnis["einheiten_entfernt"] == 6
    assert _zaehle(db, athlet, NAECHSTE) == (0, 0)


def test_beliebiger_tag_der_woche_trifft_ihren_montag(athlet, db, tresor):
    _plan(db, athlet, NAECHSTE)
    plan_stornieren(db, athlet, NAECHSTE + timedelta(days=3), heute=HEUTE)
    assert _zaehle(db, athlet, NAECHSTE) == (0, 0)


def test_ohne_plan_nichts_zu_stornieren(athlet, db, tresor):
    with pytest.raises(LookupError):
        plan_stornieren(db, athlet, NAECHSTE, heute=HEUTE)


# ── Die beiden Grenzen ──────────────────────────────────────────────────────

def test_vergangene_woche_bleibt(athlet, db, tresor):
    """Ein Plan ist auch ein Protokoll dessen, was vorgesehen war."""
    _plan(db, athlet, LETZTE)
    with pytest.raises(PlanNichtStornierbar, match="Vergangene Wochen"):
        plan_stornieren(db, athlet, LETZTE, heute=HEUTE)
    assert _zaehle(db, athlet, LETZTE) == (1, 3)


def test_laufende_woche_mit_erledigter_einheit_bleibt(athlet, db, tresor):
    """Die erledigte Einheit hängt an einer echten — die Woche verlöre ihre
    Vorgabe. Die Trainingseinheit selbst bleibt unangetastet."""
    from models import PlannedSession, TrainingSession

    plan = _plan(db, athlet, DIESE)
    zeile = db.query(PlannedSession).filter(PlannedSession.plan_id == plan.id).first()
    zeile.status = "completed"
    echt = TrainingSession(
        user_id=athlet.id, session_date=zeile.planned_date, discipline="run",
        duration_min=45, week_number=5, planned_session_id=zeile.id,
    )
    db.add(echt)
    db.commit()

    with pytest.raises(PlanNichtStornierbar, match="schon 1 Einheit erledigt"):
        plan_stornieren(db, athlet, DIESE, heute=HEUTE)
    assert _zaehle(db, athlet, DIESE) == (1, 3)
    assert db.get(TrainingSession, echt.id).planned_session_id == zeile.id


def test_laufende_woche_nur_verschoben_ist_stornierbar(athlet, db, tresor):
    """Ziehen im Kalender setzt `moved` auch auf künftigen Tagen — dort ist
    nichts passiert."""
    _plan(db, athlet, DIESE, status="moved")
    plan_stornieren(db, athlet, DIESE, heute=HEUTE)
    assert _zaehle(db, athlet, DIESE) == (0, 0)


def test_fremder_plan_bleibt(athlet, db, tresor):
    """Ausdrücklich nach Nutzer gefiltert — hier wird gelöscht."""
    from models import PlannedSession, User, WeeklyPlan

    andere = User(email=f"fremd-{datetime.utcnow().timestamp()}@test.local")
    db.add(andere)
    db.commit()
    fremd = _plan(db, andere, NAECHSTE)
    _plan(db, athlet, NAECHSTE)
    try:
        plan_stornieren(db, athlet, NAECHSTE, heute=HEUTE)
        assert _zaehle(db, athlet, NAECHSTE) == (0, 0)
        assert _zaehle(db, andere, NAECHSTE) == (1, 3)
    finally:
        db.query(PlannedSession).filter(PlannedSession.plan_id == fremd.id).delete()
        db.delete(db.get(WeeklyPlan, fremd.id))
        db.delete(andere)
        db.commit()


# ── Obsidian ────────────────────────────────────────────────────────────────

def test_obsidian_aus_datenbank_trotzdem_bereinigt(athlet, db, tresor):
    _plan(db, athlet, NAECHSTE)
    ergebnis = plan_stornieren(db, athlet, NAECHSTE, heute=HEUTE)
    assert ergebnis["obsidian"]["status"] == "deaktiviert"
    assert _zaehle(db, athlet, NAECHSTE) == (0, 0)


def test_obsidian_nicht_erreichbar_datenbank_trotzdem_bereinigt(athlet, db, tresor):
    """Ein nicht erreichbarer Tresor darf das Stornieren nicht verhindern —
    die Antwort sagt, welche Notiz von Hand zu löschen ist."""
    tresor["client"] = _Obsidian(nicht_erreichbar=True)
    _plan(db, athlet, NAECHSTE)
    ergebnis = plan_stornieren(db, athlet, NAECHSTE, heute=HEUTE)
    assert ergebnis["obsidian"]["status"] == "nicht_erreichbar"
    assert "von Hand löschen" in ergebnis["message"]
    assert _zaehle(db, athlet, NAECHSTE) == (0, 0)
    # Ein einziger Versuch — hier wartet ein Mensch.
    assert set(tresor["client"].versuche) == {0}


def _notiz_pfad(plan):
    from services.obsidian.plan_note import plan_note_path
    return plan_note_path(plan, "IronCoach")


def test_leere_plannotiz_wird_geloescht(athlet, db, tresor):
    from models import PlannedSession
    from services.obsidian.plan_note import render_plan_note

    plan = _plan(db, athlet, NAECHSTE)
    zeilen = db.query(PlannedSession).filter(PlannedSession.plan_id == plan.id).all()
    pfad = _notiz_pfad(plan)
    tresor["client"] = _Obsidian({pfad: render_plan_note(plan, zeilen)})

    ergebnis = plan_stornieren(db, athlet, NAECHSTE, heute=HEUTE)
    assert ergebnis["obsidian"]["status"] == "geloescht"
    assert pfad in tresor["client"].geloescht
    assert "Notiz in Obsidian ist entfernt" in ergebnis["message"]


def test_eigene_notizen_bleiben_erhalten(athlet, db, tresor):
    """Unter „## Notizen" steht, was der Athlet selbst geschrieben hat. Das
    verschwindet nicht — nur der Planblock geht."""
    from models import PlannedSession
    from services.obsidian import notes as note_utils
    from services.obsidian.plan_note import render_plan_note

    plan = _plan(db, athlet, NAECHSTE)
    zeilen = db.query(PlannedSession).filter(PlannedSession.plan_id == plan.id).all()
    pfad = _notiz_pfad(plan)
    notiz = render_plan_note(plan, zeilen) + "Schienbein fühlt sich gut an.\n"
    tresor["client"] = _Obsidian({pfad: notiz})

    ergebnis = plan_stornieren(db, athlet, NAECHSTE, heute=HEUTE)
    assert ergebnis["obsidian"]["status"] == "behalten_eigene_notizen"
    assert pfad not in tresor["client"].geloescht
    neu = tresor["client"].geschrieben[pfad]
    assert "Schienbein fühlt sich gut an." in neu
    assert "storniert" in neu
    # Die Markierungen bleiben, nur ihr Inhalt ist weg. Ohne sie hielte der
    # Abgleich die Notiz für eine, aus der der Athlet den Block absichtlich
    # entfernt hat — ein neu erstellter Plan derselben Woche käme nie hinein.
    assert note_utils.MARKER_START in neu and note_utils.MARKER_END in neu
    block = neu.split(note_utils.MARKER_START)[1].split(note_utils.MARKER_END)[0]
    assert "| " not in block            # keine Plantabelle mehr


def test_eigene_notizen_erkennen():
    from services.obsidian.plan_note import hat_eigene_notizen

    vorlage = (
        "---\nweek: 5\n---\n\n# Woche 5 — Base 1\n\n"
        "<!-- ironcoach:start -->\n| Tag |\n<!-- ironcoach:end -->\n\n"
        "## Notizen\n\n"
        "<!-- Alles ab hier gehört dir. IronCoach fasst diesen Bereich nie an. -->\n\n"
    )
    assert hat_eigene_notizen(vorlage) is False
    assert hat_eigene_notizen(vorlage + "Muskelkater nach Dienstag.\n") is True


# ── Testwoche und Endpunkt ──────────────────────────────────────────────────

def test_storno_einer_testwoche_gibt_die_sperre_frei(athlet, db, tresor):
    from services.benchmark_timing import letzte_testwoche, naechster_montag

    montag = naechster_montag()
    _plan(db, athlet, montag, phase="Benchmark")
    assert letzte_testwoche(db, user_id=athlet.id) == montag

    ergebnis = plan_stornieren(db, athlet, montag)
    assert ergebnis["benchmark_freigegeben"] is True
    assert "Testwoche ist freigegeben" in ergebnis["message"]
    assert letzte_testwoche(db, user_id=athlet.id) is None


def test_endpunkt(client, db, tresor):
    """Der Weg der Plan-Kachel: DELETE, danach liefert GET 404."""
    from models import User

    nutzer = db.query(User).order_by(User.id).first()
    montag = date.today() + timedelta(weeks=3)
    montag -= timedelta(days=montag.weekday())
    _plan(db, nutzer, montag)

    antwort = client.delete(f"/api/plan/am/{montag}")
    assert antwort.status_code == 200, antwort.text
    assert antwort.json()["plaene_entfernt"] == 1
    assert client.get(f"/api/plan/am/{montag}").status_code == 404
    assert client.delete(f"/api/plan/am/{montag}").status_code == 404


def test_endpunkt_vergangene_woche_409(client, db, tresor):
    from models import PlannedSession, User, WeeklyPlan

    nutzer = db.query(User).order_by(User.id).first()
    montag = date.today() - timedelta(weeks=8)
    montag -= timedelta(days=montag.weekday())
    plan = _plan(db, nutzer, montag)
    try:
        antwort = client.delete(f"/api/plan/am/{montag}")
        assert antwort.status_code == 409
        assert "Vergangene Wochen" in antwort.json()["detail"]
    finally:
        db.query(PlannedSession).filter(PlannedSession.plan_id == plan.id).delete()
        db.delete(db.get(WeeklyPlan, plan.id))
        db.commit()
