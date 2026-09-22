from datetime import date, datetime, timedelta
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func

from database import get_db
from models import AthleteProfile, TrainingSession, HrvMeasurement, User
from schemas import WeekMetrics, TrendPoint
from services.plan_generator import get_current_week
from core.prompt_templates import get_phase
from core.deps import get_profile as resolve_profile, get_plan_anchor, get_current_user
from core.wochen import kalenderwoche

router = APIRouter()


@router.get("/metrics/week", response_model=WeekMetrics)
def week_metrics(db: Session = Depends(get_db)):
    from core.deps import total_weeks_for
    from core.race_types import season_state

    anchor = get_plan_anchor(db)
    current_week = get_current_week(anchor) if anchor else 1
    total_weeks = total_weeks_for(anchor) if anchor else 33
    race_date = getattr(anchor, "race_date", None)
    # Startdatum mitgeben, sonst gilt die Zeit vor dem Aufbau als
    # "preparation" und die Oberfläche zeigt "Woche 1 von 24" für einen
    # Zeitraum, der Monate vor Woche 1 liegt.
    plan_start = getattr(anchor, "plan_start_date", None)
    state = season_state(race_date, plan_start=plan_start)

    # Nach Datum, nicht nach Planwoche — siehe `kalenderwoche`.
    woche_von, woche_bis = kalenderwoche(date.today())
    sessions = (
        db.query(TrainingSession)
        .filter(TrainingSession.session_date >= woche_von)
        .filter(TrainingSession.session_date <= woche_bis)
        .filter(TrainingSession.deleted_at == None)
        .all()
    )

    total_tss = sum((s.tss or 0) for s in sessions)
    total_duration = sum((s.duration_min or 0) for s in sessions)
    disciplines: dict[str, int] = {}
    for s in sessions:
        disciplines[s.discipline] = disciplines.get(s.discipline, 0) + 1

    hr_values = [s.avg_hr for s in sessions if s.avg_hr]
    avg_hr = round(sum(hr_values) / len(hr_values)) if hr_values else None

    hr_zones_combined: dict[str, list] = {}
    for s in sessions:
        if s.hr_zones:
            for k, v in s.hr_zones.items():
                hr_zones_combined.setdefault(k, []).append(v)
    hr_zones_avg = (
        {k: round(sum(v) / len(v), 1) for k, v in hr_zones_combined.items()}
        if hr_zones_combined
        else None
    )

    latest_hrv = (
        db.query(HrvMeasurement)
        .order_by(HrvMeasurement.measured_at.desc())
        .first()
    )

    return WeekMetrics(
        week_number=current_week,
        # Die Phase braucht die Zieldauer: ohne sie galt für jeden Plan die
        # 33-Wochen-Einteilung, und ein 14-Wochen-Halbmarathon zeigte im
        # Aufbau bereits Taper an.
        # In der Grundlagenphase keine Aufbauphase melden — das Dashboard
        # zeigte sonst "Base 1" für einen Zeitraum Monate vor Woche 1.
        phase=(
            "Grundlage" if state == "base_period"
            else get_phase(current_week, total_weeks)
        ),
        season_state=state,
        plan_start_date=plan_start,
        race_date=race_date,
        total_weeks=total_weeks,
        total_tss=round(total_tss, 1),
        sessions_count=len(sessions),
        total_duration_min=total_duration,
        disciplines=disciplines,
        avg_hr=avg_hr,
        hr_zones_avg=hr_zones_avg,
        hrv_latest=latest_hrv.rmssd if latest_hrv else None,
        hrv_status=latest_hrv.hrv_status if latest_hrv else None,
    )


