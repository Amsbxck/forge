FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y gcc libpq-dev && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/uploads

# Kein --reload: Das ist der Entwicklungsserver. Er überwacht das Dateisystem,
# läuft einprozessig und startet bei jeder Änderung neu — auf einem Server
# kostet das Speicher und bringt nichts, weil sich dort nichts ändert.
#
# Die Portnummer kommt aus der Umgebung, weil Plattformen wie Railway sie
# vorgeben; ohne Vorgabe bleibt es bei 8000. WEB_CONCURRENCY steuert die Zahl
# der Prozesse — bei einem kleinen Server ist einer richtig, mehr Prozesse
# teilen sich sonst denselben Kern und werden langsamer.
CMD ["sh", "-c", "alembic -c /app/alembic.ini upgrade head && exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --workers ${WEB_CONCURRENCY:-1} --proxy-headers --forwarded-allow-ips='*'"]
