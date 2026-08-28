"""Standalone asyncio worker for all eight background jobs.

APScheduler's AsyncIOScheduler receives coroutine functions directly. Callbacks
are kept attached to the scheduler lifecycle so event-loop errors do not escape.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings, get_settings
from app.db import _clear_rls_context, make_engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
logger = logging.getLogger("radarin.worker")

settings = get_settings()
settings.validate_reddit_startup()
engine = make_engine(settings.resolved_worker_url())
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

JOB_SPECS = (
    ("fetch_reddit_conversations", "every 15 minutes"),
    ("analyze_pending_conversations", "every 5 minutes"),
    ("recalculate_scores", "every 6 hours"),
    ("send_urgent_alerts", "every 30 minutes"),
    ("send_daily_digest", "daily at 09:00"),
    ("send_weekly_digest", "mondays at 09:00"),
    ("purge_expired_reddit_content", "every hour"),
    ("sync_deleted_reddit_content", "every 6 hours"),
)


async def _wait_for_db(max_attempts: int = 15, delay_seconds: float = 2.0) -> None:
    for attempt in range(1, max_attempts + 1):
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            logger.info("database_ready attempt=%s", attempt)
            return
        except Exception as exc:
            logger.warning("database_not_ready attempt=%s max_attempts=%s error_type=%s", attempt, max_attempts, type(exc).__name__)
            await asyncio.sleep(delay_seconds)
    raise RuntimeError(f"could not connect to the database as radar_worker after {max_attempts} attempts")


async def _run(job_name: str, worker_settings: Settings | None = None, session_factory=None) -> dict | None:
    from app.services import jobs as jobs_service

    run_settings = worker_settings or settings
    factory = session_factory or AsyncSessionLocal
    try:
        fn = jobs_service.JOB_REGISTRY[job_name]
        async with factory() as session:
            try:
                result = await fn(session, run_settings)
                logger.info(
                    "scheduled_job_complete job=%s status=%s processed=%s errors=%s duration_ms=%s",
                    job_name, result.get("status"), result.get("processed"), result.get("errors"), result.get("duration_ms"),
                )
                return result
            finally:
                await _clear_rls_context(session)
    except Exception:
        # A callback failure is isolated to this invocation. The scheduler
        # remains alive and APScheduler can run the next occurrence.
        logger.exception("scheduled_job_unhandled job=%s", job_name)
        return None


def _trigger_for(job_name: str, timezone_name: str):
    if job_name == "fetch_reddit_conversations":
        return IntervalTrigger(minutes=15, timezone=timezone_name)
    if job_name == "analyze_pending_conversations":
        return IntervalTrigger(minutes=5, timezone=timezone_name)
    if job_name == "recalculate_scores":
        return IntervalTrigger(hours=6, timezone=timezone_name)
    if job_name == "send_urgent_alerts":
        return IntervalTrigger(minutes=30, timezone=timezone_name)
    if job_name == "send_daily_digest":
        return CronTrigger(hour=9, minute=0, timezone=timezone_name)
    if job_name == "send_weekly_digest":
        return CronTrigger(day_of_week="mon", hour=9, minute=0, timezone=timezone_name)
    if job_name == "purge_expired_reddit_content":
        return IntervalTrigger(hours=1, timezone=timezone_name)
    if job_name == "sync_deleted_reddit_content":
        return IntervalTrigger(hours=6, timezone=timezone_name)
    raise KeyError(job_name)


def build_scheduler(
    worker_settings: Settings | None = None,
    runner: Callable | None = None,
    trigger_overrides: dict | None = None,
) -> AsyncIOScheduler:
    run_settings = worker_settings or settings
    callback = runner or _run
    scheduler = AsyncIOScheduler(timezone=run_settings.app_timezone)
    for job_name, frequency in JOB_SPECS:
        scheduler.add_job(
            callback,
            args=(job_name,) if runner is None else (job_name, run_settings),
            trigger=(trigger_overrides or {}).get(job_name) or _trigger_for(job_name, run_settings.app_timezone),
            id=job_name,
            name=job_name,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=60,
            replace_existing=True,
        )
        logger.info("job_registered job=%s frequency=%s", job_name, frequency)
    return scheduler


async def main(stop_event: asyncio.Event | None = None) -> None:
    await _wait_for_db()
    scheduler = build_scheduler()
    scheduler.start()
    for job in scheduler.get_jobs():
        logger.info("job_schedule job=%s next_run_at=%s", job.id, job.next_run_time)
    logger.info("worker_started timezone=%s registered_jobs=%s", settings.app_timezone, len(JOB_SPECS))
    wait_for = stop_event or asyncio.Event()
    try:
        await wait_for.wait()
    except asyncio.CancelledError:
        logger.info("worker_shutdown reason=cancelled")
    finally:
        if scheduler.running:
            scheduler.shutdown(wait=True)
        await engine.dispose()
        logger.info("worker_stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("worker_stopped reason=keyboard_interrupt")
