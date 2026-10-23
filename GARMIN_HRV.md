# Aufgabe: HRV automatisch aus Garmin Connect (Personal API)

Ziel: Jeder Athlet trägt auf der Seite **Anbindungen** seinen eigenen Garmin-Personal-API-Schlüssel ein. Danach holt FORGE die nächtliche HRV jeden Morgen selbst ab und aktualisiert jeden Sonntag die Normalspanne aus Garmins Baseline. Von Hand wird weder die tägliche HRV noch die Spanne eingetragen.

Lies vorher `CLAUDE.md`. Alle dort genannten Regeln gelten weiter: deutsche Bezeichner und Kommentare mit dem *Warum*, Tests nur im Backend-Container, eine Migration zu jeder Modelländerung, Mandantentrennung über `acting_as`, kein Commit und kein Push ohne ausdrückliche Bitte.

---

## Entscheidungen von Amir (fest, nicht neu verhandeln)

1. **Garmins Baseline hat Vorrang.** Garmin liefert seinen grünen Bereich (`balancedLow`–`balancedUpper`). Das ist genau der Wert, den Amir bisher von Hand abgetippt hat. Er ersetzt das Abtippen und gilt mit demselben Vorrang wie heute `hrv_range_source == "manual"`.
2. **Neue Kachel „GARMIN CONNECT“** auf `pages/Integrations.jsx`, direkt **unter** der Strava-Kachel. Sie ist gleich aufgebaut wie die Strava-Kachel, aber in Garmin-Farben.
3. **Pro Athlet ein eigener Schlüssel**, verschlüsselt gespeichert wie der Obsidian-Schlüssel.
4. **Tägliche HRV automatisch**, sobald der Schlüssel eingetragen ist.
5. **Spanne im Profil weiter sichtbar** (`components/HrvRange.jsx`), aber **nicht mehr von Hand änderbar**. Anzeige und Ampel-Logik bleiben, wie sie sind.
6. **Spanne wird jeden Sonntag aktualisiert**, damit die Grenzen aktuell bleiben. Zusätzlich einmal sofort beim Verbinden.
7. **Dashboard-Diagramm** (`components/HRVHistoryChart.jsx`): Die berechnete Normalspanne (grüne Fläche) bleibt. Die dort eingezeichnete **Garmin-Spanne fällt weg**.
8. Die Nutzungsbedingungen der Personal API („nicht für kommerzielle Apps mit vielen Nutzern“) nimmt Amir bewusst in Kauf, weil FORGE nicht kommerziell ist. Kein Warnhinweis in der App.

---

## Garmin Personal API: was bekannt ist

