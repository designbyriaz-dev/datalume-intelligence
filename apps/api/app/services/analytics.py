"""Deterministic analytical tools — the "controlled analytical execution"
layer the brief requires: every number here is a reproducible calculation
over the actual stored data, with no LLM involved. This module is what
the AI query planner (app/services/ai/) is restricted to calling — it
cannot execute arbitrary code, only these pre-approved operations.

Every public function takes a Polars DataFrame plus validated parameters
and returns a plain JSON-serializable dict. They're also usable directly
via the /analyze API endpoint without any AI in the loop.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Any

import polars as pl

_DATE_FORMATS = [
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%m/%d/%Y",
    "%d-%m-%Y",
    "%Y/%m/%d",
    # Written-month formats — unlike the slash/dash numeric formats above,
    # these have no DD/MM-vs-MM/DD ambiguity (a month name can't be
    # mistaken for a day number), so adding them doesn't carry the same
    # silent-misinterpretation risk documented for profiling.py's
    # numeric-text heuristic.
    "%d %B %Y",  # 15 March 2026
    "%d %b %Y",  # 15 Mar 2026
    "%B %d, %Y",  # March 15, 2026
    "%b %d, %Y",  # Mar 15, 2026
    "%B %d %Y",  # March 15 2026
    "%b %d %Y",  # Mar 15 2026
]
_ISO_LIKE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class AnalyticsError(Exception):
    """Client-facing error: unknown column, wrong type, insufficient data."""


def _require_column(df: pl.DataFrame, column: str) -> None:
    if column not in df.columns:
        raise AnalyticsError(f"Unknown column: {column}")


def _require_numeric(df: pl.DataFrame, column: str) -> pl.Series:
    _require_column(df, column)
    series = df[column]
    if series.dtype not in (
        pl.Int8, pl.Int16, pl.Int32, pl.Int64,
        pl.UInt8, pl.UInt16, pl.UInt32, pl.UInt64,
        pl.Float32, pl.Float64,
    ):
        raise AnalyticsError(f"Column '{column}' is not numeric (got {series.dtype}).")
    return series


def _jsonable(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (int, float, bool, str)):
        return value
    return str(value)


def descriptive_stats(df: pl.DataFrame, column: str) -> dict[str, Any]:
    series = _require_numeric(df, column)
    non_null = series.drop_nulls()
    if len(non_null) == 0:
        raise AnalyticsError(f"Column '{column}' has no non-null values.")

    return {
        "column": column,
        "count": len(non_null),
        "null_count": series.null_count(),
        "sum": _jsonable(non_null.sum()),
        "mean": round(float(non_null.mean()), 4),
        "median": _jsonable(non_null.median()),
        "min": _jsonable(non_null.min()),
        "max": _jsonable(non_null.max()),
        "std_dev": round(float(non_null.std()), 4) if len(non_null) > 1 else 0.0,
        "variance": round(float(non_null.var()), 4) if len(non_null) > 1 else 0.0,
    }


def frequency_table(df: pl.DataFrame, column: str, top_n: int = 20) -> dict[str, Any]:
    _require_column(df, column)
    non_null = df[column].drop_nulls()
    if len(non_null) == 0:
        raise AnalyticsError(f"Column '{column}' has no non-null values.")

    counts = non_null.value_counts(sort=True).head(top_n)
    value_col = [c for c in counts.columns if c != "count"][0]
    total = len(non_null)
    rows = [
        {
            "value": _jsonable(row[value_col]),
            "count": row["count"],
            "percentage": round(row["count"] / total * 100, 2),
        }
        for row in counts.to_dicts()
    ]
    return {"column": column, "total_non_null": total, "distinct_count": df[column].n_unique(), "top_values": rows}


def correlation(df: pl.DataFrame, column_a: str, column_b: str) -> dict[str, Any]:
    series_a = _require_numeric(df, column_a)
    series_b = _require_numeric(df, column_b)

    paired = df.select([column_a, column_b]).drop_nulls()
    if paired.height < 3:
        raise AnalyticsError("Need at least 3 paired non-null observations to compute a correlation.")

    r = paired.select(pl.corr(column_a, column_b)).item()
    scatter_sample = paired.head(200).to_dicts()

    return {
        "column_a": column_a,
        "column_b": column_b,
        "pearson_r": round(float(r), 4) if r is not None else None,
        "n": paired.height,
        "scatter_sample": scatter_sample,
    }


def detect_outliers(df: pl.DataFrame, column: str) -> dict[str, Any]:
    series = _require_numeric(df, column).drop_nulls()
    if len(series) < 4:
        raise AnalyticsError("Need at least 4 non-null values to detect outliers (IQR method).")

    q1 = series.quantile(0.25)
    q3 = series.quantile(0.75)
    iqr = q3 - q1
    lower_bound = q1 - 1.5 * iqr
    upper_bound = q3 + 1.5 * iqr

    outlier_mask = (series < lower_bound) | (series > upper_bound)
    outlier_values = series.filter(outlier_mask).to_list()

    return {
        "column": column,
        "method": "iqr_1.5",
        "q1": _jsonable(q1),
        "q3": _jsonable(q3),
        "lower_bound": round(float(lower_bound), 4),
        "upper_bound": round(float(upper_bound), 4),
        "outlier_count": len(outlier_values),
        "outlier_values": [_jsonable(v) for v in outlier_values[:200]],
    }


def group_aggregate(
    df: pl.DataFrame, group_by: str, agg: str = "sum", value_column: str | None = None
) -> dict[str, Any]:
    _require_column(df, group_by)
    valid_aggs = {"sum", "mean", "count", "min", "max", "median"}
    if agg not in valid_aggs:
        raise AnalyticsError(f"Unknown aggregation '{agg}'. Valid: {', '.join(sorted(valid_aggs))}")

    if agg == "count":
        grouped = df.group_by(group_by).agg(pl.len().alias("value"))
    else:
        if not value_column:
            raise AnalyticsError(f"value_column is required for aggregation '{agg}'.")
        _require_numeric(df, value_column)
        agg_expr = {
            "sum": pl.col(value_column).sum(),
            "mean": pl.col(value_column).mean(),
            "min": pl.col(value_column).min(),
            "max": pl.col(value_column).max(),
            "median": pl.col(value_column).median(),
        }[agg]
        grouped = df.group_by(group_by).agg(agg_expr.alias("value"))

    grouped = grouped.sort("value", descending=True)
    rows = grouped.to_dicts()

    return {
        "group_by": group_by,
        "value_column": value_column if agg != "count" else None,
        "aggregation": agg,
        "groups": [
            {"label": _jsonable(row[group_by]), "value": _jsonable(row["value"])} for row in rows
        ],
    }


def _parse_date_cell(raw: str) -> dt.date | None:
    raw = raw.strip()
    for fmt in _DATE_FORMATS:
        try:
            return dt.datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _parse_date_column(df: pl.DataFrame, column: str) -> tuple[list[dt.date], int]:
    """Best-effort parse of a text (or native date) column into Python
    dates. Returns (parsed_dates_aligned_with_a_second_list, unparseable_count)
    — unlike the ingestion-time profiler, a tool is allowed to exclude
    rows it can't parse, as long as it reports how many it dropped."""
    series = df[column]
    if series.dtype == pl.Date:
        return [v for v in series.to_list() if v is not None], series.null_count()

    unparseable = 0
    parsed: list[dt.date] = []
    for raw in series.to_list():
        if raw is None:
            continue
        d = _parse_date_cell(str(raw))
        if d is None:
            unparseable += 1
        else:
            parsed.append(d)
    return parsed, unparseable


