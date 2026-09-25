"""Der CSS-Test setzt zwei maximale Versuche voraus.

Ist das kürzere Stück nicht deutlich schneller als das längere, war es
keiner. Dann steckt in beiden Zeiten derselbe Anteil Ausdauer, die
Differenz wird zu klein und die CSS fällt viel zu schnell aus.

Rechnerisch für 400/200:  CSS = 2 x Pace(400) − Pace(200).
Sind beide Pace gleich, ist die CSS gleich der 400-m-Pace — die App
behauptete dann, das Renntempo über 400 m sei dauerhaft haltbar.

Der Anlass stand in echten Daten: 400 m in 7:53 (1:58/100 m), 200 m in
3:59 (2:00/100 m). Daraus ergäbe sich eine CSS von 1:57/100 m.
"""

import pytest

from services.swim_css import (
    MAX_PACE_S_JE_100M, MIN_PACE_S_JE_100M, css_from_times, detect_from_session,
    format_pace, paar_plausibel, pace_je_100m,
)


class _Einheit:
    def __init__(self, laps):
        self.streams = {"laps": laps}
        self.id = 1
        self.session_date = __import__("datetime").date(2026, 9, 25)


def _lap(meter, sekunden, hr=None):
    return {"d": meter / 1000, "t": sekunden, "hr": hr}


def test_der_echte_fall_wird_abgelehnt():
    einwand = paar_plausibel(473, 239, 400, 200)
    assert einwand is not None
    assert "nicht schneller" in einwand
    assert "Erholung" in einwand, "und woran es meist liegt"


def test_ein_sauberer_test_geht_durch():
    assert paar_plausibel(473, 224, 400, 200) is None
    # 2 x 118,25 − 112 = 124,5 s
    assert css_from_times(473, 224, 400, 200) == pytest.approx(124.5)


def test_die_css_ist_langsamer_als_die_lange_strecke():
    """Die Gegenprobe zur Formel: sonst stimmt etwas nicht."""
    css = css_from_times(473, 224, 400, 200)
    assert css > pace_je_100m(400, 473)


@pytest.mark.parametrize("t_lang, t_kurz, stichwort", [
    (3, 239, "unmöglich schnell"),          # 600 m in 3 s, echtes Artefakt
    (473, 5, "unmöglich schnell"),
    (2000, 239, "unplausibel langsam"),
])
def test_unsinnige_zeiten_werden_erkannt(t_lang, t_kurz, stichwort):
    assert stichwort in paar_plausibel(t_lang, t_kurz, 400, 200)


def test_erkennung_liefert_den_grund_statt_stillzuschweigen():
    """Sonst sucht der Athlet den Fehler bei der App statt beim Test."""
    einheit = _Einheit([_lap(400, 473, hr=153), _lap(200, 239, hr=173)])
    treffer = detect_from_session(einheit)
    assert treffer is not None
    assert "einwand" in treffer
    assert "css_pace_s_per_100m" not in treffer


def test_erkennung_nimmt_nicht_ersatzweise_das_kuerzere_paar():
    """Das läge ebenso daneben, nur unauffälliger."""
    # Durchgehend langsamer, je kürzer die Strecke — kein Paar trägt.
    einheit = _Einheit([
        _lap(400, 473),   # 1:58/100m
        _lap(200, 239),   # 2:00/100m
        _lap(100, 121),   # 2:01/100m
        _lap(50, 63),     # 2:06/100m
    ])
    treffer = detect_from_session(einheit)
    assert "css_pace_s_per_100m" not in treffer


def test_der_endpunkt_lehnt_ab(client, db):
    from models import AthleteProfile

    profil = db.query(AthleteProfile).first()
    vorher = profil.css_pace_s_per_100m
    try:
        antwort = client.post("/api/profile/swim-test",
                              json={"t400_s": 473, "t200_s": 239})
        assert antwort.status_code == 422
        assert "nicht schneller" in antwort.json()["detail"]
        db.expire_all()
        assert db.query(AthleteProfile).first().css_pace_s_per_100m == vorher
    finally:
        profil.css_pace_s_per_100m = vorher
        db.commit()


@pytest.mark.parametrize("sekunden, erwartet", [
    (119.5, "2:00/100m"),      # war "1:60/100m"
    (119.4, "1:59/100m"),
    (59.6, "1:00/100m"),
])
def test_pace_wird_als_ganzes_gerundet(sekunden, erwartet):
    """Minuten aus der ungerundeten Zahl und Sekunden aus dem gerundeten
    Rest ergaben Ausgaben wie "1:60"."""
    assert format_pace(sekunden) == erwartet
