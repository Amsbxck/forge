from datetime import date, timedelta
from core.zwift_catalog import get_phase_workouts


# Amirs bisheriges Schienbein-Protokoll. Steht ab sofort in seinem
# Profil (coaching_constraints) statt fest im Prompt — andere Athleten
# bekommen Regeln, die auf ihre eigene Vorgeschichte zugeschnitten sind.
DEFAULT_RUN_CONSTRAINTS = """## SCHIENBEIN-PROTOKOLL (KRITISCH — bei JEDEM Plan beachten)

**Status:** Stabil, aktuell kein Schmerz, aber Zwicken/Spannungen bei höherer Pace möglich.
Die Schienbeine adaptieren sich progressiv an neue Belastungen — sie brauchen kontrollierte Reize um stärker zu werden.

### LAUF-FORMAT (Standard)
- **Walk-Run Intervalle** sind die Basis: X km joggen + 90sec–2min gehen, wiederholen
- **Aktuelle Kapazität:** aus den Trainingsdaten der letzten 2 Wochen ableiten
- **Progression:** Intervall-Distanz erhöhen ODER Gehpause verkürzen — NIE beides gleichzeitig
- **Steigerung NUR wenn:** Vorwoche war 🟢 (kein Zwicken erwähnt)

### STRIDES (erlaubt!)
- **Was:** 4–6× 15–20 Sekunden schnell laufen + 60–90 Sekunden gehen
- **Wann:** Am ENDE eines Laufs (aufgewärmt)
- **Frequenz:** Max 1× pro Woche, nicht jede Session
- **Warum:** Progressive Adaptation der Schienbeine an höhere Pace
- **NICHT in Brick-Sessions!**

### LAUF-TYPEN
| Typ | Format | Wann |
|-----|--------|------|
| Walk-Run Intervalle | 4–5× 2–2.5km jog + 90sec–2min gehen | Standard, 1–2×/Woche |
| Walk-Run + Strides | Intervalle + 4–6× 20sec schnell am Ende | Max 1×/Woche |
| Brick-Lauf | 3–4× 800m–1km jog + 2min gehen | Nach Rad, 1×/Woche |

### LAUF-AMPEL (für Feedback-Interpretation aus letzten Sessions)
| Gefühl | Bedeutung | Nächste Woche |
|--------|-----------|---------------|
| 🟢 Nichts spürbar | Voll adaptiert | Progression möglich |
| 🟡 Zwicken bei neuer Pace | Adaptation läuft | Level halten, Strides OK |
| 🟠 Zwicken bei alter Pace | Überlastung beginnt | −20% Volumen, keine Strides |
| 🔴 Schmerz >3/10 | Stopp! | Session abbrechen, Woche pausieren |

### LAUF — VERBOTEN
- Hill Sprints, Bergläufe
- Track-Intervalle (400m Repeats mit kurzer Pause)
- Läufe >12km in einer Session
- Strides in Brick-Sessions
- Standalone-Lauf am Tag NACH einem Brick (Brick enthält bereits Lauf)
- Dauerlauf ohne Gehpausen (noch nicht stabil genug)

---"""


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


def analyze_hrv_trend(hrv_list: list) -> str:
    if not hrv_list:
        return "Keine HRV-Daten vorhanden"
    avg = sum(h["rmssd"] for h in hrv_list) / len(hrv_list)
    if avg > 80:
        return f"Grün ({avg:.0f}ms avg) — normale Einheit wie geplant"
    elif avg >= 70:
        return f"Gelb ({avg:.0f}ms avg) — machbar, aber nicht zu intensiv"
    else:
        return f"Rot ({avg:.0f}ms avg) — Intensität reduzieren oder Rest"


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
        if s.get("structure"):
            line += f"\n    {s['structure']}"
        if s.get("deviation_note"):
            line += f"\n    → {s['deviation_note']}"
        lines.append(line)
    return "\n".join(lines)


