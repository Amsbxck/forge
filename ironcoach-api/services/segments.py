"""Schnellste zusammenhängende Abschnitte einer Laufeinheit.

Warum das nötig ist: die Durchschnitts-Pace einer Einheit sagt fast nichts
über den Hauptteil. Ein Lauf mit 1 km Einlaufen, 3 km Renntempo und 1 km
Auslaufen zeigt im Schnitt 5:11/km, obwohl der Hauptteil in 4:30 gelaufen
wurde. Verglichen mit einer Ziel-Pace für den Hauptteil sähe das nach
Rückstand aus, obwohl es das Gegenteil war.

Grundlage ist der gespeicherte Geschwindigkeits-Stream. Er ist gesampelt
(jeder 10. Messpunkt), die rekonstruierte Distanz weicht dadurch um etwa
ein Prozent ab — für den Vergleich mit einem Pace-Band ist das unerheblich.
"""

import logging

logger = logging.getLogger(__name__)

# Abschnittslängen, die im Training tatsächlich vorkommen.
DEFAULT_SPLITS_KM = (1, 3, 5, 10)


def _sample_seconds(speed_kmh: list, duration_min: int | None) -> float:
    """Zeit pro Messpunkt. Aus der Einheitendauer abgeleitet, weil der
    Stream selbst kein Zeitraster mitliefert."""
    if not speed_kmh or not duration_min:
        return 10.0
    return (duration_min * 60) / len(speed_kmh)


def best_split(speed_kmh: list, distance_km: float, sample_seconds: float) -> dict | None:
    """Schnellster zusammenhängender Abschnitt über die gegebene Distanz.

    Zwei-Zeiger-Verfahren über die kumulierte Distanz: für jeden Startpunkt
    wird das Fenster so weit geöffnet, bis die Distanz erreicht ist, und die
    kürzeste dabei gefundene Zeit gewinnt.
    """
    if not speed_kmh or distance_km <= 0:
        return None

    target_m = distance_km * 1000
    # Meter pro Messpunkt
    steps = [max(0.0, v) / 3.6 * sample_seconds for v in speed_kmh]
    total = sum(steps)
    if total < target_m:
        return None

    best_seconds = None
    start = 0
    covered = 0.0
    for end, step in enumerate(steps):
        covered += step
        while covered >= target_m and start <= end:
            seconds = (end - start + 1) * sample_seconds
            if best_seconds is None or seconds < best_seconds:
                best_seconds = seconds
            covered -= steps[start]
            start += 1

    if best_seconds is None:
        return None
    pace = best_seconds / distance_km
    return {
        "distance_km": distance_km,
        "seconds": round(best_seconds),
        "pace_s_per_km": round(pace),
    }


def best_splits(session, splits_km=DEFAULT_SPLITS_KM) -> list[dict]:
    """Alle sinnvollen Abschnitte einer Einheit. Leer, wenn keine Daten."""
    if (session.discipline or "").lower() not in ("run", "brick"):
        return []
    speed = (session.streams or {}).get("speed") or []
    if not speed:
        return []

    sample_seconds = _sample_seconds(speed, session.duration_min)
    results = []
    for km in splits_km:
        if session.distance_km and km > session.distance_km:
            continue
        split = best_split(speed, km, sample_seconds)
        if split:
            results.append(split)
    return results


def format_pace(seconds_per_km: float | int | None) -> str | None:
    if not seconds_per_km:
        return None
    total = int(round(seconds_per_km))
    return f"{total // 60}:{total % 60:02d}"


# --- Struktur aus Runden ------------------------------------------------------
# Eine Runde gilt als Teil des Hauptteils, wenn sie deutlich schneller ist als
# der Rest und lang genug, um kein Wendepunkt oder keine Pause zu sein.
MAIN_PACE_TOLERANCE = 1.20   # bis 20 % langsamer als die schnellste Runde
MIN_MAIN_DISTANCE_KM = 0.4
# Rad: eine Runde gehört zum Hauptteil, wenn sie mindestens diesen Anteil der
# stärksten Runde erreicht. 0.85 trennt Intervalle (200-215 W) zuverlässig von
# Erholungen (130-140 W), ohne einen leicht schwächeren Block auszuschließen.
MAIN_POWER_SHARE = 0.85
MIN_MAIN_SECONDS = 180
# Runden unter 100 m sind Artefakte: ein Stopp an der Ampel, ein Rundentaster
# kurz vor Schluss. Sie dürfen kein "Auslaufen" vortäuschen.
MIN_SEGMENT_KM = 0.1
# Deckt der Hauptteil fast die ganze Einheit ab und gibt es keine Pausen,
# war es ein Dauerlauf — dann ist eine Aufteilung eine Erfindung.
STEADY_RUN_MAIN_SHARE = 0.85


def _lap_pace(lap: dict) -> float | None:
    if not lap.get("d") or not lap.get("t"):
        return None
    return lap["t"] / lap["d"]


