"""Die Doppeltag-Urne: eine Form je Woche, gewichtet nach HRV und Vorwochen.

Anlass: Doppeltage kamen nur, wenn man sie kannte und wünschte. Ein
Zwischenentwurf schlug sie nach dem Erstellen zum Annehmen vor — jede Annahme
kostete einen zweiten Claude-Aufruf und fügte eine Einheit hinzu (aus zwei
Schwimmeinheiten wurden drei). Jetzt zieht die App vor dem Erstellen, und der
Doppeltag entsteht durch Umlegen.

Geprüft wird, was die Ziehung verlässlich machen soll: dieselbe Woche zieht
immer dasselbe, die HRV schließt aus, was sie ausschließen muss, und die
Rotation nimmt die Form der Vorwoche aus der Urne.
"""

from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest

from core.phasenregeln import TAPER_SCHWIMMEN, UMLEGEN, doppel_block, vorrang_block
from services import doppel_urne
from services.doppel_urne import (
    KEIN, anpassungs_block, form_des_tages, prompt_block, ziehung,
)

MONTAG = date(2026, 6, 1)  # ein Montag
VORWOCHE = MONTAG - timedelta(days=7)


def E(disziplin, typ="z2_endurance", dauer=60):
    """Eine Vorgabe — für Tage aus mehreren Einheiten."""
    return (disziplin, typ, dauer)


@pytest.fixture
def athlet(db):
    """Ein eigener Athlet je Test, mit Aufräumen.

    Eigene Nutzer statt des Seed-Athleten: Die Urne liest Vorwochen und HRV,
    und Reste anderer Tests in derselben Woche würden die Gewichte verschieben.
    """
    from models import (
        AthleteProfile, HrvMeasurement, PlannedSession, TrainingSession, User,
        WeeklyPlan,
    )

    nutzer: list[int] = []

    def neu():
        u = User(email=f"urne-{uuid4().hex[:8]}@test.local", name="Urne")
        db.add(u)
        db.commit()
        db.add(AthleteProfile(user_id=u.id, name="Urne"))
        db.commit()
        nutzer.append(u.id)
        return u.id

    def woche(uid, start, tage, phase="Build 2"):
        """`tage`: je Tag eine Liste aus Disziplinen oder `E(...)`-Tupeln."""
        plan = WeeklyPlan(
            user_id=uid, week_number=50, week_start=start,
            week_end=start + timedelta(days=6), plan_phase=phase, plan_content={},
        )
        db.add(plan)
        db.commit()
        for i, tag in enumerate(tage):
            for eintrag in tag:
                d, typ, dauer = eintrag if isinstance(eintrag, tuple) else E(eintrag)
                db.add(PlannedSession(
                    user_id=uid, plan_id=plan.id, week_number=50,
                    planned_date=start + timedelta(days=i), day_name="Tag",
                    discipline=d, training_type=typ, duration_min=dauer,
                    day_index=i,
                ))
        db.commit()

    def hrv(uid, status, tag=None):
        db.add(HrvMeasurement(user_id=uid, measured_at=tag or date.today(),
                              rmssd=70, hrv_status=status))
        db.commit()

    def absolviert(uid, tag, disziplinen):
        for d in disziplinen:
            db.add(TrainingSession(user_id=uid, session_date=tag, week_number=1,
                                   discipline=d, duration_min=45))
        db.commit()

    yield SimpleNamespace(neu=neu, woche=woche, hrv=hrv, absolviert=absolviert)

    # Über die Nutzer aufräumen, nicht Objekt für Objekt: Nach einem Commit
    # sind die Objekte abgelaufen, und die Fremdschlüssel löschen teils mit.
    db.rollback()
    for modell in (PlannedSession, WeeklyPlan, HrvMeasurement, TrainingSession,
                   AthleteProfile):
        db.query(modell).filter(modell.user_id.in_(nutzer)).delete(
            synchronize_session=False)
    db.query(User).filter(User.id.in_(nutzer)).delete(synchronize_session=False)
    db.commit()


# Eine Vorwoche, die jede Form zulässt: zwei Schwimmeinheiten, ein langer Lauf,
# kein Doppeltag (also keine Rotation).
OFFEN = [
    ["bike"], [E("run", "threshold")], ["swim"], ["bike"],
    ["rest"], ["swim"], [E("run", "long_run", 100)],
]


# --- Erkennung ---------------------------------------------------------------

def _tag(*eintraege):
    return [SimpleNamespace(discipline=d, training_type=t, duration_min=m,
                            target_hr_zone=None) for d, t, m in eintraege]


