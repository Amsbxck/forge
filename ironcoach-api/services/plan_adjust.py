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

Früher war das Werkzeug zusätzlich über `tool_choice` erzwungen. Sonnet 5.5
lehnt das mit 400 ab. Jetzt verlangt es der Systemprompt, und es ist das
einzige angebotene Werkzeug.
"""

import json
import logging

from sqlalchemy.orm import Session

from models import PlannedSession, WeeklyPlan

logger = logging.getLogger(__name__)

from core.config import settings  # noqa: E402

MODELL = settings.CLAUDE_MODEL

# Kleiner als beim vollen Plan: Es gehen nur die geänderten Tage zurück, nicht
# sieben. Hier standen 3000, mit der Begründung, mehr Budget lade zur ganzen
# Woche ein. Das Modell sieht `max_tokens` aber gar nicht. Seit Sonnet 5.5
# zählt außerdem das Thinking mit, und 3000 hätte auf Effort medium die Tage
# abgeschnitten.
MAX_TOKENS = 8000


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
            f"{'  [ABSOLVIERT]' if r.status in ('completed', 'replaced') or r.matched_session_id else ''}"
        )
    return "\n".join(zeilen)


def systemprompt(db: Session, plan: WeeklyPlan, rows: list,
                 zonen: str = "") -> str:
    """Der Systemprompt der Tagesanpassung.

    Eigene Funktion, damit er sich ohne Modellaufruf rendern und prüfen lässt.
    Nötig geworden, weil hier genau die Bausteine gefehlt haben, die der
    Plan-Prompt längst hatte: Dieser Prompt war handgeschrieben und importierte
    `core.phasenregeln` nicht — keine Phasenvorgabe, keine Doppeltage, keine
    Rangordnung. Seine einzige Strukturregel war „nicht zwei harte
    hintereinander". Ein Wunsch „nutze einen Doppeltag" ging damit an einen
    Coach, der von Doppeltagen nichts wusste; dieselbe Lücke hat hier schon
    einmal die Pacevorgaben gekostet.

    Die Blöcke werden **importiert, nicht abgeschrieben** — zwei Fassungen
    desselben Textes laufen auseinander.
    """
    from core.phasenregeln import doppel_block, vorrang_block
    from services.week_shape import grundbasis

    phase = plan.plan_phase
    regel_bloecke = "\n".join(
        b for b in (doppel_block(phase), vorrang_block(phase)) if b
    )

    # Der Stand der Grundbasis **vor** dem Aufruf. Das ist der wirksame Teil:
    # Eine Tagesänderung, die die letzte Krafteinheit entfernt, lässt sich so
    # verhindern, statt sie hinterher zu melden.
    stand = ""
    try:
        gb = grundbasis(db, plan.week_start, plan.week_end,
                        user_id=plan.user_id, phase=phase)
        if gb["vorhanden"]:
            frei = gb.get("freie_tage") or []
            stand = (
                f"\n## Stand der Grundbasis in dieser Woche\n"
                f"Krafttraining **{gb['gym']} von {gb['gym_soll']}**, "
                f"{gb['einheiten']} Einheiten auf {gb['trainingstage']} Tagen, "
                f"{gb['ruhetage']} Tage ohne Einheit"
                + (
                    " (" + ", ".join(str(t) for t in frei) + ")"
                    if frei else ""
                )
                + ".\n"
            )
    except Exception as e:  # pragma: no cover - Auskunft darf nie die Änderung reissen
        logger.warning("Grundbasis für die Anpassung nicht ermittelt: %s", e)

    # Trägt die Woche schon einen Doppeltag, soll eine Tagesänderung ihn nicht
    # nebenbei auflösen — und ein neuer Doppeltag-Wunsch keine Einheit
    # dazunehmen (`phasenregeln.UMLEGEN`).
    try:
        from services.doppel_urne import anpassungs_block
        stand += anpassungs_block(db, plan.week_start, plan.week_end, phase,
                                  plan.user_id)
    except Exception as e:  # pragma: no cover - Auskunft darf nie die Änderung reissen
        logger.warning("Doppeltag der Woche nicht ermittelt: %s", e)

    return f"""Du passt einzelne Tage eines bestehenden Wochenplans an.

