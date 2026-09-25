"""Ordnerstruktur im Vault: eine Saison, ein Ordner.

Flach unter `Plans/` ist `Woche-12.md` nach der zweiten Saison doppelt belegt,
und `run/base/` sammelt Jahre ohne erkennbare Zuordnung. Diese Tests halten
fest, wie der Saisonordner bestimmt wird und wo er im Pfad steht.
"""

from datetime import date, timedelta

from core.saison import fenster, ordnername, saison_name
from services.obsidian.notes import note_path
from services.obsidian.plan_note import plan_note_path


class Ziel:
    """Ein A-Rennen, so viel wie `saison_name` davon braucht."""

    def __init__(self, race_date, plan_start_date=None, race_name=None, total_weeks=33):
        self.race_date = race_date
        self.plan_start_date = plan_start_date
        self.race_name = race_name
        self.total_weeks = total_weeks


ZELL = Ziel(date(2026, 8, 31), date(2026, 1, 12), "Ironman 70.3 Zell am See")


def test_tag_im_vorbereitungsfenster_gehoert_zur_saison():
    assert saison_name(date(2026, 5, 4), [ZELL]) == "Ironman 70.3 Zell am See 2026"


def test_planbeginn_und_wettkampftag_gehoeren_dazu():
    # Die Grenzen selbst zählen mit: sonst läge die erste Planwoche in der
    # Offseason und der Wettkampftag im Ordner des Folgejahres.
    assert saison_name(date(2026, 1, 12), [ZELL]).startswith("Ironman")
    assert saison_name(date(2026, 8, 31), [ZELL]).startswith("Ironman")


def test_nach_dem_rennen_ist_offseason():
    assert saison_name(date(2026, 10, 5), [ZELL]) == "Offseason 2026"


def test_vor_dem_ersten_rennen_ist_grundlage_keine_offseason():
    """Der Fall eines neuen Athleten.

    Tamina hat sich im September angemeldet, ihr Aufbau beginnt im Januar.
    Ihre ersten vier Monate landeten in "Offseason 2026" — einem Ordner für
    eine Saison, die sie nie hatte. "Grundlage" ist das Wort, das die App für
    diese Zeit ohnehin verwendet, im Dashboard wie in der Phasenlogik.
    """
    assert saison_name(date(2025, 11, 3), [ZELL]) == "Grundlage 2025"

    tamina = Ziel(date(2027, 8, 29), date(2027, 1, 17), "Ironman 70.3 Zell am See")
    assert saison_name(date(2026, 9, 26), [tamina]) == "Grundlage 2026"
    assert saison_name(date(2026, 12, 15), [tamina]) == "Grundlage 2026"
    # Nach ihrem Rennen ist es dann eine echte Offseason.
    assert saison_name(date(2027, 9, 5), [tamina]) == "Offseason 2027"


def test_ohne_ziele_ist_grundlage():
    """Wer noch kein Ziel gesetzt hat, war in keiner Saison."""
    assert saison_name(date(2026, 3, 1), []) == "Grundlage 2026"


def test_vorbereitung_ueber_den_jahreswechsel_bleibt_ein_ordner():
    """Das Jahr kommt vom Wettkampf, nicht vom Tag.

    Ein Aufbau, der im Dezember beginnt, läge sonst halb in "… 2025" und halb
    in "… 2026" — also genau die Zersplitterung, die der Ordner verhindert.
    """
    ziel = Ziel(date(2026, 6, 27), date(2025, 12, 22), "Roth")
    assert saison_name(date(2025, 12, 29), [ziel]) == "Roth 2026"
    assert saison_name(date(2026, 4, 1), [ziel]) == "Roth 2026"


def test_fenster_ohne_planbeginn_wird_zurueckgerechnet():
    """Wer kein Startdatum setzt, soll nicht in der Offseason landen."""
    ziel = Ziel(date(2026, 6, 27), None, "Roth", total_weeks=40)
    beginn, ende = fenster(ziel)
    assert ende == date(2026, 6, 27)
    assert beginn == date(2026, 6, 27) - timedelta(weeks=40)
    assert saison_name(date(2026, 1, 15), [ziel]) == "Roth 2026"


def test_ziel_ohne_namen_faellt_auf_die_distanz_zurueck():
    class Namenlos(Ziel):
        label = "Mitteldistanz (70.3)"

    ziel = Namenlos(date(2026, 8, 31), date(2026, 1, 12))
    assert saison_name(date(2026, 5, 4), [ziel]) == "Mitteldistanz (70.3) 2026"


def test_ordnername_entfernt_zeichen_die_obsidian_kapert():
    # `#`, `[`, `]` und `^` leiten in Obsidian Tags, Links und Blockverweise
    # ein — im Pfad hätte "Ironman 70.3 #1" einen Anker erzeugt.
    assert ordnername("Ironman 70.3 #1") == "Ironman 70.3 1"
    assert ordnername("Nizza / Frankreich") == "Nizza Frankreich"
    assert ordnername("  ") == "Unbenannt"


def test_frueheres_ziel_gewinnt_bei_ueberschneidung():
    a = Ziel(date(2026, 6, 27), date(2025, 12, 22), "Roth")
    b = Ziel(date(2026, 8, 31), date(2026, 3, 1), "Zell")
    # Sortiert nach Wettkampfdatum, wie `saison_ziele` liefert.
    assert saison_name(date(2026, 4, 1), [a, b]) == "Roth 2026"


# --- Pfade -------------------------------------------------------------------

def test_einheit_liegt_unter_sportart_saison_intensitaet():
    pfad = note_path(
        "run", date(2026, 5, 4), 12345, "Training",
        intensity="base", saison="Ironman 70.3 Zell am See 2026",
    )
    assert pfad == "Training/run/Ironman 70.3 Zell am See 2026/base/2026-05-04--12345.md"