def _lap_intensity(lap: dict, discipline: str) -> float | None:
    """Härte einer Runde, höher = anstrengender.

    Beim Rad die Leistung, beim Laufen die Geschwindigkeit. Eine gemeinsame
    Skala erlaubt dieselbe Erkennungslogik für beide Sportarten.
    """
    if discipline == "bike":
        return float(lap["w"]) if lap.get("w") else None
    if lap.get("d") and lap.get("t"):
        return lap["d"] / lap["t"]  # km pro Sekunde
    return None


def _aggregate(laps: list[dict]) -> dict | None:
    laps = [lap for lap in laps if lap.get("d") and lap.get("t")]
    if not laps:
        return None
    distance = sum(lap["d"] for lap in laps)
    seconds = sum(lap["t"] for lap in laps)
    hrs = [lap["hr"] for lap in laps if lap.get("hr")]
    # Leistung zeitgewichtet: ein 15-Minuten-Block zählt mehr als eine
    # 3-Minuten-Erholung, ein einfacher Mittelwert würde ihn verwässern.
    watt_laps = [lap for lap in laps if lap.get("w")]
    avg_watts = None
    if watt_laps:
        weighted = sum(lap["w"] * lap["t"] for lap in watt_laps)
        avg_watts = round(weighted / sum(lap["t"] for lap in watt_laps))
    return {
        "distance_km": round(distance, 2),
        "seconds": seconds,
        "pace_s_per_km": round(seconds / distance) if distance else None,
        "avg_hr": round(sum(hrs) / len(hrs)) if hrs else None,
        "avg_watts": avg_watts,
        "laps": len(laps),
    }


def structure_from_laps(session) -> dict | None:
    """Einheit in Einlaufen, Hauptteil, Pausen und Auslaufen zerlegen.

    Grundlage sind die Runden der Uhr, nicht der Plantext: dessen Struktur
    ("1km Einlaufen — 3km Race Pace — 1km Cool Down") ließe sich zwar lesen,
    wäre aber eine Annahme darüber, was tatsächlich gelaufen wurde. Die
    Runden sind die Wahrheit.
    """
    laps = (session.streams or {}).get("laps") or []
    if len(laps) < 3:
        return None

    discipline = (session.discipline or "").lower()
    intensities = [(i, _lap_intensity(lap, discipline)) for i, lap in enumerate(laps)]
    valid = [(i, v) for i, v in intensities if v]
    if not valid:
        return None

    hardest = max(v for _, v in valid)
    # Beim Rad reicht ein Anteil der Spitzenleistung, beim Laufen der
    # Kehrwert der Pace-Toleranz — beide bedeuten "nicht wesentlich lockerer
    # als der härteste Abschnitt".
    share = MAIN_POWER_SHARE if discipline == "bike" else (1 / MAIN_PACE_TOLERANCE)

    def _long_enough(lap: dict) -> bool:
        if discipline == "bike":
            return (lap.get("t") or 0) >= MIN_MAIN_SECONDS
        return (lap.get("d") or 0) >= MIN_MAIN_DISTANCE_KM

    main_idx = [i for i, v in valid if v >= hardest * share and _long_enough(laps[i])]
    if not main_idx:
        return None

    first, last = min(main_idx), max(main_idx)
    warmup = laps[:first]
    cooldown = laps[last + 1:]
    main = [laps[i] for i in main_idx]
    recoveries = [laps[i] for i in range(first, last + 1) if i not in main_idx]

    def _significant(part: dict | None) -> dict | None:
        if part and part["distance_km"] >= MIN_SEGMENT_KM:
            return part
        return None

    result = {
        "warmup": _significant(_aggregate(warmup)),
        "main": _aggregate(main),
        "recovery": _significant(_aggregate(recoveries)),
        "cooldown": _significant(_aggregate(cooldown)),
        "main_laps": len(main_idx),
    }

    # Ohne erkennbares Ein- oder Auslaufen ist es ein Dauerlauf — dann sagt
    # die Aufteilung nichts und wird weggelassen.
    if not result["warmup"] and not result["cooldown"]:
        return None

    # Auch mit etwas Vor- oder Nachlauf: wenn der "Hauptteil" fast alles ist
    # und keine Pausen darin liegen, war es ein durchgehender Lauf.
    total = sum(lap["d"] for lap in laps if lap.get("d"))
    main_share = (result["main"]["distance_km"] / total) if total and result["main"] else 0
    if main_share >= STEADY_RUN_MAIN_SHARE and not result["recovery"]:
        return None

    return result


# --- Intervalle ohne Runden ---------------------------------------------------
# Fällt die Lap-Taste aus (outdoor vergessen, Auto-Lap nach Distanz), lässt
# sich die Struktur trotzdem aus der Leistungskurve lesen. Kurze Einbrüche —
# Ampel, Kurve, Schaltvorgang — dürfen einen Block nicht zerreißen.
BLOCK_TOLERANCE = 0.95        # Anteil des Zielbandes, ab dem ein Punkt zählt
BLOCK_MIN_SECONDS = 180
BLOCK_MAX_GAP_SECONDS = 40


