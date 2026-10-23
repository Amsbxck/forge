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

### HRV-Eingang (Garmin Personal API)
Jeder Athlet trägt auf **Anbindungen** in der Kachel „GARMIN CONNECT" seinen eigenen persönlichen API-Schlüssel ein (verschlüsselt wie der Obsidian-Schlüssel). Pull-only, nichts kommt von selbst: `services/garmin_personal.py` (Client, Token-Tausch + generische GET-Hilfe, Transport für Tests injizierbar) und `services/garmin_hrv.py` (`tage_uebernehmen`, `spanne_uebernehmen`, `abgleich_fuer`). Der Token gilt 24 h und wird nicht gespeichert, jeder Lauf tauscht neu. Der Schlüssel läuft nach höchstens einem Jahr ab, danach zeigt die Kachel den Fehler und das Schlüsselfeld. Zwei Jobs in `core/scheduler.py`, nur mit `GARMIN_SYNC_ENABLED=true` (unabhängig von `RECONCILE_ENABLED`): `garmin_hrv_morgens` (7–12 Uhr stündlich zur Minute `GARMIN_MINUTE`, 7 Tage Rückblick, Athlet mit heutigem Garmin-Wert wird ausgelassen) und `garmin_spanne_sonntag` (13:15, mit Spanne). Beim Verbinden einmal sofort 30 Tage samt Spanne. Mit Garmin lehnt `POST /hrv` die Handeingabe ab (409), Garmins Wert überschreibt einen manuellen am selben Tag.

### API-Budget
`services/api_budget.py`: reservieren → abrechnen/freigeben um jeden Claude-Aufruf. Ist das Budget erschöpft, wirft er `BudgetExhausted`, `main.py` antwortet mit 402. Modell über `settings.CLAUDE_MODEL`. Der Preis dazu steht getrennt in `MODEL_PRICES` (`modell:eingabe:ausgabe,…`, Dollar je Million Token). Wer das Modell wechselt, trägt dort den Preis mit ein, sonst rechnet `Settings.model_prices` mit dem Ersatzpreis `MODEL_PRICE_FALLBACK` (3,0/15,0). Beide Werte setzt `docker-compose.yml` ebenfalls, die Vorgabe im Compose gilt also lokal vor der in `config.py`.

### Anzeige-Bausteine (`ironcoach-frontend/src/components/leisten/`)
Zahlen stehen im Kontext statt als Text, überall in derselben ruhigen Optik (Amir mag die Leisten, Ampellampen und Zierstriche hat er gestrichen):
- `SpannenSkala`: Wert in der eigenen Spanne, mit `hrvZonen(spanne)`.
- `SegmentLeiste`: Anteile, wie die Urne, die HF-Zonen der Woche und der Budgetverbrauch.
- `SollIstLeiste`: Soll als Rahmen, Ist als Füllung, Überschuss schraffiert.
- `SaisonStrahl`: Phasen, Deloads, Rennen und heute nach Datum. Läuft auf Dashboard, Plan und Rennen.
  - Gezeichnet werden die Blöcke (`teile` je Phase aus `phase_for_week`, je 3 + 1 Wochen, siehe Designentscheidungen).
  - Die Kopfzeile zeigt vor dem Planstart „PLAN STARTS IN n WEEKS“, danach den nächsten Block mit Datum. Den nächsten Deload zeigt sie bewusst nicht mehr (Amir: bringt nichts).

Die Verlauf-Seite nutzt dazu `WochenVolumen` (Stunden je Woche, darunter ein Phasenband aus `plan_phase` der Wochenpläne, Deload-Dreiecke nur für die laufende Saison aus `/metrics/saison`) und `TrainingsJahr` (Tages-Heatmap, Farbe = Hauptsportart, Helligkeit = TSS). Sie rechnet nur im Browser aus den geladenen zwei Jahren (`utils/einheiten.js`), gelöschte Einheiten zählen nicht.

