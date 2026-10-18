"""Die Profilseite zeigt dieselben Bereiche, nach denen der Coach plant.

Vorher hielt das Frontend eine eigene Kopie der Grenzen in
`ZoneEditor.jsx` — „bewusst gespiegelt", mit dem Kommentar, man müsse sie
beim Ändern an beiden Stellen anpassen. Genau das ist ausgeblieben:

  * Rad: Die Z3/Z4-Grenze stand dort noch bei 90/91 % FTP. Das Backend hatte
    sie längst auf Coggans 94/95 % korrigiert.
  * Lauf: Z6 (vVO2max) und Z7 (Steigerungen) fehlten ganz, und Z2 war nicht
    in „locker" und „ruhig zügig" geteilt. Die übrigen Grenzen waren alte
    Multiplikatoren, die zu keiner aktuellen Zone passten.

Jetzt rechnet `services/zones.anzeige` aus derselben Tabelle wie der Prompt,
und das Frontend zeigt nur noch an. Diese Tests halten fest, dass beide aus
**einer** Quelle kommen — nicht nur, dass die Zahlen heute stimmen.
"""

from types import SimpleNamespace

from services.zones import (
    LAUF_TEMPO_ZONEN,
    RAD_ZONEN,
    anzeige,
    lauf_zonen,
    rad_zonen,
)

PROFIL = SimpleNamespace(
    threshold_pace_s_per_km=286,   # 4:46/km
    ftp_watts=264,
    css_pace_s_per_100m=117,
)


def test_lauf_hat_alle_sieben_zonen():
    """Der gemeldete Fehler: vVO2max und Steigerungen fehlten."""
    zeilen = anzeige(PROFIL)["lauf"]
    labels = [z["label"] for z in zeilen]
    assert labels == ["Z1", "Z2", "Z2", "Z3", "Z4", "Z5", "Z6", "Z7"]
    namen = [z["name"] for z in zeilen]
    assert "vVO2max" in namen
    assert "Steigerungen" in namen


def test_lauf_kommt_aus_derselben_tabelle_wie_der_prompt():
    """Eine Zeile je Eintrag in `LAUF_TEMPO_ZONEN` — wächst die Tabelle,
    wächst die Anzeige mit. Das ist der Punkt: keine zweite Liste."""
    assert len(anzeige(PROFIL)["lauf"]) == len(LAUF_TEMPO_ZONEN)
    assert len(anzeige(PROFIL)["lauf"]) == len(lauf_zonen(286))


def test_z2_ist_zweimal_gruen():
    """Beide Z2-Hälften tragen Zone 2 — nach Position gefärbt, bekäme die
    zweite die Farbe von Z3."""
    zeilen = anzeige(PROFIL)["lauf"]
    z2 = [z for z in zeilen if z["label"] == "Z2"]
    assert len(z2) == 2
    assert {z["zone"] for z in z2} == {2}
    assert {z["name"] for z in z2} == {"locker", "ruhig zügig"}


def test_lauf_werte_stimmen_mit_dem_prompt_ueberein():
    """Dieselben Pacegrenzen wie im Prompt, Zeile für Zeile."""
    anz = anzeige(PROFIL)["lauf"]
    prompt = lauf_zonen(286)
    for a, p in zip(anz, prompt):
        if p["von"] is None:
            assert a["wert"] == f"> {p['bis']}"
        else:
            assert a["wert"] == f"{p['von']}–{p['bis']}"


def test_vvo2max_und_steigerungen_bei_4_46():
    """Konkrete Werte für eine Schwelle von 4:46/km — nachgerechnet.

    Z6 112–120 %: 286 / 1,20 = 238 s = 3:58, 286 / 1,12 = 255 s = 4:15.
    Z7 120–130 %: 286 / 1,30 = 220 s = 3:40, 286 / 1,20 = 238 s = 3:58.
    """
    zeilen = {z["name"]: z["wert"] for z in anzeige(PROFIL)["lauf"]}
    assert zeilen["vVO2max"] == "4:15–3:58"
    assert zeilen["Steigerungen"] == "3:58–3:40"


def test_rad_grenze_z3_z4_nach_coggan():
    """Die alte Kopie hatte 90/91 % — vier Punkte zu tief."""
    zeilen = {z["label"]: z["wert"] for z in anzeige(PROFIL)["rad"]}
    # 264 × 0,95 = 250,8: 250 W ist noch Z3 (Einstufung: „unter 0,95"),
    # 251 W die erste Schwellenwattzahl. Lückenlos statt 248 / 250.
    assert zeilen["Z3"] == "201–250"
    assert zeilen["Z4"] == "251–279"


def test_rad_kommt_aus_derselben_tabelle_wie_der_prompt():
    assert len(anzeige(PROFIL)["rad"]) == len(RAD_ZONEN)
    assert len(anzeige(PROFIL)["rad"]) == len(rad_zonen(264))


def test_sweet_spot_wird_mitgeliefert():
    """Keine eigene Zone, aber benannt — 88–94 % FTP."""
    assert anzeige(PROFIL)["sweet_spot"] == "232–248"


def test_ohne_schwellenwerte_bleibt_es_leer():
    """Erfundene Bereiche wären schlimmer als keine."""
    leer = anzeige(SimpleNamespace(
        threshold_pace_s_per_km=None, ftp_watts=None, css_pace_s_per_100m=None,
    ))
    assert leer == {"lauf": [], "rad": [], "schwimm": [], "sweet_spot": None}


def test_endpunkt_liefert_die_anzeige(client):
    """Der Weg, den die Profilseite nimmt."""
    r = client.get("/api/profile/zones")
    assert r.status_code == 200
    daten = r.json()
    assert set(daten) == {"lauf", "rad", "schwimm", "sweet_spot"}


def test_frontend_haelt_keine_eigene_kopie_mehr():
    """Die Spiegeltabellen sind weg und kommen nicht wieder.

    Gelesen wird die Datei, nicht ausgeführt: Es geht darum, dass dort keine
    Grenzen mehr stehen, aus denen jemand wieder rechnen könnte.
    """
    import pathlib

    pfad = (pathlib.Path(__file__).resolve().parents[2]
            / "ironcoach-frontend" / "src" / "components" / "ZoneEditor.jsx")
    if not pfad.exists():
        import pytest
        pytest.skip("Frontend im Container nicht eingebunden")
    text = pfad.read_text(encoding="utf-8")
    assert "const LAUF = [" not in text
    assert "const RAD = [" not in text
    assert "getProfileZones" in text
