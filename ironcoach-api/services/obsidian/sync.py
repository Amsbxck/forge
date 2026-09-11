"""Orchestrierung: TrainingSession → Obsidian-Note.

Zwei Prinzipien:

1. **Obsidian blockiert nie.** Der Postgres-Commit ist längst durch, wenn hier
   etwas passiert. Schlägt der Sync fehl, bleibt obsidian_synced_at NULL und
   der Reconcile-Job holt es später nach (Outbox-Pattern).

2. **Der Pfad wird eingefroren.** Beim ersten Sync landet er in
   obsidian_path und gilt ab dann. Ändert sich später der klassifizierte
   Trainingstyp, wandert die Note NICHT — sonst brechen Obsidian-Links und
   es bleiben Waisen liegen.
"""

import logging
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from core.config import settings
from models import PlannedSession, TrainingSession
from services.obsidian import notes
from services.obsidian.client import ObsidianClient, ObsidianError, ObsidianUnavailable
from core.deps import get_profile

logger = logging.getLogger(__name__)


def _session_dict(session: TrainingSession, ftp: int = 238) -> dict:
    from services.classification import intensity_from_session
    from services.segments import best_splits, format_pace

    return {
        "intensity": intensity_from_session(session, ftp),
        "reflection": session.reflection,
        "splits": [
            {"distance_km": s["distance_km"], "pace": format_pace(s["pace_s_per_km"])}
            for s in best_splits(session)
        ],
        "session_date": session.session_date,
        "discipline": session.discipline,
        "actual_type": session.actual_type,
        "duration_min": session.duration_min,
        "distance_km": session.distance_km,
        "avg_hr": session.avg_hr,
        "avg_watts": session.avg_watts,
        "normalized_power": session.normalized_power,
        "avg_pace_min_km": session.avg_pace_min_km,
        "tss": session.tss,
        "strava_activity_id": session.strava_activity_id,
        "week_number": session.week_number,
        "deviation_note": session.deviation_note,
    }


def _planned_dict(planned: PlannedSession | None) -> dict | None:
    if planned is None:
        return None
    from core.training_types import (
        extract_pace_bands, extract_segment_targets, intensity_for_type,
    )

    # Der langsamste genannte Pace-Bereich ist die Vorgabe fürs Ein- und
    # Auslaufen — nur so lassen sich auch diese Abschnitte bewerten.
    bands = extract_pace_bands(planned.details)
    easy = bands[-1] if len(bands) > 1 else None

    return {
        "discipline": planned.discipline,
        "easy_pace_low_s_per_km": easy[0] if easy else None,
        "easy_pace_high_s_per_km": easy[1] if easy else None,
        "training_type": planned.training_type,
        "intensity": intensity_for_type(planned.discipline, planned.training_type),
        "duration_min": planned.duration_min,
        "target_watts_low": planned.target_watts_low,
        "target_watts_high": planned.target_watts_high,
        "target_pace_low_s_per_km": planned.target_pace_low_s_per_km,
        "target_pace_high_s_per_km": planned.target_pace_high_s_per_km,
        "target_hr_zone": planned.target_hr_zone,
        "notes": planned.notes,
    }


def _find_planned(db: Session, session: TrainingSession) -> PlannedSession | None:
    """Zugeordnete Plan-Einheit.

    Bevorzugt die verbindliche Zuordnung aus der Klassifizierung. Solange die
    noch nicht existiert (Modul 4), wird provisorisch über Datum und Sportart
    gesucht, damit die Note schon jetzt einen Plan/Ist-Vergleich zeigt.
    """
    if session.planned_session_id:
        return db.query(PlannedSession).filter(
            PlannedSession.id == session.planned_session_id
        ).first()

    candidates = db.query(PlannedSession).filter(
        PlannedSession.planned_date == session.session_date
    ).all()
    if not candidates:
        return None
    same_discipline = [c for c in candidates if c.discipline == session.discipline]
    if same_discipline:
        return same_discipline[0]
    # Brick deckt Rad und Lauf ab — ein Rad-Segment darf dagegen gematcht werden.
    bricks = [c for c in candidates if c.discipline == "brick"]
    if bricks and session.discipline in ("bike", "run"):
        return bricks[0]
    return None


def _sync_reflection(session: TrainingSession, existing_note: str, content: str) -> str:
    """Reflexion zwischen App und Note abgleichen.

    Dreiwege-Vergleich gegen die zuletzt abgeglichene Fassung. Nur so lässt
    sich unterscheiden, welche Seite sich geändert hat — ohne diese Marke
    müsste man sich für eine Richtung entscheiden und würde die Änderungen
    der anderen jedes Mal verwerfen.

    Beide gleichzeitig geändert ist der einzige Fall, in dem etwas verloren
    ginge; dort gewinnt die Note, weil der Vault die sichtbare Fläche ist.
    """
    in_note = (notes.extract_reflection(existing_note) or "").strip()
    in_app = (session.reflection or "").strip()
    last = session.reflection_sync_hash

    note_hash = notes.content_hash(in_note) if in_note else None
    app_hash = notes.content_hash(in_app) if in_app else None

    if note_hash == app_hash:
        session.reflection_sync_hash = note_hash
        return content

    note_changed = note_hash != last
    app_changed = app_hash != last

    if note_changed and (in_note or not app_changed):
        # Im Vault getippt — in die Datenbank übernehmen.
        session.reflection = in_note or None
        session.reflection_updated_at = datetime.utcnow()
        session.reflection_sync_hash = note_hash
        return content

    if app_changed:
        # In der App getippt — in die Note schreiben.
        session.reflection_sync_hash = app_hash
        return notes.set_reflection(content, in_app)

    return content