Die THIS-WEEK-Kachel im Dashboard ist `WocheHero`: große Zahlen, Wochenband Mo–So (absolviert gefüllt, geplant als Umriss aus `/planned/am/{montag}`), Ist gegen Plan aus der Bilanz und 8 Wochen Stunden. Der Vergleich zur Vorwoche zählt nur **bis zum selben Wochentag**, sonst stünde jeder Mittwoch gegen eine volle Woche im Minus.

Die PERFORMANCE-Kachel (`components/PerformanceChart.jsx`, eigenes SVG ohne Recharts) bekommt `pmc`, ein Jahr Einheiten, Saison und den Plan zweier Wochen vom Dashboard und lädt nichts selbst.
- Die Lücke zwischen Fitness und Ermüdung ist die Form, darunter das Form-Band mit den Zonen aus `utils/form.js`. Das ist die einzige Quelle der Schwellen, auch für `formLabel`/`formColor`.
- Die gestrichelte Vorschau rechnet mit den `target_tss` der geplanten Tage nach heute und denselben Konstanten wie `season_summary._pmc`.
- Fitness ist bewusst weiß statt cyan, Cyan las sich neben den Sportfarben als Schwimmen.

Die Leisten und die HRV History sind **englisch beschriftet** (Amirs Wunsch, nur dort; der Rest der App bleibt deutsch).

Die HRV-Karte zeigt Ø 7 und den Tageswert nebeneinander. Die Skala beschriftet ihre Marken (Ø darüber, Ring für heute darunter). Eine 14-Tage-Linie hat Amir gestrichen, ebenso „Tage im Bereich“ in der HRV History. Deren x-Achse ist eine Zeitachse, der Zeitraum zählt nach Tagen statt nach Messungen.

Die Daten kommen aus Lese-Endpunkten, die nichts nachrechnen, sondern die Funktionen des Planers aufrufen:
- `GET /metrics/saison` (`race_types`),
- `GET /planned/am/{montag}/bilanz` (Soll/Ist je Disziplin und Einheit, über `planned_session_id` **und** `matched_session_id`),
- `GET /hrv/lage` (`doppel_urne.hrv_lage`),
- `je_art` in `GET /budget`.

`hr_zones_avg` in `/metrics/week` ist nach Dauer gewichtet. Getestet in `tests/test_anzeige_endpunkte.py`.

### Dinge, die synchron bleiben müssen
- `TRAININGSOPTIONEN.md` ↔ `core/phasenregeln.py` (+ `Glossary.jsx`, `src/utils/trainingsoptionen.js`). Ein Test hält Doku und Code zusammen. Compose mountet die `.md` und `researched_training_structures/` read-only in den Container. Ohne diesen Mount schlägt `tests/test_blockoption.py` fehl („Glossar fehlt“).
- `src/utils/phasen.js` spiegelt `core/race_types.phase_family`.
- Frontend-API-Aufrufe nur über `src/services/api.js` (hängt das Token an), Fehlertexte über `src/utils/fehler.js`.

### Weitere Verzeichnisse im Wurzelordner
- `scripts/`: `backup.sh`, `backup-taeglich.sh` (von launchd gestartet, Verbindung aus `~/.ironcoach-db-url`), `restore.sh`, `prod-nach-lokal.sh`.
  - `prod-nach-lokal.sh` holt die Produktion in die lokale DB, nur lesend und nach einer lokalen Sicherung. Danach löscht es lokal `strava_credentials`, **bevor** das Backend startet. Grund: Ein lokaler Token-Refresh (`RECONCILE_ENABLED`) macht den Refresh-Token der Produktion ungültig.
  - Das Skript startet Amir selbst. Claude Code darf die Produktionsdaten nicht abziehen, die Berechtigungsprüfung blockiert das.
- `register_webhook.py`: Strava-Webhook anmelden, auflisten, löschen. Werte nur aus Umgebung oder `.env`, nie als Vorgabe im Code.
- `backups/` (Datenbanksicherungen mit allen Nutzerdaten im Klartext), `uploads/` und `workouts/` (hochgeladene FIT-Dateien) sowie der venv `ironcoach/` stehen in `.gitignore`. Nichts davon einchecken oder in Ausgaben zitieren.

## Deployment

