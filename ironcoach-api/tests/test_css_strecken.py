"""CSS aus verschiedenen Streckenpaaren.

Die Formel verlangt keine festen 400/200 m, nur eine Differenz:

    CSS = (t_lang − t_kurz) / ((d_lang − d_kurz) / 100)

Die kürzeren Paare sind für alle gedacht, die 400 m nicht am Stück maximal
schwimmen können — dort entsteht sonst keine Messung, sondern eine
Einbruchskurve. Der Preis ist Genauigkeit, und der muss sichtbar sein.
"""

import pytest

from services.swim_css import (
    MIN_DAUER_KURZ_S, MIN_DAUER_LANG_S, PAARE, css_from_times,
    detect_from_session, guete,
)


class _Einheit:
    def __init__(self, laps):
        self.streams = {"laps": laps}
        self.id = 1
        self.session_date = __import__("datetime").date(2026, 9, 20)


def _lap(meter, sekunden, hr=None):
    return {"d": meter / 1000, "t": sekunden, "hr": hr}


@pytest.mark.parametrize("d_lang, d_kurz, t_lang, t_kurz, erwartet", [
    (400, 200, 330, 155, 87.5),    # (330-155) / 2
    (200, 100, 155, 73, 82.0),     # (155-73)  / 1
    (100, 50, 73, 35, 76.0),       # (73-35)   / 0.5
])
def test_formel_je_streckenpaar(d_lang, d_kurz, t_lang, t_kurz, erwartet):
    assert css_from_times(t_lang, t_kurz, d_lang, d_kurz) == erwartet


def test_alte_signatur_rechnet_weiter_mit_400_200():
    """Aufrufer, die nur zwei Zeiten übergeben, dürfen nicht kaputtgehen."""
    assert css_from_times(330, 155) == 87.5


@pytest.mark.parametrize("d_lang, d_kurz", [(200, 400), (100, 100)])
def test_unsinnige_paare_ergeben_nichts(d_lang, d_kurz):
    assert css_from_times(330, 155, d_lang, d_kurz) is None


def test_vertauschte_zeiten_werden_abgelehnt():
    assert css_from_times(155, 330, 400, 200) is None


def test_erkennung_nimmt_das_laengste_passende_paar():
    """Wer alle drei Strecken geschwommen ist, bekommt das beste Protokoll."""
    einheit = _Einheit([_lap(400, 330, hr=168), _lap(200, 155), _lap(100, 73), _lap(50, 35)])
    treffer = detect_from_session(einheit)
    assert (treffer["d_lang_m"], treffer["d_kurz_m"]) == (400, 200)
    assert treffer["css_pace_s_per_100m"] == 87.5
    assert treffer["guete"] is None, "lange Zeiten brauchen keinen Vorbehalt"


def test_erkennung_weicht_auf_kuerzere_paare_aus():
    einheit = _Einheit([_lap(200, 155, hr=170), _lap(100, 73)])
    treffer = detect_from_session(einheit)
    assert (treffer["d_lang_m"], treffer["d_kurz_m"]) == (200, 100)
    assert treffer["guete"] is None, "2:35 und 1:13 liegen im gültigen Bereich"


def test_kurzestes_paar_traegt_den_deutlichsten_vorbehalt():
    einheit = _Einheit([_lap(100, 73, hr=175), _lap(50, 35)])
    treffer = detect_from_session(einheit)
    assert (treffer["d_lang_m"], treffer["d_kurz_m"]) == (100, 50)
    assert "kurz" in treffer["guete"], "1:13 und 0:35 sind zu kurz für das Modell"
    # Über 100 m maximal liegt der Puls so weit über der Schwelle, dass der
    # übliche Abschlag ihn nicht einfängt — lieber kein Wert als ein falscher.
    assert treffer["hr_400"] is None


def test_puls_wird_ab_200_m_mitgenommen():
    einheit = _Einheit([_lap(200, 155, hr=170), _lap(100, 73)])
    assert detect_from_session(einheit)["hr_400"] == 170


