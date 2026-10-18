"""Die Rangordnung muss in **allen drei** Pfaden stehen, nicht nur im Plan.

Der erste Entwurf wollte sie als Absatz in `doppel_block` unterbringen. Das
wäre falsch gewesen, und zwar nachweisbar:

  * `doppel_block` endet früh, wenn die Phase keine Doppeltage erlaubt — Taper
    und Wettkampfwoche hätten gar keine Rangordnung bekommen, obwohl dort ein
    Wunsch am häufigsten gegen den Plan steht.
  * `core/prompt_templates.py` unterdrückt `doppel_block` in der Off Season.
  * Der Chat baut seinen Kontext getrennt (`services/coach_context.py`) und
    rendert `doppel_block` überhaupt **nicht**. Der Chat ist aber laut
    `TRAININGSOPTIONEN.md` einer der beiden Wege, auf denen ein Athlet einen
    Wunsch äußert.
  * `services/plan_adjust.py` hat einen eigenen, handgeschriebenen Prompt, der
    `core.phasenregeln` nicht importierte. Sobald ein Plan existiert, geht jede
    Änderung dorthin — ein Knopfdruck „nutze einen Doppeltag" wäre an einen
    Coach gegangen, der von Doppeltagen nichts weiß.

Geprüft wird deshalb die Kreuzprobe: drei Pfade × zwei Phasenlagen. Die
Grundlage ist der interessante Fall, weil dort `phasen_block` unterdrückt ist —
und genau dort lagen die gemessenen Fehltreffer bei der Kraftvorgabe.
"""

from datetime import date, timedelta

import pytest

from core.phasenregeln import vorrang_block

UEBERSCHRIFT = "## RANGORDNUNG, WENN NICHT ALLES HINEINPASST"

PROFIL = {
    "ftp_watts": 264, "threshold_hr": 188, "max_hr": 198, "weight_kg": 78,
    "age": 30, "z1_hr_max": 130, "z2_hr_min": 131, "z2_hr_max": 155,
    "z3_hr_min": 156, "z3_hr_max": 172, "z4_hr_min": 173, "z4_hr_max": 188,
    "name": "T", "total_weeks": 33, "threshold_pace_s_per_km": 286,
    "css_pace_s_per_100m": 117, "swim_threshold_hr": 153,
    "race_date": date(2026, 10, 18), "race_name": "T", "goal_label": "A",
}


# --- Der Baustein selbst ----------------------------------------------------

@pytest.mark.parametrize("phase", [
    "Grundlage", "Vorbereitung auf den Aufbau", "Base 1", "Base 2",
    "Build 1", "Build 2", "Peak", "Taper", "Race Week", "Benchmark",
])
def test_jede_phase_bekommt_eine_rangordnung(phase):
    """Anders als `phasen_block` und `doppel_block` darf er nie leer sein.

    Eine Rangordnung, die in der Grundlage verschwindet, fehlt genau dort, wo
    sieben von acht gemessenen Wochen die Kraftvorgabe verfehlt haben.
    """
    text = vorrang_block(phase)
    assert UEBERSCHRIFT in text, phase
    # Die drei Stufen, die in jeder Phase gelten.
    assert "Gesundheit und Verletzung" in text
    assert "Ruhetag" in text
    assert "Grundbasis der Phase steht" in text
    assert "coaching_comment" in text


def test_nur_die_off_season_bleibt_aussen_vor():
    """Dort bringt `services/offseason.py` die Vorgaben selbst mit.

    Diese Logik ist ausdrücklich unangetastet — zwei Quellen für dieselbe
    Vorgabe wären der nächste Widerspruch.
    """
    assert vorrang_block("Off Season") == ""
    assert vorrang_block("Off Season · Formerhalt") == ""


def test_die_zahlen_der_phase_stehen_drin():
    """Eine Rangordnung ohne Zahlen wäre eine Regel ohne Maß."""
    grundlage = vorrang_block("Grundlage")
    assert "1 Qualitätseinheit" in grundlage
    assert "2 Krafteinheiten" in grundlage

    # Zwei auch im Aufbau: einmal Oberkörper, einmal Unterkörper und Rumpf,
    # wie im Kraftdokument (vorher stand hier eine).
    aufbau = vorrang_block("Build 1")
    assert "2 Qualitätseinheiten" in aufbau
    assert "2 Krafteinheiten" in aufbau

    peak = vorrang_block("Peak")
    assert "1 Krafteinheit" in peak


