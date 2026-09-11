"""Trainingskontext für den Coach aus den Obsidian-Notes.

Die Notes tragen bereits alles, was der Coach braucht: Messwerte, erkannte
Struktur, Plan/Ist-Vergleich, Abweichungen — und als einziges Medium auch
die Reflexionen des Athleten. Sie hier zu lesen ist billiger und
vollständiger, als dieselben Felder aus der Datenbank ein zweites Mal zu
formatieren.

Zwei Regeln:

1. **Obsidian darf nie zur Voraussetzung werden.** Ist der Vault zu oder der
   Rechner aus, liefert jede Einheit ersatzweise ihre Datenbankzeile. Der
   Coach verliert dann Details, aber nie den Überblick.

2. **Objektiv und subjektiv bleiben getrennt.** Messwerte und Reflexion
   werden getrennt ausgewiesen, damit das Modell eine Selbsteinschätzung
   nicht als gemessene Tatsache behandelt.
"""

import logging
from datetime import date, timedelta

from sqlalchemy.orm import Session

from models import TrainingSession
from services.obsidian import notes as note_utils
from services.obsidian.client import ObsidianClient, ObsidianError, ObsidianUnavailable

logger = logging.getLogger(__name__)

MAX_NOTE_CHARS = 1800


def _fallback_line(session: TrainingSession) -> str:
    """Zeile aus der Datenbank, wenn keine Note lesbar ist.

    Nutzt dieselbe Formatierung wie der reine Datenbankpfad — eine zweite
    Darstellung würde beim nächsten Feld wieder auseinanderlaufen.
    """
    from core.prompt_templates import format_sessions
    from services.session_view import session_to_dict

    return format_sessions([session_to_dict(session)])


def _extract_managed(content: str) -> str:
    """Den generierten Teil der Note — ohne Frontmatter und Marker."""
    start = content.find(note_utils.MARKER_START)
    end = content.find(note_utils.MARKER_END)
    if start == -1 or end == -1:
        _, body = note_utils._parse_frontmatter(content)
        return body.strip()
    return content[start + len(note_utils.MARKER_START):end].strip()


def build_training_context(
    db: Session,
    days: int = 14,
    client: ObsidianClient | None = None,
) -> dict:
    """Notes der letzten Tage einsammeln, mit DB-Rückfall je Einheit."""
    from core.deps import get_profile
    from services.obsidian.client import client_for_profile

    client = client or client_for_profile(get_profile(db))
    cutoff = date.today() - timedelta(days=days)

    sessions = (
        db.query(TrainingSession)
        .filter(
            TrainingSession.session_date >= cutoff,
            TrainingSession.deleted_at == None,  # noqa: E711
        )
        .order_by(TrainingSession.session_date.desc())
        .all()
    )

    blocks: list[str] = []
    reflections: list[str] = []
    from_notes, from_db = 0, 0
    obsidian_down = False

    for session in sessions:
        content = None
        if client.enabled and session.obsidian_path and not obsidian_down:
            try:
                content = client.get_note(session.obsidian_path)
            except ObsidianUnavailable as e:
                # Einmal aufgeben statt bei jeder Einheit erneut in denselben
                # Timeout zu laufen — der Rest kommt aus der Datenbank.
                logger.warning("Obsidian nicht erreichbar, Kontext aus DB: %s", e)
                obsidian_down = True
            except ObsidianError as e:
                logger.warning("Note %s nicht lesbar: %s", session.obsidian_path, e)

        if not content:
            blocks.append(_fallback_line(session))
            from_db += 1
            # Ohne Note gäbe es sonst gar keine Reflexion im Prompt, obwohl
            # sie in der Datenbank steht.
            if session.reflection:
                reflections.append(
                    f"- **{session.session_date}** ({session.discipline}): {session.reflection}"
                )
            continue

        managed = _extract_managed(content)
        if len(managed) > MAX_NOTE_CHARS:
            managed = managed[:MAX_NOTE_CHARS] + "\n…"
        blocks.append(f"#### {session.session_date} — {(session.discipline or '?').upper()}\n{managed}")
        from_notes += 1

        reflection = note_utils.extract_reflection(content) or session.reflection
        if reflection:
            reflections.append(f"- **{session.session_date}** ({session.discipline}): {reflection}")

    return {
        "sessions_text": "\n\n".join(blocks) if blocks else "Keine Einheiten im Zeitraum.",
        "reflections_text": "\n".join(reflections) if reflections else "",
        "sessions_total": len(sessions),
        "from_notes": from_notes,
        "from_db": from_db,
        "obsidian_available": client.enabled and not obsidian_down,
    }
