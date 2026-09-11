#!/usr/bin/env bash
#
# Sicherung zurückspielen.
#
# Das Zurückspielen ist der Teil, den niemand übt — und der deshalb im Ernstfall
# nicht funktioniert. Vor dem eigentlichen Einspielen wird deshalb zuerst der
# **aktuelle** Stand gesichert: Wer die falsche Datei erwischt, hat sonst zwei
# verlorene Stände statt einem.
#
# Aufruf:
#   scripts/restore.sh backups/ironcoach_2026-09-10_1200.sql.gz

set -euo pipefail

DATEI="${1:-}"
if [ -z "$DATEI" ] || [ ! -f "$DATEI" ]; then
  echo "Aufruf: $0 <sicherung.sql.gz>" >&2
  echo >&2
  echo "Vorhandene Sicherungen:" >&2
  ls -1t "$(cd "$(dirname "$0")/.." && pwd)/backups"/ironcoach_*.sql.gz 2>/dev/null >&2 \
    || echo "  keine gefunden" >&2
  exit 1
fi

if ! gzip -t "$DATEI" 2>/dev/null; then
  echo "FEHLER: $DATEI ist beschädigt." >&2
  exit 1
fi

echo "Zurückspielen aus: $DATEI"
echo
echo "ACHTUNG: Der aktuelle Datenbestand wird ersetzt."
read -r -p "Fortfahren? Tippe 'ja': " ANTWORT
[ "$ANTWORT" = "ja" ] || { echo "Abgebrochen."; exit 1; }

echo "Sichere zuerst den aktuellen Stand …"
BACKUP_DIR="${BACKUP_DIR:-$(cd "$(dirname "$0")/.." && pwd)/backups}" \
  "$(dirname "$0")/backup.sh" || {
    echo "FEHLER: Der aktuelle Stand ließ sich nicht sichern — abgebrochen." >&2
    exit 1
  }

echo
echo "Spiele ein …"
if [ -n "${DATABASE_URL:-}" ]; then
  gunzip -c "$DATEI" | psql "$DATABASE_URL"
else
  # Schema leeren statt einzelne Tabellen: Der Fremdschlüssel zwischen
  # planned_sessions und training_sessions ist zyklisch, ein Löschen in
  # Reihenfolge scheitert daran.
  docker compose exec -T db psql -U amir -d ironcoach \
    -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
  gunzip -c "$DATEI" | docker compose exec -T db psql -U amir -d ironcoach
fi

echo
echo "Fertig. Prüfe den Bestand:"
if [ -n "${DATABASE_URL:-}" ]; then
  psql "$DATABASE_URL" -c "SELECT (SELECT count(*) FROM users) AS konten, (SELECT count(*) FROM training_sessions) AS einheiten, (SELECT count(*) FROM weekly_plans) AS plaene;"
else
  docker compose exec -T db psql -U amir -d ironcoach \
    -c "SELECT (SELECT count(*) FROM users) AS konten, (SELECT count(*) FROM training_sessions) AS einheiten, (SELECT count(*) FROM weekly_plans) AS plaene;"
fi
