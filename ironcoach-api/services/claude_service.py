import json
import logging
from anthropic import AsyncAnthropic
from core.config import settings
from core.training_types import ALL_TRAINING_TYPES, DISCIPLINES

logger = logging.getLogger(__name__)

client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

# Frei strukturiertes Objekt — die genauen Keys pro Sportart stehen in
# prompt_templates.DETAILS_FORMAT. Wichtig ist nur, dass Rad-Einheiten ein
# "blocks"-Array mit Watt/RPM/Dauer/Zone liefern, sonst rendert der
# Wochenkalender im Frontend keine Blöcke.
DETAILS_SCHEMA = {
    "type": "object",
    "description": (
        "Trainingsdetails. bike/brick: {workout, warmup, blocks:[{block, watt, rpm, dauer, zone}], cooldown}. "
        "run: {typ, struktur, pace, ziel_hr}. brick: {bike:{...}, transition, run:{...}}. "
        "swim/gym/rest: leeres Objekt."
    ),
    "properties": {
        "workout": {"type": "string"},
        # Ein- und Ausfahren als strukturierte Blöcke statt als Fließtext:
        # "10 min locker" enthält keine Zahl, die sich gegen die tatsächlich
        # gefahrene Leistung stellen ließe — in der Auswertung stand dort
        # deshalb immer ein Strich.
        "warmup": {
            "type": "object",
            "description": "Einfahren/Aufwärmen. Beim Rad ist 'watt' Pflicht.",
            "properties": {
                "dauer": {"type": "string", "description": "z.B. '10 min' oder '2 km'"},
                "watt": {"type": "string", "description": "Wattbereich, z.B. '120-140 W'"},
                "pace": {"type": "string", "description": "Pace-Bereich, z.B. '6:00-6:30/km'"},
                "rpm": {"type": "string"},
                "beschreibung": {"type": "string"},
            },
            "required": ["dauer"],
        },
        "cooldown": {
            "type": "object",
            "description": "Ausfahren/Auslaufen. Beim Rad ist 'watt' Pflicht, beim Laufen 'pace'.",
            "properties": {
                "dauer": {"type": "string"},
                "watt": {"type": "string"},
                "pace": {"type": "string"},
                "rpm": {"type": "string"},
                "beschreibung": {"type": "string"},
            },
            "required": ["dauer"],
        },
        "blocks": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "block": {
                        "type": "string",
                        "description": "Nummer für Arbeitsblöcke, 'Erholung' bzw. 'Trabpause' für Pausen",
                    },
                    "watt": {"type": "string", "description": "Rad: Wattbereich"},
                    "pace": {"type": "string", "description": "Lauf: Pace-Bereich, z.B. '4:10-4:30/km'"},
                    "rpm": {"type": "string"},
                    "dauer": {"type": "string"},
                    "zone": {"type": "string"},
                },
            },
        },
        "typ": {"type": "string"},
        "struktur": {"type": "string"},
        "pace": {"type": "string"},
        "ziel_hr": {"type": "string"},
        "distanz_richtwert": {"type": "string"},
    },
}

# Numerische Zielwerte — die maschinenlesbare Hälfte einer Session.
# Bewusst getrennt von details: details beschreibt die Einheit für den Menschen
# ("145-155 W, Kadenz 76-80"), targets liefert dieselbe Vorgabe als Zahl, damit
# der Ist/Soll-Abgleich rechnen kann statt Strings zu parsen.
TARGETS_SCHEMA = {
    "type": "object",
    "description": (
        "Numerische Zielwerte dieser Einheit. Nur Felder angeben, die für die "
        "Sportart sinnvoll sind — lieber weglassen als raten."
    ),
    "properties": {
        "tss": {"type": "number", "description": "Geschätzter Training Stress Score"},
        "watts_low": {"type": "integer", "description": "Untere Grenze des Ziel-Wattbands (Rad)"},
        "watts_high": {"type": "integer", "description": "Obere Grenze des Ziel-Wattbands (Rad)"},
        "pace_low_s_per_km": {
            "type": "integer",
            "description": "Schnellste Ziel-Pace in Sekunden/km (Lauf), z.B. 360 = 6:00/km",
        },
        "pace_high_s_per_km": {
            "type": "integer",
            "description": "Langsamste Ziel-Pace in Sekunden/km (Lauf), z.B. 410 = 6:50/km",
        },
        "hr_zone": {"type": "string", "enum": ["Z1", "Z2", "Z3", "Z4", "Z5"]},
        "distance_km": {"type": "number"},
    },
}

