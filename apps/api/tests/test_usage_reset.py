import datetime as dt

from app.models.billing import Subscription
from app.services.billing import next_usage_reset


def _subscription(current_period_end: dt.datetime | None = None) -> Subscription:
    # Plain in-memory construction — no DB session needed. id/created_at
    # use server-side defaults that only apply on flush, and
    # next_usage_reset never reads them.
    return Subscription(plan_id="free", current_period_end=current_period_end)


def test_free_plan_resets_at_start_of_next_month() -> None:
    sub = _subscription(current_period_end=None)
    now = dt.datetime(2026, 3, 15, 12, 0, tzinfo=dt.timezone.utc)
    resets_at = next_usage_reset(sub, "2026-03", now=now)
    assert resets_at == dt.datetime(2026, 4, 1, tzinfo=dt.timezone.utc)


def test_free_plan_december_rolls_over_to_next_year() -> None:
    sub = _subscription(current_period_end=None)
    now = dt.datetime(2026, 12, 20, tzinfo=dt.timezone.utc)
    resets_at = next_usage_reset(sub, "2026-12", now=now)
    assert resets_at == dt.datetime(2027, 1, 1, tzinfo=dt.timezone.utc)


def test_stripe_backed_subscription_uses_real_period_end_when_future() -> None:
    period_end = dt.datetime(2026, 3, 28, 9, 0, tzinfo=dt.timezone.utc)
    sub = _subscription(current_period_end=period_end)
    now = dt.datetime(2026, 3, 15, tzinfo=dt.timezone.utc)
    resets_at = next_usage_reset(sub, "2026-03", now=now)
    assert resets_at == period_end


def test_stale_past_period_end_falls_back_to_calendar_month() -> None:
    # e.g. a cancelled/downgraded subscription whose last real Stripe
    # period already ended — using it verbatim would report a negative
    # "days until reset".
    stale_period_end = dt.datetime(2026, 1, 28, tzinfo=dt.timezone.utc)
    sub = _subscription(current_period_end=stale_period_end)
    now = dt.datetime(2026, 3, 15, tzinfo=dt.timezone.utc)
    resets_at = next_usage_reset(sub, "2026-03", now=now)
    assert resets_at == dt.datetime(2026, 4, 1, tzinfo=dt.timezone.utc)


def test_naive_period_end_from_sqlite_is_treated_as_utc() -> None:
    # SQLite returns a DateTime(timezone=True) column naive on read even
    # though it's always written as UTC — next_usage_reset must not
    # crash comparing it against an aware `now`.
    naive_period_end = dt.datetime(2026, 3, 28, 9, 0)  # no tzinfo
    sub = _subscription(current_period_end=naive_period_end)
    now = dt.datetime(2026, 3, 15, tzinfo=dt.timezone.utc)
    resets_at = next_usage_reset(sub, "2026-03", now=now)
    assert resets_at == dt.datetime(2026, 3, 28, 9, 0, tzinfo=dt.timezone.utc)
