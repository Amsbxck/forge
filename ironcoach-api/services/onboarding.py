"""Einstiegsstrecke für neue Athleten.

Die Bausteine existieren alle — Konto, Ziel, Testwoche, Zonenableitung,
erster Plan —, aber nichts führt jemanden hindurch. Ein neuer Nutzer sieht
sonst eine leere Oberfläche und muss die Reihenfolge erraten.

Der Zustand wird bewusst aus den vorhandenen Daten abgeleitet statt in einem
Fortschrittsfeld mitgeführt: ein solches Feld läuft irgendwann aus dem Tritt,
wenn jemand ein Ziel wieder löscht oder die Zonen von Hand setzt.
"""

import logging
from datetime import date

from sqlalchemy.orm import Session

from models import PlannedSession, TrainingSession, WeeklyPlan

logger = logging.getLogger(__name__)


def _benchmark_plan(db: Session) -> WeeklyPlan | None:
    return (
        db.query(WeeklyPlan)
        .filter(WeeklyPlan.plan_phase == "Benchmark")
        .order_by(WeeklyPlan.generated_at.desc())
        .first()
    )


def _training_plan(db: Session) -> WeeklyPlan | None:
    """Ein echter Wochenplan — die Testwoche zählt nicht."""
    return (
        db.query(WeeklyPlan)
        .filter(WeeklyPlan.plan_phase != "Benchmark")
        .order_by(WeeklyPlan.generated_at.desc())
        .first()
    )


def _completed_tests(db: Session, since: date | None) -> dict:
    """Absolvierte Testeinheiten seit Beginn der Testwoche.

    Als Test gilt eine Rad- oder Laufeinheit mit aufgezeichneten Rohdaten —
    ohne die lässt sich ohnehin nichts ableiten.
    """
    if since is None:
        return {"bike": 0, "run": 0}

    sessions = (
        db.query(TrainingSession)
        .filter(
            TrainingSession.session_date >= since,
            TrainingSession.discipline.in_(("bike", "run")),
            TrainingSession.deleted_at == None,  # noqa: E711
        )
        .all()
    )
    counts = {"bike": 0, "run": 0}
    for session in sessions:
        streams = session.streams or {}
        if streams.get("watts") or streams.get("speed") or streams.get("hr"):
            counts[session.discipline] = counts.get(session.discipline, 0) + 1
    return counts


def status(db: Session, user=None) -> dict:
    from core.deps import get_active_goal, get_profile

    profile = get_profile(db, user)
    goal = get_active_goal(db, user)
    bench_plan = _benchmark_plan(db)
    train_plan = _training_plan(db)

    needs_bike = goal is None or goal.sport == "triathlon"
    tests = _completed_tests(db, bench_plan.week_start if bench_plan else None)
    tests_done = tests.get("run", 0) > 0 and (not needs_bike or tests.get("bike", 0) > 0)

    # "manual" zählt mit: wer seine Werte selbst gemessen und eingetragen
    # hat, ist genauso fertig wie nach einem Benchmark. Offen ist der Schritt
    # nur bei den Platzhaltern eines frischen Kontos.
    zones_measured = bool(profile and profile.zones_source in ("benchmark", "manual"))

    steps = [
        {
            "key": "account",
            "label": "Konto angelegt",
            "done": user is not None,
            "detail": (user.name or user.email) if user else None,
        },
        {
            "key": "goal",
            "label": "Ziel gewählt",
            "done": goal is not None,
            "detail": f"{goal.label} am {goal.race_date}" if goal else None,
            "hint": "Sportart und Distanz bestimmen Planlänge und Phasen.",
            "action": "/races",
        },
        {
            "key": "benchmark_plan",
            "label": "Testwoche geplant",
            "done": bench_plan is not None,
            "detail": f"ab {bench_plan.week_start}" if bench_plan else None,
            "hint": "Eine Woche mit Testeinheiten, aus denen die Zonen hervorgehen.",
            "action": "/races",
        },
        {
            "key": "benchmark_done",
            "label": "Tests absolviert",
            "done": tests_done,
            # Nur zeigen, was für dieses Ziel gebraucht wird — bei einem
            # Laufziel wäre "0 Rad" eine Aufgabe, die es gar nicht gibt.
            "detail": (
                " · ".join(
                    [f"Lauftest {'✓' if tests.get('run', 0) else 'offen'}"]
                    + ([f"Radtest {'✓' if tests.get('bike', 0) else 'offen'}"] if needs_bike else [])
                )
                if bench_plan else None
            ),
            "hint": "Nach dem Hochladen oder Strava-Abgleich erkennt die App die Tests selbst.",
        },
        {
            "key": "zones",
            "label": "Zonen hinterlegt",
            "done": zones_measured,
            "detail": (
                f"FTP {profile.ftp_watts} W · HFmax {profile.max_hr}"
                # Herkunft ausdrücklich benennen: „gemessen" über selbst
                # eingetragenen Zahlen wäre eine falsche Zusicherung — der
                # Athlet soll sehen, dass die Testwoche sie noch bestätigt.
                + (" (gemessen)" if profile.zones_source == "benchmark"
                   else " (selbst eingetragen)")
                if profile and zones_measured else
                ("noch Platzhalterwerte" if profile else None)
            ),
            "hint": (
                "Aus der Testwoche werden sie automatisch übernommen. "
                "Selbst eingetragene Werte bleiben dabei erhalten und werden "
                "nicht überschrieben."
            ),
            "action": "/races",
        },
        {
            "key": "plan",
            "label": "Erster Wochenplan",
            "done": train_plan is not None,
            "detail": f"Woche {train_plan.week_number}" if train_plan else None,
            "hint": "Der Coach plant auf Basis deiner gemessenen Werte.",
            "action": "/plan",
        },
    ]

    next_step = next((s["key"] for s in steps if not s["done"]), None)
    return {
        "complete": next_step is None,
        "next": next_step,
        "steps": steps,
    }