def test_erkennung_der_formen():
    assert form_des_tages(_tag(E("run", "threshold"), E("swim"))) == "schwimmen_als_zweite"
    assert form_des_tages(_tag(E("run"), E("run", "threshold"))) == "locker_plus_qualitaet"
    assert form_des_tages(_tag(E("run", "threshold"), E("run", "threshold"))) == "doppelschwelle_leicht"
    assert form_des_tages(_tag(E("run"), E("run"))) == "langer_lauf_geteilt"


def test_schwimmen_plus_kraft_ist_keine_gezogene_form():
    """Das ist das Mittel der Grundbasis-Regel bei voller Woche.

    Zählte es mit, nähme jede volle Vorwoche der Urne das Schwimmen weg.
    """
    assert form_des_tages(_tag(E("swim"), E("gym", "strength"))) is None
    assert form_des_tages(_tag(E("run"))) is None
    assert form_des_tages(_tag(E("run"), E("rest"))) is None


# --- Ziehung -----------------------------------------------------------------

def test_dieselbe_woche_zieht_immer_dasselbe(athlet, db):
    """Sonst spränge der Doppeltag bei jedem Neuerzeugen, und die Kachel zeigte
    vorher etwas anderes an, als der Plan bekommt."""
    uid = athlet.neu()
    athlet.woche(uid, VORWOCHE, OFFEN)
    athlet.hrv(uid, "green")
    erste = ziehung(db, MONTAG, "Build 2", uid)
    for _ in range(5):
        assert ziehung(db, MONTAG, "Build 2", uid)["form"] == erste["form"]


def test_unter_der_spanne_nur_schwimmen_oder_nichts(athlet, db):
    uid = athlet.neu()
    athlet.woche(uid, VORWOCHE, OFFEN)
    athlet.hrv(uid, "red")
    z = ziehung(db, MONTAG, "Build 2", uid)
    erlaubt = {f for f, g in z["gewichte"].items() if g > 0}
    assert erlaubt <= {KEIN, "schwimmen_als_zweite"}
    assert z["form"] in (None, "schwimmen_als_zweite")
    assert "HRV unter der Spanne" in z["grund"]


@pytest.mark.parametrize("status", ["yellow", None])
def test_doppelschwelle_nur_bei_normaler_hrv(athlet, db, status):
    uid = athlet.neu()
    athlet.woche(uid, VORWOCHE, OFFEN)
    athlet.absolviert(uid, MONTAG - timedelta(days=10), ["run", "run"])
    if status:
        athlet.hrv(uid, status)
    z = ziehung(db, MONTAG, "Build 2", uid)
    assert z["gewichte"]["doppelschwelle_leicht"] == 0
    # Und „kein" wird wahrscheinlicher.
    assert z["gewichte"][KEIN] > doppel_urne.GRUNDGEWICHT[KEIN]


def test_doppelschwelle_erst_nach_vertragenem_doppeltag(athlet, db):
    uid = athlet.neu()
    athlet.woche(uid, VORWOCHE, OFFEN)
    athlet.hrv(uid, "green")
    assert ziehung(db, MONTAG, "Build 2", uid)["gewichte"]["doppelschwelle_leicht"] == 0

    athlet.absolviert(uid, MONTAG - timedelta(days=10), ["run", "swim"])
    assert ziehung(db, MONTAG, "Build 2", uid)["gewichte"]["doppelschwelle_leicht"] > 0


def test_deload_und_rennwoche_ohne_doppeltag(athlet, db):
    uid = athlet.neu()
    athlet.woche(uid, VORWOCHE, OFFEN)
    athlet.hrv(uid, "green")
    assert ziehung(db, MONTAG, "Build 2", uid, deload=True)["form"] is None
    assert "Deload" in ziehung(db, MONTAG, "Build 2", uid, deload=True)["grund"]
    assert ziehung(db, MONTAG, "Race Week", uid)["form"] is None
    assert ziehung(db, MONTAG, "Off Season", uid)["form"] is None


def test_im_taper_nur_lockeres_schwimmen(athlet, db):
    uid = athlet.neu()
    athlet.woche(uid, VORWOCHE, OFFEN)
    athlet.hrv(uid, "green")
    z = ziehung(db, MONTAG, "Taper", uid)
    assert set(z["gewichte"]) == {"schwimmen_als_zweite", KEIN}
    # „kein" ist im Taper der Normalfall.
    assert z["gewichte"][KEIN] > z["gewichte"]["schwimmen_als_zweite"]


