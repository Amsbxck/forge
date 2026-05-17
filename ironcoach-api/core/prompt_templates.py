from datetime import date, timedelta
from core.zwift_catalog import get_phase_workouts


def get_phase(week: int) -> str:
    if week <= 4:
        return "Base 1"
    elif week <= 8:
        return "Base 2"
    elif week <= 12:
        return "Base 3"
    elif week <= 16:
        return "Build 1"
    elif week <= 20:
        return "Build 2"
    elif week <= 24:
        return "Build 3"
    elif week <= 28:
        return "Peak 1"
    elif week <= 30:
        return "Peak 2"
    elif week <= 33:
        return "Taper"
    else:
        return "Race Week"


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
    if not sessions:
        return "Keine Einheiten in den letzten 14 Tagen oder IronCoachAI frisch implementiert."
    lines = []
    for s in sessions:
        parts = [f"- {s['session_date']} | {s['discipline'].upper()} | {s.get('duration_min', '?')}min"]
        if s.get("avg_watts"):
            parts.append(f"| {s['avg_watts']}W avg ({s.get('normalized_power', '?')}W NP)")
        if s.get("avg_hr"):
            parts.append(f"| HR {s['avg_hr']} bpm")
        if s.get("distance_km"):
            parts.append(f"| {s['distance_km']:.1f}km")
        if s.get("tss"):
            parts.append(f"| TSS {s['tss']:.0f}")
        if s.get("hr_zones"):
            z = s["hr_zones"]
            parts.append(f"| Z2: {z.get('z2', 0)}%")
        lines.append(" ".join(parts))
    return "\n".join(lines)


def format_hrv(hrv_list: list) -> str:
    if not hrv_list:
        return "Keine HRV-Daten."
    lines = []
    for h in hrv_list:
        status_icon = "🟢" if h["rmssd"] > 85 else ("🟡" if h["rmssd"] >= 75 else "🔴")
        lines.append(f"- {h['measured_at']}: {h['rmssd']}ms rMSSD {status_icon} ({h.get('hrv_status', '')})")
    return "\n".join(lines)


def build_plan_prompt(
    athlete_profile: dict,
    sessions: list,
    hrv: list,
    week: int,
    requests: str = "",
    plan_start: date = date(2025, 12, 22),
    season_context: str = "",
) -> str:
    phase = get_phase(week)
    hrv_status = analyze_hrv_trend(hrv[-3:] if hrv else [])
    session_summary = format_sessions(sessions)
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
- Name: Amir
- Ziel: Sub-5:30h 70.3 Triathlon am {athlete_profile['race_date']}
- FTP: {athlete_profile['ftp_watts']}W
- Max HR: {athlete_profile['max_hr']} bpm
- HR-Zonen: Z1 0-{athlete_profile['z1_hr_max']} | Z2 {athlete_profile['z2_hr_min']}-{athlete_profile['z2_hr_max']} | Z3 {athlete_profile['z3_hr_min']}-{athlete_profile['z3_hr_max']} | Z4 {athlete_profile['z4_hr_min']}-{athlete_profile['z4_hr_max']} | Z5 >{athlete_profile['max_hr']}
- Equipment: Wahoo KICKR Core, Zwift, Garmin Forerunner 255, Wahoo Elemnt Bolt v2

## SCHIENBEIN-PROTOKOLL (KRITISCH — bei JEDEM Plan beachten)

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

---

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
- Aktuelle Woche: {week}/33
- Phase: {phase}
- Zeitraum: {week_start} bis {week_end}
- Tages-Daten (EXAKT verwenden, nicht selbst berechnen):
{week_days_str}
 
## Trainingsdaten letzte 7-14 Tage
{session_summary}
 
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

## 33-Wochen Saisonstruktur
| Phase | Wochen | Fokus | Deload |
|-------|--------|-------|--------|
| Base 1 | W1–4 | Lauf-Reha, Kraftaufbau, Z2-Rad | W4 |
| Base 2 | W5–8 | Lauf-Volumen steigern, Z2-Dominanz | W8 |
| Base 3 | W9–12 | Längere Einheiten, erste Bricks | W12 |
| Build 1 | W13–16 | Sweet Spot (2×15min @88-94% FTP) + Tempo-Lauf | W16 |
| Build 2 | W17–20 | Sweet Spot + Brick-Sessions | W20 |
| Build 3 | W21–24 | VO₂max + Race-Pace | W24 |
| Peak 1 | W25–28 | Rennsimulationen, lange Bricks | W28 |
| Peak 2 | W29–30 | Test-Races / Peak-Load | – |
| Taper | W31–33 | Volumen ↓, Frische tanken | – |
 
{season_context if season_context else ""}
 
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
 
### Gym
- Base 1-2: 2×/Woche | Ab Base 3: 1×/Woche
- Nur Termin, keine Übungsdetails
 
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
      "duration_min": 60,
      "details": {{}},
      "notes": "..."
    }}
  ]
}}
```
 
### details-Format:

**bike:** (Zwift-Workout-Name in "workout" angeben)
```json
{{
  "workout": "Name aus der Bibliothek (z.B. Tempo #1)",
  "warmup": "10 min Ramp 100→140 W, Kadenz 70-75 rpm",
  "blocks": [
    {{"block": "1", "watt": "145-155 W", "rpm": "76-80", "dauer": "14 min", "zone": "Z2"}},
    {{"block": "Erholung", "watt": "115 W", "rpm": "locker", "dauer": "2 min", "zone": "Z1"}},
    {{"block": "2", "watt": "145-155 W", "rpm": "76-80", "dauer": "14 min", "zone": "Z2"}}
  ],
  "cooldown": "8 min Ramp 140→100 W"
}}
```
 
**run (Intervalle):**
```json
{{
  "typ": "Intervalle",
  "struktur": "4×1.5km joggen + 2min gehen",
  "pace": "7:00-7:30/km",
  "ziel_hr": "139-173 bpm",
  "distanz_richtwert": "~7km"
}}
```
 
**run (Dauerlauf):**
```json
{{
  "typ": "Dauerlauf Z2",
  "dauer": "30 min",
  "pace": "nach Gefühl",
  "ziel_hr": "139-173 bpm"
}}
```
 
**brick:**
```json
{{
  "bike": {{...}},
  "transition": "Schneller Wechsel",
  "run": {{...kürzer als standalone...}}
}}
```
 
**swim / gym:** `{{}}` (leer, nur duration_min + notes)
"""
 