def test_kuerzere_strecken_ergeben_eine_schnellere_css():
    """Der Grund für den Vorbehalt, in Zahlen.

    Derselbe Schwimmer, drei Protokolle: Je kürzer die Strecken, desto
    grösser der Anteil der anaeroben Startreserve — und desto zu schnell
    fällt die CSS aus.
    """
    lang = css_from_times(330, 155, 400, 200)
    mittel = css_from_times(155, 73, 200, 100)
    kurz = css_from_times(73, 35, 100, 50)
    assert lang > mittel > kurz


def test_endpunkt_lehnt_fremde_paare_ab(client):
    antwort = client.post("/api/profile/swim-test",
                          json={"t400_s": 330, "t200_s": 155, "d_lang_m": 300, "d_kurz_m": 150})
    assert antwort.status_code == 422
    assert "400/200" in antwort.json()["detail"]


def test_endpunkt_speichert_die_strecken(client, db):
    from models import AthleteProfile

    profil = db.query(AthleteProfile).first()
    vorher = (profil.css_pace_s_per_100m, profil.css_dist_lang_m, profil.css_dist_kurz_m)
    try:
        antwort = client.post("/api/profile/swim-test",
                              json={"t400_s": 155, "t200_s": 73, "d_lang_m": 200, "d_kurz_m": 100})
        assert antwort.status_code == 200
        db.expire_all()
        profil = db.query(AthleteProfile).first()
        assert profil.css_pace_s_per_100m == 82.0
        assert (profil.css_dist_lang_m, profil.css_dist_kurz_m) == (200, 100)
    finally:
        profil.css_pace_s_per_100m, profil.css_dist_lang_m, profil.css_dist_kurz_m = vorher
        db.commit()


def test_die_erlaubten_paare_stehen_an_einer_stelle():
    assert PAARE == ((400, 200), (200, 100), (100, 50))


def test_guete_bewertet_die_dauer_nicht_die_strecke():
    """Der Kern der Sache.

    Dieselben 100/50 m sind für einen schnellen Schwimmer zu kurz und für
    einen Anfänger einwandfrei — weil das Modell Belastungen ab etwa zwei
    Minuten voraussetzt, nicht Strecken ab 400 m. Eine Bewertung nach
    Metern hätte genau den gewarnt, für den das kurze Paar gedacht ist.
    """
    # Schnell: 100 m in 1:15, 50 m in 0:35.
    assert guete(75, 35) is not None
    # Anfänger: dieselben Strecken in 2:20 und 1:06.
    assert guete(140, 66) is None


@pytest.mark.parametrize("t_lang, t_kurz, mit_vorbehalt", [
    (MIN_DAUER_LANG_S, MIN_DAUER_KURZ_S, False),          # genau auf der Grenze
    (MIN_DAUER_LANG_S - 1, MIN_DAUER_KURZ_S, True),
    (MIN_DAUER_LANG_S, MIN_DAUER_KURZ_S - 1, True),
])
def test_grenzen_des_gueltigkeitsbereichs(t_lang, t_kurz, mit_vorbehalt):
    assert (guete(t_lang, t_kurz) is not None) is mit_vorbehalt


def test_endpunkt_meldet_den_vorbehalt_mit(client, db):
    from models import AthleteProfile

    profil = db.query(AthleteProfile).first()
    vorher = (profil.css_pace_s_per_100m, profil.css_dist_lang_m, profil.css_dist_kurz_m)
    try:
        # Schneller Schwimmer über 100/50 — zu kurz.
        antwort = client.post("/api/profile/swim-test",
                              json={"t400_s": 75, "t200_s": 35,
                                    "d_lang_m": 100, "d_kurz_m": 50}).json()
        assert antwort["guete"] is not None
        assert "zwei Minuten" in antwort["guete"]
    finally:
        profil.css_pace_s_per_100m, profil.css_dist_lang_m, profil.css_dist_kurz_m = vorher
        db.commit()
