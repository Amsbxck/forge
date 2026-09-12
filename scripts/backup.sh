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
# `find` statt eines Platzhalters: Ein Muster wie ironcoach_*.sql.gz bleibt
# unaufgelöst stehen, wenn die Shell das Verzeichnis nicht auflisten darf —
# unter launchd ist das bei geschützten Orten der Fall. `ls` bekommt dann das
# Muster als Dateinamen, scheitert, und das Skript bricht nach dem Schreiben
# der Sicherung ab: Die Datei ist da, der Lauf gilt trotzdem als gescheitert.
liste_sicherungen() {
  find "$ZIEL" -maxdepth 1 -name 'ironcoach_*.sql.gz' -type f 2>/dev/null | sort
}

ANZAHL="$(liste_sicherungen | wc -l | tr -d ' ')"
if [ "$ANZAHL" -gt "$BEHALTEN" ]; then
  liste_sicherungen | sort -r | tail -n +$((BEHALTEN + 1)) | while read -r alt; do
    rm -f "$alt"
    echo "Alte Sicherung entfernt: $(basename "$alt")"
  done
fi

echo "Vorhandene Sicherungen: $(liste_sicherungen | wc -l | tr -d ' ')"
