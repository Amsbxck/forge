"""Zu welcher Saison ein Tag gehört.

Im Vault lagen bisher alle Wochenpläne flach in einem Ordner und alle
Einheiten flach unter ihrer Sportart. Nach der zweiten Saison steht dort
`Woche-12.md` zweimal — einmal vom 70.3, einmal vom Marathon — und
`run/base/` enthält vier Jahre Läufe ohne erkennbare Zuordnung.

Ein Tag gehört zu genau einer Saison:

  * Er liegt im Vorbereitungsfenster eines A-Rennens  → dessen Saison
  * sonst                                             → "Offseason <Jahr>"

Das Fenster reicht vom Planbeginn bis zum Wettkampftag. Nur A-Rennen zählen
— B- und C-Rennen liegen innerhalb einer laufenden Vorbereitung und dürfen
keinen eigenen Ordner aufspannen, sonst zerfällt eine Saison in Schnipsel.

Absichtlich ohne Datenbankzugriff in der Namensbildung: die Pfadfunktionen
werden für jede Einheit aufgerufen, und die Ziele eines Athleten sind eine
Handvoll Zeilen, die der Aufrufer einmal lädt.
"""

import re
from datetime import date, timedelta

from sqlalchemy.orm import Session

OFFSEASON = "Offseason"

# Zeichen, die in Obsidian-Pfaden nichts Gutes tun: die üblichen
# Dateisystem-Verbote plus `#`, `[`, `]` und `^`, die dort Links, Tags und
# Blockverweise einleiten. Ein Rennen namens "Ironman 70.3 #1" hätte sonst
# eine Note erzeugt, deren Pfad Obsidian als Überschriftenanker liest.
_VERBOTEN = re.compile(r'[\\/:*?"<>|#\[\]^]+')


def ordnername(text: str) -> str:
    """Freitext zu einem Ordnernamen, der im Vault keinen Schaden anrichtet."""
    saubere = _VERBOTEN.sub(" ", text or "")
    saubere = re.sub(r"\s+", " ", saubere).strip(" .")
    return saubere or "Unbenannt"


def fenster(ziel) -> tuple[date, date]:
    """Von wann bis wann die Vorbereitung auf dieses Ziel läuft.

    `plan_start_date` ist optional — wer ein Rennen einträgt, ohne den
    Beginn zu setzen, bekommt ihn aus der empfohlenen Dauer zurückgerechnet.
    Ohne diesen Rückfall hätte jedes Ziel ohne gesetzten Start ein leeres
    Fenster, und alle seine Einheiten lägen in der Offseason.
    """
    ende = ziel.race_date
    beginn = ziel.plan_start_date
    if beginn is None:
        wochen = getattr(ziel, "total_weeks", None) or 33
        beginn = ende - timedelta(weeks=wochen)
    return beginn, ende


def saison_ziele(db: Session, user=None) -> list:
    """Alle A-Rennen des Athleten, auch vergangene und abgehakte.

    Nicht auf `is_active` gefiltert: Einheiten aus früheren Saisons müssen
    weiterhin ihren Ordner finden, sonst wanderte der Bestand bei jedem
    Saisonwechsel geschlossen in die Offseason.
    """
    from core.deps import resolve_user
    from models import RaceGoal

    user = user or resolve_user(db)
    query = db.query(RaceGoal).filter(RaceGoal.priority == "A")
    if user is not None:
        query = query.filter(RaceGoal.user_id == user.id)
    return query.order_by(RaceGoal.race_date.asc()).all()


def saison_name(tag: date, ziele: list) -> str:
    """Der Ordnername für diesen Tag.

    Bei Überschneidung — zwei A-Rennen dicht hintereinander, deren Fenster
    sich berühren — gewinnt das frühere: `ziele` kommt nach Datum sortiert,
    und ein Tag gehört zu der Vorbereitung, die zuerst begonnen hat.
    """
    if tag is None:
        return f"{OFFSEASON} {date.today().year}"
    for ziel in ziele:
        beginn, ende = fenster(ziel)
        if beginn <= tag <= ende:
            name = ziel.race_name or getattr(ziel, "label", None) or "Wettkampf"
            # Das Jahr des Wettkampfs, nicht das des Tages: eine
            # Vorbereitung, die im Dezember beginnt, gehört zur Saison des
            # Rennens im Juni — sonst lägen ihre Wochen in zwei Ordnern.
            return f"{ordnername(name)} {ende.year}"
    return f"{OFFSEASON} {tag.year}"


def saison_fuer_tag(db: Session, tag: date, user=None) -> str:
    """Bequemlichkeit für Aufrufer mit einem einzelnen Tag."""
    return saison_name(tag, saison_ziele(db, user))
