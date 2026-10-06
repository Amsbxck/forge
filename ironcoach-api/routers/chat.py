from datetime import date, timedelta
from services.api_budget import BudgetExhausted, NoBillingContext
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import ChatMessage, AthleteProfile, PlannedSession, WeeklyPlan, TrainingSession, HrvMeasurement
from schemas import ChatMessageIn, ChatMessageOut, ChatResponse
from services.claude_service import chat_with_coach
from services.plan_generator import get_current_week
from core.prompt_templates import get_phase, format_hrv, get_week_dates
from core.deps import get_profile

router = APIRouter()


def _tag(wert):
    """Datum aus dem Werkzeugaufruf lesen — dort kommt es als Zeichenkette."""
    from datetime import date as _d

    if isinstance(wert, _d):
        return wert
    try:
        return _d.fromisoformat(str(wert)[:10])
    except (TypeError, ValueError):
        return None


@router.post("/chat", response_model=ChatResponse)
async def chat(body: ChatMessageIn, db: Session = Depends(get_db)):
    # Die JÜNGSTEN Nachrichten, nicht die ältesten: mit asc().limit(20) sah
    # der Coach ab der 21. Nachricht dauerhaft nur den Gesprächsanfang und
    # nie das laufende Gespräch.
    history_records = (
        db.query(ChatMessage)
        .order_by(ChatMessage.created_at.desc())
        .limit(20)
        .all()
    )
    history = [
        {"role": r.role, "content": r.content}
        for r in reversed(history_records)
    ]

    # Wochennummer, Phase und Ziel kommen aus derselben Quelle wie bei der
    # Planerstellung. Vorher las der Chat die Woche aus dem Profil statt aus
    # dem Saisonziel und rechnete die Phase gegen feste 33 Wochen — er sprach
    # also über eine andere Woche als die, für die der Plan gilt.
    from services.coach_context import chat_kontext

    gemeinsam = chat_kontext(db)
    profile = get_profile(db)
    current_week = gemeinsam["week"]

    # Letzte 14 Tage Einheiten
    cutoff = date.today() - timedelta(days=14)
    sessions = db.query(TrainingSession).filter(
        TrainingSession.session_date >= cutoff,
        TrainingSession.deleted_at == None,
    ).order_by(TrainingSession.session_date.desc()).all()

    from services.session_view import session_to_dict
    # Die FTP nur für die harten Minuten; fehlt ein Profil, fehlt die Angabe
    # und der Rest der Einheit bleibt vollständig.
    ftp = profile.ftp_watts if profile else None
    sessions_dicts = [session_to_dict(s, ftp) for s in sessions]

    # Letzte 7 Tage HRV
    hrv_cutoff = date.today() - timedelta(days=7)
    hrv_records = db.query(HrvMeasurement).filter(
        HrvMeasurement.measured_at >= hrv_cutoff
    ).order_by(HrvMeasurement.measured_at.asc()).all()
    hrv_dicts = [{"measured_at": str(h.measured_at), "rmssd": h.rmssd, "hrv_status": h.hrv_status} for h in hrv_records]

    # Der Plan der **laufenden Woche**, nicht der zuletzt erzeugte: Wer sich
    # eine spätere Woche vorausplanen lässt, bekam sonst im Chat diese Woche
    # als "aktuell" vorgehalten.
    latest_plan = (
        db.query(WeeklyPlan)
        .filter(WeeklyPlan.week_number == current_week)
        .order_by(WeeklyPlan.generated_at.desc())
        .first()
        or db.query(WeeklyPlan).order_by(WeeklyPlan.generated_at.desc()).first()
    )
    plan_text = latest_plan.plan_text if latest_plan else None
    plan_content = latest_plan.plan_content if latest_plan else None

    latest_hrv_record = (
        db.query(HrvMeasurement)
        .order_by(HrvMeasurement.measured_at.desc())
        .first()
    )
    latest_hrv = None
    if latest_hrv_record:
        latest_hrv = {
            "measured_at": str(latest_hrv_record.measured_at),
            "rmssd": latest_hrv_record.rmssd,
            "hrv_status": latest_hrv_record.hrv_status,
        }

    # Dieselben Bausteine wie im Plan-Prompt, dazu das, was nur der Chat
    # braucht: aktueller Plan im Volltext und die jüngste HRV-Messung.
    constraints = gemeinsam.get("constraints")
    context = {
        **gemeinsam,
        "sessions_summary": gemeinsam["sessions_text"],
        "reflections": gemeinsam["reflections_text"],
        "hrv_summary": format_hrv(hrv_dicts),
        "latest_hrv": latest_hrv,
        "current_plan": plan_text,
        "current_plan_detail": plan_content,
        "constraints_block": (
            "## INDIVIDUELLE REGELN (KRITISCH)\n\n" + constraints
            if constraints else ""
        ),
    }

    try:
        reply, updated_plan, tagesaenderung = await chat_with_coach(body.message, history, context)
    except NoBillingContext:
        # Kein Serverfehler im üblichen Sinn: Die Anfrage war in Ordnung, nur
        # ließ sich kein Konto zuordnen. Als 500 wäre das im Log von echten
        # Abstürzen nicht zu unterscheiden.
        raise HTTPException(
            status_code=503,
            detail="Anfrage konnte keinem Konto zugeordnet werden — bitte neu anmelden.",
        )
    except BudgetExhausted:
        # Siehe plan.py: gehört als 402 nach draußen, nicht als 500.
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chat fehlgeschlagen: {str(e)}")

    # Plan in DB speichern wenn Claude einen erstellt/geändert hat.
    # Ohne days wäre der Plan im Wochenkalender leer — dann lieber den alten behalten.
    db_plan = None
    # Ohne Nutzerzuordnung wird der Plan nicht gespeichert: Er wäre durch den
    # Mandantenfilter unsichtbar, und der Athlet bekäme eine Antwort mit dem
    # Hinweis auf einen geänderten Plan, den es nirgends gibt.
    if updated_plan and updated_plan.get("days") and profile and profile.user_id:
        target_week = updated_plan.get("week", current_week + 1)
        # Startdatum aus dem Saisonziel, ersatzweise aus dem Profil — dieselbe
        # Reihenfolge wie in der Planerstellung. Aus dem Profil allein datierte
        # der Chat die Woche anders als der Generator dieselbe Woche.
        from core.deps import get_plan_anchor
        anker = get_plan_anchor(db) or profile
        plan_start = getattr(anker, "plan_start_date", None) or profile.plan_start_date
        week_start, week_end = get_week_dates(target_week, plan_start)
        plan_text_lines = [f"Wochenplan {target_week} ({week_start} – {week_end})", ""]
        for day in updated_plan["days"]:
            training_type = day.get("training_type")
            type_suffix = f" [{training_type}]" if training_type else ""
            plan_text_lines.append(
                f"{day.get('day', '?')} ({day.get('date', '?')}): "
                f"{str(day.get('session_type', '')).upper()}{type_suffix} "
                f"{day.get('duration_min', '')}min — {day.get('notes', '')}"
            )
        plan_text_lines.append("")
        plan_text_lines.append(updated_plan.get("coaching_comment", ""))

        db_plan = WeeklyPlan(
            user_id=profile.user_id,
            week_number=target_week,
            week_start=week_start,
            week_end=week_end,
            # In der Off Season steht die Phase fest; vom Modell übernommen
            # hieße sie mal "Off Season" und mal "Base 1".
            plan_phase=(
                gemeinsam["phase"] if gemeinsam.get("offseason")
                else updated_plan.get("phase")
            ),
            plan_content=updated_plan,
            plan_text="\n".join(plan_text_lines),
            adjustments_applied=updated_plan.get("adjustments", []),
        )
        db.add(db_plan)

    # Teiländerung: nur die gelieferten Tage ersetzen, der Rest bleibt
    # wortgleich stehen. Das ist der Normalfall für Umstellungen innerhalb der
    # laufenden Woche — und es spart nicht nur Token, sondern schützt die
    # unberührten Tage davor, beim Neuschreiben versehentlich anders auszufallen.
    if db_plan is None and tagesaenderung and profile and profile.user_id:
        from core.wochen import kalenderwoche
        from services.plan_merge import merge_days
        from services.plan_selection import pick_plan

        neue_tage = tagesaenderung.get("days") or []
        # Die Woche folgt aus den geänderten Daten, nicht aus "heute": Wer am
        # Sonntag die kommende Woche umstellt, meint nicht die laufende.
        daten = sorted(
            d for d in (
                _tag(t.get("date")) for t in neue_tage
            ) if d is not None
        )
        basis = None
        if daten:
            montag, _ = kalenderwoche(daten[0])
            basis = pick_plan(db.query(WeeklyPlan).filter(WeeklyPlan.week_start == montag))

        if basis is None:
            reply += (
                "\n\nFür diese Woche gibt es noch keinen Plan, an dem sich einzelne "
                "Tage ändern ließen — erstelle sie zuerst über \u201ePlan erstellen\u201c."
            )
        else:
            # Absolvierte Tage sperren: Ihre Vorgabe nachträglich auf das zu
            # setzen, was gemacht wurde, ergäbe eine Planerfüllung, die nie
            # stattgefunden hat.
            gesperrt = {
                p.planned_date for p in db.query(PlannedSession)
                .filter(PlannedSession.plan_id == basis.id,
                        PlannedSession.status == "completed").all()
            }
            inhalt, uebernommen, abgewiesen = merge_days(
                basis.plan_content or {}, neue_tage, gesperrte_daten=gesperrt
            )
            if uebernommen:
                # Als neue Zeile, nicht als Änderung der alten: Der Verlauf der
                # Woche bleibt nachvollziehbar, und `pick_plan` nimmt ohnehin
                # die jüngste Fassung.
                grund = tagesaenderung.get("reason") or "Einzelne Tage im Chat angepasst"
                db_plan = WeeklyPlan(
                    user_id=profile.user_id,
                    week_number=basis.week_number,
                    week_start=basis.week_start,
                    week_end=basis.week_end,
                    plan_phase=basis.plan_phase,
                    plan_content=inhalt,
                    plan_text=basis.plan_text,
                    adjustments_applied=(basis.adjustments_applied or []) + [grund],
                )
                db.add(db_plan)
            if abgewiesen:
                reply += (
                    "\n\nNicht geändert: " + ", ".join(abgewiesen)
                    + ". Vergangene und bereits absolvierte Tage bleiben stehen."
                )

    chat_user_id = profile.user_id if profile else None
    db.add(ChatMessage(user_id=chat_user_id, role="user", content=body.message, context_week=current_week))
    db.add(ChatMessage(user_id=chat_user_id, role="assistant", content=reply, context_week=current_week))
    db.commit()

    if db_plan is not None:
        from services.plan_projection import project_plan
        db.refresh(db_plan)
        project_plan(db, db_plan)
        try:
            from services.obsidian.plan_note import sync_plan_note
            sync_plan_note(db, db_plan)
        except Exception as e:  # pragma: no cover - darf die Antwort nie reißen
            import logging
            logging.getLogger(__name__).warning("Plan-Note fehlgeschlagen: %s", e)

    # Ebenso für die Anzeige: sonst zeigt der Chat für immer die ersten 40
    # Nachrichten und die gerade gesendete taucht nie auf.
    all_records = list(reversed(
        db.query(ChatMessage)
        .order_by(ChatMessage.created_at.desc())
        .limit(40)
        .all()
    ))
    return ChatResponse(reply=reply, history=all_records)


