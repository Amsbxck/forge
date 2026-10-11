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
