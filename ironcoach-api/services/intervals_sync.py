"""Die geplanten Läufe und Radeinheiten einer Woche mit dem intervals.icu-Kalender abgleichen.

Von dort gehen sie zu den Geräten, die der Athlet bei intervals.icu verbunden
hat: Garmin Connect und damit die Uhr, Wahoo für den Radcomputer (siehe
`services/intervals_icu.py`, warum der Umweg). Welches Gerät was bekommt,
entscheidet jeder dort selbst, FORGE schickt alles.

**Ohne gespeicherten Zustand.** `project_plan` ersetzt bei jeder Neuplanung
die Zeilen der Woche (`plan_projection.py`), eine Event-ID an der Zeile ginge
dabei verloren. Stattdessen trägt jedes Event eine `external_id`
(`forge-<nutzer>-<datum>-<lfd>`), und jeder Abgleich liest die Woche bei
intervals.icu neu:

1. Soll: die geplanten Läufe und Radeinheiten der Woche ab heute (ein Brick
   wird zu zwei Workouts, Rad und Lauf).
2. Ist: die FORGE-Events der Woche ab heute bei intervals.icu.
3. Fehlt eines, wird es angelegt. Weicht eines ab, wird es ersetzt. Steht bei
   intervals.icu eines, das nicht mehr geplant ist (verschoben, gestrichen,
   ersetzt), wird es gelöscht.

Fremde Events des Athleten bleiben unberührt: Gelöscht wird nur, was eine
FORGE-Kennung trägt. Vergangene Tage auch, dort liegt längst die Aufzeichnung.

**Wirft nie.** Ein Ausfall bei intervals.icu darf keine Planung kippen.
Fehler landen als fester Text im Profil (`intervals_letzter_fehler`), die
Kachel auf Anbindungen zeigt ihn.

**Wann:** von selbst nach jeder Änderung an den geplanten Einheiten, also
nach dem Erstellen, Anpassen, Verschieben, Ersetzen und Stornieren
(`anstossen`). Wer einen neuen Weg baut, der `planned_sessions` ändert, muss
den Abgleich dort ebenfalls anstoßen. Ein Test hält die Aufrufstellen von
`project_plan` damit zusammen.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from datetime import date, datetime, timedelta
from typing import Iterable

from sqlalchemy.orm import Session, sessionmaker

from core.tenancy import acting_as
from core.wochen import montag_von
from models import AthleteProfile, PlannedSession
from services import intervals_icu
from services.intervals_icu import (
    IntervalsFehler, IntervalsNichtErreichbar, IntervalsZugangUngueltig, zugang_aus_profil,
)
from services.geplantes_workout import workouts

logger = logging.getLogger(__name__)

PRAEFIX = "forge-"
NAME_PRAEFIX = "FORGE · "

FEHLER_ZUGANG = "intervals.icu hat den Zugang abgelehnt. Schlüssel oder Verbindung erneuern."
FEHLER_NETZ = "intervals.icu war nicht erreichbar. Der nächste Abgleich versucht es erneut."
FEHLER_SONST = "Abgleich mit intervals.icu fehlgeschlagen."


def _kennung(user_id: int, tag: date, lfd: int) -> str:
    return f"{PRAEFIX}{user_id}-{tag.isoformat()}-{lfd}"


def _profil(db: Session, user_id: int) -> AthleteProfile | None:
    # Ausdrücklich nach Nutzer, wie `get_profile`, aber ohne dessen Rückfall
    # auf das erste Profil: Hier wird mit dem Zugang eines Athleten in einen
    # fremden Kalender geschrieben. Ein falsches Profil hieße, die Läufe des
    # einen in den Kalender des anderen zu legen.
    with acting_as(user_id):
        return db.query(AthleteProfile).filter(AthleteProfile.user_id == user_id).first()


def soll_events(db: Session, user_id: int, von: date, bis: date) -> dict[str, dict]:
    """Die geplanten Workouts zwischen `von` und `bis` als Events, nach Kennung."""
    with acting_as(user_id):
        einheiten = (
            db.query(PlannedSession)
            .filter(
                # Zusätzlich zum Mandantenfilter (`core/tenancy.py`), nicht
                # statt seiner: Der Hook hängt erst nach dem App-Start, und ein
                # Lauf im Kalender eines anderen Athleten wäre ein Datenleck
                # nach außen, das sich nicht zurückholen lässt.
                PlannedSession.user_id == user_id,
                PlannedSession.planned_date >= von,
                PlannedSession.planned_date <= bis,
                # Erledigte zählen mit, damit ein heute schon gelaufenes
                # Workout bei intervals.icu stehen bleibt (dort hängt die
                # Aufzeichnung daran). Angefasst werden sie nicht.
                # "moved" ist ein verschobener, weiter offener Lauf: Mit nur
                # "planned" verschwände jeder Lauf von der Uhr, sobald man ihn
                # im Kalender auf einen anderen Tag zieht.
                PlannedSession.status.in_(("planned", "moved", "completed")),
                PlannedSession.discipline.in_(("run", "bike", "brick")),
            )
            .order_by(PlannedSession.planned_date, PlannedSession.day_index, PlannedSession.id)
            .all()
        )

    profil = _profil(db, user_id)
    ftp = profil.ftp_watts if profil else None

    soll: dict[str, dict] = {}
    je_tag: dict[date, int] = {}
    for einheit in einheiten:
        # Wettkampf oder nichts Lesbares: keine Workouts. Ein Brick liefert
        # zwei (Rad, dann Lauf), jedes mit eigener laufender Nummer des Tages.
        for workout in workouts(einheit, ftp=ftp):
            lfd = je_tag[einheit.planned_date] = je_tag.get(einheit.planned_date, 0) + 1
            kennung = _kennung(user_id, einheit.planned_date, lfd)
            soll[kennung] = {
                "category": "WORKOUT",
                "type": workout.sport,
                "start_date_local": f"{einheit.planned_date.isoformat()}T00:00:00",
                "name": workout.name,
                "description": workout.text,
                "external_id": kennung,
                "_erledigt": einheit.status == "completed",
            }
    return soll


def _ist_zuordnen(events: list[dict], user_id: int) -> tuple[dict[str, dict], list[dict]]:
    """Die FORGE-Events nach Kennung, dazu die Dubletten.

    Liefert intervals.icu die `external_id` nicht mit (beim persönlichen
    Schlüssel nicht gesichert), werden FORGE-Events am Namen erkannt und je
    Tag in ihrer Reihenfolge durchnummeriert, wie beim Anlegen.

    Trägt mehr als ein Event dieselbe Kennung, gilt das älteste, die übrigen
    sind Dubletten und werden gelöscht. Vorher überschrieb das zweite still
    das erste: Das erste sah danach kein Abgleich und kein Trennen mehr, und
    es blieb für immer auf der Uhr. Entstehen kann so etwas aus einem
    Abgleich, der vor der Sperre lief, oder aus einem zweiten Prozess.
    """
    eigene = f"{PRAEFIX}{user_id}-"
    ist: dict[str, dict] = {}
    dubletten: list[dict] = []
    ohne_kennung: list[dict] = []
    for event in sorted(events, key=lambda e: e.get("id") or 0):
        kennung = str(event.get("external_id") or "")
        if kennung.startswith(eigene):
            if kennung in ist:
                dubletten.append(event)
            else:
                ist[kennung] = event
        elif not kennung and str(event.get("name") or "").startswith(NAME_PRAEFIX):
            ohne_kennung.append(event)
    je_tag: dict[str, int] = {}
    for event in sorted(ohne_kennung, key=lambda e: (str(e.get("start_date_local")), e.get("id") or 0)):
        tag = str(event.get("start_date_local") or "")[:10]
        lfd = je_tag[tag] = je_tag.get(tag, 0) + 1
        try:
            kennung = _kennung(user_id, date.fromisoformat(tag), lfd)
        except ValueError:
            continue
        ist.setdefault(kennung, event)
    return ist, dubletten


def _gleich(ist: dict, soll: dict) -> bool:
    # Auch die Sportart: Kommt an einem Tag eine Radeinheit vor den Lauf,
    # rückt der Lauf auf die zweite Nummer, und unter der ersten steht dann
    # ein Rad-Workout. Ein „Run" mit Wattzielen nähme kein Gerät an.
    return (
        (ist.get("type") or soll["type"]) == soll["type"]
        and str(ist.get("start_date_local") or "")[:10] == soll["start_date_local"][:10]
        and (ist.get("name") or "") == soll["name"]
        and (ist.get("description") or "").strip() == soll["description"].strip()
    )


async def woche_abgleichen(db: Session, user_id: int, montag: date, transport=None, heute: date | None = None) -> dict:
    """Eine Woche abgleichen. Wirft nie, liefert die Zählung oder den Fehler.

    Ohne Sperre. Von außen über `abgleichen` aufrufen, sonst können zwei
    Abgleiche zugleich dasselbe Workout anlegen.
    """
    ergebnis = {"angelegt": 0, "ersetzt": 0, "geloescht": 0, "unveraendert": 0}
    profil = _profil(db, user_id)
    zugang = zugang_aus_profil(profil)
    if zugang is None:
        return {**ergebnis, "uebersprungen": "nicht verbunden"}

    heute = heute or date.today()
    von = max(montag, heute)
    bis = montag + timedelta(days=6)
    if von > bis:
        return {**ergebnis, "uebersprungen": "Woche vorbei"}

    try:
        soll = soll_events(db, user_id, von, bis)
        ist, dubletten = _ist_zuordnen(await intervals_icu.events_lesen(zugang, von, bis, transport), user_id)
        for doppelt in dubletten:
            await intervals_icu.event_loeschen(zugang, doppelt["id"], transport)
            ergebnis["geloescht"] += 1

        for kennung, event in soll.items():
            vorhanden = ist.get(kennung)
            if event.pop("_erledigt"):
                ergebnis["unveraendert"] += 1
                continue
            if vorhanden is None:
                await intervals_icu.event_anlegen(zugang, event, transport)
                ergebnis["angelegt"] += 1
            elif _gleich(vorhanden, event):
                ergebnis["unveraendert"] += 1
            else:
                await intervals_icu.event_ersetzen(zugang, vorhanden["id"], event, transport)
                ergebnis["ersetzt"] += 1
        for kennung, vorhanden in ist.items():
            if kennung not in soll and vorhanden.get("id") is not None:
                await intervals_icu.event_loeschen(zugang, vorhanden["id"], transport)
                ergebnis["geloescht"] += 1
        fehler = None
    except IntervalsZugangUngueltig:
        fehler = FEHLER_ZUGANG
    except IntervalsNichtErreichbar:
        fehler = FEHLER_NETZ
    except IntervalsFehler:
        fehler = FEHLER_SONST
    except Exception:
        # Auch ein Fehler im eigenen Code soll keine Planung kippen. Ohne die
        # Ausnahme im Text: Sie könnte den Kopf samt Schlüssel tragen.
        logger.error("intervals.icu-Abgleich für Nutzer %s fehlgeschlagen", user_id)
        fehler = FEHLER_SONST

    if fehler:
        profil.intervals_letzter_fehler = fehler
    else:
        profil.intervals_letzter_fehler = None
        profil.intervals_letzter_abgleich = datetime.utcnow()
    db.commit()
    return {**ergebnis, "fehler": fehler} if fehler else ergebnis


# --- Sperre je Athlet ------------------------------------------------------
#
# Zwei Abgleiche zugleich (Verbinden und gleich danach „Sync now", zwei
# schnelle Verschiebungen) lasen beide eine leere Woche und legten beide an:
# dasselbe Workout zweimal auf der Uhr. Deshalb läuft der ganze Zyklus aus
# Lesen und Schreiben je Athlet unter einer Sperre, für den Faden wie für die
# Knöpfe. Die Sperre gilt im Prozess. Liefe das Backend einmal mit mehreren
# Prozessen, räumt `_ist_zuordnen` die Dubletten beim nächsten Abgleich ab.
_SPERREN: dict[int, threading.Lock] = {}
_SPERREN_SCHUTZ = threading.Lock()


def _sperre(user_id: int) -> threading.Lock:
    with _SPERREN_SCHUTZ:
        return _SPERREN.setdefault(user_id, threading.Lock())


def abgleichen(db: Session, user_id: int, montage: Iterable[date], transport=None,
               heute: date | None = None) -> list[dict]:
    """Die Wochen nacheinander abgleichen, unter der Sperre des Athleten.

    Synchron mit eigenem Event-Loop: aufrufbar aus dem Faden und aus
    synchronen Routen (die FastAPI im Threadpool ausführt). Nicht aus einer
    `async`-Route: Dort liefe schon ein Loop, und die Sperre hielte ihn an.
    """
    with _sperre(user_id):
        return [
            asyncio.run(woche_abgleichen(db, user_id, montag, transport=transport, heute=heute))
            for montag in montage
        ]


def alles_entfernen(db: Session, user_id: int, tage: int = 60, transport=None) -> bool:
    """Beim Trennen: die FORGE-Workouts ab heute löschen. True, wenn es klappte."""
    zugang = zugang_aus_profil(_profil(db, user_id))
    if zugang is None:
        return True
    heute = date.today()

    async def _loeschen():
        events = await intervals_icu.events_lesen(zugang, heute, heute + timedelta(days=tage), transport)
        ist, dubletten = _ist_zuordnen(events, user_id)
        for event in list(ist.values()) + dubletten:
            if event.get("id") is not None:
                await intervals_icu.event_loeschen(zugang, event["id"], transport)

    with _sperre(user_id):
        try:
            asyncio.run(_loeschen())
            return True
        except IntervalsFehler:
            return False


def _abgleich_im_faden(bind, user_id: int, montage: list[date]) -> None:
    db = sessionmaker(bind=bind, autoflush=False)()
    try:
        abgleichen(db, user_id, montage)
    except Exception:
        logger.error("intervals.icu-Abgleich im Hintergrund für Nutzer %s abgebrochen", user_id)
    finally:
        db.close()


def anstossen(db: Session, user_id: int | None, tage: Iterable[date | None]) -> threading.Thread | None:
    """Den Abgleich der Wochen dieser Tage im Hintergrund starten.

    Erst hier im Aufrufer prüfen, ob der Athlet überhaupt verbunden ist: Für
    alle anderen startet nichts. Der Faden bekommt eine eigene Sitzung auf
    **derselben** Datenbank wie der Aufrufer, nicht `database.SessionLocal`.
    Sonst griffe ein Test über den Faden auf die Entwicklungsdatenbank zu und
    schickte womöglich an ein echtes Konto.

    Ein eigener Faden statt `BackgroundTasks`: Die Aufrufstellen sind teils
    Dienste ohne Zugriff auf die Anfrage (Planerstellung, Anpassung), teils
    synchrone Routen. Der Faden wartet auf nichts und hält keine Antwort auf.
    """
    if not user_id:
        return None
    try:
        if zugang_aus_profil(_profil(db, user_id)) is None:
            return None
    except Exception:
        return None
    montage = sorted({montag_von(t) for t in tage if t})
    if not montage:
        return None
    faden = threading.Thread(
        target=_abgleich_im_faden, args=(db.get_bind(), user_id, montage),
        name=f"intervals-{user_id}", daemon=True,
    )
    faden.start()
    return faden