@router.get("/chat/history", response_model=list[ChatMessageOut])
def get_chat_history(db: Session = Depends(get_db)):
    return list(reversed(
        db.query(ChatMessage)
        .order_by(ChatMessage.created_at.desc())
        .limit(40)
        .all()
    ))


@router.delete("/chat")
def clear_chat(db: Session = Depends(get_db)):
    """Eigenen Chatverlauf löschen.

    Der Nutzerfilter steht hier ausdrücklich, obwohl er beim Lesen automatisch
    greift: Der Mandantenschutz hängt an SELECT-Anweisungen und wirkt bei einer
    Massenlöschung **nicht**. Ohne die Bedingung löscht ein Klick auf „Verlauf
    löschen" die Unterhaltungen aller Athleten — ein Fehler, der beim Testen
    mit einem einzigen Konto nie auffällt.
    """
    from core.deps import resolve_user

    user = resolve_user(db)
    if user is None:
        # Ohne erkennbaren Nutzer lieber nichts tun als alles: Im lokalen
        # Einzelplatzbetrieb ohne Anmeldung wäre „alles" sonst wörtlich.
        raise HTTPException(status_code=401, detail="Kein angemeldeter Nutzer")

    geloescht = (
        db.query(ChatMessage)
        .filter(ChatMessage.user_id == user.id)
        .delete(synchronize_session=False)
    )
    db.commit()
    return {"message": "Chat-Verlauf gelöscht", "geloescht": geloescht}
