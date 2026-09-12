#!/usr/bin/env bash
#
# Startablauf des Containers.
#
# Zwei Aufgaben: das private Netz aufbauen, falls eines konfiguriert ist, und
# danach Migrationen und Server starten.
#
# Tailscale ist optional. Ohne TS_AUTHKEY passiert nichts — lokal und auf
# Installationen ohne eigenen Vault soll sich nichts ändern, nur weil das
# Abbild die Möglichkeit mitbringt.

set -euo pipefail

if [ -n "${TS_AUTHKEY:-}" ]; then
  echo "[start] Tailscale: verbinde …"

  # Userspace-Modus, weil Railway kein /dev/net/tun bereitstellt. Der
  # SOCKS5-Server ist der einzige Weg nach draußen ins Tailnet — ohne ihn
  # kennt der Container die Adressen zwar, erreicht sie aber nicht.
  /usr/sbin/tailscaled \
    --tun=userspace-networking \
    --socks5-server=localhost:1055 \
    --state=/tmp/tailscaled.state \
    --statedir=/tmp/tailscale \
    >/tmp/tailscaled.log 2>&1 &

  # Auf den Dienst warten, statt blind weiterzulaufen: `tailscale up` gegen
  # einen noch nicht bereiten Daemon scheitert mit einer irreführenden Meldung.
  for _ in $(seq 1 30); do
    /usr/bin/tailscale status >/dev/null 2>&1 && break
    sleep 1
  done

  if /usr/bin/tailscale up \
       --authkey="${TS_AUTHKEY}" \
       --hostname="${TS_HOSTNAME:-ironcoach-api}" \
       --advertise-tags="${TS_TAGS:-tag:ironcoach}" \
       --accept-dns=true; then
    echo "[start] Tailscale: verbunden als ${TS_HOSTNAME:-ironcoach-api}"
    # Ausdrücklich NICHT als ALL_PROXY: Der gesamte ausgehende Verkehr — zu
    # Anthropic, Strava, zum Mailserver — liefe sonst durch den Tunnel. Nur
    # der Obsidian-Client braucht ihn, und der liest diese Variable selbst.
    export OBSIDIAN_PROXY="socks5://localhost:1055"
  else
    # Kein Abbruch: Ohne Tailscale fehlt nur der Obsidian-Abgleich. Die App
    # deswegen nicht starten zu lassen, wäre die härtere Strafe.
    echo "[start] Tailscale: Verbindung fehlgeschlagen — weiter ohne." >&2
    tail -5 /tmp/tailscaled.log >&2 || true
  fi
else
  echo "[start] Tailscale: kein TS_AUTHKEY gesetzt, übersprungen."
fi

echo "[start] Migrationen …"
alembic -c /app/alembic.ini upgrade head

echo "[start] Server auf Port ${PORT:-8000}, ${WEB_CONCURRENCY:-1} Prozess(e)"
exec uvicorn main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --workers "${WEB_CONCURRENCY:-1}" \
  --proxy-headers \
  --forwarded-allow-ips='*'
