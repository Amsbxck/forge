import re
from io import BytesIO
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, PageBreak
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER

# Farbpalette der Anwendung. Das PDF sah bisher aus wie ein fremdes
# Dokument — lila auf weiß, während die Oberfläche dunkel mit Cyan ist.
# Wer den Plan ausdruckt, soll dieselbe Sache vor sich haben.
GROUND = colors.HexColor("#07080f")     # Seitengrund
PANEL = colors.HexColor("#111318")      # Karten
PANEL_DEEP = colors.HexColor("#0d0f17")  # Eingabeflächen, Tabellenzeilen
LINE = colors.HexColor("#1e2228")       # Trennlinien
INK = colors.HexColor("#e8eaf0")        # Fließtext
MUTED = colors.HexColor("#8a909e")      # Sekundärtext
FAINT = colors.HexColor("#3a3f4a")      # Beschriftungen
ACCENT = colors.HexColor("#00d4ff")     # Akzent

WARN = colors.HexColor("#f59e0b")
BAD = colors.HexColor("#ef4444")
WHITE = colors.white

# Rückwärtskompatible Namen — im Code wird an mehreren Stellen darauf
# verwiesen, und ein Umbenennen dort brächte keinen Gewinn.
PURPLE = ACCENT
PURPLE_LIGHT = PANEL_DEEP
DARK = INK
GRAY_HEADER = PANEL_DEEP
ORANGE = WARN
GREEN = colors.HexColor("#22c55e")
GRAY_BG = PANEL

def P(text, style) -> "Paragraph":
    """Paragraph mit automatischer Latin-1 Bereinigung."""
    return Paragraph(_safe(text), style)


def _safe(text) -> str:
    """Ersetzt Unicode-Zeichen die Helvetica/Latin-1 nicht kennt."""
    if not isinstance(text, str):
        text = str(text)
    replacements = {
        '—': '-', '–': '-', '‒': '-',  # em/en dash
        '’': "'", '‘': "'", '“': '"', '”': '"',
        '→': '->', '←': '<-', '•': '*', '…': '...',
        '°': 'deg', '×': 'x', '÷': '/',
    }
    for orig, repl in replacements.items():
        text = text.replace(orig, repl)
    # Emojis und alle restlichen non-Latin-1 Zeichen entfernen
    text = re.sub(r'[^\x00-\xff]', '', text)
    return text


# Dieselben Farben wie in der Oberfläche (utils/colors.js): Ampelfarben
# bleiben Bewertungen vorbehalten, Disziplinen bewerten nichts.
SESSION_COLORS = {
    "swim": colors.HexColor("#38bdf8"),
    "bike": colors.HexColor("#a855f7"),
    "run": colors.HexColor("#ec4899"),
    "brick": colors.HexColor("#d946ef"),
    "gym": colors.HexColor("#94a3b8"),
    "hike": colors.HexColor("#a1a1aa"),
    "rest": colors.HexColor("#3a3f4a"),
}

SESSION_LABELS = {
    "bike": "RAD",
    "run": "LAUFEN",
    "swim": "SCHWIMMEN",
    "gym": "GYM",
    "brick": "BRICK",
    "rest": "REST",
}


