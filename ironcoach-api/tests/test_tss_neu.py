"""TSS gegen die heutigen Schwellenwerte neu rechnen.

Die TSS wird beim Import einmal berechnet und danach nie wieder angefasst.
Ändert sich später die Schwelle, stehen alte und neue Einheiten auf
verschiedenen Bezugsgrössen — und genau daraus entsteht die Formkurve, die über
jede Planung entscheidet.

Amirs Fall: Seine FTP stand durch einen falsch erkannten Test auf 175 statt 264.
Eine fünfeinhalbstündige Grundlagenausfahrt bekam dadurch 598 TSS — ein
Intensitätsfaktor von 1,05, also fünfeinhalb Stunden über der Schwelle.
"""

from datetime import date

import pytest

from models import TrainingSession, User
from services.tss_neu import IF_UNMOEGLICH, _tss_neu, neu_rechnen


class Profil:
    def __init__(self, ftp_watts=264, threshold_hr=188, z2_hr_max=176, swim_threshold_hr=153):
        self.ftp_watts = ftp_watts
        self.threshold_hr = threshold_hr
        self.z2_hr_max = z2_hr_max
        self.swim_threshold_hr = swim_threshold_hr


class Einheit:
    def __init__(self, **kw):
        self.discipline = kw.get("discipline", "bike")
        self.duration_min = kw.get("duration_min", 60)
        self.normalized_power = kw.get("normalized_power")
        self.avg_watts = kw.get("avg_watts")
        self.avg_hr = kw.get("avg_hr")
        self.tss = kw.get("tss")


def test_amirs_ausfahrt_wird_plausibel():
    """598 TSS für eine Grundlagenausfahrt war der sichtbarste Schaden."""
    neu, grund = _tss_neu(
        Einheit(duration_min=327, normalized_power=158, avg_watts=133, avg_hr=136),
        Profil(),
    )
    assert neu == 195.2
    assert "FTP 264" in grund
    intensitaet = (neu / ((327 / 60) * 100)) ** 0.5
    assert intensitaet < 0.7, "eine fünfeinhalbstündige Ausfahrt liegt weit unter der Schwelle"


def test_durchschnittswatt_ist_kein_np_ersatz():
    """Der Fund aus der Vorschau.

    Taminas Samstagsfahrt hatte keine NP. Mit ihrem Durchschnitt von 116 W als
    Ersatz fiel die TSS von 346 auf 188 — nicht weil die alte Zahl falsch war,
    sondern weil ein Durchschnitt jedes Rollen und jede Ampel mitträgt. Ohne NP
    ist der Puls die ehrlichere Grundlage.
    """
    ohne_np = Einheit(duration_min=306, avg_watts=116, avg_hr=149)
    neu, grund = _tss_neu(ohne_np, Profil(ftp_watts=191, threshold_hr=181))
    assert grund.startswith("HF"), grund
    assert neu == pytest.approx(345.6, abs=1.0)


def test_mit_np_gilt_die_leistung():
    neu, grund = _tss_neu(Einheit(duration_min=60, normalized_power=264, avg_hr=170), Profil())
    assert grund.startswith("NP")
    assert neu == 100.0, "eine Stunde genau an der Schwelle ist definitionsgemäß 100 TSS"


def test_schwimmen_nutzt_den_eigenen_schwellenpuls():
    """Im Wasser liegt der Puls tiefer; mit dem Laufwert fiele jede Schwimm-TSS
    zu niedrig aus."""
    _, grund = _tss_neu(Einheit(discipline="swim", duration_min=45, avg_hr=134), Profil())
    assert "153" in grund


def test_ohne_grundlage_keine_zahl():
    neu, grund = _tss_neu(Einheit(duration_min=60), Profil(threshold_hr=None, z2_hr_max=None))
    assert neu is None
    assert grund == "keine Grundlage"


def test_unmoegliche_werte_werden_gemeldet_nicht_geschrieben(db):
    """Bleibt der Wert auch neu unmöglich, stimmt die Schwelle noch nicht.

    Dann wird gemeldet statt geschrieben — sonst ersetzt eine falsche Zahl die
    andere und niemand sieht es.
    """
    nutzer = db.query(User).first()
    s = TrainingSession(
        user_id=nutzer.id, session_date=date(2026, 10, 1), discipline="bike",
        duration_min=240, normalized_power=300, week_number=1, tss=10.0,
    )
    db.add(s); db.commit()

    bericht = neu_rechnen(db, nutzer, apply=True)
    treffer = [u for u in bericht["unmoeglich"] if u["session_id"] == s.id]
    assert treffer, bericht
    assert str(IF_UNMOEGLICH) in treffer[0]["hinweis"]

    db.refresh(s)
    assert s.tss == 10.0, "nicht übernommen"

    db.query(TrainingSession).filter(TrainingSession.id == s.id).delete()
    db.commit()


def test_vorschau_schreibt_nichts(db):
    nutzer = db.query(User).first()
    s = TrainingSession(
        user_id=nutzer.id, session_date=date(2026, 10, 2), discipline="bike",
        duration_min=60, normalized_power=200, week_number=1, tss=1.0,
    )
    db.add(s); db.commit()

    bericht = neu_rechnen(db, nutzer, apply=False)
    assert bericht["angewandt"] is False
    assert any(a["session_id"] == s.id for a in bericht["geaendert"])

    db.refresh(s)
    assert s.tss == 1.0, "die Vorschau darf nichts verändern"

    db.query(TrainingSession).filter(TrainingSession.id == s.id).delete()
    db.commit()
