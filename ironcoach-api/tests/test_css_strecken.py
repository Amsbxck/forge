"""CSS aus verschiedenen Streckenpaaren.

Die Formel verlangt keine festen 400/200 m, nur eine Differenz:

    CSS = (t_lang − t_kurz) / ((d_lang − d_kurz) / 100)

Die kürzeren Paare sind für alle gedacht, die 400 m nicht am Stück maximal
schwimmen können — dort entsteht sonst keine Messung, sondern eine
Einbruchskurve. Der Preis ist Genauigkeit, und der muss sichtbar sein.
"""

import pytest

from services.swim_css import PAARE, css_from_times, detect_from_session, guete


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
    assert treffer["guete"] is None, "400/200 braucht keinen Vorbehalt"


def test_erkennung_weicht_auf_kuerzere_paare_aus():
    einheit = _Einheit([_lap(200, 155, hr=170), _lap(100, 73)])
    treffer = detect_from_session(einheit)
    assert (treffer["d_lang_m"], treffer["d_kurz_m"]) == (200, 100)
    assert "200/100" in treffer["guete"]


def test_kurzestes_paar_traegt_den_deutlichsten_vorbehalt():
    einheit = _Einheit([_lap(100, 73, hr=175), _lap(50, 35)])
    treffer = detect_from_session(einheit)
    assert (treffer["d_lang_m"], treffer["d_kurz_m"]) == (100, 50)
    assert "gröbste" in treffer["guete"]
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
    assert guete(400) is None and guete(200) and guete(100)
