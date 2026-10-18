"""Die Normalspanne: Mittelwert ± 0,5 Standardabweichungen.

Die halbe Standardabweichung ist nicht beliebig gewählt — sie ist die
**kleinste bedeutsame Änderung**, also die kleinste Verschiebung, die über das
normale Messrauschen hinausgeht. Innerhalb der Spanne ist ein Unterschied
Zufall; wer darauf reagiert, reagiert auf Rauschen.

Deshalb hat die Spanne zwei Grenzen. Lange gab es nur die untere: Alles darüber
war grün, ob fünf oder fünfzig Prozent über dem Mittel — damit war nicht zu
erkennen, ob ein guter Wert wirklich gut war oder nur innerhalb der Streuung lag.
"""

import statistics
from datetime import date, timedelta

import pytest

from models import HrvMeasurement, User
from services.hrv_baseline import (
    BAND_SIGMA,
    MIN_MESSUNGEN,
    compute_baseline,
    status_for,
    thresholds_for,
    ueber_band,
)


@pytest.fixture
def messreihe(db):
    """Genug Messungen für eine Grundlinie, mit bekannter Streuung."""
    nutzer = db.query(User).order_by(User.id.asc()).first()
    db.query(HrvMeasurement).delete()
    db.commit()
    werte = [70, 75, 80, 85, 90, 72, 78, 82, 88, 74, 76, 84, 86, 79, 81, 83]
    heute = date.today()
    for i, w in enumerate(werte):
        db.add(HrvMeasurement(user_id=nutzer.id, measured_at=heute - timedelta(days=i), rmssd=w))
    db.commit()
    yield nutzer, werte
    db.query(HrvMeasurement).delete()
    db.commit()


# --- Die Spanne --------------------------------------------------------------

def test_die_spanne_ist_mittelwert_plusminus_halbe_streuung(db, messreihe):
    nutzer, werte = messreihe
    grundlinie = compute_baseline(db, nutzer)

    mittel = statistics.fmean(werte)
    streuung = statistics.pstdev(werte)
    assert grundlinie["mean"] == round(mittel, 1)
    assert grundlinie["sd"] == round(streuung, 1)
    assert grundlinie["band_unten"] == round(mittel - 0.5 * streuung, 1)
    assert grundlinie["band_oben"] == round(mittel + 0.5 * streuung, 1)


def test_die_halbe_streuung_ist_die_kleinste_bedeutsame_aenderung():
    assert BAND_SIGMA == 0.5


def test_die_untere_bandgrenze_ist_die_ampelschwelle(db, messreihe):
    """Zwei Namen für eine Zahl — aber nicht zwei Zahlen."""
    nutzer, _ = messreihe
    g = compute_baseline(db, nutzer)
    assert g["gruen_ab"] == g["band_unten"]


def test_die_obere_grenze_kommt_bei_den_grenzen_an(db, messreihe):
    """Sie fehlte: `thresholds_for` gab im automatischen Fall nur
    `gruen_ab` und `rot_unter` zurück, und das Diagramm zeichnete die grüne
    Fläche deshalb bis zum oberen Rand."""
    nutzer, _ = messreihe
    grenzen = thresholds_for(None, compute_baseline(db, nutzer))
    assert grenzen["quelle"] == "auto"
    assert grenzen["gruen_bis"] is not None
    assert grenzen["gruen_bis"] > grenzen["gruen_ab"]


# --- Über der Spanne ---------------------------------------------------------

GRENZEN = {"gruen_ab": 72.0, "gruen_bis": 88.0, "rot_unter": 64.0}


@pytest.mark.parametrize("wert,ueber", [(95, True), (88.1, True), (88, False), (80, False), (60, False)])
def test_ueber_band_erkennt_echte_abweichung(wert, ueber):
    assert ueber_band(wert, GRENZEN) is ueber


def test_ueber_der_spanne_bleibt_gruen():
    """Keine vierte Ampelfarbe: Über der Spanne ist nicht besser als grün, es
    ist grün — nur nachweislich und nicht innerhalb des Rauschens. Ein vierter
    Statuswert hätte jede Stelle berührt, die heute drei kennt."""
    assert status_for(95, GRENZEN) == "green"
    assert ueber_band(95, GRENZEN) is True


def test_ohne_obere_grenze_keine_aussage():
    """Eine von Hand gesetzte Spanne ohne Obergrenze darf nichts behaupten."""
    assert ueber_band(200, {"gruen_ab": 72.0, "rot_unter": 64.0}) is False


def test_zu_wenige_messungen_ergeben_keine_spanne(db):
    """Geraten wäre schlechter als offen zu sagen, dass die Grundlinie noch
    entsteht."""
    nutzer = db.query(User).order_by(User.id.asc()).first()
    db.query(HrvMeasurement).delete()
    db.add(HrvMeasurement(user_id=nutzer.id, measured_at=date.today(), rmssd=80))
    db.commit()

    g = compute_baseline(db, nutzer)
    assert g["status"] == "zu_wenige_daten"
    assert g["benoetigt"] == MIN_MESSUNGEN
    assert thresholds_for(None, g) is None

    db.query(HrvMeasurement).delete()
    db.commit()


# --- Wo die Spanne ankommt ---------------------------------------------------