def power_blocks(
    session,
    threshold_w: float,
    min_seconds: int = BLOCK_MIN_SECONDS,
    max_gap_seconds: int = BLOCK_MAX_GAP_SECONDS,
) -> list[dict]:
    """Zusammenhängende Belastungsblöcke aus dem Leistungsstrom."""
    watts = (session.streams or {}).get("watts") or []
    if not watts or not threshold_w:
        return []

    sample_seconds = _sample_seconds(watts, session.duration_min)
    max_gap_samples = max(1, int(round(max_gap_seconds / sample_seconds)))

    blocks: list[dict] = []
    current: list[float] = []
    gap = 0

    def _close():
        nonlocal current
        if current:
            seconds = len(current) * sample_seconds
            if seconds >= min_seconds:
                blocks.append({
                    "seconds": int(round(seconds)),
                    "avg_watts": round(sum(current) / len(current)),
                })
        current = []

    for value in watts:
        if value >= threshold_w:
            current.append(value)
            gap = 0
        elif current:
            gap += 1
            if gap > max_gap_samples:
                _close()
                gap = 0
            else:
                current.append(value)  # kurzer Einbruch bleibt Teil des Blocks
    _close()
    return blocks


def structure_from_power(session, threshold_w: float) -> dict | None:
    """Ersatz für die Rundenstruktur, wenn keine Runden vorliegen."""
    blocks = power_blocks(session, threshold_w)
    if not blocks:
        return None
    seconds = sum(b["seconds"] for b in blocks)
    weighted = sum(b["avg_watts"] * b["seconds"] for b in blocks)
    return {
        "main": {
            "seconds": seconds,
            "avg_watts": round(weighted / seconds),
            "laps": len(blocks),
            "distance_km": 0,
            "pace_s_per_km": None,
            "avg_hr": None,
        },
        "source": "power",
    }


def best_effort_power(session, seconds: int = 1200) -> dict | None:
    """Höchste Durchschnittsleistung über ein Zeitfenster.

    Grundlage jedes FTP-Tests: die besten 20 Minuten einer Einheit, egal wo
    sie liegen. Ein gleitendes Fenster findet sie auch dann, wenn der Test
    nicht sauber als eigene Runde aufgezeichnet wurde.
    """
    watts = (session.streams or {}).get("watts") or []
    if not watts:
        return None
    sample_seconds = _sample_seconds(watts, session.duration_min)
    window = max(1, int(round(seconds / sample_seconds)))
    if len(watts) < window:
        return None

    running = sum(watts[:window])
    best = running
    for i in range(window, len(watts)):
        running += watts[i] - watts[i - window]
        if running > best:
            best = running
    return {
        "seconds": int(window * sample_seconds),
        "avg_watts": round(best / window),
    }


def best_effort_pace(session, seconds: int = 1200) -> dict | None:
    """Schnellste Durchschnittspace über ein Zeitfenster."""
    speed = (session.streams or {}).get("speed") or []
    if not speed:
        return None
    sample_seconds = _sample_seconds(speed, session.duration_min)
    window = max(1, int(round(seconds / sample_seconds)))
    if len(speed) < window:
        return None

    # Über die Distanz maximieren: in gleicher Zeit weiter = schneller.
    running = sum(speed[:window])
    best = running
    for i in range(window, len(speed)):
        running += speed[i] - speed[i - window]
        if running > best:
            best = running

    avg_kmh = best / window
    if avg_kmh <= 0:
        return None
    return {
        "seconds": int(window * sample_seconds),
        "avg_kmh": round(avg_kmh, 2),
        "pace_s_per_km": round(3600 / avg_kmh),
    }


def time_in_band(session, low_w: float, high_w: float | None = None) -> int | None:
    """Minuten innerhalb des vorgegebenen Wattbandes.

    Eine einzige Zahl, die beantwortet, ob die Vorgabe umgesetzt wurde —
    unabhängig davon, wie die Einheit strukturiert aufgezeichnet wurde.
    """
    watts = (session.streams or {}).get("watts") or []
    if not watts or not low_w:
        return None
    sample_seconds = _sample_seconds(watts, session.duration_min)
    high = high_w or float("inf")
    count = sum(1 for w in watts if low_w <= w <= high)
    return int(round(count * sample_seconds / 60))


def reference_split(session) -> dict | None:
    """Der Abschnitt, der den Hauptteil am ehesten abbildet.

    3 km, wenn die Einheit lang genug war, sonst 1 km. Bewusst nicht der
    schnellste Kilometer bei langen Läufen: ein einzelner schneller
    Kilometer ist kein Hauptteil.
    """
    splits = {s["distance_km"]: s for s in best_splits(session, (1, 3))}
    return splits.get(3) or splits.get(1)
