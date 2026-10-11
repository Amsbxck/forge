"""Die Aufrufstellen der Prompt-Bauer müssen zu ihren Signaturen passen.

Ein Schlüsselwort, das der Aufrufer übergibt und die Funktion nicht kennt, wirft
erst zur Laufzeit. Das blieb unentdeckt, weil der einzige Test, der
`/api/plan/generate` anfasst, genau die Funktion mit der falschen Signatur durch
einen `AsyncMock` ersetzt — und der schluckt jedes beliebige Schlüsselwort. Die
Planerzeugung war deshalb in Produktion tot, während die Suite grün blieb.

Geprüft wird hier nicht ein einzelner Parameter, sondern die Beziehung: alles,
was der Aufrufer nennt, muss die Funktion annehmen können. Das fängt auch den
nächsten Parameter, der dazukommt.
"""

import ast
import inspect
from pathlib import Path

import pytest


def _schluesselwoerter(quelldatei: Path, funktion: str) -> set[str]:
    """Die Schlüsselwörter, mit denen `funktion` in `quelldatei` gerufen wird."""
    baum = ast.parse(quelldatei.read_text(encoding="utf-8"))
    namen: set[str] = set()
    for knoten in ast.walk(baum):
        if not isinstance(knoten, ast.Call):
            continue
        ziel = knoten.func
        gerufen = (
            ziel.id if isinstance(ziel, ast.Name)
            else ziel.attr if isinstance(ziel, ast.Attribute)
            else None
        )
        if gerufen != funktion:
            continue
        for kw in knoten.keywords:
            # **kwargs hat arg=None und sagt über die Namen nichts aus.
            if kw.arg is not None:
                namen.add(kw.arg)
    return namen


def _annehmbar(funktion) -> tuple[set[str], bool]:
    sig = inspect.signature(funktion)
    namen = {
        n for n, p in sig.parameters.items()
        if p.kind in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY)
    }
    offen = any(p.kind is p.VAR_KEYWORD for p in sig.parameters.values())
    return namen, offen


BASIS = Path(__file__).resolve().parent.parent

AUFRUFE = [
    ("services/plan_generator.py", "generate_weekly_plan",
     "services.claude_service", "generate_weekly_plan"),
    ("services/claude_service.py", "build_plan_prompt",
     "core.prompt_templates", "build_plan_prompt"),
]


@pytest.mark.parametrize("quelle,aufruf,modul,funktion", AUFRUFE)
def test_aufrufstelle_passt_zur_signatur(quelle, aufruf, modul, funktion):
    import importlib

    ziel = getattr(importlib.import_module(modul), funktion)
    uebergeben = _schluesselwoerter(BASIS / quelle, aufruf)
    assert uebergeben, f"In {quelle} wurde kein Aufruf von {aufruf}(…) gefunden"

    annehmbar, offen = _annehmbar(ziel)
    if offen:
        return

    unbekannt = uebergeben - annehmbar
    assert not unbekannt, (
        f"{quelle} übergibt an {modul}.{funktion} Schlüsselwörter, die es nicht "
        f"annimmt: {sorted(unbekannt)}. Entweder fehlt der Parameter in der "
        f"Signatur, oder der Aufruf nennt ihn falsch."
    )
