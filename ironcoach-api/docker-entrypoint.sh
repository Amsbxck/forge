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

  # Wo die Knotenidentität liegt. In diesem Zustand steckt der Node-Key —
  # geht er verloren, meldet sich der Container beim nächsten Start als
  # NEUES Gerät an. Tailscale hängt dann eine Ziffer an den Namen
  # (ironcoach-api-2, -3, …), der alte Eintrag bleibt als Leiche im Tailnet
  # stehen und belegt weiter einen Geräteplatz. Schlimmer: die frische
  # Anmeldung braucht Zeit, bis eine Verbindung zu den Gegenstellen steht.
  # Solange sie fehlt, nimmt der SOCKS5-Server Verbindungen trotzdem an und
  # leitet sie ins Leere — der Aufrufer sieht keinen Verbindungsfehler,
  # sondern einen Zeitablauf mitten im TLS-Handschlag.
  #
  # Auf Railway ist das Dateisystem flüchtig, /tmp also bei jedem Deploy
  # leer. Wer ein Volume einbindet, setzt TS_STATE_DIR auf dessen Pfad und
  # bekommt bei jedem Start denselben Knoten mit derselben Adresse.
  TS_STATE_DIR="${TS_STATE_DIR:-/tmp/tailscale}"
  mkdir -p "$TS_STATE_DIR"
  case "$TS_STATE_DIR" in
    /tmp/*)
      echo "[start] Tailscale: Zustand liegt in $TS_STATE_DIR — auf Railway" \
           "flüchtig. Jeder Deploy erzeugt damit ein neues Gerät im Tailnet." \
           "Für einen festen Knoten ein Volume einbinden und TS_STATE_DIR" \
           "auf dessen Pfad setzen." >&2
      ;;
  esac

  # Direkt ablesbar machen, ob das Volume greift: Liegt hier schon eine
  # Identität, kommt derselbe Knoten zurück. Fehlt sie bei jedem Deploy neu,
  # ist der Pfad nicht dauerhaft — und man sieht es hier, statt es aus dem
  # Knotennamen erraten zu müssen.
  if [ -s "$TS_STATE_DIR/tailscaled.state" ]; then
    ZUSTAND="gefunden"
  else
    ZUSTAND="leer, neue Anmeldung"
  fi

  # Userspace-Modus, weil Railway kein /dev/net/tun bereitstellt. Der
  # SOCKS5-Server ist der einzige Weg nach draußen ins Tailnet — ohne ihn
  # kennt der Container die Adressen zwar, erreicht sie aber nicht.
  /usr/sbin/tailscaled \
    --tun=userspace-networking \
    --socks5-server=localhost:1055 \
    --state="$TS_STATE_DIR/tailscaled.state" \
    --statedir="$TS_STATE_DIR" \
    >/tmp/tailscaled.log 2>&1 &

  # Auf den Dienst warten, statt blind weiterzulaufen: `tailscale up` gegen
  # einen noch nicht bereiten Daemon scheitert mit einer irreführenden Meldung.
  for _ in $(seq 1 30); do
    /usr/bin/tailscale status >/dev/null 2>&1 && break
    sleep 1
  done

  # Tags nur, wenn ausdrücklich gesetzt. Ein Vorgabewert hier wäre eine
  # Falle: Tailscale verlangt, dass ein Tag vorher in den Zugriffsregeln
  # unter `tagOwners` steht. Wer das nicht eingerichtet hat, bekommt
  # "requested tags are invalid or not permitted" — und sucht den Fehler beim
  # Schlüssel statt in einer Einstellung, von der er nichts weiß.
  TS_ARGS=(
    --authkey="${TS_AUTHKEY}"
    --hostname="${TS_HOSTNAME:-ironcoach-api}"
    --accept-dns=true
  )
  if [ -n "${TS_TAGS:-}" ]; then
    TS_ARGS+=(--advertise-tags="${TS_TAGS}")
  fi

  if /usr/bin/tailscale up "${TS_ARGS[@]}"; then
    # Den tatsächlichen Namen ausschreiben, nicht den gewünschten: Bei einer
    # Neuanmeldung heißt der Knoten "ironcoach-api-1" statt "ironcoach-api",
    # und genau daran soll man im Log sehen, dass der Zustand verloren ging.
    #
    # Hier stand ein grep auf '"DNSName":"'. Die Ausgabe von
    # `tailscale status --json` ist aber eingerückt, zwischen Schlüssel und
    # Wert steht also ein Leerzeichen — das Muster passte nie. Und weil
    # `pipefail` gesetzt ist, riss der erfolglose grep die Pipeline mit, der
    # Ersatzwert sprang an und das war ausgerechnet der **gewünschte** Name.
    # Die Zeile meldete damit "verbunden als ironcoach-api", während der
    # Knoten in Wahrheit "ironcoach-api-1" hieß: sie konnte den Fall, für den
    # sie gebaut war, gar nicht anzeigen. Deshalb jetzt über einen echten
    # JSON-Parser — Python liegt im Abbild ohnehin.
    knoten="$(/usr/bin/tailscale status --json 2>/dev/null \
      | python3 -c 'import json,sys; print(json.load(sys.stdin)["Self"]["DNSName"].split(".")[0])' \
      2>/dev/null)" || knoten=""
    echo "[start] Tailscale: verbunden als ${knoten:-unbekannt}" \
         "(gewünscht: ${TS_HOSTNAME:-ironcoach-api}, Zustand: ${ZUSTAND})"
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
