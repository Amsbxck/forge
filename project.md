# IronCoach AI — Vollständiger Projektplan

> Full-Stack Triathlon Coaching Plattform mit Claude API & Strava Integration  
> Ziel: Automatisierung des wöchentlichen Trainingsplan-Workflows  
> Renntag: 31. August 2026 — 70.3 Triathlon, Sub 5:30h

---

## Projektziel

Eine Full-Stack Coaching-Plattform, die den manuellen Wochenend-Workflow (Daten pasten → Claude → Plan kopieren) vollständig automatisiert. Nach jeder Einheit werden Daten automatisch via Strava Webhook importiert, analysiert und ein angepasster Wochenplan via Claude API generiert — inkl. HRV, HR-Zonen, Watt, Pace und Fatigue.

**Vorher (manuell):** Trainingsdaten kopieren → In Claude pasten → Plan bekommen → PDF erstellen  
**Nachher (automatisch):** Einheit abschließen → Garmin sync → Strava → Webhook → IronCoach → Plan fertig

---

## Tech Stack

| Schicht | Technologie |
|--------|-------------|
| Backend | FastAPI (Python), SQLAlchemy, PostgreSQL, Alembic |
| FIT Parser | fitparse (Garmin/Wahoo .fit Dateien) |
| Strava Integration | Strava API v3, OAuth2, Webhooks |
| Frontend | React + Vite, TailwindCSS, Recharts |
| KI | Anthropic Claude API (claude-sonnet-4-6) |
| PDF Export | Reportlab |
| Infrastruktur | Docker Compose (lokal), Railway/Render (optional deploy) |

---

## Systemarchitektur

```
┌─────────────────────────────────────────────────────────────┐
│                        FRONTEND (React)                      │
│  Dashboard │ Upload │ Wochenplan │ Chat │ History │ Profile  │
└───────────────────────────┬─────────────────────────────────┘
                            │ HTTP (Axios)
┌───────────────────────────▼─────────────────────────────────┐
│                     FASTAPI BACKEND                          │
│  /upload  /plan  /chat  /hrv  /metrics  /webhook  /history  │
└──────┬──────────────┬──────────────────┬────────────────────┘
       │              │                  │
┌──────▼──────┐ ┌─────▼──────┐ ┌────────▼────────┐
│ PostgreSQL  │ │ Claude API │ │   Strava API    │
│ (alle Daten)│ │ Sonnet 4.6 │ │ OAuth + Webhook │
└─────────────┘ └────────────┘ └─────────────────┘
```

**Automatischer Datenfluss:**
```
Einheit abgeschlossen → Garmin sync → Strava → Webhook POST → 
FastAPI → Strava API (Aktivitätsdaten holen) → DB speichern → 
(optional) Plan für nächste Woche automatisch generieren
```

---

## Datenbankschema (PostgreSQL)

