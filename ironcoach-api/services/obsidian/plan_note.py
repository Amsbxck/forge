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


def wochen_kennung(week_number: int) -> str:
    """Name einer Woche für Dateiname und Schlagwort.

    Wochen vor dem Beginn der Vorbereitung tragen negative Nummern. Direkt
    formatiert ergäbe das "Woche--7" — zwei Bindestriche, ohne Auffüllung,
    und im Vault sähe es nach einem Tippfehler aus. Sie bekommen deshalb
    ein eigenes Wort und dieselbe zweistellige Schreibweise, damit die
    Dateien beieinander stehen und sich sortieren lassen.
    """
    if week_number < 1:
        return f"Vorlauf-{abs(week_number):02d}"
    return f"Woche-{week_number:02d}"


def plan_note_path(
    plan: WeeklyPlan, subdir: str | None = None, saison: str | None = None
) -> str:
    """Eine Note je Trainingswoche, getrennt von den Einheiten.

    Mit Saisonordner, weil die Wochennummer nur innerhalb einer
    Vorbereitung eindeutig ist: `Woche-12.md` gibt es im 70.3-Aufbau und im
    Marathonaufbau, und flach in `Plans/` überschreibt der eine den anderen.
    """
    base = (subdir or settings.OBSIDIAN_VAULT_SUBDIR).strip("/")
    teile = [base, "Plans"]
    if saison:
        teile.append(saison)
    return "/".join(teile) + f"/{wochen_kennung(plan.week_number)}.md"


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
        "tags": ["plan", f"plan/{wochen_kennung(plan.week_number).lower()}"],
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


def sync_plan_note(
    db: Session,
    plan: WeeklyPlan,
    client: ObsidianClient | None = None,
    ziele: list | None = None,
) -> dict:
    """Wochenplan nach Obsidian schreiben. Wirft nicht.

    `ziele` sind die A-Rennen, aus denen der Saisonordner folgt — beim
    Durchlauf über alle Pläne einmal geladen statt je Woche erneut.
    """
    from core.deps import get_profile
    from core.saison import saison_name, saison_ziele
    from services.obsidian.client import client_for_profile, vault_subdir_for

    profile = get_profile(db)
    client = client or client_for_profile(profile)
    if not client.enabled:
        return {"status": "disabled", "plan_id": plan.id}

    subdir = vault_subdir_for(profile)
    saison = saison_name(
        plan.week_start, ziele if ziele is not None else saison_ziele(db)
    )
    path = plan_note_path(plan, subdir, saison)

    # Anders als Einheiten tragen Pläne ihren letzten Pfad nicht in der
    # Datenbank. Der einzige Vorgänger ist deshalb der flache Ort ohne
    # Saisonordner — von dort wird beim ersten Lauf nach der Umstellung
    # umgezogen, damit die eigenen Notizen unter dem Plan mitkommen.
    alt_pfad = plan_note_path(plan, subdir)
    rows = (
        db.query(PlannedSession)
        .filter(PlannedSession.plan_id == plan.id)
        .order_by(PlannedSession.planned_date.asc(), PlannedSession.day_index.asc())
        .all()
    )

    try:
        existing = client.get_note(path)
        moved_from = None
        if existing is None and alt_pfad != path:
            existing = client.get_note(alt_pfad)
            if existing is not None:
                moved_from = alt_pfad

        if existing is None:
            content = render_plan_note(plan, rows)
        elif note_utils.MARKER_START not in existing:
            # Der Block wurde bewusst entfernt: die Note gehört jetzt dem
            # Athleten. Dann auch nicht verschieben — sie bleibt, wo sie ist.
            bleibt = moved_from or path
            logger.info("Plan-Note %s ohne Managed Block — unangetastet gelassen", bleibt)
            return {"status": "skipped_block_removed", "path": bleibt, "plan_id": plan.id}
        else:
            content = merge_plan_note(existing, plan, rows)

        if existing is not None and content == existing and not moved_from:
            return {"status": "unchanged", "path": path, "plan_id": plan.id}

        client.put_note(path, content)

        # Erst nach erfolgreichem Schreiben aufräumen — bricht es dazwischen
        # ab, bleibt lieber eine Kopie zu viel als gar keine Note.
        if moved_from:
            try:
                client.delete_note(moved_from)
            except ObsidianError as e:
                logger.warning("Alte Plan-Note %s nicht entfernt: %s", moved_from, e)

        return {
            "status": "moved" if moved_from else "written",
            "path": path,
            "moved_from": moved_from,
            "plan_id": plan.id,
            "sessions": len(rows),
        }

    except ObsidianUnavailable as e:
        logger.warning("Plan-Note %s nicht geschrieben: %s", path, e)
        return {"status": "unavailable", "path": path, "error": str(e)}
    except ObsidianError as e:
        logger.error("Plan-Note %s fehlgeschlagen: %s", path, e)
        return {"status": "error", "path": path, "error": str(e)}
    except Exception as e:  # pragma: no cover
        logger.exception("Unerwarteter Fehler bei Plan-Note %s", path)
        return {"status": "error", "path": path, "error": str(e)}


