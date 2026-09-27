"""Der Plan-Prompt darf nichts von einem einzelnen Athleten enthalten.

Der Prompt ist aus Amirs persönlichem Coaching-Prompt entstanden. Übrig
geblieben waren daraus: sein Schienbein-Protokoll samt TENS-Anweisung, seine
Pacebereiche, seine Pulszonen — und zwar fest im Text, nicht aus seinem Profil.
Jeder weitere Athlet bekam das mit. Tamina bekam ein Protokoll für eine
Verletzung, die sie nie hatte, und Pulsgrenzen, die 20 Schläge neben ihren
liegen.

Der Test liest den fertig gebauten Prompt eines *anderen* Athleten und prüft,
dass nichts Persönliches darin steht.
"""

from datetime import date

import pytest

from core.prompt_templates import build_plan_prompt

TAMINA = {
    "name": "Tamina",
    "ftp_watts": 180,
    "max_hr": 195,
    "z1_hr_max": 128,
    "z2_hr_min": 129,
    "z2_hr_max": 158,
    "z3_hr_min": 159,
    "z3_hr_max": 172,
    "z4_hr_min": 173,
    "z4_hr_max": 190,
    "race_date": "2027-08-29",
    "race_goal": None,
    "total_weeks": 33,
    "css_pace_s_per_100m": 124.0,
    "swim_threshold_hr": 158,
}


@pytest.fixture
def prompt():
    return build_plan_prompt(TAMINA, [], [], week=12, plan_start=date(2027, 1, 11))


@pytest.mark.parametrize("fremd", [
    "Amir",                    # namentliche Zuschreibung
    "SCHIENBEIN-PROTOKOLL",    # Amirs Reha-Vorgeschichte
    "TENS",                    # seine Behandlung
    "139-173",                 # seine Z2-Pulsgrenzen
    "6:00-6:50",               # seine Laufpace
])
def test_nichts_persoenliches_im_prompt(prompt, fremd):
    assert fremd not in prompt, f"{fremd!r} steht im Prompt eines anderen Athleten"


def test_die_eigenen_zonen_stehen_drin(prompt):
    """Gegenprobe: Die Werte des Athleten selbst müssen ankommen."""
    assert "129-158" in prompt      # ihr Z2
    assert "195 bpm" in prompt      # ihr Maximalpuls
    assert "180W" in prompt         # ihre FTP


def test_gehpausen_sind_werkzeug_keine_vorgabe(prompt):
    """Walk-Run bleibt möglich — auf Wunsch oder aus Gesundheitsgründen.

    Es war vorher die Grundeinstellung für jeden Lauf. Das ist eine
    Anpassung an eine Verletzung und gehört niemandem sonst vorgeschrieben.
    """
    assert "walk_run" in prompt, "als Trainingstyp weiterhin verfügbar"
    assert "IMMER als Walk-Run" not in prompt
    assert "Gehpausen" in prompt and "Grundeinstellung" in prompt


def test_keine_erfundene_pace(prompt):
    """Ohne gemessene Schwellenpace darf keine Zahl entstehen."""
    assert "keine Pace erfinden" in prompt
