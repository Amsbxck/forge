#!/usr/bin/env bash
#
# Sicherung der Datenbank.
#
# Es gab keine. In einer Arbeitssitzung sind dadurch rund vierzig Wochenpläne
# verlorengegangen, und es gab nichts zum Zurückholen — die Trainingsdaten
# selbst waren nur deshalb heil, weil der Fehler eine andere Tabelle traf.
# Bei mehreren Athleten ist das keine Unannehmlichkeit mehr.
#
# Aufruf:
#   scripts/backup.sh                  # lokal, gegen den Compose-Container
#   DATABASE_URL=postgres://… scripts/backup.sh   # gegen einen entfernten Server
#
# Wiederherstellen: scripts/restore.sh <datei.sql.gz>

set -euo pipefail

ZIEL="${BACKUP_DIR:-$(cd "$(dirname "$0")/.." && pwd)/backups}"
BEHALTEN="${BACKUP_KEEP:-14}"
STEMPEL="$(date +%Y-%m-%d_%H%M)"
DATEI="$ZIEL/ironcoach_$STEMPEL.sql.gz"

mkdir -p "$ZIEL"

if [ -n "${DATABASE_URL:-}" ]; then
  # Entfernter Server: pg_dump muss lokal installiert sein.
  pg_dump --no-owner --no-privileges "$DATABASE_URL" | gzip > "$DATEI"
else
  # Lokal über den Container — so braucht niemand pg_dump auf dem Rechner.
  docker compose exec -T db pg_dump --no-owner --no-privileges -U amir ironcoach \
    | gzip > "$DATEI"
fi

GROESSE="$(du -h "$DATEI" | cut -f1)"
echo "Sicherung geschrieben: $DATEI ($GROESSE)"

# Eine leere oder winzige Datei ist keine Sicherung, sieht aber wie eine aus.
# Deshalb wird geprüft, bevor alte Stände gelöscht werden — sonst räumt ein
# fehlgeschlagener Lauf die letzte funktionierende Sicherung weg.
BYTES="$(wc -c < "$DATEI")"
if [ "$BYTES" -lt 1024 ]; then
  echo "FEHLER: Sicherung ist nur $BYTES Bytes groß — wird nicht als gültig gewertet." >&2
  echo "Alte Sicherungen bleiben unangetastet." >&2
  exit 1
fi

if ! gzip -t "$DATEI" 2>/dev/null; then
  echo "FEHLER: Sicherung ist beschädigt (gzip-Prüfung fehlgeschlagen)." >&2
  exit 1
fi

# Alte Stände aufräumen, die jüngsten behalten.
ANZAHL="$(ls -1 "$ZIEL"/ironcoach_*.sql.gz 2>/dev/null | wc -l | tr -d ' ')"
if [ "$ANZAHL" -gt "$BEHALTEN" ]; then
  ls -1t "$ZIEL"/ironcoach_*.sql.gz | tail -n +$((BEHALTEN + 1)) | while read -r alt; do
    rm -f "$alt"
    echo "Alte Sicherung entfernt: $(basename "$alt")"
  done
fi

echo "Vorhandene Sicherungen: $(ls -1 "$ZIEL"/ironcoach_*.sql.gz | wc -l | tr -d ' ')"
