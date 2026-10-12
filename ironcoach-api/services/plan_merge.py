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

Ein Doppeltag erscheint als **zwei Einträge mit demselben Datum** — das Schema
trägt eine Sportart je Eintrag, also ist das die einzige Form, in der ein
zweiter Termin am selben Tag für die Zähler und den Soll/Ist-Abgleich sichtbar
wird. Wer einen solchen Tag ändert, liefert alle seine Einträge zusammen.
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

    # Ein Datum kann mehrere Einträge tragen — ein Doppeltag ist genau das.
    # Deshalb Reihenfolge der Daten plus Liste je Datum, nicht ein Index je
    # Datum: `{datum: index}` behielt bei zwei Einträgen nur den letzten, und
    # eine Änderung an diesem Tag ersetzte dann stillschweigend die falsche
    # Hälfte.
    reihenfolge: list[date | None] = []
    bestand: dict[date | None, list[dict]] = {}
    for t in tage:
        tag = _als_datum(t.get("date"))
        if tag not in bestand:
            bestand[tag] = []
            reihenfolge.append(tag)
        bestand[tag].append(t)

    # Die gelieferten Tage nach Datum bündeln. Ein geliefertes Datum ersetzt
    # **alle** bisherigen Einträge dieses Datums — dieselbe Vollersetzung wie
    # bisher, nur auf den ganzen Tag bezogen. Wer einen Doppeltag will, liefert
    # beide Hälften zusammen; wer aus zwei Einheiten eine macht, liefert eine.
    # Die Alternative, auf (Datum, Sportart) zu schlüsseln, hätte das Ändern
    # der Sportart eines Tages zerstört: aus „Lauf wird Rad" wäre „Lauf **und**
    # Rad" geworden.
    gebuendelt: dict[date | None, list[dict]] = {}
    ungueltig: list[str] = []
    for neu in neue_tage:
        tag = _als_datum(neu.get("date"))
        if tag is None:
            ungueltig.append(f"{neu.get('day') or '?'} (kein gültiges Datum)")
            continue
        gebuendelt.setdefault(tag, []).append(dict(neu))

    uebernommen: list[str] = []
    abgewiesen: list[str] = list(ungueltig)

    for tag, gruppe in gebuendelt.items():
        if tag not in bestand:
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
        bestand[tag] = gruppe
        uebernommen.append(str(tag))

    inhalt["days"] = [t for tag in reihenfolge for t in bestand[tag]]
    return inhalt, uebernommen, abgewiesen