DAY_SCHEMA = {
    "type": "object",
    "properties": {
        "day": {"type": "string", "description": "Wochentag auf Deutsch, z.B. Montag"},
        "date": {"type": "string", "description": "YYYY-MM-DD"},
        "session_type": {
            "type": "string",
            "enum": DISCIPLINES,
            "description": "Sportart",
        },
        "training_type": {
            "type": "string",
            "enum": ALL_TRAINING_TYPES,
            "description": (
                "Trainingstyp, muss zur Sportart passen. "
                "bike: recovery|z2_endurance|sweet_spot|threshold|vo2max|race_pace|long_ride. "
                "run: recovery|walk_run|z2_endurance|tempo|intervals|brick_run|long_run. "
                "swim: technique|endurance|intervals|open_water. gym: strength|mobility. "
                "brick: brick. rest: rest."
            ),
        },
        "duration_min": {"type": "integer"},
        "targets": TARGETS_SCHEMA,
        "details": DETAILS_SCHEMA,
        "notes": {"type": "string"},
    },
    "required": ["day", "date", "session_type", "training_type"],
}

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
            "days": {"type": "array", "items": DAY_SCHEMA},
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
    sessions_text: str | None = None,
    reflections: str = "",
    total_weeks: int = 33,
    constraints: str | None = None,
    health: str | None = None,
    races: str | None = None,
    offseason: str | None = None,
    season_history: str | None = None,
    zones: str | None = None,
    quality: str | None = None,
    base_period: str | None = None,
) -> dict:
    """Erzeugt den Wochenplan.

    Gibt neben dem Plan den **tatsächlich verschickten** Prompt zurück, unter
    dem Schlüssel `_prompt`. Vorher baute der Aufrufer sich denselben Prompt
    ein zweites Mal, um ihn zu archivieren — mit einer getrennt gepflegten
    Argumentliste. Die beiden liefen auseinander: Im Archiv fehlten zuletzt
    Obsidian-Kontext, Reflexionen und Saisonnotizen, sodass die gespeicherte
    Fassung nicht mehr zeigte, worauf der Plan beruhte.
    """
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
        sessions_text=sessions_text,
        reflections=reflections,
        total_weeks=total_weeks,
        constraints=constraints,
        health=health,
        races=races,
        offseason=offseason,
        season_history=season_history,
        zones=zones,
        quality=quality,
        base_period=base_period,
    )

    # Guthaben vor dem Aufruf prüfen, nicht danach: Nachträglich abzurechnen
    # hieße, dass jeder sein Guthaben beliebig überziehen kann.
    from services.api_budget import ensure_budget, record
    from core.deps import resolve_user
    from database import SessionLocal

    abrechnung = SessionLocal()
    try:
        nutzer = resolve_user(abrechnung)
        ensure_budget(abrechnung, nutzer)
    finally:
        abrechnung.close()

    MODELL = "claude-sonnet-4-6"
    response = await client.messages.create(
        model=MODELL,
        max_tokens=4096,
        system=(
            "Du bist ein erfahrener Ausdauer-Coach und Sportwissenschaftler.\n"
            f"Du betreust diesen Athleten seit Woche 1 seiner {total_weeks}-Wochen-Vorbereitung.\n"
            f"Ziel: {athlete_profile.get('goal_label') or 'Wettkampf'} am "
            f"{athlete_profile.get('race_date')}"
            + (f", {athlete_profile['race_goal']}" if athlete_profile.get('race_goal') else "")
            + ".\nVerwende immer das create_training_plan Tool für deine Antwort."
        ),
        tools=[PLAN_TOOL],
        tool_choice={"type": "tool", "name": "create_training_plan"},
        messages=[{"role": "user", "content": prompt}],
    )

    # Nach dem Aufruf mit den tatsächlichen Token buchen — geschätzte Werte
    # würden am Monatsende von der Rechnung abweichen.
    abrechnung = SessionLocal()
    try:
        record(
            abrechnung, resolve_user(abrechnung), kind="plan", model=MODELL,
            input_tokens=getattr(response.usage, "input_tokens", 0),
            output_tokens=getattr(response.usage, "output_tokens", 0),
        )
    except Exception as e:  # pragma: no cover - Buchung darf nie den Plan reißen
        logger.warning("Verbrauch konnte nicht gebucht werden: %s", e)
    finally:
        abrechnung.close()

    for block in response.content:
        if block.type == "tool_use" and block.name == "create_training_plan":
            # Der Prompt reist mit, statt beim Aufrufer neu gebaut zu werden.
            # Unterstrich, weil er nicht Teil des Planinhalts ist.
            return {**block.input, "_prompt": prompt}

    raise ValueError("Claude hat kein gültiges Plan-Tool zurückgegeben")