@router.get("/metrics/trends", response_model=list[TrendPoint])
def trends(weeks: int = 4, db: Session = Depends(get_db)):
    """Belastung der letzten Wochen, je Kalenderwoche.

    Gebündelt wird nach Datum, aus demselben Grund wie in `week_metrics`:
    Über die Planwoche fielen vor dem Aufbaubeginn sämtliche Wochen auf die
    Nummer 1 zusammen — ein einziger Balken mit allem darin und daneben
    lauter leere.
    """
    from services.plan_generator import get_week_for_date

    anchor = get_plan_anchor(db)
    diese_woche, _ = kalenderwoche(date.today())

    result = []
    for zurueck in range(weeks - 1, -1, -1):
        woche_von = diese_woche - timedelta(weeks=zurueck)
        woche_bis = woche_von + timedelta(days=6)

        sessions = (
            db.query(TrainingSession)
            .filter(TrainingSession.session_date >= woche_von)
            .filter(TrainingSession.session_date <= woche_bis)
            # Gelöschte zählten hier mit, in `week_metrics` dagegen nicht.
            # Dieselbe Woche stand dadurch je nach Kachel mit anderen Zahlen da.
            .filter(TrainingSession.deleted_at == None)
            .all()
        )
        total_tss = sum((s.tss or 0) for s in sessions)

        result.append(
            TrendPoint(
                # Die Nummer bleibt die Planwoche — sie beschriftet den Balken.
                # Gebündelt wird trotzdem nach Datum.
                week_number=get_week_for_date(anchor, woche_von) if anchor else 1,
                week_start=woche_von,
                total_tss=round(total_tss, 1),
                sessions_count=len(sessions),
            )
        )
    return result


def _profile_out(db: Session, profile):
    """Profil mit den Werten des Saisonziels.

    Wochennummer und Renntag kamen bisher aus dem Profil. Dort stehen aber
    Platzhalter aus der Registrierung — sobald ein Ziel gesetzt ist, weichen
    sie davon ab, und die Profilseite zeigte eine andere Woche als das
    Dashboard.
    """
    from schemas import AthleteProfileOut
    from core.deps import get_plan_anchor, total_weeks_for

    anchor = get_plan_anchor(db) or profile
    out = AthleteProfileOut.model_validate(profile)
    out.current_week = get_current_week(anchor)
    out.total_weeks = total_weeks_for(anchor)
    renntag = getattr(anchor, "race_date", None)
    if renntag:
        out.race_date = renntag
    # Auch das Startdatum aus dem Ziel: Im Profil steht der Platzhalter aus
    # der Registrierung. Ohne diese Zeile beurteilt die Profilseite die
    # Grundlagenphase gegen ein Datum, das mit dem Ziel nichts zu tun hat.
    startdatum = getattr(anchor, "plan_start_date", None)
    if startdatum:
        out.plan_start_date = startdatum
    return out


@router.get("/metrics/pmc")
def pmc_series(db: Session = Depends(get_db)):
    """Fitness, Ermüdung und Form je Tag.

    Die Rechnung lief bisher zweimal: hier für den Coach-Prompt und noch
    einmal im Browser für das Diagramm. Zwei Fassungen derselben Formel
    driften auseinander, und dann nennt das Dashboard eine andere Form als
    die, mit der geplant wurde — ohne dass eine von beiden falsch aussieht.
    Diese hier ist die maßgebliche; das Diagramm holt sie sich.
    """
    from services.season_summary import _pmc
    from models import TrainingSession

    sessions = (
        db.query(TrainingSession)
        .filter(TrainingSession.deleted_at.is_(None))
        .order_by(TrainingSession.session_date.asc())
        .all()
    )
    verlauf = _pmc(sessions, date.today())
    tages_tss: dict = {}
    for s in sessions:
        if s.tss and s.session_date:
            tages_tss[s.session_date] = tages_tss.get(s.session_date, 0) + s.tss
    return [
        {
            "date": str(p["datum"]),
            "label": str(p["datum"])[5:],
            "tss": round(tages_tss.get(p["datum"], 0), 1) or None,
            "ctl": round(p["ctl"], 1),
            "atl": round(p["atl"], 1),
            "tsb": round(p["tsb"], 1),
        }
        for p in verlauf
    ]


@router.get("/budget")
def budget_status(db: Session = Depends(get_db)):
    """Guthaben, Verbrauch und Rest für den angemeldeten Athleten."""
    from core.deps import resolve_user
    from services.api_budget import status

    return status(db, resolve_user(db))


