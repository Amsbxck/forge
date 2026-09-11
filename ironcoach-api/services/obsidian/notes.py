"""Rendering und Merge der Trainings-Notes.

Die zentrale Anforderung: **Freitext des Athleten darf nie verloren gehen.**
Eine Note besteht deshalb aus drei Zonen:

  1. YAML-Frontmatter  — generiert, aber fremde Keys bleiben erhalten
  2. Managed Block     — zwischen zwei Markern, wird bei jedem Sync ersetzt
  3. Alles andere      — insbesondere "## Reflexion", wird nie angefasst

Ändert sich der Trainingstyp bei einer Re-Klassifizierung, wandert die Note
NICHT. Der Pfad richtet sich nach der Sportart (die steht fest), der Typ ist
Frontmatter und Tag — sonst brechen bei jedem Re-Sync die Obsidian-Links.
"""

import hashlib
import re
from datetime import date, datetime

from core.training_types import (
    FUN_DISCIPLINES,
    FUN_FOLDER,
    INTENSITY_DISCIPLINES,
    intensity_label,
)

MARKER_START = "<!-- ironcoach:start -->"
MARKER_END = "<!-- ironcoach:end -->"
REFLECTION_HEADING = "## Reflexion"

_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n?", re.DOTALL)
_MANAGED_RE = re.compile(
    re.escape(MARKER_START) + r".*?" + re.escape(MARKER_END), re.DOTALL
)

# Frontmatter-Keys, für die IronCoach zuständig ist. Nur diese dürfen beim
# Merge entfernt werden, wenn sie im neuen Stand fehlen — alles andere hat
# der Athlet von Hand ergänzt und bleibt unangetastet.
MANAGED_FRONTMATTER_KEYS = {
    "date", "discipline", "planned_type", "actual_type", "duration_min",
    "distance_km", "avg_hr", "avg_watts", "normalized_power", "avg_pace_min_km",
    "tss", "strava_activity_id", "week_number", "deviation", "tags",
    "intensity", "planned_intensity",
}

DISCIPLINE_LABEL = {
    "bike": "Rad",
    "run": "Lauf",
    "swim": "Schwimmen",
    "gym": "Kraft",
    "brick": "Koppeltraining",
    "rest": "Ruhetag",
}


def note_path(
    discipline: str,
    session_date,
    activity_id=None,
    subdir: str = "Training",
    session_id=None,
    intensity: str | None = None,
) -> str:
    """Stabiler Pfad: Sportart-Ordner, Datum + eindeutige Kennung im Dateinamen.

    Die Kennung verhindert Kollisionen, wenn an einem Tag mehrere Einheiten
    derselben Sportart stattfinden — ein Brick ist in Strava zwei Aktivitäten,
    und zwei Läufe an einem Tag kommen ebenfalls vor.

    Bevorzugt die Strava-ID, weil sie über Systeme hinweg stabil ist. Bei
    Einheiten aus FIT-Uploads (rund zwei Drittel des Bestands) gibt es die
    nicht — dann dient die DB-ID mit s-Präfix als Unterscheider, damit sich
    zwei Einheiten desselben Tages nicht gegenseitig überschreiben.
    """
    day = session_date.isoformat() if hasattr(session_date, "isoformat") else str(session_date)[:10]
    if activity_id:
        stem = f"{day}--{activity_id}"
    elif session_id:
        stem = f"{day}--s{session_id}"
    else:
        stem = day

    # Rad, Lauf und Brick werden nach Intensität abgelegt, damit sich Einheiten
    # gleicher Härte gemeinsam lesen lassen. Schwimmen bleibt flach: dafür gibt
    # es einen eigenen Plan. Alles ohne Trainingsstruktur landet in fun/ —
    # Wanderungen, Ausflüge und Einheiten, die mangels Messwerten nicht
    # eingestuft werden können.
    folder = (discipline or "other").lower()
    if folder in FUN_DISCIPLINES:
        folder = FUN_FOLDER
    elif folder in INTENSITY_DISCIPLINES:
        folder = f"{folder}/{intensity}" if intensity else FUN_FOLDER
    return f"{subdir.strip('/')}/{folder}/{stem}.md"


# --- YAML (bewusst minimal, keine externe Abhängigkeit) ----------------------

