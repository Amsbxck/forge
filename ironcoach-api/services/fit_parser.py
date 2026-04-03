import os
from datetime import date
from fitparse import FitFile
from services.tss_calculator import calculate_np, calculate_tss, calculate_run_tss


def calculate_hr_zones(hr_data: list, zones: dict | None = None) -> dict:
    """Berechnet % Zeit in Z1-Z5."""
    if zones is None:
        zones = {"z1_max": 138, "z2_max": 173, "z3_max": 189, "z4_max": 210}
    counts = {"z1": 0, "z2": 0, "z3": 0, "z4": 0, "z5": 0}
    for hr in hr_data:
        if hr <= zones["z1_max"]:
            counts["z1"] += 1
        elif hr <= zones["z2_max"]:
            counts["z2"] += 1
        elif hr <= zones["z3_max"]:
            counts["z3"] += 1
        elif hr <= zones["z4_max"]:
            counts["z4"] += 1
        else:
            counts["z5"] += 1
    total = len(hr_data)
    if not total:
        return counts
    return {k: round(v / total * 100, 1) for k, v in counts.items()}


def sample_stream(data: list, interval: int = 10) -> list:
    """Samplet eine Zeitreihe auf jeden N-ten Wert (für Charts)."""
    return [data[i] for i in range(0, len(data), interval)]


def parse_fit_file(file_path: str, ftp: int = 238, max_hr: int | None = None) -> dict:
    """
    Parst Garmin/Wahoo FIT Datei.
    Extrahiert: Dauer, Distanz, HR, Watt, Pace, TSS, HR-Zonen
    """
    fitfile = FitFile(file_path)
    hr_data, power_data, speed_data = [], [], []
    timestamps = []
    total_distance_m = 0.0
    session_date = None
    discipline = "bike"

    # Swim-spezifische Felder
    swim_active_time_sec = None
    swim_pool_length_m = None
    swim_num_lengths = 0
    swim_avg_swolf = None
    swim_lap_times = []  # reine Schwimmzeiten pro Bahn (ohne Pausen)

    for record in fitfile.get_messages("record"):
        data = {f.name: f.value for f in record if f.value is not None}
        if "heart_rate" in data:
            hr_data.append(data["heart_rate"])
        if "power" in data:
            power_data.append(data["power"])
        if "enhanced_speed" in data:
            speed_data.append(data["enhanced_speed"])
        elif "speed" in data:
            speed_data.append(data["speed"])
        if "timestamp" in data:
            timestamps.append(data["timestamp"])
        if "distance" in data:
            total_distance_m = max(total_distance_m, data["distance"])

    for session_msg in fitfile.get_messages("session"):
        data = {f.name: f.value for f in session_msg if f.value is not None}
        if "sport" in data:
            sport = str(data["sport"]).lower()
            if "cycling" in sport or "bike" in sport or "virtual" in sport:
                discipline = "bike"
            elif "running" in sport or "run" in sport:
                discipline = "run"
            elif "swimming" in sport or "swim" in sport or "open_water" in sport:
                discipline = "swim"
        if "start_time" in data and data["start_time"]:
            try:
                session_date = data["start_time"].date()
            except Exception:
                pass
        if "total_distance" in data and data["total_distance"]:
            total_distance_m = data["total_distance"]
        # Swim aktive Zeit (ohne Pausen)
        if "total_timer_time" in data and data["total_timer_time"]:
            swim_active_time_sec = data["total_timer_time"]
        if "pool_length" in data and data["pool_length"]:
            swim_pool_length_m = data["pool_length"]
        if "num_lengths" in data and data["num_lengths"]:
            swim_num_lengths = data["num_lengths"]
        if "avg_swolf_score" in data and data["avg_swolf_score"]:
            swim_avg_swolf = data["avg_swolf_score"]

    # Lap Messages: nur aktive Schwimmbahnen (kein Rest)
    for lap_msg in fitfile.get_messages("length"):
        data = {f.name: f.value for f in lap_msg if f.value is not None}
        length_type = str(data.get("length_type", "")).lower()
        if "active" in length_type and "total_elapsed_time" in data:
            swim_lap_times.append(data["total_elapsed_time"])

    if session_date is None:
        session_date = date.today()

    duration_sec = len(timestamps) if timestamps else 0
    duration_min = round(duration_sec / 60) if duration_sec else None

    avg_hr = round(sum(hr_data) / len(hr_data)) if hr_data else None
    max_hr = max(hr_data) if hr_data else None
    avg_watts = round(sum(power_data) / len(power_data)) if power_data else None
    np = calculate_np(power_data) if power_data else None
    if power_data:
        tss = calculate_tss(power_data, ftp, duration_sec)
    elif discipline in ("run", "swim") and avg_hr and duration_min:
        threshold_hr = int((max_hr or 190) * 0.88)
        tss = calculate_run_tss(duration_min, avg_hr, threshold_hr)
    else:
        tss = None

    distance_km = round(total_distance_m / 1000, 2) if total_distance_m else None

    avg_pace_min_km = None
    if speed_data and discipline == "run":
        avg_speed_ms = sum(speed_data) / len(speed_data)
        if avg_speed_ms > 0:
            avg_pace_min_km = round(1000 / avg_speed_ms / 60, 2)

    hr_zones = calculate_hr_zones(hr_data) if hr_data else None

    # Swim Pace (min/100m) — nur reine Schwimmzeit (Bahnen ohne Pausen)
    swim_pace_per_100m = None
    if discipline == "swim" and total_distance_m > 0:
        if swim_lap_times and swim_pool_length_m:
            # Summe aller aktiven Bahnzeiten = echte Schwimmzeit
            pure_swim_sec = sum(swim_lap_times)
            swim_pace_per_100m = round((pure_swim_sec / total_distance_m) * 100 / 60, 2)
        elif swim_active_time_sec:
            # Fallback: aktive Zeit aus Session
            swim_pace_per_100m = round((swim_active_time_sec / total_distance_m) * 100 / 60, 2)

    streams = {}
    if hr_data:
        streams["hr"] = sample_stream(hr_data)
    if power_data:
        streams["watts"] = sample_stream(power_data)
    if speed_data:
        if discipline == "run":
            pace_stream = [round(1000 / s / 60, 2) if s > 0 else None for s in speed_data]
            streams["pace"] = sample_stream(pace_stream)
        elif discipline != "swim":
            speed_kmh = [round(s * 3.6, 1) if s else None for s in speed_data]
            streams["speed"] = sample_stream(speed_kmh)
    if discipline == "swim" and swim_num_lengths and swim_pool_length_m:
        pure_swim_sec = sum(swim_lap_times) if swim_lap_times else swim_active_time_sec
        streams["swim_info"] = {
            "pool_length_m": swim_pool_length_m,
            "num_lengths": swim_num_lengths,
            "pure_swim_sec": round(pure_swim_sec) if pure_swim_sec else None,
            "pace_per_100m": swim_pace_per_100m,
            "avg_swolf": swim_avg_swolf,
        }

    return {
        "session_date": session_date,
        "discipline": discipline,
        "duration_min": duration_min,
        "distance_km": distance_km,
        "avg_hr": avg_hr,
        "max_hr": max_hr,
        "avg_watts": avg_watts,
        "normalized_power": round(np) if np else None,
        "avg_pace_min_km": swim_pace_per_100m if discipline == "swim" else avg_pace_min_km,
        "tss": round(tss, 1) if tss else None,
        "hr_zones": hr_zones,
        "streams": streams if streams else None,
    }