@router.get("/budget/usage")
def budget_usage(limit: int = 20, db: Session = Depends(get_db)):
    """Die letzten Aufrufe — damit nachvollziehbar bleibt, wofür das
    Guthaben verbraucht wurde."""
    from core.deps import resolve_user
    from models import ApiUsage

    user = resolve_user(db)
    if user is None:
        return []
    zeilen = (
        db.query(ApiUsage)
        .filter(ApiUsage.user_id == user.id)
        .order_by(ApiUsage.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "datum": z.created_at.isoformat() if z.created_at else None,
            "art": z.kind,
            "modell": z.model,
            "token_ein": z.input_tokens,
            "token_aus": z.output_tokens,
            "kosten_eur": round(z.cost_eur, 4),
        }
        for z in zeilen
    ]


@router.get("/profile")
def get_profile(db: Session = Depends(get_db)):
    profile = resolve_profile(db)
    if not profile:
        return {}
    return _profile_out(db, profile)


class IntakeIn(BaseModel):
    """Werte, die ein Athlet beim Einstieg schon kennt.

    Alles freiwillig. Wer nichts einträgt, schickt ein leeres Objekt und wird
    trotzdem als aufgenommen vermerkt — sonst ginge das Fenster bei jedem
    Aufruf wieder auf.
    """
    max_hr: int | None = None
    threshold_hr: int | None = None
    threshold_pace_s_per_km: int | None = None
    ftp_watts: int | None = None
    css_pace_s_per_100m: float | None = None
    swim_threshold_hr: int | None = None
    # Pulszonen, entweder alle oder keine.
    z1_hr_max: int | None = None
    z2_hr_min: int | None = None
    z2_hr_max: int | None = None
    z3_hr_min: int | None = None
    z3_hr_max: int | None = None
    z4_hr_min: int | None = None
    z4_hr_max: int | None = None


@router.get("/metrics/ftp-check")
def ftp_check(db: Session = Depends(get_db)):
    """Passt die hinterlegte FTP noch zu dem, was gefahren wird?

    Eigener Endpunkt und nicht Teil von `/metrics/week`: Die Prüfung liest
    die Leistungsdaten mehrerer Fahrten und ist damit deutlich teurer als
    der Rest der Kachel. Wer sie nicht braucht, soll sie nicht bezahlen.
    """
    from services.ftp_check import ftp_ueberpruefung

    return {"befund": ftp_ueberpruefung(db, resolve_profile(db))}


