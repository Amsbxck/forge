"""Einheitliche Darstellung einer Trainingseinheit für Prompts.

Bisher wurde der Session-Dict an zwei Stellen getrennt aufgebaut (Chat und
Plangenerierung) und enthielt nur Rohwerte — Dauer, Watt, HF, TSS. Alles,
was die Klassifizierung ermittelt hat, fehlte: erkannter Trainingstyp,
Intensitätsstufe, Struktur, Abweichung vom Plan.

Diese Darstellung ist die Rückfallebene, wenn die Obsidian-Note nicht
gelesen werden kann. Sie soll deshalb dieselbe Aussage tragen, nur knapper.
"""

from models import TrainingSession


def _structure_summary(session: TrainingSession) -> str | None:
    """Hauptteil in einem Satz — der Kern jeder Intervalleinheit."""
    try:
        from services.segments import format_pace, structure_from_laps
    except Exception:  # pragma: no cover
        return None

    structure = structure_from_laps(session)
    main = (structure or {}).get("main")
    if not main:
        return None

    count = main.get("laps") or 1
    minutes = round((main.get("seconds") or 0) / 60)
    if session.discipline == "bike" and main.get("avg_watts"):
        per = round(minutes / count) if count else minutes
        return f"Hauptteil {count}× à ~{per}min @ {main['avg_watts']}W"
    if main.get("pace_s_per_km"):
        return f"Hauptteil {main.get('distance_km')}km @ {format_pace(main['pace_s_per_km'])}/km"
    return None


def session_to_dict(session: TrainingSession) -> dict:
    """Trainingseinheit als Dict für die Prompt-Formatierung."""
    return {
        "session_date": str(session.session_date),
        "discipline": session.discipline,
        # Ohne die Originalbezeichnung stünde im Prompt nur "OTHER" — der
        # Coach wüsste nicht, ob es Rudern, Crosstrainer oder StairMaster war.
        "sport_type": session.sport_type,
        # Woher die Belastungszahl stammt. Eine pulsbasierte Schätzung ist
        # nicht dasselbe wie eine Messung über Leistung, und sie ungekennzeichnet
        # danebenzustellen suggeriert eine Genauigkeit, die es nicht gibt.
        "tss_source": (
            "power" if (session.avg_watts and session.discipline in ("bike", "brick"))
            else "hr" if session.avg_hr else None
        ),
        "duration_min": session.duration_min,
        "distance_km": session.distance_km,
        "avg_hr": session.avg_hr,
        "avg_watts": session.avg_watts,
        "normalized_power": session.normalized_power,
        "avg_pace_min_km": session.avg_pace_min_km,
        "tss": session.tss,
        "hr_zones": session.hr_zones,
        # Ergebnis der Klassifizierung — ohne diese Felder zieht der Coach
        # aus dem Gesamtschnitt falsche Schlüsse.
        "actual_type": session.actual_type,
        "intensity": session.intensity,
        "deviation_note": session.deviation_note,
        "structure": _structure_summary(session),
    }