def time_trend(
    df: pl.DataFrame, date_column: str, value_column: str, period: str = "month", agg: str = "sum"
) -> dict[str, Any]:
    _require_column(df, date_column)
    _require_numeric(df, value_column)
    if period not in ("month", "year"):
        raise AnalyticsError("period must be 'month' or 'year'")

    pairs_df = df.select([date_column, value_column]).drop_nulls()
    dates: list[dt.date] = []
    values: list[float] = []
    unparseable = 0
    for raw_date, raw_value in pairs_df.iter_rows():
        if df[date_column].dtype == pl.Date:
            parsed = raw_date
        else:
            parsed = _parse_date_cell(str(raw_date))
        if parsed is None:
            unparseable += 1
            continue
        dates.append(parsed)
        values.append(float(raw_value))

    if len(dates) < 2:
        raise AnalyticsError(
            f"Could not parse enough dates in '{date_column}' to build a trend "
            f"({len(dates)} parsed, {unparseable} unparseable)."
        )

    bucket: dict[str, list[float]] = {}
    for d, v in zip(dates, values):
        key = f"{d.year:04d}" if period == "year" else f"{d.year:04d}-{d.month:02d}"
        bucket.setdefault(key, []).append(v)

    def _agg(values: list[float]) -> float:
        if agg == "sum":
            return sum(values)
        if agg == "mean":
            return sum(values) / len(values)
        if agg == "count":
            return float(len(values))
        if agg == "min":
            return min(values)
        if agg == "max":
            return max(values)
        raise AnalyticsError(f"Unknown aggregation '{agg}'")

    points = [{"period": key, "value": round(_agg(vals), 4)} for key, vals in sorted(bucket.items())]

    return {
        "date_column": date_column,
        "value_column": value_column,
        "period": period,
        "aggregation": agg,
        "rows_excluded_unparseable_date": unparseable,
        "points": points,
    }