def format_hrv(hrv_list: list) -> str:
    if not hrv_list:
        return "Keine HRV-Daten."
    lines = []
    for h in hrv_list:
        status_icon = "🟢" if h["rmssd"] > 85 else ("🟡" if h["rmssd"] >= 75 else "🔴")
        lines.append(f"- {h['measured_at']}: {h['rmssd']}ms rMSSD {status_icon} ({h.get('hrv_status', '')})")
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

| Sportart | erlaubte training_type |
|----------|------------------------|
| bike | recovery, z2_endurance, sweet_spot, threshold, vo2max, race_pace, long_ride |
| run | recovery, walk_run, z2_endurance, tempo, intervals, threshold, vo2max, brick_run, long_run |
| swim | technique, endurance, intervals, open_water |
| gym | strength, mobility |
| brick | brick |
| other | cross_training |
| rest | rest |

Keine eigenen Werte erfinden — der Typ wird 1:1 gegen die Ist-Daten abgeglichen.

### Intensitätsstufen (Rad und Lauf)

Aus dem Trainingstyp folgt automatisch die Intensitätsstufe. Plane bewusst
entlang dieser vier Stufen und halte die Z2-Dominanz ein:

| Stufe | Zone | Trainingstypen |
|-------|------|----------------|
| Base / Endurance | Z1–Z2 | recovery, z2_endurance, long_ride, walk_run, long_run, brick_run |
| Sweet Spot | Z3 | sweet_spot, race_pace, tempo |
| Threshold | Z4 | threshold |
| VO₂max | Z5 | vo2max, intervals |

Für Läufe gelten dieselben Stufen wie fürs Rad: eine Bahneinheit mit
1km-Intervallen ist `vo2max`, kein `intervals`-Sammelbegriff, wenn sie
tatsächlich in Z5 führt. Schwimmen bleibt außen vor — dafür gibt es einen
eigenen Plan.
"""

DETAILS_FORMAT = """### details-Format:

**bike:** (Zwift-Workout-Name in "workout" angeben)
```json
{
  "workout": "Name aus der Bibliothek (z.B. Tempo #1)",
  "warmup": {"dauer": "10 min", "watt": "100-140 W", "rpm": "70-75"},
  "blocks": [
    {"block": "1", "watt": "145-155 W", "rpm": "76-80", "dauer": "14 min", "zone": "Z2"},
    {"block": "Erholung", "watt": "115 W", "rpm": "locker", "dauer": "2 min", "zone": "Z1"},
    {"block": "2", "watt": "145-155 W", "rpm": "76-80", "dauer": "14 min", "zone": "Z2"}
  ],
  "cooldown": {"dauer": "8 min", "watt": "140-100 W", "rpm": "85-90"}
}
```

**WICHTIG bei Rad-Einheiten:** `warmup` und `cooldown` sind Objekte mit
**konkretem Wattbereich**, keine Sätze. "10 min locker ausfahren" enthält
keine Zahl und lässt sich später nicht gegen die tatsächlich gefahrene
Leistung stellen — in der Auswertung bleibt dort sonst eine Lücke. Dasselbe
gilt für Erholungsblöcke: jeder Block braucht `watt`.

**run (Intervalle):** — gleiche Blockstruktur wie beim Rad, nur mit `pace`
```json
{
  "typ": "Walk-Run Intervalle",
  "struktur": "4×2km joggen + 90sec-2min gehen",
  "warmup": {"dauer": "1 km", "pace": "6:30-7:00/km"},
  "blocks": [
    {"block": "1", "pace": "6:00-6:50/km", "dauer": "2 km", "zone": "Z2"},
    {"block": "Trabpause", "pace": "8:00-9:00/km", "dauer": "90 sec", "zone": "Z1"},
    {"block": "2", "pace": "6:00-6:50/km", "dauer": "2 km", "zone": "Z2"}
  ],
  "cooldown": {"dauer": "1 km", "pace": "6:30-7:00/km"},
  "ziel_hr": "139-173 bpm",
  "distanz_richtwert": "~8-10km"
}
```