def _styles():
    base = getSampleStyleSheet()
    s = {}

    s["title"] = ParagraphStyle(
        "title",
        parent=base["Normal"],
        fontName="Helvetica-Bold",
        fontSize=24,
        # Ohne eigenes leading behält der Absatz die Zeilenhöhe der
        # Grundschrift — die Unterzeile lief dann quer durch die Überschrift.
        leading=27,
        textColor=INK,
        spaceAfter=2 * mm,
    )
    s["subtitle"] = ParagraphStyle(
        "subtitle",
        parent=base["Normal"],
        fontName="Helvetica",
        fontSize=11,
        textColor=MUTED,
        spaceAfter=4 * mm,
    )
    s["section_header"] = ParagraphStyle(
        "section_header",
        parent=base["Normal"],
        fontName="Helvetica-Bold",
        fontSize=13,
        textColor=WHITE,
        spaceAfter=0,
    )
    s["subsection"] = ParagraphStyle(
        "subsection",
        parent=base["Normal"],
        fontName="Helvetica-Bold",
        fontSize=10,
        textColor=PURPLE,
        spaceAfter=1 * mm,
        spaceBefore=2 * mm,
    )
    s["body"] = ParagraphStyle(
        "body",
        parent=base["Normal"],
        fontName="Helvetica",
        fontSize=9,
        textColor=DARK,
        spaceAfter=1 * mm,
        leading=13,
    )
    s["body_bold"] = ParagraphStyle(
        "body_bold",
        parent=base["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9,
        textColor=DARK,
        spaceAfter=1 * mm,
    )
    s["note"] = ParagraphStyle(
        "note",
        parent=base["Normal"],
        fontName="Helvetica-Oblique",
        fontSize=9,
        textColor=PURPLE,
        spaceAfter=1 * mm,
    )
    s["warning"] = ParagraphStyle(
        "warning",
        parent=base["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9,
        textColor=ORANGE,
        spaceAfter=1 * mm,
    )
    s["table_header"] = ParagraphStyle(
        "table_header",
        parent=base["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7.5,
        textColor=MUTED,
        alignment=TA_CENTER,
    )
    s["table_cell"] = ParagraphStyle(
        "table_cell",
        parent=base["Normal"],
        fontName="Helvetica",
        fontSize=9,
        textColor=INK,
        alignment=TA_CENTER,
    )
    s["progress"] = ParagraphStyle(
        "progress",
        parent=base["Normal"],
        fontName="Helvetica-Bold",
        fontSize=10,
        textColor=DARK,
        spaceAfter=3 * mm,
    )
    return s


def _day_section_header(day_obj: dict, st: dict):
    """Erstellt den farbigen Header-Block für jeden Tag."""
    session_type = day_obj.get("session_type", "rest")
    color = SESSION_COLORS.get(session_type, PURPLE)
    label = SESSION_LABELS.get(session_type, session_type.upper())

    day_name = day_obj.get("day", "")
    date_str = day_obj.get("date", "")
    duration = day_obj.get("duration_min", "")
    duration_text = f" | {duration} min" if duration else ""

    header_text = f"{day_name.upper()} {date_str} – {label}{duration_text}"

    kopf_stil = ParagraphStyle(
        "day_header", parent=st["section_header"], textColor=color, fontSize=11,
    )
    table_data = [[P(header_text, kopf_stil)]]
    t = Table(table_data, colWidths=[170 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PANEL),
        ("LINEBEFORE", (0, 0), (0, -1), 3, color),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("ROUNDEDCORNERS", [4, 4, 4, 4]),
    ]))
    return t


def _render_blocks(blocks, st: dict) -> list:
    """Rendert eine Liste von Intervall-Blöcken als Tabelle."""
    if not blocks or not isinstance(blocks, list):
        return []

    # Prüfe ob Blöcke Tabellenformat haben (dict mit Feldern)
    if not isinstance(blocks[0], dict):
        # Einfache String-Liste
        items = []
        for b in blocks:
            items.append(P(f"• {b}", st["body"]))
        return items

    # Ermittle alle Spalten
    all_keys = []
    for b in blocks:
        for k in b.keys():
            if k not in all_keys:
                all_keys.append(k)

    if not all_keys:
        return []

    # Header-Zeile
    header_row = [P(k.upper(), st["table_header"]) for k in all_keys]
    data = [header_row]

    for b in blocks:
        row = [P(str(b.get(k, "–")), st["table_cell"]) for k in all_keys]
        data.append(row)

    col_w = 170 * mm / len(all_keys)
    t = Table(data, colWidths=[col_w] * len(all_keys))
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PANEL_DEEP),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [PANEL, PANEL_DEEP]),
        ("GRID", (0, 0), (-1, -1), 0.4, LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return [t]


LABEL_MAP = {
    "warmup": "Warm-up",
    "warm_up": "Warm-up",
    "hauptteil": "Hauptteil",
    "main": "Hauptteil",
    "blocks": "Trainingsblöcke",
    "intervals": "Intervalle",
    "kraftblock": "Kraftblock",
    "exercises": "Übungen",
    "cooldown": "Cool-down",
    "cool_down": "Cool-down",
    "struktur": "Struktur",
    "structure": "Struktur",
    "bike": "RAD",
    "run": "LAUFEN",
    "swim": "SCHWIMMEN",
    "transition": "Wechsel",
    "typ": "Typ",
    "pace": "Pace",
    "ziel_hr": "Ziel-HR",
    "strides": "Strides",
    "hinweis": "Hinweis",
}


def _label_for(key: str) -> str:
    return LABEL_MAP.get(key, key.replace("_", " ").title())


def _render_details(details: dict, st: dict, depth: int = 0) -> list:
    """Rendert das details-Objekt eines Trainingstags rekursiv."""
    if not details or not isinstance(details, dict):
        return []

    elements = []

    order = ["bike", "transition", "run", "swim",
             "warmup", "warm_up", "hauptteil", "main", "typ", "struktur", "structure",
             "blocks", "intervals", "pace", "ziel_hr", "kraftblock", "exercises",
             "cooldown", "cool_down", "strides", "hinweis"]

    ordered_keys = [k for k in order if k in details]
    remaining_keys = [k for k in details.keys() if k not in ordered_keys]

    for key in ordered_keys + remaining_keys:
        val = details[key]
        if val is None or val == "":
            continue

        label = _label_for(key)

        if isinstance(val, list):
            elements.append(P(label, st["subsection"]))
            block_els = _render_blocks(val, st)
            if block_els:
                elements.extend(block_els)
            else:
                for item in val:
                    elements.append(P(f"• {item}", st["body"]))
        elif isinstance(val, dict):
            # Recursive: subsection-style for nested blocks (bike/run in brick)
            elements.append(P(label, st["subsection"]))
            elements.extend(_render_details(val, st, depth=depth + 1))
        else:
            if depth == 0:
                elements.append(P(label, st["subsection"]))
                elements.append(P(str(val), st["body"]))
            else:
                elements.append(P(f"<b>{label}:</b> {val}", st["body"]))

    return elements


def _overview_table(days: list, st: dict) -> Table:
    """Wochenübersichts-Tabelle."""
    header = [
        P("Tag", st["table_header"]),
        P("Datum", st["table_header"]),
        P("Einheit", st["table_header"]),
        P("Dauer", st["table_header"]),
    ]
    data = [header]

    for d in days:
        session_type = d.get("session_type", "rest")
        label = SESSION_LABELS.get(session_type, session_type.upper())
        duration = f"{d.get('duration_min', '–')} min" if d.get("duration_min") else "–"
        row = [
            P(d.get("day", ""), st["table_cell"]),
            P(d.get("date", ""), st["table_cell"]),
            P(label, st["table_cell"]),
            P(duration, st["table_cell"]),
        ]
        data.append(row)

    col_widths = [35 * mm, 35 * mm, 60 * mm, 40 * mm]
    t = Table(data, colWidths=col_widths)

    row_colors = []
    for i, d in enumerate(days, start=1):
        session_type = d.get("session_type", "rest")
        c = SESSION_COLORS.get(session_type, MUTED)
        # Auf dunklem Grund reicht eine sehr schwache Einfärbung; mehr davon
        # macht die Schrift darüber unlesbar.
        row_colors.append(("BACKGROUND", (0, i), (-1, i),
                           colors.Color(c.red, c.green, c.blue, alpha=0.10)))
        # Farbkante links statt Gitternetz — dieselbe Zuordnung wie im
        # Wochenkalender der Oberfläche.
        row_colors.append(("LINEBEFORE", (0, i), (0, i), 2, c))

    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PANEL_DEEP),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        *row_colors,
    ]))
    return t