GitLab (`main`, Quelle) → Push-Mirror auf GitHub → Railway (Backend + Postgres, Root `ironcoach-api`). Vercel (Frontend, Root `ironcoach-frontend`) hängt per Webhook direkt an GitLab. `/health` liefert den laufenden Commit. Prüfbefehle und Fallen stehen in `DEPLOYMENT.md`, Abschnitt CI/CD. Die `README.md` ist in Teilen veraltet (feste 33 Wochen, Zwift-Katalog, Endpunkttabelle).

## Designentscheidungen

- **Deload im 3:1-Takt, durchgehend gezählt** (`core/race_types.deload_wochen`): jede 4. Planwoche bis vor den Taper, nie im Taper, in der Rennwoche oder in der Woche direkt davor. Grundlage: Raddokument „2–3 load weeks + 1 recovery". Ohne Saisonziel (Grundlage, Off Season) gibt es keine Deload-Zählung.
- **Phasen und Blöcke im selben Takt** (`race_types.phase_boundaries`, `phase_for_week`): Die Grenzen Base→Build und Build→Peak rasten auf die nächste Deload-Woche ein, jeder Block (Base 1, Base 2 …) ist 3 + 1. Bei Gleichstand ist Base länger, und Peak behält mindestens 4 Wochen (`MIN_PEAK_IM_TAKT`), sonst wird Build länger. Der Peak-Rest nach dem letzten Deload ist ein eigener Block, eine einzelne Restwoche hängt am Block davor. Pläne mit weniger als zwei Deloads vor dem Taper (unter 11 Wochen) behalten die Anteile. Taper und Deload-Wochen hat das nicht verändert (Test in `tests/test_deload_rhythmus.py`). Vorher wurden Phasen nur nach Anteil geteilt und gedrittelt: Bei 20 Wochen begann Build mit einem Deload. Gilt nur für neue Pläne, gespeicherte `plan_phase` bleiben.
- **Rangordnung, wenn nicht alles in eine Woche passt** (`phasenregeln.vorrang_block`): Gesundheit > Ruhetag > Grundbasis der Phase (Qualitäts- und Krafteinheiten) > Wunsch des Athleten. Passt die Grundbasis nicht in die freien Tage, setzt der Coach **von selbst** einen Doppeltag (Schwimmen + Kraft zuerst). Erst danach wird ein Wunsch gekürzt, und das steht dann im `coaching_comment`. Die Off Season (also jeder ohne Ziel) hat eine eigene Fassung (`_offseason_vorrang`): Im Formerhalt kommt bei Engpass ein lockerer Doppeltag für 2× Kraft und 2 Einheiten je Disziplin, im Übergang nie. `offseason.py` bleibt unverändert, ein Test hält die Zahlen zusammen.
- **Wunsch-Knöpfe** (`WunschKnoepfe.jsx`, Quelle `utils/trainingsoptionen.js`): nur Doppeltage und Blockwoche, nach Phase gefiltert. „Schwimmen + Kraft" hat keinen Knopf mehr, das setzen Grundbasis-Regel und Urne von selbst. Textfeld, Ziehung, Knöpfe und Absenden stehen zusammen in `WunschKonsole.jsx`. Der Text wird erst beim Absenden zusammengesetzt, nichts wird gespeichert. Eine gemerkte Blockwoche würde sich still jede Woche wiederholen.
- **Doppeltag-Urne** (`services/doppel_urne.py`): Vor dem Erstellen zieht die App je Woche eine Doppeltag-Form oder „keine", gewichtet nach HRV (unter der Spanne nur lockeres Schwimmen, Doppelschwelle nur bei green und nach einem absolvierten Doppeltag), Vorwochen (Form der Vorwoche ×0, vor zwei Wochen ×0,5) und Wochenlage (Deload, Rennwoche und Off Season: keine). Gesät mit Athlet und Montag, bei gleichem Stand von HRV und Vorwochen also dieselbe Ziehung in Kachel und Plan. Die Plankachel zeigt sie an (`GET /plan/doppeltag/am/{montag}`, `DoppeltagZiehung.jsx`), darüber die HRV als Ampel mit dem 7-Tage-Schnitt (`HrvAmpel.jsx`, `doppel_urne.hrv_lage`; die Farbe ist der Status, mit dem die Urne gewichtet, nicht ein Urteil über den Schnitt). Der Baustein geht in den einen Erstell-Aufruf mit. Im Chat nur, solange die Woche keinen Plan hat, und bedingt formuliert („nur falls du den Wochenplan schreibst"), sonst steht dort, was der Plan trägt. „Ohne Doppeltag" (`generate?doppeltag=false`), ein gewählter Doppeltag-Knopf und die Blockwoche schalten ihn ab, gespeichert wird nichts. Die Neuplanung nach einer Gesundheitsmeldung plant ohne. **Umlegen statt Hinzufügen** (`phasenregeln.UMLEGEN`, in `doppel_block` und `vorrang_block`): Ein Doppeltag entsteht aus vorhandenen Einheiten. Im Taper nur lockeres Schwimmen und nie von selbst (`doppel_auf_wunsch`, `TAPER_SCHWIMMEN`).
- **Testwoche (Benchmark) erst mit Saisonziel.** Die Testeinheiten sollen aufs Rennen abgestimmt sein. Backend: `BenchmarkGesperrt`, `ohne_ziel` in `/benchmark/timing`. Frontend: Kachel ausgegraut mit „ERST ZIEL SETZEN".
- **Automatisch abgeleitete Zonen überschreiben keine Handwerte**: `derive_zones(..., von_hand=False)` lässt manuelle CSS-, Schwellen- und FTP-Werte stehen.
- **HRV-Diagramm:** Die grüne Fläche ist immer die *berechnete* Spanne (gleiche Regeln wie `compute_baseline`, vom Backend mitgeliefert). Eine Garmin-Linie gibt es nicht mehr (die Spanne steht im Profil). Mit Garmin urteilen die Punktfarben nach Garmins Spanne, das sagt ein Satz unter dem Diagramm.
- **Chat-Wochenplan:** Der Systemprompt enthält einen Kalender mit Wochentag und Datum für diese und die kommende Woche. Mit dem Athleten vereinbarte Tage bleiben, wo sie sind. `walk_run` vergibt `classify_run` nur, wenn der Geschwindigkeitsverlauf ≥ 10 % Gehen (< 7 km/h) **und** ≥ 50 % Laufen zeigt. Ein Rennen ist nie Walk-Run.
- **Strava-OAuth:** `state` ist ein 10-Minuten-Zwecktoken. Die Rückleitung legt nur einen offenen Vorgang an, verbunden wird erst nach `POST /api/strava/bestaetigen` aus dem angemeldeten Browser.
- **Sonnet 5.5 mit Effort je Pfad** (`CLAUDE_EFFORT_PLAN` high, `_ANPASSUNG` und `_CHAT` medium in `core/config.py`, übergeben als `output_config`). Kein `tool_choice` „tool“ oder „any“: Sonnet 5.5 antwortet darauf mit 400, das Werkzeug wird über den Systemprompt verlangt. Kein `thinking`- oder `temperature`-Parameter: Thinking läuft immer und zählt in `max_tokens`, deshalb Plan und Chat 16000, Anpassung 8000. SDK bleibt auf 0.x (`anthropic==0.125.0`), 1.x bräuchte httpx2.
- **Name FORGE statt IronCoach** in allem, was Nutzer sehen: Die App deckt auch reine Lauf- und Radziele ab. Alte Plan-Notizvorlagen werden über `_VORLAGE_EIGENES_ALT` weiter erkannt.