```sql
-- Athletenprofil (einmalig, mit deinen Werten vorbelegt)
CREATE TABLE athlete_profile (
  id SERIAL PRIMARY KEY,
  name VARCHAR,
  ftp_watts INT DEFAULT 238,
  max_hr INT DEFAULT 212,
  z1_hr_max INT DEFAULT 138,
  z2_hr_min INT DEFAULT 139,
  z2_hr_max INT DEFAULT 173,
  z3_hr_min INT DEFAULT 174,
  z3_hr_max INT DEFAULT 189,
  z4_hr_min INT DEFAULT 190,
  z4_hr_max INT DEFAULT 210,
  race_date DATE DEFAULT '2026-08-31',
  race_goal VARCHAR DEFAULT 'sub 5:30h 70.3',
  current_week INT DEFAULT 10,
  updated_at TIMESTAMP DEFAULT NOW()
);

-- Trainingseinheiten (nach jedem Upload/Import)
CREATE TABLE training_sessions (
  id SERIAL PRIMARY KEY,
  session_date DATE NOT NULL,
  week_number INT NOT NULL,
  discipline VARCHAR NOT NULL,  -- 'bike', 'run', 'swim', 'gym'
  duration_min INT,
  distance_km FLOAT,
  avg_hr INT,
  max_hr INT,
  avg_watts INT,             -- Rad: aus FIT / Strava
  normalized_power INT,      -- Rad: NP
  avg_pace_min_km FLOAT,     -- Lauf
  tss FLOAT,                 -- Training Stress Score
  rpe INT,                   -- Perceived exertion 1-10
  hr_zones JSONB,            -- {"z1": 5, "z2": 60, "z3": 25, ...} in %
  strava_activity_id BIGINT, -- Strava Activity ID (falls via Webhook)
  notes TEXT,
  fit_file_path VARCHAR,
  created_at TIMESTAMP DEFAULT NOW()
);

-- HRV-Messungen (morgens, Garmin Nacht-Messung oder manuell)
CREATE TABLE hrv_measurements (
  id SERIAL PRIMARY KEY,
  measured_at DATE NOT NULL,
  rmssd FLOAT NOT NULL,       -- Baseline: 58-93ms
  hrv_status VARCHAR,         -- 'green' >85ms | 'yellow' 75-85ms | 'red' <=70ms
  readiness_score INT,        -- optional Garmin Body Battery
  notes TEXT
);

-- Generierte Wochenpläne (von Claude API)
CREATE TABLE weekly_plans (
  id SERIAL PRIMARY KEY,
  week_number INT NOT NULL,
  week_start DATE NOT NULL,
  week_end DATE NOT NULL,
  plan_phase VARCHAR,         -- 'base', 'build', 'peak', 'taper', 'deload'
  plan_content JSONB NOT NULL,-- Strukturierter Plan (Tag-für-Tag)
  plan_text TEXT,             -- Klartext für PDF Export
  claude_prompt TEXT,         -- Was wurde an Claude geschickt (Debug)
  adjustments_applied TEXT[], -- z.B. ["HRV niedrig -> Intensität reduziert"]
  generated_at TIMESTAMP DEFAULT NOW()
);

-- Chat-Verlauf mit Coach
CREATE TABLE chat_messages (
  id SERIAL PRIMARY KEY,
  role VARCHAR NOT NULL,      -- 'user' oder 'assistant'
  content TEXT NOT NULL,
  context_week INT,
  created_at TIMESTAMP DEFAULT NOW()
);

-- Strava OAuth Credentials
CREATE TABLE strava_credentials (
  id SERIAL PRIMARY KEY,
  athlete_id INT NOT NULL,           -- Strava Athlete ID
  access_token VARCHAR NOT NULL,
  refresh_token VARCHAR NOT NULL,
  expires_at BIGINT NOT NULL,        -- Unix timestamp (läuft alle 6h ab)
  scope VARCHAR DEFAULT 'activity:read_all',
  connected_at TIMESTAMP DEFAULT NOW()
);
```

---

## Backend — Projektstruktur

```
ironcoach-api/
├── main.py
├── database.py
├── models.py
├── schemas.py
├── routers/
│   ├── upload.py          # FIT/GPX Dateien manuell verarbeiten
│   ├── plan.py            # Wochenplan generieren (Claude API)
│   ├── chat.py            # Coach Chatbot (Claude API)
│   ├── metrics.py         # Dashboard Daten
│   ├── hrv.py             # HRV Eingabe/Abruf
│   ├── history.py         # Wochenverlauf
│   └── strava_webhook.py  # Strava OAuth + Webhook Endpoint
├── services/
│   ├── fit_parser.py      # FIT Dateien parsen → Training Session
│   ├── claude_service.py  # Claude API Calls
│   ├── plan_generator.py  # Prompt bauen + Plan strukturieren
│   ├── tss_calculator.py  # Training Stress Score berechnen
│   └── strava_service.py  # Strava API + Token Refresh
└── core/
    ├── config.py           # Env vars (API Keys etc.)
    └── prompt_templates.py # Alle Claude Prompts
```

### API Endpoints Übersicht

| Method | Endpoint | Beschreibung |
|--------|----------|--------------|
| POST | `/api/upload` | FIT/GPX Datei hochladen, parsen, speichern |
| POST | `/api/hrv` | HRV Messung eingeben |
| GET | `/api/plan/generate` | Wochenplan via Claude generieren |
| GET | `/api/plan/current` | Aktuellen Plan abrufen |
| GET | `/api/metrics/week` | Diese Woche: TSS, HR-Zonen, Compliance |
| GET | `/api/metrics/trends` | Letzte 4 Wochen Trend |
| POST | `/api/chat` | Coach Chatbot mit Trainingskontext |
| GET | `/api/history` | Alle vergangenen Wochen |
| GET | `/api/strava/auth` | OAuth URL generieren (Redirect zu Strava) |
| GET | `/api/strava/callback` | OAuth Code empfangen, Token speichern |
| GET | `/webhook` | Strava Verification Challenge |
| POST | `/webhook` | Neue Aktivität empfangen → automatisch verarbeiten |

