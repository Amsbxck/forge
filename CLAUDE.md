# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

FORGE (früher IronCoach AI) ist eine Coaching-App für Triathlon, Laufen und Rad: Strava/FIT-Daten rein, Claude erzeugt Wochenpläne und beantwortet den Coach-Chat. Mehrere Athleten, ein Backend.

Sprache: Bezeichner, Kommentare, Testnamen und Commit-Nachrichten sind deutsch, Kommentare erklären ausführlich das *Warum* (oft samt Vorgeschichte des Fehlers). So weiterschreiben. Antworten an Amir auf Deutsch.

## Befehle

Alles läuft über Docker Compose (`db` auf 5433, `backend` auf 8000 mit `--reload`, `frontend` auf 3000). Die Quellen sind in die Container gemountet, Änderungen am Code wirken ohne Neubau. Die Pakete aber nicht: Nach einer Änderung an `requirements.txt` braucht es `docker compose up -d --build backend`, sonst läuft im Container still die alte Version weiter (beim Umstieg auf Sonnet 5.5 kannte das alte SDK `output_config` nicht, und jeder Claude-Aufruf scheiterte).

```bash
docker compose up --build
```

**Tests nur im Backend-Container.** Der lokale venv `ironcoach/` ist kaputt (toter Shebang, fehlende Pakete), und `conftest.py` verbindet auf den Compose-Host `db`.

```bash
# ganze Suite
docker exec -e TEST_DATABASE_URL=postgresql://amir:localdev@db/ironcoach_fix_test \
  ironcoach-ai-backend-1 python -m pytest -q -p no:warnings tests/
# einzelner Test
docker exec -e TEST_DATABASE_URL=postgresql://amir:localdev@db/ironcoach_fix_test \
  ironcoach-ai-backend-1 python -m pytest -q tests/test_deload_rhythmus.py::test_name
```

`conftest.py` erzwingt eine eigene Testdatenbank (Name muss auf `_test` enden, sonst `<name>_test`) und **löscht deren Schema**. Ohne `TEST_DATABASE_URL` nimmt es `ironcoach_test`. Es setzt außerdem `AUTH_REQUIRED=false` und `RECONCILE_ENABLED=false`.

Frontend (`ironcoach-frontend`): kein Lint- und kein Testskript, nur `npm run dev` (Proxy auf `/api`, `/webhook`, `/health` über `VITE_PROXY_TARGET`, Vorgabe `http://backend:8000`) und `npm run build`. Einen Python-Linter gibt es ebenfalls nicht.

Migrationen: Alembic, fortlaufend nummeriert (`alembic/versions/0NN_<thema>.py`, `revision = "0NN"`, `down_revision` = Vorgänger). Laufen beim Containerstart (`docker-entrypoint.sh` bzw. Compose-Befehl). `tests/test_schema_migrationen.py` baut eine leere DB über die Migrationen und vergleicht sie mit den Modellen. Jede Modelländerung braucht also eine passende Migration.

## Architektur

Backend `ironcoach-api/` (FastAPI, SQLAlchemy, Postgres 15), Frontend `ironcoach-frontend/` (React 18, Vite, Tailwind, Recharts; Seiten per `React.lazy`). Alle Router außer `auth` und dem Strava-Webhook/OAuth-Callback hängen in `main.py` hinter `require_user`.

### Mandantentrennung (`core/tenancy.py`)
Kein `.filter(user_id == …)` von Hand. Eine Middleware in `main.py` setzt den Nutzer aus dem JWT, ein `do_orm_execute`-Hook filtert jedes SELECT sowie Bulk-UPDATE/DELETE der betroffenen Modelle. **Ohne gesetzten Nutzer filtert nichts**: Hintergrundjobs und Skripte sehen alle Athleten. Für Arbeit im Namen eines Athleten `acting_as(user_id)`. Tokens mit `zweck` (z. B. OAuth-`state`) sind kein Zugang.

### Wochen werden über den Montag gewählt
`week_number` ist nur eine Beschriftung relativ zum Anker (Saisonziel oder Profil) und verschiebt sich mit jedem Zielwechsel. Alles, was „diese Woche" meint, rechnet mit `core/wochen.py` (`montag_von`, `kalenderwoche`) und `services/plan_selection.plan_der_woche`. Planstarts liegen immer auf einem Montag. Server-TZ ist `Europe/Berlin` (Dockerfile), `date.today()` ist also Ortszeit.

