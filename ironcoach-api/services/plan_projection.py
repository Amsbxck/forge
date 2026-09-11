"""Projiziert WeeklyPlan.plan_content["days"] in die Tabelle planned_sessions.

Warum überhaupt projizieren statt plan_content zu ersetzen:
plan_content ist der Claude-Rohoutput und bleibt die Quelle für Anzeige und PDF.
Die Projektion gibt jeder geplanten Einheit zusätzlich eine DB-Identität, damit
Drag & Drop sie verschieben und der Ist/Soll-Abgleich sie referenzieren kann.

Die Projektion ist idempotent: sie ersetzt die Zeilen genau eines Plans.

Wichtig: Solange Migration 005 nicht gelaufen ist, existiert die Tabelle nicht.
project_plan() darf deshalb unter keinen Umständen die Plangenerierung
mitreißen — sie fängt das ab und loggt nur.
"""

import logging
from datetime import date, datetime, timedelta

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from models import PlannedSession, TrainingSession, WeeklyPlan
from core.training_types import (
    default_training_type,
    extract_targets_from_details,
    infer_training_type,
    is_valid_training_type,
    normalize_discipline,
)

logger = logging.getLogger(__name__)

DAY_ORDER = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]

_table_available: bool | None = None


def planned_sessions_available(db: Session) -> bool:
    """Existiert die Tabelle? Ergebnis wird pro Prozess gecacht."""
    global _table_available
    if _table_available is None:
        try:
            _table_available = inspect(db.get_bind()).has_table("planned_sessions")
        except Exception as e:  # pragma: no cover - Infrastrukturfehler
            logger.warning("Konnte planned_sessions nicht prüfen: %s", e)
            _table_available = False
        if not _table_available:
            logger.info(
                "Tabelle planned_sessions fehlt — Projektion übersprungen. "
                "Migration 005 ausführen, um Drag&Drop-Persistenz zu aktivieren."
            )
    return _table_available


def _parse_date(value, fallback: date | None) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.strptime(value[:10], "%Y-%m-%d").date()
        except ValueError:
            pass
    return fallback


def _num(value) -> float | None:
    """Zahl aus Claude-Output — akzeptiert auch "145" als String."""
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip().replace(",", "."))
        except ValueError:
            return None
    return None


def _int(value) -> int | None:
    n = _num(value)
    return int(round(n)) if n is not None else None


