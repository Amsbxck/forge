import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Uvicorn konfiguriert nur seine eigenen Logger. Ohne das hier verschwinden
# alle Meldungen der Anwendung spurlos — auch die des stündlichen
# Reconcile-Jobs, dessen Ergebnis man sonst nirgends sieht.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logging.getLogger("apscheduler.executors.default").setLevel(logging.WARNING)

from core.config import settings
from core.scheduler import shutdown_scheduler, start_scheduler
from fastapi import Depends

from core.deps import require_user
from services.api_budget import BudgetExhausted
from routers import (
    auth, upload, plan, chat, metrics, health, hrv, history, integrations,
    obsidian, planned, races, strava_webhook,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Mandantenfilter registrieren, bevor die erste Anfrage kommt.
    from core.tenancy import install as install_tenancy
    install_tenancy()

    # Ohne gesetztes Geheimnis gilt ein flüchtiges, das bei jedem Neustart
    # wechselt — alle Anmeldungen wären dann weg. Auf einem Server ist ein
    # Neustart Alltag, und eine Warnung im Log liest niemand. Deshalb hier
    # ein Abbruch, solange die Anmeldung überhaupt verlangt wird.
    if settings.AUTH_REQUIRED and not settings.JWT_SECRET:
        raise RuntimeError(
            "JWT_SECRET ist nicht gesetzt. Ohne festes Geheimnis werden alle "
            "Nutzer bei jedem Neustart abgemeldet. Setze die Variable — oder "
            "AUTH_REQUIRED=false für den Betrieb ohne Anmeldung."
        )

    # Ohne öffentliche Adresse zeigen die Links in Bestätigungs- und
    # Passwortmails auf localhost. Die Mail kommt an, der Link ist wertlos,
    # und es fällt erst auf, wenn sich jemand nicht anmelden kann. Beim
    # Versand wäre es zu spät — deshalb hier beim Start.
    # Nach `mail_configured()` gefragt, nicht nach MAIL_HOST: Seit es den
    # Versand über HTTPS gibt, ist eine vollständig eingerichtete Installation
    # ohne MAIL_HOST möglich — und wäre an dieser Schranke vorbeigelaufen.
    from services.mail import mail_configured

    if mail_configured() and not settings.PUBLIC_BASE_URL:
        raise RuntimeError(
            "Mailversand ist eingerichtet, PUBLIC_BASE_URL aber nicht. Die Links "
            "in Bestätigungs- und Passwortmails zeigten dann auf localhost und "
            "wären für die Empfänger nutzlos."
        )

    # Startet nur, wenn RECONCILE_ENABLED=true gesetzt ist.
    start_scheduler()
    yield
    shutdown_scheduler()


app = FastAPI(title="IronCoach AI", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Anmeldung ist offen, alles andere verlangt einen Nutzer. Zentral hier
# statt an jedem Endpoint einzeln — sonst fehlt der Schutz beim nächsten
# hinzugefügten Router, ohne dass es jemandem auffällt.
app.include_router(auth.router, prefix="/api")

PROTECTED = [upload, plan, chat, metrics, hrv, history, planned, obsidian, races, integrations, health]
for module in PROTECTED:
    app.include_router(module.router, prefix="/api", dependencies=[Depends(require_user)])

# Strava ruft Webhook und OAuth-Rückleitung ohne Token auf: der Webhook weist
# sich über den Verify-Token aus, die Rückleitung über den state-Parameter.
# Alles übrige unter /api/strava/ verlangt eine Anmeldung.
app.include_router(strava_webhook.router)
app.include_router(strava_webhook.api_router, dependencies=[Depends(require_user)])


@app.middleware("http")
async def bind_current_user(request, call_next):
    """Nutzer der Anfrage aus dem Token bestimmen.

    Setzt den Mandantenkontext, den der ORM-Filter auswertet. Ohne gültiges
    Token bleibt er leer — die Endpoints entscheiden dann selbst, ob sie
    eine Anmeldung verlangen.
    """
    from core.config import settings
    from core.security import decode_access_token, token_issued_after
    from core.tenancy import set_current_user_id

    header = request.headers.get("authorization") or ""
    token = header[7:].strip() if header[:7].lower() == "bearer " else None

    user_id = None
    if token:
        payload = decode_access_token(token)
        if payload:
            try:
                kandidat = int(payload["sub"])
            except (KeyError, TypeError, ValueError):
                kandidat = None
            if kandidat is not None:
                # Widerruf prüfen: ein JWT lässt sich nicht einsammeln, also
                # wird gegen die Marke am Konto verglichen. Ohne diese Prüfung
                # gilt ein Token nach dem Abmelden zwei Wochen weiter.
                from database import SessionLocal
                from models import User

                db = SessionLocal()
                try:
                    user = db.query(User).filter(User.id == kandidat).first()
                    if user and user.is_active and token_issued_after(payload, user.tokens_valid_from):
                        user_id = user.id
                finally:
                    db.close()

    if user_id is None and not settings.AUTH_REQUIRED:
        # Lokale Entwicklung ohne Anmeldung: wie vorher der erste Nutzer.
        from core.deps import resolve_user
        from database import SessionLocal

        db = SessionLocal()
        try:
            user = resolve_user(db)
            user_id = user.id if user else None
        finally:
            db.close()

    set_current_user_id(user_id)
    try:
        return await call_next(request)
    finally:
        set_current_user_id(None)


@app.exception_handler(BudgetExhausted)
async def _budget_exhausted(request, exc: BudgetExhausted):
    """Aufgebrauchtes Guthaben ist kein Serverfehler.

    402 statt 500: Der Aufruf ist nicht fehlgeschlagen, er wurde bewusst
    nicht ausgeführt — und die Oberfläche kann das unterscheiden.
    """
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=402,
        content={
            "detail": (
                f"Dein API-Guthaben ist aufgebraucht "
                f"({exc.verbraucht:.2f} € von {exc.guthaben:.2f} €). "
                "Neue Pläne und Chat-Antworten sind erst nach dem Aufladen wieder möglich."
            ),
            "verbraucht_eur": round(exc.verbraucht, 4),
            "guthaben_eur": round(exc.guthaben, 2),
        },
    )


@app.get("/health")
def health():
    return {"status": "ok"}