## Verworfene Ansätze

- **Rangordnung als Absatz in `doppel_block`:** Der Block wird weder im Chat noch in Off Season, Taper oder Rennwoche gerendert. Deshalb ist es ein eigener Baustein in allen drei Pfaden.
- **Doppeltage ohne Auslöser, die eine Einheit hinzufügen:** Sie hätten die Belastung aus eigenem Antrieb erhöht. Die Doppeltag-Urne legt deshalb nur um, statt hinzuzufügen.
- **Doppeltag-Vorschläge nach dem Erstellen zum Annehmen:** Jede Annahme war ein zweiter Claude-Aufruf (`/plan/anpassen`) und fügte eine Einheit hinzu (aus zwei Schwimmeinheiten wurden drei). Ersetzt durch die Urne vor dem Erstellen.
- **Knöpfe für Intervallformate:** von Amir abgelehnt. Die Formatrotation entscheidet das schon, ein Knopf wäre eine zweite Quelle.
- **Deload nur am Phasenende**, später je Phase neu gezählt: Das ergab 11 bzw. 5 Belastungswochen am Stück. Ganz früher stand dort `week % 4 == 0`, das machte teils die Rennwoche zum Deload.
- **Garmin-Spanne als Fläche im HRV-Diagramm** (zuletzt durch die Code-Prüfung vom 18.10. wieder eingeführt, mit ff29415 zurückgenommen): Die eigene Rechnung war dann genau für Athleten mit gepflegter Garmin-Spanne unsichtbar. Ebenso verworfen: ein Band aus Mittelwert ± 1σ über 7 Messungen, es lief der Kurve hinterher.
- **Mandantenfilter von Hand an jeder Abfrage:** Die nächste neue Abfrage vergisst ihn. Deshalb der ORM-Hook.
- **Planauswahl über `week_number`:** Die Nummer verschiebt sich mit jedem Zielwechsel, deshalb wird über den Montag gewählt.