def test_die_form_der_vorwoche_ist_aus_der_urne(athlet, db):
    uid = athlet.neu()
    vorwoche = [list(t) for t in OFFEN]
    vorwoche[1] = [E("run"), E("run", "threshold")]  # locker + Qualität
    athlet.woche(uid, VORWOCHE, vorwoche)
    athlet.hrv(uid, "green")
    z = ziehung(db, MONTAG, "Build 2", uid)
    assert z["gewichte"]["locker_plus_qualitaet"] == 0
    assert "war letzte Woche dran" in z["grund"]


def test_die_form_von_vor_zwei_wochen_nur_halb(athlet, db):
    uid = athlet.neu()
    zwei = [list(t) for t in OFFEN]
    zwei[1] = [E("run"), E("run", "threshold")]
    athlet.woche(uid, MONTAG - timedelta(days=14), zwei)
    athlet.woche(uid, VORWOCHE, OFFEN)
    athlet.hrv(uid, "green")
    z = ziehung(db, MONTAG, "Build 2", uid)
    assert z["gewichte"]["locker_plus_qualitaet"] == doppel_urne.GRUNDGEWICHT["locker_plus_qualitaet"] * 0.5


def test_ohne_zwei_schwimmeinheiten_nichts_umzulegen(athlet, db):
    """Mit einem Schwimmen gäbe es den Doppeltag nur mit einer Einheit mehr."""
    uid = athlet.neu()
    athlet.woche(uid, VORWOCHE, [["bike"], ["run"], ["swim"], ["bike"], ["rest"], ["run"], ["bike"]])
    athlet.hrv(uid, "green")
    z = ziehung(db, MONTAG, "Grundlage", uid)
    assert z["gewichte"]["schwimmen_als_zweite"] == 0
    # Und ohne langen Lauf nichts zu teilen.
    assert z["gewichte"]["langer_lauf_geteilt"] == 0


def test_ohne_vorwoche_schliesst_nichts_aus(athlet, db):
    """Erster Plan: Unbekanntes ist kein Ausschluss.

    Sonst bekäme ein neuer Athlet nie das Schwimmen gezogen. Ob es passt,
    entscheidet dann der Coach, der Baustein erlaubt ihm das Weglassen.
    """
    uid = athlet.neu()
    athlet.hrv(uid, "green")
    z = ziehung(db, MONTAG, "Grundlage", uid)
    assert z["gewichte"]["schwimmen_als_zweite"] > 0
    assert z["gewichte"]["langer_lauf_geteilt"] > 0


def test_die_historie_eines_anderen_athleten_zaehlt_nicht(athlet, db):
    a, b = athlet.neu(), athlet.neu()
    athlet.woche(a, VORWOCHE, OFFEN)
    andere = [list(t) for t in OFFEN]
    andere[1] = [E("run"), E("run", "threshold")]
    athlet.woche(b, VORWOCHE, andere)
    athlet.hrv(a, "green")
    athlet.hrv(b, "red")
    z = ziehung(db, MONTAG, "Build 2", a)
    assert z["gewichte"]["locker_plus_qualitaet"] > 0
    assert "HRV normal" in z["grund"]


def test_ueber_viele_wochen_kommt_jede_form_vor():
    """Die Urne verteilt, sie entscheidet nicht immer gleich.

    Historie und HRV hier festgehalten, damit nur der Zufall je Montag wirkt.
    """
    # Je Einheit ein eigener Tag — am selben Datum wären sie selbst ein
    # Doppeltag, und die Rotation nähme das Schwimmen aus der Urne.
    vorwoche = [
        SimpleNamespace(discipline=d, training_type=t, duration_min=m,
                        planned_date=VORWOCHE + timedelta(days=i), target_hr_zone=None)
        for i, (d, t, m) in enumerate((E("swim"), E("swim"), E("run", "long_run", 100)))
    ]
    gezogen = []
    with patch("services.week_shape.einheiten_der_woche", return_value=vorwoche), \
            patch.object(doppel_urne, "_hrv_status", return_value="green"), \
            patch.object(doppel_urne, "_doppeltag_vertragen", return_value=True):
        for i in range(200):
            gezogen.append(ziehung(None, MONTAG + timedelta(days=7 * i), "Build 2", 1)["form"])
    for form in ("schwimmen_als_zweite", "locker_plus_qualitaet",
                 "langer_lauf_geteilt", "doppelschwelle_leicht", None):
        assert form in gezogen, form
    # „kein Doppeltag" hat Gewicht 2 von 10 — rund ein Fünftel.
    assert 0.1 < gezogen.count(None) / len(gezogen) < 0.35


