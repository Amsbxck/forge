"""Einzelne Tage in einen bestehenden Wochenplan einsetzen.

Warum überhaupt: Eine Änderung an Donnerstag bis Sonntag ging bisher nur über
einen komplett neu geschriebenen Wochenplan — alle sieben Tage mit Blocks,
Watt- und Pacewerten, rund 3000 Token Ausgabe. Drei davon waren unverändert und
wurden trotzdem neu erzeugt. Das kostet nicht nur Geld: Jede Wiederholung ist
eine Gelegenheit, eine Zahl zu verändern, die niemand ändern wollte.

Hier wird stattdessen der bestehende Inhalt genommen und nur ersetzt, was
tatsächlich neu ist. Die unberührten Tage laufen nie durch das Modell und
können sich deshalb auch nicht ändern.

Zwei Grenzen, die nicht verhandelbar sind:

  * **Vergangene Tage bleiben, wie sie waren.** Ein Plan ist auch ein Protokoll
    dessen, was vorgesehen war. Ihn rückwirkend zu ändern macht jeden
    Soll/Ist-Vergleich wertlos.
  * **Absolvierte Tage bleiben ebenfalls.** Sie hängen an einer echten Einheit.
    Die Vorgabe nachträglich auf das zu setzen, was gemacht wurde, erzeugte
    eine perfekte Planerfüllung, die nie stattgefunden hat.
"""

import logging
from datetime import date

logger = logging.getLogger(__name__)


def _als_datum(wert) -> date | None:
    if isinstance(wert, date):
        return wert
    try:
        return date.fromisoformat(str(wert)[:10])
    except (TypeError, ValueError):
        return None


def merge_days(
    basis_content: dict,
    neue_tage: list[dict],
    gesperrte_daten: set[date] | None = None,
    heute: date | None = None,
) -> tuple[dict, list[str], list[str]]:
    """Geänderte Tage in `basis_content` einsetzen.

    Gibt (neuer_inhalt, übernommen, abgewiesen) zurück. Die beiden Listen sind
    für die Antwort an den Athleten: Eine stillschweigend verworfene Änderung
    ist schlimmer als eine abgelehnte, weil er von einem Plan ausgeht, den es
    nicht gibt.
    """
    heute = heute or date.today()
    gesperrt = gesperrte_daten or set()

    inhalt = dict(basis_content or {})
    tage = [dict(t) for t in (inhalt.get("days") or [])]
    nach_datum = {_als_datum(t.get("date")): i for i, t in enumerate(tage)}

    uebernommen: list[str] = []
    abgewiesen: list[str] = []

    for neu in neue_tage:
        tag = _als_datum(neu.get("date"))
        if tag is None:
            abgewiesen.append(f"{neu.get('day') or '?'} (kein gültiges Datum)")
            continue
        if tag not in nach_datum:
            # Ein Datum außerhalb dieser Woche gehört in einen anderen Plan.
            # Es hier anzuhängen ergäbe eine Woche mit acht Tagen.
            abgewiesen.append(f"{tag} (liegt nicht in dieser Woche)")
            continue
        if tag < heute:
            abgewiesen.append(f"{tag} (vergangen)")
            continue
        if tag in gesperrt:
            abgewiesen.append(f"{tag} (bereits absolviert)")
            continue

        # Der gelieferte Tag ersetzt den bisherigen vollständig. Ein Mischen
        # Feld für Feld wäre gefährlicher: Bleibt aus dem alten Tag ein
        # Wattblock stehen, während der neue ein Lauf ist, trägt die Einheit
        # Vorgaben aus zwei verschiedenen Sportarten.
        tage[nach_datum[tag]] = dict(neu)
        uebernommen.append(str(tag))

    inhalt["days"] = tage
    return inhalt, uebernommen, abgewiesen