def _yaml_scalar(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    text = str(value)
    if text == "":
        return '""'
    # Anführungszeichen nur wo nötig — hält die Notes für Menschen lesbar.
    if re.search(r"[:#\[\]{}|>*&!%@`\"']|^\s|\s$", text):
        return '"' + text.replace('"', '\\"') + '"'
    return text


def _dump_frontmatter(data: dict) -> str:
    lines = []
    for key, value in data.items():
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            if not value:
                continue
            lines.append(f"{key}: [{', '.join(_yaml_scalar(v) for v in value)}]")
        else:
            lines.append(f"{key}: {_yaml_scalar(value)}")
    return "\n".join(lines)


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Sehr einfacher Parser: nur flache key: value-Paare.

    Reicht für unsere Felder. Zeilen, die er nicht versteht, werden unter
    ihrem Schlüssel als Rohtext behalten — sie gehen also nicht verloren,
    auch wenn sie jemand von Hand ergänzt hat.
    """
    match = _FRONTMATTER_RE.match(text or "")
    if not match:
        return {}, text or ""
    block = match.group(1)
    rest = (text or "")[match.end():]
    data: dict = {}
    for line in block.split("\n"):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        data[key.strip()] = value.strip()
    return data, rest


# --- Rendering ---------------------------------------------------------------

def _fmt_pace(seconds) -> str | None:
    """Sekunden/km als mm:ss — ohne Einheit, damit Bereiche sie nur einmal tragen."""
    if not seconds:
        return None
    return f"{int(seconds // 60)}:{int(round(seconds % 60)):02d}"


def build_frontmatter(session: dict, planned: dict | None = None) -> dict:
    """Frontmatter aus Ist-Daten (+ geplanter Einheit, falls gematcht)."""
    planned = planned or {}
    deviation = session.get("deviation_note")

    data = {
        "date": session.get("session_date"),
        "discipline": session.get("discipline"),
        "planned_type": planned.get("training_type"),
        "actual_type": session.get("actual_type"),
        "planned_intensity": planned.get("intensity"),
        "intensity": session.get("intensity"),
        "duration_min": session.get("duration_min"),
        "distance_km": session.get("distance_km"),
        "avg_hr": session.get("avg_hr"),
        "avg_watts": session.get("avg_watts"),
        "normalized_power": session.get("normalized_power"),
        "avg_pace_min_km": session.get("avg_pace_min_km"),
        "tss": session.get("tss"),
        "strava_activity_id": session.get("strava_activity_id"),
        "week_number": session.get("week_number"),
    }
    if deviation:
        data["deviation"] = deviation

    tags = ["training", f"training/{session.get('discipline') or 'other'}"]
    if session.get("actual_type"):
        tags.append(f"type/{session['actual_type']}")
    if session.get("intensity"):
        tags.append(f"intensity/{session['intensity']}")
    data["tags"] = tags
    return {k: v for k, v in data.items() if v is not None}


def build_managed_block(session: dict, planned: dict | None = None) -> str:
    """Der generierte Teil der Note — wird bei jedem Sync ersetzt."""
    planned = planned or {}
    lines = [MARKER_START, ""]

    discipline = session.get("discipline") or "other"
    heading = DISCIPLINE_LABEL.get(discipline, discipline.title())
    label = intensity_label(session.get("intensity"))
    if label:
        heading = f"{heading} — {label}"
    lines.append(f"## {heading}")
    lines.append("")

    # Ist-Werte
    facts = []
    if session.get("duration_min"):
        facts.append(f"- **Dauer:** {session['duration_min']} min")
    if session.get("distance_km"):
        facts.append(f"- **Distanz:** {session['distance_km']} km")
    if session.get("avg_pace_min_km"):
        pace = session["avg_pace_min_km"]
        facts.append(f"- **Pace:** {int(pace)}:{int(round((pace % 1) * 60)):02d}/km")
    if session.get("avg_watts"):
        np_part = f" (NP {session['normalized_power']} W)" if session.get("normalized_power") else ""
        facts.append(f"- **Leistung:** {session['avg_watts']} W{np_part}")
    if session.get("avg_hr"):
        facts.append(f"- **Herzfrequenz:** {session['avg_hr']} bpm")
    if session.get("tss"):
        facts.append(f"- **TSS:** {session['tss']}")
    lines.extend(facts or ["- _Keine Messwerte übermittelt_"])
    lines.append("")

    # Schnellste Abschnitte machen den Hauptteil sichtbar, den die
    # Durchschnitts-Pace verschluckt — bei Intervallen der eigentliche Inhalt.
    splits = session.get("splits") or []
    if splits:
        rendered = " · ".join(
            f"{s['distance_km']} km {s['pace']}/km" for s in splits if s.get("pace")
        )
        if rendered:
            lines.append(f"**Schnellste Abschnitte:** {rendered}")
            lines.append("")

    # Struktur auch ohne zugeordneten Plan zeigen: sie beschreibt die Einheit
    # selbst und ist unabhängig davon interessant, ob sie geplant war.
    structure = session.get("structure") or {}
    if structure.get("main") and not planned:
        segments = []
        for key, label in (
            ("warmup", "Einlaufen"),
            ("main", "Hauptteil"),
            ("cooldown", "Auslaufen"),
        ):
            part = structure.get(key)
            if part and part.get("pace"):
                text = f"{label} {part['distance_km']} km @{part['pace']}/km"
                if key == "main" and structure.get("recovery"):
                    text += f" ({structure['recovery']['laps']} Pausen)"
                segments.append(text)
        if segments:
            lines.append(f"**Struktur:** {' · '.join(segments)}")
            lines.append("")

    # Soll/Ist — nur Zeilen, die für diese Sportart auch etwas aussagen.
    if planned:
        # Ein Brick kommt als zwei Aktivitäten an. Für die Teilaktivität sind
        # weder der Typ ("brick" gegen "threshold") noch die Gesamtdauer
        # sinnvolle Vergleichsgrößen, und das Watt-Zielband gilt nur fürs Rad.
        is_brick_part = planned.get("discipline") == "brick" and discipline in ("bike", "run")

        rows: list[tuple[str, str, str]] = []

        if not is_brick_part:
            rows.append((
                "Typ",
                planned.get("training_type") or "—",
                session.get("actual_type") or "—",
            ))

        if is_brick_part and session.get("brick_total_min"):
            breakdown = session.get("brick_breakdown")
            actual = f"{session['brick_total_min']} min"
            if breakdown:
                actual += f" ({breakdown})"
            rows.append(("Dauer — Brick gesamt", f"{planned.get('duration_min') or '—'} min", actual))
        else:
            rows.append((
                "Dauer",
                f"{planned.get('duration_min') or '—'} min",
                f"{session.get('duration_min') or '—'} min",
            ))

        # Leistung ausschließlich beim Rad: Laufwatt wird gar nicht erst
        # eingelesen, und ein Rad-Zielband neben einer Laufeinheit wäre irreführend.
        if discipline in ("bike", "brick") and (planned.get("target_watts_low") or session.get("avg_watts")):
            target = "—"
            if planned.get("target_watts_low"):
                high = planned.get("target_watts_high") or planned["target_watts_low"]
                target = f"{planned['target_watts_low']}–{high} W"

            # Die Vorgabe gilt den Intervallen, nicht der ganzen Ausfahrt.
            # Ohne diese Aufteilung stünde neben "200–215 W" der Schnitt
            # inklusive Ein-, Ausfahren und Erholungen — hier 188 statt 210 W.
            structure = session.get("structure") or {}
            main = structure.get("main")
            # Der Plan gibt auch für Einfahren, Erholungen und Ausfahren
            # Wattbereiche vor — die gehören neben den jeweiligen Istwert.
            segment_targets = planned.get("segment_targets") or {}

            def _seg_target(key: str, fallback: str = "—") -> str:
                band = (segment_targets.get(key) or {}).get("watt")
                if not band:
                    return fallback
                low, high = band
                return f"{low}–{high} W" if low != high else f"{low} W"

            if main and main.get("avg_watts"):
                for key, label, tgt in (
                    ("warmup", "Einfahren", _seg_target("warmup")),
                    ("main", "Hauptteil", _seg_target("main", target)),
                    ("recovery", "Erholungen", _seg_target("recovery")),
                    ("cooldown", "Ausfahren", _seg_target("cooldown")),
                ):
                    part = structure.get(key)
                    if not part or not part.get("avg_watts"):
                        continue
                    minutes = round(part["seconds"] / 60)
                    name = f"Leistung — {label}"
                    if key == "main" and part.get("laps", 0) > 1:
                        name += f" ({part['laps']}× à ~{round(minutes / part['laps'])} min)"
                    else:
                        name += f" ({minutes} min)"
                    # Ohne Runden aufgezeichnet: kenntlich machen, dass die
                    # Aufteilung aus der Leistungskurve stammt.
                    if key == "main" and session.get("structure_source") == "power":
                        name += " *"
                    rows.append((name, tgt, f"{part['avg_watts']} W"))

            if session.get("time_in_band_min"):
                rows.append((
                    "Zeit im Zielband",
                    session.get("target_band") or "—",
                    f"{session['time_in_band_min']} min",
                ))
            else:
                rows.append(("Leistung — Ø gesamt", target, f"{session.get('avg_watts') or '—'} W"))

        if discipline in ("run", "brick"):
            def _band(low, high):
                lo, hi = _fmt_pace(low), _fmt_pace(high)
                if lo and hi and lo != hi:
                    return f"{lo}–{hi}/km"
                return f"{lo or hi}/km" if (lo or hi) else "—"

            main_target = _band(
                planned.get("target_pace_low_s_per_km"),
                planned.get("target_pace_high_s_per_km"),
            )
            easy_target = _band(
                planned.get("easy_pace_low_s_per_km"),
                planned.get("easy_pace_high_s_per_km"),
            )

            # Die Struktur kommt aus den Runden der Uhr. Damit lässt sich jeder
            # Abschnitt gegen seine eigene Vorgabe stellen, statt einen
            # Durchschnitt über Einlaufen, Hauptteil und Auslaufen zu bilden,
            # der zu keiner der Vorgaben passt.
            # Vorgaben je Abschnitt aus der Blockstruktur; fehlen sie (ältere
            # Pläne ohne Blöcke), greifen die aus dem Fließtext gelesenen
            # Bänder als Ersatz.
            seg = planned.get("segment_targets") or {}

            def _seg_pace(key: str, fallback: str = "—") -> str:
                band = (seg.get(key) or {}).get("pace")
                if not band:
                    return fallback
                lo, hi = _fmt_pace(band[0]), _fmt_pace(band[1])
                return f"{lo}–{hi}/km" if lo != hi else f"{lo}/km"

            structure = session.get("structure") or {}
            if structure.get("main"):
                for key, label, target in (
                    ("warmup", "Einlaufen", _seg_pace("warmup", easy_target)),
                    ("main", "Hauptteil", _seg_pace("main", main_target)),
                    ("recovery", "Trabpausen", _seg_pace("recovery")),
                    ("cooldown", "Auslaufen", _seg_pace("cooldown", easy_target)),
                ):
                    part = structure.get(key)
                    if not part or not part.get("pace"):
                        continue
                    name = f"Pace — {label} ({part['distance_km']} km)"
                    actual = f"{part['pace']}/km"
                    if part.get("avg_hr"):
                        actual += f" · HF {part['avg_hr']}"
                    rows.append((name, target, actual))
            elif planned.get("target_pace_low_s_per_km") or session.get("avg_pace_min_km"):
                ref = session.get("reference_split")
                if ref and ref.get("pace"):
                    rows.append((f"Pace — Hauptteil ({ref['distance_km']} km)", main_target, f"{ref['pace']}/km"))
                elif session.get("avg_pace_min_km"):
                    p = session["avg_pace_min_km"]
                    rows.append((
                        "Pace — Ø gesamt", main_target,
                        f"{int(p)}:{int(round((p % 1) * 60)):02d}/km",
                    ))

        lines.append("### Plan vs. Ist")
        lines.append("")
        lines.append("| | Geplant | Tatsächlich |")
        lines.append("|---|---|---|")
        for label, target, actual in rows:
            lines.append(f"| {label} | {target} | {actual} |")
        if session.get("structure_source") == "power":
            lines.append("")
            lines.append("_\\* Struktur aus der Leistungskurve rekonstruiert — keine Runden aufgezeichnet._")
        lines.append("")
        if session.get("deviation_note"):
            lines.append(f"> [!warning] Abweichung\n> {session['deviation_note']}")
            lines.append("")
        if planned.get("notes"):
            lines.append(f"**Vorgabe:** {planned['notes']}")
            lines.append("")

    lines.append(MARKER_END)
    return "\n".join(lines)


def render_new_note(session: dict, planned: dict | None = None) -> str:
    """Vollständige Note für den ersten Sync — inkl. leerer Reflexionssektion."""
    frontmatter = _dump_frontmatter(build_frontmatter(session, planned))
    managed = build_managed_block(session, planned)
    # In der App geschriebene Reflexion in die neue Note übernehmen — sonst
    # stünde sie zwar in der Datenbank, aber nicht dort, wo der Athlet liest.
    existing_reflection = (session.get("reflection") or "").strip()
    body = f"{existing_reflection}\n\n" if existing_reflection else ""

    return (
        f"---\n{frontmatter}\n---\n\n"
        f"{managed}\n\n"
        f"{REFLECTION_HEADING}\n\n"
        f"{body}"
        f"<!-- Hier oder in der App schreiben — beides wird abgeglichen. -->\n\n"
    )


# --- Merge -------------------------------------------------------------------

def merge_note(existing: str, session: dict, planned: dict | None = None) -> str:
    """Bestehende Note aktualisieren, ohne Handgeschriebenes zu verlieren.

    - Frontmatter: unsere Keys werden aktualisiert, fremde bleiben stehen
    - Managed Block: wird ersetzt
    - Fehlt der Managed Block (jemand hat ihn gelöscht), wird er NICHT
      wieder eingefügt — das war eine bewusste Entscheidung des Athleten
    - Alles übrige bleibt Zeichen für Zeichen erhalten
    """
    old_frontmatter, body = _parse_frontmatter(existing)

    new_values = build_frontmatter(session, planned)
    merged_frontmatter = dict(old_frontmatter)

    # Von uns verwaltete Keys, die es nicht mehr gibt, müssen verschwinden —
    # sonst behauptet die Note für immer eine Abweichung, die längst
    # aufgelöst ist. Fremde Keys sind davon ausgenommen.
    for key in MANAGED_FRONTMATTER_KEYS - set(new_values):
        merged_frontmatter.pop(key, None)

    for key, value in new_values.items():
        if isinstance(value, (list, tuple)):
            merged_frontmatter[key] = f"[{', '.join(_yaml_scalar(v) for v in value)}]"
        else:
            merged_frontmatter[key] = _yaml_scalar(value)

    frontmatter_text = "\n".join(f"{k}: {v}" for k, v in merged_frontmatter.items() if v is not None)

    if _MANAGED_RE.search(body):
        new_body = _MANAGED_RE.sub(lambda _: build_managed_block(session, planned), body, count=1)
    else:
        new_body = body

    return f"---\n{frontmatter_text}\n---\n{new_body}"


def set_reflection(content: str, text: str | None) -> str:
    """Reflexionsabschnitt einer Note ersetzen.

    Damit wird die App zur Schreibfläche: wer dort tippt, findet es im Vault
    wieder, ohne die Note anfassen zu müssen. Alles außerhalb des Abschnitts
    bleibt unberührt — auch eigene Überschriften darunter.
    """
    body = (text or "").strip()
    section = f"{REFLECTION_HEADING}\n\n{body}\n" if body else f"{REFLECTION_HEADING}\n\n"

    pattern = re.compile(
        re.escape(REFLECTION_HEADING) + r"\s*\n.*?(?=\n## |\Z)", re.DOTALL
    )
    if pattern.search(content):
        return pattern.sub(lambda _: section.rstrip("\n"), content, count=1)
    # Kein Abschnitt vorhanden — jemand hat ihn entfernt. Dann wird er nicht
    # wieder eingefügt; das war eine Entscheidung des Athleten.
    return content


def content_hash(text: str) -> str:
    """Fingerabdruck des zuletzt geschriebenen Inhalts.

    Weicht die Note beim nächsten Sync davon ab, wurde von Hand editiert —
    dann wird außerhalb des Managed Blocks nichts angetastet.
    """
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:16]


def extract_reflection(text: str) -> str | None:
    """Freitext unter '## Reflexion' — Input für die Wochenplanung."""
    if not text:
        return None
    _, body = _parse_frontmatter(text)
    body = _MANAGED_RE.sub("", body)
    match = re.search(
        re.escape(REFLECTION_HEADING) + r"\s*\n(.*?)(?=\n## |\Z)", body, re.DOTALL
    )
    if not match:
        return None
    reflection = re.sub(r"<!--.*?-->", "", match.group(1), flags=re.DOTALL).strip()
    return reflection or None
