#!/usr/bin/env bash
#
# Produktionsdaten in die lokale Entwicklungsdatenbank holen.
#
# Lokal testen, bevor etwas in die Produktion geht, hilft nur, wenn lokal
# dieselben Daten liegen: dieselben Ziele, Pläne, HRV-Messungen. Lokal war
# Amir zuletzt in der Off Season mit einem Ziel vom August, und Saisonstrahl
# und Soll/Ist ließen sich nur über Tests prüfen.
#
# Die Produktion wird dabei nur **gelesen** (pg_dump über dieselbe Verbindung
# wie die tägliche Sicherung, `~/.ironcoach-db-url`). Geschrieben wird nur in
# den Compose-Container `db`.
#
# **Strava wird lokal getrennt.** Die Tokens liegen im Klartext in der
# Datenbank, und lokal läuft der stündliche Abgleich (`RECONCILE_ENABLED`).
# Holt sich der lokale Server mit dem Refresh-Token der Produktion einen neuen,
# macht Strava den alten ungültig — die Produktion verliert die Verbindung,
# und zwar für jeden Athleten, den der lokale Abgleich anfasst. Deshalb
# werden die Strava-Verbindungen gelöscht, **bevor** das Backend wieder
# startet, und auch dann, wenn das Einspielen mittendrin scheitert.
# Garmin- und Obsidian-Schlüssel sind mit dem Produktionsschlüssel
# verschlüsselt und lokal nicht lesbar (`core/geheim.py`), sie bleiben stehen.
#
# Aufruf:
#   scripts/prod-nach-lokal.sh                       # frischer Dump
#   scripts/prod-nach-lokal.sh ~/Backups/IronCoach/ironcoach_….sql.gz
#                                                    # vorhandene Sicherung
#   scripts/prod-nach-lokal.sh --ja [datei]          # ohne Rückfrage
#
# `--ja` für den Aufruf ohne Terminal (etwa `!` in Claude Code): Dort gibt es
# keine Tastatureingabe, `read` bekommt sofort Dateiende, und das Skript
# brach vor dem ersten Schritt ab.
#
# Zurück zum vorherigen lokalen Stand: scripts/restore.sh mit der Sicherung,
# die dieses Skript als Erstes schreibt.

set -euo pipefail

cd "$(dirname "$0")/.."

# Nie gegen eine fremde Datenbank: `backup.sh` sichert sonst die Adresse aus
# DATABASE_URL statt des lokalen Containers.
unset DATABASE_URL

OHNE_RUECKFRAGE=false
if [ "${1:-}" = "--ja" ]; then
  OHNE_RUECKFRAGE=true
  shift
fi
QUELLE="${1:-}"
URL_DATEI="$HOME/.ironcoach-db-url"
LOKAL_PW="localdev"

fehler() { echo "FEHLER: $*" >&2; exit 1; }

command -v psql >/dev/null || fehler "psql fehlt (brew install libpq oder postgresql)."
if [ -n "$QUELLE" ]; then
  [ -f "$QUELLE" ] || fehler "$QUELLE gibt es nicht."
  gzip -t "$QUELLE" 2>/dev/null || fehler "$QUELLE ist beschädigt."
else
  command -v pg_dump >/dev/null || fehler "pg_dump fehlt."
  [ -r "$URL_DATEI" ] || fehler "$URL_DATEI fehlt — dort steht die Verbindung zur Produktion."
fi

# Der lokale Port kommt aus Compose, nicht aus einer Annahme.
PORT="$(docker compose port db 5432 2>/dev/null | head -1 | sed 's/.*://')"
[ -n "$PORT" ] || fehler "Der Container db läuft nicht (docker compose up -d db)."
LOKAL="postgresql://amir:${LOKAL_PW}@localhost:${PORT}/ironcoach"

echo "Ziel: lokale Datenbank ironcoach im Container db (Port $PORT)."
echo "Quelle: ${QUELLE:-frischer Dump aus der Produktion (nur lesend)}"
echo
echo "ACHTUNG: Der lokale Datenbestand wird ersetzt. Die Strava-Verbindungen"
echo "werden lokal entfernt, damit die Produktion ihre Tokens behält."
if [ "$OHNE_RUECKFRAGE" = true ]; then
  echo "Bestätigt über --ja."
else
  ANTWORT=""
  read -r -p "Fortfahren? Tippe 'ja': " ANTWORT || true
  [ "$ANTWORT" = "ja" ] || { echo "Abgebrochen (ohne Terminal: --ja)."; exit 1; }
fi

