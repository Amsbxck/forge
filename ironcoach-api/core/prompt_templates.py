from datetime import date, timedelta

from core.race_types import is_deload
from core.training_types import planbare_typen_tabelle




def get_phase(week: int, total_weeks: int = 33) -> str:
    """Phase einer Trainingswoche.

    Die Grenzen ergeben sich aus der Gesamtdauer der Vorbereitung, nicht mehr
    aus fest verdrahteten 33 Wochen — ein Sprint-Triathlon über 12 Wochen
    braucht dieselbe Abfolge in gestauchter Form.
    """
    from core.race_types import phase_for_week
    return phase_for_week(week, total_weeks)


def get_week_dates(week_number: int, plan_start: date) -> tuple[date, date]:
    week_start = plan_start + timedelta(weeks=week_number - 1)
    week_end = week_start + timedelta(days=6)
    return week_start, week_end


def analyze_hrv_trend(hrv_list: list, grenzen: dict | None = None) -> str:
    """Richtung und Streuung der HRV — das, was ein Tageswert nicht zeigt.

    Hier stand ein Mittel der letzten drei Tage gegen fest verdrahtete 80 und
    70 ms. Das waren die Zahlen eines einzelnen Athleten, und sie standen im
    Prompt zwei Zeilen neben der persönlich gerechneten Normalspanne — zwei
    widersprechende Urteile über denselben Tag. Für einen Athleten mit einer
    Normallage um 45 ms war das Urteil dauerhaft "Rot".

    Was ein Tageswert gegen die Spanne nicht beantwortet, ist die Richtung: drei
    fallende Tage innerhalb der Spanne sind ein anderes Bild als drei
    schwankende. Genau diese Zeile stand bisher als „⚠️ Fallend 3+ Tage" in
    zwei Prompt-Tabellen, ohne dass irgendetwas sie berechnete.

    Die Streuung wird nur gegen eine **berechnete** Grundlinie verglichen. Bei
    einer eingetragenen Spanne aus der Uhr ist deren Breite kein σ, und sie als
    solches zu verrechnen wäre eine erfundene Begründung.
    """
    werte = [h["rmssd"] for h in hrv_list if h.get("rmssd")]
    if not werte:
        return "Keine HRV-Daten vorhanden"

    teile = []

    # Richtung: nur eine durchgehend fallende Folge ist eine Aussage. Zwei
    # fallende Tage mit einem Ausreißer dazwischen sind Rauschen.
    if len(werte) >= 3:
        letzte = werte[-3:]
        if letzte[0] > letzte[1] > letzte[2]:
            # Gezählt werden die Rückgänge, nicht die Messwerte: vier Tage in
            # Folge tiefer sind fünf Werte.
            folge = 0
            for i in range(len(werte) - 1, 0, -1):
                if werte[i] >= werte[i - 1]:
                    break
                folge += 1
            teile.append(
                f"seit {folge} Tagen fallend "
                f"({' → '.join(f'{w:.0f}' for w in werte[-(folge + 1):])})"
            )
        elif letzte[0] < letzte[1] < letzte[2]:
            teile.append("seit 3 Tagen steigend")

    if len(werte) >= 3:
        import statistics

        mittel = statistics.fmean(werte)
        if mittel > 0:
            cv = statistics.pstdev(werte) / mittel * 100
            text = f"Streuung der letzten {len(werte)} Tage: CV {cv:.1f} %"
            if grenzen and grenzen.get("quelle") == "auto":
                unten, oben = grenzen.get("gruen_ab"), grenzen.get("gruen_bis")
                if unten and oben:
                    # Die Spanne ist Mittelwert ± 0,5 σ, ihre Breite also 1 σ.
                    mitte = (unten + oben) / 2
                    if mitte > 0:
                        basis = (oben - unten) / mitte * 100
                        text += f" gegen {basis:.1f} % in der Grundlinie"
                        if cv > basis * 1.5:
                            text += " — deutlich erhöht"
            teile.append(text)

    if not teile:
        return f"{len(werte)} Messung(en), kein auswertbarer Trend"
    return " · ".join(teile)


