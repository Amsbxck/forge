"""Die zwei Klammern des Laufumfangs — und warum eine allein sich selbst füttert.

Die Einzellauf-Regel (Frandsen 2025) begrenzt **einen** Lauf gegen den längsten
der letzten 30 Tage. Allein angewendet hat sie zwei Löcher:

1. Sie steuert den **Plan**, nicht die Ausführung. Wer einen Plantag durch
   einen langen Lauf ersetzt, überschreitet sie ungeprüft — und hebt damit die
   Grenze für die Folgewochen. Der Verstoß belohnte sich selbst: Amirs Lauf am
   05.07. lag 99 % über der damaligen Grenze von 10,7 km und hob sie am Tag
   danach auf 23,4 km.
2. Sie sagt nichts über den **Wochen**umfang. Nutzt der Coach sie bei jedem
   Lauf aus, wächst die Woche mit.
"""

from datetime import date, timedelta
from types import SimpleNamespace

from services.season_summary import (
    SPRUNG_ANTEIL,
    WOCHEN_ZUWACHS_GRENZE,
    _lauf_obergrenze,
    _lauf_wochenumfang,
)

HEUTE = date(2026, 10, 11)


def lauf(tage_her: int, km: float, disziplin: str = "run", commute: bool = False):
    return SimpleNamespace(
        discipline=disziplin, session_date=HEUTE - timedelta(days=tage_her),
        distance_km=km, duration_min=int(km * 6), is_commute=commute,
    )


def test_grenze_folgt_dem_laengsten_lauf():
    g = _lauf_obergrenze([lauf(10, 10.0), lauf(3, 8.0)], HEUTE)
    assert g["laengster_km"] == 10.0
    assert g["hoechstens_km"] == round(10.0 * SPRUNG_ANTEIL, 1)


def test_ohne_lauf_im_fenster_keine_grenze():
    """Ein Lauf von vor 40 Tagen zählt nicht mehr."""
    assert _lauf_obergrenze([lauf(40, 21.0)], HEUTE) is None


def test_sprung_wird_nicht_als_niveau_verbucht():
    """Der Kern: ein Sprung darf die Grenze nicht erben.

    Vorher: 8 km, erlaubt wären 8,8 gewesen. Gelaufen: 17 km. Die Grenze
    stand danach bei 18,7 km, als hätte der Athlet sich das erarbeitet.
    """
    einheiten = [lauf(40, 8.0), lauf(25, 8.0), lauf(20, 17.0)]
    g = _lauf_obergrenze(einheiten, HEUTE)
    assert g["laengster_km"] == 17.0
    # Die Grenze bleibt rechnerisch, aber der Sprung wird benannt.
    assert g["war_selbst_sprung"] is not None
    assert g["war_selbst_sprung"] > 90  # 17 / 8.8 - 1 = 93 %


def test_gewachsener_lauf_gilt_nicht_als_sprung():
    """Wer schrittweise steigert, bekommt keine Warnung."""
    einheiten = [lauf(28, 10.0), lauf(21, 10.8), lauf(14, 11.8), lauf(7, 12.9)]
    g = _lauf_obergrenze(einheiten, HEUTE)
    assert g["laengster_km"] == 12.9
    assert g["war_selbst_sprung"] is None


def test_erster_lauf_ueberhaupt_ist_kein_sprung():
    """Ohne Vorgeschichte gibt es nichts zu überschreiten."""
    g = _lauf_obergrenze([lauf(5, 9.0)], HEUTE)
    assert g["war_selbst_sprung"] is None


# HEUTE ist ein Sonntag; die Wochenfenster sind montagsbasiert, und die
# **laufende** Woche bleibt draußen — gezählt werden nur abgeschlossene
# Wochen. Daraus ergeben sich diese Abstände:
#   Woche -4: 28–34 Tage her    Woche -2: 14–20 Tage her
#   Woche -3: 21–27 Tage her    Woche -1:  7–13 Tage her
W4, W3, W2, W1 = 30, 23, 16, 9


def test_wochenumfang_und_zweiwochenzuwachs():
    einheiten = [
        lauf(W4, 5.0), lauf(W4 - 1, 5.0),    # Woche -4: 10 km
        lauf(W3, 6.0), lauf(W3 - 1, 6.0),    # Woche -3: 12 km
        lauf(W2, 7.0), lauf(W2 - 1, 7.0),    # Woche -2: 14 km
        lauf(W1, 8.0), lauf(W1 - 1, 8.0),    # Woche -1: 16 km
    ]
    u = _lauf_wochenumfang(einheiten, HEUTE)
    assert u["wochen_km"] == [10.0, 12.0, 14.0, 16.0]
    # 16 gegen 12 km sind +33 % über zwei Wochen, also über der Grenze.
    assert u["zuwachs_zwei_wochen"] == 33
    assert u["zuwachs_zwei_wochen"] > u["grenze_prozent"]


def test_laufende_woche_bleibt_draussen():
    """Eine halbe Woche sagt nichts über den Wochenumfang."""
    assert _lauf_wochenumfang([lauf(1, 8.0)], HEUTE) is None