UPDATE_PLAN_TOOL = {
    "name": "update_training_plan",
    "description": (
        "Erstellt oder aktualisiert den Wochentrainingsplan basierend auf dem Chat-Gespräch. "
        "IMMER alle 7 Tage (Montag–Sonntag) mit vollständigen details liefern — auch die Tage, "
        "die unverändert bleiben. Ein Plan ohne komplette days-Liste wird verworfen."
    ),
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
    import json
    from datetime import date as _date
    from core.prompt_templates import DETAILS_FORMAT, TARGETS_FORMAT
    sessions_text = current_week_context.get("sessions_summary", "")
    hrv_text = current_week_context.get("hrv_summary", "")
    current_plan_text = current_week_context.get("current_plan", "")
    plan_detail = current_week_context.get("current_plan_detail")
    latest_hrv = current_week_context.get("latest_hrv")

    plan_detail_str = "Kein Detail-Plan verfügbar"
    if plan_detail:
        try:
            plan_detail_str = json.dumps(plan_detail, ensure_ascii=False, indent=2)
        except Exception:
            plan_detail_str = str(plan_detail)

    today = _date.today()
    weekday_de = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"][today.weekday()]
    today_str = f"{weekday_de}, {today.isoformat()}"

    # Subjektives getrennt ausweisen — eine Selbsteinschätzung ist keine Messung.
    reflections = current_week_context.get("reflections", "")
    reflections_block = ""
    if reflections:
        reflections_block = (
            "\n**Reflexionen des Athleten (subjektiv, selbst notiert):**\n"
            f"{reflections}\n"
            "→ Zur Einordnung nutzen, nicht als gemessene Werte behandeln.\n"
        )

    latest_hrv_str = "Keine HRV-Daten"
    if latest_hrv:
        latest_hrv_str = f"{latest_hrv.get('rmssd')}ms ({latest_hrv.get('hrv_status', '?')}), gemessen {latest_hrv.get('measured_at', '?')}"

    # Alle Angaben aus dem Kontext, keine aus dem Code. Vorher standen hier
    # Amirs Name, sein Renntag und seine Zielzeit fest verdrahtet — jeder
    # andere Athlet bekam damit einen Coach, der ihn für Amir hielt und ihn
    # auf ein Rennen vorbereitete, das er nie gemeldet hatte.
    name = current_week_context.get("name") or "der Athlet"
    gesamt = current_week_context.get("total_weeks") or 33
    ziel_teile = [t for t in (
        current_week_context.get("race_name") or current_week_context.get("race_label"),
        f"am {current_week_context['race_date']}" if current_week_context.get("race_date") else None,
        f"Ziel {current_week_context['goal_time']}" if current_week_context.get("goal_time") else None,
    ) if t]
    ziel_text = ", ".join(ziel_teile) if ziel_teile else "kein Saisonziel hinterlegt"
    ftp_text = (f"FTP: {current_week_context['ftp']}W, "
                if current_week_context.get("ftp") else "")
    positions_text = (
        "Off Season — kein laufendes Saisonziel"
        if current_week_context.get("offseason")
        else "Grundlagenphase — der Aufbau beginnt am "
             f"{current_week_context.get('plan_start')}"
        if current_week_context.get("base_period")
        else f"Woche {current_week_context.get('week', '?')}/{gesamt}"
    )

    def abschnitt(text):
        """Leere Bausteine ganz weglassen statt als Überschrift ohne Inhalt."""
        return f"\n{text}\n" if text else ""

    system = f"""Du bist der persönliche Triathlon-Coach von {name}.

**HEUTE: {today_str}**  ← Nutze immer dieses Datum als Referenz. "Gestern" = {(_date.fromordinal(today.toordinal() - 1)).isoformat()}.

Athletenkontext: {positions_text}, Phase: {current_week_context.get('phase', 'Base')}, {ftp_text}Ziel: {ziel_text}.
{abschnitt(current_week_context.get("offseason_block"))}{abschnitt(current_week_context.get("base_block"))}{abschnitt(current_week_context.get("health"))}{abschnitt(current_week_context.get("races"))}{abschnitt(current_week_context.get("constraints_block"))}{abschnitt(current_week_context.get("zones"))}

**Aktuelle HRV (heute):** {latest_hrv_str}

**HRV-Verlauf letzte 7 Tage:**
{hrv_text if hrv_text else 'Keine Daten'}

**Letzte Trainingseinheiten (gemessen, inkl. Struktur und Plan/Ist-Abgleich):**
{sessions_text if sessions_text else 'Keine Daten'}
{reflections_block}

**Aktueller Wochenplan (Übersicht):**
{current_plan_text if current_plan_text else 'Noch kein Plan generiert'}

**Aktueller Wochenplan (volle Details mit Blocks, Watts, RPM, Pace):**
```json
{plan_detail_str}
```

{abschnitt(current_week_context.get("season_history"))}{abschnitt(current_week_context.get("quality"))}

## Verhaltensregeln (STRIKT)

1. **ANTWORTE direkt auf die Frage des Athleten.** Wenn er fragt "Mittwoch nachholen oder lassen?" → gib eine Empfehlung. Stelle NUR Gegenfragen wenn wirklich kritische Info fehlt.

2. **Nutze die Daten oben — frag nicht erneut nach.** HRV, geplanter Tag, letzte Sessions stehen alle da. Wenn HRV grün ist und du es brauchst, nimm sie aus dem Kontext.

3. **Erfinde nichts.** Keine Verletzungen, keine Angst, keine Schmerzen, keine Sessions die der Athlet nicht erwähnt hat. Wenn etwas nicht in den Daten steht, existiert es nicht.

4. **Daten-Interpretation:**
   - "Gestern" = exakt {(_date.fromordinal(today.toordinal() - 1)).isoformat()}, schau im Plan UND in den Sessions nach
   - Wenn eine geplante Session NICHT in den Sessions auftaucht: sie wurde nicht gemacht — frag was passiert ist, erfinde keinen Grund
   - Wochentage aus dem Plan EXAKT übernehmen, nicht raten

5. **Plan ändern:** Nutze update_training_plan Tool nur wenn der Athlet explizit eine Änderung will.
   Wenn du es nutzt, gilt STRIKT:
   - **Alle 7 Tage** (Montag bis Sonntag) mit `day`, `date` (YYYY-MM-DD) und `session_type`
     (`rest|bike|run|swim|gym|brick`) — auch unveränderte Tage komplett wiederholen.
   - **Jeder Trainingstag braucht ausgefüllte `details`** im Format unten (Rad mit `blocks`
     inkl. Watt/RPM/Dauer/Zone, Lauf mit Pace und Ziel-HR). Ohne `details` sieht der Athlet
     im Wochenplan keine Vorgaben.
   - **Jeder Tag braucht `training_type` und `targets`** (numerisch) — daran wird später
     automatisch gemessen, ob die Einheit wie geplant gelaufen ist.
   - `coaching_comment` und `adjustments` kurz halten (max. 3-4 Sätze bzw. 4 Punkte) —
     das Token-Budget gehört den Tagen.
   - Antworte im Text nur mit 1-2 Sätzen, wenn du das Tool nutzt.

{TARGETS_FORMAT}

{DETAILS_FORMAT}

6. Antworte auf Deutsch, kurz, direkt, ohne unnötige Emojis. Eine klare Empfehlung > drei Rückfragen."""

    messages = chat_history + [{"role": "user", "content": message}]

    from services.api_budget import ensure_budget, record
    from core.deps import resolve_user
    from database import SessionLocal

    abrechnung = SessionLocal()
    try:
        nutzer = resolve_user(abrechnung)
        ensure_budget(abrechnung, nutzer)
    finally:
        abrechnung.close()

    MODELL = "claude-sonnet-4-6"
    response = await client.messages.create(
        model=MODELL,
        # Ein kompletter Wochenplan mit Blocks/Watts/Pace braucht deutlich mehr als
        # eine reine Chat-Antwort — bei zu kleinem Budget bricht das tool_use mitten
        # im JSON ab und "days" fehlt komplett.
        max_tokens=8192,
        system=system,
        tools=[UPDATE_PLAN_TOOL],
        messages=messages,
    )

    # Nach dem Aufruf mit den tatsächlichen Token buchen — geschätzte Werte
    # würden am Monatsende von der Rechnung abweichen.
    abrechnung = SessionLocal()
    try:
        record(
            abrechnung, resolve_user(abrechnung), kind="chat", model=MODELL,
            input_tokens=getattr(response.usage, "input_tokens", 0),
            output_tokens=getattr(response.usage, "output_tokens", 0),
        )
    except Exception as e:  # pragma: no cover - Buchung darf nie den Plan reißen
        logger.warning("Verbrauch konnte nicht gebucht werden: %s", e)
    finally:
        abrechnung.close()

    updated_plan = None
    reply_parts = []

    for block in response.content:
        if block.type == "text":
            reply_parts.append(block.text)
        elif block.type == "tool_use" and block.name == "update_training_plan":
            candidate = block.input
            if not candidate.get("days"):
                # Abgeschnittenes oder unvollständiges tool_use — lieber gar keinen Plan
                # speichern als den bestehenden durch einen tagelosen zu überdecken.
                logger.warning(
                    "update_training_plan ohne days verworfen (stop_reason=%s, keys=%s)",
                    response.stop_reason,
                    sorted(candidate.keys()),
                )
                reply_parts.append(
                    "Der Plan konnte nicht vollständig erstellt werden (Antwort abgeschnitten) — "
                    "der bestehende Wochenplan bleibt unverändert. Bitte nochmal anfragen, "
                    "gerne für einzelne Tage."
                )
                continue
            updated_plan = candidate
            reply_parts.append(
                f"Plan für Woche {updated_plan.get('week')} wurde aktualisiert. "
                f"Phase: {updated_plan.get('phase')}. "
                f"{updated_plan.get('coaching_comment', '')}"
            )

    reply = "\n".join(reply_parts) if reply_parts else "Ich habe keine Antwort erhalten."
    return reply, updated_plan