def sync_session(
    db: Session,
    session: TrainingSession,
    client: ObsidianClient | None = None,
    commit: bool = True,
) -> dict:
    """Eine Einheit nach Obsidian schreiben. Wirft nicht — gibt Status zurück."""
    # Profil des Athleten liefert FTP, Zonen und die Vault-Anbindung. Ein
    # globaler Client würde die Notes aller Athleten in denselben Vault
    # schreiben — den der Installation.
    from services.obsidian.client import client_for_profile, vault_subdir_for

    profile = get_profile(db)
    client = client or client_for_profile(profile)
    if not client.enabled:
        return {"status": "disabled", "session_id": session.id}

    ftp = profile.ftp_watts if profile else 238
    subdir = vault_subdir_for(profile)

    session_data = _session_dict(session, ftp)

    # Der Pfad hängt jetzt an der Intensität. Ändert sie sich durch eine
    # Neuklassifizierung, wird die Note verschoben statt dupliziert —
    # sonst bliebe die alte Datei als Waise im falschen Ordner liegen.
    target_path = notes.note_path(
        session.discipline,
        session.session_date,
        session.strava_activity_id,
        subdir,
        session_id=session.id,
        intensity=session_data.get("intensity"),
    )
    old_path = session.obsidian_path
    path = target_path
    moved_from = None

    try:
        existing = client.get_note(path)
        if existing is None and old_path and old_path != target_path:
            # Note liegt noch unter dem alten Pfad — Inhalt übernehmen,
            # damit Reflexionen den Umzug überleben.
            existing = client.get_note(old_path)
            if existing is not None:
                moved_from = old_path

        planned = _find_planned(db, session)
        planned_data = _planned_dict(planned)

        # Abschnittsvorgaben passend zur Sportart dieser Einheit: bei einem
        # Brick liegen Rad- und Laufstruktur getrennt im Plan, und die
        # Radhälfte braucht die Wattblöcke, die Laufhälfte die Pace-Blöcke.
        if planned_data is not None:
            from core.training_types import extract_segment_targets
            planned_data["segment_targets"] = extract_segment_targets(
                planned.details,
                part=session.discipline if session.discipline in ("bike", "run") else None,
            )

        # Hauptteil-Pace und Brick-Gesamtdauer für die Plan/Ist-Tabelle.
        from services.segments import (
            format_pace, reference_split, structure_from_laps,
            structure_from_power, time_in_band,
        )

        structure = structure_from_laps(session)

        # Ohne Runden — outdoor die Lap-Taste vergessen, oder Auto-Lap nach
        # Distanz mitten durch die Intervalle — die Blöcke aus der
        # Leistungskurve lesen. Sonst stünde in der Note der Gesamtschnitt.
        if (
            structure is None
            and session.discipline in ("bike", "brick")
            and planned is not None
            and planned.target_watts_low
        ):
            structure = structure_from_power(session, planned.target_watts_low * 0.95)

        if planned is not None and planned.target_watts_low and session.discipline in ("bike", "brick"):
            minutes = time_in_band(session, planned.target_watts_low, planned.target_watts_high)
            if minutes:
                session_data["time_in_band_min"] = minutes
                session_data["target_band"] = (
                    f"{planned.target_watts_low}–{planned.target_watts_high or planned.target_watts_low} W"
                )

        if structure:
            session_data["structure"] = {
                key: {
                    "distance_km": part["distance_km"],
                    "pace": format_pace(part["pace_s_per_km"]),
                    "avg_hr": part["avg_hr"],
                    # Leistung und Dauer werden für die Rad-Zeilen gebraucht:
                    # ohne sie fällt die Tabelle auf den Gesamtschnitt zurück.
                    "avg_watts": part.get("avg_watts"),
                    "seconds": part["seconds"],
                    "laps": part["laps"],
                }
                for key, part in structure.items()
                if isinstance(part, dict) and part
            }
            # Transparent halten, woher die Struktur stammt: aus den Runden
            # der Uhr oder aus der Leistungskurve rekonstruiert.
            session_data["structure_source"] = structure.get("source", "laps")

        ref = reference_split(session)
        if ref:
            session_data["reference_split"] = {
                "distance_km": ref["distance_km"],
                "pace": format_pace(ref["pace_s_per_km"]),
            }
        if planned is not None and planned.discipline == "brick" and session.discipline in ("bike", "run"):
            from services.classification import brick_components
            components = brick_components(db, planned, session)
            if len(components) > 1:
                session_data["brick_total_min"] = sum(c.duration_min or 0 for c in components)
                session_data["brick_breakdown"] = ", ".join(
                    f"{'Rad' if c.discipline == 'bike' else 'Lauf'} {c.duration_min}"
                    for c in components if c.duration_min
                )

        if existing is None:
            content = notes.render_new_note(session_data, planned_data)
        else:
            # Hat der Athlet den Managed Block gelöscht, war das Absicht —
            # dann wird die Note in Ruhe gelassen, aber als synchronisiert
            # markiert, damit der Reconcile-Job sie nicht ewig erneut anfasst.
            if notes.MARKER_START not in existing:
                # Liegt sie noch am alten Pfad, bleibt sie dort: verschieben
                # wäre ein Eingriff in eine Note, die der Athlet übernommen hat.
                actual_path = moved_from or path
                session.obsidian_path = actual_path
                session.obsidian_synced_at = datetime.utcnow()
                session.obsidian_content_hash = notes.content_hash(existing)
                if commit:
                    db.commit()
                logger.info("Note %s ohne Managed Block — unangetastet gelassen", actual_path)
                return {
                    "status": "skipped_block_removed",
                    "path": actual_path,
                    "session_id": session.id,
                }
            content = notes.merge_note(existing, session_data, planned_data)
            content = _sync_reflection(session, existing, content)

        if existing is not None and content == existing and not moved_from:
            written = False
        else:
            client.put_note(path, content)
            written = True

        # Erst nach erfolgreichem Schreiben die alte Datei entfernen —
        # bei einem Fehler dazwischen bleibt lieber eine Kopie zu viel
        # als gar keine Note.
        if moved_from:
            try:
                client.delete_note(moved_from)
            except ObsidianError as e:
                logger.warning("Alte Note %s konnte nicht entfernt werden: %s", moved_from, e)

        session.obsidian_path = path
        session.obsidian_synced_at = datetime.utcnow()
        session.obsidian_content_hash = notes.content_hash(content)
        if commit:
            db.commit()

        return {
            "status": "moved" if moved_from else ("written" if written else "unchanged"),
            "path": path,
            "moved_from": moved_from,
            "session_id": session.id,
        }

    except ObsidianUnavailable as e:
        # obsidian_synced_at bleibt NULL — der Reconcile-Job versucht es erneut.
        logger.warning("Obsidian nicht erreichbar für Session %s: %s", session.id, e)
        return {"status": "unavailable", "session_id": session.id, "error": str(e)}
    except ObsidianError as e:
        logger.error("Obsidian-Fehler für Session %s: %s", session.id, e)
        return {"status": "error", "session_id": session.id, "error": str(e)}
    except Exception as e:  # pragma: no cover - Sync darf nie den Aufrufer reißen
        logger.exception("Unerwarteter Fehler beim Obsidian-Sync von Session %s", session.id)
        return {"status": "error", "session_id": session.id, "error": str(e)}


