
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.services.daily_scheduler import start_daily_scheduler

from app.api.routes.auth import router as auth_router
from app.api.routes.progress import router as progress_router
from app.api.routes.submission import router as submission_router
from app.api.routes.challenges import router as challenges_router
from app.api.routes.admin_challenges import router as admin_challenges_router
from app.api.routes.admin_scheduler import router as admin_scheduler_router
from app.api.routes.scheduler_health import router as scheduler_health_router
from app.api.routes.progress_history import router as progress_history_router
from app.api.routes.leaderboard import router as leaderboard_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = start_daily_scheduler()
    app.state.daily_scheduler = scheduler

    try:
        yield
    finally:
        scheduler.shutdown(wait=False)


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin, "http://localhost:5173",
        "http://127.0.0.1:5173",],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "bhasha-quest-api",
    }


@app.get("/health/db")
def database_health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        return {
            "status": "ok",
            "database": "connected",
        }
    except Exception:
        raise HTTPException(
            status_code=503,
            detail="Database unavailable",
        )


app.include_router(auth_router)
app.include_router(challenges_router)
app.include_router(progress_router)
app.include_router(submission_router)
app.include_router(admin_challenges_router)
app.include_router(admin_scheduler_router)
app.include_router(scheduler_health_router)
app.include_router(progress_history_router)
app.include_router(leaderboard_router)