"""Einen Wochenplan stornieren — in der Datenbank und in Obsidian.

Bisher konnte nur der Admin einen falschen Plan entfernen, und nur von Hand
in der Datenbank. Jetzt kann der Athlet ihn selbst in der Plan-Kachel
stornieren.

Storniert wird die **ganze Woche**: alle Fassungen des Plans (eine Anpassung
legt eine neue Zeile an, siehe `services/plan_adjust.py`), ihre geplanten
Einheiten und die Notiz in Obsidian. Danach ist die Woche leer und lässt sich
neu erstellen. Nur die jüngste Fassung zu entfernen hieße, die vorige wieder
erscheinen zu lassen — das ist „Änderung zurücknehmen", nicht „Plan
stornieren".

Zwei Grenzen:

  * **Vergangene Wochen bleiben.** Ein Plan ist auch ein Protokoll dessen, was
    vorgesehen war; ohne ihn wird jeder Soll/Ist-Vergleich wertlos. Dieselbe
    Begründung wie in `services/plan_merge.py`.
  * **Die laufende Woche nur, solange darin nichts erledigt ist.** Eine
    erledigte Einheit hängt an einer echten Trainingseinheit. Die überlebte
    zwar (der Fremdschlüssel setzt nur ihren Verweis zurück), aber die Woche
    verlöre ihre Vorgabe, gegen die sie gemessen wurde. Wer dort etwas ändern
    will, nimmt „Tage anpassen".

Die Datenbank wird zuerst bereinigt und gespeichert, Obsidian danach. Ein
nicht erreichbarer Tresor darf das Stornieren nicht verhindern — die Antwort
sagt dann, welche Notiz von Hand zu löschen ist.
"""

from __future__ import annotations

import logging
from datetime import date

from sqlalchemy.orm import Session

from core.wochen import kalenderwoche
from models import PlannedSession, WeeklyPlan

logger = logging.getLogger(__name__)

# Bei einem Menschen, der auf die Antwort wartet: kurze Grenzen statt der
# 20 s Verbindungsaufbau des normalen Abgleichs.
OBSIDIAN_GRENZE_S = 8.0


class PlanNichtStornierbar(RuntimeError):
    """Die Woche existiert, darf aber nicht storniert werden."""


def _erledigt(db: Session, plan_ids: list[int]) -> int:
    """Wie viele Einheiten dieser Pläne schon erledigt oder ersetzt sind.

    Verschoben (`moved`) zählt nicht: Ziehen im Kalender setzt das auch auf
    künftigen Tagen, und dort ist nichts passiert.
    """
    return (
        db.query(PlannedSession)
        .filter(
            PlannedSession.plan_id.in_(plan_ids),
            (PlannedSession.matched_session_id.isnot(None))
            | (PlannedSession.status.in_(("completed", "replaced"))),
        )
        .count()
    )


def _obsidian_pfade(db: Session, user, plaene: list[WeeklyPlan]):
    """Client und Notizpfade — **vor** dem Löschen bestimmt, weil der Pfad
    an der Wochennummer und am Saisonordner des Plans hängt."""
    from core.deps import get_profile
    from core.saison import saison_name, saison_ziele
    from services.obsidian.client import client_for_profile, vault_subdir_for
    from services.obsidian.plan_note import plan_note_path

    profil = get_profile(db, user)
    client = client_for_profile(profil)
    if not client.enabled:
        return client, []

    subdir = vault_subdir_for(profil)
    # Mit dem Nutzer, nicht über den Mandantenkontext: Der ist hier nicht
    # zuverlässig gesetzt, und ein fremder Saisonordner ergäbe einen
    # falschen Pfad — die Notiz bliebe liegen.
    ziele = saison_ziele(db, user)
    pfade: list[str] = []
    for p in plaene:
        # Saisonordner und der flache Altort — eine Fassung kann noch dort
        # liegen, wenn sie vor der Umstellung auf Saisonordner entstand.
        for pfad in (plan_note_path(p, subdir, saison_name(p.week_start, ziele)),
                     plan_note_path(p, subdir)):
            if pfad not in pfade:
                pfade.append(pfad)
    return client, pfade