## Der Plan dieser Woche ({plan.week_start} bis {plan.week_end}, Phase {plan.plan_phase})
{_plan_text(plan, rows)}

## Werte des Athleten
{zonen}
{stand}
{regel_bloecke}

## Auftrag
Setze den Wunsch des Athleten um, indem du `adjust_training_days` aufrufst.
Antworte immer über dieses Werkzeug, nie nur mit Text.

- **Nur die Tage liefern, die sich ändern.** Alles andere bleibt unberührt und
  muss nicht wiederholt werden. Das ist der Zweck dieses Wegs.
- Tage, die mit [ABSOLVIERT] markiert sind, und Tage in der Vergangenheit nicht
  anfassen — sie werden ohnehin abgewiesen.
- Jeder gelieferte Tag braucht `date`, `session_type`, `training_type`,
  `targets` und ausgefüllte `details`; er ersetzt den bisherigen komplett.
- **Ein geliefertes Datum ersetzt alle Einträge dieses Datums.** Ein Doppeltag
  sind zwei Einträge mit demselben `date` — wer ihn ändert, liefert beide
  Hälften; wer einen Doppeltag anlegt, liefert zwei Einträge für diesen Tag.
- Bleibt die Wochenstruktur sinnvoll: Wer einen harten Tag verschiebt, setzt
  nicht zwei harte hintereinander. (Ausnahme ist allein eine ausdrücklich
  geplante Blockwoche — die wird aber nicht hier, sondern mit einem neuen
  Wochenplan erzeugt.)
- **Die Grundbasis oben nicht verletzen.** Entfernt die Änderung die letzte
  Krafteinheit oder die einzige Qualitätseinheit der Woche, setze sie auf einem
  anderen Tag wieder ein — wenn nötig als Doppeltag — und sage es im Satz
  dazu. Den Wunsch nur dann kürzen, wenn beides nicht geht.