### Saisonstruktur
Kommt aus dem Ziel, nicht aus Konstanten: `core/race_types.py` (Distanzen, Phasengrenzen, `DELOAD_RHYTHMUS`/`deload_wochen`, `phase_family`). Davor liegt die Grundlage (`services/base_period.py`), danach die Off Season (`services/offseason.py`). Phasenvorgaben je Woche (Qualitäts-/Krafteinheiten, Doppeltage, Rangordnung) stehen in `core/phasenregeln.py`, belegt durch `researched_training_structures/`. Einheitenstrukturen kommen aus `core/einheiten_bibliothek.py`, **nicht** mehr aus `zwift_catalog.py`.

### Plan: Quelle und Projektion
`WeeklyPlan.plan_content` (JSON von Claude) ist die Quelle für Anzeige und PDF. `services/plan_projection.py` projiziert die Tage in `planned_sessions` (DB-Identität für Drag&Drop und Soll/Ist-Abgleich), idempotent je Kalenderwoche. `project_plan` schluckt jede Ausnahme. Was danach geprüft werden muss (z. B. `services/week_shape.bericht`), läuft deshalb **nach** ihr, nicht darin. `week_shape` berichtet nur und lehnt nie ab.

### Drei getrennte Prompt-Pfade
Eine neue Coaching-Regel muss in **alle drei**, sonst kennt sie nur einer:

1. Planerstellung: `services/plan_generator.py` → `core/prompt_templates.py` → `claude_service.generate_weekly_plan` (Tool `create_training_plan`).
2. Anpassung im Planfenster (`POST /api/plan/anpassen`): `services/plan_adjust.py` mit eigenem, handgeschriebenem Systemprompt. Nur das Tool `adjust_training_days`, Ergebnis über `services/plan_merge.py` (vergangene und absolvierte Tage bleiben unverändert).
3. Coach-Chat: `claude_service.chat_with_coach`, Kontext aus `services/coach_context.py`.

`tests/test_rangordnung_alle_pfade.py` macht diese Kreuzprobe für `vorrang_block`, daran orientieren. `tests/test_prompt_signaturen.py` prüft per AST, dass Aufrufstellen und Signaturen der Prompt-Funktionen zusammenpassen.

### Aktivitäten-Eingang
Webhook (`routers/strava_webhook.py`) und stündlicher Abgleich (`services/reconcile.py`, APScheduler in `core/scheduler.py`, nur mit `RECONCILE_ENABLED=true`) laufen beide über `services/ingest.ingest_activity`. Das Matching geht zuerst über die Strava-ID, sonst über Datum, Sportart und Dauer (Verknüpfen statt Dublette). FIT/GPX-Upload über `routers/upload.py` + `services/fit_parser.py`. Klassifikation der Einheiten in `services/classification.py`. Danach optional Sync in den Obsidian-Vault des Athleten (`services/obsidian/`, über Tailscale-SOCKS-Proxy, Schlüssel mit Fernet verschlüsselt über `core/geheim.py`).

### API-Budget
`services/api_budget.py`: reservieren → abrechnen/freigeben um jeden Claude-Aufruf. Ist das Budget erschöpft, wirft er `BudgetExhausted`, `main.py` antwortet mit 402. Modell über `settings.CLAUDE_MODEL`. Der Preis dazu steht getrennt in `MODEL_PRICES` (`modell:eingabe:ausgabe,…`, Dollar je Million Token). Wer das Modell wechselt, trägt dort den Preis mit ein, sonst rechnet `Settings.model_prices` mit dem Ersatzpreis `MODEL_PRICE_FALLBACK` (3,0/15,0). Beide Werte setzt `docker-compose.yml` ebenfalls, die Vorgabe im Compose gilt also lokal vor der in `config.py`.

### Dinge, die synchron bleiben müssen
- `TRAININGSOPTIONEN.md` ↔ `core/phasenregeln.py` (+ `Glossary.jsx`, `src/utils/trainingsoptionen.js`). Ein Test hält Doku und Code zusammen. Compose mountet die `.md` und `researched_training_structures/` read-only in den Container. Ohne diesen Mount schlägt `tests/test_blockoption.py` fehl („Glossar fehlt“).
- `src/utils/phasen.js` spiegelt `core/race_types.phase_family`.
- Frontend-API-Aufrufe nur über `src/services/api.js` (hängt das Token an), Fehlertexte über `src/utils/fehler.js`.

