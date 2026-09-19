import logging
from datetime import date, timedelta
from sqlalchemy.orm import Session
from models import AthleteProfile, TrainingSession, HrvMeasurement, WeeklyPlan
from services.claude_service import generate_weekly_plan
from core.prompt_templates import get_phase, get_week_dates
from core.deps import get_profile

logger = logging.getLogger(__name__)


def get_current_week(anchor) -> int:
    """Aktuelle Trainingswoche.

    `anchor` ist das aktive Wettkampfziel oder ersatzweise das Profil —
    beide tragen plan_start_date. Die Obergrenze kommt aus der Zieldauer
    statt aus einer festen 33, damit ein 14-Wochen-Halbmarathonplan nicht
    bis Woche 33 weiterzählt.
    """
    return get_week_for_date(anchor, date.today())


def get_week_for_date(anchor, target_date: date) -> int:
    """Trainingswoche eines Datums, gezählt ab dem Beginn der Vorbereitung.

    Woche 1 ist die Woche, in der `plan_start_date` liegt. Davor wird
    weitergezählt: 0 ist die Woche unmittelbar davor, -1 die davor, und so
    fort. Acht Wochen vor dem Start steht also -7.

    Bis hierher stand hier `max(1, …)`. Die Absicht war richtig — "Woche
    minus sieben" klingt zunächst nach Unsinn. Der Preis war aber, dass
    **jedes** Datum vor dem Beginn dieselbe Nummer bekam. Die Nummer war
    damit als Beschriftung falsch und als Kennung unbrauchbar, und beides
    hat sich gerächt: Der Wochenbreakdown zeigte sämtliche jemals
    absolvierten Einheiten, die Testwoche für die kommende Woche galt als
    bereits vorhanden, und im Wochenplan liess sich nicht vorwärts
    blättern — alles dieselbe Ursache.

    Die vorzeichenbehaftete Zählung ist auch inhaltlich die ehrlichere
    Auskunft: Sie sagt, wie weit es noch bis zum Aufbau ist, statt eine
    Woche 1 zu behaupten, die erst in zwei Monaten beginnt.

    Ohne Startdatum gibt es keinen Bezugspunkt — dann bleibt es bei 1.
    """
    start = getattr(anchor, "plan_start_date", None)
    if start is None:
        return 1
    # Ganzzahlige Division rundet in Python immer abwärts, auch bei
    # negativen Zahlen: -55 // 7 ist -8, nicht -7. Genau das ist hier
    # richtig — ein Datum 55 Tage vor dem Start liegt in der achten Woche
    # davor und bekommt damit die -7.
    return (target_date - start).days // 7 + 1


def build_athlete_dict(profile: AthleteProfile, goal=None) -> dict:
    """Profilwerte für den Prompt. Das Ziel ergänzt Name, Distanz und Dauer."""
    return {
        "name": profile.name,
        "goal_label": goal.label if goal is not None else None,
        # Die Zielzeit kam bisher nirgends an: der Prompt nutzte nur das alte
        # Freitextfeld im Profil. Wer sein Ziel über die Races-Kachel anlegt,
        # trug sie damit ins Leere ein.
        "goal_time": getattr(goal, "goal_time", None),
        "race_name": getattr(goal, "race_name", None),
        "total_weeks": getattr(goal, "total_weeks", 33) if goal is not None else 33,
        "ftp_watts": profile.ftp_watts,
        "max_hr": profile.max_hr,
        "z1_hr_max": profile.z1_hr_max,
        "z2_hr_min": profile.z2_hr_min,
        "z2_hr_max": profile.z2_hr_max,
        "z3_hr_min": profile.z3_hr_min,
        "z3_hr_max": profile.z3_hr_max,
        "z4_hr_min": profile.z4_hr_min,
        "z4_hr_max": profile.z4_hr_max,
        "race_date": str(profile.race_date),
        "race_goal": profile.race_goal,
    }


