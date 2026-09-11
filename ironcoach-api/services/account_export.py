"""Daten mitnehmen und Konto löschen.

Beides gehört zusammen: Wer löschen darf, muss vorher mitnehmen können, was
ihm gehört. Und beides muss vollständig sein — ein Export, der die Hälfte
vergisst, ist wertlos, und eine Löschung, die Reste liegen lässt, ist keine.

Die Vollständigkeit hängt an einer Liste von Modellen. Kommt später eine
Tabelle dazu, muss sie hier eingetragen werden; deshalb wird beim Löschen
zusätzlich geprüft, ob irgendwo noch Zeilen mit dieser Nutzer-ID stehen.
"""

import logging
import os
from datetime import date, datetime

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from core.config import settings
from models import (
    AthleteProfile, AuthAction, ChatMessage, HealthEvent, HrvMeasurement,
    PlannedSession, RaceGoal, RaceResult, StravaCredentials,
    TrainingSession, User, WeeklyPlan,
)

logger = logging.getLogger(__name__)

# Alles, was an einem Nutzer hängt. Reihenfolge egal — die Fremdschlüssel
# löschen ohnehin per CASCADE mit; hier geht es um Vollständigkeit.
NUTZERDATEN = [
    ("profil", AthleteProfile),
    ("einheiten", TrainingSession),
    ("wochenplaene", WeeklyPlan),
    ("geplante_einheiten", PlannedSession),
    ("hrv", HrvMeasurement),
    ("ziele", RaceGoal),
    ("rennen", RaceResult),
    ("gesundheit", HealthEvent),
    ("chat", ChatMessage),
    ("strava", StravaCredentials),
    ("anmeldelinks", AuthAction),
]

# Was aus dem Export herausbleibt: Zugangsdaten und Fingerabdrücke. Sie
# gehören dem Nutzer nicht in dem Sinne, dass sie ihm nützen — sie wären nur
# ein Risiko in einer Datei, die per Mail weitergereicht wird.
GEHEIM = {
    "password_hash", "access_token", "refresh_token", "obsidian_api_key",
    "token_hash", "reflection_sync_hash", "claude_prompt",
}


def _zeile(objekt) -> dict:
    """Ein ORM-Objekt in einfache Typen übersetzen."""
    daten = {}
    for spalte in inspect(objekt).mapper.column_attrs:
        name = spalte.key
        if name in GEHEIM:
            continue
        wert = getattr(objekt, name)
        if isinstance(wert, (datetime, date)):
            wert = wert.isoformat()
        daten[name] = wert
    return daten


def build_export(db: Session, user: User) -> dict:
    """Alle Daten des Nutzers als JSON-taugliche Struktur."""
    export = {
        "exportiert_am": datetime.utcnow().isoformat(),
        "konto": {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "angelegt_am": user.created_at.isoformat() if user.created_at else None,
            "email_bestaetigt": user.email_verified_at is not None,
        },
        "hinweis": (
            "Zugangsdaten sind bewusst nicht enthalten. Streams und Rohdaten "
            "der Einheiten sind enthalten, Bilddateien liegen separat."
        ),
    }

    for name, modell in NUTZERDATEN:
        if modell is AuthAction:
            continue  # Einmal-Links sind kein Trainingsinhalt
        zeilen = db.query(modell).filter(modell.user_id == user.id).all()
        export[name] = [_zeile(z) for z in zeilen]

    export["umfang"] = {name: len(export[name]) for name, _ in NUTZERDATEN if name in export}
    return export


def _rennfotos_loeschen(db: Session, user: User) -> int:
    """Hochgeladene Rennfotos vom Datenträger entfernen.

    Die Datenbankzeilen verschwinden per CASCADE, die Dateien nicht — sie
    blieben sonst als verwaiste Bilder auf der Platte liegen.
    """
    verzeichnis = os.path.join(settings.UPLOAD_DIR, "races")
    entfernt = 0
    for rennen in db.query(RaceResult).filter(RaceResult.user_id == user.id).all():
        if not rennen.image_file:
            continue
        try:
            os.remove(os.path.join(verzeichnis, rennen.image_file))
            entfernt += 1
        except OSError:
            pass  # schon weg oder nie geschrieben — kein Grund abzubrechen
    return entfernt


def delete_user_data(db: Session, user: User) -> dict:
    """Konto samt allem löschen. Gibt zurück, was entfernt wurde."""
    zusammenfassung = {
        name: db.query(modell).filter(modell.user_id == user.id).count()
        for name, modell in NUTZERDATEN
    }
    zusammenfassung["rennfotos"] = _rennfotos_loeschen(db, user)

    user_id = user.id
    db.delete(user)   # Fremdschlüssel räumen den Rest per CASCADE ab
    db.commit()

    # Nachkontrolle: Bleibt irgendwo eine Zeile stehen, ist die Liste oben
    # unvollständig — das soll auffallen und nicht still danebengehen.
    reste = {
        name: db.query(modell).filter(modell.user_id == user_id).count()
        for name, modell in NUTZERDATEN
    }
    uebrig = {name: anzahl for name, anzahl in reste.items() if anzahl}
    if uebrig:
        logger.error("Nach dem Löschen von Nutzer %s sind Daten übrig: %s", user_id, uebrig)
        zusammenfassung["nicht_geloescht"] = uebrig

    return zusammenfassung
