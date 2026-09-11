# IronCoach AI

A full-stack triathlon coaching platform that automates the weekly training plan workflow using Claude AI, Garmin/Wahoo `.fit` files, and Strava integration.

**Use case:** Replace the manual loop of "paste training data → ask Claude → copy plan → make PDF" with an automated pipeline. Finish a workout, Garmin syncs to Strava, the Strava webhook pushes it into IronCoach, and a freshly adapted weekly plan is generated based on real performance metrics, HRV, and a structured Zwift workout catalog.

Target: Sub-5:30h 70.3 Triathlon on 30 August 2026.

---

## Features

- **Auto-import via Strava webhook** — every completed activity is pulled in, parsed (HR zones, power, NP, TSS) and stored
- **Manual upload** for `.fit` and `.gpx` files when Strava is off
- **HRV tracking** with daily input, baseline calculation, and a GitHub-style calendar heatmap
- **Weekly plan generation** through Claude Sonnet 4.6 — phase-aware (33-week season structure), HRV-responsive, with a curated Zwift workout catalog
- **Interactive coach chat** that can read your real session data and generate/update plans on demand
- **PDF export** of the weekly plan (Reportlab)
- **Performance dashboard** — CTL/ATL/TSB trends, HR zone distribution, weekly TSS, session history

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | FastAPI, SQLAlchemy, PostgreSQL 15, Alembic migrations |
| FIT parsing | `fitparse` (Python) |
| External APIs | Anthropic Claude API (`claude-sonnet-4-6`), Strava API v3 (OAuth2 + Webhooks) |
| Frontend | React 18 + Vite, TailwindCSS, Recharts |
| PDF | Reportlab |
| Infra | Docker Compose (local dev) |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    FRONTEND (React + Vite)                   │
│  Dashboard │ Upload │ Weekly Plan │ Chat │ History │ Profile │
└───────────────────────────┬─────────────────────────────────┘
                            │ HTTP (Axios)
┌───────────────────────────▼─────────────────────────────────┐
│                     FASTAPI BACKEND                          │
│  /upload  /plan  /chat  /hrv  /metrics  /webhook  /history  │
└──────┬──────────────┬──────────────────┬────────────────────┘
       │              │                  │