@router.get("/profile/intake")
def intake_status(
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    """Soll das Willkommensfenster erscheinen?

    Erst nach bestätigter E-Mail. Vorher steht der Athlet vor einem Dialog,
    der nach Wettkampfziel, Zonen und Einschränkungen fragt — während sein
    Konto noch gar nicht ihm gehören muss. Wer sich mit einer fremden
    Adresse anmeldet, käme sonst bis zum eingerichteten Profil, und der
    eigentliche Inhaber bekäme davon nichts mit.

    Die Prüfung sitzt hier und nicht in der Oberfläche: Sie gilt dann für
    jede Ansicht, die das Fenster zeigt, auch für künftige.
    """
    profile = resolve_profile(db)
    if not profile:
        return {"faellig": False}

    # Nur dort, wo es überhaupt eine Anmeldung gibt. Im lokalen
    # Einzelplatzbetrieb (AUTH_REQUIRED=false) wird keine Adresse bestätigt,
    # weil es keinen Anmeldeweg gibt — die Sperre würde das Fenster dort für
    # immer zurückhalten.
    from core.config import settings

    unbestaetigt = bool(
        settings.AUTH_REQUIRED and user is not None and user.email_verified_at is None
    )

    return {
        "faellig": profile.intake_done_at is None and not unbestaetigt,
        "erledigt_am": profile.intake_done_at.isoformat() if profile.intake_done_at else None,
        # Damit die Oberfläche den Unterschied zwischen "schon erledigt" und
        # "noch gesperrt" zeigen kann, statt einfach nichts anzuzeigen.
        "wartet_auf_bestaetigung": unbestaetigt,
    }


@router.post("/profile/intake")
def submit_intake(body: IntakeIn = IntakeIn(), db: Session = Depends(get_db)):
    """Bekannte Werte übernehmen — oder nur wegklicken.

    Übernommene Werte werden als "manual" markiert. Das schützt sie davor,
    von der automatischen Ableitung überschrieben zu werden: Wer seine
    gemessenen Garmin-Zonen einträgt, soll sie nicht durch einen beiläufigen
    Sonntagslauf ersetzt bekommen.

    Die Testwoche entfällt dadurch ausdrücklich **nicht**. Eingetragene Werte
    stammen aus einem anderen Kontext und altern; der Test misst sie unter
    den Bedingungen, unter denen später auch trainiert wird. Beides
    nebeneinander zu haben ist der Sinn — nicht das eine statt des anderen.
    """
    from fastapi import HTTPException

    profile = resolve_profile(db)
    if not profile:
        raise HTTPException(status_code=404, detail="Kein Profil gefunden")

    ZONEN = ["z1_hr_max", "z2_hr_min", "z2_hr_max",
             "z3_hr_min", "z3_hr_max", "z4_hr_min", "z4_hr_max"]
    daten = body.model_dump(exclude_none=True)

    # Zonen nur vollständig übernehmen: Drei von sieben Grenzen ergeben eine
    # Einteilung, in der sich Bereiche überlappen oder Lücken klaffen.
    zonen_da = [k for k in ZONEN if k in daten]
    if zonen_da and len(zonen_da) != len(ZONEN):
        raise HTTPException(
            status_code=422,
            detail="Pulszonen bitte vollständig eintragen oder ganz weglassen.",
        )
    if zonen_da:
        folge = [daten[k] for k in ZONEN]
        if any(a >= b for a, b in zip(folge, folge[1:])):
            raise HTTPException(
                status_code=422,
                detail="Die Zonengrenzen müssen aufsteigend sein.",
            )
        obergrenze = daten.get("max_hr", profile.max_hr)
        if obergrenze and daten["z4_hr_max"] > obergrenze:
            raise HTTPException(
                status_code=422,
                detail=f"Z4-Ende liegt über dem Maximalpuls ({obergrenze}).",
            )

    uebernommen = []
    for feld, wert in daten.items():
        setattr(profile, feld, wert)
        uebernommen.append(feld)

    if any(f in daten for f in ("max_hr", "ftp_watts", *ZONEN)):
        profile.zones_source = "manual"
        profile.zones_updated_at = datetime.utcnow()
    if any(f in daten for f in ("threshold_hr", "threshold_pace_s_per_km")):
        profile.threshold_source = "manual"
    if "css_pace_s_per_100m" in daten:
        profile.css_source = "manual"

    profile.intake_done_at = datetime.utcnow()
    db.commit()
    db.refresh(profile)
    return {"uebernommen": uebernommen, "profil": _profile_out(db, profile)}


class SwimTestIn(BaseModel):
    """Zeiten des CSS-Tests in Sekunden — oder die Pace direkt.

    Die Feldnamen stammen aus der Zeit, als der Test fest auf 400/200 m lag:
    `t400_s` ist die Zeit der **längeren** Strecke, `t200_s` die der
    kürzeren. Welche Strecken es waren, sagen `d_lang_m` und `d_kurz_m`;
    ohne Angabe gilt weiterhin 400/200.
    """
    t400_s: int | None = None
    t200_s: int | None = None
    d_lang_m: int | None = None
    d_kurz_m: int | None = None
    css_pace_s_per_100m: float | None = None
    # Eigener Schwellenpuls fürs Wasser; optional.
    swim_threshold_hr: int | None = None


@router.post("/profile/swim-test")
def set_swim_test(
    body: SwimTestIn,
    db: Session = Depends(get_db),
):
    """CSS von Hand setzen.

    Entweder beide Testzeiten — dann wird gerechnet — oder die Pace direkt,
    für alle, die ihren Wert schon kennen. Von Hand gesetzte Werte werden von
    der automatischen Ableitung nicht mehr überschrieben.
    """
    from fastapi import HTTPException
    from services.swim_css import css_from_times, format_pace, guete

    profile = resolve_profile(db)
    if not profile:
        raise HTTPException(status_code=404, detail="Kein Profil gefunden")

    if body.t400_s and body.t200_s:
        from services.swim_css import PAARE

        d_lang = body.d_lang_m or 400
        d_kurz = body.d_kurz_m or 200
        if (d_lang, d_kurz) not in PAARE:
            erlaubt = ", ".join(f"{a}/{b} m" for a, b in PAARE)
            raise HTTPException(
                status_code=422,
                detail=f"Nur diese Streckenpaare sind vorgesehen: {erlaubt}.",
            )

        css = css_from_times(body.t400_s, body.t200_s, d_lang, d_kurz)
        if css is None:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Die Zeit über {d_lang} m muss größer sein als die über "
                    f"{d_kurz} m. Vertauscht?"
                ),
            )
        profile.css_t400_s = body.t400_s
        profile.css_t200_s = body.t200_s
        profile.css_dist_lang_m = d_lang
        profile.css_dist_kurz_m = d_kurz
    elif body.css_pace_s_per_100m:
        css = round(body.css_pace_s_per_100m, 1)
        profile.css_t400_s = None
        profile.css_t200_s = None
    else:
        raise HTTPException(
            status_code=422,
            detail="Entweder beide Testzeiten oder die Pace angeben",
        )

    profile.css_pace_s_per_100m = css
    profile.css_source = "manual"
    if body.swim_threshold_hr:
        profile.swim_threshold_hr = body.swim_threshold_hr
        profile.swim_threshold_source = "manual"
    db.commit()
    db.refresh(profile)
    return {
        "css_pace_s_per_100m": css,
        "css_pace_label": format_pace(css),
        "source": "manual",
        # Vorbehalt, falls die Zeiten unterhalb des Bereichs liegen, in dem
        # die Rechnung trägt. Bewertet werden die Zeiten, nicht die
        # Strecken: Für einen langsamen Schwimmer sind 100/50 m einwandfrei,
        # für einen schnellen nicht.
        "guete": guete(body.t400_s, body.t200_s),
    }