## Bekannte Probleme

- **Railway deployt nicht immer automatisch** (zuletzt nach 60a7fd4). Nach dem Push `/health` prüfen und den Commit notfalls in Railway von Hand anstoßen.
- **Der GitLab-Webhook zu Vercel schaltet sich nach mehreren Fehlversuchen selbst ab.** Wieder freigeben über GitLab → Settings → Webhooks → Test.
- **Neue Strava-Apps dürfen nur einen Athleten anbinden.** Alle anderen laden `.fit`-Dateien von Hand hoch.
- **HRV-Diagramm:** Gilt eine Garmin-Spanne, kann ein Punkt in der berechneten grünen Fläche liegen und trotzdem rot sein. Das ist bewusst so. Angeboten, nicht umgesetzt: die Fläche in diesem Fall grau zeichnen.
- **Garmin Personal API ist nicht offiziell dokumentiert:** Endpunkte und Feldnamen stammen aus dem inoffiziellen Client gcpapi-sync und werden von Garmin nicht garantiert. Am 23.10.2026 live geprüft: Der Token-Tausch liefert das JWT als `text/plain` (nicht als JSON, anders als im inoffiziellen Client beschrieben) und antwortet auf `Accept: application/json` mit 406. Die HRV-Antwort entsprach der erwarteten Form.
- **Railway braucht `GARMIN_SYNC_ENABLED=true`**, sonst laufen die Garmin-Jobs nicht (die Kachel sagt das dann, „Jetzt abrufen" geht trotzdem). Prüfen über `/api/strava/scheduler` (`garmin_enabled`, Jobs `garmin_hrv_morgens` und `garmin_spanne_sonntag`).
- **Der Anmeldeweg hat keine Tests:** `conftest.py` setzt `AUTH_REQUIRED=false`.
- **Einzeln gemountete Dateien (`TRAININGSOPTIONEN.md`) verlieren nach dem Bearbeiten den Mount:** Editoren und `sed -i` schreiben eine neue Datei, der Container sieht weiter die alte oder keine („Glossar fehlt“). Danach `docker compose restart backend`.
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
- Garmins Baseline (automatisch, sonntags aktualisiert) hat Vorrang vor jeder berechneten Grenze. Die Spanne ist nicht von Hand änderbar.
- Walk-Run, Trab-Bricks und Gehpausen nie als Vorgabe für alle, nur als Reaktion auf eine gemeldete Beschwerde (`services/health.py`) oder auf Wunsch. Die Brick-Regeln hält `tests/test_brick_regeln.py` fest.
- Unverändert lassen trotz Umbenennung auf FORGE: Marker `<!-- ironcoach:start/end -->`, `ironcoach_token`, DB- und Reponamen.
