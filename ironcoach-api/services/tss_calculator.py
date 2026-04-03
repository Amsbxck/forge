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


def calculate_tss(power_data: list[int | float], ftp: int, duration_sec: int | None = None) -> float | None:
    """Training Stress Score = (duration_sec * NP * IF) / (FTP * 3600) * 100."""
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


def hrv_status_from_rmssd(rmssd: float) -> str:
    if rmssd > 80:
        return "green"
    elif rmssd >= 70:
        return "yellow"
    else:
        return "red"