def test_der_doppeltag_steht_nur_wo_die_phase_ihn_erlaubt():
    """In Taper und Wettkampfwoche ist er kein Mittel — aber die Stufe fehlt nicht."""
    assert "setze einen Doppeltag ein" in vorrang_block("Grundlage")
    taper = vorrang_block("Taper")
    assert "setze einen Doppeltag ein" not in taper
    assert "kein** Mittel" in taper


def test_ohne_phasentabelle_wird_nichts_behauptet():
    """„Benchmark" hat keine Regeln — dann fehlt die Doppeltagstufe ganz.

    Weder „nutze einen Doppeltag" noch „Doppeltage sind hier kein Mittel"
    wäre belegt. Eine erfundene Behauptung ist schlimmer als eine fehlende
    Stufe.
    """
    text = vorrang_block("Benchmark")
    assert "setze einen Doppeltag ein" not in text
    assert "kein** Mittel" not in text
    assert UEBERSCHRIFT in text


# --- Pfad 1: die Planerstellung ---------------------------------------------

@pytest.mark.parametrize("woche,base_period", [
    # Grundlage: `phasen_block` ist unterdrückt, die Rangordnung nicht.
    (-4, "## GRUNDLAGENPHASE\n- Regel\n"),
    # Aufbau: beide stehen da.
    (12, None),
])
def test_planprompt_traegt_die_rangordnung(woche, base_period):
    from core.prompt_templates import build_plan_prompt

    text = build_plan_prompt(
        athlete_profile=PROFIL, sessions=[], hrv=[], week=woche,
        plan_start=date(2026, 11, 9), total_weeks=33,
        base_period=base_period,
    )
    assert UEBERSCHRIFT in text
    if base_period:
        # Der Beweis, dass die Rangordnung nicht an der Phasenvorgabe hängt.
        assert "WOCHENVORGABE DIESER PHASE" not in text


def test_wuensche_bekommen_ein_gewicht():
    """`## Besondere Wünsche` war eine nackte Überschrift ohne Gewichtung.

    Vierzig Zeilen hinter den Phasenregeln, während die Nachbarabschnitte mit
    Gewicht „KRITISCH" dazuschreiben. Jetzt verweist sie auf die Rangordnung.
    """
    from core.prompt_templates import build_plan_prompt

    mit = build_plan_prompt(
        athlete_profile=PROFIL, sessions=[], hrv=[], week=12,
        plan_start=date(2026, 11, 9), total_weeks=33,
        requests="Bitte Donnerstag frei.",
    )
    assert "Gewicht dieser Wünsche" in mit
    assert "zuletzt** gekürzt" in mit

    # Ohne Wünsche kein Gewichtungssatz — sonst Rauschen in jedem Prompt.
    ohne = build_plan_prompt(
        athlete_profile=PROFIL, sessions=[], hrv=[], week=12,
        plan_start=date(2026, 11, 9), total_weeks=33,
    )
    assert "Gewicht dieser Wünsche" not in ohne


# --- Pfad 2: die Tagesanpassung ---------------------------------------------

@pytest.fixture
def plan_mit_tagen(db):
    """Ein Plan mit sieben projizierten Tagen, Phase einstellbar."""
    from models import PlannedSession, User, WeeklyPlan

    nutzer = db.query(User).order_by(User.id.asc()).first()
    angelegt = []
    montag = date(2026, 4, 6)

    def bauen(phase: str):
        plan = WeeklyPlan(
            user_id=nutzer.id, week_number=78, week_start=montag,
            week_end=montag + timedelta(days=6), plan_phase=phase,
            plan_content={"days": []},
        )
        db.add(plan)
        db.commit()
        angelegt.append(plan)
        zeilen = []
        for i in range(7):
            p = PlannedSession(
                user_id=nutzer.id, plan_id=plan.id, week_number=78,
                planned_date=montag + timedelta(days=i), day_name="Tag",
                discipline="bike" if i else "rest",
                training_type="z2_endurance", duration_min=60, day_index=i,
            )
            db.add(p)
            angelegt.append(p)
            zeilen.append(p)
        db.commit()
        return plan, zeilen

    yield bauen
    for o in reversed(angelegt):
        db.delete(o)
    db.commit()