class ThresholdsIn(BaseModel):
    """Schwellenwerte fürs Laufen, wie die Uhr sie meldet."""
    threshold_hr: int | None = None
    # "5:13" oder Sekunden je Kilometer.
    threshold_pace: str | None = None


@router.post("/profile/thresholds")
def set_thresholds(body: ThresholdsIn, db: Session = Depends(get_db)):
    """Schwellenpuls und Schwellenpace eintragen.

    Der Schwellenpuls ist die Bezugsgröße der pulsbasierten TSS. Fehlt er,
    wird ersatzweise die Obergrenze von Zone 2 benutzt — die liegt tiefer und
    lässt jede Einheit belastender aussehen, als sie war.
    """
    from fastapi import HTTPException

    profile = resolve_profile(db)
    if not profile:
        raise HTTPException(status_code=404, detail="Kein Profil gefunden")

    if body.threshold_hr is not None:
        if not 100 <= body.threshold_hr <= 230:
            raise HTTPException(status_code=422, detail="Schwellenpuls außerhalb des Plausiblen (100–230)")
        if profile.max_hr and body.threshold_hr >= profile.max_hr:
            raise HTTPException(
                status_code=422,
                detail=f"Schwellenpuls muss unter dem Maximalpuls liegen ({profile.max_hr})",
            )
        profile.threshold_hr = body.threshold_hr

    if body.threshold_pace:
        text = body.threshold_pace.strip()
        try:
            if ":" in text:
                minuten, sekunden = text.split(":")
                sek_pro_km = int(minuten) * 60 + int(sekunden)
            else:
                sek_pro_km = int(float(text))
        except (ValueError, TypeError):
            raise HTTPException(status_code=422, detail=f"Pace nicht lesbar: {text!r} (erwartet MM:SS)")
        if not 120 <= sek_pro_km <= 900:
            raise HTTPException(status_code=422, detail="Pace außerhalb des Plausiblen (2:00–15:00 /km)")
        profile.threshold_pace_s_per_km = sek_pro_km

    profile.threshold_source = "manual"
    db.commit()
    db.refresh(profile)
    return {
        "threshold_hr": profile.threshold_hr,
        "threshold_pace_s_per_km": profile.threshold_pace_s_per_km,
        "source": "manual",
    }


@router.delete("/profile/thresholds")
def clear_thresholds(db: Session = Depends(get_db)):
    """Laufwerte zurücknehmen — danach greift die Ableitung wieder."""
    from fastapi import HTTPException

    profile = resolve_profile(db)
    if not profile:
        raise HTTPException(status_code=404, detail="Kein Profil gefunden")
    profile.threshold_hr = None
    profile.threshold_pace_s_per_km = None
    profile.threshold_source = None
    db.commit()
    return {"status": "zurückgesetzt"}


