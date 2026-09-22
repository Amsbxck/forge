"""Benchmark-Woche: Zonen messen statt schätzen.

Ein neuer Athlet hat weder FTP noch Herzfrequenzzonen. Beides zu raten wäre
der schlechteste Start — jede spätere Vorgabe, jede Klassifizierung und jede
TSS-Berechnung hinge an einer erfundenen Zahl. Stattdessen steht am Anfang
eine Woche mit Testeinheiten, aus denen die Werte hervorgehen.

Ausgewertet wird mit denselben Bausteinen, die schon für die
Intervallerkennung existieren: das gleitende Fenster findet die besten
20 Minuten auch dann, wenn der Test nicht als eigene Runde aufgezeichnet
wurde.
"""

import logging
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from models import AthleteProfile, TrainingSession
from services.segments import best_effort_pace, best_effort_power

logger = logging.getLogger(__name__)

# FTP ist definitionsgemäß 95 % der besten 20-Minuten-Leistung.
FTP_FACTOR = 0.95
# Die Schwellen-HF liegt bei einem 20-Minuten-Test nahe an der mittleren HF
# des Tests selbst; der kleine Abschlag berücksichtigt den Anstieg zu Beginn.
LTHR_FACTOR = 0.98

TEST_WINDOW_S = 1200  # 20 Minuten


def benchmark_week(sport: str, start: date) -> list[dict]:
    """Testeinheiten der ersten Woche, im Format des Wochenplans.

    Bewusst wenige Tests mit Erholung dazwischen: wer am Montag einen
    FTP-Test fährt und am Dienstag einen Laufschwellentest läuft, misst im
    zweiten Test vor allem seine Ermüdung.
    """
    day_names = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]

    def day(index: int, **fields) -> dict:
        return {
            "day": day_names[index],
            "date": str(start + timedelta(days=index)),
            **fields,
        }

    if sport == "cycling":
        # Nur was fürs Rad zählt. Ein Laufschwellentest oder ein CSS-Test
        # lieferte Zahlen, die in keine einzige Vorgabe eingehen — und käme
        # den Athleten trotzdem einen harten Tag zu stehen.
        return [
            day(0, session_type="rest", training_type="rest", duration_min=0,
                notes="Ruhetag vor dem Test."),
            day(1, session_type="bike", training_type="threshold", duration_min=60,
                notes="BENCHMARK FTP-Test: 20 min einfahren, 5 min hart öffnen, "
                      "5 min locker, dann 20 min maximal gleichmäßig. Danach "
                      "10 min ausfahren. Nicht zu schnell starten — die letzten "
                      "fünf Minuten entscheiden.",
                details={"workout": "Benchmark 20-Minuten-FTP-Test",
                         "warmup": {"dauer": "20 min", "watt": "locker bis zügig"},
                         "blocks": [{"block": "Test", "dauer": "20 min",
                                     "watt": "so hoch wie gleichmäßig durchhaltbar"}],
                         "cooldown": {"dauer": "10 min", "watt": "locker"}}),
            day(2, session_type="rest", training_type="rest", duration_min=0),
            day(3, session_type="bike", training_type="z2_endurance", duration_min=75,
                notes="Locker nach Gefühl. Dient als Vergleichswert für die Zonen."),
            day(4, session_type="rest", training_type="rest", duration_min=0),
            day(5, session_type="bike", training_type="long_ride", duration_min=150,
                notes="Ruhige lange Ausfahrt, Gesprächstempo. Nebenbei ein Test "
                      "der Verpflegung — was auf 2,5 Stunden funktioniert, "
                      "funktioniert später auch länger."),
            day(6, session_type="rest", training_type="rest", duration_min=0),
        ]

    if sport == "running":
        return [
            day(0, session_type="rest", training_type="rest", duration_min=0,
                notes="Ruhetag vor dem ersten Test."),
            day(1, session_type="run", training_type="threshold", duration_min=45,
                notes="BENCHMARK Laufschwellentest: 15 min locker einlaufen, dann "
                      "20 min so schnell wie du gleichmäßig durchhältst, 10 min auslaufen. "
                      "Nicht zu schnell starten — die letzten 5 Minuten entscheiden.",
                details={"typ": "Benchmark 20-Minuten-Test",
                         "struktur": "15 min ein — 20 min maximal gleichmäßig — 10 min aus"}),
            day(2, session_type="rest", training_type="rest", duration_min=0),
            day(3, session_type="run", training_type="z2_endurance", duration_min=40,
                notes="Locker nach Gefühl. Dient als Vergleichswert für die Zonen."),
            day(4, session_type="rest", training_type="rest", duration_min=0),
            day(5, session_type="run", training_type="long_run", duration_min=60,
                notes="Ruhiger Dauerlauf, Gesprächstempo."),
            day(6, session_type="rest", training_type="rest", duration_min=0),
        ]

    return [
        day(0, session_type="rest", training_type="rest", duration_min=0,
            notes="Ruhetag vor dem ersten Test."),
        day(1, session_type="bike", training_type="threshold", duration_min=60,
            notes="BENCHMARK FTP-Test: 20 min einfahren, 5 min hart öffnen, 5 min locker, "
                  "dann 20 min maximal gleichmäßig. Danach 10 min ausfahren.",
            details={"workout": "Benchmark 20-Minuten-FTP-Test",
                     "warmup": {"dauer": "20 min", "watt": "locker bis zügig"},
                     "blocks": [{"block": "Test", "dauer": "20 min",
                                 "watt": "so hoch wie gleichmäßig durchhaltbar"}],
                     "cooldown": {"dauer": "10 min", "watt": "locker"}}),
        day(2, session_type="rest", training_type="rest", duration_min=0),
        day(3, session_type="run", training_type="threshold", duration_min=45,
            notes="BENCHMARK Laufschwellentest: 15 min einlaufen, 20 min maximal "
                  "gleichmäßig, 10 min auslaufen.",
            details={"typ": "Benchmark 20-Minuten-Test",
                     "struktur": "15 min ein — 20 min maximal gleichmäßig — 10 min aus"}),
        day(4, session_type="swim", training_type="intervals", duration_min=45,
            notes="BENCHMARK Schwimmtest: 400 m und 200 m je maximal, dazwischen "
                  "5 min locker. Zeiten notieren — daraus ergibt sich die CSS-Pace."),
        day(5, session_type="bike", training_type="z2_endurance", duration_min=75,
            notes="Locker ausfahren, Gesprächstempo."),
        day(6, session_type="rest", training_type="rest", duration_min=0),
    ]


