from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import upload, plan, chat, metrics, hrv, history, strava_webhook

app = FastAPI(title="IronCoach AI", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload.router, prefix="/api")
app.include_router(plan.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(metrics.router, prefix="/api")
app.include_router(hrv.router, prefix="/api")
app.include_router(history.router, prefix="/api")
app.include_router(strava_webhook.router)


@app.get("/health")
def health():
    return {"status": "ok"}