echo
echo "1/6 Sichere den lokalen Stand …"
scripts/backup.sh

if [ -z "$QUELLE" ]; then
  echo
  echo "2/6 Lese die Produktion …"
  # Nur für den Besitzer lesbar: Der Dump enthält alle Athleten im Klartext.
  umask 077
  QUELLE="backups/ironcoach_prod_$(date +%Y-%m-%d_%H%M).sql.gz"
  pg_dump --no-owner --no-privileges "$(tr -d '\n' < "$URL_DATEI")" | gzip > "$QUELLE"
  # Wie in backup.sh: Eine winzige Datei ist kein Dump, sieht aber wie einer aus.
  [ "$(wc -c < "$QUELLE")" -ge 1024 ] || { rm -f "$QUELLE"; fehler "Der Dump ist leer."; }
  echo "    $QUELLE ($(du -h "$QUELLE" | cut -f1))"
else
  echo
  echo "2/6 Nehme $QUELLE"
fi

# Ab hier ist die Datenbank in Bewegung. Was auch passiert: Die Strava-Tokens
# der Produktion dürfen nicht lokal liegen bleiben, und das Backend startet
# nicht von selbst auf einem halben Stand.
strava_trennen() {
  PGPASSWORD="$LOKAL_PW" psql -q -X "$LOKAL" -c \
    "DO \$\$ BEGIN IF to_regclass('public.strava_credentials') IS NOT NULL THEN DELETE FROM strava_credentials; END IF; END \$\$;" \
    >/dev/null 2>&1 || true
}
beim_abbruch() {
  strava_trennen
  echo >&2
  echo "Abgebrochen. Das Backend bleibt gestoppt." >&2
  echo "Zurück zum vorherigen Stand: scripts/restore.sh mit der Sicherung aus Schritt 1," >&2
  echo "danach docker compose start backend." >&2
}
trap beim_abbruch ERR INT TERM

echo
echo "3/6 Stoppe das Backend (sonst läuft der Abgleich auf halbem Stand) …"
docker compose stop backend >/dev/null

echo
echo "4/6 Spiele ein …"
# Schema leeren statt einzelner Tabellen — wie in restore.sh, wegen des
# zyklischen Fremdschlüssels zwischen planned_sessions und training_sessions.
PGPASSWORD="$LOKAL_PW" psql -q -X "$LOKAL" -c "SET client_min_messages = warning; DROP SCHEMA public CASCADE; CREATE SCHEMA public;" >/dev/null
# Über das psql des Macs, nicht über das im Container: pg_dump 18 schreibt
# `\restrict`-Zeilen, die psql 15 nicht kennt. `transaction_timeout` gibt es
# erst ab Postgres 17, der lokale Server ist 15 — die Zeile fällt weg.
# ON_ERROR_STOP, damit ein Fehler auffällt, statt still einen halben Stand zu
# hinterlassen.
gunzip -c "$QUELLE" \
  | grep -v '^SET transaction_timeout' \
  | PGPASSWORD="$LOKAL_PW" psql -q -X -v ON_ERROR_STOP=1 "$LOKAL" >/dev/null

echo
echo "5/6 Trenne Strava lokal …"
strava_trennen
REST="$(PGPASSWORD="$LOKAL_PW" psql -tA -X "$LOKAL" -c "SELECT count(*) FROM strava_credentials;")"
[ "$REST" = "0" ] || fehler "Strava-Verbindungen nicht entfernt — Backend bleibt gestoppt."
trap - ERR INT TERM

echo
echo "6/6 Starte das Backend (Migrationen laufen dabei auf den Stand des Branches) …"
docker compose start backend >/dev/null
for _ in $(seq 1 30); do
  curl -fs http://localhost:8000/health >/dev/null 2>&1 && break
  sleep 2
done
curl -fs http://localhost:8000/health >/dev/null 2>&1 \
  || echo "    Backend antwortet noch nicht — docker compose logs backend"

echo
PGPASSWORD="$LOKAL_PW" psql -X "$LOKAL" -c \
  "SELECT (SELECT count(*) FROM users) AS konten,
          (SELECT count(*) FROM training_sessions) AS einheiten,
          (SELECT count(*) FROM weekly_plans) AS plaene,
          (SELECT count(*) FROM hrv_measurements) AS hrv,
          (SELECT version_num FROM alembic_version) AS migration;"
echo "Fertig. Lokal mit dem Passwort aus der Produktion anmelden."
echo "Der Dump liegt in $QUELLE — löschen, wenn er nicht mehr gebraucht wird."