def test_ohne_saison_bleibt_der_flache_aufbau():
    """Aufrufer ohne Datenbank — und die Vorlage für den Umzug."""
    assert note_path("run", date(2026, 5, 4), 12345, "Training", intensity="base") == (
        "Training/run/base/2026-05-04--12345.md"
    )


def test_wanderung_bekommt_keinen_intensitaetsordner():
    pfad = note_path("hike", date(2026, 10, 5), None, "Training",
                     session_id=7, saison="Offseason 2026")
    assert pfad == "Training/fun/Offseason 2026/2026-10-05--s7.md"


def test_plan_liegt_im_saisonordner():
    class Plan:
        week_number = 12

    assert plan_note_path(Plan(), "Training", "Ironman 70.3 Zell am See 2026") == (
        "Training/Plans/Ironman 70.3 Zell am See 2026/Woche-12.md"
    )


def test_grundlagenwoche_landet_im_offseason_ordner():
    class Plan:
        week_number = -7

    assert plan_note_path(Plan(), "Training", "Offseason 2026") == (
        "Training/Plans/Offseason 2026/Vorlauf-07.md"
    )


# --- Verwaiste Plan-Noten ----------------------------------------------------

class VaultDoppel:
    """Ein Vault im Speicher, so viel wie die Einordnung davon braucht."""

    def __init__(self, dateien):
        self.dateien = dict(dateien)
        self.geloescht = []

    def list_dir(self, path=""):
        praefix = f"{path.rstrip('/')}/"
        namen = set()
        for pfad in self.dateien:
            if not pfad.startswith(praefix):
                continue
            rest = pfad[len(praefix):]
            namen.add(rest if "/" not in rest else rest.split("/", 1)[0] + "/")
        return sorted(namen)

    def get_note(self, path):
        return self.dateien.get(path)

    def put_note(self, path, content):
        self.dateien[path] = content

    def delete_note(self, path):
        self.dateien.pop(path, None)
        self.geloescht.append(path)


def _note(week, week_start):
    return (
        f"---\nweek: {week}\nphase: Base 3\nweek_start: {week_start}\n"
        f"week_end: {week_start}\n---\n\n<!-- ironcoach:start -->x<!-- ironcoach:end -->\n"
    )


def test_verwaiste_note_ordnet_sich_aus_dem_frontmatter_ein():
    """Zu diesen Noten gibt es keine Planzeile mehr — nach einem Umzug auf
    eine neue Installation ist das der Normalfall, nicht die Ausnahme."""
    from services.obsidian.plan_note import verwaiste_plannoten_einordnen

    vault = VaultDoppel({
        "Training/Plans/Woche-11.md": _note(11, "2026-03-30"),
        "Training/Plans/Woche-32.md": _note(32, "2026-08-24"),
        "Training/Plans/Offseason 2026/Vorlauf-07.md": _note(-7, "2026-09-21"),
    })

    ergebnis = verwaiste_plannoten_einordnen(None, vault, "Training", [ZELL])

    assert "Training/Plans/Ironman 70.3 Zell am See 2026/Woche-11.md" in vault.dateien
    assert "Training/Plans/Ironman 70.3 Zell am See 2026/Woche-32.md" in vault.dateien
    assert "Training/Plans/Woche-11.md" not in vault.dateien
    # Was schon in einem Saisonordner liegt, wird nicht angefasst.
    assert "Training/Plans/Offseason 2026/Vorlauf-07.md" in vault.dateien
    assert all(e["status"] == "verschoben" for e in ergebnis)


def test_inhalt_bleibt_beim_umzug_erhalten():
    from services.obsidian.plan_note import verwaiste_plannoten_einordnen

    inhalt = _note(11, "2026-03-30") + "\n## Notizen\n\nRippe zwickt wieder.\n"
    vault = VaultDoppel({"Training/Plans/Woche-11.md": inhalt})
    verwaiste_plannoten_einordnen(None, vault, "Training", [ZELL])
    ziel = "Training/Plans/Ironman 70.3 Zell am See 2026/Woche-11.md"
    assert vault.dateien[ziel] == inhalt


def test_belegtes_ziel_wird_nicht_ueberschrieben():
    """Lieber eine Datei zu viel als eine überschriebene Reflexion."""
    from services.obsidian.plan_note import verwaiste_plannoten_einordnen

    ziel = "Training/Plans/Ironman 70.3 Zell am See 2026/Woche-11.md"
    vault = VaultDoppel({
        "Training/Plans/Woche-11.md": _note(11, "2026-03-30"),
        ziel: "schon da, mit eigenen Notizen",
    })
    ergebnis = verwaiste_plannoten_einordnen(None, vault, "Training", [ZELL])

    assert vault.dateien[ziel] == "schon da, mit eigenen Notizen"
    assert vault.dateien["Training/Plans/Woche-11.md"] is not None
    assert ergebnis == [{"pfad": "Training/Plans/Woche-11.md",
                        "status": "ziel_belegt", "ziel": ziel}]


def test_note_ohne_datum_bleibt_liegen():
    """Raten wäre schlimmer als liegenlassen — im falschen Ordner findet sie
    niemand wieder."""
    from services.obsidian.plan_note import verwaiste_plannoten_einordnen

    vault = VaultDoppel({
        "Training/Plans/Woche-09.md": "---\nweek: 9\nphase: Base\n---\n\nohne Datum\n",
    })
    ergebnis = verwaiste_plannoten_einordnen(None, vault, "Training", [ZELL])

    assert "Training/Plans/Woche-09.md" in vault.dateien
    assert ergebnis == [{"pfad": "Training/Plans/Woche-09.md", "status": "ohne_datum"}]
