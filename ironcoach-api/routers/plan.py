import re
from services.api_budget import BudgetExhausted, NoBillingContext
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from database import get_db
from datetime import date

from core.wochen import kalenderwoche
from models import AthleteProfile, User, WeeklyPlan
from schemas import WeeklyPlanOut
from services.plan_generator import generate_and_save_plan, get_current_week
from services.plan_selection import active_plan_for_week, pick_plan as _pick_plan, plan_der_woche
from services.pdf_generator import generate_plan_pdf

_UMLAUTE = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "Ä": "Ae", "Ö": "Oe", "Ü": "Ue", "ß": "ss"})


def _safe_filename(name: str) -> str:
    """ASCII-Dateiname für den Download-Header.

    Umlaute werden umschrieben statt gestrichen — aus „Übergang" wurde
    vorher „bergang".
    """
    name = name.replace('—', '-').replace('–', '-').replace('·', '-').translate(_UMLAUTE)
    return re.sub(r'[^\x00-\x7f]', '', name).replace(' ', '_')


def _pdf_antwort(plan: WeeklyPlan) -> Response:
    pdf_bytes = generate_plan_pdf({"plan_content": plan.plan_content})
    filename = _safe_filename(
        f"IronCoach_{plan.week_start or ''}_Woche_{plan.week_number}_{plan.plan_phase or 'Plan'}.pdf"
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
from core.deps import get_current_user, get_profile, get_plan_anchor

router = APIRouter()


@router.get("/plan/generate", response_model=WeeklyPlanOut)
async def generate_plan(
    requests: str = Query(default="", description="Besondere Wünsche oder Hinweise"),
    montag: date | None = Query(
        default=None,
        description="Montag der Woche, für die geplant werden soll. Ohne Angabe die laufende.",
    ),
    db: Session = Depends(get_db),
):
    """Plan erzeugen — für die laufende Woche oder für die angegebene.

    `montag` gibt es, weil sonst immer die Woche geplant wurde, in der heute
    liegt. Am Sonntag war das ein Plan für sechs vergangene Tage. Die
    Oberfläche schickt den Montag der Woche, die sie gerade anzeigt, und
    schreibt dasselbe Datum auf den Knopf — dann ist vor dem Drücken
    sichtbar, was entsteht.
    """
    try:
        plan = await generate_and_save_plan(db, special_requests=requests, montag=montag)
        return plan
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except NoBillingContext:
        # Kein Serverfehler im üblichen Sinn: Die Anfrage war in Ordnung, nur
        # ließ sich kein Konto zuordnen. Als 500 wäre das im Log von echten
        # Abstürzen nicht zu unterscheiden.
        raise HTTPException(
            status_code=503,
            detail="Anfrage konnte keinem Konto zugeordnet werden — bitte neu anmelden.",
        )
    except BudgetExhausted:
        # Weiterreichen an den Handler in main.py: ein aufgebrauchtes Guthaben
        # ist kein Serverfehler, und als 500 könnte die Oberfläche es nicht
        # von einem echten Ausfall unterscheiden.
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Plan-Generierung fehlgeschlagen: {str(e)}")


@router.post("/plan/anpassen")
async def plan_anpassen(
    wunsch: str = Query(..., description="Was geändert werden soll"),
    montag: date | None = Query(default=None, description="Woche; ohne Angabe die laufende"),
    db: Session = Depends(get_db),
):
    """Einzelne Tage eines bestehenden Plans ändern.

    Der Gegenstück zu `/plan/generate` im selben Fenster: Dort entsteht eine
    ganze Woche, hier ändern sich nur die Tage, die gemeint sind. Bisher gab es
    die Teiländerung nur im Coach-Chat — wer sie im Planfenster verlangte, bekam
    sieben neu geschriebene Tage und hielt das für einen Fehler.
    """
    from core.wochen import kalenderwoche
    from services.plan_adjust import tage_anpassen

    start, _ = kalenderwoche(montag) if montag else kalenderwoche()
    plan = _pick_plan(db.query(WeeklyPlan).filter(WeeklyPlan.week_start == start))
    if plan is None:
        raise HTTPException(
            status_code=404,
            detail=f"Für die Woche ab {start} gibt es noch keinen Plan, an dem sich "
                   f"Tage ändern liessen — erst erstellen.",
        )

    try:
        return await tage_anpassen(db, plan, wunsch)
    except NoBillingContext:
        # Wie bei `/plan/generate`: kein Serverfehler, sondern ein Konto, das
        # sich nicht zuordnen ließ. Hier landete es bisher als 500.
        raise HTTPException(
            status_code=503,
            detail="Anfrage konnte keinem Konto zugeordnet werden — bitte neu anmelden.",
        )
    except BudgetExhausted:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Anpassung fehlgeschlagen: {e}")


@router.get("/plan/current", response_model=WeeklyPlanOut)
def get_current_plan(db: Session = Depends(get_db)):
    # Über das Datum, nicht über die Planwochennummer: Die Nummer entstand
    # früher aus `max(1, …)` und fiel vor dem Beginn des Aufbaus für jedes
    # Datum auf 1 zusammen; heute verschiebt sie sich mit jedem Zielwechsel. Eine Testwoche für die kommende Woche bekäme dann
    # dieselbe Nummer wie die laufende und erschiene hier als aktueller Plan
    # — obwohl sie sieben Tage später liegt.
    plan = plan_der_woche(db)
    if not plan:
        raise HTTPException(status_code=404, detail="Kein Plan für diese Woche — erst /api/plan/generate aufrufen")
    return plan


@router.get("/plan/current/pdf")
def download_current_plan_pdf(db: Session = Depends(get_db)):
    # Die laufende Kalenderwoche — vorher der neueste Plan überhaupt, also
    # oft eine vorausgeplante Woche oder die Testwoche.
    plan = plan_der_woche(db)
    if not plan:
        raise HTTPException(status_code=404, detail="Kein Plan für diese Woche")
    return _pdf_antwort(plan)


@router.get("/plan/am/{montag}/pdf")
def download_plan_pdf_by_monday(montag: date, db: Session = Depends(get_db)):
    """PDF einer Kalenderwoche. Über den Montag, weil die Wochennummer nach
    einem Zielwechsel eine andere Woche meint — und Woche 0 sich über sie
    gar nicht exportieren liess."""
    plan = plan_der_woche(db, montag)
    if not plan:
        raise HTTPException(status_code=404, detail=f"Kein Plan für die Woche ab {kalenderwoche(montag)[0]}")
    return _pdf_antwort(plan)


@router.get("/plan/{week_number}/pdf")
def download_plan_pdf(week_number: int, db: Session = Depends(get_db)):
    plan = active_plan_for_week(db, week_number)
    if not plan:
        raise HTTPException(status_code=404, detail=f"Kein Plan für Woche {week_number}")
    return _pdf_antwort(plan)


@router.get("/plan/am/{montag}", response_model=WeeklyPlanOut)
def get_plan_by_monday(montag: date, db: Session = Depends(get_db)):
    """Plan einer Kalenderwoche, angesprochen über ihren Montag.

    Neben `/plan/{week_number}`, weil die Wochennummer zum Blättern nicht
    taugt: Sie entstand früher aus `max(1, …)` und war vor dem Beginn des
    Aufbaus für jedes Datum 1 (heute verschiebt sie sich mit jedem Zielwechsel). "Eine Woche vor" führte dort auf Nummer 2, für die es
    nie einen Plan gibt — während die kommende Woche unter derselben 1 lag
    wie die laufende und unerreichbar blieb.

    Ein beliebiger Tag wird auf seinen Montag gezogen, damit die Adresse
    nicht davon abhängt, welchen Wochentag der Aufrufer geschickt hat.
    """
    from services.plan_storno import storno_pruefung

    start, _ = kalenderwoche(montag)
    plan = _pick_plan(db.query(WeeklyPlan).filter(WeeklyPlan.week_start == start))
    if not plan:
        raise HTTPException(status_code=404, detail=f"Kein Plan für die Woche ab {start}")
    antwort = WeeklyPlanOut.model_validate(plan)
    antwort.stornierbar, antwort.storno_grund = storno_pruefung(db, plan.user_id, start)
    return antwort


@router.delete("/plan/am/{montag}")
def cancel_plan(montag: date, db: Session = Depends(get_db),
                user: User | None = Depends(get_current_user)):
    """Den Plan einer Woche stornieren — alle Fassungen, die geplanten
    Einheiten und die Obsidian-Notiz. Siehe `services/plan_storno.py`."""
    from services.plan_storno import PlanNichtStornierbar, plan_stornieren

    try:
        return plan_stornieren(db, user, montag)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PlanNichtStornierbar as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/plan/{week_number}", response_model=WeeklyPlanOut)
def get_plan_by_week(week_number: int, db: Session = Depends(get_db)):
    plan = active_plan_for_week(db, week_number)
    if not plan:
        raise HTTPException(status_code=404, detail=f"Kein Plan für Woche {week_number}")
    return plan
