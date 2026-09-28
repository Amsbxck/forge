"""Einzelne Tage eines bestehenden Plans ändern, aus dem Planfenster heraus.

Im Coach-Chat gibt es das schon: `adjust_training_days` liefert nur die Tage,
die sich ändern. Im Planfenster nicht — das Feld "besondere Wünsche" dort ruft
`/api/plan/generate`, und der baut immer eine ganze Woche. Wer dort "ändere
Donnerstag bis Sonntag" eintippt, bekommt deshalb sieben neu geschriebene Tage.

Genau das ist passiert und als Fehler gemeldet worden. Es war keiner: Die
Teiländerung gab es nur an einer von zwei Stellen, an denen man dasselbe
verlangt.

Der Unterschied zum Chat: Hier wird **nur** das Tage-Werkzeug angeboten. Es gibt
nichts zu entscheiden — wer einen bestehenden Plan anpassen will, will keine neue
Woche. Das spart den Umweg über die Werkzeugwahl und macht das Ergebnis
vorhersehbar.
"""

import json
import logging

from sqlalchemy.orm import Session

from models import PlannedSession, WeeklyPlan

logger = logging.getLogger(__name__)

MODELL = "claude-sonnet-4-6"

# Kleiner als beim vollen Plan: Es gehen nur die geänderten Tage zurück, nicht
# sieben. Mehr Budget würde das Modell nur einladen, die ganze Woche zu liefern.
MAX_TOKENS = 3000


def _plan_text(plan: WeeklyPlan, rows: list[PlannedSession]) -> str:
    zeilen = []
    for r in rows:
        ziele = []
        if r.target_watts_low:
            ziele.append(f"{r.target_watts_low}-{r.target_watts_high or r.target_watts_low} W")
        if r.target_hr_zone:
            ziele.append(r.target_hr_zone)
        if r.target_tss:
            ziele.append(f"TSS {r.target_tss:.0f}")
        zeilen.append(
            f"- {r.planned_date} ({r.day_name}): {r.discipline}"
            f"{' / ' + r.training_type if r.training_type else ''}"
            f"{f', {r.duration_min} min' if r.duration_min else ''}"
            f"{' · ' + ' · '.join(ziele) if ziele else ''}"
            f"{' · ' + r.notes if r.notes else ''}"
            f"{'  [ABSOLVIERT]' if r.status == 'completed' else ''}"
        )
    return "\n".join(zeilen)


async def tage_anpassen(db: Session, plan: WeeklyPlan, wunsch: str) -> dict:
    """Den Wunsch auf die Tage dieses Plans anwenden.

    Gibt einen Bericht zurück; die neue Planzeile steckt darin als `plan_id`.
    Wirft nicht für fachliche Fälle — ein abgelehnter Tag ist eine Auskunft,
    kein Fehler.
    """
    from anthropic import AsyncAnthropic

    from core.config import settings
    from core.deps import get_profile
    from services.api_budget import ensure_budget, record
    from services.claude_service import ADJUST_DAYS_TOOL
    from services.plan_merge import merge_days

    rows = (
        db.query(PlannedSession)
        .filter(PlannedSession.plan_id == plan.id)
        .order_by(PlannedSession.planned_date.asc())
        .all()
    )
    if not rows:
        return {"status": "kein_plan", "hinweis": "Dieser Plan hat keine Tage."}

    profil = get_profile(db)
    from core.deps import resolve_user
    nutzer = resolve_user(db)
    ensure_budget(db, nutzer)

    zonen = ""
    if profil:
        zonen = (
            f"FTP {profil.ftp_watts} W · Maximalpuls {profil.max_hr} · "
            f"Z2 {profil.z2_hr_min}-{profil.z2_hr_max} · "
            f"Z3 {profil.z3_hr_min}-{profil.z3_hr_max} · "
            f"Z4 {profil.z4_hr_min}-{profil.z4_hr_max}"
        )

    system = f"""Du passt einzelne Tage eines bestehenden Wochenplans an.

## Der Plan dieser Woche ({plan.week_start} bis {plan.week_end}, Phase {plan.plan_phase})
{_plan_text(plan, rows)}

## Werte des Athleten
{zonen}

## Auftrag
Setze den Wunsch des Athleten um, indem du `adjust_training_days` aufrufst.

- **Nur die Tage liefern, die sich ändern.** Alles andere bleibt unberührt und
  muss nicht wiederholt werden. Das ist der Zweck dieses Wegs.
- Tage, die mit [ABSOLVIERT] markiert sind, und Tage in der Vergangenheit nicht
  anfassen — sie werden ohnehin abgewiesen.
- Jeder gelieferte Tag braucht `date`, `session_type`, `training_type`,
  `targets` und ausgefüllte `details`; er ersetzt den bisherigen komplett.
- Bleibt die Wochenstruktur sinnvoll: Wer einen harten Tag verschiebt, setzt
  nicht zwei harte hintereinander.
- Antworte knapp, ein bis zwei Sätze."""

    client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    antwort = await client.messages.create(
        model=MODELL, max_tokens=MAX_TOKENS, system=system,
        tools=[ADJUST_DAYS_TOOL], tool_choice={"type": "tool", "name": "adjust_training_days"},
        messages=[{"role": "user", "content": wunsch}],
    )

    try:
        record(db, nutzer, kind="plan_adjust", model=MODELL,
               input_tokens=getattr(antwort.usage, "input_tokens", 0),
               output_tokens=getattr(antwort.usage, "output_tokens", 0))
    except Exception as e:  # pragma: no cover - Buchung darf nie den Plan reissen
        logger.warning("Verbrauch nicht gebucht: %s", e)

    tage, text = [], []
    for block in antwort.content:
        if block.type == "text":
            text.append(block.text)
        elif block.type == "tool_use" and block.name == "adjust_training_days":
            tage = (block.input or {}).get("days") or []
            grund = (block.input or {}).get("reason")
            if grund:
                text.append(grund)

    if not tage:
        return {"status": "keine_aenderung",
                "hinweis": " ".join(text) or "Das Modell hat keine Tage geliefert."}

    gesperrt = {r.planned_date for r in rows if r.status == "completed"}
    inhalt, uebernommen, abgewiesen = merge_days(
        plan.plan_content or {}, tage, gesperrte_daten=gesperrt
    )
    if not uebernommen:
        return {"status": "nichts_uebernommen", "abgewiesen": abgewiesen,
                "hinweis": " ".join(text)}

    # Als neue Zeile: Der Verlauf der Woche bleibt nachvollziehbar, und
    # `pick_plan` nimmt ohnehin die jüngste Fassung.
    neu = WeeklyPlan(
        user_id=plan.user_id,
        week_number=plan.week_number,
        week_start=plan.week_start,
        week_end=plan.week_end,
        plan_phase=plan.plan_phase,
        plan_content=inhalt,
        plan_text=plan.plan_text,
        adjustments_applied=(plan.adjustments_applied or []) + [wunsch[:200]],
    )
    db.add(neu)
    db.commit()
    db.refresh(neu)

    from services.plan_projection import project_plan
    project_plan(db, neu)

    try:
        from services.obsidian.plan_note import sync_plan_note
        sync_plan_note(db, neu)
    except Exception as e:  # pragma: no cover
        logger.warning("Plan-Note nach Anpassung nicht geschrieben: %s", e)

    return {
        "status": "angepasst",
        "plan_id": neu.id,
        "geaendert": uebernommen,
        "abgewiesen": abgewiesen,
        "hinweis": " ".join(text),
    }