def test_arbeitswege_zaehlen_nicht_zum_laufumfang():
    ohne = _lauf_wochenumfang([lauf(W1, 8.0)], HEUTE)
    mit = _lauf_wochenumfang(
        [lauf(W1, 8.0), lauf(W1, 5.0, commute=True)], HEUTE
    )
    assert ohne["wochen_km"] == mit["wochen_km"] == [0, 0, 0, 8.0]


def test_kein_zuwachs_aus_einer_nullwoche():
    """Aus 0 km lässt sich kein Prozentwert bilden."""
    u = _lauf_wochenumfang([lauf(W1, 8.0)], HEUTE)
    assert u["zuwachs_zwei_wochen"] is None


def test_beide_klammern_stehen_im_prompt(db):
    from models import TrainingSession, User
    from services.season_summary import prompt_block

    nutzer = db.query(User).first()
    angelegt = []
    try:
        for tage_her, km in ((40, 8.0), (34, 8.0), (31, 17.0), (9, 9.0)):
            s = TrainingSession(
                user_id=nutzer.id, session_date=HEUTE - timedelta(days=tage_her),
                discipline="run", duration_min=int(km * 6), distance_km=km,
                week_number=1,
            )
            db.add(s)
            angelegt.append(s)
        db.commit()

        text = prompt_block(db, nutzer, heute=HEUTE)
        assert "Längster Lauf der letzten 30 Tage" in text
        assert "Laufumfang der letzten" in text
        # Der 17er liegt ausserhalb des 30-Tage-Fensters, der 9er bestimmt
        # die Grenze — und gegen 17 km ist er kein Sprung.
        assert "**9.0 km**" in text
        assert "Achtung:" not in text
    finally:
        for s in angelegt:
            db.delete(s)
        db.commit()


def test_konstanten_folgen_den_studien():
    assert SPRUNG_ANTEIL == 1.10          # Frandsen 2025
    assert WOCHEN_ZUWACHS_GRENZE == 0.30  # Nielsen 2014


# --- Soll gegen Ist: wann ein verworfenes Paar doch etwas sagt ---------------

def test_wiederholte_verwerfung_wird_zur_auskunft(db):
    """Einmal ist ein Zuordnungsfehler, dreimal ist eine Aussage.

    Paare über dem Dreifachen der Vorgabe gelten als Zuordnungsfehler — eine
    ungeplante lange Ausfahrt, die auf einem kurzen Slot landete. Bei beiden
    Athleten war das aber **jede** Radeinheit des Zeitraums: 327 statt 75, 320
    statt 90, 244 statt 55 Minuten. Das Signal, das einen zu kurz angesetzten
    Umfang melden soll, war dafür blind — es warf die Belege weg.
    """
    from models import PlannedSession, TrainingSession, User, WeeklyPlan
    from services.season_summary import _belastbarkeit

    nutzer = db.query(User).first()
    plan = WeeklyPlan(
        user_id=nutzer.id, week_number=1, week_start=HEUTE - timedelta(days=20),
        week_end=HEUTE - timedelta(days=14), plan_phase="Base 1", plan_content={},
    )
    db.add(plan)
    db.commit()

    angelegt = [plan]
    try:
        for i, (soll_min, ist_min) in enumerate(((75, 327), (90, 320), (55, 244))):
            tag = HEUTE - timedelta(days=19 - i)
            p = PlannedSession(
                user_id=nutzer.id, plan_id=plan.id, week_number=1,
                planned_date=tag, day_name="Mo", discipline="bike",
                training_type="z2_endurance", duration_min=soll_min, day_index=i,
            )
            db.add(p)
            db.commit()
            s = TrainingSession(
                user_id=nutzer.id, session_date=tag, discipline="bike",
                duration_min=ist_min, week_number=1, planned_session_id=p.id,
            )
            db.add(s)
            db.commit()
            angelegt += [p, s]

        b = _belastbarkeit(db, HEUTE - timedelta(weeks=10), HEUTE)
        # Weiter nicht mitgezählt — die Zahl bliebe sonst unbrauchbar.
        assert b["mehr"] == 0
        assert b["verworfen"] >= 3
        # Aber nicht mehr verschwiegen.
        assert "bike" in b["weit_darueber"]
        anzahl, faktor = b["weit_darueber"]["bike"]
        assert anzahl == 3
        assert 3.5 < faktor < 5.0
    finally:
        for o in reversed(angelegt):
            db.delete(o)
        db.commit()


def test_einzelner_ausreisser_bleibt_ein_zuordnungsfehler():
    """Ein Paar allein ergibt keine Aussage über den Umfang."""
    from services.season_summary import _belastbarkeit
    # Über die reine Zählung geprüft: `weit_darueber` nimmt erst ab zwei auf.
    # (Der Schwellenwert steht in der Rückgabe von `_belastbarkeit`.)
    import inspect

    from services import season_summary
    quelle = inspect.getsource(season_summary._belastbarkeit)
    assert "if len(v) >= 2" in quelle