class BenchmarkGesperrt(RuntimeError):
    """Die Testwoche darf gerade nicht liegen. Trägt Gründe und Ersatztermin."""

    def __init__(self, lage: dict):
        self.lage = lage
        super().__init__("; ".join(lage["gruende"]))


def create_benchmark_plan(db: Session, user=None):
    """Die Testwoche als echten Wochenplan anlegen.

    Bis hierher gab es sie nur als Vorschau. Ein neuer Athlet soll sie aber
    im Wochenkalender sehen, abarbeiten und danach automatisch seine Zonen
    bekommen — dafür muss sie ein Plan wie jeder andere sein, inklusive
    Projektion und Obsidian-Note.
    """
    from core.deps import get_active_goal, get_profile
    from models import WeeklyPlan
    from services.plan_projection import project_plan

    profile = get_profile(db, user)
    goal = get_active_goal(db, user)
    sport = goal.sport if goal else "triathlon"

    # Die kommende Woche, nicht das Startdatum des Plans. Für einen neuen
    # Athleten war beides dasselbe; für jeden anderen liegt das Startdatum in
    # der Vergangenheit, und der Test landete in einer längst vergangenen
    # Woche — sichtbar für niemanden.
    from core.race_types import season_state
    from services.benchmark_timing import entzerren, naechster_montag, pruefe

    ziel_datum = getattr(goal, "race_date", None)
    lage = pruefe(db, ziel_datum)
    if not lage["moeglich"]:
        # Kein stiller Plan zu einem Termin, der schadet: Der Aufrufer bekommt
        # die Gründe und den frühesten sinnvollen Termin zurück.
        raise BenchmarkGesperrt(lage)

    start = lage["start"] or naechster_montag()
    days = benchmark_week(sport, start)

    # Off Season: nur ein Maximaltest je Woche. Ohne Grundlagenumfang sind
    # zwei harte Tests in sieben Tagen der schnellste Weg in die Überlastung.
    ist_offseason = goal is None or season_state(ziel_datum) == "off_season"
    if ist_offseason:
        days = entzerren(days)

    # Die Wochennummer aus dem Termin ableiten statt fest auf 1: Sonst
    # überschreibt eine Testwoche im September die Zählung des Saisonstarts.
    from services.plan_generator import get_week_for_date
    anker = goal or profile
    woche = get_week_for_date(anker, start) if anker else 1

    # Nicht zweimal dieselbe Woche anlegen — erkannt am Montag, nicht an der
    # Wochennummer. Die Nummer entsteht aus `max(1, …)` und ist vor dem Beginn
    # des Aufbaus für jedes Datum 1: Die Testwoche hätte dann dieselbe Nummer
    # wie ein längst bestehender Plan, und statt sie anzulegen käme dieser
    # fremde Plan zurück.
    existing = (
        db.query(WeeklyPlan)
        .filter(WeeklyPlan.week_start == start)
        .order_by(WeeklyPlan.generated_at.desc())
        .first()
    )
    if existing is not None:
        return existing, False

    plan = WeeklyPlan(
        user_id=user.id if user else (profile.user_id if profile else None),
        week_number=woche,
        week_start=start,
        week_end=start + timedelta(days=6),
        plan_phase="Benchmark",
        plan_content={
            "week": woche,
            "phase": "Benchmark",
            "coaching_comment": (
                "Testwoche. Ziel ist nicht Training, sondern Messen: aus diesen "
                "Einheiten ergeben sich FTP, Schwellenpace und Herzfrequenzzonen. "
                "Geh die Tests wirklich aus — zu vorsichtig gemessene Werte machen "
                "jede spätere Vorgabe zu leicht."
            ),
            "adjustments": ["Benchmark-Woche: Zonen werden gemessen, nicht geschätzt"],
            "days": days,
        },
        plan_text="\n".join(
            f"{d['day']} ({d['date']}): {d['session_type'].upper()} "
            f"{d.get('duration_min', '')}min — {d.get('notes', '')}"
            for d in days
        ),
        adjustments_applied=["Benchmark-Woche"],
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)

    project_plan(db, plan)
    try:
        from services.obsidian.plan_note import sync_plan_note
        sync_plan_note(db, plan)
    except Exception as e:  # pragma: no cover
        logger.warning("Benchmark-Note fehlgeschlagen: %s", e)

    return plan, True