def verwaiste_plannoten_einordnen(
    db: Session,
    client: ObsidianClient,
    subdir: str,
    ziele: list,
) -> list[dict]:
    """Plan-Noten einordnen, zu denen es keine Planzeile mehr gibt.

    `sync_plan_note` kann nur verschieben, was die Datenbank noch kennt. Nach
    dem Umzug auf eine neue Installation ist das oft wenig: Die Einheiten
    wurden übernommen, die Wochenpläne nicht. In Amirs Vault lagen dadurch 20
    Noten der Saison 2026 flach unter `Plans/`, während die Datenbank genau
    eine Planzeile hatte — der Durchgang meldete "1 Wochenplan geprüft" und
    ließ die anderen zwanzig liegen.

    Die Noten wissen aber selbst, wohin sie gehören: `week_start` steht in
    ihrem Frontmatter. Daraus lässt sich die Saison genauso bestimmen wie aus
    einer Planzeile. Verschoben wird nur, was unmittelbar in `Plans/` liegt,
    und nie über eine bestehende Datei hinweg — eine Note, die am Ziel schon
    steht, bleibt unangetastet und wird gemeldet.
    """
    from core.saison import saison_name

    wurzel = f"{subdir.strip('/')}/Plans"
    ergebnis: list[dict] = []

    for eintrag in client.list_dir(wurzel):
        # Unterordner überspringen — die sind bereits eingeordnet.
        if not eintrag.endswith(".md"):
            continue

        quelle = f"{wurzel}/{eintrag}"
        inhalt = client.get_note(quelle)
        if inhalt is None:
            continue

        frontmatter, _ = note_utils._parse_frontmatter(inhalt)
        rohdatum = (frontmatter.get("week_start") or "").strip().strip('"')
        try:
            beginn = datetime.strptime(rohdatum[:10], "%Y-%m-%d").date()
        except ValueError:
            # Ohne verlässliches Datum lässt sich keine Saison bestimmen.
            # Raten wäre hier schlimmer als liegenlassen: die Note landete
            # in einem falschen Ordner und wäre dort nicht mehr zu finden.
            ergebnis.append({"pfad": quelle, "status": "ohne_datum"})
            continue

        ziel = f"{wurzel}/{saison_name(beginn, ziele)}/{eintrag}"
        if ziel == quelle:
            continue

        if client.get_note(ziel) is not None:
            ergebnis.append({"pfad": quelle, "status": "ziel_belegt", "ziel": ziel})
            continue

        client.put_note(ziel, inhalt)
        try:
            client.delete_note(quelle)
        except ObsidianError as e:
            logger.warning("Verwaiste Plan-Note %s nicht entfernt: %s", quelle, e)
        ergebnis.append({"von": quelle, "nach": ziel, "status": "verschoben"})

    return ergebnis
