"""Den Wochenplan als Note nach Obsidian schreiben.

Gegenstück zum Session-Sync: dort wandern die Ist-Daten in den Vault, hier
das Soll. Damit steht die Woche im selben Medium wie die Reflexionen, und
beim nächsten Planungslauf liest der Coach beides nebeneinander.

Wie bei den Trainings-Notes wird nur der Bereich zwischen den Markern
ersetzt. Alles, was du selbst unter die Note schreibst, bleibt stehen —
auch dann, wenn der Plan mitten in der Woche neu generiert wird.
"""

import logging
from datetime import datetime

from sqlalchemy.orm import Session

from core.config import settings
from core.training_types import intensity_label
from models import PlannedSession, WeeklyPlan
from services.obsidian import notes as note_utils
from services.obsidian.client import ObsidianClient, ObsidianError, ObsidianUnavailable

logger = logging.getLogger(__name__)

DAY_SHORT = {
    "Montag": "Mo", "Dienstag": "Di", "Mittwoch": "Mi", "Donnerstag": "Do",
    "Freitag": "Fr", "Samstag": "Sa", "Sonntag": "So",
}


def plan_note_path(plan: WeeklyPlan, subdir: str | None = None) -> str:
    """Eine Note je Trainingswoche, getrennt von den Einheiten."""
    base = (subdir or settings.OBSIDIAN_VAULT_SUBDIR).strip("/")
    return f"{base}/Plans/Woche-{plan.week_number:02d}.md"


def _fmt_pace(seconds: int | None) -> str | None:
    if not seconds:
        return None
    return f"{seconds // 60}:{seconds % 60:02d}"


def _targets_cell(row: PlannedSession) -> str:
    """Die Zielwerte einer Einheit in einer Zelle."""
    parts = []
    if row.target_watts_low:
        high = row.target_watts_high or row.target_watts_low
        parts.append(f"{row.target_watts_low}–{high} W" if high != row.target_watts_low else f"{row.target_watts_low} W")
    if row.target_pace_low_s_per_km:
        lo = _fmt_pace(row.target_pace_low_s_per_km)
        hi = _fmt_pace(row.target_pace_high_s_per_km)
        parts.append(f"{lo}–{hi}/km" if hi and hi != lo else f"{lo}/km")
    if row.target_hr_zone:
        parts.append(row.target_hr_zone)
    if row.target_tss:
        parts.append(f"TSS {row.target_tss:.0f}")
    if row.target_distance_km:
        parts.append(f"{row.target_distance_km:g} km")
    return " · ".join(parts) or "—"


def build_plan_block(plan: WeeklyPlan, rows: list[PlannedSession]) -> str:
    """Der generierte Teil der Wochennote."""
    content = plan.plan_content or {}
    lines = [note_utils.MARKER_START, "", "## Diese Woche", ""]

    if content.get("coaching_comment"):
        lines.append(content["coaching_comment"])
        lines.append("")

    adjustments = plan.adjustments_applied or content.get("adjustments") or []
    if adjustments:
        lines.append("### Anpassungen")
        lines.extend(f"- {item}" for item in adjustments)
        lines.append("")

    if rows:
        lines.append("| Tag | Datum | Sportart | Typ | Intensität | Dauer | Vorgaben |")
        lines.append("|---|---|---|---|---|---|---|")
        for row in rows:
            label = intensity_label(row.intensity, with_zone=False) or "—"
            duration = f"{row.duration_min} min" if row.duration_min else "—"
            lines.append(
                f"| {DAY_SHORT.get(row.day_name or '', row.day_name or '?')} "
                f"| {row.planned_date.strftime('%d.%m.')} "
                f"| {row.discipline} "
                f"| {(row.training_type or '—').replace('_', ' ')} "
                f"| {label} | {duration} | {_targets_cell(row)} |"
            )
        lines.append("")

        # Notizen je Tag darunter: die Tabelle bleibt lesbar, die Details
        # gehen trotzdem nicht verloren.
        detail_lines = [f"- **{DAY_SHORT.get(r.day_name or '', r.day_name)}**: {r.notes}"
                        for r in rows if r.notes]
        if detail_lines:
            lines.append("### Hinweise")
            lines.extend(detail_lines)
            lines.append("")

    lines.append(note_utils.MARKER_END)
    return "\n".join(lines)