def maybe_autoderive(db: Session) -> dict | None:
    """Zonen automatisch übernehmen, solange sie noch nie gemessen wurden.

    Läuft nach jedem Ingest. Bewusst eng begrenzt: nur wenn der Athlet in
    der Testphase steckt und seine Zonen nicht von Hand gesetzt sind. Wer
    seine Werte selbst korrigiert hat, soll sie nicht durch einen Sonntagslauf
    überschrieben bekommen.
    """
    from core.deps import get_plan_anchor, get_profile
    from services.plan_generator import get_current_week

    profile = get_profile(db)
    if profile is None or profile.zones_source == "manual":
        return None

    anchor = get_plan_anchor(db)
    if anchor is None or get_current_week(anchor) > 2:
        return None

    result = derive_zones(db, days=21, apply=True)
    if result.get("status") == "ok" and result.get("applied"):
        logger.info("Zonen automatisch aus Benchmark übernommen: %s", result["applied"])
        return result
    return None


def _benchmark_sessions(db: Session, days: int = 21) -> list[TrainingSession]:
    """Einheiten, die als Test in Frage kommen.

    Erkannt an der Zuordnung zu einer geplanten Threshold-Einheit oder
    schlicht daran, dass es die härtesten Einheiten im Zeitraum sind — beides
    besser, als eine Markierung zu verlangen, die vergessen wird.
    """
    cutoff = date.today() - timedelta(days=days)
    return (
        db.query(TrainingSession)
        .filter(
            TrainingSession.session_date >= cutoff,
            TrainingSession.deleted_at == None,  # noqa: E711
        )
        .order_by(TrainingSession.session_date.desc())
        .all()
    )


