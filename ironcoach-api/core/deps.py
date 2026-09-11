"""Auflösung des aktuellen Nutzers.

Eine einzige Stelle, an der entschieden wird, wessen Daten eine Anfrage
sieht. Bis die Anmeldung steht, ist das immer derselbe Nutzer — der Rest
der Anwendung fragt aber schon jetzt danach, sodass mit der Anmeldung nur
`resolve_user()` getauscht werden muss und kein Aufrufer.

Warum nicht weiter `AthleteProfile.first()`: dieser Aufruf stand an 17
Stellen und liefert bei mehreren Nutzern schlicht irgendeinen Datensatz —
in aller Regel den falschen, ohne dass irgendwo ein Fehler entstünde.
"""

import logging

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from core.config import settings
from database import get_db
from models import AthleteProfile, User

logger = logging.getLogger(__name__)


def resolve_user(db: Session) -> User | None:
    """Der Nutzer dieser Anfrage.

    Die Anfrage-Middleware wertet das Token aus und legt die Nutzer-ID im
    Kontext ab; hier wird sie nur noch nachgeschlagen. Ist keine gesetzt und
    die Anmeldung abgeschaltet, gilt wie früher der erste Nutzer — das hält
    die lokale Entwicklung ohne Login benutzbar.
    """
    from core.tenancy import get_current_user_id

    user_id = get_current_user_id()
    if user_id is not None:
        return db.query(User).filter(User.id == user_id).first()

    if settings.AUTH_REQUIRED:
        return None
    return db.query(User).order_by(User.id.asc()).first()


def get_current_user(db: Session = Depends(get_db)) -> User | None:
    return resolve_user(db)


def require_user(db: Session = Depends(get_db)) -> User:
    """Für Endpoints, die ohne Anmeldung nichts zu tun haben."""
    user = resolve_user(db)
    if user is None:
        raise HTTPException(status_code=401, detail="Nicht angemeldet")
    return user


def get_profile(db: Session, user: User | None = None) -> AthleteProfile | None:
    """Athletenprofil des Nutzers.

    Fällt auf das erste Profil zurück, solange die Zuordnung noch nicht
    migriert ist — sonst stünde die App nach dem Deploy ohne Profil da.
    """
    user = user or resolve_user(db)
    if user is not None:
        profile = (
            db.query(AthleteProfile).filter(AthleteProfile.user_id == user.id).first()
        )
        if profile is not None:
            return profile
        # Ein Nutzer ohne eigenes Profil bekommt keines von jemand anderem.
        return None
    if settings.AUTH_REQUIRED:
        return None
    # Ohne Anmeldung (lokale Entwicklung) wie bisher das einzige Profil.
    return db.query(AthleteProfile).first()


def get_current_profile(db: Session = Depends(get_db)) -> AthleteProfile | None:
    return get_profile(db)


def get_active_goal(db: Session, user: User | None = None):
    """Das Saisonziel — immer ein A-Rennen.

    B- und C-Rennen liegen in derselben Tabelle, dürfen die Planung aber
    nicht verankern: Planlänge, Phasen und Wochenzählung hängen hier dran.
    Ohne diesen Filter würde ein eingetragener Zwischenwettkampf die
    gesamte Vorbereitung übernehmen.
    """
    from models import RaceGoal

    user = user or resolve_user(db)
    query = db.query(RaceGoal).filter(
        RaceGoal.is_active == True,  # noqa: E712
        RaceGoal.priority == "A",
    )
    if user is not None:
        query = query.filter(RaceGoal.user_id == user.id)
    return query.order_by(RaceGoal.race_date.asc()).first()


def get_plan_anchor(db: Session, user: User | None = None):
    """Woran die Wochenzählung hängt.

    Das aktive Ziel bestimmt Planstart und Gesamtdauer. Solange keines
    gesetzt ist, übernimmt das Profil diese Rolle — beide tragen
    `plan_start_date`, weshalb die Wochenberechnung mit beidem arbeitet.
    """
    return get_active_goal(db, user) or get_profile(db, user)


def total_weeks_for(anchor) -> int:
    """Gesamtdauer der Vorbereitung; ohne Ziel die bisherige 33-Wochen-Annahme."""
    return getattr(anchor, "total_weeks", None) or 33


def scoped(query, model, user: User | None):
    """Query auf den Nutzer einschränken.

    Ohne Nutzer (Einzelplatzbetrieb vor der Migration) bleibt die Abfrage
    unverändert — mit Nutzer werden zusätzlich Altdatensätze ohne
    Zuordnung mitgenommen, damit nach dem Deploy nichts verschwindet.
    """
    if user is None:
        return query
    return query.filter(
        (model.user_id == user.id) | (model.user_id.is_(None))
    )
