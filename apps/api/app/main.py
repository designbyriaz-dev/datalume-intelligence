import datetime as dt
import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.services.dunning import downgrade_overdue_subscriptions
from app.services.email import EmailNotConfiguredError, get_email_sender
from app.services.rate_limit import purge_expired_windows
from app.services.scheduled_reports import run_due_scheduled_reports
from app.services.storage import get_storage
from app.services.stripe_billing import BillingNotConfiguredError, get_stripe_client

settings = get_settings()
logger = logging.getLogger("datalume.scheduler")

# How often the in-process scheduler checks for due scheduled reports.
# Real schedules are daily/weekly/monthly; this only needs to be frequent
# enough that a due report doesn't wait long past its next_run_at — it
# does NOT need to match the schedule's own frequency.
_SCHEDULER_INTERVAL_MINUTES = 5

# How often to purge expired rate_limit_windows rows. Infrequent on
# purpose — an expired window is already inert (see
# app/services/rate_limit.py), so this is just housekeeping, not
# correctness, and doesn't need to run anywhere near as often as the
# windows themselves (the longest configured window today is 1 hour).
_RATE_LIMIT_CLEANUP_INTERVAL_MINUTES = 60
_RATE_LIMIT_WINDOW_RETENTION = dt.timedelta(hours=6)

# How often the in-process scheduler checks for subscriptions whose
# dunning grace period has expired. The grace period itself (see
# app/services/dunning.py's DEFAULT_GRACE_PERIOD) is measured in days,
# so this only needs to be frequent enough that a subscription doesn't
# sit downgrade-eligible for long after its grace period actually ends
# — it does NOT need to match the grace period's own length.
_DUNNING_INTERVAL_MINUTES = 60


async def _run_due_scheduled_reports_tick() -> None:
    try:
        try:
            email_sender = get_email_sender()
        except EmailNotConfiguredError:
            email_sender = None
        async with AsyncSessionLocal() as db:
            generated = await run_due_scheduled_reports(db, get_storage(), email_sender=email_sender)
            if generated:
                logger.info("Generated %d scheduled report(s).", len(generated))
    except Exception:
        # A failed tick must never crash the scheduler loop — log and
        # retry on the next interval.
        logger.exception("Scheduled report tick failed.")


async def _downgrade_overdue_subscriptions_tick() -> None:
    try:
        try:
            email_sender = get_email_sender()
        except EmailNotConfiguredError:
            email_sender = None
        try:
            stripe_client = get_stripe_client()
        except BillingNotConfiguredError:
            stripe_client = None
        async with AsyncSessionLocal() as db:
            downgraded = await downgrade_overdue_subscriptions(
                db, email_sender=email_sender, stripe_client=stripe_client
            )
            if downgraded:
                logger.info("Downgraded %d overdue subscription(s) for non-payment.", len(downgraded))
    except Exception:
        logger.exception("Dunning tick failed.")


async def _purge_expired_rate_limit_windows_tick() -> None:
    try:
        async with AsyncSessionLocal() as db:
            cutoff = dt.datetime.now(dt.timezone.utc) - _RATE_LIMIT_WINDOW_RETENTION
            deleted = await purge_expired_windows(db, older_than=cutoff)
            if deleted:
                logger.info("Purged %d expired rate-limit window row(s).", deleted)
    except Exception:
        logger.exception("Rate-limit window cleanup tick failed.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = AsyncIOScheduler()
    scheduler.add_job(_run_due_scheduled_reports_tick, "interval", minutes=_SCHEDULER_INTERVAL_MINUTES)
    scheduler.add_job(_downgrade_overdue_subscriptions_tick, "interval", minutes=_DUNNING_INTERVAL_MINUTES)
    scheduler.add_job(
        _purge_expired_rate_limit_windows_tick, "interval", minutes=_RATE_LIMIT_CLEANUP_INTERVAL_MINUTES
    )
    scheduler.start()
    app.state.scheduler = scheduler
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