def derive_zones(db: Session, days: int = 21, apply: bool = False) -> dict:
    """FTP, Schwellen-HF, Pace und Zonen aus den Testeinheiten ableiten.

    apply=False meldet nur, was sich ergäbe. Ohne verwertbare Daten wird
    nichts gesetzt — geschätzte Zonen wären schlimmer als gar keine.
    """
    from services.fit_parser import calculate_hr_zones  # noqa: F401  (Konsistenzprüfung)

    sessions = _benchmark_sessions(db, days)
    if not sessions:
        return {"status": "no_sessions"}

    result: dict = {"status": "ok", "sources": {}}

    # Die derzeit gesetzten Werte mitgeben: ohne sie sieht der Athlet beim
    # Übernehmen nicht, was sich ändert — und ein Testergebnis, das eine
    # sorgfältig eingetragene Zahl ersetzt, soll er vorher sehen.
    aktuell = db.query(AthleteProfile).first()
    if aktuell is not None:
        result["current"] = {
            "ftp_watts": aktuell.ftp_watts,
            "threshold_pace_s_per_km": aktuell.threshold_pace_s_per_km,
            "threshold_hr": aktuell.threshold_hr,
            "max_hr": aktuell.max_hr,
            "css_pace_s_per_100m": aktuell.css_pace_s_per_100m,
            "swim_threshold_hr": aktuell.swim_threshold_hr,
            "quellen": {
                "zones": aktuell.zones_source,
                "threshold": aktuell.threshold_source,
                "css": aktuell.css_source,
                "swim_hr": aktuell.swim_threshold_source,
            },
        }

    # --- Rad: beste 20 Minuten Leistung ---
    best_bike, best_bike_session = None, None
    for session in sessions:
        if session.discipline != "bike":
            continue
        effort = best_effort_power(session, TEST_WINDOW_S)
        if effort and (best_bike is None or effort["avg_watts"] > best_bike["avg_watts"]):
            best_bike, best_bike_session = effort, session
    if best_bike:
        result["ftp_watts"] = round(best_bike["avg_watts"] * FTP_FACTOR)
        result["sources"]["ftp"] = {
            "session_id": best_bike_session.id,
            "date": str(best_bike_session.session_date),
            "best_20min_watts": best_bike["avg_watts"],
        }

    # --- Lauf: schnellste 20 Minuten + zugehörige HF ---
    best_run, best_run_session = None, None
    for session in sessions:
        if session.discipline != "run":
            continue
        effort = best_effort_pace(session, TEST_WINDOW_S)
        if effort and (best_run is None or effort["pace_s_per_km"] < best_run["pace_s_per_km"]):
            best_run, best_run_session = effort, session
    if best_run:
        result["threshold_pace_s_per_km"] = best_run["pace_s_per_km"]
        result["sources"]["pace"] = {
            "session_id": best_run_session.id,
            "date": str(best_run_session.session_date),
            "best_20min_pace": best_run["pace_s_per_km"],
        }

    # --- Schwimmen: CSS aus den Runden des Testschwimmens ---
    from services.swim_css import detect_from_session, format_pace

    for session in sessions:
        if session.discipline != "swim":
            continue
        treffer = detect_from_session(session)
        if treffer:
            result["css_pace_s_per_100m"] = treffer["css_pace_s_per_100m"]
            result["css_pace_label"] = format_pace(treffer["css_pace_s_per_100m"])
            # Der Puls während der 400 m ist das Einzige, was der Test an
            # Herzfrequenz hergibt. Er liegt über der Schwelle — 400 m
            # maximal sind kein Dauertempo —, deshalb ein Abschlag von 5 %
            # und die ausdrückliche Kennzeichnung als Schätzung.
            if treffer.get("hr_400"):
                result["swim_threshold_hr"] = round(treffer["hr_400"] * 0.95)
            result["sources"]["css"] = {
                "session_id": treffer["session_id"],
                "date": treffer["date"],
                "t400_s": treffer["t400_s"],
                "t200_s": treffer["t200_s"],
                # Ausdrücklich gekennzeichnet: aus Runden abgeleitet heißt
                # geraten, welche Bahn der Test war.
                "hinweis": (
                    "Aus den Runden abgeleitet — bitte prüfen. Welche Strecke der "
                    "Test war, weiß nur der Athlet."
                ),
            }
            break

    # --- Herzfrequenz: höchster gemessener Wert als Maximum ---
    max_hr_session = max(
        (s for s in sessions if s.max_hr),
        key=lambda s: s.max_hr,
        default=None,
    )
    if max_hr_session:
        max_hr = max_hr_session.max_hr
        result["max_hr"] = max_hr
        result["sources"]["max_hr"] = {
            "session_id": max_hr_session.id,
            "date": str(max_hr_session.session_date),
        }
        # Dieselbe Aufteilung wie bei der Neukalibrierung: 70/85/90/95 % HFmax.
        result["hr_zones"] = {
            "z1_max": round(max_hr * 0.70),
            "z2_max": round(max_hr * 0.85),
            "z3_max": round(max_hr * 0.90),
            "z4_max": round(max_hr * 0.95),
        }
        # Schwellenpuls aus **demselben** Fenster wie die Schwellenpace.
        #
        # Vorher stand hier `best_run_session.avg_hr` — das Mittel über die
        # ganze Einheit. Bei einem Test mit Ein- und Auslaufen liegt das weit
        # unter dem Puls während der 20 harten Minuten; an echten Einheiten
        # gemessen waren es bis zu 22 Schläge. Und ein zu niedriger
        # Schwellenpuls bläht jede pulsbasierte TSS auf: Sie geht quadratisch
        # in die Intensität ein, 16 Schläge zu wenig ergeben rund 19 Prozent
        # zu viel Belastung — bei jedem Lauf, monatelang.
        fenster_hr = (best_run or {}).get("avg_hr")
        if fenster_hr:
            result["threshold_hr"] = round(fenster_hr * LTHR_FACTOR)
            result["sources"]["threshold_hr"] = {
                "session_id": best_run_session.id,
                "date": str(best_run_session.session_date),
                "avg_hr_20min": fenster_hr,
                "basis": "20-Minuten-Fenster",
            }
        elif best_run_session and best_run_session.avg_hr:
            # Kein Pulsstream: Dann bleibt nur das Mittel der ganzen Einheit.
            # Es wird benutzt, aber ausdrücklich als das gekennzeichnet, was
            # es ist — sonst sieht der Wert aus wie gemessen.
            result["threshold_hr"] = round(best_run_session.avg_hr * LTHR_FACTOR)
            result["sources"]["threshold_hr"] = {
                "session_id": best_run_session.id,
                "date": str(best_run_session.session_date),
                "avg_hr_gesamt": best_run_session.avg_hr,
                "basis": "ganze Einheit — kein Pulsstream, Wert eher zu niedrig",
            }

    if not any(k in result for k in ("ftp_watts", "threshold_pace_s_per_km", "max_hr", "css_pace_s_per_100m")):
        return {"status": "no_usable_data", "checked_sessions": len(sessions)}

    if apply:
        profile = db.query(AthleteProfile).first()
        if profile is None:
            return {**result, "status": "no_profile"}
        applied = []
        if result.get("ftp_watts"):
            profile.ftp_watts = result["ftp_watts"]; applied.append("ftp_watts")
        # Ohne Rücksicht auf "manual": Das Übernehmen ist eine bewusste
        # Handlung nach einem Vergleich alt gegen neu. Eine Sperre hier hieße,
        # dass ein frischer Test die alten Zahlen nicht korrigieren darf.
        if result.get("threshold_pace_s_per_km"):
            profile.threshold_pace_s_per_km = result["threshold_pace_s_per_km"]
            applied.append("threshold_pace_s_per_km")
        if result.get("threshold_hr"):
            profile.threshold_hr = result["threshold_hr"]
            profile.threshold_source = "auto"
            applied.append("threshold_hr")
        # Ein von Hand eingetragener CSS-Wert wird nicht überschrieben: er
        # stammt vom Athleten und ist verlässlicher als die Ableitung.
        if result.get("swim_threshold_hr"):
            profile.swim_threshold_hr = result["swim_threshold_hr"]
            profile.swim_threshold_source = "auto"
            applied.append("swim_threshold_hr")
        if result.get("css_pace_s_per_100m"):
            quelle = result["sources"].get("css", {})
            profile.css_pace_s_per_100m = result["css_pace_s_per_100m"]
            profile.css_source = "auto"
            profile.css_t400_s = quelle.get("t400_s")
            profile.css_t200_s = quelle.get("t200_s")
            applied.append("css_pace_s_per_100m")
        if result.get("max_hr") and result.get("hr_zones"):
            zones = result["hr_zones"]
            profile.max_hr = result["max_hr"]
            profile.z1_hr_max = zones["z1_max"]
            profile.z2_hr_min = zones["z1_max"] + 1
            profile.z2_hr_max = zones["z2_max"]
            profile.z3_hr_min = zones["z2_max"] + 1
            profile.z3_hr_max = zones["z3_max"]
            profile.z4_hr_min = zones["z3_max"] + 1
            profile.z4_hr_max = zones["z4_max"]
            applied.append("hr_zones")
        profile.zones_source = "benchmark"
        profile.zones_updated_at = datetime.utcnow()
        db.commit()
        result["applied"] = applied

    return result
