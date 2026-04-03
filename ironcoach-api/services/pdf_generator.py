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

# Farbpalette (passend zum PDF-Beispiel)
PURPLE = colors.HexColor("#6B3FA0")
PURPLE_LIGHT = colors.HexColor("#EDE7F6")
DARK = colors.HexColor("#2D2D2D")
GRAY_HEADER = colors.HexColor("#444444")
ORANGE = colors.HexColor("#E65100")
GREEN = colors.HexColor("#2E7D32")
GRAY_BG = colors.HexColor("#F5F5F5")
WHITE = colors.white

SESSION_COLORS = {
    "bike": colors.HexColor("#1565C0"),
    "run": colors.HexColor("#2E7D32"),
    "swim": colors.HexColor("#00838F"),
    "gym": colors.HexColor("#6A1B9A"),
    "brick": colors.HexColor("#BF360C"),
    "rest": colors.HexColor("#757575"),
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
        textColor=DARK,
        spaceAfter=2 * mm,
    )
    s["subtitle"] = ParagraphStyle(
        "subtitle",
        parent=base["Normal"],
        fontName="Helvetica",
        fontSize=11,
        textColor=colors.HexColor("#555555"),
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
        fontSize=9,
        textColor=WHITE,
        alignment=TA_CENTER,
    )
    s["table_cell"] = ParagraphStyle(
        "table_cell",
        parent=base["Normal"],
        fontName="Helvetica",
        fontSize=9,
        textColor=DARK,
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

    table_data = [[Paragraph(header_text, st["section_header"])]]
    t = Table(table_data, colWidths=[170 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), color),
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
            items.append(Paragraph(f"• {b}", st["body"]))
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
    header_row = [Paragraph(k.upper(), st["table_header"]) for k in all_keys]
    data = [header_row]

    for b in blocks:
        row = [Paragraph(str(b.get(k, "–")), st["table_cell"]) for k in all_keys]
        data.append(row)

    col_w = 170 * mm / len(all_keys)
    t = Table(data, colWidths=[col_w] * len(all_keys))
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), GRAY_HEADER),
        ("BACKGROUND", (0, 1), (-1, -1), GRAY_BG),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, GRAY_BG]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return [t]


def _render_details(details: dict, st: dict) -> list:
    """Rendert das details-Objekt eines Trainingstags."""
    if not details or not isinstance(details, dict):
        return []

    elements = []

    # Bekannte Schlüssel in sinnvoller Reihenfolge
    order = ["warmup", "warm_up", "hauptteil", "main", "blocks", "intervals",
             "kraftblock", "exercises", "cooldown", "cool_down", "struktur", "structure"]

    rendered_keys = set()

    for key in order:
        if key not in details:
            continue
        rendered_keys.add(key)
        val = details[key]

        label_map = {
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
        }
        label = label_map.get(key, key.replace("_", " ").title())
        elements.append(Paragraph(label, st["subsection"]))

        if isinstance(val, list):
            block_els = _render_blocks(val, st)
            if block_els:
                elements.extend(block_els)
            else:
                for item in val:
                    elements.append(Paragraph(f"• {item}", st["body"]))
        elif isinstance(val, dict):
            for k, v in val.items():
                elements.append(Paragraph(f"<b>{k}:</b> {v}", st["body"]))
        else:
            elements.append(Paragraph(str(val), st["body"]))

    # Restliche Schlüssel
    for key, val in details.items():
        if key in rendered_keys:
            continue
        elements.append(Paragraph(key.replace("_", " ").title(), st["subsection"]))
        if isinstance(val, list):
            block_els = _render_blocks(val, st)
            if block_els:
                elements.extend(block_els)
            else:
                for item in val:
                    elements.append(Paragraph(f"• {item}", st["body"]))
        elif isinstance(val, dict):
            for k, v in val.items():
                elements.append(Paragraph(f"<b>{k}:</b> {v}", st["body"]))
        else:
            elements.append(Paragraph(str(val), st["body"]))

    return elements


def _overview_table(days: list, st: dict) -> Table:
    """Wochenübersichts-Tabelle."""
    header = [
        Paragraph("Tag", st["table_header"]),
        Paragraph("Datum", st["table_header"]),
        Paragraph("Einheit", st["table_header"]),
        Paragraph("Dauer", st["table_header"]),
    ]
    data = [header]

    for d in days:
        session_type = d.get("session_type", "rest")
        label = SESSION_LABELS.get(session_type, session_type.upper())
        duration = f"{d.get('duration_min', '–')} min" if d.get("duration_min") else "–"
        row = [
            Paragraph(d.get("day", ""), st["table_cell"]),
            Paragraph(d.get("date", ""), st["table_cell"]),
            Paragraph(label, st["table_cell"]),
            Paragraph(duration, st["table_cell"]),
        ]
        data.append(row)

    col_widths = [35 * mm, 35 * mm, 60 * mm, 40 * mm]
    t = Table(data, colWidths=col_widths)

    row_colors = []
    for i, d in enumerate(days, start=1):
        session_type = d.get("session_type", "rest")
        c = SESSION_COLORS.get(session_type, GRAY_HEADER)
        light = colors.Color(c.red, c.green, c.blue, alpha=0.12)
        row_colors.append(("BACKGROUND", (0, i), (-1, i), light))

    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), DARK),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#DDDDDD")),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        *row_colors,
    ]))
    return t


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
        topMargin=18 * mm,
        bottomMargin=18 * mm,
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
    elements.append(Paragraph(f"WOCHE {week} – {phase}", st["title"]))
    if date_range:
        elements.append(Paragraph(date_range, st["subtitle"]))

    # ── Coaching-Kommentar ──
    if coaching_comment:
        elements.append(Paragraph(coaching_comment, st["note"]))

    # ── Anpassungen ──
    if adjustments:
        adj_text = " | ".join(adjustments)
        elements.append(Paragraph(adj_text, st["progress"]))

    elements.append(HRFlowable(width="100%", thickness=0.5, color=PURPLE, spaceAfter=4 * mm))

    # ── Wochenübersicht ──
    elements.append(Paragraph("Wochenübersicht", st["subsection"]))
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
                elements.append(Paragraph(f"⚠ {notes}", st["warning"]))
            else:
                elements.append(Paragraph(notes, st["note"]))

        # Details
        details = day_obj.get("details", {})
        detail_elements = _render_details(details, st)
        elements.extend(detail_elements)

        elements.append(Spacer(1, 5 * mm))

    # ── Zusammenfassung ──
    elements.append(PageBreak())
    elements.append(Paragraph(f"Woche {week} – Zusammenfassung", st["title"]))
    elements.append(Spacer(1, 4 * mm))

    # Zähle Sessions
    counts: dict[str, int] = {}
    total_min = 0
    for d in days:
        st_key = d.get("session_type", "rest")
        counts[st_key] = counts.get(st_key, 0) + 1
        total_min += d.get("duration_min") or 0

    summary_header = [
        Paragraph("Einheit", st["table_header"]),
        Paragraph("Anzahl", st["table_header"]),
        Paragraph("Gesamtdauer", st["table_header"]),
    ]
    summary_data = [summary_header]
    for s_type, count in counts.items():
        dur = sum(d.get("duration_min") or 0 for d in days if d.get("session_type") == s_type)
        summary_data.append([
            Paragraph(SESSION_LABELS.get(s_type, s_type.upper()), st["table_cell"]),
            Paragraph(f"{count}×", st["table_cell"]),
            Paragraph(f"~{dur} min" if dur else "Nach Plan", st["table_cell"]),
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

    doc.build(elements)
    return buf.getvalue()