def build_plan_frontmatter(plan: WeeklyPlan) -> dict:
    return {
        "week": plan.week_number,
        "phase": plan.plan_phase,
        "week_start": plan.week_start,
        "week_end": plan.week_end,
        "generated_at": plan.generated_at.isoformat() if plan.generated_at else None,
        "tags": ["plan", f"plan/woche-{plan.week_number:02d}"],
    }


def render_plan_note(plan: WeeklyPlan, rows: list[PlannedSession]) -> str:
    frontmatter = note_utils._dump_frontmatter(build_plan_frontmatter(plan))
    return (
        f"---\n{frontmatter}\n---\n\n"
        f"# Woche {plan.week_number} — {plan.plan_phase or ''}\n\n"
        f"{build_plan_block(plan, rows)}\n\n"
        "## Notizen\n\n"
        "<!-- Alles ab hier gehört dir. IronCoach fasst diesen Bereich nie an. -->\n\n"
    )


PLAN_FRONTMATTER_KEYS = {"week", "phase", "week_start", "week_end", "generated_at", "tags"}


def merge_plan_note(existing: str, plan: WeeklyPlan, rows: list[PlannedSession]) -> str:
    """Nur den Marker-Block ersetzen, alles andere unangetastet lassen."""
    old_frontmatter, body = note_utils._parse_frontmatter(existing)

    merged = dict(old_frontmatter)
    for key, value in build_plan_frontmatter(plan).items():
        if value is None:
            merged.pop(key, None)
            continue
        if isinstance(value, (list, tuple)):
            merged[key] = f"[{', '.join(note_utils._yaml_scalar(v) for v in value)}]"
        else:
            merged[key] = note_utils._yaml_scalar(value)

    frontmatter_text = "\n".join(f"{k}: {v}" for k, v in merged.items() if v is not None)

    if note_utils._MANAGED_RE.search(body):
        new_body = note_utils._MANAGED_RE.sub(
            lambda _: build_plan_block(plan, rows), body, count=1
        )
    else:
        # Block wurde bewusst entfernt — dann bleibt die Note in Ruhe.
        new_body = body

    return f"---\n{frontmatter_text}\n---\n{new_body}"


def sync_plan_note(db: Session, plan: WeeklyPlan, client: ObsidianClient | None = None) -> dict:
    """Wochenplan nach Obsidian schreiben. Wirft nicht."""
    from core.deps import get_profile
    from services.obsidian.client import client_for_profile, vault_subdir_for

    profile = get_profile(db)
    client = client or client_for_profile(profile)
    if not client.enabled:
        return {"status": "disabled", "plan_id": plan.id}

    path = plan_note_path(plan, vault_subdir_for(profile))
    rows = (
        db.query(PlannedSession)
        .filter(PlannedSession.plan_id == plan.id)
        .order_by(PlannedSession.planned_date.asc(), PlannedSession.day_index.asc())
        .all()
    )

    try:
        existing = client.get_note(path)
        if existing is None:
            content = render_plan_note(plan, rows)
        elif note_utils.MARKER_START not in existing:
            logger.info("Plan-Note %s ohne Managed Block — unangetastet gelassen", path)
            return {"status": "skipped_block_removed", "path": path, "plan_id": plan.id}
        else:
            content = merge_plan_note(existing, plan, rows)

        if existing is not None and content == existing:
            return {"status": "unchanged", "path": path, "plan_id": plan.id}

        client.put_note(path, content)
        return {"status": "written", "path": path, "plan_id": plan.id, "sessions": len(rows)}

    except ObsidianUnavailable as e:
        logger.warning("Plan-Note %s nicht geschrieben: %s", path, e)
        return {"status": "unavailable", "path": path, "error": str(e)}
    except ObsidianError as e:
        logger.error("Plan-Note %s fehlgeschlagen: %s", path, e)
        return {"status": "error", "path": path, "error": str(e)}
    except Exception as e:  # pragma: no cover
        logger.exception("Unerwarteter Fehler bei Plan-Note %s", path)
        return {"status": "error", "path": path, "error": str(e)}