def day_to_row(day: dict, plan: WeeklyPlan, index: int) -> dict | None:
    """Ein Tag aus plan_content → Spaltenwerte für planned_sessions.

    Verträgt beide Schema-Generationen: neue Pläne liefern training_type und
    targets, alte nur session_type + details-Freitext. Für alte Pläne werden
    Zielwerte best-effort aus dem Text extrahiert (fehlend statt geraten).
    """
    raw_discipline = str(day.get("session_type") or "").strip()
    discipline = normalize_discipline(raw_discipline)
    if discipline is None:
        # Unbekannte Sportart nicht verwerfen — der Tag existiert im Plan und
        # soll im Kalender verschiebbar bleiben.
        logger.warning(
            "Sportart '%s' (Plan %s) nicht zuordenbar — als 'rest' projiziert",
            raw_discipline, plan.id,
        )
        discipline = "rest"

    # Datum: bevorzugt aus dem Tag, sonst aus Wochenstart + Wochentagsposition.
    fallback = None
    if plan.week_start:
        day_name = day.get("day")
        offset = DAY_ORDER.index(day_name) if day_name in DAY_ORDER else index
        fallback = plan.week_start + timedelta(days=min(offset, 6))
    planned_date = _parse_date(day.get("date"), fallback)
    if planned_date is None:
        logger.warning("Tag ohne auflösbares Datum in Plan %s übersprungen", plan.id)
        return None

    training_type = day.get("training_type")
    if not is_valid_training_type(discipline, training_type):
        if training_type:
            logger.debug(
                "training_type '%s' passt nicht zu '%s' (Plan %s) — Fallback",
                training_type, discipline, plan.id,
            )
        # Alt-Pläne tragen den Typ oft im Freitext — im Workout-Namen, in der
        # Struktur ("Laufbahn VO2max Intervalle") oder in der Notiz. Alle
        # Textfelder durchsuchen, bevor pauschal gedefaultet wird.
        detail_texts: list[str | None] = []
        raw_details = day.get("details")
        if isinstance(raw_details, dict):
            for key in ("workout", "typ", "struktur", "beschreibung", "ziel"):
                value = raw_details.get(key)
                if isinstance(value, str):
                    detail_texts.append(value)
        training_type = infer_training_type(
            discipline, raw_discipline, *detail_texts, day.get("notes")
        ) or default_training_type(discipline)

    details = day.get("details") if isinstance(day.get("details"), dict) else None
    targets = dict(day.get("targets") or {}) if isinstance(day.get("targets"), dict) else {}

    # Lücken aus dem Fließtext auffüllen statt die Extraktion ganz zu
    # überspringen: bei Bricks liefert Claude oft Watt und TSS im
    # targets-Objekt, während die Ziel-Pace nur in details.run.pace steht.
    # Ohne das Auffüllen bliebe das Pace-Zielband leer und jeder Vergleich
    # gegen die tatsächliche Pace unmöglich.
    extracted = extract_targets_from_details(details)
    for key, value in extracted.items():
        if targets.get(key) in (None, ""):
            targets[key] = value

    return {
        "plan_id": plan.id,
        # Die Zuordnung erbt vom Plan statt neu aufgelöst zu werden: eine
        # projizierte Einheit gehört zwangsläufig dem, dem der Plan gehört.
        "user_id": plan.user_id,
        "week_number": plan.week_number,
        "planned_date": planned_date,
        "day_name": day.get("day"),
        "discipline": discipline,
        "training_type": training_type,
        "duration_min": _int(day.get("duration_min")),
        "target_tss": _num(targets.get("tss")),
        "target_watts_low": _int(targets.get("watts_low")),
        "target_watts_high": _int(targets.get("watts_high")),
        "target_pace_low_s_per_km": _int(targets.get("pace_low_s_per_km")),
        "target_pace_high_s_per_km": _int(targets.get("pace_high_s_per_km")),
        "target_hr_zone": targets.get("hr_zone"),
        "target_distance_km": _num(targets.get("distance_km")),
        "details": details,
        "notes": day.get("notes"),
        "day_index": index,
    }


