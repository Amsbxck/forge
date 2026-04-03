import json
import logging
from anthropic import AsyncAnthropic
from core.config import settings

logger = logging.getLogger(__name__)

client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

PLAN_TOOL = {
    "name": "create_training_plan",
    "description": "Erstellt einen strukturierten Wochentrainingsplan für einen Triathleten.",
    "input_schema": {
        "type": "object",
        "properties": {
            "week": {"type": "integer"},
            "phase": {"type": "string"},
            "coaching_comment": {"type": "string"},
            "adjustments": {"type": "array", "items": {"type": "string"}},
            "days": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "day": {"type": "string"},
                        "date": {"type": "string"},
                        "session_type": {"type": "string"},
                        "duration_min": {"type": "integer"},
                        "details": {"type": "object"},
                        "notes": {"type": "string"},
                    },
                    "required": ["day", "date", "session_type"],
                },
            },
        },
        "required": ["week", "phase", "coaching_comment", "adjustments", "days"],
    },
}


async def generate_weekly_plan(
    athlete_profile: dict,
    last_sessions: list,
    hrv_data: list,
    week_number: int,
    special_requests: str = "",
    plan_start=None,
    season_context: str = "",
) -> dict:
    from datetime import date
    from core.prompt_templates import build_plan_prompt

    if plan_start is None:
        plan_start = date(2025, 12, 22)

    prompt = build_plan_prompt(
        athlete_profile=athlete_profile,
        sessions=last_sessions,
        hrv=hrv_data,
        week=week_number,
        requests=special_requests,
        plan_start=plan_start,
        season_context=season_context,
    )

    response = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system="""Du bist ein erfahrener Triathlon-Coach und Sportwissenschaftler.
Du kennst diesen Athleten seit Woche 1 seines 33-Wochen 70.3-Plans.
Ziel: 31. August 2026, sub 5:30h, zweiter 70.3.
Verwende immer das create_training_plan Tool für deine Antwort.""",
        tools=[PLAN_TOOL],
        tool_choice={"type": "tool", "name": "create_training_plan"},
        messages=[{"role": "user", "content": prompt}],
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == "create_training_plan":
            return block.input

    raise ValueError("Claude hat kein gültiges Plan-Tool zurückgegeben")


UPDATE_PLAN_TOOL = {
    "name": "update_training_plan",
    "description": "Erstellt oder aktualisiert den Wochentrainingsplan basierend auf dem Chat-Gespräch.",
    "input_schema": PLAN_TOOL["input_schema"],
}


async def chat_with_coach(
    message: str,
    chat_history: list,
    current_week_context: dict,
) -> tuple[str, dict | None]:
    """
    Returns (reply_text, updated_plan_or_None)
    """
    sessions_text = current_week_context.get("sessions_summary", "")
    hrv_text = current_week_context.get("hrv_summary", "")
    current_plan_text = current_week_context.get("current_plan", "")
    season_text = current_week_context.get("season_context", "")

    system = f"""Du bist Amirs persönlicher Triathlon-Coach.
Aktueller Kontext: Woche {current_week_context.get('week', '?')}, Phase: {current_week_context.get('phase', 'Base')}, FTP: {current_week_context.get('ftp', 238)}W, Renntag: 31.08.2026 (70.3, Ziel sub 5:30h).

Letzte Trainingseinheiten:
{sessions_text if sessions_text else 'Keine Daten'}

HRV letzte Woche:
{hrv_text if hrv_text else 'Keine Daten'}

Aktueller Wochenplan:
{current_plan_text if current_plan_text else 'Noch kein Plan generiert'}

Saisonplan & Referenzpläne:
{season_text if season_text else 'Kein Saisonplan hinterlegt'}

Wenn der Athlet einen Plan erstellen oder ändern möchte, nutze das update_training_plan Tool.
Antworte immer auf Deutsch, direkt und sportwissenschaftlich fundiert."""

    messages = chat_history + [{"role": "user", "content": message}]

    response = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        system=system,
        tools=[UPDATE_PLAN_TOOL],
        messages=messages,
    )

    updated_plan = None
    reply_parts = []

    for block in response.content:
        if block.type == "text":
            reply_parts.append(block.text)
        elif block.type == "tool_use" and block.name == "update_training_plan":
            updated_plan = block.input
            reply_parts.append(
                f"Plan für Woche {updated_plan.get('week')} wurde aktualisiert. "
                f"Phase: {updated_plan.get('phase')}. "
                f"{updated_plan.get('coaching_comment', '')}"
            )

    reply = "\n".join(reply_parts) if reply_parts else "Ich habe keine Antwort erhalten."
    return reply, updated_plan
