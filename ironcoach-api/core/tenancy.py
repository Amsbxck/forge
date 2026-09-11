"""Automatische Mandantentrennung auf ORM-Ebene.

Die Alternative wäre, an 58 Abfragestellen in 17 Dateien ein
`.filter(Model.user_id == ...)` zu ergänzen. Das ist nicht nur viel Arbeit,
sondern vor allem nicht haltbar: die 59. Abfrage vergisst es, und der Fehler
äußert sich nicht als Absturz, sondern als fremde Trainingsdaten im eigenen
Wochenplan.

Deshalb hängt der Filter an `do_orm_execute` und wird auf jede SELECT-Abfrage
der betroffenen Modelle angewendet — auch auf solche, die es noch gar nicht
gibt.

Zwei bewusste Entscheidungen:

* Datensätze ohne Zuordnung sind für niemanden sichtbar. Während der
  Migration war das anders — dort galten sie als gemeinsam, damit Altdaten
  nicht verschwinden. Inzwischen trägt jede Zeile eine Zuordnung.
* Ohne gesetzten Nutzer (Hintergrundjobs, Migrationen) filtert nichts. Ein
  Job, der über alle Athleten läuft, soll das auch dürfen.
"""

import logging
from contextlib import contextmanager
from contextvars import ContextVar

from sqlalchemy import event
from sqlalchemy.orm import Session, with_loader_criteria

logger = logging.getLogger(__name__)

_current_user_id: ContextVar[int | None] = ContextVar("current_user_id", default=None)

# Ausführungsoption, um den Filter bewusst zu umgehen — etwa für einen
# Hintergrundjob, der über alle Nutzer arbeitet.
SKIP_OPTION = "skip_tenant_filter"


def set_current_user_id(user_id: int | None) -> None:
    _current_user_id.set(user_id)


def get_current_user_id() -> int | None:
    return _current_user_id.get()


@contextmanager
def acting_as(user_id: int | None):
    """Vorübergehend im Namen eines Nutzers arbeiten."""
    token = _current_user_id.set(user_id)
    try:
        yield
    finally:
        _current_user_id.reset(token)


def _tenant_models():
    from models import (
        AthleteProfile, ChatMessage, HealthEvent, HrvMeasurement, PlannedSession,
        RaceGoal, RaceResult, StravaCredentials, TrainingSession,
        WeeklyPlan,
    )
    return (
        AthleteProfile, ChatMessage, HealthEvent, HrvMeasurement, PlannedSession,
        RaceGoal, RaceResult, StravaCredentials, TrainingSession,
        WeeklyPlan,
    )


def install() -> None:
    """Filter registrieren. Einmal beim Start aufrufen."""

    @event.listens_for(Session, "do_orm_execute")
    def _apply_tenant_filter(state):  # pragma: no cover - über Integrationstest geprüft
        if not state.is_select or state.is_column_load or state.is_relationship_load:
            return
        if state.execution_options.get(SKIP_OPTION):
            return

        user_id = _current_user_id.get()
        if user_id is None:
            return

        for model in _tenant_models():
            state.statement = state.statement.options(
                with_loader_criteria(
                    model,
                    # Bewusst ein fertiger Ausdruck statt eines Lambdas:
                    # SQLAlchemy cacht Lambda-Kriterien anhand des Codeobjekts
                    # und backt den Wert des ersten Aufrufs ein. Der zweite
                    # Nutzer bekäme dann die Daten des ersten zu sehen — ein
                    # Fehler, der sich nicht als Absturz zeigt.
                    #
                    # Ohne Ausnahme für user_id IS NULL: die war nötig, solange
                    # Altdaten unzugeordnet waren. Jetzt trägt jede Zeile eine
                    # Zuordnung, und eine künftige ohne wäre für alle sichtbar.
                    model.user_id == user_id,
                    include_aliases=True,
                )
            )

    logger.info("Mandantenfilter aktiv")
