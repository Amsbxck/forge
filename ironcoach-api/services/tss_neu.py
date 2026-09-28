"""TSS gegen die heutigen Schwellenwerte neu rechnen.

Die TSS wird beim Import einmal berechnet und danach nie wieder angefasst.
Ändert sich später die Schwelle, stehen alte und neue Einheiten auf
verschiedenen Bezugsgrössen — und genau daraus wird die Formkurve gebildet, die
über jede Planung entscheidet.

Was das anrichten kann, zeigt Amirs Fall: Seine FTP stand durch einen falsch
erkannten Test auf 175 statt 264. Eine fünfeinhalbstündige Grundlagenausfahrt
erhielt dadurch 598 TSS — das entspricht einem Intensitätsfaktor von 1,05, also
fünfeinhalb Stunden **über** der Schwelle. Unmöglich, und trotzdem in der CTL.

Zwei Änderungen gegenüber der Rechnung beim Import:

1. **NP aus Stravas `weighted_average_watts`** statt aus dem gespeicherten
   Leistungsstrom. Der ist heruntergerechnet — bei einer 327-Minuten-Fahrt
   liegen 1968 Werte vor, also einer je zehn Sekunden. Das 30-Werte-Fenster der
   NP-Formel umspannt damit fünf Minuten statt dreissig Sekunden und glättet
   genau die Spitzen weg, um die es bei NP geht. Strava rechnet auf der
   Vollauflösung.

2. **Bewegungszeit als Dauer**, nicht die Länge des Stroms. Die enthält die
   Pausen mit.
"""

import logging
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from models import AthleteProfile, TrainingSession, User

logger = logging.getLogger(__name__)

# Ein Intensitätsfaktor über diesem Wert ist über eine ganze Einheit nicht
# fahrbar. Er bedeutet nicht "sehr hart", sondern "die Bezugsgrösse stimmt
# nicht" — und wird gemeldet statt stillschweigend übernommen.
IF_UNMOEGLICH = 1.05


@dataclass
class Aenderung:
    session_id: int
    datum: str
    disziplin: str
    alt: float | None
    neu: float | None
    grundlage: str
    hinweis: str | None = None


@dataclass
class Bericht:
    geprueft: int = 0
    geaendert: list[Aenderung] = field(default_factory=list)
    unmoeglich: list[Aenderung] = field(default_factory=list)
    angewandt: bool = False

    def as_dict(self) -> dict:
        return {
            "geprueft": self.geprueft,
            "angewandt": self.angewandt,
            "anzahl_geaendert": len(self.geaendert),
            "geaendert": [vars(a) for a in self.geaendert],
            "unmoeglich": [vars(a) for a in self.unmoeglich],
        }


def _tss_neu(session: TrainingSession, profil: AthleteProfile) -> tuple[float | None, str]:
    """Die TSS dieser Einheit nach heutigem Stand — und woraus sie entstand."""
    dauer_h = (session.duration_min or 0) / 60
    if dauer_h <= 0:
        return None, "keine Dauer"

    disziplin = (session.discipline or "").lower()

    # Leistung schlägt Puls, aber nur beim Rad: Beim Laufen ist die Wattangabe
    # der Uhr eine Schätzung ohne gemeinsame Bezugsgrösse.
    if disziplin in ("bike", "brick"):
        # **Nur** mit echter NP. Der Durchschnitt ist kein Ersatz: Er enthält
        # jedes Rollen und jede Ampel mit und liegt bei einer langen Ausfahrt
        # weit darunter. In der Vorschau fiel Taminas Samstagsfahrt dadurch von
        # 346 auf 188 TSS — nicht weil die alte Zahl falsch war, sondern weil
        # ihr Durchschnitt von 116 W als NP gelesen wurde. Ohne NP ist der Puls
        # die ehrlichere Grundlage.
        np = session.normalized_power
        ftp = profil.ftp_watts if profil else None
        if np and ftp:
            faktor = np / ftp
            return round(dauer_h * faktor ** 2 * 100, 1), f"NP {np} / FTP {ftp}"

    schwelle = None
    if profil:
        schwelle = (
            profil.swim_threshold_hr if disziplin == "swim" else None
        ) or profil.threshold_hr or profil.z2_hr_max
    if session.avg_hr and schwelle:
        faktor = session.avg_hr / schwelle
        return round(dauer_h * faktor ** 2 * 100, 1), f"HF {session.avg_hr} / {schwelle}"

    return None, "keine Grundlage"


def neu_rechnen(db: Session, user: User | None = None, apply: bool = False) -> dict:
    """Alle Einheiten durchrechnen. Ohne `apply` nur ein Bericht.

    Bewusst zweistufig, wie beim Ableiten der Zonen: Das Ergebnis verschiebt die
    Formkurve rückwirkend, und wer das auslöst, soll vorher sehen, um wie viel.
    """
    from core.deps import get_profile, resolve_user

    user = user or resolve_user(db)
    profil = get_profile(db, user)
    bericht = Bericht(angewandt=apply)

    query = db.query(TrainingSession).filter(TrainingSession.deleted_at == None)  # noqa: E711
    if user is not None:
        query = query.filter(TrainingSession.user_id == user.id)

    for s in query.order_by(TrainingSession.session_date.asc()).all():
        bericht.geprueft += 1
        neu, grundlage = _tss_neu(s, profil)
        if neu is None:
            continue

        alt = round(s.tss, 1) if s.tss is not None else None
        if alt is not None and abs(alt - neu) < 0.5:
            continue

        eintrag = Aenderung(
            session_id=s.id, datum=str(s.session_date),
            disziplin=s.discipline or "?", alt=alt, neu=neu, grundlage=grundlage,
        )

        # Bleibt der Wert auch neu unmöglich, stimmt die Schwelle noch nicht.
        # Dann wird gemeldet statt geschrieben — sonst ersetzt eine falsche Zahl
        # die andere und niemand sieht es.
        dauer_h = (s.duration_min or 0) / 60
        if dauer_h > 0 and (neu / (dauer_h * 100)) ** 0.5 > IF_UNMOEGLICH:
            eintrag.hinweis = (
                f"Auch neu ergibt das einen Intensitätsfaktor über "
                f"{IF_UNMOEGLICH} — die Bezugsgrösse stimmt noch nicht. "
                f"Nicht übernommen."
            )
            bericht.unmoeglich.append(eintrag)
            continue

        bericht.geaendert.append(eintrag)
        if apply:
            s.tss = neu

    if apply:
        db.commit()
        logger.info("TSS neu gerechnet: %s von %s Einheiten geändert",
                    len(bericht.geaendert), bericht.geprueft)
    return bericht.as_dict()