def project_plan(db: Session, plan: WeeklyPlan, commit: bool = True) -> int:
    """Schreibt die Tage eines Plans nach planned_sessions.

    Ersetzt bestehende Zeilen desselben Plans, damit ein Re-Run keine
    Duplikate erzeugt. Gibt die Anzahl geschriebener Zeilen zurück; 0 heißt
    "nichts projiziert" (Tabelle fehlt, keine Tage, oder Fehler).
    """
    if not planned_sessions_available(db):
        return 0

    days = (plan.plan_content or {}).get("days") or []
    if not days:
        logger.info("Plan %s hat keine days — nichts zu projizieren", plan.id)
        return 0

    try:
        # Bewusst ORM-Delete statt Bulk-Delete: bei 7 Zeilen pro Plan
        # irrelevant für die Performance, hält aber die Identity Map sauber,
        # wenn in derselben Session direkt neu projiziert wird.
        #
        # Nicht nur die Zeilen desselben Plans, sondern **alle** dieser Woche:
        # Ein neu erstellter Plan bekommt eine neue plan_id, und die alte
        # Projektion blieb dadurch stehen. In den Daten fanden sich Wochen mit
        # drei Plänen à sieben Einheiten — jede Auswertung von „geplant gegen
        # erledigt" zählte dann gegen das Dreifache.
        # Der Nutzerfilter steht ausdrücklich da, obwohl der Mandantenschutz
        # beim Lesen ohnehin greift: Läuft die Projektion aus einem
        # Hintergrundjob ohne gesetzten Kontext, sammelte sie sonst die
        # Planeinheiten **aller** Athleten dieser Wochennummer ein — und
        # löschte sie im nächsten Schritt.
        existing_query = db.query(PlannedSession).filter(
            PlannedSession.week_number == plan.week_number
        )
        if plan.user_id is not None:
            existing_query = existing_query.filter(PlannedSession.user_id == plan.user_id)
        existing = existing_query.all()

        # Was der Abgleich erarbeitet hat, ist nicht aus dem Plan ableitbar und
        # muss die Neuprojektion überleben: Ohne Übernahme setzt jede
        # Neuerstellung die Woche auf „nichts erledigt" zurück.
        uebernahme = {
            (row.planned_date, row.discipline): {
                "status": row.status,
                "matched_session_id": row.matched_session_id,
                "replacement": row.replacement,
                "replacement_min": row.replacement_min,
                "moved_from_date": row.moved_from_date,
            }
            for row in existing
            if row.status != "planned" or row.matched_session_id is not None
        }
        # Die Rückverweise aus training_sessions werden beim Löschen auf NULL
        # gesetzt (ondelete=SET NULL). Deshalb hier die betroffenen Einheiten
        # **namentlich** merken, statt sie später über Datum und Sportart neu
        # zu suchen: Diese Suche traf jede passende Einheit, auch die eines
        # anderen Athleten, der am selben Tag dieselbe Sportart trainiert hat —
        # und ein Massen-UPDATE unterliegt dem Mandantenfilter nicht. Wer schon
        # zugeordnet war, ist dagegen zweifelsfrei bekannt.
        alt_ids = [row.id for row in existing]
        rueckverweise: dict[int, list[int]] = {}
        if alt_ids:
            for sitzung_id, ps_id in (
                db.query(TrainingSession.id, TrainingSession.planned_session_id)
                .filter(TrainingSession.planned_session_id.in_(alt_ids))
                .all()
            ):
                rueckverweise.setdefault(ps_id, []).append(sitzung_id)
        schluessel_je_alt_id = {
            row.id: (row.planned_date, row.discipline) for row in existing
        }
        for row in existing:
            db.delete(row)
        db.flush()

        written = 0
        neue_zeilen: dict[tuple, PlannedSession] = {}
        for index, day in enumerate(days):
            if not isinstance(day, dict):
                continue
            row = day_to_row(day, plan, index)
            if row is None:
                continue
            neu = PlannedSession(**row)
            schluessel = (neu.planned_date, neu.discipline)
            if schluessel in uebernahme:
                for feld, wert in uebernahme[schluessel].items():
                    setattr(neu, feld, wert)
            db.add(neu)
            neue_zeilen.setdefault(schluessel, neu)
            written += 1
        db.flush()

        # Rückverweise umhängen — nur die vorher gemerkten Einheiten, über
        # ihren Primärschlüssel. Findet sich in der neuen Fassung keine Zeile
        # mit gleichem Tag und gleicher Sportart, bleibt die Zuordnung leer:
        # Die geplante Einheit gibt es dann schlicht nicht mehr.
        for alt_id, sitzungs_ids in rueckverweise.items():
            ziel = neue_zeilen.get(schluessel_je_alt_id.get(alt_id))
            if ziel is None or not sitzungs_ids:
                continue
            db.query(TrainingSession).filter(
                TrainingSession.id.in_(sitzungs_ids)
            ).update({"planned_session_id": ziel.id}, synchronize_session=False)

        if commit:
            db.commit()
        logger.info("Plan %s projiziert: %s Einheiten", plan.id, written)
        return written
    except Exception as e:
        # Projektion darf die Plangenerierung nie mitreißen — der Plan selbst
        # ist an dieser Stelle bereits committed.
        db.rollback()
        logger.error("Projektion von Plan %s fehlgeschlagen: %s", plan.id, e)
        return 0


def backfill_all(db: Session, limit: int | None = None) -> dict:
    """Projiziert bestehende Pläne nachträglich.

    Gedacht als einmaliger Aufruf nach der Migration. Pläne ohne days
    (abgebrochene Chat-Pläne) werden übersprungen, nicht gelöscht.
    """
    if not planned_sessions_available(db):
        return {"projected_plans": 0, "sessions": 0, "skipped": 0, "reason": "table_missing"}

    query = db.query(WeeklyPlan).order_by(WeeklyPlan.week_number.asc())
    if limit:
        query = query.limit(limit)

    projected, total, skipped = 0, 0, 0
    for plan in query.all():
        written = project_plan(db, plan, commit=False)
        if written:
            projected += 1
            total += written
        else:
            skipped += 1
    db.commit()
    return {"projected_plans": projected, "sessions": total, "skipped": skipped}