---

## Claude Service — Kernlogik

```python
# services/claude_service.py
import anthropic
from core.prompt_templates import build_plan_prompt

client = anthropic.Anthropic()  # ANTHROPIC_API_KEY aus env

async def generate_weekly_plan(
    athlete_profile: dict,
    last_sessions: list,      # Letzte 7-14 Tage Training
    hrv_data: list,           # Letzte 7 Tage HRV
    week_number: int,
    special_requests: str = ""
) -> dict:
    prompt = build_plan_prompt(
        athlete_profile=athlete_profile,
        sessions=last_sessions,
        hrv=hrv_data,
        week=week_number,
        requests=special_requests
    )
    
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system="""Du bist ein erfahrener Triathlon-Coach und Sportwissenschaftler.
        Du kennst diesen Athleten seit Woche 1 seines 33-Wochen 70.3-Plans.
        Ziel: 31. August 2026, sub 5:30h, zweiter 70.3.
        Antworte immer mit einem JSON-Plan plus einer kurzen deutschen Erklärung.""",
        messages=[{"role": "user", "content": prompt}]
    )
    
    return parse_plan_response(response.content[0].text)


async def chat_with_coach(
    message: str,
    chat_history: list,
    current_week_context: dict
) -> str:
    messages = chat_history + [{"role": "user", "content": message}]
    
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=f"""Du bist Amirs persönlicher Triathlon-Coach.
        Aktueller Kontext: Woche {current_week_context['week']}, 
        Phase: {current_week_context['phase']},
        FTP: 238W, Renntag: 31.08.2026.
        Sei direkt, sportwissenschaftlich fundiert, auf Deutsch.""",
        messages=messages
    )
    
    return response.content[0].text
```

---

## Prompt Template — Plan Generation

```python
# core/prompt_templates.py

def build_plan_prompt(athlete_profile, sessions, hrv, week, requests=""):
    
    recent_hrv = hrv[-3:] if hrv else []
    hrv_status = analyze_hrv_trend(recent_hrv)
    session_summary = format_sessions(sessions)
    
    return f"""
## Athletenprofil
- FTP: {athlete_profile['ftp_watts']}W
- HR-Zonen: Z1 0-138 | Z2 139-173 | Z3 174-189 | Z4 190-210 | Z5 211+
- Max HR: 212 bpm
- Renntag: 31.08.2026 (70.3 Triathlon, Ziel sub 5:30h)
- Aktuell: Woche {week}/33 (Phase: {get_phase(week)})
- Equipment: Wahoo KICKR Core, Zwift, Garmin Forerunner 255

## Trainingsdaten letzte 7-14 Tage
{session_summary}

## HRV-Daten (letzte 7 Tage)
{format_hrv(hrv)}
HRV-Trend: {hrv_status}
(Baseline: 58-93ms rMSSD, Garmin Nacht-Messung)
HRV-Regeln: >85ms = normale Einheit | 75-85ms = machbar nicht intensiv | <=70ms = reduzieren/Rest

## Bisherige Woche {week} Struktur
{get_planned_week_structure(week)}

## Besondere Hinweise / Wünsche
{requests if requests else "Keine besonderen Anpassungen nötig."}

## Aufgabe
Erstelle den Trainingsplan für Woche {week + 1} ({get_dates(week + 1)}).

Beachte:
- Shin/Schienbein: progressiver Laufaufbau, max 1km Jogging am Stück
- Rad: Zwift ERG-kompatibel, exakte Watt + Kadenz + Zeiten
- Gym: Unterkörper Fokus (Glutes, Abduktoren, Sprunggelenk-Stabilisierung)
- Deload wenn {week + 1} % 4 == 0
- HRV berücksichtigen: {hrv_status}

Antworte mit:
1. JSON-Plan (Tag-für-Tag, alle Einheiten vollständig)
2. 3-4 Sätze Coaching-Kommentar auf Deutsch
3. Angewendete Anpassungen (Liste)

JSON-Format:
{{
  "week": {week + 1},
  "phase": "...",
  "days": [
    {{
      "day": "Montag",
      "date": "...",
      "session_type": "rest|bike|run|swim|gym|brick",
      "duration_min": ...,
      "details": {{...}},  
      "notes": "..."
    }}
  ],
  "coaching_comment": "...",
  "adjustments": ["..."]
}}
"""
```

