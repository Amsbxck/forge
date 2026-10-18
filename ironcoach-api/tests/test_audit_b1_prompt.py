"""Audit B1 — Prompt-Schicht. Jeder Test hier beschreibt einen gefundenen Fehler.

Aus der Code-Prüfung vom 18.10.2026. Die Fehler sind behoben; die Tests
halten das erwartete Verhalten fest.
"""

import asyncio
from datetime import date
from types import SimpleNamespace

import pytest

from core.prompt_templates import build_plan_prompt
from services.plan_generator import build_athlete_dict


def _profil(**extra):
    werte = dict(
        name="Prüfathlet", ftp_watts=250, max_hr=190,
        z1_hr_max=133, z2_hr_min=134, z2_hr_max=162, z3_hr_min=163,
        z3_hr_max=171, z4_hr_min=172, z4_hr_max=181,
        # So legt die Registrierung das Profil an: Renndatum als Platzhalter
        # (heute + 180), Zielzeit aus dem Spaltenvorgabewert in models.py.
        race_date=date(2027, 4, 16), race_goal="sub 5:30h 70.3",
        plan_start_date=date(2026, 10, 12),
        css_pace_s_per_100m=None, swim_threshold_hr=None,
    )
    werte.update(extra)
    return SimpleNamespace(**werte)


def _ziel(**extra):
    werte = dict(
        label="Laufen Halbmarathon", goal_time=None, race_name="Stadtlauf",
        total_weeks=14, race_date=date(2027, 9, 12), sport="running",
    )
    werte.update(extra)
    return SimpleNamespace(**werte)


# ── Checkliste 1: Datum und Zielzeit des Saisonziels ─────────────────────────

def test_prompt_nennt_renntag_und_zielzeit_des_saisonziels():
    """`build_athlete_dict` liest `race_date` und `race_goal` aus dem Profil.

    Für ein Ziel ohne Zielzeit steht damit im Prompt „Stadtlauf am 2027-04-16"
    (der Platzhalter aus der Registrierung) und „Zielzeit: sub 5:30h 70.3" —
    die Zielzeit eines fremden Athleten für eine andere Sportart.
    """
    athlet = build_athlete_dict(_profil(), _ziel())
    prompt = build_plan_prompt(athlet, [], [], week=3,
                               plan_start=date(2027, 6, 14), total_weeks=14)
    assert "am 2027-09-12" in prompt, "Renntag des Saisonziels fehlt"
    assert "2027-04-16" not in prompt, "Platzhalter-Renndatum aus dem Profil"
    assert "sub 5:30h 70.3" not in prompt, "fremde Zielzeit aus dem Profil-Default"


def test_systemprompt_nennt_renntag_des_saisonziels(monkeypatch):
    """Derselbe Fehler im Systemprompt (`claude_service.generate_weekly_plan`):
    „Ziel: … am {profile.race_date}, sub 5:30h 70.3"."""
    import database
    import services.api_budget as budget
    import services.claude_service as cs
    import core.deps as deps

    gesendet = {}

    class _Antwort:
        usage = SimpleNamespace(input_tokens=0, output_tokens=0)
        stop_reason = "tool_use"
        content = [SimpleNamespace(type="tool_use", name="create_training_plan",
                                   input={"days": []})]

    async def erstellen(**kwargs):
        gesendet.update(kwargs)
        return _Antwort()

    monkeypatch.setattr(cs.client.messages, "create", erstellen)
    monkeypatch.setattr(budget, "ensure_budget", lambda *a, **k: None)
    monkeypatch.setattr(budget, "record", lambda *a, **k: None)
    monkeypatch.setattr(deps, "resolve_user", lambda db: None)
    monkeypatch.setattr(database, "SessionLocal",
                        lambda: SimpleNamespace(close=lambda: None))

    athlet = build_athlete_dict(_profil(), _ziel())
    asyncio.run(cs.generate_weekly_plan(
        athlete_profile=athlet, last_sessions=[], hrv_data=[], week_number=3,
        plan_start=date(2027, 6, 14), total_weeks=14,
    ))
    system = gesendet["system"]
    assert "2027-09-12" in system, system
    assert "sub 5:30h" not in system, system


# ── Checkliste 9/16: Off Season ohne Saisonziel ──────────────────────────────

def _offseason_prompt(woche):
    athlet = build_athlete_dict(_profil(), None)
    return build_plan_prompt(
        athlet, [], [], week=woche, plan_start=date(2026, 10, 12),
        total_weeks=33, offseason="## OFF SEASON (KRITISCH)\n- kein Ziel",
    )


def test_offseason_ohne_ziel_keine_negative_woche_nach_dem_saisonziel():
    """Ohne Ziel kommt die Woche aus dem Profilanker (Registrierungsmontag).

    `prompt_templates.py:635` rechnet `week - total_weeks` — für ein frisch
    registriertes Konto (Woche 1) steht im Prompt
    „Off Season, -32. Woche nach dem Saisonziel", obwohl es keines gibt.
    """
    prompt = _offseason_prompt(1)
    assert "-32. Woche nach dem Saisonziel" not in prompt


def test_offseason_ohne_ziel_keine_deload_ansage():
    """`is_deload(12, 33)` ist wahr (letzte Base-Woche). Ein Athlet ohne Ziel
    in Profilwoche 12 bekommt im Off-Season-Prompt die Zeile
    „🔄 DELOAD-WOCHE: Volumen -40-50%" — eine Aufbaulogik, die der
    Off-Season-Block direkt darüber ausschließt."""
    prompt = _offseason_prompt(12)
    assert "DELOAD-WOCHE" not in prompt


