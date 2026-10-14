
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.entities import Challenge
from app.services.challenge_generator import generate_challenge
from app.services.challenge_persistence import save_challenge_draft
from app.services.challenge_publisher import publish_challenge

logger = logging.getLogger(__name__)

app_timezone = ZoneInfo(settings.timezone)


def prepare_tomorrow_challenge():
    """Generate tomorrow's challenge if one isn't already prepared."""
    db = SessionLocal()

    try:
        tomorrow = datetime.now(app_timezone).date() + timedelta(days=1)

        existing = db.scalar(
            select(Challenge).where(
                Challenge.publish_date == tomorrow
            )
        )

        if existing:
            return {
                "status": "skipped",
                "date": tomorrow.isoformat(),
                "reason": "A challenge already exists for this date.",
                "challengeId": str(existing.id),
            }

        draft = generate_challenge(
            topic_hint="Everyday life",
            difficulty="beginner",
        )

        try:
            challenge_id = save_challenge_draft(
                db=db,
                draft=draft,
                concept_key=f"daily-{tomorrow.isoformat()}",
                publish_date=tomorrow,
            )
        except IntegrityError:
            db.rollback()
            logger.info(
                "Another run created the challenge for %s",
                tomorrow,
            )

            existing = db.scalar(
                select(Challenge).where(
                    Challenge.publish_date == tomorrow
                )
            )

            return {
                "status": "skipped",
                "date": tomorrow.isoformat(),
                "reason": "Another run already created a challenge for this date.",
                "challengeId": str(existing.id) if existing else None,
            }

        return {
            "status": "prepared",
            "date": tomorrow.isoformat(),
            "challengeId": str(challenge_id),
            "topic": draft.topic,
        }

    except Exception:
        logger.exception("Failed to prepare tomorrow's challenge")
        return {
            "status": "error",
            "message": "Challenge preparation failed. Check server logs.",
        }
    finally:
        db.close()


def publish_today_challenge():
    """Publish today's prepared challenge, if one exists."""
    db = SessionLocal()

    try:
        today = datetime.now(app_timezone).date()

        challenge = db.scalar(
            select(Challenge)
            .where(
                Challenge.publish_date == today,
                Challenge.status == "draft",
            )
            .with_for_update()
        )

        if challenge is None:
            return {
                "status": "skipped",
                "date": today.isoformat(),
                "reason": "No unpublished draft exists for today.",
            }

        try:
            publish_challenge(db, challenge.id, today)
        except IntegrityError:
            db.rollback()
            logger.warning(
                "Publication conflict for %s",
                today,
            )
            return {
                "status": "skipped",
                "date": today.isoformat(),
                "reason": "A challenge is already published for this date.",
            }

        return {
            "status": "published",
            "date": today.isoformat(),
            "challengeId": str(challenge.id),
        }

    except Exception:
        db.rollback()
        logger.exception("Failed to publish today's challenge")
        return {
            "status": "error",
            "message": "Challenge publication failed. Check server logs.",
        }
    finally:
        db.close()


def start_daily_scheduler():
    scheduler = BackgroundScheduler(timezone=app_timezone)

    scheduler.add_job(
        prepare_tomorrow_challenge,
        CronTrigger(
            hour=11,
            minute=30,
            timezone=app_timezone,
        ),
        id="prepare_tomorrow_challenge",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    scheduler.add_job(
        publish_today_challenge,
        CronTrigger(
            hour=12,
            minute=0,
            timezone=app_timezone,
        ),
        id="publish_today_challenge",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    scheduler.start()
    return scheduler