def _page_furniture(canvas, doc):
    """Dunkler Grund, Wortmarke oben, Seitenzahl unten.

    ReportLab kennt keinen Seitenhintergrund — er wird als Rechteck über die
    volle Seite gezeichnet, bevor der Inhalt darüberkommt.
    """
    canvas.saveState()
    breite, hoehe = A4

    canvas.setFillColor(GROUND)
    canvas.rect(0, 0, breite, hoehe, stroke=0, fill=1)

    # Wortmarke
    canvas.setFillColor(ACCENT)
    canvas.setFont("Helvetica-Bold", 12)
    canvas.drawString(20 * mm, hoehe - 12 * mm, "F O R G E")
    canvas.setFillColor(FAINT)
    canvas.setFont("Helvetica", 6.5)
    canvas.drawString(20 * mm, hoehe - 15.5 * mm, "I R O N C O A C H   A I")

    # Haarlinie unter dem Kopf
    canvas.setStrokeColor(LINE)
    canvas.setLineWidth(0.5)
    canvas.line(20 * mm, hoehe - 18 * mm, breite - 20 * mm, hoehe - 18 * mm)

    # Fußzeile
    canvas.setFillColor(FAINT)
    canvas.setFont("Helvetica", 7)
    canvas.drawRightString(breite - 20 * mm, 12 * mm, f"Seite {canvas.getPageNumber()}")
    canvas.drawString(20 * mm, 12 * mm, datetime.now().strftime("%d.%m.%Y"))
    canvas.restoreState()


