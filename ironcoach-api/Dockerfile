FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y gcc libpq-dev curl ca-certificates tzdata \
    && rm -rf /var/lib/apt/lists/*

# Die Zeitzone der Athleten. Ohne sie lief der Server in UTC, und zwischen
# Mitternacht und zwei Uhr (im Winter eins) galt dort noch der Vortag: Montags
# zeigte „diese Woche" die vergangene, eine dann gebuchte Testwoche begann in
# der laufenden Woche, und eine Krankmeldung „ab heute" lag in der Zukunft.
# `date.today()` steht an rund 75 Stellen — die Zeitzone hier richtet sie alle.
ENV TZ=Europe/Berlin

# Tailscale, damit der Server die Obsidian-Instanzen der Athleten erreicht.
# Die laufen auf deren eigenen Rechnern im Heimnetz — ohne privates Netz gibt
# es dorthin keinen Weg. Ohne TS_AUTHKEY bleibt alles davon ungenutzt; das
# Abbild wird dadurch nur etwa 30 MB größer.
COPY --from=docker.io/tailscale/tailscale:stable /usr/local/bin/tailscaled /usr/sbin/tailscaled
COPY --from=docker.io/tailscale/tailscale:stable /usr/local/bin/tailscale /usr/bin/tailscale

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/uploads

COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

# Kein --reload: Das ist der Entwicklungsserver. Er überwacht das Dateisystem,
# läuft einprozessig und startet bei jeder Änderung neu — auf einem Server
# kostet das Speicher und bringt nichts, weil sich dort nichts ändert.
#
# Der Ablauf steht im Startskript statt hier, weil vor dem Server noch das
# private Netz aufgebaut werden muss und eine CMD-Zeile dafür zu eng wird.
CMD ["/app/docker-entrypoint.sh"]
