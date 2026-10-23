"""Geplante Läufe und Radeinheiten in die Workout-Schreibweise von intervals.icu.

Die Formen stammen aus echten Plänen (lokale Datenbank, Oktober 2026), nicht
nur aus dem Schema: Pace mal langsam–schnell, „langsamer als …", „90 sek",
ausgeschriebene Wiederholungen, Benchmark nur als `struktur`, Watt fallend
beim Ausfahren, Radeinheiten ganz ohne Details.
"""

from types import SimpleNamespace

from services.geplantes_workout import schritte, workouts


def workout_text(einheit):
    """Der Text des einzigen Workouts, None wenn keines."""
    liste = workouts(einheit)
    assert len(liste) <= 1, liste
    return liste[0].text if liste else None


def _lauf(details=None, **felder):
    werte = dict(
        discipline="run", training_type="z2_endurance", duration_min=40,
        target_pace_low_s_per_km=None, target_pace_high_s_per_km=None,
        target_watts_low=None, target_watts_high=None,
        target_hr_zone=None, details=details,
    )
    werte.update(felder)
    return SimpleNamespace(**werte)


TEMPO = {
    "typ": "Tempo-Intervalle auf dem Track",
    "warmup": {"pace": "6:33–7:00/km", "dauer": "1.5 km"},
    "blocks": [
        {"pace": "5:23–5:45/km", "zone": "Z3", "block": "1", "dauer": "1 km"},
        {"pace": "6:33–7:00/km", "zone": "Z1", "block": "Trabpause", "dauer": "90 sec"},
        {"pace": "5:23–5:45/km", "zone": "Z3", "block": "2", "dauer": "1 km"},
        {"pace": "6:33–7:00/km", "zone": "Z1", "block": "Trabpause", "dauer": "90 sec"},
        {"pace": "5:23–5:45/km", "zone": "Z3", "block": "3", "dauer": "1 km"},
        {"pace": "6:33–7:00/km", "zone": "Z1", "block": "Trabpause", "dauer": "90 sec"},
        {"pace": "5:23–5:45/km", "zone": "Z3", "block": "4", "dauer": "1 km"},
    ],
    "cooldown": {"pace": "6:33–7:00/km", "dauer": "1.5 km"},
}


def test_intervalle_werden_zur_wiederholung_ohne_angehaengte_pause():
    text = workout_text(_lauf(TEMPO, training_type="tempo"))
    assert text == (
        "Warmup\n- 1.5km 6:33-7:00/km Pace\n\n"
        "3x\n- 1km 5:23-5:45/km Pace\n- 1m30 6:33-7:00/km Pace\n\n"
        "Main Set\n- 1km 5:23-5:45/km Pace\n\n"
        "Cooldown\n- 1.5km 6:33-7:00/km Pace"
    )


def test_steigerungen_langsamer_als_bleibt_ohne_ziel():
    details = {
        "typ": "Dauerlauf Z2 mit Steigerungen",
        "warmup": {"pace": "langsamer als 7:16/km", "dauer": "1 km"},
        "blocks": [{"pace": "7:16–6:17/km", "zone": "Z2", "block": "1", "dauer": "7 km"}]
        + [b for _ in range(4) for b in (
            {"pace": "4:14–3:55/km", "zone": "Z7", "block": "x", "dauer": "15 sek"},
            {"pace": "langsamer als 7:16/km", "zone": "Z1", "block": "Erholung", "dauer": "90 sek"},
        )],
    }
    text = workout_text(_lauf(details))
    # Pace schnell zuerst, auch wenn der Plan langsam zuerst schreibt.
    assert "- 7km 6:17-7:16/km Pace" in text
    assert "4x\n- 15s 3:55-4:14/km Pace\n- 1m30\n" in text + "\n"
    # „Langsamer als" hat keine schnelle Grenze: kein geratenes Ziel.
    assert "Warmup\n- 1km\n" in text


def test_dauerlauf_nach_gefuehl_fuehrt_nach_pulszone():
    details = {"typ": "Dauerlauf locker", "pace": "nach Gefühl — Puls bleibt unter 176 bpm",
               "dauer": "40 min", "ziel_hr": "146–176 bpm (Z2)"}
    assert workout_text(_lauf(details, target_hr_zone="Z2")) == "Main Set\n- 40m Z2 HR"


def test_dauerlauf_mit_pace_im_text():
    details = {"typ": "Dauerlauf Z2", "pace": "6:09–5:26/km — nach Gefühl", "dauer": "40 min"}
    assert workout_text(_lauf(details)) == "Main Set\n- 40m 5:26-6:09/km Pace"


def test_ohne_details_die_ganze_einheit():
    assert workout_text(_lauf(None, duration_min=60)) == "Main Set\n- 60m"
    mit_pace = _lauf(None, target_pace_low_s_per_km=377, target_pace_high_s_per_km=436)
    assert workout_text(mit_pace) == "Main Set\n- 40m 6:17-7:16/km Pace"


def test_benchmark_aus_struktur():
    details = {"typ": "Benchmark 20-Minuten-Test",
               "struktur": "15 min ein — 20 min maximal gleichmäßig — 10 min aus"}
    assert workout_text(_lauf(details, duration_min=45)) == (
        "Warmup\n- 15m\n\nMain Set\n- 20m\n\nCooldown\n- 10m"
    )