def format_sessions(sessions: list) -> str:
    """Kompakte Zeile je Einheit — inklusive Klassifizierung und Abweichung.

    Der Gesamtschnitt allein führt in die Irre: 188 W über eine Ausfahrt mit
    Ein-, Ausfahren und Erholungen sagt nichts darüber, ob die Intervalle bei
    210 W getroffen wurden. Deshalb stehen Trainingstyp, Hauptteil und
    Abweichung mit in der Zeile.
    """
    if not sessions:
        return "Keine Einheiten in den letzten 14 Tagen oder IronCoachAI frisch implementiert."
    lines = []
    for s in sessions:
        # Bei Sportarten außerhalb der geplanten Disziplinen die
        # Originalbezeichnung zeigen — "OTHER" sagt dem Coach nichts.
        bezeichnung = (
            (s.get("sport_type") or "Crosstraining")
            if s["discipline"] == "other" else s["discipline"]
        )
        head = f"- {s['session_date']} | {bezeichnung.upper()}"
        if s.get("actual_type"):
            head += f" {s['actual_type']}"
        parts = [head, f"| {s.get('duration_min', '?')}min"]

        if s.get("distance_km"):
            parts.append(f"| {s['distance_km']:.1f}km")
        if s.get("avg_watts"):
            parts.append(f"| Ø {s['avg_watts']}W ({s.get('normalized_power', '?')}W NP)")
        if s.get("avg_pace_min_km"):
            pace = s["avg_pace_min_km"]
            parts.append(f"| Ø {int(pace)}:{int(round((pace % 1) * 60)):02d}/km")
        if s.get("avg_hr"):
            parts.append(f"| HF {s['avg_hr']}")
        if s.get("tss"):
            # Geschätzte Werte kenntlich machen.
            marke = "~" if s.get("tss_source") == "hr" else ""
            parts.append(f"| TSS {marke}{s['tss']:.0f}")
        if s.get("hr_zones"):
            z = s["hr_zones"]
            parts.append(f"| Z2 {z.get('z2', 0)}% Z4 {z.get('z4', 0)}% Z5 {z.get('z5', 0)}%")

        line = " ".join(parts)
        # Hauptteil und Abweichung in eigene Zeilen: sie sind der Grund,
        # warum eine Einheit gelungen ist oder nicht.
        if s.get("harte_minuten"):
            from services.segments import harte_minuten_text
            if (text := harte_minuten_text(s["harte_minuten"])):
                line += f"\n    harte Arbeit: {text}"
        if s.get("structure"):
            line += f"\n    {s['structure']}"
        if s.get("deviation_note"):
            line += f"\n    → {s['deviation_note']}"
        lines.append(line)
    return "\n".join(lines)


AMPEL_SYMBOL = {"green": "🟢", "yellow": "🟡", "red": "🔴"}


def format_hrv(hrv_list: list, grenzen: dict | None = None) -> str:
    """HRV-Verlauf für den Prompt — gegen die eigene Spanne, nicht gegen Zahlen.

    Hier stand `"🟢" if h["rmssd"] > 85 else ...`, also genau die festen
    Schwellen, die `services/hrv_baseline.py` ersetzt. Der Coach bekam damit
    zwei widersprechende Signale in derselben Zeile: ein Symbol nach fremden
    Zahlen und daneben den richtig gerechneten Status. Für einen Athleten mit
    einer Normallage um 45 stand dort dauerhaft 🔴 neben "green".
    """
    if not hrv_list:
        return "Keine HRV-Daten."

    lines = []
    if grenzen:
        unten, oben = grenzen.get("gruen_ab"), grenzen.get("gruen_bis")
        if unten and oben:
            # Die Herkunft nennen, nicht unterstellen. Eine eingetragene Spanne
            # kommt aus der Uhr, die über Monate gelernt hat — sie ist nicht
            # "Mittelwert ± 0,5 σ", und das so zu behaupten wäre eine erfundene
            # Begründung für eine Zahl, die jemand von Hand gesetzt hat.
            herkunft = (
                "vom Athleten eingetragen, aus seiner Uhr"
                if grenzen.get("quelle") == "manual"
                else "Mittelwert ± 0,5 σ seiner Messungen"
            )
            lines.append(
                f"Normalspanne dieses Athleten: {unten}–{oben} ms ({herkunft}). "
                f"Innerhalb davon ist ein Unterschied Messrauschen und keine "
                f"Aussage — erst ausserhalb lohnt eine Reaktion. "
                f"Rot unter {grenzen.get('rot_unter')} ms."
            )
    for h in hrv_list:
        status = h.get("hrv_status")
        symbol = AMPEL_SYMBOL.get(status, "·")
        zusatz = ""
        if grenzen and grenzen.get("gruen_bis") and h.get("rmssd", 0) > grenzen["gruen_bis"]:
            zusatz = " — über der Normalspanne"
        lines.append(
            f"- {h['measured_at']}: {h['rmssd']}ms rMSSD {symbol}"
            f"{f' ({status})' if status else ' (noch keine Grundlinie)'}{zusatz}"
        )
    return "\n".join(lines)


