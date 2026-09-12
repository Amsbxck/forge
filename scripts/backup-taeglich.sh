#!/usr/bin/env bash
#
# Täglicher Sicherungslauf, gestartet von launchd.
#
# Der Umweg über dieses Skript statt direkt `backup.sh` aufzurufen hat zwei
# Gründe: Die Verbindungszeichenfolge soll nicht in der Aufgabendefinition
# stehen — dort läge sie für jedes Programm lesbar —, und ein Lauf, der
# scheitert, soll eine Spur hinterlassen statt lautlos zu verschwinden.
#
# Die Verbindung kommt aus ~/.ironcoach-db-url (Rechte 600). Das Ziel ist ein
# synchronisierter Ordner: Eine Sicherung auf derselben Platte wie die
# Arbeitskopie hilft gegen gelöschte Zeilen, nicht gegen einen verlorenen
# Rechner.

set -uo pipefail

PROJEKT="$(cd "$(dirname "$0")/.." && pwd)"
URL_DATEI="$HOME/.ironcoach-db-url"
PROTOKOLL="$HOME/Library/Logs/ironcoach-backup.log"

mkdir -p "$(dirname "$PROTOKOLL")"

melde() {
  echo "$(date '+%Y-%m-%d %H:%M:%S')  $*" >> "$PROTOKOLL"
}

if [ ! -f "$URL_DATEI" ]; then
  melde "FEHLER: $URL_DATEI fehlt — keine Verbindung hinterlegt."
  exit 1
fi

# Rechte prüfen: Läge die Datei offen, stünde das Datenbankpasswort für jedes
# Programm des Rechners lesbar herum.
RECHTE="$(stat -f '%Lp' "$URL_DATEI")"
if [ "$RECHTE" != "600" ]; then
  melde "WARNUNG: $URL_DATEI hat Rechte $RECHTE statt 600 — wird korrigiert."
  chmod 600 "$URL_DATEI"
fi

DATABASE_URL="$(tr -d '\n' < "$URL_DATEI")"
export DATABASE_URL

# Ziel ist ein gewöhnlicher Ordner, kein iCloud-Pfad. macOS schützt
# ~/Library/Mobile Documents über die Zugriffsverwaltung: Ein Hintergrundjob
# darf dort schreiben, das Verzeichnis aber nicht auflisten — die Sicherung
# entsteht, der Lauf gilt trotzdem als gescheitert, und das Aufräumen alter
# Stände findet nie statt.
: "${BACKUP_DIR:=$HOME/Backups/IronCoach}"
export BACKUP_DIR
mkdir -p "$BACKUP_DIR"

# Zweitkopie nach iCloud, damit die Sicherung einen Festplattenschaden
# überlebt. Schlägt sie fehl, ist das kein Grund, den Lauf als gescheitert zu
# werten — die Hauptkopie liegt dann trotzdem.
ICLOUD="$HOME/Library/Mobile Documents/com~apple~CloudDocs/IronCoach-Backups"

melde "Start — Ziel: $BACKUP_DIR"

AUSGABE="$("$PROJEKT/scripts/backup.sh" 2>&1)"
CODE=$?

# Die Verbindungszeichenfolge könnte in einer Fehlermeldung auftauchen —
# sie wird vor dem Schreiben ins Protokoll unkenntlich gemacht.
echo "$AUSGABE" | sed -E 's|postgres(ql)?://[^ ]*|<verbindung>|g' \
  | while IFS= read -r zeile; do melde "  $zeile"; done

if [ $CODE -ne 0 ]; then
  melde "FEHLGESCHLAGEN (Code $CODE)"
  exit $CODE
fi

# Nur die jüngste Datei kopieren; ältere liegen dort schon.
if [ -d "$(dirname "$ICLOUD")" ]; then
  mkdir -p "$ICLOUD" 2>/dev/null
  JUENGSTE="$(find "$BACKUP_DIR" -maxdepth 1 -name 'ironcoach_*.sql.gz' -type f 2>/dev/null \
    | sort | tail -1)"
  if [ -n "$JUENGSTE" ] && cp "$JUENGSTE" "$ICLOUD/" 2>/dev/null; then
    melde "  Zweitkopie in iCloud: $(basename "$JUENGSTE")"
  else
    melde "  Zweitkopie nach iCloud nicht möglich — Hauptkopie liegt trotzdem."
  fi
fi

melde "Fertig."