def simple_forecast(
    df: pl.DataFrame, date_column: str, value_column: str, periods_ahead: int = 3, period: str = "month"
) -> dict[str, Any]:
    """A deliberately simple linear-trend baseline (ordinary least squares
    over period-aggregated history) — NOT ARIMA/Prophet/anything
    seasonality-aware. Good enough to show direction and a naive
    uncertainty band; documented as a baseline so it's never mistaken for
    more than it is. See docs/CHECKLIST.md."""
    if periods_ahead < 1 or periods_ahead > 24:
        raise AnalyticsError("periods_ahead must be between 1 and 24.")

    trend = time_trend(df, date_column, value_column, period=period, agg="sum")
    points = trend["points"]
    if len(points) < 3:
        raise AnalyticsError(
            f"Need at least 3 historical {period} periods to forecast; found {len(points)}."
        )

    xs = list(range(len(points)))
    ys = [p["value"] for p in points]

    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    covariance = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    variance_x = sum((x - mean_x) ** 2 for x in xs)
    slope = covariance / variance_x if variance_x else 0.0
    intercept = mean_y - slope * mean_x

    residuals = [y - (slope * x + intercept) for x, y in zip(xs, ys)]
    residual_std = (sum(r**2 for r in residuals) / n) ** 0.5

    last_key = points[-1]["period"]
    forecast_points = []
    for step in range(1, periods_ahead + 1):
        x = n - 1 + step
        predicted = slope * x + intercept
        forecast_points.append(
            {
                "period": _advance_period(last_key, step, period),
                "predicted_value": round(predicted, 4),
                "lower_bound": round(predicted - 1.96 * residual_std, 4),
                "upper_bound": round(predicted + 1.96 * residual_std, 4),
            }
        )

    return {
        "date_column": date_column,
        "value_column": value_column,
        "period": period,
        "method": "linear_trend_ols",
        "historical_points": points,
        "forecast_points": forecast_points,
        "residual_std_dev": round(residual_std, 4),
        "caveat": (
            "Simple linear-trend baseline. Does not account for seasonality "
            "or external factors. Treat as directional, not precise."
        ),
    }


def _advance_period(period_key: str, steps: int, period: str) -> str:
    if period == "year":
        return str(int(period_key) + steps)
    year, month = (int(part) for part in period_key.split("-"))
    total_month_index = (year * 12 + (month - 1)) + steps
    new_year, new_month = divmod(total_month_index, 12)
    return f"{new_year:04d}-{new_month + 1:02d}"