def plan_stornieren(db: Session, user, montag: date,
                    heute: date | None = None) -> dict:
    """Den Plan der Woche, in der `montag` liegt, vollständig entfernen.

    Wirft `LookupError`, wenn es keinen gibt, und `PlanNichtStornierbar`,
    wenn eine der beiden Grenzen greift.
    """
    from core.deps import resolve_user

    from sqlalchemy import text

    from services.benchmark import BENCHMARK_SPERRE_NS

    heute = heute or date.today()
    user = user or resolve_user(db)
    start, ende = kalenderwoche(montag)

    # Dieselbe Sperre wie beim Anlegen einer Testwoche. Ohne sie konnte ein
    # Storno genau zwischen dem Speichern einer neuen Testwoche und ihrer
    # Projektion landen — das Anlegen scheiterte dann an einem Plan, den es
    # nicht mehr gab. So läuft beides nacheinander.
    db.execute(text("SELECT pg_advisory_xact_lock(:ns, :uid)"),
               {"ns": BENCHMARK_SPERRE_NS, "uid": user.id or 0})

    # Ausdrücklich nach Nutzer gefiltert, nicht nur über den Mandantenfilter:
    # Der greift nur auf SELECTs und nur mit gesetztem Kontext. Hier wird
    # gelöscht — ein fremder Plan darf dabei unter keinen Umständen
    # mitkommen.
    plaene = (
        db.query(WeeklyPlan)
        .filter(WeeklyPlan.week_start == start, WeeklyPlan.user_id == user.id)
        .all()
    )
    if not plaene:
        raise LookupError(f"Kein Plan für die Woche ab {start}")

    if ende < heute:
        raise PlanNichtStornierbar(
            "Vergangene Wochen bleiben als Protokoll stehen — ohne sie lässt "
            "sich später nicht mehr vergleichen, was vorgesehen war."
        )

    ids = [p.id for p in plaene]
    if start <= heute:
        erledigt = _erledigt(db, ids)
        if erledigt:
            raise PlanNichtStornierbar(
                f"In dieser Woche {'ist' if erledigt == 1 else 'sind'} schon "
                f"{erledigt} {'Einheit' if erledigt == 1 else 'Einheiten'} "
                f"erledigt. Einzelne Tage lassen sich über „Tage anpassen“ "
                f"ändern."
            )

    benchmark = any(p.plan_phase == "Benchmark" for p in plaene)
    client, pfade = _obsidian_pfade(db, user, plaene)

    einheiten = (
        db.query(PlannedSession)
        .filter(PlannedSession.plan_id.in_(ids))
        .delete(synchronize_session=False)
    )
    for p in plaene:
        db.delete(p)
    db.commit()
    logger.info("Plan storniert: Nutzer %s, Woche %s, %s Fassung(en), %s Einheiten",
                user.id, start, len(ids), einheiten)

    try:
        obsidian = _obsidian_entfernen(client, pfade, heute)
    except Exception as e:  # noqa: BLE001 - die Datenbank ist schon bereinigt
        logger.exception("Obsidian beim Stornieren fehlgeschlagen")
        obsidian = {"status": "fehler", "pfade": pfade, "error": str(e)}

    teile = [f"Plan für die Woche ab {start.strftime('%d.%m.')} storniert."]
    if benchmark:
        teile.append("Die Testwoche ist freigegeben.")
    teile.append(_obsidian_satz(obsidian))
    return {
        "status": "storniert",
        "week_start": str(start),
        "plaene_entfernt": len(ids),
        "einheiten_entfernt": einheiten,
        "benchmark_freigegeben": benchmark,
        "obsidian": obsidian,
        "message": " ".join(t for t in teile if t),
    }


def _obsidian_entfernen(client, pfade: list[str], heute: date) -> dict:
    from services.obsidian.plan_note import plannotizen_entfernen

    if not client.enabled:
        return {"status": "deaktiviert", "pfade": []}
    # Kurze Grenzen: Ein über Tailscale nicht erreichbarer Tresor hielt die
    # Anfrage sonst über eine Minute auf, länger als das Frontend wartet.
    client.timeout = OBSIDIAN_GRENZE_S
    client.CONNECT_TIMEOUT_S = OBSIDIAN_GRENZE_S
    return plannotizen_entfernen(
        client, pfade, hinweis=f"*Plan am {heute.strftime('%d.%m.%Y')} storniert.*",
    )


def _obsidian_satz(obsidian: dict) -> str:
    status = obsidian.get("status")
    if status == "geloescht":
        return "Die Notiz in Obsidian ist entfernt."
    if status == "behalten_eigene_notizen":
        return ("In Obsidian ist der Plan aus der Notiz entfernt; deine eigenen "
                "Notizen darin bleiben.")
    if status == "nicht_erreichbar":
        pfad = (obsidian.get("pfade") or ["die Wochennotiz"])[0]
        return (f"Obsidian war nicht erreichbar — bitte die Notiz {pfad} dort "
                f"von Hand löschen.")
    if status == "fehler":
        return "Die Notiz in Obsidian ließ sich nicht entfernen."
    return ""