### Weitere Verzeichnisse im Wurzelordner
- `scripts/`: `backup.sh`, `backup-taeglich.sh` (von launchd gestartet, Verbindung aus `~/.ironcoach-db-url`), `restore.sh`.
- `register_webhook.py`: Strava-Webhook anmelden, auflisten, löschen. Werte nur aus Umgebung oder `.env`, nie als Vorgabe im Code.
- `backups/` (Datenbanksicherungen mit allen Nutzerdaten im Klartext), `uploads/` und `workouts/` (hochgeladene FIT-Dateien) sowie der venv `ironcoach/` stehen in `.gitignore`. Nichts davon einchecken oder in Ausgaben zitieren.

## Deployment

GitLab (`main`, Quelle) → Push-Mirror auf GitHub → Railway (Backend + Postgres, Root `ironcoach-api`). Vercel (Frontend, Root `ironcoach-frontend`) hängt per Webhook direkt an GitLab. `/health` liefert den laufenden Commit. Prüfbefehle und Fallen stehen in `DEPLOYMENT.md`, Abschnitt CI/CD. Die `README.md` ist in Teilen veraltet (feste 33 Wochen, Zwift-Katalog, Endpunkttabelle).

## Designentscheidungen

- **Deload im 3:1-Takt, durchgehend gezählt** (`core/race_types.deload_wochen`): jede 4. Planwoche bis vor den Taper, nie im Taper, in der Rennwoche oder in der Woche direkt davor. Grundlage: Raddokument „2–3 load weeks + 1 recovery". Ohne Saisonziel (Grundlage, Off Season) gibt es keine Deload-Zählung.
- **Rangordnung, wenn nicht alles in eine Woche passt** (`phasenregeln.vorrang_block`): Gesundheit > Ruhetag > Grundbasis der Phase (Qualitäts- und Krafteinheiten) > Wunsch des Athleten. Passt die Grundbasis nicht in die freien Tage, setzt der Coach **von selbst** einen Doppeltag (Schwimmen + Kraft zuerst). Erst danach wird ein Wunsch gekürzt, und das steht dann im `coaching_comment`.
- **Wunsch-Knöpfe** (`WunschKnoepfe.jsx`, Quelle `utils/trainingsoptionen.js`): nur Doppeltage und Blockwoche, nach Phase gefiltert. Der Text wird erst beim Absenden zusammengesetzt, nichts wird gespeichert. Eine gemerkte Blockwoche würde sich still jede Woche wiederholen.
- **Testwoche (Benchmark) erst mit Saisonziel.** Die Testeinheiten sollen aufs Rennen abgestimmt sein. Backend: `BenchmarkGesperrt`, `ohne_ziel` in `/benchmark/timing`. Frontend: Kachel ausgegraut mit „ERST ZIEL SETZEN".
- **Automatisch abgeleitete Zonen überschreiben keine Handwerte**: `derive_zones(..., von_hand=False)` lässt manuelle CSS-, Schwellen- und FTP-Werte stehen.
- **HRV-Diagramm:** Die grüne Fläche ist immer die *berechnete* Spanne (gleiche Regeln wie `compute_baseline`, vom Backend mitgeliefert). Die Garmin-Spanne ist eine gestrichelte Linie mit der Marke GARMIN und urteilt allein.
- **Chat-Wochenplan:** Der Systemprompt enthält einen Kalender mit Wochentag und Datum für diese und die kommende Woche. Mit dem Athleten vereinbarte Tage bleiben, wo sie sind. `walk_run` vergibt `classify_run` nur, wenn der Geschwindigkeitsverlauf ≥ 10 % Gehen (< 7 km/h) **und** ≥ 50 % Laufen zeigt. Ein Rennen ist nie Walk-Run.
- **Strava-OAuth:** `state` ist ein 10-Minuten-Zwecktoken. Die Rückleitung legt nur einen offenen Vorgang an, verbunden wird erst nach `POST /api/strava/bestaetigen` aus dem angemeldeten Browser.
- **Sonnet 5.5 mit Effort je Pfad** (`CLAUDE_EFFORT_PLAN` high, `_ANPASSUNG` und `_CHAT` medium in `core/config.py`, übergeben als `output_config`). Kein `tool_choice` „tool“ oder „any“: Sonnet 5.5 antwortet darauf mit 400, das Werkzeug wird über den Systemprompt verlangt. Kein `thinking`- oder `temperature`-Parameter: Thinking läuft immer und zählt in `max_tokens`, deshalb Plan und Chat 16000, Anpassung 8000. SDK bleibt auf 0.x (`anthropic==0.125.0`), 1.x bräuchte httpx2.
- **Name FORGE statt IronCoach** in allem, was Nutzer sehen: Die App deckt auch reine Lauf- und Radziele ab. Alte Plan-Notizvorlagen werden über `_VORLAGE_EIGENES_ALT` weiter erkannt.