---

## FIT Parser — Kernfunktion

```python
# services/fit_parser.py
from fitparse import FitFile

def parse_fit_file(file_path: str) -> dict:
    """
    Parst Garmin/Wahoo FIT Datei.
    Extrahiert: Dauer, Distanz, HR (avg/max/Zonen), 
                Watt (avg/NP), Kadenz, Pace, TSS
    """
    fitfile = FitFile(file_path)
    hr_data, power_data, speed_data = [], [], []
    
    for record in fitfile.get_messages('record'):
        for field in record:
            if field.name == 'heart_rate' and field.value:
                hr_data.append(field.value)
            if field.name == 'power' and field.value:
                power_data.append(field.value)
            if field.name == 'enhanced_speed' and field.value:
                speed_data.append(field.value)
    
    return {
        "avg_hr": sum(hr_data) / len(hr_data) if hr_data else None,
        "max_hr": max(hr_data) if hr_data else None,
        "avg_watts": sum(power_data) / len(power_data) if power_data else None,
        "normalized_power": calculate_np(power_data) if power_data else None,
        "tss": calculate_tss(power_data, ftp=238) if power_data else None,
        "hr_zones": calculate_hr_zones(hr_data),
    }

def calculate_hr_zones(hr_data: list) -> dict:
    """Berechnet % Zeit in Z1-Z5 nach deinen HR-Grenzen."""
    zones = {"z1": 0, "z2": 0, "z3": 0, "z4": 0, "z5": 0}
    for hr in hr_data:
        if hr <= 138:   zones["z1"] += 1
        elif hr <= 173: zones["z2"] += 1
        elif hr <= 189: zones["z3"] += 1
        elif hr <= 210: zones["z4"] += 1
        else:           zones["z5"] += 1
    total = len(hr_data)
    return {k: round(v/total*100, 1) for k, v in zones.items()} if total else zones
```

---

## Strava API Integration

### Zugang als normaler Nutzer

Kein App-Review, kein Approval-Prozess nötig. Jeder registrierte Strava-Nutzer kann direkt loslegen.

**Schritt 1 — App registrieren (2 Minuten):**
Geh auf `strava.com/settings/api`, erstell eine App (Name: "IronCoach", Website: `localhost`).  
Du bekommst sofort `Client ID` und `Client Secret`.

**Schritt 2 — Einmalige Browser-Auth:**
```
http://www.strava.com/oauth/authorize
  ?client_id=DEINE_CLIENT_ID
  &response_type=code
  &redirect_uri=http://localhost/exchange_token
  &approval_prompt=force
  &scope=activity:read_all
```
Im Browser öffnen → Authorize klicken → Code aus URL holen.

**Schritt 3 — Token tauschen:**
```bash
curl -X POST https://www.strava.com/oauth/token \
  -F client_id=DEINE_CLIENT_ID \
  -F client_secret=DEIN_CLIENT_SECRET \
  -F code=CODE_AUS_URL \
  -F grant_type=authorization_code
```
Ergebnis: `access_token` + `refresh_token` (Access läuft alle 6h ab, Refresh ist dauerhaft).

### Webhook — automatischer Trigger

Sobald du eine Einheit auf Garmin abschliesst und es zu Strava syncronisiert, schickt Strava einen automatischen POST-Request an IronCoach. Kein manuelles Hochladen mehr.

```
Einheit fertig → Garmin sync → Strava → 
POST /webhook → FastAPI → Strava API (Daten holen) → DB
```

### Strava Service