# ── Checkliste 5: gespeicherte Off-Season-Phase „Übergang" ───────────────────

def test_offseason_uebergang_gehoert_zur_familie_off_season():
    """`plan_generator.py:301` speichert „Off Season · Übergang" in den ersten
    zwei Wochen nach dem Rennen. `PHASEN_ALIAS` kennt nur „· Formerhalt".

    Folge: `vorrang_block` (in `plan_adjust.systemprompt`) liefert für
    „Übergang" eine Rangordnung, für „Formerhalt" nichts."""
    from core.phasenregeln import vorrang_block
    from core.race_types import phase_family

    assert phase_family("Off Season · Übergang") == "Off Season"
    assert vorrang_block("Off Season · Übergang") == vorrang_block(
        "Off Season · Formerhalt")


# ── Checkliste 12: Beispielwerte eines einzelnen Athleten ────────────────────

def test_keine_fremden_beispielwerte_im_plan_prompt():
    """Die Kommentare `prompt_templates.py:196-207` sagen, 145-155 W seien die
    Bereiche eines bestimmten Athleten und entfernt worden. Das JSON-Beispiel
    der Aufgabe (`:799`) trägt sie weiter — als Z2-Einheit. Ebenso die Pace
    6:00–6:50/km als 360/410 s (`:218`, `:227`), die
    `test_prompt_ohne_fremde_vorgaben` nur in der Schreibweise „6:00-6:50"
    sucht."""
    athlet = build_athlete_dict(_profil(), None)
    prompt = build_plan_prompt(athlet, [], [], week=5, plan_start=date(2026, 10, 12))
    assert '"watts_low": 145, "watts_high": 155' not in prompt
    assert '"pace_low_s_per_km": 360, "pace_high_s_per_km": 410' not in prompt


# ── Sportart wird nicht an den Prompt durchgereicht ──────────────────────────

def test_laufziel_bekommt_keine_schwimmvorgabe():
    """`race_types.SPORT_DISCIPLINES` legt fest, dass ein Laufplan kein
    Schwimmen und keinen Brick enthält — die Tabelle wird nirgends gelesen.
    `build_athlete_dict` reicht die Sportart nicht weiter, und die Vorlage
    verlangt für jeden „Schwimmen 2×/Woche", Brick-Progression und
    Freiwasser ab Peak."""
    athlet = build_athlete_dict(_profil(), _ziel(sport="running"))
    prompt = build_plan_prompt(athlet, [], [], week=3,
                               plan_start=date(2027, 6, 14), total_weeks=14)
    assert "- 2×/Woche, **nur Termin und Dauer**" not in prompt
    assert "## BRICK-SESSIONS" not in prompt


# ── Checkliste 8/15: Widersprüche zur Evidenz ────────────────────────────────

def test_hrv_gelb_senkt_nicht_alle_prozentwerte():
    """`prompt_templates.py:661`: „🟡 gelb: alle Prozentwerte um 3–5 %
    reduzieren". `bike-training.md` (Daily rule): „Do not water down VO2max /
    30/15 sessions by lowering %FTP … Small reductions (−3 to 5 %) are
    acceptable only for sweet spot / threshold sessions." `TRAININGSOPTIONEN.md`
    sagt dasselbe („nicht einfach die Prozente senken")."""
    athlet = build_athlete_dict(_profil(), None)
    prompt = build_plan_prompt(athlet, [], [], week=15, plan_start=date(2026, 10, 12))
    assert "alle Prozentwerte um 3–5 % reduzieren" not in prompt


def test_rotation_im_peak_schlaegt_nur_peak_formate_vor(monkeypatch):
    """`intervall_format.rotation_block` läuft in Build **und** Peak, schlägt
    fürs Rad aber fest „30/15, 4x8 oder 5x5" vor. `PHASENREGELN["Peak"]["rad"]`
    erlaubt nur wettkampftempo_rad, threshold_lang und 4x8; das Glossar nennt
    den Formatwechsel nur für den Aufbau."""
    import services.intervall_format as fmt

    monkeypatch.setattr(
        fmt, "letzte_formate",
        lambda db, bis, wochen, user_id=None: [(date(2026, 10, 6), "bike", "vo2max", "4x8")],
    )
    text = fmt.rotation_block(None, date(2026, 10, 12), "Peak 2")
    assert "30/15" not in text, text


def test_glossar_blockwoche_deckt_sich_mit_phasenregeln():
    """`TRAININGSOPTIONEN.md` (Blockwoche): „nur Aufbau (Base/Build)".
    `PHASENREGELN["Base"]` hat kein `block_moeglich` — nur „Build". Der
    bestehende Test prüft nur die Teilzeichenkette „nur Aufbau"."""
    import pathlib

    from core.phasenregeln import PHASENREGELN

    text = (pathlib.Path(__file__).resolve().parent.parent.parent
            / "TRAININGSOPTIONEN.md").read_text(encoding="utf-8")
    if "nur Aufbau (Base/Build)" in text:
        assert PHASENREGELN["Base"].get("block_moeglich"), (
            "Glossar verspricht die Blockwoche in Base, der Code erlaubt sie nicht")