# --- Prompt ------------------------------------------------------------------

def test_prompt_verlangt_umlegen_statt_hinzufuegen():
    z = {"form": "schwimmen_als_zweite", "titel": "Schwimmen als zweite Einheit",
         "grund": "HRV normal"}
    text = prompt_block(z, "Build 2")
    assert "DOPPELTAG DIESER WOCHE" in text
    assert "Umlegen" in text
    assert "kein** zusätzliches Schwimmen" in text
    assert "genau einen" in text
    assert "coaching_comment" in text
    assert "Taper" not in text
    assert "Z1–Z2" in prompt_block(z, "Taper")


def test_ohne_doppeltag_kein_prompt():
    assert prompt_block({"form": None, "grund": "x"}) == ""
    assert prompt_block(None) == ""


def test_anpassung_kennt_den_doppeltag_der_woche(athlet, db):
    uid = athlet.neu()
    woche = [list(t) for t in OFFEN]
    woche[1] = [E("run", "threshold"), E("swim")]
    athlet.woche(uid, MONTAG, woche)
    text = anpassungs_block(db, MONTAG, MONTAG + timedelta(days=6), "Build 2", uid)
    assert "Schwimmen als zweite Einheit" in text
    assert "erhalten" in text
    assert anpassungs_block(db, VORWOCHE, VORWOCHE + timedelta(days=6), "Build 2", uid) == ""


# --- Regeln in allen Pfaden --------------------------------------------------

def test_umlegen_steht_im_doppel_und_im_vorrangblock():
    """`vorrang_block` rendern alle drei Pfade, `doppel_block` Plan und Anpassung."""
    assert UMLEGEN in doppel_block("Build 2")
    assert UMLEGEN in vorrang_block("Build 2")
    assert UMLEGEN in vorrang_block("Grundlage")


def test_taper_ausnahme_in_allen_pfaden():
    assert TAPER_SCHWIMMEN in doppel_block("Taper")
    assert TAPER_SCHWIMMEN in vorrang_block("Taper")
    # Von selbst weiterhin keine — die Ausnahme ist kein Freibrief.
    assert "In dieser Phase keine" in doppel_block("Taper")
    assert TAPER_SCHWIMMEN not in vorrang_block("Race Week")
    assert TAPER_SCHWIMMEN not in doppel_block("Race Week")


# --- Endpunkte ---------------------------------------------------------------

def test_endpunkt_liefert_die_ziehung(client):
    resp = client.get(f"/api/plan/doppeltag/am/{MONTAG}")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert set(data) >= {"form", "titel", "grund", "hinweise", "hrv", "phase", "week_start"}
    # Der Testathlet hat kein Saisonziel: Off Season, also kein Doppeltag.
    assert data["form"] is None


# --- HRV-Ampel in der Kachel ---------------------------------------------------

def test_hinweise_sind_der_grund_ohne_die_hrv(db, athlet):
    """Die Kachel zeigt die HRV als Ampel; der Satz daneben soll sie nicht
    noch einmal als Text wiederholen. Der Prompt behält den ganzen Satz."""
    uid = athlet.neu()
    athlet.hrv(uid, "green")
    z = ziehung(db, MONTAG, "Build 2", uid, heute=date.today())
    assert z["grund"].startswith("HRV normal")
    assert all("HRV" not in h for h in z["hinweise"])


def test_hrv_lage_schnitt_und_dieselbe_farbe_wie_die_urne(db, athlet):
    from models import AthleteProfile, HrvMeasurement
    from services.doppel_urne import _hrv_status, hrv_lage

    uid = athlet.neu()
    heute = date.today()
    for tage, wert, status in ((0, 60, "yellow"), (1, 80, "green"), (3, 70, "green"),
                               # Außerhalb der sieben Tage: zählt nicht mit.
                               (8, 20, "red")):
        db.add(HrvMeasurement(user_id=uid, measured_at=heute - timedelta(days=tage),
                              rmssd=wert, hrv_status=status))
    db.commit()
    profil = db.query(AthleteProfile).filter(AthleteProfile.user_id == uid).one()

    lage = hrv_lage(db, profil, heute)
    assert lage["schnitt_7"] == 70.0
    assert lage["messungen"] == 3
    assert lage["letzter_wert"] == 60
    # Die Ampel urteilt wie die Urne — nicht nach dem Schnitt.
    assert lage["status"] == _hrv_status(db, uid, heute) == "yellow"