TARGETS_FORMAT = """### targets — numerische Zielwerte (PFLICHT für jede Trainingseinheit)

Jede Einheit braucht neben `details` (Beschreibung für den Athleten) ein
`targets`-Objekt mit **Zahlen**. Daran wird später automatisch gemessen, ob die
tatsächlich gefahrene/gelaufene Einheit dem Plan entsprach.

```json
{
  "tss": 145,
  "watts_low": 210, "watts_high": 220,
  "pace_low_s_per_km": 360, "pace_high_s_per_km": 410,
  "hr_zone": "Z2",
  "distance_km": 100
}
```

Regeln:
- **Rad:** immer `watts_low`/`watts_high` (Hauptteil, nicht Warmup) + `tss`
- **Lauf:** immer `pace_low_s_per_km`/`pace_high_s_per_km` in **Sekunden/km**
  (6:00/km = 360, 6:50/km = 410) + `hr_zone`
- **Schwimmen:** `distance_km` falls bekannt
- **Gym / Rest:** `targets` weglassen
- Nur angeben, was du wirklich vorgibst — eine erfundene Zahl ist schlechter
  als ein fehlendes Feld.

### training_type — Trainingstyp (PFLICHT, kontrolliertes Vokabular)

Zusätzlich zu `session_type` (Sportart) braucht jeder Tag einen `training_type`
aus genau dieser Liste:

<<TYPENTABELLE>>

Keine eigenen Werte erfinden — der Typ wird 1:1 gegen die Ist-Daten abgeglichen.

### Intensitätsstufen (Rad und Lauf)

Aus dem Trainingstyp folgt automatisch die Intensitätsstufe. Plane bewusst
entlang dieser vier Stufen und halte die Z2-Dominanz ein:

| Stufe | Zone | Trainingstypen |
|-------|------|----------------|
| Base / Endurance | Z1–Z2 | recovery, z2_endurance, long_ride, walk_run, long_run, brick_run |
| Sweet Spot | Z3 | sweet_spot, race_pace, tempo |
| Threshold | Z4 | threshold |
| VO₂max | Z5–Z7 | vo2max, intervals |

Für Läufe gelten dieselben Stufen wie fürs Rad: eine Bahneinheit mit
1km-Intervallen ist `vo2max`, kein `intervals`-Sammelbegriff, wenn sie
tatsächlich in Z5 oder höher führt. Schwimmen bleibt außen vor — dafür gibt es
einen eigenen Plan.

**Die drei schnellen Laufbereiche sind nicht dasselbe.** Z5 ist 5-Kilometer-
Tempo, Z6 ist vVO2max (die Geschwindigkeit, bei der VO2max erreicht wird), Z7
sind Steigerungen.

- **VO2max-Intervalle über drei bis vier Minuten gehören in Z5**, nicht in Z6:
  Sie werden bei etwa 95 % von vVO2max gelaufen. Das ist die Einheit mit dem
  stärksten Beleg (4×4 min, +8,1 % VO2max).
- **Z6 ist vVO2max selbst** und nur für kurze Wiederholungen gedacht
  (15 s / 15 s), als Abwechslung und mit kleinem Geschwindigkeitsunterschied
  zwischen schnell und locker. Vier Minuten in Z6 hält niemand durch.
- **Z7 ist keine Belastungseinheit**, sondern Technik: 15–20 Sekunden locker
  schnell, volle Erholung.

Beurteile nach Pace, nicht nach Puls: der Puls hinkt bei kurzen Intervallen
hinterher, und in einem Vergleich zeigte er sogar das Gegenteil des
tatsächlichen Reizes.
"""

# Die Typentabelle wird eingesetzt statt abgeschrieben. Kein f-String, weil der
# Block JSON-Beispiele mit geschweiften Klammern enthält.
TARGETS_FORMAT = TARGETS_FORMAT.replace(
    "<<TYPENTABELLE>>", planbare_typen_tabelle()
)

