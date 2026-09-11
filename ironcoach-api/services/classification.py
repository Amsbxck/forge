"""Ist-Daten klassifizieren und gegen den Plan abgleichen.

Bewusst regelbasiert statt per Claude-Aufruf: das Ergebnis muss
reproduzierbar sein, in Tests prüfbar, kostenlos bei 77 Einheiten — und vor
allem darf es nichts erfinden. Ein Sprachmodell würde bei dünner Datenlage
einen plausiblen Trainingstyp halluzinieren; hier bleibt das Feld dann eben
leer, und das ist die ehrlichere Aussage.

Zwei Schritte:
  1. actual_type — was war es wirklich? (aus Leistung, HF, Pace, Dauer)
  2. Matching gegen planned_sessions — war es das, was geplant war?
"""

import logging

from sqlalchemy.orm import Session

from core.training_types import (
    INTENSITY_DISCIPLINES,
    intensity_for_type,
    is_valid_training_type,
)
from models import AthleteProfile, PlannedSession, TrainingSession
from core.deps import get_profile

logger = logging.getLogger(__name__)

# Intensitätsfaktor = NP / FTP. Grenzen nach gängiger Trainingslehre,
# leicht großzügig geschnitten, weil reale Ausfahrten selten sauber in
# eine Schublade fallen.
IF_RECOVERY = 0.56
IF_ENDURANCE = 0.76
IF_SWEET_SPOT = 0.88
IF_THRESHOLD = 0.96

LONG_RIDE_MIN = 180
LONG_RUN_MIN = 75

# Matching
MAX_DATE_DISTANCE_DAYS = 1
MIN_MATCH_CONFIDENCE = 0.5


def _z(hr_zones: dict | None, *keys: str) -> float:
    """Anteil der Zeit in einer oder mehreren HF-Zonen (Prozent)."""
    if not hr_zones:
        return 0.0
    return sum(float(hr_zones.get(k) or 0) for k in keys)


def classify_bike(session: TrainingSession, ftp: int) -> str | None:
    np = session.normalized_power or session.avg_watts
    duration = session.duration_min or 0

    if np and ftp:
        intensity = np / ftp
        if intensity < IF_RECOVERY:
            return "recovery"
        if intensity < IF_ENDURANCE:
            return "long_ride" if duration >= LONG_RIDE_MIN else "z2_endurance"
        if intensity < IF_SWEET_SPOT:
            # Lange Einheit in diesem Band ist eher Renntempo als ein
            # klassischer Sweet-Spot-Block.
            return "race_pace" if duration >= LONG_RIDE_MIN else "sweet_spot"
        if intensity < IF_THRESHOLD:
            return "threshold"
        return "vo2max"

    # Ohne Leistungsmesser über die HF-Verteilung
    zones = session.hr_zones
    if zones:
        if _z(zones, "z4", "z5") >= 15:
            return "threshold"
        if _z(zones, "z3") >= 25:
            return "sweet_spot"
        if _z(zones, "z1") >= 75:
            return "recovery"
        return "long_ride" if duration >= LONG_RIDE_MIN else "z2_endurance"

    return None


def classify_run(session: TrainingSession) -> str | None:
    duration = session.duration_min or 0
    zones = session.hr_zones

    # Walk-Run ist Amirs Standardformat: erkennbar an einem hohen Z1-Anteil
    # mitten in einer Laufeinheit — das sind die Gehpausen.
    if zones and _z(zones, "z1") >= 30 and _z(zones, "z2", "z3") >= 15:
        return "walk_run"

    if zones:
        # Getrennt nach Z5 und Z4, damit VO₂max und Threshold auch beim Lauf
        # auseinandergehalten werden — nicht mehr pauschal "intervals".
        if _z(zones, "z5") >= 5:
            return "vo2max"
        if _z(zones, "z4") >= 10:
            return "threshold"
        if _z(zones, "z3") >= 30:
            return "tempo"
        if _z(zones, "z1") >= 80:
            return "recovery"

    if duration >= LONG_RUN_MIN:
        return "long_run"
    if zones:
        return "z2_endurance"
    return None


def classify_swim(session: TrainingSession) -> str | None:
    # Schwimmdaten sind zu dünn für eine belastbare Aussage (kein Power,
    # HF oft unbrauchbar unter Wasser). Lieber nichts behaupten.
    return None


def classify_actual_type(session: TrainingSession, ftp: int = 238) -> str | None:
    """Trainingstyp aus den Ist-Daten. None, wenn die Daten nichts hergeben."""
    discipline = (session.discipline or "").lower()
    if discipline == "bike":
        return classify_bike(session, ftp)
    if discipline == "run":
        return classify_run(session)
    if discipline == "swim":
        return classify_swim(session)
    if discipline == "brick":
        return "brick"
    if discipline == "gym":
        return "strength"
    if discipline == "hike":
        return "hike"
    if discipline == "rest":
        return "rest"
    return None


