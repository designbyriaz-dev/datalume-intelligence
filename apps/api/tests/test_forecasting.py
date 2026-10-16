import datetime as dt
import math

import polars as pl
import pytest

from app.services.analytics import AnalyticsError, simple_forecast


def _monthly_df(
    n_months: int,
    start: tuple[int, int] = (2023, 1),
    seasonal_amplitude: float = 20.0,
    trend_per_month: float = 2.0,
    base: float = 100.0,
) -> pl.DataFrame:
    dates = []
    values = []
    year, month = start
    for i in range(n_months):
        dates.append(dt.date(year, month, 1).isoformat())
        seasonal = seasonal_amplitude * math.sin(2 * math.pi * i / 12)
        values.append(base + trend_per_month * i + seasonal)
        month += 1
        if month > 12:
            month = 1
            year += 1
    return pl.DataFrame({"date": dates, "value": values})


def test_falls_back_to_linear_trend_under_two_years_of_monthly_data() -> None:
    df = _monthly_df(12)  # exactly 1 year — not enough for a reliable seasonal fit
    result = simple_forecast(df, "date", "value", periods_ahead=3, period="month")
    assert result["method"] == "linear_trend_ols"
    assert len(result["forecast_points"]) == 3


def test_uses_seasonal_model_with_two_full_years_of_monthly_data() -> None:
    df = _monthly_df(24)
    result = simple_forecast(df, "date", "value", periods_ahead=6, period="month")
    assert result["method"] == "holt_winters_additive"
    assert len(result["forecast_points"]) == 6
    # Bounds must bracket the point prediction, not be degenerate or reversed.
    for point in result["forecast_points"]:
        assert point["lower_bound"] <= point["predicted_value"] <= point["upper_bound"]


def test_seasonal_forecast_captures_the_seasonal_pattern() -> None:
    """Build 3 years of data with a strong, clean seasonal swing and
    confirm the forecast actually tracks it — not just that the seasonal
    method was selected, but that it produces a materially different,
    better-shaped answer than a flat/linear projection would for data
    that genuinely swings this much every year."""
    df = _monthly_df(36, seasonal_amplitude=50.0, trend_per_month=1.0)
    result = simple_forecast(df, "date", "value", periods_ahead=12, period="month")
    assert result["method"] == "holt_winters_additive"

    predictions = [p["predicted_value"] for p in result["forecast_points"]]
    # The seasonal swing should survive into the forecast: its range
    # across 12 forecast months should be close to the ~100-unit
    # peak-to-trough swing the historical data has (2x amplitude), not
    # collapse to something close to a flat line the way a linear
    # baseline over the same data would.
    assert max(predictions) - min(predictions) > 60


def test_year_period_never_uses_seasonal_model_regardless_of_history_length() -> None:
    """No sub-annual cycle exists to detect at yearly granularity."""
    dates = [dt.date(2000 + i, 6, 15).isoformat() for i in range(30)]
    values = [100.0 + 5 * i for i in range(30)]
    df = pl.DataFrame({"date": dates, "value": values})
    result = simple_forecast(df, "date", "value", periods_ahead=3, period="year")
    assert result["method"] == "linear_trend_ols"


def test_forecast_is_deterministic() -> None:
    """Every number in this module is meant to be a reproducible
    calculation (see analytics.py's own module docstring) — confirm the
    seasonal path's Monte Carlo confidence bounds don't drift between
    calls on identical input."""
    df = _monthly_df(30)
    first = simple_forecast(df, "date", "value", periods_ahead=4, period="month")
    second = simple_forecast(df, "date", "value", periods_ahead=4, period="month")
    assert first["forecast_points"] == second["forecast_points"]


def test_rejects_too_few_periods() -> None:
    df = _monthly_df(2)
    with pytest.raises(AnalyticsError):
        simple_forecast(df, "date", "value", periods_ahead=3, period="month")