async def generate_and_save_plan(
    db: Session,
    special_requests: str = "",
) -> WeeklyPlan:
    profile = get_profile(db)
    if not profile:
        raise ValueError("Kein Athletenprofil gefunden")

    # Ziel bestimmt Distanz, Planlänge und Phasen; die Einschränkungen
    # kommen aus dem Profil des Athleten statt aus dem Prompt-Text.
    from core.deps import get_active_goal, total_weeks_for
    goal = get_active_goal(db)
    anchor = goal or profile
    total_weeks = total_weeks_for(anchor)
    constraints = profile.coaching_constraints

    # Wochennummer und Wochendaten müssen aus derselben Quelle stammen.
    # Vorher kam die Nummer vom Ziel und das Datum vom Profil: sobald beide
    # Startdaten auseinanderlagen — bei jedem Athleten, der nach der
    # Registrierung ein Ziel setzt — wies der Plan Wochen im falschen Jahr aus.
    plan_start = getattr(anchor, "plan_start_date", None) or profile.plan_start_date

    current_week = get_current_week(anchor)

    cutoff = date.today() - timedelta(days=14)
    sessions = db.query(TrainingSession).filter(
        TrainingSession.session_date >= cutoff
    ).order_by(TrainingSession.session_date.desc()).all()

    hrv_cutoff = date.today() - timedelta(days=7)
    hrv_records = db.query(HrvMeasurement).filter(
        HrvMeasurement.measured_at >= hrv_cutoff
    ).order_by(HrvMeasurement.measured_at.asc()).all()

    from services.session_view import session_to_dict
    sessions_dicts = [session_to_dict(s) for s in sessions]

    hrv_dicts = [
        {
            "measured_at": str(h.measured_at),
            "rmssd": h.rmssd,
            "hrv_status": h.hrv_status,
        }
        for h in hrv_records
    ]

    # Trainingskontext aus den Obsidian-Notes: sie enthalten Struktur,
    # Plan/Ist-Vergleich und die Reflexionen. Fällt Obsidian aus, liefert
    # der Aufbau je Einheit die Datenbankzeile.
    from services.obsidian.context import build_training_context
    obsidian_ctx = build_training_context(db, days=14)

    # Krankheit und Verletzung stehen über der Saisonstruktur. Die Regeln
    # werden ausgerechnet, nicht dem Modell zur Abwägung überlassen.
    from services.health import prompt_block as health_block_for
    health_block = health_block_for(
        db,
        race_date=getattr(goal, "race_date", None),
        total_weeks=total_weeks,
    )

    # Off Season: kein Saisonziel in der Zukunft. Dann gilt Erhalt statt
    # Aufbau — und ausdrücklich ohne Watt- und Pacevorgaben.
    from core.race_types import season_state
    from services.offseason import phase_label as offseason_phase
    from services.offseason import prompt_block as offseason_block_for

    ziel_datum = getattr(goal, "race_date", None)
    lage = "preparation" if goal is None else season_state(ziel_datum, plan_start=plan_start)
    ist_offseason = goal is None or lage == "off_season"
    offseason_block = offseason_block_for(db, ziel_datum) if ist_offseason else ""

    # Grundlagenphase: Das Ziel steht, der Aufbau beginnt aber erst später.
    # Der Baustein ersetzt die Phasenvorgabe, wie es der Off-Season-Block
    # auf der anderen Seite der Saison tut.
    from services.base_period import phase_label as base_phase
    from services.base_period import prompt_block as base_block_for

    ist_grundlage = lage == "base_period"
    base_block = base_block_for(
        plan_start,
        race_label=getattr(goal, "race_name", None) or getattr(goal, "label", None),
        race_date=ziel_datum,
    ) if ist_grundlage else ""

    # Wettkämpfe unterwegs. Die Wochendaten kommen weiter unten aus
    # get_week_dates — hier vorab berechnet, weil der Block in den Prompt geht.
    # Langzeitkontext: Formkurve, Wochenverlauf und Bestmarken. Die 14 Tage
    # oben zeigen den Zustand, dieser Block die Entwicklung.
    from services.season_summary import prompt_block as season_history_block
    # Ohne ausdrücklichen Nutzer: der Mandantenfilter schränkt die Abfragen
    # bereits ein, und eine zweite Quelle für dieselbe Frage kann abweichen.
    history_block = season_history_block(db)

    from services.zones import prompt_block as zones_block_for
    zones_block = zones_block_for(profile, sport=getattr(goal, "sport", None))

    # Spitzen- und Ermüdungssignale aus dem Soll/Ist-Vergleich, jeweils mit
    # der Reflexion des Athleten daneben.
    from services.session_quality import prompt_block as quality_block_for
    quality_block = quality_block_for(db, date.today() - timedelta(weeks=10), profile=profile)

    from services.race_calendar import week_block as race_week_block
    _ws, _we = get_week_dates(current_week, plan_start)
    races_block = race_week_block(db, _ws, _we)

    plan_content = await generate_weekly_plan(
        athlete_profile=build_athlete_dict(profile, goal),
        last_sessions=sessions_dicts,
        hrv_data=hrv_dicts,
        week_number=current_week,
        special_requests=special_requests,
        plan_start=plan_start,
        sessions_text=obsidian_ctx["sessions_text"],
        reflections=obsidian_ctx["reflections_text"],
        total_weeks=total_weeks,
        constraints=constraints,
        health=health_block,
        races=races_block,
        offseason=offseason_block,
        season_history=history_block,
        zones=zones_block,
        quality=quality_block,
        base_period=base_block,
    )

    target_week = current_week
    week_start, week_end = get_week_dates(target_week, plan_start)

    plan_text_lines = [f"Wochenplan {current_week} ({week_start} – {week_end})", ""]
    for day in plan_content.get("days", []):
        plan_text_lines.append(
            f"{day['day']} ({day['date']}): {day['session_type'].upper()} "
            f"{day.get('duration_min', '')}min — {day.get('notes', '')}"
        )
    plan_text_lines.append("")
    plan_text_lines.append(plan_content.get("coaching_comment", ""))

    # Der Prompt kommt aus der Generierung zurück, statt hier ein zweites Mal
    # gebaut zu werden — sonst weicht das Archiv vom Verschickten ab.
    prompt_used = plan_content.pop("_prompt", None)

    # Ein Plan ohne Zuordnung wäre für niemanden auffindbar: Der
    # Mandantenfilter vergleicht auf Gleichheit, und NULL trifft nie zu. Er
    # verschwände also lautlos — deshalb hier lieber ein klarer Abbruch als
    # ein Plan, den der Athlet nie zu sehen bekommt.
    if profile is None or profile.user_id is None:
        raise ValueError(
            "Profil ohne Nutzerzuordnung — der Plan wäre nach dem Speichern "
            "unsichtbar. Bitte das Konto prüfen."
        )

    db_plan = WeeklyPlan(
        user_id=profile.user_id,
        week_number=target_week,
        week_start=week_start,
        week_end=week_end,
        # In der Off Season steht die Phase fest; sie vom Modell zu übernehmen
        # hieße, dass sie mal "Off Season" und mal "Base 1" heißt.
        plan_phase=(
            f"Off Season · {offseason_phase(ziel_datum)}" if ist_offseason
            else base_phase(plan_start) if ist_grundlage
            else plan_content.get("phase")
        ),
        plan_content=plan_content,
        plan_text="\n".join(plan_text_lines),
        claude_prompt=prompt_used,
        adjustments_applied=(
            (plan_content.get("adjustments") or [])
            + (["Gesundheit: Plan angepasst"] if health_block else [])
        ),
    )
    db.add(db_plan)
    db.commit()
    db.refresh(db_plan)

    # Normalisierte Projektion für Drag&Drop und Ist/Soll-Abgleich.
    # Schlägt still fehl, solange Migration 005 nicht gelaufen ist.
    from services.plan_projection import project_plan
    project_plan(db, db_plan)

    # Wochenplan als Note in den Vault — nach der Projektion, weil die
    # Tabelle die normalisierten Einheiten braucht.
    try:
        from services.obsidian.plan_note import sync_plan_note
        result = sync_plan_note(db, db_plan)
        logger.info("Plan-Note für Woche %s: %s", db_plan.week_number, result["status"])
    except Exception as e:  # pragma: no cover - darf die Generierung nie reißen
        logger.warning("Plan-Note für Woche %s fehlgeschlagen: %s", db_plan.week_number, e)

    return db_plan