# --- Intensitätsstufe --------------------------------------------------------

def intensity_from_session(session: TrainingSession, ftp: int = 238) -> str | None:
    """Intensität aus den Ist-Daten — nur Rad und Lauf.

    Reihenfolge: gemessene Leistung schlägt HF-Verteilung, HF schlägt die
    Ableitung aus dem Trainingstyp. So wird aus geplanten "intervals" die
    Stufe, die tatsächlich gefahren wurde, statt der angenommenen.
    """
    discipline = (session.discipline or "").lower()
    if discipline not in INTENSITY_DISCIPLINES:
        return None

    # Rad mit Leistungsmesser: eindeutig über den Intensitätsfaktor.
    if discipline == "bike":
        np = session.normalized_power or session.avg_watts
        if np and ftp:
            intensity = np / ftp
            if intensity < IF_ENDURANCE:
                return "base"
            if intensity < IF_SWEET_SPOT:
                return "sweet_spot"
            if intensity < IF_THRESHOLD:
                return "threshold"
            return "vo2max"

    # Sonst über die Zeit in den harten Zonen. Die Schwellen sind bewusst
    # niedrig: 5 Minuten echtes Z5 in einer Stunde machen die Einheit zur
    # VO₂max-Einheit, auch wenn der Rest locker war.
    zones = session.hr_zones
    if zones:
        if _z(zones, "z5") >= 5:
            return "vo2max"
        if _z(zones, "z4") >= 10:
            return "threshold"
        if _z(zones, "z3") >= 25:
            return "sweet_spot"
        return "base"

    return intensity_for_type(discipline, session.actual_type)


# --- Matching gegen den Plan -------------------------------------------------

def _duration_similarity(planned_min: int | None, actual_min: int | None) -> float:
    if not planned_min or not actual_min:
        return 0.0
    ratio = min(planned_min, actual_min) / max(planned_min, actual_min)
    return max(0.0, (ratio - 0.5) * 2)  # 50% Abweichung → 0, identisch → 1


def score_match(planned: PlannedSession, session: TrainingSession) -> float:
    """0..1 — wie gut passt eine geplante Einheit zu dieser Ist-Einheit?"""
    score = 0.0
    distance = abs((planned.planned_date - session.session_date).days)

    if planned.discipline == session.discipline:
        score += 0.5
    elif planned.discipline == "brick" and session.discipline in ("bike", "run"):
        # Ein Brick besteht aus beidem und kommt als zwei Aktivitäten an.
        # Aber nur am selben Tag: sonst wird jede lange Ausfahrt dem Brick
        # vom Vortag zugeschlagen, nur weil sonst nichts in der Nähe liegt.
        if distance > 0:
            return 0.0
        score += 0.35

    if distance == 0:
        score += 0.3
    elif distance <= MAX_DATE_DISTANCE_DAYS:
        score += 0.15

    score += 0.2 * _duration_similarity(planned.duration_min, session.duration_min)
    return round(score, 3)


def find_best_planned(db: Session, session: TrainingSession) -> tuple[PlannedSession | None, float]:
    candidates = (
        db.query(PlannedSession)
        .filter(
            PlannedSession.planned_date >= session.session_date - _days(MAX_DATE_DISTANCE_DAYS),
            PlannedSession.planned_date <= session.session_date + _days(MAX_DATE_DISTANCE_DAYS),
            PlannedSession.discipline != "rest",
        )
        .all()
    )
    if not candidates:
        return None, 0.0

    # Für eine Woche können mehrere Pläne existieren (Neugenerierung,
    # Chat-Änderung). Nur die Einheiten des jeweils aktiven Plans zählen,
    # sonst wird gegen eine längst ersetzte Fassung gematcht.
    from services.plan_selection import active_plan_for_week

    active_ids: dict[int, int | None] = {}
    for candidate in candidates:
        if candidate.week_number not in active_ids:
            plan = active_plan_for_week(db, candidate.week_number)
            active_ids[candidate.week_number] = plan.id if plan else None
    candidates = [c for c in candidates if active_ids.get(c.week_number) == c.plan_id]
    if not candidates:
        return None, 0.0

    scored = [(score_match(c, session), c) for c in candidates]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    best_score, best = scored[0]
    if best_score < MIN_MATCH_CONFIDENCE:
        return None, best_score
    return best, best_score


def _days(n: int):
    from datetime import timedelta
    return timedelta(days=n)