## Verworfene Ansätze

- **Rangordnung als Absatz in `doppel_block`:** Der Block wird weder im Chat noch in Off Season, Taper oder Rennwoche gerendert. Deshalb ist es ein eigener Baustein in allen drei Pfaden.
- **Doppeltage ohne Auslöser:** Sie hätten die Belastung aus eigenem Antrieb erhöht. Ein Doppeltag kommt nur, wenn die Grundbasis sonst nicht passt.
- **Knöpfe für Intervallformate:** von Amir abgelehnt. Die Formatrotation entscheidet das schon, ein Knopf wäre eine zweite Quelle.
- **Deload nur am Phasenende**, später je Phase neu gezählt: Das ergab 11 bzw. 5 Belastungswochen am Stück. Ganz früher stand dort `week % 4 == 0`, das machte teils die Rennwoche zum Deload.
- **Garmin-Spanne als Fläche im HRV-Diagramm** (zuletzt durch die Code-Prüfung vom 18.10. wieder eingeführt, mit ff29415 zurückgenommen): Die eigene Rechnung war dann genau für Athleten mit gepflegter Garmin-Spanne unsichtbar. Ebenso verworfen: ein Band aus Mittelwert ± 1σ über 7 Messungen, es lief der Kurve hinterher.
- **Mandantenfilter von Hand an jeder Abfrage:** Die nächste neue Abfrage vergisst ihn. Deshalb der ORM-Hook.
- **Planauswahl über `week_number`:** Die Nummer verschiebt sich mit jedem Zielwechsel, deshalb wird über den Montag gewählt.

## Bekannte Probleme

- **Railway deployt nicht immer automatisch** (zuletzt nach 60a7fd4). Nach dem Push `/health` prüfen und den Commit notfalls in Railway von Hand anstoßen.
- **Der GitLab-Webhook zu Vercel schaltet sich nach mehreren Fehlversuchen selbst ab.** Wieder freigeben über GitLab → Settings → Webhooks → Test.
- **Neue Strava-Apps dürfen nur einen Athleten anbinden.** Alle anderen laden `.fit`-Dateien von Hand hoch.
- **HRV-Diagramm:** Ist eine Garmin-Spanne eingetragen, kann ein Punkt in der berechneten grünen Fläche liegen und trotzdem rot sein. Das ist bewusst so. Angeboten, nicht umgesetzt: die Fläche in diesem Fall grau zeichnen.
- **Der Anmeldeweg hat keine Tests:** `conftest.py` setzt `AUTH_REQUIRED=false`.
- **Korrekturen am Planer wirken nur auf neue Pläne.** Bestehende Pläne in der Produktion werden nicht umgeschrieben (Datenbank nur lesend).

## Offene Aufgaben (Stand 19.10.2026)

- Bei Brevo die IP-Allowlist abschalten, sonst wird der Mailversand vom Server abgelehnt (Amir).
- Auf Railway `MAIL_FROM_NAME=FORGE` setzen, falls dort noch IronCoach steht (Amir).
- Tamina muss ihre Woche im Chat neu durchgeben. Ihr gespeicherter Plan stammt noch von vor dem Fix 59515fe, der die verschobenen Tage und das als Walk-Run eingestufte Rennen behoben hat (`tests/test_chatplan_tamina.py`).
- Nicht bestätigt: der Live-Test der Rangordnung, also eine Woche mit knappen Tagen und „Schwimmen + Kraft" planen und prüfen, ob die zweite Krafteinheit als Doppeltag kommt, ohne dass der Ruhetag geopfert wird.

## Feste Absprachen

- Commit und Push nur auf ausdrückliche Bitte.
- Produktionsdatenbank nur lesend.
- `services/offseason.py` nicht anfassen.
- `/obsidian/neu-ordnen` nicht ausführen.
- Das von Hand gesetzte Garmin-HRV-Band hat Vorrang vor jeder berechneten Grenze.
- Walk-Run, Trab-Bricks und Gehpausen nie als Vorgabe für alle, nur als Reaktion auf eine gemeldete Beschwerde (`services/health.py`) oder auf Wunsch. Die Brick-Regeln hält `tests/test_brick_regeln.py` fest.
- Unverändert lassen trotz Umbenennung auf FORGE: Marker `<!-- ironcoach:start/end -->`, `ironcoach_token`, DB- und Reponamen.