DETAILS_FORMAT = """### details-Format:

**bike:** (`workout` NICHT selbst füllen — siehe unten)
```json
{
  "warmup": {"dauer": "10 min", "watt": "100-140 W", "rpm": "70-75"},
  "blocks": [
    {"block": "1", "watt": "145-155 W", "rpm": "76-80", "dauer": "14 min", "zone": "Z2"},
    {"block": "Erholung", "watt": "115 W", "rpm": "locker", "dauer": "2 min", "zone": "Z1"},
    {"block": "2", "watt": "145-155 W", "rpm": "76-80", "dauer": "14 min", "zone": "Z2"}
  ],
  "cooldown": {"dauer": "8 min", "watt": "140-100 W", "rpm": "85-90"}
}
```

Das Feld `workout` bleibt weg. Welches Zwift-Workout der geplanten Struktur
entspricht, trägt die App hinterher selbst ein — sie vergleicht die Blöcke mit
ihrem Katalog und schreibt den Namen nur bei eindeutiger Übereinstimmung. Einen
Namen zu erfinden hieße, dem Athleten eine Einheit zu nennen, die er im Trainer
nicht findet.

**WICHTIG bei Rad-Einheiten:** `warmup` und `cooldown` sind Objekte mit
**konkretem Wattbereich**, keine Sätze. "10 min locker ausfahren" enthält
keine Zahl und lässt sich später nicht gegen die tatsächlich gefahrene
Leistung stellen — in der Auswertung bleibt dort sonst eine Lücke. Dasselbe
gilt für Erholungsblöcke: jeder Block braucht `watt`.

**run (Intervalle):** — gleiche Blockstruktur wie beim Rad, nur mit `pace`

Die Werte hier sind **Platzhalter für die Form**, keine Vorgabe. Setze die
Bereiche dieses Athleten ein, aus "Trainingsbereiche" und den HR-Zonen oben.
Hier standen echte Zahlen eines einzelnen Athleten — und sie wurden wörtlich
in die Pläne aller anderen übernommen.

```json
{
  "typ": "Intervalle",
  "struktur": "4×2km + Pause",
  "warmup": {"dauer": "1 km", "pace": "<Z1-Pace>/km"},
  "blocks": [
    {"block": "1", "pace": "<Z2-Pace>/km", "dauer": "2 km", "zone": "Z2"},
    {"block": "Trabpause", "pace": "<Z1-Pace>/km", "dauer": "90 sec", "zone": "Z1"},
    {"block": "2", "pace": "<Z2-Pace>/km", "dauer": "2 km", "zone": "Z2"}
  ],
  "cooldown": {"dauer": "1 km", "pace": "<Z1-Pace>/km"},
  "ziel_hr": "<Z2-Bereich des Athleten> bpm",
  "distanz_richtwert": "~8-10km"
}
```

**Auch beim Laufen gilt:** Trabpausen und Gehpausen brauchen eine **eigene
Pace-Vorgabe** als Block. "2min Trabpause" allein enthält keine Zahl und
lässt sich später nicht bewerten — die Pause bleibt in der Auswertung leer,
obwohl sie Teil der Einheit ist.

**WICHTIG zur Lauf-Pace:**
- Die Bereiche stehen im Abschnitt "Trainingsbereiche", abgeleitet aus der
  **gemessenen Schwellenpace** dieses Athleten. Nimm sie von dort.
- Fehlt dort eine Schwellenpace, ist keine gemessen. Dann nach Puls planen und
  **keine Pace erfinden** — eine geratene Zahl sieht in der Auswertung aus wie
  eine gemessene.
- Hier standen feste Pacebereiche eines einzelnen Athleten. Jeder andere bekam
  damit dessen Tempo vorgeschrieben.

**run (Dauerlauf):**
```json
{
  "typ": "Dauerlauf Z2",
  "dauer": "30 min",
  "pace": "nach Gefühl",
  "ziel_hr": "<Z2-Bereich des Athleten> bpm"
}
```

**brick:**
```json
{
  "bike": {...},
  "transition": "Schneller Wechsel",
  "run": {...kürzer als standalone...}
}
```

**swim (Becken) / gym:** `{}` (leer, nur duration_min + notes) — bei gym nennt
`notes` keine Übungen und keine Muskelgruppen, beim Schwimmen keine Serien und
keine Technikübungen (der Inhalt kommt aus einem externen Trainingsplan)

**swim mit training_type `open_water`:** `{"struktur": "10 min einschwimmen · 20 min GA · 10 min zügig · 5 min ausschwimmen", "ziel_hr": "Z2"}`
— die einzige Schwimmeinheit mit Inhalt, weil es für Freiwasser keinen
externen Plan gibt. Gliederung nach Dauer und Intensität, keine Serien.
"""