@router.delete("/profile/swim-test")
def clear_swim_test(db: Session = Depends(get_db)):
    """Eintrag zurücknehmen — danach greift die Ableitung wieder."""
    from fastapi import HTTPException

    profile = resolve_profile(db)
    if not profile:
        raise HTTPException(status_code=404, detail="Kein Profil gefunden")
    profile.css_pace_s_per_100m = None
    profile.css_source = None
    profile.css_t400_s = None
    profile.css_t200_s = None
    profile.swim_threshold_hr = None
    profile.swim_threshold_source = None
    db.commit()
    return {"status": "zurückgesetzt"}


@router.patch("/profile")
def update_profile(data: dict, db: Session = Depends(get_db)):
    from fastapi import HTTPException

    profile = resolve_profile(db)
    if not profile:
        raise HTTPException(status_code=404, detail="Kein Profil gefunden")
    # Die Zonengrenzen sind ausdrücklich änderbar: Wer von Garmin kommt, hat
    # dort bereits gemessene Bereiche stehen und soll sie nicht durch eine
    # Prozentrechnung aus dem Maximalpuls ersetzt bekommen.
    ZONEN = ["z1_hr_max", "z2_hr_min", "z2_hr_max",
             "z3_hr_min", "z3_hr_max", "z4_hr_min", "z4_hr_max"]
    # Eine von Hand eingetragene FTP als solche festhalten — etwa der Wert,
    # den ein Smart Trainer am Ende eines Stufentests ausgibt. Ohne das
    # Feld liesse sie sich in der Oberfläche nicht von der Voreinstellung
    # unterscheiden, und das automatische Ableiten würde sie kommentarlos
    # ersetzen.
    if "ftp_watts" in data:
        profile.ftp_source = "manual"

    allowed = {"ftp_watts", "max_hr", "name", "race_goal",
               "threshold_hr", "threshold_pace_s_per_km",
               *ZONEN}
    zone_fields = {"ftp_watts", "max_hr", "threshold_hr",
                   "threshold_pace_s_per_km", *ZONEN}

    # Zusammen prüfen, nicht Feld für Feld: Eine einzelne Grenze ist für sich
    # genommen immer plausibel — falsch wird erst die Reihenfolge. Ein
    # Zwischenstand mit z2_min > z2_max ließe die Zonenanzeige leerlaufen
    # und die pulsbasierte TSS gegen Unsinn rechnen.
    if any(k in data for k in ZONEN):
        entwurf = {k: data.get(k, getattr(profile, k)) for k in ZONEN}
        if any(v is None for v in entwurf.values()):
            raise HTTPException(status_code=422, detail="Zonengrenzen dürfen nicht leer sein")
        folge = [entwurf[k] for k in ZONEN]
        if any(int(a) >= int(b) for a, b in zip(folge, folge[1:])):
            raise HTTPException(
                status_code=422,
                detail="Die Zonengrenzen müssen aufsteigend sein: "
                       "Z1-Ende < Z2-Start < Z2-Ende < Z3-Start < … < Z4-Ende.",
            )
        obergrenze = data.get("max_hr", profile.max_hr)
        if obergrenze and int(entwurf["z4_hr_max"]) > int(obergrenze):
            raise HTTPException(
                status_code=422,
                detail=f"Z4-Ende ({entwurf['z4_hr_max']}) liegt über dem "
                       f"Maximalpuls ({obergrenze}).",
            )

    for key, value in data.items():
        if key in allowed:
            setattr(profile, key, value)
            # Von Hand gesetzte Werte dürfen ein Benchmark-Lauf nicht
            # stillschweigend überschreiben.
            if key in zone_fields:
                profile.zones_source = "manual"
                # Auch beim Eintragen von Hand: Ohne Zeitpunkt lässt sich
                # später nicht sagen, wie alt der Wert ist — und genau daran
                # hängt, wann der nächste Test fällig wird.
                profile.zones_updated_at = datetime.utcnow()
    db.commit()
    db.refresh(profile)
    return _profile_out(db, profile)