def parse_gpx_file(file_path: str) -> dict:
    """Parst GPX Datei (Fallback wenn kein FIT vorhanden)."""
    import gpxpy

    with open(file_path, "r") as f:
        gpx = gpxpy.parse(f)

    total_distance_m = 0.0
    hr_data = []
    timestamps = []
    session_date = date.today()

    for track in gpx.tracks:
        for segment in track.segments:
            prev_point = None
            for point in segment.points:
                if point.time and not timestamps:
                    session_date = point.time.date()
                if point.time:
                    timestamps.append(point.time)
                if prev_point:
                    total_distance_m += point.distance_2d(prev_point) or 0
                prev_point = point
                for ext in point.extensions:
                    for child in ext:
                        if "hr" in child.tag.lower() and child.text:
                            try:
                                hr_data.append(int(child.text))
                            except ValueError:
                                pass

    duration_sec = 0
    if len(timestamps) >= 2:
        duration_sec = int((timestamps[-1] - timestamps[0]).total_seconds())

    sport = "run"
    for track in gpx.tracks:
        if track.type:
            t = track.type.lower()
            if "cycling" in t or "bike" in t:
                sport = "bike"
            elif "swim" in t or "swimming" in t:
                sport = "swim"

    return {
        "session_date": session_date,
        "discipline": sport,
        "duration_min": round(duration_sec / 60) if duration_sec else None,
        "distance_km": round(total_distance_m / 1000, 2) if total_distance_m else None,
        "avg_hr": round(sum(hr_data) / len(hr_data)) if hr_data else None,
        "max_hr": max(hr_data) if hr_data else None,
        "avg_watts": None,
        "normalized_power": None,
        "avg_pace_min_km": None,
        "tss": None,
        "hr_zones": calculate_hr_zones(hr_data) if hr_data else None,
    }