def generate_plan_pdf(plan: dict) -> bytes:
    """
    Generiert ein PDF aus einem WeeklyPlan (plan_content dict).
    Gibt die Bytes des PDFs zurück.
    """
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=26 * mm,
        bottomMargin=20 * mm,
    )

    content = plan.get("plan_content", plan)  # akzeptiert plan_content oder direkt dict
    week = content.get("week", "?")
    phase = content.get("phase", "")
    coaching_comment = content.get("coaching_comment", "")
    adjustments = content.get("adjustments", [])
    days = content.get("days", [])

    # Datums-Range aus days
    dates = [d.get("date", "") for d in days if d.get("date")]
    date_range = f"{dates[0]} – {dates[-1]}" if len(dates) >= 2 else ""

    st = _styles()
    elements = []

    # ── Titel ──
    elements.append(P(f"WOCHE {week} – {phase}", st["title"]))
    if date_range:
        elements.append(P(date_range, st["subtitle"]))

    # ── Coaching-Kommentar ──
    if coaching_comment:
        elements.append(P(coaching_comment, st["note"]))

    # ── Anpassungen ──
    if adjustments:
        adj_text = " | ".join(adjustments)
        elements.append(P(adj_text, st["progress"]))

    elements.append(HRFlowable(width="100%", thickness=0.5, color=PURPLE, spaceAfter=4 * mm))

    # ── Wochenübersicht ──
    elements.append(P("Wochenübersicht", st["subsection"]))
    elements.append(_overview_table(days, st))
    elements.append(Spacer(1, 6 * mm))

    # ── Tagesdetails ──
    for day_obj in days:
        session_type = day_obj.get("session_type", "rest")

        # Section-Header
        elements.append(_day_section_header(day_obj, st))
        elements.append(Spacer(1, 2 * mm))

        # Notes
        notes = day_obj.get("notes", "")
        if notes:
            # Warnungen hervorheben
            if any(w in notes.lower() for w in ["stopp", "achtung", "vorsicht", "sofort"]):
                elements.append(P(f"⚠ {notes}", st["warning"]))
            else:
                elements.append(P(notes, st["note"]))

        # Details
        details = day_obj.get("details", {})
        detail_elements = _render_details(details, st)
        elements.extend(detail_elements)

        elements.append(Spacer(1, 5 * mm))

    # ── Zusammenfassung ──
    elements.append(PageBreak())
    elements.append(P(f"Woche {week} – Zusammenfassung", st["title"]))
    elements.append(Spacer(1, 4 * mm))

    # Zähle Sessions
    counts: dict[str, int] = {}
    total_min = 0
    for d in days:
        st_key = d.get("session_type", "rest")
        counts[st_key] = counts.get(st_key, 0) + 1
        total_min += d.get("duration_min") or 0

    summary_header = [
        P("Einheit", st["table_header"]),
        P("Anzahl", st["table_header"]),
        P("Gesamtdauer", st["table_header"]),
    ]
    summary_data = [summary_header]
    for s_type, count in counts.items():
        dur = sum(d.get("duration_min") or 0 for d in days if d.get("session_type") == s_type)
        summary_data.append([
            P(SESSION_LABELS.get(s_type, s_type.upper()), st["table_cell"]),
            P(f"{count}×", st["table_cell"]),
            P(f"~{dur} min" if dur else "Nach Plan", st["table_cell"]),
        ])

    sum_table = Table(summary_data, colWidths=[60 * mm, 40 * mm, 70 * mm])
    sum_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), DARK),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, GRAY_BG]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#DDDDDD")),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
    ]))
    elements.append(sum_table)

    elements.append(Spacer(1, 4 * mm))
    generated = datetime.now().strftime("%d.%m.%Y %H:%M")
    elements.append(Paragraph(
        f"Erstellt von IronCoach AI am {generated}",
        st["note"]
    ))

    doc.build(elements, onFirstPage=_page_furniture, onLaterPages=_page_furniture)
    return buf.getvalue()