```python
# services/strava_service.py
import httpx
from datetime import datetime

STRAVA_BASE = "https://www.strava.com/api/v3"

class StravaService:
    def __init__(self, db):
        self.db = db

    async def refresh_token_if_needed(self, athlete_id: int) -> str:
        """Erneuert Access Token automatisch wenn abgelaufen."""
        creds = self.db.get_strava_credentials(athlete_id)
        
        if creds.expires_at < datetime.now().timestamp():
            async with httpx.AsyncClient() as client:
                resp = await client.post("https://www.strava.com/oauth/token", data={
                    "client_id": settings.STRAVA_CLIENT_ID,
                    "client_secret": settings.STRAVA_CLIENT_SECRET,
                    "grant_type": "refresh_token",
                    "refresh_token": creds.refresh_token,
                })
                new_tokens = resp.json()
                self.db.update_strava_credentials(athlete_id, new_tokens)
                return new_tokens["access_token"]
        
        return creds.access_token

    async def fetch_activity(self, activity_id: int, athlete_id: int) -> dict:
        """Holt vollständige Aktivitätsdaten von Strava."""
        token = await self.refresh_token_if_needed(athlete_id)
        
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{STRAVA_BASE}/activities/{activity_id}",
                headers={"Authorization": f"Bearer {token}"}
            )
            return resp.json()

    async def fetch_activity_streams(self, activity_id: int, athlete_id: int) -> dict:
        """Holt HR, Watt, Pace Zeitreihen für HR-Zonen Berechnung."""
        token = await self.refresh_token_if_needed(athlete_id)
        
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{STRAVA_BASE}/activities/{activity_id}/streams",
                params={"keys": "heartrate,watts,velocity_smooth,cadence,time"},
                headers={"Authorization": f"Bearer {token}"}
            )
            return resp.json()
```

### Webhook Endpoint

```python
# routers/strava_webhook.py
from fastapi import APIRouter, Request, HTTPException, BackgroundTasks

router = APIRouter()

@router.get("/webhook")  # Strava Verification
async def verify_webhook(request: Request):
    params = request.query_params
    if params.get("hub.verify_token") == settings.STRAVA_VERIFY_TOKEN:
        return {"hub.challenge": params.get("hub.challenge")}
    raise HTTPException(status_code=403)

@router.post("/webhook")  # Aktivität empfangen
async def receive_webhook(payload: dict, background_tasks: BackgroundTasks):
    """
    Strava schickt diesen POST sobald eine Einheit abgeschlossen wird.
    Sofort mit 200 antworten, Verarbeitung im Background.
    """
    if payload.get("object_type") == "activity" and payload.get("aspect_type") == "create":
        activity_id = payload["object_id"]
        athlete_id = payload["owner_id"]
        
        background_tasks.add_task(
            process_new_strava_activity,
            activity_id=activity_id,
            athlete_id=athlete_id
        )
    
    return {"status": "ok"}
```

### Was die Strava Activity API liefert

```json
{
  "distance": 15230,
  "moving_time": 3600,
  "average_heartrate": 148.2,
  "max_heartrate": 173,
  "average_watts": 195,
  "weighted_average_watts": 201,
  "kilojoules": 702,
  "average_cadence": 88.4,
  "average_speed": 4.23,
  "sport_type": "VirtualRide",
  "trainer": true
}
```

Für HR-Zonen-Berechnung → Streams API (`heartrate`, `watts`, `velocity_smooth`).

---

## Frontend — Projektstruktur

```
ironcoach-frontend/
├── src/
│   ├── pages/
│   │   ├── Dashboard.jsx      # Übersicht: Diese Woche, HRV, TSS
│   │   ├── Upload.jsx         # FIT Datei hochladen (Drag & Drop, Fallback)
│   │   ├── WeeklyPlan.jsx     # Aktueller Wochenplan anzeigen
│   │   ├── Chat.jsx           # Coach Chatbot
│   │   ├── History.jsx        # Alle vergangenen Wochen
│   │   └── Profile.jsx        # Athletenprofil + Einstellungen
│   ├── components/
│   │   ├── HRVInput.jsx       # Tägliche HRV Eingabe
│   │   ├── SessionCard.jsx    # Eine Trainingseinheit
│   │   ├── WeekCalendar.jsx   # 7-Tage Kalenderansicht
│   │   ├── HRZoneChart.jsx    # Recharts HR-Zonen Balken
│   │   ├── TSSTrend.jsx       # Recharts TSS Verlauf (4 Wochen)
│   │   └── PlanExport.jsx     # PDF Export Button
│   └── services/
│       └── api.js             # Alle API Calls (Axios)
```

### HRV Ampel-System im Dashboard