@pytest.mark.parametrize("phase", ["Grundlage", "Build 1"])
def test_anpassungsprompt_traegt_rangordnung_und_doppeltage(plan_mit_tagen, db, phase):
    """Ohne das läuft jeder Knopfdruck bei bestehendem Plan ins Leere.

    Sobald ein Plan existiert, schickt das Frontend an `/plan/anpassen`.
    """
    from services.plan_adjust import systemprompt

    plan, zeilen = plan_mit_tagen(phase)
    text = systemprompt(db, plan, zeilen)

    assert UEBERSCHRIFT in text
    assert "## DOPPELTAGE" in text
    # Der Stand der Grundbasis vor dem Aufruf — der Teil, der die Entfernung
    # der letzten Krafteinheit verhindert statt sie zu melden.
    assert "Stand der Grundbasis" in text
    assert "Krafttraining **0 von 2**" in text or "Krafttraining **0 von 1**" in text
    # Und die Darstellung des Doppeltags, ohne die er nicht lieferbar wäre.
    assert "zwei Einträge mit demselben `date`" in text


def test_anpassungsprompt_nennt_die_blockwoche_als_ausnahme(plan_mit_tagen, db):
    """„Nicht zwei harte hintereinander" widerspricht einer Blockwoche.

    Die Blockwoche läuft deshalb über einen neuen Wochenplan, nicht über
    diesen Pfad — und der Prompt sagt das, statt sich selbst zu widersprechen.
    """
    from services.plan_adjust import systemprompt

    plan, zeilen = plan_mit_tagen("Build 1")
    text = systemprompt(db, plan, zeilen)
    assert "nicht zwei harte hintereinander" in text
    assert "Blockwoche" in text


# --- Pfad 3: der Chat -------------------------------------------------------

def test_chatkontext_traegt_die_rangordnung(db):
    """`_phasen` schweigt in der Grundlage, `doppel_block` rendert der Chat nicht.

    Ohne eigenen Baustein beantwortete der Coach im Gespräch also genau die
    Frage ohne Rangordnung, um die es hier geht: „kann ich diese Woche statt
    Kraft lieber …".
    """
    from services.coach_context import chat_kontext

    ctx = chat_kontext(db)
    assert "vorrang" in ctx, "Der Schlüssel fehlt im Chat-Kontext"


# --- Das Glossar für den Athleten -------------------------------------------

def test_glossar_nennt_dieselbe_reihenfolge():
    """Das Glossar darf nichts versprechen, was der Prompt nicht sagt.

    Es ist die einzige Stelle, an der der Athlet die Rangordnung lesen kann —
    weicht sie vom Prompt ab, ist eine der beiden Seiten eine Lüge.
    """
    import pathlib

    pfad = (pathlib.Path(__file__).resolve().parent.parent.parent
            / "TRAININGSOPTIONEN.md")
    text = pfad.read_text(encoding="utf-8")

    # Die Ruhetagsregel mit ihrer Zahl — vorher gab es sie im Code nirgends.
    assert "Mindestens ein vollständiger Ruhetag" in text
    assert "Mindestens ein vollständiger Ruhetag" in vorrang_block("Grundlage")

    # Der Doppeltag ohne Wunsch, der eine Fall, der von selbst kommt.
    assert "von selbst" in text
    assert "ohne dass der Athlet darum bittet" in vorrang_block("Grundlage")

    # Und die Darstellung, ohne die die zweite Einheit nicht zählt.
    assert "zwei Einträge am selben Datum" in text


@pytest.mark.parametrize("phase", ["Grundlage", "Build 1"])
def test_chatprompt_rendert_den_schluessel(phase):
    """Ein Schlüssel im Wörterbuch nützt nichts, wenn ihn niemand einsetzt.

    Genau das war der Fehler, den dieser Test ausschließt: `wochenform` und
    `phasen` werden an einer einzigen Stelle interpoliert, und ein neuer
    Schlüssel daneben wäre still liegen geblieben.
    """
    import inspect

    from services import claude_service

    quelle = inspect.getsource(claude_service)
    assert 'current_week_context.get("vorrang")' in quelle