def build_plan_prompt(
    athlete_profile: dict,
    sessions: list,
    hrv: list,
    week: int,
    requests: str = "",
    plan_start: date = date(2025, 12, 22),
    sessions_text: str | None = None,
    reflections: str = "",
    total_weeks: int = 33,
    constraints: str | None = None,
    health: str | None = None,
    races: str | None = None,
    offseason: str | None = None,
    season_history: str | None = None,
    zones: str | None = None,
    quality: str | None = None,
    base_period: str | None = None,
    # Die Normalspanne der HRV. Nicht hier berechnet, weil dieses Modul keine
    # Datenbank kennt — der Aufrufer hat sie ohnehin zur Hand.
    hrv_grenzen: dict | None = None,
    # Wie die Vorwoche tatsächlich aussah: Anzahl harter Einheiten und ihr
    # Abstand. Berichtend, nicht ablehnend — siehe `services/week_shape.py`.
    wochenform: str | None = None,
) -> str:
    from core.race_types import phase_boundaries

    phase = get_phase(week, total_weeks)

    # Saisonstruktur aus der Zieldauer statt als feste 33-Wochen-Tabelle.
    # Die Deload-Spalte kommt aus derselben Funktion, die auch die aktuelle
    # Woche beurteilt — sonst laufen Tabelle und Vorgabe auseinander, was sie
    # jahrelang taten.
    rows = [
        f"| {name} | W{start}–{end} | "
        f"{'Deload W' + str(end) if is_deload(end, total_weeks) else '–'} |"
        for name, start, end in phase_boundaries(total_weeks)
    ]
    season_structure = "\n".join(
        [f"## Saisonstruktur ({total_weeks} Wochen)", "| Phase | Wochen | Deload |", "|---|---|---|"]
        + rows
    )

    # Individuelle Einschränkungen des Athleten. Was hier steht, kommt aus
    # seinem Profil — nicht aus fest verdrahteten Annahmen über jemand anderen.
    constraints_block = ""
    if constraints:
        constraints_block = (
            "## INDIVIDUELLE REGELN (KRITISCH — bei JEDEM Plan beachten)\n\n"
            f"{constraints}\n\n---"
        )
    # Gesundheit steht vor den individuellen Regeln: was hier steht, hebt
    # Phasenvorgabe und Progression auf.
    health_block = health or ""
    # Wettkämpfe unterwegs: sie ändern die Phase nicht, wohl aber die Woche,
    # in die sie fallen.
    races_block = races or ""
    # Off Season: ersetzt die Phasenvorgabe, deshalb steht sie ganz oben.
    offseason_block = offseason or ""
    # Grundlagenphase: das Gegenstück auf der anderen Seite der Saison — das
    # Ziel steht, der Aufbau beginnt erst. Ersetzt die Phasenvorgabe ebenso.
    base_block = base_period or ""
    # Solange der Aufbau nicht läuft, gibt es keine Aufbauphase. "Base 1"
    # wäre eine Vorgabe aus einem Zeitplan, der noch nicht begonnen hat.
    if base_block:
        phase = "Grundlage"
    # Dasselbe auf der anderen Seite der Saison. Ohne diese Zeile stand im
    # Prompt eine Aufbauphase ("Base 3"), während der Off-Season-Block direkt
    # darüber Formerhalt verlangte und die Datenbank "Off Season · Formerhalt"
    # speicherte — drei Angaben, zwei davon falsch. Die Off-Season-Logik selbst
    # bleibt unberührt; hier wird nur ihr Name übernommen.
    elif offseason_block:
        phase = "Off Season"
    # Der Langzeitverlauf steht vor den 14 Tagen im Detail: erst wohin die
    # Saison läuft, dann was zuletzt passiert ist. Umgekehrt liest sich das
    # Fenster als Gesamtbild — und genau der Trugschluss soll hier weg.
    history_block = season_history or ""
    # Die gemessenen Schwellen und die daraus abgeleiteten Bereiche. Vorher
    # kannte der Prompt nur FTP und Maximalpuls — ein gemessener Schwellenlauf
    # blieb folgenlos, und Laufeinheiten hatten keine Paceangabe.
    zones_block = zones or ""
    # Auffällige Einheiten samt Reflexion. Sie stehen direkt vor den 14 Tagen:
    # erst was bemerkenswert war und warum, dann die vollständige Liste.
    quality_block = quality or ""

    # Über den ganzen übergebenen Zeitraum, nicht über drei Tage: Richtung und
    # Streuung lassen sich aus drei Werten kaum beurteilen, und der Aufrufer
    # übergibt ohnehin nur die letzte Woche.
    hrv_status = analyze_hrv_trend(hrv or [], hrv_grenzen)
    # Bevorzugt der ausführliche Kontext aus den Obsidian-Notes; ohne ihn
    # die kompakte Zusammenfassung aus der Datenbank.
    session_summary = sessions_text or format_sessions(sessions)

    # Subjektives strikt getrennt ausweisen: eine Selbsteinschätzung darf
    # nicht als gemessener Wert behandelt werden.
    reflections_block = ""
    if reflections:
        reflections_block = (
            "\n## Reflexionen des Athleten (subjektiv, selbst notiert)\n"
            "Diese Notizen stammen vom Athleten selbst, nicht aus Messdaten. "
            "Nutze sie zur Einordnung — behandle sie nicht als gemessene Werte.\n\n"
            f"{reflections}\n"
        )
    hrv_text = format_hrv(hrv, hrv_grenzen)
    week_start, week_end = get_week_dates(week, plan_start)
    # Eine Quelle für den Deload — dieselbe, aus der die Saisonübersicht
    # weiter unten gebaut wird. Vorher stand hier `week % 4 == 0`, was in
    # jedem Plan mit durch vier teilbarer Länge die Wettkampfwoche als
    # Entlastungswoche auswies.
    deload = is_deload(week, total_weeks)

    # Die Phasenvorgabe ersetzt die eine alte Wochenvorlage, die nur für
    # „Build 2" existierte und nur das Rad kannte. In Grundlage und Off Season
    # bleibt sie leer — dort gilt der eigene Block, und zwei Quellen für
    # dieselbe Vorgabe wären der nächste Widerspruch.
    from core.phasenregeln import prompt_block as phasen_prompt
    phasen_block = "" if (base_block or offseason_block) else phasen_prompt(phase, deload)
    wochenform_block = wochenform or ""
    day_names = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
    week_days = [(day_names[i], str(week_start + timedelta(days=i))) for i in range(7)]
    week_days_str = "\n".join(f"- {name}: {d}" for name, d in week_days)

    # Schwimm-Orientierungswerte als fertiger Text. Fehlt einer, steht dort
    # "unbekannt" — dann darf der Coach ihn weglassen statt einen Wert zu
    # erfinden, den der Athlet für gemessen halten würde.
    css_s = athlete_profile.get("css_pace_s_per_100m")
    css_text = f"{int(css_s) // 60}:{int(css_s) % 60:02d}/100m" if css_s else "unbekannt"
    swim_hr = athlete_profile.get("swim_threshold_hr")
    swim_hr_text = f"{swim_hr} bpm" if swim_hr else "unbekannt"

    return f"""## Athletenprofil
- Name: {athlete_profile.get('name') or 'Athlet'}
- Ziel: {athlete_profile.get('race_name') or athlete_profile.get('goal_label') or 'Triathlon'} am {athlete_profile['race_date']}{f" — {athlete_profile.get('goal_label')}" if athlete_profile.get('race_name') and athlete_profile.get('goal_label') else ''}
- Zielzeit: {athlete_profile.get('goal_time') or athlete_profile.get('race_goal') or 'keine angegeben'}
- Vorbereitung: {"Off Season — kein laufendes Saisonziel" if offseason_block else "Grundlagenphase — der Aufbau hat noch nicht begonnen" if base_block else f"Woche {week} von {athlete_profile.get('total_weeks', 33)}"}
- FTP: {athlete_profile['ftp_watts']}W
- Max HR: {athlete_profile['max_hr']} bpm
- HR-Zonen: Z1 0-{athlete_profile['z1_hr_max']} | Z2 {athlete_profile['z2_hr_min']}-{athlete_profile['z2_hr_max']} | Z3 {athlete_profile['z3_hr_min']}-{athlete_profile['z3_hr_max']} | Z4 {athlete_profile['z4_hr_min']}-{athlete_profile['z4_hr_max']} | Z5 >{athlete_profile['max_hr']}
- Schwimmen: CSS {css_text} | Schwellenpuls {swim_hr_text}
- Equipment: Wahoo KICKR Core, Zwift, Garmin Forerunner 255, Wahoo Elemnt Bolt v2

{offseason_block}
{base_block}
{health_block}
{races_block}
{constraints_block}

## BRICK-SESSIONS

### REGELN
- Nur **Bike → Run** (Swim → Bike erst ab der Peak-Phase)
- Laufanteil durchgehend, **es sei denn**, die Athletenvorgaben oder der
  Gesundheitsabschnitt verlangen Gehpausen — oder der Athlet hat darum gebeten
- IMMER kürzer als Standalone-Lauf der gleichen Woche
- KEINE Strides in Brick-Läufen
- Ziel: Umgewöhnung der Beine, NICHT Pace
- Tag nach Brick = Rest, Schwimmen oder Rad — KEIN Standalone-Lauf

### BRICK-PROGRESSION
Nach Phase, nicht nach Wochennummer: In einem Plan unter sechzehn Wochen heißen
die Phasen „Base", „Build" und „Peak" ohne Blocknummer, und eine auf „Base 3"
geschlüsselte Zeile griff dort gar nicht.

| Phase | Bike | Run |
|-------|------|-----|
| Base (späterer Teil) | 50–60min Z2 | 3×5min jog + 2min walk |
| Build (erste Hälfte) | 60–75min Z2 + Sweet Spot | 3–4×800m–1km jog + 2min walk |
| Build (letzter Block) | 75–90min mit Threshold-Block | 4×1km jog + 90sec walk |
| Peak | Race-Simulation | 15–20min kontinuierlich (NUR wenn 4 Wochen schmerzfrei) |

---

## RAD-LOGIK

- **Sessions/Woche dynamisch 2–3**, je nach Phase und HRV
- **Ab Build (zweiter Block): Threshold UND VO2max erlaubt**
- **Sweet Spot bleibt Brot-und-Butter** in allen Build-Phasen
- **Rad ist die Hauptbelastungs-Quelle** — hier darf Volumen und Intensität hoch sein
- Die Zahl der harten Einheiten gibt die Phasentabelle vor, nicht diese Zeile

### SESSION-SKALIERUNG NACH HRV
Maßgeblich ist die **Normalspanne dieses Athleten** (sie steht oben bei den
HRV-Daten), nicht ein absoluter Millisekundenwert. Hier standen die Zahlen eines
einzelnen Athleten; bei einer Normallage um 45 ms hätte diese Tabelle dauerhaft
Ruhetage verordnet.

| HRV-Status | Anpassung |
|------------|-----------|
| 🟢 in der Spanne oder darüber | Plan wie vorgesehen, bis 2 Intensitätseinheiten |
| 🟡 unter der Spanne, über der roten Grenze | max. 1 Intensität (Threshold streichen, Sweet Spot bleibt) |
| 🔴 unter der roten Grenze | nur Z2 oder Ruhetag, Volumen −30 % |
| fallender Trend über drei Tage | eine Einheit streichen, auch wenn die Ampel grün ist |

Ein Wert **über** der Spanne ist nicht besser als grün, er ist grün — nur eben
belegt. Er ist kein Grund, zusätzlich zu belasten.

{phasen_block}
{wochenform_block}
## Aktuelle Position
- Aktuelle Woche: {"Off Season, " + str(week - total_weeks) + ". Woche nach dem Saisonziel" if offseason_block else "Grundlagenphase — zählt nicht als Vorbereitungswoche" if base_block else f"{week}/{total_weeks}"}
- Phase: {phase}
- Zeitraum: {week_start} bis {week_end}
- Tages-Daten (EXAKT verwenden, nicht selbst berechnen):
{week_days_str}
 
{zones_block}
{history_block}
{quality_block}
## Trainingsdaten letzte 7-14 Tage (gemessen)
{session_summary}
{reflections_block}
## HRV-Daten (Nacht-Messung)
{hrv_text}
**Richtung und Streuung:** {hrv_status}

## HR-Modifikatoren
- Kühlung (Ventilator + kühle Luft): senkt HR ~8-12 bpm
- Volle Glykogenspeicher (Carbs): senkt HR ~3-5 bpm

## Rad-Vorgaben in Watt
Skaliere alle Prozentangaben auf absolute Watt: FTP = {athlete_profile['ftp_watts']}W.
Beispiel: 88 % FTP = {int(athlete_profile['ftp_watts'] * 0.88)}W, 95 % FTP = {int(athlete_profile['ftp_watts'] * 0.95)}W.

**Intensitätsregel nach HRV:**
- 🟢 grün: Prozentwerte wie in der Formattabelle dieser Phase
- 🟡 gelb: alle Prozentwerte um 3–5 % reduzieren
- 🔴 rot: nur Endurance, kein Sweet Spot, keine Schwelle, kein VO2max

Baue die Struktur aus der Formattabelle dieser Phase (weiter oben) und rechne
ihre Prozentwerte in Watt um. Einen passenden Zwift-Namen trägt die App
hinterher selbst ein — such keinen aus und erfinde keinen.

{season_structure}
 
 
## Besondere Wünsche
{requests if requests else "Keine."}
 
---
 
## TRAININGSREGELN (WICHTIG!)
 
### Rad
- **Kadenz:** 75-85 rpm (natürlich), NICHT höher!
- **Warm-up/Cool-down:** 70-75 rpm
- **Z2-Blöcke:** 76-82 rpm
- **Z1-Erholungen:** 1-3 min @ 115-130W zwischen Z2-Blöcken (locker treten)
- **1× Feel Ride/Woche:** Kadenz komplett frei, nur Watt vorgegeben
- **Zwift ERG-Modus** kompatibel
 
### Lauf
- **Brick-Läufe:** Kürzer und konservativer als Standalone
- **HR-Ziel:** Z2 — die Grenzen stehen oben im Athletenprofil
- **Gehpausen** sind ein Werkzeug, keine Grundeinstellung: Sie kommen in den
  Plan, wenn die Athletenvorgaben oder der Gesundheitsabschnitt sie verlangen,
  oder wenn der Athlet danach fragt. Hier standen sie als Vorgabe für die
  Grundlagenphase, dazu die Pulsgrenzen eines einzelnen Athleten — beides
  bekam jeder andere mit.
 
### Schwimmen
Der Athlet schwimmt nach einem **externen Trainingsplan** — aus dem Verein,
einer App oder von einem Schwimmtrainer. Dieser Plan kennt Becken, Gruppe und
Technikstand; du kennst sie nicht. Eine Serie vorzugeben, die neben dem
externen Plan steht, hieße zwei Pläne gegeneinander laufen zu lassen.

- 2×/Woche, **nur Termin und Dauer**. `training_type` immer `endurance`.
- **Kein Inhalt.** Keine Serien, keine Strecken, keine Technikübungen, keine
  Intervallvorgaben — auch nicht in `notes`. `details` bleibt `{{}}`.
- `notes` sagt, dass Schwimmen ansteht, und nennt die Orientierungswerte:
  CSS und Schwellenpuls. Mehr nicht. Beispiel:
  "Schwimmen nach deinem externen Plan. Orientierung: CSS {css_text}, Schwellenpuls {swim_hr_text}."
- Fehlt ein Wert, lass ihn weg statt zu raten.
- **Kein Progressionsziel.** Steigere die Schwimmdauer nicht von Woche zu
  Woche und leite aus vergangenen Schwimmeinheiten keine Vorgabe ab — der
  Aufbau steckt im externen Plan.

### Freiwasser (ab Peak)
Ab der **Peak-Phase** ersetzt eine der beiden Schwimmeinheiten das Becken
durch Freiwasser. Dafür gibt es keinen externen Plan, also planst du sie
selbst — hier ist Struktur ausdrücklich erwünscht.

- `training_type` `open_water`, `details` mit Dauer und Grobgliederung.
- Gegliedert nach Dauer und Intensität, z.B. "10 min einschwimmen · 20 min GA
  · 10 min zügig · 5 min ausschwimmen". Länge an der Wettkampfdistanz
  orientiert, im Peak bis zur Renndistanz aufgebaut.
- **Keine Technikübungen und keine Serien.** Ohne Bahn, Wand und Uhr am
  Beckenrand ist beides im Freiwasser nicht durchführbar.
- Wettkampfnahe Punkte gehören hierher: Neopren, Sichten/Orientieren,
  Massenstart, Beschleunigung auf den ersten Metern.
- Im Taper bleibt Freiwasser, aber kurz und ohne harte Anteile.
 
### Ersatztraining (session_type `other`)
- Für Ausdauer ohne die eigentliche Disziplin: StairMaster, Crosstrainer,
  Ruderergometer, Aquajogging, Radfahren als Laufersatz.
- Nur einsetzen, wenn ein Grund vorliegt — Verletzung, Ausfall der Anlage,
  Wetter. Im Normalbetrieb wird die Disziplin selbst trainiert.
- `details` nennt das Gerät und die Zone, `targets` nur `hr_zone`.
  Watt- und Pacevorgaben gibt es hier nicht: die Geräte messen anders und
  sind untereinander nicht vergleichbar.

### Gym
- Häufigkeit: in Grundlage und Off Season **zweimal** pro Woche, ab der
  Aufbauphase **einmal**, in Taper und Wettkampfwoche nichts Schweres. Steht
  oben eine Phasenvorgabe, gilt deren Angabe.
- **NUR Termin und Dauer.** Keine Übungen, keine Muskelgruppen, keine Sätze
  oder Wiederholungen — auch nicht in `notes`. Der Athlet gestaltet den Inhalt
  selbst; eine Vorgabe ohne Kenntnis von Ausrüstung und Technikstand wäre
  geraten. Zulässig ist höchstens ein Hinweis zur Einordnung in die Woche
  (etwa "Beine frisch halten für morgen").
- **Abstand zur Ausdauereinheit: mindestens 3 Stunden.** Lässt sich das an
  einem Tag nicht einrichten, kommt Kraft **zuerst** und die Ausdauereinheit
  danach — in der umgekehrten Reihenfolge fällt der Kraftreiz weg.
- Kraft ist **nicht** das Erste, was bei einer Umfangskürzung gestrichen wird.
  Sie senkt das Verletzungsrisiko auf etwa ein Drittel und ist damit die
  wirksamste einzelne Maßnahme im ganzen Plan. Wenn eine Woche kürzer wird,
  kürze Ausdauerumfang, nicht die Krafteinheit.
 
### Zielzeit
- Ist eine Zielzeit angegeben, ergibt sich daraus das Renntempo. Einheiten im
  Wettkampftempo orientieren sich daran, nicht an einem allgemeinen Richtwert.
- Prüfe die Zielzeit gegen die gemessenen Werte (FTP, Schwellenpace, CSS).
  Trägt sie nicht, sag das im `coaching_comment` klar und benenne, was dafür
  fehlt — eine stillschweigend zu hoch angesetzte Vorgabe führt zu Einheiten,
  die der Athlet nicht durchhält.
- Ohne Zielzeit wird nach Zonen geplant. Erfinde keine.

### Z2-Dominanz
- Mind. 80% Volumen in Z2
- Sweet Spot/Tempo/VO₂max ZUSÄTZLICH zu Z2, ersetzt es nicht
 
---
 
## Aufgabe

Erstelle den Plan für **Woche {week}** ({week_start} – {week_end}).

{'🔄 DELOAD-WOCHE: Volumen -40-50%, keine neue Intensität!' if deload else ''}

**Antworte NUR mit JSON:**

```json
{{
  "week": {week},
  "phase": "{phase}",
  "week_start": "{week_start}",
  "week_end": "{week_end}",
  "coaching_comment": "3-4 Sätze: Was war gut, HRV-Interpretation, Fokus diese Woche",
  "adjustments": ["Anpassung 1 basierend auf Daten", "Anpassung 2"],
  "days": [
    {{
      "day": "Montag",
      "date": "YYYY-MM-DD",
      "session_type": "rest|bike|run|swim|gym|brick",
      "training_type": "z2_endurance",
      "duration_min": 60,
      "targets": {{"tss": 60, "watts_low": 145, "watts_high": 155, "hr_zone": "Z2"}},
      "details": {{}},
      "notes": "..."
    }}
  ]
}}
```

{TARGETS_FORMAT}

{DETAILS_FORMAT}"""
 