**Auch beim Laufen gilt:** Trabpausen und Gehpausen brauchen eine **eigene
Pace-Vorgabe** als Block. "2min Trabpause" allein enthält keine Zahl und
lässt sich später nicht bewerten — die Pause bleibt in der Auswertung leer,
obwohl sie Teil der Einheit ist.

**WICHTIG zur Lauf-Pace:**
- Amir laeuft seine Walk-Run Intervalle aktuell in **6:00-6:50/km** (nicht mehr 7:00-7:30)
- Bei gutem Gefuehl koennen einzelne Intervalle in **5:30-6:00/km** gelaufen werden
- Plane Pace-Bereich entsprechend, nicht zu konservativ
- 5:xx-Pace nur als optionale "wenn Gefuehl gut"-Erlaubnis, nicht als Vorgabe

**run (Dauerlauf):**
```json
{
  "typ": "Dauerlauf Z2",
  "dauer": "30 min",
  "pace": "nach Gefühl",
  "ziel_hr": "139-173 bpm"
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

**swim / gym:** `{}` (leer, nur duration_min + notes) — bei gym nennt `notes`
keine Übungen und keine Muskelgruppen
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
) -> str:
    from core.race_types import phase_boundaries

    phase = get_phase(week, total_weeks)

    # Saisonstruktur aus der Zieldauer statt als feste 33-Wochen-Tabelle.
    # Deload jeweils in der letzten Woche einer Phase.
    rows = [
        f"| {name} | W{start}–{end} | {'Deload W' + str(end) if end - start >= 3 else '–'} |"
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

    hrv_status = analyze_hrv_trend(hrv[-3:] if hrv else [])
    # Bevorzugt der ausführliche Kontext aus den Obsidian-Notes; ohne ihn
    # die kompakte Zusammenfassung aus der Datenbank.
    session_summary = sessions_text or format_sessions(sessions)

    # Subjektives strikt getrennt ausweisen: eine Selbsteinschätzung darf
    # nicht als gemessener Wert behandelt werden.
    reflections_block = ""
    if reflections:
        reflections_block = (
            "\n## Reflexionen des Athleten (subjektiv, selbst notiert)\n"
            "Diese Notizen stammen von Amir selbst, nicht aus Messdaten. "
            "Nutze sie zur Einordnung — behandle sie nicht als gemessene Werte.\n\n"
            f"{reflections}\n"
        )
    hrv_text = format_hrv(hrv)
    week_start, week_end = get_week_dates(week, plan_start)
    is_deload = week % 4 == 0
    phase_workouts_sst = get_phase_workouts(phase, is_deload, "sst_tempo")
    phase_workouts_endurance = get_phase_workouts(phase, is_deload, "endurance")
    phase_workouts_threshold = get_phase_workouts(phase, is_deload, "threshold")
    phase_workouts_vo2max = get_phase_workouts(phase, is_deload, "vo2max")
    day_names = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
    week_days = [(day_names[i], str(week_start + timedelta(days=i))) for i in range(7)]
    week_days_str = "\n".join(f"- {name}: {d}" for name, d in week_days)

    return f"""## Athletenprofil
- Name: {athlete_profile.get('name') or 'Athlet'}
- Ziel: {athlete_profile.get('race_name') or athlete_profile.get('goal_label') or 'Triathlon'} am {athlete_profile['race_date']}{f" — {athlete_profile.get('goal_label')}" if athlete_profile.get('race_name') and athlete_profile.get('goal_label') else ''}
- Zielzeit: {athlete_profile.get('goal_time') or athlete_profile.get('race_goal') or 'keine angegeben'}
- Vorbereitung: {"Off Season — kein laufendes Saisonziel" if offseason_block else "Grundlagenphase — der Aufbau hat noch nicht begonnen" if base_block else f"Woche {week} von {athlete_profile.get('total_weeks', 33)}"}
- FTP: {athlete_profile['ftp_watts']}W
- Max HR: {athlete_profile['max_hr']} bpm
- HR-Zonen: Z1 0-{athlete_profile['z1_hr_max']} | Z2 {athlete_profile['z2_hr_min']}-{athlete_profile['z2_hr_max']} | Z3 {athlete_profile['z3_hr_min']}-{athlete_profile['z3_hr_max']} | Z4 {athlete_profile['z4_hr_min']}-{athlete_profile['z4_hr_max']} | Z5 >{athlete_profile['max_hr']}
- Equipment: Wahoo KICKR Core, Zwift, Garmin Forerunner 255, Wahoo Elemnt Bolt v2

{offseason_block}
{base_block}
{health_block}
{races_block}
{constraints_block}

## BRICK-SESSIONS

### REGELN
- Nur **Bike → Run** (Swim → Bike erst ab Peak Phase W25+)
- **Laufanteil IMMER als Walk-Run Intervalle**, nicht kontinuierlich
- IMMER kürzer als Standalone-Lauf der gleichen Woche
- KEINE Strides in Brick-Läufen
- Ziel: Umgewöhnung der Beine, NICHT Pace
- Tag nach Brick = Rest, Schwimmen oder Rad — KEIN Standalone-Lauf

### BRICK-PROGRESSION
| Phase | Bike | Run |
|-------|------|-----|
| Base 3 | 50–60min Z2 | 3×5min jog + 2min walk |
| Build 1–2 | 60–75min Z2 + Sweet Spot | 3–4×800m–1km jog + 2min walk |
| Build 3 | 75–90min mit Threshold-Block | 4×1km jog + 90sec walk |
| Peak | Race-Simulation | 15–20min kontinuierlich (NUR wenn 4 Wochen schmerzfrei) |

---

## RAD-LOGIK

**Quelle für konkrete Workout-Strukturen ist die Zwift-Bibliothek weiter unten.**
Hier nur die übergeordneten Regeln:

- **Sessions/Woche dynamisch 2–3**, je nach Phase und HRV
- **Ab Build 2: Threshold UND VO2max erlaubt** (nicht erst ab Build 3)
- **Sweet Spot bleibt Brot-und-Butter** in allen Build-Phasen
- **Max 2 Intensitäts-Sessions/Woche** (Rest ist Z2 oder Recovery)
- **Rad ist die Hauptbelastungs-Quelle** — hier darf Volumen und Intensität hoch sein

### SESSION-SKALIERUNG NACH HRV
| HRV Status | Anpassung |
|------------|-----------|
| 🟢 >80ms | Plan wie vorgesehen, 3× Rad mit 2× Intensität OK |
| 🟡 70–80ms | 2–3× Rad, max 1× Intensität (Threshold streichen, Sweet Spot bleibt) |
| 🟠 65–70ms | Nur 2× Rad Z2, keine Intensität |
| 🔴 <65ms | 1× Rad Z2 oder Rest, Volumen −30% |
| ⚠️ Fallend 3+ Tage | Deload-Signale beachten, eine Session streichen |

### TYPISCHE BUILD 2 WOCHE (HRV 🟢)
- 3× Rad (1× Sweet Spot, 1× Threshold ODER VO2max, 1× Z2/Feel)
- 2× Lauf (1× Walk-Run + Strides, 1× im Brick)
- 2× Schwimmen
- 1× Brick (Sa)
- 0–1× Gym

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
## HRV-Daten (Garmin Nacht-Messung, Baseline 58-93ms rMSSD)
{hrv_text}
**HRV-Trend:** {hrv_status}
 
## HRV-Trainingsregeln
| HRV | Status | Aktion |
|-----|--------|--------|
| >80ms | 🟢 Oberes Drittel | Normale/harte Einheit |
| 70-80ms | 🟡 Mitte | Machbar, nicht zu intensiv |
| 65-70ms | 🟠 Unteres Drittel | Auf Körpergefühl achten |
| <65ms | 🔴 Niedrig | Intensität reduzieren/Rest |
| Fallend 3+ Tage | ⚠️ Trend | Akkumulierte Müdigkeit |
 
## HR-Modifikatoren
- Kühlung (Ventilator + kühle Luft): senkt HR ~8-12 bpm
- Volle Glykogenspeicher (Carbs): senkt HR ~3-5 bpm

## Zwift Workout Bibliothek (Phase: {phase}{" — DELOAD" if is_deload else ""})
Verwende für jede Bike-Session EINE dieser Strukturen als Basis.
Skaliere alle FTP%-Angaben auf absolute Watt: FTP = {athlete_profile['ftp_watts']}W.
Beispiel: 88% FTP = {int(athlete_profile['ftp_watts'] * 0.88)}W, 95% FTP = {int(athlete_profile['ftp_watts'] * 0.95)}W.

**Intensitätsregel:**
- 🟢 HRV grün: FTP%-Werte wie angegeben verwenden (bis 95% der Katalog-Prozente)
- 🟡 HRV gelb: alle FTP%-Werte −3-5% reduzieren
- 🔴 HRV rot: Nur Endurance-Einheiten, keine Sweet Spot / Threshold / VO2max

### 🟦 Endurance (Z2-Z3 Grundlage)
{phase_workouts_endurance}

### 🟨 Sweet Spot & Tempo (Z3-Z4 Übergang)
{phase_workouts_sst}

### 🟧 Threshold / Lactate (Z4 Schwelle)
{phase_workouts_threshold}

### 🟥 VO2max & Anaerob (Z5-Z6)
{phase_workouts_vo2max}

{season_structure}
 
 
## Besondere Wünsche
{requests if requests else "Keine."}
 
---
 
## TRAININGSREGELN (WICHTIG!)
 
### Schienbein-Protokoll
- **Stopp-Regel:** Schmerz >3/10 → SOFORT stoppen, nur gehen
- **TENS:** 20 min täglich, Innenseite Schienbein
- **Progression:** Nur steigern wenn 100% schmerzfrei
- **Aktuell:** 4×1.5km Intervalle + 5km Dauerlauf möglich
 
### Rad
- **Kadenz:** 75-85 rpm (natürlich), NICHT höher!
- **Warm-up/Cool-down:** 70-75 rpm
- **Z2-Blöcke:** 76-82 rpm
- **Z1-Erholungen:** 1-3 min @ 115-130W zwischen Z2-Blöcken (locker treten)
- **1× Feel Ride/Woche:** Kadenz komplett frei, nur Watt vorgegeben
- **Zwift ERG-Modus** kompatibel
 
### Lauf
- **Base Phase:** Intervalle mit Gehpausen (z.B. 4×1.5km + 2min gehen)
- **Brick-Läufe:** Kürzer und konservativer als Standalone
- **HR-Ziel:** Z2 (139-173 bpm)
 
### Schwimmen
- Eigener Plan, 2×/Woche
- Nur Termin + Dauer, keine Details
 
### Ersatztraining (session_type `other`)
- Für Ausdauer ohne die eigentliche Disziplin: StairMaster, Crosstrainer,
  Ruderergometer, Aquajogging, Radfahren als Laufersatz.
- Nur einsetzen, wenn ein Grund vorliegt — Verletzung, Ausfall der Anlage,
  Wetter. Im Normalbetrieb wird die Disziplin selbst trainiert.
- `details` nennt das Gerät und die Zone, `targets` nur `hr_zone`.
  Watt- und Pacevorgaben gibt es hier nicht: die Geräte messen anders und
  sind untereinander nicht vergleichbar.

### Gym
- Base 1-2: 2×/Woche | Ab Base 3: 1×/Woche
- **NUR Termin und Dauer.** Keine Übungen, keine Muskelgruppen, keine Sätze
  oder Wiederholungen — auch nicht in `notes`. Der Athlet gestaltet den Inhalt
  selbst; eine Vorgabe ohne Kenntnis von Ausrüstung und Technikstand wäre
  geraten. Zulässig ist höchstens ein Hinweis zur Einordnung in die Woche
  (etwa "Beine frisch halten für morgen").
 
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

{'🔄 DELOAD-WOCHE: Volumen -40-50%, keine neue Intensität!' if is_deload else ''}

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
 