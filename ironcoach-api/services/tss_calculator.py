import math


def calculate_np(power_data: list[int | float]) -> float | None:
    """Normalized Power: 30s rolling average → 4th power → mean → 4th root."""
    if not power_data or len(power_data) < 30:
        return None
    window = 30
    rolling_avgs = []
    for i in range(window - 1, len(power_data)):
        window_mean = sum(power_data[i - window + 1 : i + 1]) / window
        rolling_avgs.append(window_mean ** 4)
    if not rolling_avgs:
        return None
    return (sum(rolling_avgs) / len(rolling_avgs)) ** 0.25


def tss_aus_np(np_watts: float | None, ftp: int | None, duration_min: float | None) -> float | None:
    """TSS aus Normalized Power. Die eine Stelle, an der das gerechnet wird.

    `np_watts` muss eine **echte** NP sein — Stravas `weighted_average_watts`.
    Weder der Wattdurchschnitt noch eine selbst gerechnete NP aus dem
    gespeicherten Strom taugen dafür:

    * Der **Durchschnitt** trägt jedes Rollen und jede Ampel mit und liegt bei
      einer langen Ausfahrt weit unter der NP.
    * Der **gespeicherte Strom** ist heruntergerechnet, bei einer
      320-Minuten-Fahrt ein Wert je zehn Sekunden. Das 30-Werte-Fenster der
      NP-Formel umspannt damit fünf Minuten statt dreissig Sekunden und glättet
      genau die Spitzen weg, um die es bei NP geht.

    Vorher gab es zwei Rechenwege: `tss_neu` nahm Stravas NP, der Import rechnete
    selbst. Die Ausfahrt vom 03.10. bekam dadurch 228 TSS statt 170 — 34 % zu
    hoch, und das in der Formkurve, aus der jede Planung folgt. Deshalb steht es
    jetzt hier und nirgends sonst.
    """
    if not np_watts or not ftp or not duration_min or duration_min <= 0:
        return None
    return round((duration_min / 60) * (np_watts / ftp) ** 2 * 100, 1)


def tss_aus_puls(avg_hr: int | None, threshold_hr: int | None, duration_min: float | None) -> float | None:
    """TSS über die Herzfrequenz — für alles ohne verlässliche Leistungsmessung.

    Gilt auch für Radeinheiten ohne NP: Der Puls ist dort die ehrlichere
    Grundlage als ein Wattdurchschnitt.
    """
    if not avg_hr or not threshold_hr or not duration_min or duration_min <= 0:
        return None
    return round((duration_min / 60) * (avg_hr / threshold_hr) ** 2 * 100, 1)


def calculate_tss(power_data: list[int | float], ftp: int, duration_sec: int | None = None) -> float | None:
    """Training Stress Score aus einem Leistungsstrom.

    Nur noch für Quellen ohne eigene NP — FIT-Uploads etwa. Für Strava gilt
    `tss_aus_np` mit `weighted_average_watts`; die dortige NP ist auf der
    Vollauflösung gerechnet, diese hier auf dem, was gespeichert wurde.
    """
    np = calculate_np(power_data)
    if not np or not ftp:
        return None
    if duration_sec is None:
        duration_sec = len(power_data)
    intensity_factor = np / ftp
    return (duration_sec * np * intensity_factor) / (ftp * 3600) * 100


def calculate_run_tss(duration_min: float, avg_hr: int, threshold_hr: int = 173) -> float:
    """Simplified run TSS based on HR intensity factor."""
    if not avg_hr or not threshold_hr:
        return 0.0
    hr_if = avg_hr / threshold_hr
    return (duration_min / 60) * (hr_if ** 2) * 100


# `hrv_status_from_rmssd` stand hier mit festen Schwellen bei 80 und 70.
# Sie wurde nirgends aufgerufen — bewertet wird über die eigene Normallage
# des Athleten (`hrv_green_min`/`hrv_red_below` im Profil, ausgewertet in
# services/hrv_baseline.py). Feste Schwellen waren genau der Fehler, den
# diese Spannen beheben: Wer sich normal um 45 bewegt, stünde damit
# dauerhaft auf Rot, und der Coach striche dauerhaft Intensität.
#
# Entfernt statt liegengelassen: Eine unbenutzte Funktion, die der gültigen
# Logik widerspricht, ist eine Falle für den Nächsten, der sie findet.