Quellen: [Personal API](https://developer.garmin.com/gc-developer-program/personal/personal-api/), [FAQ](https://developer.garmin.com/gc-developer-program/personal/personal-faq/). Die Endpunkte und Feldnamen stammen aus dem inoffiziellen Client [gcpapi-sync](https://github.com/thomascamminady/gcpapi-sync) (`_endpoints.py`, `models/_generated.py`), weil Garmins Swagger-Seite ohne Anmeldung nichts zeigt.

- **Basis-URL:** `https://personal.connectapi.garmin.com`
- **Schlüssel gegen Token tauschen:** `POST /personalapitoken-service/personal-api/personal-api-key/token` mit Header `Authorization: ApiKey <schlüssel>`. Die Antwort ist ein OAuth2-Access-Token.
- **Token:** gilt 24 h oder bis der Schlüssel abläuft. Refresh-Tokens gibt es nicht, also einfach erneut tauschen. Der Token wird nicht gespeichert, jeder Joblauf tauscht neu.
- **Schlüssel:** läuft nach 30, 90, 180 Tagen oder 1 Jahr ab (Wahl beim Anlegen). Garmin schickt etwa eine Woche vorher eine Mail. Ein gelöschter Schlüssel macht alle daraus erzeugten Tokens ungültig.
- **Nur Pull:** Es kommt nichts von selbst, FORGE muss fragen.
- **HRV-Endpunkt:** `GET /hrv-service/hrv/daily/{von}/{bis}` mit Daten im Format `YYYY-MM-DD` und `Authorization: Bearer <token>`. Die Antwort sieht so aus:
  ```json
  {
    "userProfilePk": 123,
    "hrvSummaries": [
      {
        "calendarDate": "2026-10-23",
        "weeklyAvg": 78,
        "lastNightAvg": 81,
        "lastNight5MinHigh": 104,
        "status": "BALANCED",          // NONE | POOR | LOW | UNBALANCED | BALANCED | INVALID
        "baseline": { "lowUpper": 62, "balancedLow": 70, "balancedUpper": 92, "markerValue": 0.4 }
      }
    ]
  }
  ```
  Der Client teilt Zeiträume in Fenster von höchstens 365 Tagen. Für den Rückblick reichen 30 Tage.
- **Einzelner Tag** (falls nötig): `GET /hrv-service/hrv/{tag}` liefert `hrvSummary` und die Einzelwerte.
- **Noch keine Daten:** Hat die Uhr nach dem Aufwachen noch nicht synchronisiert, fehlt der Tag oder `lastNightAvg` ist leer. Das ist kein Fehler.
- **Rate-Limits:** nicht dokumentiert. Bei HTTP 429 `Retry-After` beachten und den Athleten bis zum nächsten Lauf auslassen.

**Zuerst prüfen:** Die Feldnamen stammen aus einem inoffiziellen Client. Bevor du darauf aufbaust, mit einem echten Schlüssel (Amir gibt dir einen oder testet selbst) **einmal** die Rohantwort von Token- und HRV-Endpunkt ansehen und den Parser danach ausrichten. Schlüssel und Token dabei nie ausgeben oder loggen.

Kein neues Paket einbinden. Es sind zwei Endpunkte, das geht mit dem vorhandenen `httpx` wie in `services/strava_service.py`.

---

## Backend

### 1. Migration `040_garmin_hrv.py` und Modelle

`AthleteProfile` (neben den Obsidian-Feldern, mit Kommentar warum):
- `garmin_api_key: VerschluesselterText`: wie `obsidian_api_key`, Begründung siehe `core/geheim.py`.
- `garmin_verbunden_am: DateTime | None`
- `garmin_letzter_abruf: DateTime | None`: letzter erfolgreicher Abruf.
- `garmin_letzter_fehler: String | None`: Klartext für die Kachel, z. B. „Schlüssel ungültig oder abgelaufen“. Wird bei Erfolg geleert.

`HrvMeasurement`:
- `quelle: String | None`: `"garmin"` oder `"manual"`. Alte Zeilen bleiben `NULL` und gelten als manuell.

`hrv_range_source` bekommt den neuen Wert `"garmin"`.

`tests/test_schema_migrationen.py` muss danach grün sein.

### 2. `services/garmin_personal.py` (neu)

- `async def token_holen(api_key) -> str`
- `async def hrv_tage(token, von, bis) -> list[dict]`: gibt die Liste `hrvSummaries` zurück.
- Den `httpx.AsyncClient` bzw. Transport injizierbar machen, damit Tests `httpx.MockTransport` nutzen können. `respx` ist nicht installiert und soll es auch nicht werden.
- Eigene Ausnahmen: `GarminSchluesselUngueltig` (401/403 beim Tausch oder Abruf), `GarminRateLimit` (429, mit `retry_after`), `GarminNichtErreichbar` (Netz/5xx).
- Basis-URL über `settings.GARMIN_PERSONAL_BASE_URL` (Vorgabe siehe oben).

### 3. `services/garmin_hrv.py` (neu): die Logik

**`tage_uebernehmen(db, user, summaries) -> dict`**
- Pro Summary mit gültigem `lastNightAvg` (nicht leer, `status` nicht `NONE`/`INVALID`) eine Messung für `calendarDate` anlegen oder aktualisieren:
  - Gibt es für den Tag schon eine Zeile, wird die erste (kleinste `id`) mit `rmssd = lastNightAvg` und `quelle = "garmin"` überschrieben. Garmin ist die Quelle.
  - Weitere Zeilen desselben Tags bleiben unangetastet. Es gibt in Bestandsdaten Tage mit zwei Messungen (siehe Kommentar in `HRVHistoryChart.jsx`), und gelöscht wird nichts automatisch.
  - Gibt es noch keine Zeile, wird eine neu angelegt.
  - Idempotent: Ein zweiter Lauf mit denselben Daten ändert nichts.
- Danach **einmal** `hrv_baseline.recompute_all(db, user)` aufrufen, damit Status und Farben zur geltenden Spanne passen. Das macht `POST /hrv` heute genauso.
- Rückgabe für Log und Kachel: `{"neu": n, "aktualisiert": m, "ohne_daten": k}`.

**`spanne_uebernehmen(db, user, summaries) -> bool`**
- Die jüngste Summary mit `baseline.balancedLow` und `balancedUpper` nehmen.
- Danach genau wie heute in `POST /hrv/range` verfahren: `hrv_green_min = balancedLow`, `hrv_band_high = balancedUpper`, `hrv_red_below = red_from_band(...)`. Die Ableitung der roten Grenze bleibt unverändert. `lowUpper` wird bewusst **nicht** verwendet, weil Amir will, dass es so bleibt, wie es ist.
- `hrv_range_source = "garmin"`, danach `recompute_all`.
- Ohne Baseline (Garmin ist noch in der Lernphase, die ersten ca. 3 Wochen) nichts ändern und `False` zurückgeben.

**`abgleich_fuer(db, user, tage=7, mit_spanne=False)`**
- Bündelt Token holen, `hrv_tage(heute - tage, heute)`, `tage_uebernehmen` und optional `spanne_uebernehmen`. Die Spanne nimmt die Summaries aus demselben Abruf, es gibt keinen zweiten Aufruf.
- 7 Tage Rückblick, damit ein verpasster Morgen (Rechner aus, Garmin langsam) von selbst nachgeholt wird.
- Setzt `garmin_letzter_abruf` bzw. `garmin_letzter_fehler`.
- Bei `GarminSchluesselUngueltig`: Fehlertext setzen und abbrechen. **Schlüssel nicht löschen**, der Athlet soll in der Kachel sehen, was los ist.

### 4. `services/hrv_baseline.thresholds_for`

- `"garmin"` bekommt denselben unbedingten Vorrang wie `"manual"`, Rückgabe `"quelle": "garmin"`.
- `"manual"` bleibt lesbar: Wer heute ein eingetragenes Band hat und Garmin nicht verbindet, behält es. Ein Setzen über die Oberfläche gibt es nicht mehr (siehe unten).
- Docstring nachziehen.

### 5. Scheduler (`core/scheduler.py`)

- Neue Einstellung `GARMIN_SYNC_ENABLED: bool = False` in `core/config.py`. Begründung im Kommentar: Auch dieser Job schreibt in die DB und redet nach außen, also soll ein Container-Neustart ihn nicht versehentlich auslösen. Er ist unabhängig von `RECONCILE_ENABLED`, denn wer Strava nicht nutzt, soll trotzdem HRV bekommen.
- `start_scheduler` startet, wenn **eines** der beiden Flags gesetzt ist, und hängt nur die jeweils aktivierten Jobs an. `scheduler_status` entsprechend anpassen.
- **Job `garmin_hrv_morgens`:** `CronTrigger(hour="7-12", minute=settings.GARMIN_MINUTE)`, Vorgabe `GARMIN_MINUTE = 23`, damit er nicht mit Reconcile (Minute 7) zusammenfällt. Zeitzone wie die bestehenden Jobs über `ZoneInfo("Europe/Berlin")`.
  - Nutzer-IDs aller Profile mit `garmin_api_key` (mit `SKIP_OPTION` wie in `_reconcile_job`).
  - Für jeden Athleten eine **eigene Session** in `acting_as(user_id)`. Das Muster mit Begründung steht schon in `_reconcile_job`.
  - Einen Athleten auslassen, wenn für **heute** schon eine Messung mit `quelle == "garmin"` existiert. Sobald der Wert da ist, fragen die restlichen Läufe des Vormittags also nicht mehr.
  - Ein Fehler bei einem Athleten hält die anderen nicht auf.
- **Job `garmin_spanne_sonntag`:** `CronTrigger(day_of_week="sun", hour=13, minute=15)` ruft `abgleich_fuer(..., mit_spanne=True)` auf. Um 13 Uhr hat die Uhr sicher synchronisiert.
- `tests/conftest.py`: `GARMIN_SYNC_ENABLED=false` setzen, so wie heute `RECONCILE_ENABLED`.

### 6. Router `routers/integrations.py`

- `GET /integrations`: neuer Block
  `"garmin": {"configured", "api_key_hint" (über _mask), "verbunden_am", "letzter_abruf", "letzter_fehler", "sync_aktiv": settings.GARMIN_SYNC_ENABLED}`.
  `sync_aktiv` braucht die Kachel, damit sie nicht „automatisch“ verspricht, wenn der Job auf Railway gar nicht läuft.
- `PUT /integrations/garmin` mit `{api_key}`:
  - Zuerst Token tauschen. Ist der Schlüssel ungültig, kommt 422 mit verständlichem Text, und es wird **nichts gespeichert**.
  - Bei Erfolg verschlüsselt speichern, `garmin_verbunden_am` setzen und sofort einen Rückblick über **30 Tage mit Spanne** fahren (`abgleich_fuer(tage=30, mit_spanne=True)`). So sieht der Athlet direkt Werte und muss nicht bis morgen bzw. Sonntag warten.
  - Antwort: Integrationszustand plus Ergebnis (`neu`, `aktualisiert`, Spanne übernommen ja/nein).
- `POST /integrations/garmin/abrufen` für den Knopf „JETZT ABRUFEN“ in der Kachel. Holt 7 Tage, ohne Spanne.
- `DELETE /integrations/garmin`: Schlüssel und Status-Felder leeren. Bereits übernommene Messungen bleiben. `hrv_range_source` bleibt `"garmin"` mit den letzten Werten, bis wieder verbunden wird. Das im Kommentar begründen: Eine Trennung soll die Ampel nicht still auf die berechnete Spanne umstellen.

### 7. `routers/hrv.py`

- `POST /hrv`: Ist Garmin verbunden, mit 409 ablehnen („HRV kommt automatisch aus Garmin Connect“). Ohne Garmin bleibt die Handeingabe. Athleten ohne Garmin-Uhr hätten sonst gar keine HRV. Manuelle Messungen bekommen `quelle = "manual"`.
- `POST /hrv/range` und `DELETE /hrv/range`: **entfernen**, samt `setHrvRange`/`clearHrvRange` in `src/services/api.js`. Die Spanne ist nicht mehr von Hand änderbar. Bestehende Tests, die diese Endpunkte nutzen, auf `spanne_uebernehmen` bzw. direktes Setzen am Profil umstellen.
- `GET /hrv/range`: unverändert, liefert `quelle: "garmin"` mit.

### 8. Datenexport `services/account_export.py`

- `garmin_api_key` in die Liste der Felder aufnehmen, die **nie** exportiert werden (dort, wo heute `obsidian_api_key` steht).

---

## Frontend

### 1. Kachel „GARMIN CONNECT“ (`pages/Integrations.jsx`)

- Position: zwischen der Strava-Kachel und der Obsidian-Kachel.
- Aufbau wie Strava: `CARD`, linker Rand `3px solid <Garmin-Farbe>`, Titel `GARMIN CONNECT` in `DISPLAY`, kurzer Text, `Status`-Punkt, Rückmeldebox grün/rot im selben Stil.
- **Farbe:** Garmin-Blau. Vorschlag `#007CC3`, vorher gegen das aktuelle Garmin-Connect-Logo prüfen. Gleiche Tönung wie beim Strava-Knopf: Hintergrund `<farbe>20`, Rand `<farbe>55`, Schrift `<farbe>`.
- Text: „Holt jeden Morgen deine nächtliche HRV und jeden Sonntag deine Normalspanne direkt aus Garmin Connect. Dafür brauchst du einen persönlichen API-Schlüssel.“
- **Nicht verbunden:** Passwortfeld `API-SCHLÜSSEL` und Knopf `VERBINDEN`. Darunter ein eingeklapptes `<details>` „So bekommst du den Schlüssel“:
  1. In Garmin Connect im Browser anmelden und `connect.garmin.com/app/settings/personalApiToken` öffnen.
  2. „Create Key“ wählen, die Bedingungen akzeptieren und als Ablauf **1 Jahr** wählen.
  3. Den Schlüssel sofort kopieren, denn Garmin zeigt ihn nur einmal.
  4. Hier einfügen und „Verbinden“ drücken.
  5. Läuft der Schlüssel ab, schickt Garmin eine Woche vorher eine Mail. Dann einen neuen anlegen und hier eintragen.
- **Verbunden:** Status „Verbunden · Schlüssel …abcd“, dazu „Letzter Abruf: <Datum Uhrzeit>“. Bei `letzter_fehler` erscheint eine rote Box mit dem Text und das Schlüsselfeld wieder (Schlüssel ersetzen). Knöpfe: `JETZT ABRUFEN` und `TRENNEN` (mit `confirm`, Text: „Bereits geholte HRV-Werte bleiben erhalten.“).
- Ist `sync_aktiv` false, ein dezenter Hinweis: „Der automatische Abruf ist auf dem Server nicht eingeschaltet. ‚Jetzt abrufen‘ funktioniert trotzdem.“
- API-Aufrufe nur über `src/services/api.js`, Fehlertexte über `fehlerText`.

### 2. Profil: `components/HrvRange.jsx`

- Anzeige (grüner Bereich, rote Grenze) bleibt **unverändert**.
- Entfernen: Knopf `ÄNDERN`/`EINTRAGEN`, Formular, `ZURÜCKSETZEN`, `speichern`, `zuruecksetzen` und alle Imports dazu.
- Herkunftszeile:
  - `quelle === "garmin"`: „aus Garmin Connect · wird jeden Sonntag aktualisiert“
  - `quelle === "manual"`: „von dir eingetragen“
  - sonst: die bisherige Zeile „berechnet aus deinen letzten …“
- Die gelbe Box „Noch keine Ampel“: Den Satz „Wer seine Spanne kennt … kann sie hier eintragen“ ersetzen durch einen Verweis auf die Garmin-Kachel unter Anbindungen.

### 3. Dashboard: `HRVInput`

- In `pages/Dashboard.jsx` nur anzeigen, wenn Garmin **nicht** verbunden ist (den Zustand aus `getIntegrations` laden oder ein Feld aus einem bereits geladenen Endpunkt nutzen, ohne zusätzlichen Aufruf, falls möglich).
- Mit Garmin steht an der Stelle eine kleine Zeile „HRV kommt automatisch aus Garmin“.

### 4. Dashboard-Diagramm: `components/HRVHistoryChart.jsx`

- **Bleibt:** die berechnete Fläche `band` mit ihren beiden feinen Randlinien, die Trendlinie `mean`, die rMSSD-Kurve mit Punkten in der Ampelfarbe, die **rote Grenze** als Bezugslinie und der Legendeneintrag „Rote Grenze“.
- **Weg:**
  - die gestrichelten `ReferenceLine`s für `grenzen.gruen_ab` (mit Label `GARMIN`) und `grenzen.gruen_bis`
  - der Legendeneintrag „Garmin“
  - der Satzteil unter dem Diagramm „Geurteilt wird aber nach deiner eingetragenen Garmin-Spanne …“ für `quelle === "manual"`
- Neuer kurzer Satz für `quelle` `"garmin"` oder `"manual"`: „Die Farbe der Punkte richtet sich nach deiner Garmin-Spanne (siehe Profil).“ Begründung: Ein Punkt kann in der grünen Fläche liegen und trotzdem rot sein (bekanntes Problem in `CLAUDE.md`). Ohne diesen Satz wirkt das wie ein Fehler.
- Die langen Kommentare im Diagramm auf den neuen Stand bringen und die Vorgeschichte in einem Satz behalten.

---

## Tests (neu, im Backend-Container)

`tests/test_garmin_hrv.py`, Garmin über `httpx.MockTransport`:
- Ein Tag mit `lastNightAvg` wird zur Messung mit `quelle == "garmin"`, und der Status ist gesetzt.
- Zweiter Lauf mit denselben Daten: nichts neu, nichts geändert (idempotent).
- Ein vorhandener manueller Wert am selben Tag wird überschrieben, bei Tagen mit zwei Zeilen bleibt die zweite stehen.
- `status` `NONE`/`INVALID` oder leeres `lastNightAvg` legen nichts an und zählen als `ohne_daten`.
- `spanne_uebernehmen`: `hrv_green_min`/`hrv_band_high` = `balancedLow`/`balancedUpper`, rot = `red_from_band(...)`, Quelle `"garmin"`, und alte Messungen werden neu bewertet.
- Ohne Baseline bleibt die Spanne unverändert.
- 401 beim Token: `garmin_letzter_fehler` ist gesetzt, und der Schlüssel bleibt gespeichert.
- `PUT /integrations/garmin` mit ungültigem Schlüssel: 422, nichts gespeichert.
- `GET /integrations` gibt den Schlüssel nie im Klartext zurück.
- Mandanten: Der Job für Athlet A schreibt nichts bei Athlet B.
- `POST /hrv` liefert mit Garmin 409, ohne Garmin läuft es wie bisher.
- `thresholds_for`: `"garmin"` hat Vorrang vor der berechneten Spanne.
- Der Export enthält `garmin_api_key` nicht.

Bestehende Tests (`test_hrv.py`, `test_hrv_normalspanne.py`) an die entfernten Range-Endpunkte anpassen, ohne ihre fachliche Aussage zu verlieren. Am Ende die ganze Suite laufen lassen.

---

## `CLAUDE.md` nachziehen

- **Architektur:** neuer kurzer Abschnitt „HRV-Eingang (Garmin Personal API)“: Kachel, zwei Jobs, `GARMIN_SYNC_ENABLED`, Pull-only, Token je Lauf, Schlüssel läuft nach höchstens einem Jahr ab.
- **Designentscheidungen:** den Punkt „HRV-Diagramm“ ersetzen. Die Fläche ist die berechnete Spanne, eine Garmin-Linie gibt es nicht mehr, und die Punktfarben urteilen nach Garmin.
- **Feste Absprachen:** „Das von Hand gesetzte Garmin-HRV-Band hat Vorrang …“ wird zu „Garmins Baseline (automatisch, sonntags aktualisiert) hat Vorrang vor jeder berechneten Grenze. Die Spanne ist nicht von Hand änderbar.“
- **Bekannte Probleme:** Personal-API-Feldnamen stammen aus einem inoffiziellen Client und werden in der Doku nicht garantiert. Railway braucht `GARMIN_SYNC_ENABLED=true`.

## Für Amir nach der Umsetzung (in die Antwort schreiben, nicht selbst tun)

- Auf Railway `GARMIN_SYNC_ENABLED=true` setzen, Backend neu starten und `scheduler_status` prüfen.
- In Garmin Connect einen Schlüssel mit 1 Jahr Laufzeit anlegen und in der neuen Kachel eintragen.
- Nach dem Verbinden prüfen, ob die Spanne im Profil exakt dem grünen Bereich aus der Garmin-App entspricht.

## Ausblick: später nachrüsten (NICHT Teil dieser Aufgabe)

Geplant ist, später auch **Ruhepuls (RHR)**, **Training Readiness** und **Sleep Score** aus Garmin zu holen. Damit soll eine **eigene Trainingsbereitschaft** gebaut werden, die in die Planung eingeht, und eventuell eine **Health-Kachel** im Dashboard entstehen. Jetzt wird davon nichts gebaut. Die HRV-Umsetzung soll so angelegt sein, dass das ohne Umbau dazukommen kann:

- `services/garmin_personal.py` als allgemeinen Client schreiben, also Token holen plus eine generische GET-Hilfe. HRV ist dann nur die erste Methode, nicht die Struktur des Ganzen.
- `abgleich_fuer` und den Morgen-Job so schneiden, dass weitere Tageswerte als zusätzliche Schritte im selben Lauf dazukommen. Ein Token pro Lauf, ein Athlet pro Session.
- Die Kachel-Texte nicht nur auf HRV festnageln, z. B. „Holt jeden Morgen deine Erholungswerte“.

Was laut dem inoffiziellen Client verfügbar ist, ist vor dem Nachrüsten mit echtem Schlüssel zu prüfen:
- **Ruhepuls:** `restingHeartRate` und `lastSevenDaysAvgRestingHeartRate` in `GET /usersummary-service/usersummary/daily` bzw. `GET /wellness-service/wellness/dailyHeartRate`.
- **Sleep Score:** `sleepScores.overall` in `GET /sleep-service/sleep/dailySleep` bzw. `dailySleepSummariesByDate` (höchstens 31 Tage je Abfrage).
- **Training Readiness:** In der Endpunktliste des Clients **nicht gefunden**. Möglicherweise liefert die Personal API Garmins Readiness gar nicht. Das wäre ein Grund mehr, die eigene Bereitschaft aus HRV, RHR und Schlaf zu rechnen statt Garmins Zahl zu übernehmen.

Bei der späteren Umsetzung zu beachten:
- `HrvMeasurement.readiness_score` existiert schon (heute von Hand). Entscheiden, ob die eigene Bereitschaft dort landet oder eine eigene Tabelle „Tageswerte“ bekommt. Letzteres ist wahrscheinlich sauberer, wenn RHR und Schlaf dazukommen.
- Es gibt schon `components/HealthStatus.jsx` (`variant="tile"`) für gemeldete Beschwerden (`services/health.py`). Eine Health-Kachel muss sich dazu abgrenzen oder sie erweitern, sonst gibt es zwei Gesundheitskacheln.
- Eine neue Bereitschaft, die die Planung beeinflusst, ist eine Coaching-Regel. Sie muss also in **alle drei Prompt-Pfade** (siehe `CLAUDE.md`).

## Nicht tun

- Kein Commit und kein Push ohne ausdrückliche Bitte.
- Keine Schreibzugriffe auf die Produktionsdatenbank.
- `services/offseason.py` nicht anfassen.
- Schlüssel und Tokens nie loggen, nie in Fehlertexte oder Antworten schreiben.
- Keine HRV-Zeilen automatisch löschen.