def test_unlesbare_dauer_faellt_auf_die_gesamtdauer_zurueck():
    details = {"blocks": [{"block": "1", "dauer": "bis es weh tut", "pace": "5:00/km"}]}
    einheit = _lauf(details, duration_min=30)
    assert schritte(einheit, details)[0][1].sekunden == 1800


def test_meter_werden_kilometer():
    # In intervals.icu heißt „m" Minuten, nicht Meter.
    details = {"blocks": [{"block": "1", "dauer": "400 m", "pace": "4:00/km"}]}
    assert workout_text(_lauf(details)) == "Main Set\n- 0.4km 4:00/km Pace"


def test_brick_wird_zu_rad_und_lauf_und_ohne_teil_fehlt_er():
    brick = _lauf({"bike": {"workout": "Sweet Spot kurz", "dauer": "60 min", "watt": "200–215 W"},
                   "run": {"typ": "Koppellauf", "dauer": "15 min", "pace": "5:30–5:50/km"}},
                  discipline="brick", duration_min=75)
    rad, lauf = workouts(brick)
    assert (rad.sport, rad.text) == ("Ride", "Main Set\n- 60m 200-215w")
    assert rad.name == "FORGE · Koppel Rad · Sweet Spot kurz"
    assert (lauf.sport, lauf.text) == ("Run", "Main Set\n- 15m 5:30-5:50/km Pace")
    assert lauf.name == "FORGE · Koppel Lauf · Koppellauf"
    # Ohne Laufteil kein Lauf über die ganzen 75 Minuten, und umgekehrt.
    assert [w.sport for w in workouts(_lauf({"bike": {"dauer": "60 min"}}, discipline="brick"))] == ["Ride"]
    assert workouts(_lauf({"bike": {}}, discipline="brick")) == []


def _rad(details=None, **felder):
    return _lauf(details, **{"discipline": "bike", "training_type": "z2_endurance", **felder})


def test_rad_intervalle_in_watt_mit_wiederholung():
    details = {
        "workout": "Sweet Spot 3x10",
        "warmup": {"dauer": "10 min", "watt": "105–143 W"},
        "blocks": [b for _ in range(3) for b in (
            {"block": "Sweet Spot", "dauer": "10 min", "watt": "232–248 W", "rpm": "85–95"},
            {"block": "Erholung", "dauer": "3 min", "watt": "120–140 W"},
        )],
        # Fallend beim Ausfahren: ein Bereich, keine Rampe.
        "cooldown": {"dauer": "10 min", "watt": "130-110 W"},
    }
    (w,) = workouts(_rad(details, duration_min=69))
    assert w.sport == "Ride" and w.name == "FORGE · Sweet Spot 3x10"
    assert w.text == (
        "Warmup\n- 10m 105-143w\n\n"
        "3x\n- 10m 232-248w\n- 3m 120-140w\n\n"
        "Cooldown\n- 10m 110-130w"
    )


def test_rad_ohne_details_mit_zielwatt_der_projektion():
    (w,) = workouts(_rad(None, duration_min=90, target_watts_low=150, target_watts_high=170))
    assert w.text == "Main Set\n- 90m 150-170w"
    assert w.name == "FORGE · Z2 Endurance"


def test_lockeres_rad_ganz_ohne_watt_bekommt_die_zone_aus_der_ftp():
    # Wahoo nimmt Workouts ohne Ziel nicht an. Z2 bei 160 W FTP: 88–121 W,
    # wie die Zonentabelle (`zones._rad_watt`).
    (w,) = workouts(_rad(None, duration_min=75), ftp=160)
    assert w.text == "Main Set\n- 75m 88-121w"
    # Ohne FTP kein geratenes Ziel, und bei harten Typen auch mit FTP nicht.
    assert workouts(_rad(None, duration_min=75))[0].text == "Main Set\n- 75m"
    assert workouts(_rad(None, training_type="threshold"), ftp=160)[0].text == "Main Set\n- 40m"


def test_rad_ohne_watt_bleibt_ohne_ziel_statt_puls():
    # „So hoch wie gleichmäßig durchhaltbar" hat keine Zahl. Puls als Ersatz
    # gäbe es beim Rad nicht: Das Ziel ist Leistung, oder keins.
    details = {"typ": "Benchmark FTP-Test",
               "struktur": "15 min ein — 20 min so hoch wie gleichmäßig durchhaltbar — 10 min aus"}
    (w,) = workouts(_rad(details, duration_min=45, target_hr_zone="Z4"))
    assert w.text == "Warmup\n- 15m\n\nMain Set\n- 20m\n\nCooldown\n- 10m"


def test_rad_dauer_mit_ca_und_spanne():
    (w,) = workouts(_rad({"typ": "Lange Ausfahrt", "dauer": "ca. 180 min", "watt": "140–165 W"}))
    assert w.text == "Main Set\n- 180m 140-165w"
    (w,) = workouts(_rad({"typ": "Locker", "dauer": "15–20 min"}, duration_min=20))
    # „15–20 min": die Zahl mit der Einheit, also die obere. Das ist auch die
    # Dauer, mit der die Projektion die Einheit führt.
    assert w.text == "Main Set\n- 20m"


def test_schwimmen_wird_kein_workout():
    assert workouts(_lauf({"dauer": "45 min"}, discipline="swim")) == []


def test_wettkampf_wird_kein_workout():
    details = {"typ": "Wettkampf", "pace": "Renntempo nach Gefühl"}
    assert workout_text(_lauf(details, training_type="race_pace", duration_min=110)) is None
    assert workouts(_rad({"workout": "Wettkampf Radsplit", "dauer": "150 min"})) == []