def brick_components(db: Session, planned: PlannedSession, session: TrainingSession) -> list:
    """Alle Teilaktivitäten eines Bricks am geplanten Tag.

    Ein Brick kommt als zwei Strava-Aktivitäten an (Rad und Lauf). Jede
    einzeln gegen die Gesamtdauer zu messen ergibt zwei absurde Rückstände,
    obwohl zusammen vielleicht fast alles erledigt wurde.
    """
    return (
        db.query(TrainingSession)
        .filter(
            TrainingSession.session_date == session.session_date,
            TrainingSession.discipline.in_(("bike", "run")),
            TrainingSession.deleted_at == None,  # noqa: E711
        )
        .order_by(TrainingSession.id.asc())
        .all()
    )


def build_deviation_note(
    planned: PlannedSession | None,
    session: TrainingSession,
    actual_type: str | None,
    components: list | None = None,
) -> str | None:
    """Knapper Klartext, was anders lief. None wenn alles im Rahmen war."""
    if planned is None:
        return "Keine geplante Einheit zugeordnet — ungeplantes Training"

    parts: list[str] = []
    is_brick_part = planned.discipline == "brick" and session.discipline in ("bike", "run")

    # Bei einem Brick sagt der Typvergleich nichts: die Radhälfte IST eine
    # Radeinheit und kann gar nicht "brick" sein.
    if (
        not is_brick_part
        and actual_type
        and planned.training_type
        and actual_type != planned.training_type
    ):
        parts.append(f"Typ: geplant {planned.training_type}, tatsächlich {actual_type}")

    if is_brick_part and components and len(components) > 1:
        total = sum(c.duration_min or 0 for c in components)
        breakdown = ", ".join(
            f"{'Rad' if c.discipline == 'bike' else 'Lauf'} {c.duration_min}"
            for c in components if c.duration_min
        )
        if planned.duration_min and total:
            delta = total - planned.duration_min
            if abs(delta) >= max(10, planned.duration_min * 0.15):
                parts.append(
                    f"Brick gesamt: {delta:+d} min ({total} statt {planned.duration_min}; {breakdown})"
                )
    elif planned.duration_min and session.duration_min:
        delta = session.duration_min - planned.duration_min
        if abs(delta) >= max(10, planned.duration_min * 0.15):
            parts.append(f"Dauer: {delta:+d} min ({session.duration_min} statt {planned.duration_min})")

    # "Härter als geplant" wird getrennt gesammelt: eine kürzere Einheit,
    # die dafür schneller gelaufen wurde, ist kein Ausfall, sondern eine
    # Verdichtung. Ohne diese Unterscheidung liest sich jede intensivere
    # Einheit im Rückblick wie ein verpasstes Training.
    harder: list[str] = []

    # Watt nur beim Radfahren vergleichen. Laufuhren melden ebenfalls eine
    # Leistung, die aber nichts mit einem Rad-Zielband zu tun hat — sonst
    # entsteht Unsinn wie "288 W Laufleistung, 13 W über Rad-Zielband".
    if planned.target_watts_low and session.discipline in ("bike", "brick"):
        from services.segments import structure_from_laps, structure_from_power

        # Gegen die Intervalle vergleichen, nicht gegen die ganze Ausfahrt:
        # der Schnitt enthält Ein-, Ausfahren und Erholungen und liegt
        # zwangsläufig unter jedem Intervall-Zielband.
        structure = structure_from_laps(session)
        if structure is None:
            # Ohne Runden aus der Leistungskurve rekonstruieren.
            structure = structure_from_power(session, planned.target_watts_low * 0.95)
        main = (structure or {}).get("main")
        if main and main.get("avg_watts"):
            watts = main["avg_watts"]
            basis = f"Hauptteil {main['laps']}× à ~{round(main['seconds'] / 60 / main['laps'])} min"
        else:
            watts = session.normalized_power or session.avg_watts
            basis = "Ø gesamt"

        high = planned.target_watts_high or planned.target_watts_low
        if watts and watts < planned.target_watts_low:
            parts.append(f"Leistung: {planned.target_watts_low - watts} W unter Zielband ({basis})")
        elif watts and watts > high:
            harder.append(f"{basis} {watts - high} W über Zielband")
        elif watts:
            # Im Band getroffen — das gehört ins Protokoll, sonst sieht eine
            # perfekt umgesetzte Einheit aus wie eine ohne Befund.
            parts.append(f"Leistung im Zielband ({basis}: {watts} W)")

    if session.discipline in ("run", "brick"):
        # Gegen den Hauptteil vergleichen, nicht gegen den Schnitt: bei einer
        # Einheit aus Einlaufen, Renntempo und Auslaufen sagt der Durchschnitt
        # nichts über die Qualität des Hauptteils aus.
        from services.segments import format_pace, reference_split, structure_from_laps

        # Die Runden der Uhr schlagen das gleitende Fenster: sie zeigen den
        # tatsächlich gelaufenen Hauptteil statt des schnellsten beliebigen
        # Abschnitts, der auch quer über eine Pause liegen könnte.
        structure = structure_from_laps(session)
        main = (structure or {}).get("main")
        ref = reference_split(session)

        if main and main.get("pace_s_per_km"):
            actual_s = main["pace_s_per_km"]
            basis = f"Hauptteil {main['distance_km']} km in {format_pace(actual_s)}/km"
        elif ref:
            actual_s = ref["pace_s_per_km"]
            basis = f"schnellster {ref['distance_km']}-km-Abschnitt {format_pace(actual_s)}/km"
        elif session.avg_pace_min_km:
            actual_s = session.avg_pace_min_km * 60
            basis = f"Ø-Pace {format_pace(actual_s)}/km"
        else:
            actual_s = None
            basis = None

        if actual_s and planned.target_pace_high_s_per_km and actual_s > planned.target_pace_high_s_per_km + 20:
            slower = round(actual_s - planned.target_pace_high_s_per_km)
            parts.append(f"Pace: {slower}s/km langsamer als Zielband ({basis})")
        elif actual_s and planned.target_pace_low_s_per_km and actual_s < planned.target_pace_low_s_per_km - 10:
            faster = round(planned.target_pace_low_s_per_km - actual_s)
            harder.append(f"{basis}, {faster}s/km schneller als Zielband")

    if harder:
        # Steht die kürzere Dauer neben einer höheren Intensität, gehört
        # beides in denselben Satz — sonst wirkt die Einheit im Log wie ein
        # Rückstand, obwohl mehr Reiz gesetzt wurde als geplant.
        verdichtet = any("min" in p for p in parts)
        prefix = "dafür " if verdichtet else ""
        parts.append(prefix + " und ".join(harder))

    return " | ".join(parts) if parts else None