| HRV (rMSSD) | Status | Bedeutung |
|-------------|--------|-----------|
| > 85ms | 🟢 Grün | Normale Einheit wie geplant |
| 75–85ms | 🟡 Gelb | Machbar, aber nicht zu intensiv |
| ≤ 70ms | 🔴 Rot | Intensität reduzieren / Rest |

---

## Docker Compose — lokales Setup

```yaml
# docker-compose.yml
version: '3.8'
services:
  db:
    image: postgres:15
    environment:
      POSTGRES_DB: ironcoach
      POSTGRES_USER: amir
      POSTGRES_PASSWORD: localdev
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

  backend:
    build: ./ironcoach-api
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgresql://amir:localdev@db/ironcoach
      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY}
      STRAVA_CLIENT_ID: ${STRAVA_CLIENT_ID}
      STRAVA_CLIENT_SECRET: ${STRAVA_CLIENT_SECRET}
      STRAVA_VERIFY_TOKEN: ${STRAVA_VERIFY_TOKEN}
    volumes:
      - ./ironcoach-api:/app
      - ./uploads:/app/uploads
    depends_on:
      - db

  frontend:
    build: ./ironcoach-frontend
    ports:
      - "3000:3000"
    environment:
      VITE_API_URL: http://localhost:8000
    volumes:
      - ./ironcoach-frontend/src:/app/src

volumes:
  postgres_data:
```

---

## Umgebungsvariablen (.env)

```bash
# Claude API
ANTHROPIC_API_KEY=sk-ant-...

# Datenbank
DATABASE_URL=postgresql://amir:localdev@localhost/ironcoach

# Strava
STRAVA_CLIENT_ID=deine_client_id
STRAVA_CLIENT_SECRET=dein_client_secret
STRAVA_VERIFY_TOKEN=ironcoach_webhook_secret   # selbst gewählt

# Upload
UPLOAD_DIR=./uploads
MAX_UPLOAD_SIZE_MB=50
```

> **Hinweis für Webhooks lokal:** Strava braucht eine öffentlich erreichbare URL.  
> `ngrok http 8000` → gibt eine temporäre HTTPS-URL → diese als Webhook Callback URL eintragen.

---

## Athletenprofil — Voreinstellungen

Beim ersten Start wird das Profil automatisch mit diesen Werten angelegt:

| Parameter | Wert |
|-----------|------|
| FTP | 238W |
| Max HR | 212 bpm |
| Z1 | 0–138 bpm |
| Z2 | 139–173 bpm |
| Z3 | 174–189 bpm |
| Z4 | 190–210 bpm |
| Z5 | 211+ bpm |
| HRV Baseline | 58–93ms rMSSD (Garmin Nacht) |
| Renntag | 31.08.2026 |
| Ziel | Sub 5:30h, 70.3 Triathlon |
| Aktuell | Woche 10/33, Phase: Base 3 |

---

## Entwicklungsreihenfolge für Claude Code

### Phase 1 — Backend Foundation (Session 1–2)
- [ ] Projektstruktur anlegen (`ironcoach-api/`, `ironcoach-frontend/`, `docker-compose.yml`)
- [ ] FastAPI + PostgreSQL Setup mit Alembic Migrations
- [ ] Alle DB-Tabellen anlegen (inkl. `strava_credentials`)
- [ ] `fit_parser.py` — FIT Dateien parsen (Garmin + Wahoo)
- [ ] `POST /api/upload` — Datei hochladen, parsen, in DB speichern
- [ ] `POST /api/hrv` — HRV manuell eingeben
- [ ] Tests: `pytest` + `httpx` für alle Endpoints

### Phase 2 — Claude Integration (Session 3–4)
- [ ] `claude_service.py` — API Calls + Fehlerbehandlung
- [ ] `prompt_templates.py` — Vollständiger Prompt mit Athletenprofil vorbeladen
- [ ] `POST /api/plan/generate` — Plan generieren + in DB speichern
- [ ] `POST /api/chat` — Coach Chatbot mit vollem Trainingskontext

### Phase 3 — Strava Integration (Session 5)
- [ ] `strava_service.py` — OAuth Flow + Token Auto-Refresh
- [ ] `GET /api/strava/auth` + `GET /api/strava/callback`
- [ ] `GET /webhook` (Verification) + `POST /webhook` (Events empfangen)
- [ ] Background Task: Aktivität von Strava holen → parsen → DB speichern
- [ ] Streams API für detaillierte HR/Watt-Zeitreihen