def sync_session_by_id(db: Session, session_id: int) -> dict:
    session = db.query(TrainingSession).filter(TrainingSession.id == session_id).first()
    if not session:
        return {"status": "not_found", "session_id": session_id}
    return sync_session(db, session)


def pending_sessions(db: Session, days: int = 30, limit: int = 50) -> list[TrainingSession]:
    """Die Outbox: Einheiten, die noch nie erfolgreich synchronisiert wurden."""
    cutoff = date.today() - timedelta(days=days)
    return (
        db.query(TrainingSession)
        .filter(
            TrainingSession.obsidian_synced_at == None,  # noqa: E711
            TrainingSession.deleted_at == None,  # noqa: E711
            TrainingSession.session_date >= cutoff,
        )
        .order_by(TrainingSession.session_date.desc())
        .limit(limit)
        .all()
    )


def sync_pending(db: Session, days: int = 30, limit: int = 50) -> dict:
    """Offene Syncs abarbeiten. Bricht beim ersten Ausfall ab.

    Wenn Obsidian weg ist, sind auch alle folgenden Versuche vergeblich —
    weiterzulaufen würde nur Timeouts aufaddieren und den Circuit öffnen.
    """
    # Client des Athleten, nicht der der Installation. Ein `ObsidianClient()`
    # ohne Argumente greift auf die .env zurück — und die zeigt auf genau einen
    # Vault, den des Betreibers. Jede Notiz jedes Athleten wäre dort gelandet.
    #
    # `sync_session` wählt den richtigen Client bereits selbst, sobald keiner
    # übergeben wird; die Absicherung wurde hier durch das Mitgeben eines
    # eigenen Clients ausgehebelt.
    from core.deps import get_profile
    from services.obsidian.client import client_for_profile

    client = client_for_profile(get_profile(db))
    if not client.enabled:
        return {"status": "disabled", "written": 0, "pending": 0}

    sessions = pending_sessions(db, days=days, limit=limit)
    counts: dict[str, int] = {}
    for session in sessions:
        result = sync_session(db, session, client=client)
        counts[result["status"]] = counts.get(result["status"], 0) + 1
        if result["status"] == "unavailable":
            break

    return {
        "status": "ok",
        "processed": sum(counts.values()),
        "by_status": counts,
        "pending_remaining": len(pending_sessions(db, days=days, limit=limit)),
    }
