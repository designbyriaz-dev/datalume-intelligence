"""Scenario ("what-if") modeling. Deliberately reuses the Phase 5 KPI
engine rather than building a second calculation path: a scenario is
just "apply these adjustments to the raw data, then run the exact same
KPI calculators again." Baseline and scenario numbers can never drift
apart from how /industry-kpis computes them, because it's the same code.
"""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl

_NUMERIC_DTYPES = (
    pl.Int8, pl.Int16, pl.Int32, pl.Int64, pl.UInt8, pl.UInt16, pl.UInt32, pl.UInt64, pl.Float32, pl.Float64,
)

_VALID_ADJUSTMENT_TYPES = {"percentage", "fixed_amount", "set_value"}


class ScenarioError(Exception):
    pass


@dataclass
class ScenarioAdjustment:
    column: str
    adjustment_type: str  # "percentage" | "fixed_amount" | "set_value"
    value: float


def apply_adjustments(df: pl.DataFrame, adjustments: list[ScenarioAdjustment]) -> pl.DataFrame:
    if not adjustments:
        raise ScenarioError("At least one adjustment is required.")

    adjusted = df
    for adj in adjustments:
        if adj.column not in adjusted.columns:
            raise ScenarioError(f"Unknown column: {adj.column}")
        if adj.adjustment_type not in _VALID_ADJUSTMENT_TYPES:
            raise ScenarioError(
                f"Unknown adjustment_type '{adj.adjustment_type}'. Valid: {', '.join(sorted(_VALID_ADJUSTMENT_TYPES))}"
            )
        if adjusted[adj.column].dtype not in _NUMERIC_DTYPES:
            raise ScenarioError(f"Column '{adj.column}' is not numeric — cannot apply a '{adj.adjustment_type}' adjustment.")

        if adj.adjustment_type == "percentage":
            adjusted = adjusted.with_columns((pl.col(adj.column) * (1 + adj.value / 100)).alias(adj.column))
        elif adj.adjustment_type == "fixed_amount":
            adjusted = adjusted.with_columns((pl.col(adj.column) + adj.value).alias(adj.column))
        else:  # set_value
            adjusted = adjusted.with_columns(pl.lit(adj.value).alias(adj.column))

    return adjusted