### Phase 4 — Frontend (Session 6–8)
- [ ] Dashboard: HRV Ampel, TSS Trend, nächste Einheit
- [ ] Upload Page: Drag & Drop FIT (Fallback wenn kein Strava)
- [ ] Wochenplan Ansicht: Kalender + vollständige Einheiten
- [ ] Chat Interface: Coach Chatbot
- [ ] History: Alle Wochen, Statistiken

### Phase 5 — Polish (Session 9)
- [ ] PDF Export (Reportlab, wie bestehende Wochenpläne)
- [ ] HRV Ampel visuell im Dashboard
- [ ] Athletenprofil editierbar (FTP Update nach Test etc.)
- [ ] Strava Connected Badge im Profil

---

## Claude Code Prompt — Phase 1

```
Ich möchte ein Full-Stack Projekt namens "IronCoach AI" bauen.

Kontext: Ich bin Triathlet (70.3 am 31.08.2026, Ziel sub 5:30h, aktuell Woche 10/33).
Ich trainiere mit Wahoo KICKR Core (Zwift), Garmin Forerunner 255, und schwimme 2x/Woche.
FTP: 238W. HR-Zonen: Z1 ≤138, Z2 139-173, Z3 174-189, Z4 190-210, Z5 211+.
HRV Baseline: 58-93ms rMSSD (Garmin Nacht-Messung).
HRV-Regeln: >85ms = normal | 75-85ms = machbar nicht intensiv | <=70ms = reduzieren/Rest.

Das Projekt automatisiert meinen wöchentlichen Workflow:
Bisher: Trainingsdaten manuell in Claude pasten → Plan bekommen → kopieren
Neu: Strava Webhook → automatisch importieren → Claude API → Plan fertig

Stack:
- Backend: FastAPI + PostgreSQL + SQLAlchemy + Alembic + fitparse
- Frontend: React + Vite + TailwindCSS + Recharts
- KI: Anthropic Claude API (claude-sonnet-4-6)
- Strava: OAuth2 + Webhook Events API
- Infra: Docker Compose

Starte mit Phase 1:
1. Projektstruktur anlegen (ironcoach-api/ + ironcoach-frontend/ + docker-compose.yml)
2. FastAPI + PostgreSQL Setup mit Alembic
3. Alle DB-Tabellen (athlete_profile, training_sessions, hrv_measurements, 
   weekly_plans, chat_messages, strava_credentials)
4. FIT Parser Service (fitparse) — extrahiert HR, Watt, Pace, HR-Zonen
5. POST /api/upload Endpoint
6. POST /api/hrv Endpoint
7. pytest + httpx Tests für alle Endpoints

Athletenprofil soll beim ersten Start automatisch vorbelegt sein:
FTP=238, MaxHR=212, Z1≤138, Z2 139-173, Z3 174-189, Z4 190-210, 
race_date=2026-08-31, current_week=10
```

## Claude Code Prompt — Phase 3 (Strava)

```
Jetzt Phase 3: Strava API Integration.

Neue Tabelle strava_credentials ist bereits im Schema.

Implementiere:
1. StravaService mit Token Auto-Refresh (Access Token läuft alle 6h ab)
2. GET /api/strava/auth → OAuth URL generieren
3. GET /api/strava/callback → Code empfangen, Token speichern
4. GET /webhook → Strava Verification Challenge beantworten
5. POST /webhook → Neue Aktivität empfangen, sofort 200 zurückgeben,
   dann im Background: Strava API aufrufen (fetch_activity + fetch_streams),
   HR-Zonen berechnen, als training_session in DB speichern
6. Strava Streams API für heartrate, watts, velocity_smooth, cadence
7. Env vars: STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET, STRAVA_VERIFY_TOKEN

Für lokale Entwicklung: ngrok als Tunnel (in README dokumentieren).
Scope: activity:read_all
```

---

## Projektstatus

| Feature | Status |
|---------|--------|
| Projektplan | ✅ Fertig |
| Backend Setup | ⬜ Offen |
| FIT Parser | ⬜ Offen |
| Claude Integration | ⬜ Offen |
| Strava OAuth + Webhook | ⬜ Offen |
| Frontend | ⬜ Offen |
| PDF Export | ⬜ Offen |

---

*Erstellt: März 2026 — IronCoach AI für 70.3 Triathlon Saison 2026*