def classify_session(db: Session, session: TrainingSession, commit: bool = True) -> dict:
    """Einheit klassifizieren, dem Plan zuordnen, Abweichung festhalten."""
    profile = get_profile(db)
    ftp = profile.ftp_watts if profile else 238

    actual_type = classify_actual_type(session, ftp)
    if actual_type and not is_valid_training_type(session.discipline, actual_type):
        logger.warning(
            "Klassifizierung %s passt nicht zu %s (Einheit %s) — verworfen",
            actual_type, session.discipline, session.id,
        )
        actual_type = None

    planned, confidence = find_best_planned(db, session)

    components = None
    if planned is not None and planned.discipline == "brick" and session.discipline in ("bike", "run"):
        components = brick_components(db, planned, session)

    session.actual_type = actual_type
    session.planned_session_id = planned.id if planned else None
    session.match_confidence = confidence if planned else None
    session.deviation_note = build_deviation_note(planned, session, actual_type, components)

    if planned is not None:
        # Der Rückverweis fasst nur eine Einheit; bei einem Brick gewinnt
        # deterministisch die erste Teilaktivität, damit das Ergebnis nicht
        # von der Reihenfolge der Klassifizierung abhängt. Die vollständige
        # Beziehung trägt ohnehin TrainingSession.planned_session_id.
        if planned.matched_session_id is None or session.id < planned.matched_session_id:
            planned.matched_session_id = session.id
        if planned.status in ("planned", "moved"):
            planned.status = "completed"

    if commit:
        db.commit()

    return {
        "session_id": session.id,
        "discipline": session.discipline,
        "actual_type": actual_type,
        "planned_session_id": planned.id if planned else None,
        "planned_type": planned.training_type if planned else None,
        "confidence": confidence if planned else None,
        "deviation": session.deviation_note,
    }


def classify_all(
    db: Session,
    limit: int | None = None,
    only_unclassified: bool = True,
    commit: bool = True,
) -> dict:
    query = db.query(TrainingSession).filter(TrainingSession.deleted_at == None)  # noqa: E711
    if only_unclassified:
        query = query.filter(TrainingSession.actual_type == None)  # noqa: E711
    query = query.order_by(TrainingSession.session_date.desc())
    if limit:
        query = query.limit(limit)

    results = [classify_session(db, s, commit=False) for s in query.all()]
    if commit:
        db.commit()

    typed = sum(1 for r in results if r["actual_type"])
    matched = sum(1 for r in results if r["planned_session_id"])
    return {
        "processed": len(results),
        "with_actual_type": typed,
        "matched_to_plan": matched,
        "details": results,
    }
