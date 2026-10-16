"""Compares two versions of the same dataset table — the brief's
"upload a new monthly CSV and compare it with previous data... identify
changes" (section 12). Deterministic: every number here is a direct
calculation over the two stored Parquet snapshots, no AI involved.
"""

from __future__ import annotations

from typing import Any

import polars as pl

_NUMERIC_DTYPES = (
    pl.Int8, pl.Int16, pl.Int32, pl.Int64, pl.UInt8, pl.UInt16, pl.UInt32, pl.UInt64, pl.Float32, pl.Float64,
)


class VersionCompareError(Exception):
    pass


def _pct_change(before: float, after: float) -> float | None:
    if before == 0:
        return None  # undefined — avoid division by zero, don't fake a number
    return round((after - before) / abs(before) * 100, 2)


def _compare_numeric_column(df_a: pl.DataFrame, df_b: pl.DataFrame, column: str) -> dict[str, Any]:
    series_a = df_a[column].drop_nulls()
    series_b = df_b[column].drop_nulls()
    sum_a = float(series_a.sum()) if len(series_a) else 0.0
    sum_b = float(series_b.sum()) if len(series_b) else 0.0
    mean_a = float(series_a.mean()) if len(series_a) else None
    mean_b = float(series_b.mean()) if len(series_b) else None
    return {
        "column": column,
        "type": "numeric",
        "sum_before": round(sum_a, 2),
        "sum_after": round(sum_b, 2),
        "sum_delta": round(sum_b - sum_a, 2),
        "sum_pct_change": _pct_change(sum_a, sum_b),
        "mean_before": round(mean_a, 2) if mean_a is not None else None,
        "mean_after": round(mean_b, 2) if mean_b is not None else None,
    }


def _compare_categorical_column(df_a: pl.DataFrame, df_b: pl.DataFrame, column: str) -> dict[str, Any]:
    series_a = df_a[column].drop_nulls()
    series_b = df_b[column].drop_nulls()

    def _top_value(series: pl.Series) -> str | None:
        if len(series) == 0:
            return None
        counts = series.value_counts(sort=True)
        value_col = [c for c in counts.columns if c != "count"][0]
        return str(counts[value_col][0])

    return {
        "column": column,
        "type": "categorical",
        "distinct_before": series_a.n_unique(),
        "distinct_after": series_b.n_unique(),
        "most_common_before": _top_value(series_a),
        "most_common_after": _top_value(series_b),
    }


def compare_tables(df_a: pl.DataFrame, df_b: pl.DataFrame) -> dict[str, Any]:
    columns_a = set(df_a.columns)
    columns_b = set(df_b.columns)
    common_columns = sorted(columns_a & columns_b)

    column_comparisons = []
    for column in common_columns:
        if df_a[column].dtype in _NUMERIC_DTYPES and df_b[column].dtype in _NUMERIC_DTYPES:
            column_comparisons.append(_compare_numeric_column(df_a, df_b, column))
        else:
            column_comparisons.append(_compare_categorical_column(df_a, df_b, column))

    row_count_a = df_a.height
    row_count_b = df_b.height

    return {
        "row_count_before": row_count_a,
        "row_count_after": row_count_b,
        "row_count_delta": row_count_b - row_count_a,
        "row_count_pct_change": _pct_change(row_count_a, row_count_b),
        "columns_added": sorted(columns_b - columns_a),
        "columns_removed": sorted(columns_a - columns_b),
        "common_columns": common_columns,
        "column_comparisons": column_comparisons,
    }
