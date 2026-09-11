"""Der gemeinsame Wissensstand von Planerstellung und Coach-Chat.

Beide Wege haben ihren Kontext bisher getrennt zusammengebaut, und sie sind
weit auseinandergelaufen. Der Chat kannte weder die Trainingsbereiche noch den
Saisonverlauf, die auffälligen Einheiten, gemeldete Krankheiten, Wettkämpfe
unterwegs oder die individuellen Regeln des Athleten. Er rechnete die Phase
zudem gegen feste 33 Wochen und las die Wochennummer aus dem Profil statt aus
dem Saisonziel.

Praktisch heißt das: Der Athlet bekommt einen Plan, der auf zehn Wochen
Verlauf und gemessenen Schwellen beruht — und wenn er im Chat nachfragt,
warum die Woche so aussieht, antwortet ein Coach, der nichts davon kennt.
Rückfragen und Änderungen sind dann bestenfalls Zufall.

Hier entsteht der Kontext deshalb genau einmal. Was neu dazukommt, steht
danach automatisch an beiden Stellen.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

WOCHEN_RUECKBLICK = 10


def athlet(db: Session, user=None) -> dict:
    """Wer ist das, worauf trainiert er, in welcher Woche steht er?

    Wochennummer und Phase kommen aus dem Saisonziel, nicht aus dem Profil.
    Im Profil stehen Platzhalter aus der Registrierung; sobald jemand ein Ziel
    setzt, weichen beide voneinander ab.
    """
    from core.deps import get_active_goal, get_profile, total_weeks_for
    from core.prompt_templates import get_phase
    from core.race_types import season_state
    from services.base_period import phase_label as base_phase
    from services.plan_generator import get_current_week

    profile = get_profile(db, user)
    goal = get_active_goal(db, user)
    anker = goal or profile
    total_weeks = total_weeks_for(anker) if anker else 33
    woche = get_current_week(anker) if anker else 1
    renntag = getattr(goal, "race_date", None) or getattr(profile, "race_date", None)
    plan_start = getattr(goal, "plan_start_date", None) or (
        profile.plan_start_date if profile else None)
    lage = (
        "preparation" if goal is None
        else season_state(getattr(goal, "race_date", None), plan_start=plan_start)
    )
    offseason = goal is None or lage == "off_season"
    grundlage = lage == "base_period"

    return {
        "profile": profile,
        "goal": goal,
        "name": (profile.name if profile else None) or "der Athlet",
        "week": woche,
        "total_weeks": total_weeks,
        # In der Grundlagenphase gibt es keine Aufbauphase — sie hier zu
        # nennen wäre eine Vorgabe, die noch gar nicht gilt.
        "phase": (
            "Off Season" if offseason
            else base_phase(plan_start) if grundlage
            else get_phase(woche, total_weeks)
        ),
        "plan_start": plan_start,
        "base_period": grundlage,
        "season_state": lage,
        "race_date": renntag,
        "race_label": getattr(goal, "label", None) or (profile.race_goal if profile else None),
        "race_name": getattr(goal, "race_name", None),
        "goal_time": getattr(goal, "goal_time", None),
        "offseason": offseason,
        "ftp": profile.ftp_watts if profile else None,
    }


def bloecke(db: Session, user=None, fakten: dict | None = None) -> dict:
    """Die Textbausteine, die in beide Prompts gehören.

    Jeder Baustein fängt seine eigenen Fehler ab: Ein Ausfall der
    Saisonauswertung darf weder den Plan noch eine Chatantwort verhindern —
    lieber ein Kontext ohne diesen Abschnitt als gar keine Antwort.
    """
    fakten = fakten or athlet(db, user)
    profile = fakten["profile"]
    goal = fakten["goal"]
    heute = date.today()

    def sicher(name, fn):
        try:
            return fn()
        except Exception as e:  # pragma: no cover
            logger.warning("Kontextbaustein '%s' fehlgeschlagen: %s", name, e)
            return ""

    def _zonen():
        from services.zones import prompt_block
        return prompt_block(profile) if profile else ""

    def _verlauf():
        from services.season_summary import prompt_block
        return prompt_block(db)

    def _auffaellig():
        from services.session_quality import prompt_block
        return prompt_block(db, heute - timedelta(weeks=WOCHEN_RUECKBLICK),
                            profile=profile) if profile else ""

    def _gesundheit():
        from services.health import prompt_block
        return prompt_block(db, race_date=getattr(goal, "race_date", None),
                            total_weeks=fakten["total_weeks"])

    def _rennen():
        from core.prompt_templates import get_week_dates
        from services.race_calendar import week_block
        start = getattr(goal, "plan_start_date", None) or (
            profile.plan_start_date if profile else None)
        if start is None:
            return ""
        ws, we = get_week_dates(fakten["week"], start)
        return week_block(db, ws, we)

    def _grundlage():
        if not fakten.get("base_period"):
            return ""
        from services.base_period import prompt_block
        return prompt_block(
            fakten.get("plan_start"),
            race_label=fakten.get("race_name") or fakten.get("race_label"),
            race_date=fakten.get("race_date"),
        )

    def _offseason():
        if not fakten["offseason"]:
            return ""
        from services.offseason import prompt_block
        return prompt_block(db, getattr(goal, "race_date", None))

    def _obsidian():
        from services.obsidian.context import build_training_context
        return build_training_context(db, days=14)

    ctx = sicher("obsidian", _obsidian) or {"sessions_text": "", "reflections_text": ""}

    return {
        "zones": sicher("zonen", _zonen),
        "season_history": sicher("verlauf", _verlauf),
        "quality": sicher("auffaellig", _auffaellig),
        "health": sicher("gesundheit", _gesundheit),
        "races": sicher("rennen", _rennen),
        # Bewusst `offseason_block`: `offseason` ist der Wahrheitswert aus
        # `athlet()`. Gleiche Namen für Text und Ja/Nein hatten sich beim
        # Zusammenführen der beiden Wörterbücher gegenseitig überschrieben.
        "offseason_block": sicher("offseason", _offseason),
        "base_block": sicher("grundlage", _grundlage),
        "constraints": (profile.coaching_constraints if profile else None) or "",
        "sessions_text": ctx.get("sessions_text", ""),
        "reflections_text": ctx.get("reflections_text", ""),
    }


def chat_kontext(db: Session, user=None) -> dict:
    """Alles, was der Coach im Gespräch braucht — dieselbe Grundlage wie der Plan."""
    fakten = athlet(db, user)
    b = bloecke(db, user, fakten)
    return {
        "name": fakten["name"],
        "week": fakten["week"],
        "total_weeks": fakten["total_weeks"],
        "phase": fakten["phase"],
        "ftp": fakten["ftp"],
        "race_date": str(fakten["race_date"]) if fakten["race_date"] else None,
        "race_label": fakten["race_label"],
        "race_name": fakten["race_name"],
        "goal_time": fakten["goal_time"],
        "offseason": fakten["offseason"],
        "base_period": fakten.get("base_period", False),
        "plan_start": str(fakten["plan_start"]) if fakten.get("plan_start") else None,
        **b,
    }
