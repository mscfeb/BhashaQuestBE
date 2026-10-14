from fastapi import APIRouter, Request

router = APIRouter(
    prefix="/api/admin/scheduler",
    tags=["Admin - Scheduler"],
)


@router.get("/health")
def scheduler_health(request: Request):
    scheduler = getattr(request.app.state, "daily_scheduler", None)

    if scheduler is None:
        return {
            "status": "unavailable",
            "schedulerRunning": False,
        }

    return {
        "status": "ok" if scheduler.running else "unavailable",
        "schedulerRunning": scheduler.running,
        "jobs": [
            {
                "id": job.id,
                "nextRunTime": (
                    job.next_run_time.isoformat()
                    if job.next_run_time
                    else None
                ),
            }
            for job in scheduler.get_jobs()
        ],
    }