┌──────▼──────┐ ┌─────▼──────┐ ┌────────▼────────┐
│ PostgreSQL  │ │ Claude API │ │   Strava API    │
│ (all data)  │ │ Sonnet 4.6 │ │ OAuth + Webhook │
└─────────────┘ └────────────┘ └─────────────────┘
```

---

## Repository Layout

```
IronCoach-AI/
├── ironcoach-api/              # FastAPI backend
│   ├── core/
│   │   ├── config.py           # Settings (env vars)
│   │   ├── prompt_templates.py # System prompt + phase logic
│   │   └── zwift_catalog.py    # 65+ structured workouts (SST, Threshold, VO2max, Endurance)
│   ├── routers/                # API endpoints
│   │   ├── upload.py           # FIT/GPX upload
│   │   ├── plan.py             # Plan generation, PDF export
│   │   ├── chat.py             # Coach chat (Claude tool use)
│   │   ├── hrv.py              # HRV CRUD
│   │   ├── metrics.py          # Week metrics, CTL/ATL/TSB trends
│   │   ├── history.py          # Session/plan history
│   │   ├── season.py           # Season context (uploaded reference PDFs/texts)
│   │   └── strava_webhook.py   # OAuth + webhook receiver
│   ├── services/
│   │   ├── claude_service.py   # Anthropic SDK wrapper (plan gen + chat)
│   │   ├── fit_parser.py       # .fit parsing, TSS, HR zones, NP
│   │   ├── plan_generator.py   # Orchestrates plan generation
│   │   ├── pdf_generator.py    # Weekly plan PDF
│   │   ├── pdf_extractor.py    # Extract text from uploaded reference PDFs
│   │   ├── strava_service.py   # Strava OAuth + activity fetching
│   │   └── tss_calculator.py   # Training Stress Score
│   ├── alembic/                # DB migrations
│   ├── models.py               # SQLAlchemy models
│   ├── schemas.py              # Pydantic schemas
│   └── main.py                 # FastAPI app
│
├── ironcoach-frontend/         # React + Vite SPA
│   └── src/
│       ├── pages/              # Dashboard, Upload, WeeklyPlan, Chat, History, Profile, Season
│       ├── components/         # HRVHeatmap, PerformanceChart, WeekCalendar, etc.
│       └── services/api.js     # Axios client
│
├── docker-compose.yml          # db + backend + frontend
├── .env.example                # Required environment variables
└── README.md
```

---

## Setup

### Prerequisites

- Docker Desktop
- Anthropic API key
- (Optional) Strava developer app for auto-import

### 1. Clone & configure

```bash
git clone https://gitlab.com/laxerju/ironcoach-ai.git
cd ironcoach-ai
cp .env.example .env
```

Fill in `.env`:

```env
ANTHROPIC_API_KEY=sk-ant-...
STRAVA_CLIENT_ID=...
STRAVA_CLIENT_SECRET=...
STRAVA_VERIFY_TOKEN=any_random_string
```

### 2. Build & run

```bash
docker compose up --build
```

This starts:
- **PostgreSQL** on `localhost:5433`
- **Backend** on `localhost:8000` (Alembic runs migrations on boot)
- **Frontend** on `localhost:3000`

### 3. (Optional) Connect Strava

For local webhook testing, expose port 8000 via [ngrok](https://ngrok.com/):

```bash
ngrok http 8000
```

Then run:

```bash
python register_webhook.py
```

In the frontend Profile page, click **Connect Strava** to OAuth your account.

---

## Daily Use

1. **Train** — Garmin/Wahoo records the session
2. **Sync** — Strava receives the activity, webhook fires, backend imports it
3. **Log HRV** in the dashboard each morning (Garmin Body Battery + rMSSD)
4. **Monday: generate weekly plan** in the *Weekly Plan* page — Claude reads the last 14 days of sessions, last 7 days of HRV, and the current phase
5. **Coach chat** for ad-hoc adjustments — Claude can update the plan via tool use
6. **Export to PDF** for printing or sharing

---

## Plan Generation Logic

The plan prompt is assembled in [`core/prompt_templates.py`](ironcoach-api/core/prompt_templates.py) and combines:

- **Athlete profile** (FTP, HR zones, equipment, race date)
- **Shin protocol** — progressive walk-run loading, strides rules, brick format
- **Bike logic** — Sweet Spot / Threshold / VO2max ladder, dynamic 2–3 sessions/week scaled by HRV
- **Current week + phase** (33-week structure: Base 1–3, Build 1–3, Peak 1–2, Taper)
- **Last 14 days of training data**
- **Last 7 days of HRV**
- **HRV decision matrix** (🟢🟡🟠🔴 → intensity adjustments)
- **Zwift workout catalog** filtered by current phase (from [`core/zwift_catalog.py`](ironcoach-api/core/zwift_catalog.py))
- **Season context** — uploaded reference plans/PDFs

Claude returns a structured JSON plan (via tool use) with per-day session details, which is persisted in the `weekly_plans` table.

---

## API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/upload` | Upload .fit/.gpx file |
| `GET` | `/api/plan/generate` | Generate plan for current week |
| `GET` | `/api/plan/current` | Current plan |
| `GET` | `/api/plan/{week}/pdf` | Download plan as PDF |
| `POST` | `/api/chat` | Send chat message to coach |
| `POST` | `/api/hrv` | Submit daily HRV |
| `GET` | `/api/hrv?limit=N` | HRV history |
| `GET` | `/api/metrics/week` | Current week metrics |
| `GET` | `/api/metrics/trends` | CTL/ATL/TSB time series |
| `GET` | `/api/history/sessions` | Session list |
| `POST` | `/api/webhook` | Strava webhook receiver |
| `GET` | `/api/strava/auth` | Start Strava OAuth |

Interactive docs: `http://localhost:8000/docs`

---

## Environment Variables

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | Claude API key |
| `DATABASE_URL` | Postgres connection string (set automatically by Docker Compose) |
| `STRAVA_CLIENT_ID` | Strava OAuth client ID |
| `STRAVA_CLIENT_SECRET` | Strava OAuth client secret |
| `STRAVA_VERIFY_TOKEN` | Arbitrary string used to verify webhook subscription |
| `UPLOAD_DIR` | Where uploaded .fit files are stored |
| `MAX_UPLOAD_SIZE_MB` | Upload size cap |

---

## Development

**Hot reload** is enabled — Python via `uvicorn --reload`, frontend via Vite. Editing files in `ironcoach-api/` or `ironcoach-frontend/src/` updates the running containers without a rebuild.

**Database changes** require an Alembic migration:

```bash
docker compose exec backend alembic revision --autogenerate -m "your change"
docker compose exec backend alembic upgrade head
```

**Reset everything:**

```bash
docker compose down -v   # removes Postgres volume too
docker compose up --build
```

---

## License

Private project. Not licensed for redistribution.