def test_hrv_lage_ohne_messungen_schweigt(db, athlet):
    from models import AthleteProfile
    from services.doppel_urne import hrv_lage

    uid = athlet.neu()
    profil = db.query(AthleteProfile).filter(AthleteProfile.user_id == uid).one()
    assert hrv_lage(db, profil) is None


def _generieren(client, **params):
    from tests.test_plan import MOCK_PLAN

    gezogen = {"form": "schwimmen_als_zweite", "titel": "Schwimmen als zweite Einheit",
               "grund": "HRV normal", "gewichte": {}}
    with patch("services.plan_generator.generate_weekly_plan", autospec=True,
               return_value=MOCK_PLAN) as mock, \
            patch("services.doppel_urne.ziehung", return_value=gezogen):
        resp = client.get("/api/plan/generate", params=params)
    assert resp.status_code == 200, resp.text
    return mock.call_args.kwargs["wochenform"]


def test_generieren_baut_die_ziehung_ein_und_laesst_sich_abschalten(client):
    assert "DOPPELTAG DIESER WOCHE" in _generieren(client)
    assert "DOPPELTAG DIESER WOCHE" not in _generieren(client, doppeltag="false")


def test_im_chat_nur_bedingt():
    """Im Chat steht der Baustein in jeder Nachricht — er darf keinen Doppeltag
    aufdrängen, wenn niemand nach dem Wochenplan gefragt hat."""
    z = {"form": "locker_plus_qualitaet", "titel": "Locker morgens, Qualität abends",
         "grund": "HRV normal"}
    text = prompt_block(z, "Build 2", bedingt=True)
    assert "Nur falls" in text
    assert "genau einen" in text


def _chat_wochenform(db, uid):
    from services import coach_context

    gezogen = {"form": "schwimmen_als_zweite", "titel": "Schwimmen als zweite Einheit",
               "grund": "x", "gewichte": {}}
    from models import AthleteProfile

    profil = db.query(AthleteProfile).filter(AthleteProfile.user_id == uid).first()
    profil.plan_start_date = MONTAG  # nur im Speicher; das Aufräumen rollt zurück
    fakten = {
        "offseason": False, "base_period": False, "phase": "Build 2",
        "week": 10, "total_weeks": 33, "profile": profil, "goal": None,
    }
    with patch("core.prompt_templates.get_week_dates",
               return_value=(MONTAG, MONTAG + timedelta(days=6))), \
            patch("services.week_shape.prompt_block", return_value=""), \
            patch("services.intervall_format.rotation_block", return_value=""), \
            patch("services.doppel_urne.ziehung", return_value=gezogen):
        return coach_context.bloecke(db, fakten=fakten)["wochenform"]


def test_chat_ohne_plan_nennt_die_ziehung_bedingt(athlet, db):
    uid = athlet.neu()
    text = _chat_wochenform(db, uid)
    assert "DOPPELTAG DIESER WOCHE: Schwimmen als zweite Einheit" in text
    assert "Nur falls" in text


def test_chat_mit_plan_nennt_den_plan_nicht_die_ziehung(athlet, db):
    """Wer mit „ohne Doppeltag" erstellt hat, bekommt im Chat keinen aufgedrängt."""
    uid = athlet.neu()
    athlet.woche(uid, MONTAG, OFFEN)  # ein Plan ohne Doppeltag
    assert "DOPPELTAG" not in _chat_wochenform(db, uid)

    woche = [list(t) for t in OFFEN]
    woche[1] = [E("run", "threshold"), E("swim")]
    athlet.woche(uid, MONTAG, woche)  # jüngerer Plan mit Doppeltag
    text = _chat_wochenform(db, uid)
    assert "Die Woche enthält einen Doppeltag" in text
    assert "Nur falls" not in text


def test_wochenlage_liefert_dieselbe_phase_wie_der_plan(client, db):
    """`wochenlage` ist aus dem Generator herausgelöst — die Kachel und der
    Plan müssen dieselbe Phase sehen, sonst zeigt die Kachel eine Ziehung an,
    die der Plan nicht bekommt."""
    from tests.test_plan import MOCK_PLAN

    from services.plan_generator import wochenlage

    w = wochenlage(db)
    with patch("services.plan_generator.generate_weekly_plan", autospec=True,
               return_value=MOCK_PLAN):
        plan = client.get("/api/plan/generate").json()
    # Der Testathlet hat kein Saisonziel: Off Season, ohne Deload-Zählung.
    assert w["phase"] == "Off Season"
    assert w["deload"] is False
    assert plan["plan_phase"].startswith(w["phase"])
    assert plan["week_start"] == str(w["week_start"])
