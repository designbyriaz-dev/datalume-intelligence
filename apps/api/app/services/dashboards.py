"""Dashboard widget computation and "generate automatically" logic.
Widgets store only their configuration; every value shown is computed
live from the current data each time a dashboard is read — reusing the
exact same KPI engine (Phase 5) and tool registry (Phase 3) as their
single-shot counterparts, so a dashboard can never show a number that
/industry-kpis or /analyze would disagree with.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

import polars as pl

from app.core.industry_packs import get_industry_pack
from app.models.dataset import DatasetTable
from app.models.workspace import Workspace
from app.services.analytics import AnalyticsError
from app.services.industry_kpis import compute_kpis
from app.services.industry_matching import get_effective_field_mapping
from app.services.tools import TOOLS


class WidgetComputeError(Exception):
    pass


def compute_widget_value(
    df: pl.DataFrame, table: DatasetTable, workspace: Workspace, widget_type: str, config: dict[str, Any]
) -> dict[str, Any]:
    if widget_type == "kpi":
        kpi_id = config.get("kpi_id")
        pack = get_industry_pack(workspace.industry)
        if pack is None:
            raise WidgetComputeError("This workspace has no industry pack, so KPI widgets can't be computed.")
        kpi_def = next((k for k in pack.kpis if k.kpi_id == kpi_id), None)
        if kpi_def is None:
            raise WidgetComputeError(f"Unknown kpi_id '{kpi_id}' for pack '{pack.industry_id}'.")

        mapping = get_effective_field_mapping(table, pack, df.columns)
        results = compute_kpis(df, pack, mapping, as_of=dt.date.today())
        result = next(r for r in results if r.kpi_id == kpi_id)
        return {
            "kind": "kpi",
            "kpi_id": result.kpi_id,
            "format": result.format,
            "value": result.value,
            "formatted": result.formatted,
            "error": result.error,
        }

    if widget_type == "chart":
        operation = config.get("operation")
        tool = TOOLS.get(operation)
        if tool is None:
            raise WidgetComputeError(f"Unknown operation '{operation}'.")
        parameters = config.get("parameters", {})
        try:
            result = tool.execute(df, parameters)
        except AnalyticsError as exc:
            return {"kind": "chart", "operation": operation, "result": None, "error": str(exc)}
        return {"kind": "chart", "operation": operation, "result": result, "error": None}

    raise WidgetComputeError(f"Unknown widget_type '{widget_type}'. Must be 'kpi' or 'chart'.")


def build_default_widgets(table: DatasetTable, workspace: Workspace) -> list[dict[str, Any]]:
    """"Generate Dashboard Automatically": one KPI widget per pack metric
    for an industry workspace, or a small profile-driven set of chart
    widgets (numeric column summaries, plus a breakdown if a suitable
    category column exists) for a general workspace."""
    pack = get_industry_pack(workspace.industry)
    if pack is not None:
        return [
            {"widget_type": "kpi", "title": kpi.name, "config": {"kpi_id": kpi.kpi_id}} for kpi in pack.kpis
        ]

    columns = table.profile["columns"]
    numeric_cols = [c["name"] for c in columns if c["inferred_type"] in ("integer", "float")]
    categorical_cols = [
        c["name"] for c in columns if c["inferred_type"] == "text" and 1 < c["distinct_count"] <= 20
    ]

    widgets: list[dict[str, Any]] = []
    for col in numeric_cols[:4]:
        widgets.append(
            {
                "widget_type": "chart",
                "title": f"{col} summary",
                "config": {"operation": "descriptive_stats", "parameters": {"column": col}},
            }
        )

    if categorical_cols and numeric_cols:
        widgets.append(
            {
                "widget_type": "chart",
                "title": f"{numeric_cols[0]} by {categorical_cols[0]}",
                "config": {
                    "operation": "group_aggregate",
                    "parameters": {"group_by": categorical_cols[0], "agg": "sum", "value_column": numeric_cols[0]},
                },
            }
        )
    elif categorical_cols:
        widgets.append(
            {
                "widget_type": "chart",
                "title": f"{categorical_cols[0]} breakdown",
                "config": {"operation": "frequency_table", "parameters": {"column": categorical_cols[0]}},
            }
        )

    return widgets