- Antworte knapp, ein bis zwei Sätze."""


async def tage_anpassen(db: Session, plan: WeeklyPlan, wunsch: str) -> dict:
    """Den Wunsch auf die Tage dieses Plans anwenden.

    Gibt einen Bericht zurück; die neue Planzeile steckt darin als `plan_id`.
    Wirft nicht für fachliche Fälle — ein abgelehnter Tag ist eine Auskunft,
    kein Fehler.
    """
    from anthropic import AsyncAnthropic

    from core.config import settings
    from core.deps import get_profile
    from services.api_budget import abrechnen, freigeben, reservieren
    from services.claude_service import ADJUST_DAYS_TOOL
    from services.plan_merge import merge_days, plan_text_aus

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
    # Reservieren statt sperren: Die Kontozeile blieb sonst über den ganzen
    # Claude-Aufruf gesperrt (siehe `api_budget.reservieren`).
    reservierung = reservieren(db, nutzer, kind="plan_adjust", model=MODELL,
                               max_output=MAX_TOKENS)

    # Die vollständigen Trainingsbereiche, nicht nur FTP und Puls.
    #
    # Hier standen bisher ausschließlich HF-Zonen Z2 bis Z4 und die FTP. Ein
    # geänderter Tag bekam damit keine Pacevorgabe, obwohl der Wochenplan, in
    # den er eingesetzt wird, durchgehend welche trägt — und seit die
    # Laufbereiche am schnellen Ende drei Stufen haben, hätte ein hier
    # geänderter Lauftag die Zonen anders ausgelegt als der Rest der Woche.
    zonen = ""
    if profil:
        from services.zones import prompt_block as bereiche
        zonen = bereiche(profil) or (
            f"FTP {profil.ftp_watts} W · Maximalpuls {profil.max_hr}"
        )
        zonen += (
            f"\n\nHF-Zonen: Z2 {profil.z2_hr_min}-{profil.z2_hr_max} · "
            f"Z3 {profil.z3_hr_min}-{profil.z3_hr_max} · "
            f"Z4 {profil.z4_hr_min}-{profil.z4_hr_max} · "
            f"Z5 und höher über {profil.z4_hr_max}. "
            f"Oberhalb der Schwelle über Pace und Watt steuern, nicht über den "
            f"Puls."
        )

    system = systemprompt(db, plan, rows, zonen)

    client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    try:
        antwort = await client.messages.create(
            model=MODELL, max_tokens=MAX_TOKENS, system=system,
            tools=[ADJUST_DAYS_TOOL],
            output_config={"effort": settings.CLAUDE_EFFORT_ANPASSUNG},
            messages=[{"role": "user", "content": wunsch}],
        )
    except Exception:
        freigeben(db, reservierung)
        raise

    try:
        abrechnen(db, nutzer, reservierung, kind="plan_adjust", model=MODELL,
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

    # Abgeschnitten: Ohne diese Prüfung sähe eine abgebrochene Antwort aus wie
    # „das Modell wollte nichts ändern“. Der Planpfad prüft das schon lange.
    if getattr(antwort, "stop_reason", None) == "max_tokens":
        raise ValueError(
            "Die Anpassung kam unvollständig zurück (abgeschnitten). "
            "Bitte noch einmal versuchen."
        )

    if not tage:
        return {"status": "keine_aenderung",
                "hinweis": " ".join(text) or "Das Modell hat keine Tage geliefert."}

    # Erledigt heißt wie beim Stornieren: absolviert, ersetzt oder zugeordnet.
    gesperrt = {
        r.planned_date for r in rows
        if r.status in ("completed", "replaced") or r.matched_session_id is not None
    }
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
        # Neu gebaut: die alte Übersicht zeigte sonst die alten Tage.
        plan_text=plan_text_aus(inhalt, plan.week_number, plan.week_start, plan.week_end),
        adjustments_applied=(plan.adjustments_applied or []) + [wunsch[:200]],
    )
    db.add(neu)
    db.commit()
    db.refresh(neu)

    from services.plan_projection import project_plan
    if not project_plan(db, neu):
        # Vorher still: der Plan stand gespeichert, der Kalender blieb leer.
        logger.error("Plan %s nach Anpassung nicht projiziert", neu.id)
        abgewiesen = abgewiesen + [
            "Kalender nicht aktualisiert — bitte Woche neu laden"
        ]

    try:
        from services.obsidian.plan_note import sync_plan_note
        sync_plan_note(db, neu)
    except Exception as e:  # pragma: no cover
        logger.warning("Plan-Note nach Anpassung nicht geschrieben: %s", e)

    # Die Woche nach der Änderung nachzählen.
    #
    # Hier prüfte bisher **nichts**: `services/week_shape.py` wurde weder von
    # hier noch von `plan_merge` gerufen. Eine Tagesänderung, die die letzte
    # Krafteinheit entfernt, fiel damit niemandem auf.
    #
    # Nach `project_plan` und in eigenem `try`: Die Projektion schluckt jede
    # Ausnahme, ein Zähler darin wäre unsichtbar ausgefallen — und er liest die
    # projizierten Zeilen, muss also danach laufen.
    befund = None
    try:
        from services.week_shape import nach_anpassung
        befund = nach_anpassung(db, neu.week_start, neu.week_end,
                                plan.plan_phase, user_id=neu.user_id)
    except Exception as e:  # pragma: no cover - Auskunft darf die Änderung nie reissen
        logger.warning("Wochenform nach Anpassung nicht geprüft: %s", e)

    if befund:
        # In beides: `adjustments_applied` ist das Protokoll, `hinweis` ist das
        # Einzige, was das Frontend im Moment der Änderung anzeigt. Nur im
        # Protokoll wäre der Befund genau dann unsichtbar, wenn er zählt.
        neu.adjustments_applied = (neu.adjustments_applied or []) + [befund]
        db.commit()

    return {
        "status": "angepasst",
        "plan_id": neu.id,
        "geaendert": uebernommen,
        "abgewiesen": abgewiesen,
        "hinweis": " ".join(text + ([befund] if befund else [])),
    }