def test_der_prompt_nennt_die_spanne_und_nutzt_keine_festen_schwellen():
    """Hier stand `"🟢" if h["rmssd"] > 85 else ...` — genau die festen Zahlen,
    die die Normalspanne ersetzt. Der Coach bekam zwei widersprechende Signale
    in derselben Zeile: ein Symbol nach fremden Zahlen und daneben den richtig
    gerechneten Status. Bei einer Normallage um 45 stand dort dauerhaft 🔴
    neben "green".
    """
    from core.prompt_templates import format_hrv

    # Das Verhalten prüfen, nicht den Quelltext: Die alten Schwellen stehen in
    # der Dokumentation der Funktion als Erklärung, und ein Test, der darüber
    # stolpert, prüft den Text statt die Wirkung.
    #
    # Der Fall, in dem alte und neue Regel auseinandergehen: ein Athlet mit
    # einer Normallage um 45. Nach festen Schwellen wäre 45 ms rot (unter 75),
    # gegen die eigene Spanne ist es grün.
    niedrig = {"gruen_ab": 40.0, "gruen_bis": 50.0, "rot_unter": 36.0}
    tief = format_hrv([{"measured_at": "2026-10-10", "rmssd": 45, "hrv_status": "green"}], niedrig)
    assert "🟢" in tief, "die eigene Spanne entscheidet, nicht 75 ms"
    assert "🔴" not in tief

    text = format_hrv(
        [{"measured_at": "2026-10-10", "rmssd": 95, "hrv_status": "green"},
         {"measured_at": "2026-10-09", "rmssd": 68, "hrv_status": "yellow"}],
        GRENZEN,
    )
    assert "Normalspanne dieses Athleten: 72.0–88.0 ms" in text
    assert "Mittelwert ± 0,5 σ" in text
    assert "über der Normalspanne" in text
    assert "🟡" in text


def test_der_prompt_haelt_eine_fehlende_grundlinie_offen():
    from core.prompt_templates import format_hrv

    text = format_hrv([{"measured_at": "2026-10-10", "rmssd": 68, "hrv_status": None}])
    assert "noch keine Grundlinie" in text


def test_neue_messung_zieht_die_grundlinie_nach(client, db, messreihe):
    """Jede neue Messung verschiebt Mittelwert und Streuung, also die Spanne.

    Ohne das Nachziehen trug die neue Messung die heutige Spanne und jede
    ältere die von damals — im Diagramm lägen Punkte in Farben, die zur
    eingezeichneten Spanne nicht passen.
    """
    import inspect

    from routers import hrv

    quelle = inspect.getsource(hrv.create_hrv)
    assert "recompute_all" in quelle

    antwort = client.post("/api/hrv", json={
        "measured_at": str(date.today() + timedelta(days=1)), "rmssd": 81,
    })
    assert antwort.status_code == 200
    assert antwort.json()["hrv_status"] in ("green", "yellow", "red")


# --- Vorrang der eingetragenen Spanne ---------------------------------------

class Eingetragen:
    """Eine Spanne aus der Uhr, wie sie im Profil steht."""

    hrv_range_source = "manual"
    hrv_green_min = 67.0
    hrv_band_high = 98.0
    hrv_red_below = 59.2


GRUNDLINIE_OK = {
    "status": "ok", "messungen": 30, "mean": 77.1, "sd": 12.0,
    "band_unten": 71.1, "band_oben": 83.1, "gruen_ab": 71.1, "rot_unter": 65.1,
}


def test_eingetragene_spanne_schlaegt_die_rechnung():
    """Sie kommt aus der Uhr, die über Monate und mit dem eigenen Messverfahren
    gelernt hat. Die Rechnung hier sieht nur, was in dieser App gelandet ist."""
    grenzen = thresholds_for(Eingetragen(), GRUNDLINIE_OK)
    assert grenzen["quelle"] == "manual"
    assert grenzen["gruen_ab"] == 67.0
    assert grenzen["gruen_bis"] == 98.0


def test_vorrang_gilt_auch_ohne_rote_grenze():
    """Das Loch im Vorrang: Hier wurden **beide** Werte verlangt. Fehlte die
    rote Grenze, fiel die Funktion stillschweigend auf die berechnete Spanne
    zurück — die eingetragene galt dann nicht, ohne dass irgendwo etwas davon
    stand."""
    class OhneRot(Eingetragen):
        hrv_red_below = None

    grenzen = thresholds_for(OhneRot(), GRUNDLINIE_OK)
    assert grenzen["quelle"] == "manual"
    assert grenzen["gruen_ab"] == 67.0
    assert grenzen["rot_unter"] < 67.0, "aus dem Band abgeleitet"


def test_vorrang_gilt_auch_mit_nur_einer_grenze():
    class NurUnten(Eingetragen):
        hrv_band_high = None
        hrv_red_below = None

    grenzen = thresholds_for(NurUnten(), GRUNDLINIE_OK)
    assert grenzen["quelle"] == "manual"
    assert grenzen["gruen_ab"] == 67.0


def test_ohne_eintrag_rechnet_die_app():
    assert thresholds_for(None, GRUNDLINIE_OK)["quelle"] == "auto"


def test_der_prompt_nennt_die_herkunft_statt_sie_zu_erfinden():
    """Eine eingetragene Spanne ist nicht "Mittelwert ± 0,5 σ" — das so zu
    behaupten wäre eine erfundene Begründung für eine Zahl, die jemand von Hand
    gesetzt hat."""
    from core.prompt_templates import format_hrv

    messung = [{"measured_at": "2026-10-10", "rmssd": 80, "hrv_status": "green"}]

    eingetragen = format_hrv(messung, thresholds_for(Eingetragen(), GRUNDLINIE_OK))
    assert "eingetragen" in eingetragen
    assert "Mittelwert ± 0,5 σ" not in eingetragen

    gerechnet = format_hrv(messung, thresholds_for(None, GRUNDLINIE_OK))
    assert "Mittelwert ± 0,5 σ" in gerechnet
