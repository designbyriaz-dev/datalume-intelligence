"""Industry-pack KPI calculators. Each function takes the dataset's
DataFrame plus the resolved column mapping (app/services/industry_matching.py)
and returns a plain JSON-serializable result. Every calculation here is
deterministic — reuses app/services/analytics.py's vetted date parsing
where relevant — and documents its own assumptions rather than silently
guessing (see especially the social housing "overdue inspection" KPI).
"""

from __future__ import annotations

import calendar
import datetime as dt
from dataclasses import dataclass
from typing import Any

import polars as pl

from app.core.industry_packs import IndustryPack, KPIDefinition
from app.services.analytics import _parse_date_cell

_OCCUPIED_MARKERS = ("occ", "let", "tenanted")
_VACANT_MARKERS = ("vac", "void", "empty")

# Default for the two date-window KPIs below when a workspace hasn't
# configured its own (Workspace.kpi_window_months is None). Not a value
# the brief specified — see docs/CHECKLIST.md's Phase 5 section.
DEFAULT_KPI_WINDOW_MONTHS = 12


def _add_months(d: dt.date, months: int) -> dt.date:
    """Add a (possibly negative) number of months to a date, clamping the
    day to the target month's length (e.g. 2024-02-29 + 12 months ->
    2025-02-28, not a ValueError) — same clamping approach as
    scheduled_reports.compute_next_run's monthly cadence."""
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return d.replace(year=year, month=month, day=day)


class KPIError(Exception):
    pass


@dataclass
class KPIResult:
    kpi_id: str
    name: str
    format: str
    value: float | int | None
    formatted: str
    error: str | None = None


def _resolve_numeric_series(df: pl.DataFrame, mapping: dict[str, str | None], field: str) -> pl.Series:
    col = mapping.get(field)
    if col is None or col not in df.columns:
        raise KPIError(f"Required field '{field}' is not mapped to a column.")
    series = df[col]
    if series.dtype not in (
        pl.Int8, pl.Int16, pl.Int32, pl.Int64, pl.UInt8, pl.UInt16, pl.UInt32, pl.UInt64, pl.Float32, pl.Float64,
    ):
        raise KPIError(f"Column '{col}' mapped to '{field}' is not numeric.")
    return series.drop_nulls()


def _resolve_text_series(df: pl.DataFrame, mapping: dict[str, str | None], field: str) -> list[str]:
    col = mapping.get(field)
    if col is None or col not in df.columns:
        raise KPIError(f"Required field '{field}' is not mapped to a column.")
    return [str(v) for v in df[col].to_list() if v is not None]


def _format(value: float | int | None, fmt: str) -> str:
    if value is None:
        return "—"
    if fmt == "currency_gbp":
        return f"£{value:,.2f}"
    if fmt == "percentage":
        return f"{value:.1f}%"
    if fmt == "count":
        return f"{int(value):,}"
    return f"{value:,.2f}"


def _status_share(values: list[str], markers: tuple[str, ...]) -> float:
    if not values:
        raise KPIError("No status values to evaluate.")
    matches = sum(1 for v in values if any(m in v.lower() for m in markers))
    return round(matches / len(values) * 100, 2)


def _sum_rent_by_group(df: pl.DataFrame, group_col: str, value_col: str) -> dict[str, float]:
    grouped = df.select([group_col, value_col]).drop_nulls().group_by(group_col).agg(pl.col(value_col).sum())
    return {str(row[group_col]): float(row[value_col]) for row in grouped.to_dicts()}


def _calc_total_rent_roll(df, mapping, **_kwargs) -> float:
    return round(float(_resolve_numeric_series(df, mapping, "rent_amount").sum()), 2)


def _calc_average_rent(df, mapping, **_kwargs) -> float:
    series = _resolve_numeric_series(df, mapping, "rent_amount")
    if len(series) == 0:
        raise KPIError("No rent values present.")
    return round(float(series.mean()), 2)


def _calc_occupancy_rate(df, mapping, **_kwargs) -> float:
    return _status_share(_resolve_text_series(df, mapping, "status"), _OCCUPIED_MARKERS)


def _calc_vacancy_rate(df, mapping, **_kwargs) -> float:
    return _status_share(_resolve_text_series(df, mapping, "status"), _VACANT_MARKERS)


def _calc_total_arrears(df, mapping, **_kwargs) -> float:
    return round(float(_resolve_numeric_series(df, mapping, "arrears_amount").sum()), 2)


def _calc_arrears_pct_of_rent_roll(df, mapping, **_kwargs) -> float:
    rent_roll = float(_resolve_numeric_series(df, mapping, "rent_amount").sum())
    if rent_roll <= 0:
        raise KPIError("Rent roll is zero — cannot compute arrears percentage.")
    arrears = float(_resolve_numeric_series(df, mapping, "arrears_amount").sum())
    return round(arrears / rent_roll * 100, 2)


def _calc_total_maintenance_cost(df, mapping, **_kwargs) -> float:
    return round(float(_resolve_numeric_series(df, mapping, "maintenance_cost").sum()), 2)


def _calc_leases_expiring_12_months(
    df, mapping, as_of: dt.date | None = None, window_months: int = DEFAULT_KPI_WINDOW_MONTHS, **_kwargs
) -> int:
    col = mapping.get("lease_end_date")
    if col is None:
        raise KPIError("Required field 'lease_end_date' is not mapped to a column.")
    reference = as_of or dt.date.today()
    cutoff = _add_months(reference, window_months)
    count = 0
    for raw in df[col].to_list():
        if raw is None:
            continue
        parsed = raw if isinstance(raw, dt.date) else _parse_date_cell(str(raw))
        if parsed is not None and reference <= parsed <= cutoff:
            count += 1
    return count


def _calc_tenant_concentration_top5(df, mapping, **_kwargs) -> float:
    tenant_col = mapping.get("tenant")
    rent_col = mapping.get("rent_amount")
    if tenant_col is None or rent_col is None:
        raise KPIError("Required fields 'tenant' and 'rent_amount' must both be mapped.")
    by_tenant = _sum_rent_by_group(df, tenant_col, rent_col)
    total = sum(by_tenant.values())
    if total <= 0:
        raise KPIError("Total rent roll is zero — cannot compute concentration.")
    top5_total = sum(sorted(by_tenant.values(), reverse=True)[:5])
    return round(top5_total / total * 100, 2)


def _calc_total_properties(df, mapping, **_kwargs) -> int:
    col = mapping.get("property_id")
    if col is None:
        raise KPIError("Required field 'property_id' is not mapped to a column.")
    return int(df[col].drop_nulls().len())


def _calc_properties_overdue_inspection(
    df, mapping, as_of: dt.date | None = None, window_months: int = DEFAULT_KPI_WINDOW_MONTHS, **_kwargs
) -> int:
    col = mapping.get("last_inspection_date")
    if col is None:
        raise KPIError("Required field 'last_inspection_date' is not mapped to a column.")
    reference = as_of or dt.date.today()
    cutoff = _add_months(reference, -window_months)
    count = 0
    for raw in df[col].to_list():
        if raw is None:
            continue
        parsed = raw if isinstance(raw, dt.date) else _parse_date_cell(str(raw))
        if parsed is not None and parsed < cutoff:
            count += 1
    return count


def _calc_void_rate(df, mapping, **_kwargs) -> float:
    return _status_share(_resolve_text_series(df, mapping, "void_status"), _VACANT_MARKERS)


def _calc_total_repair_cost(df, mapping, **_kwargs) -> float:
    return round(float(_resolve_numeric_series(df, mapping, "repair_cost").sum()), 2)


def _calc_average_repair_cost(df, mapping, **_kwargs) -> float:
    series = _resolve_numeric_series(df, mapping, "repair_cost")
    if len(series) == 0:
        raise KPIError("No repair cost values present.")
    return round(float(series.mean()), 2)


def _calc_total_planned_investment(df, mapping, **_kwargs) -> float:
    return round(float(_resolve_numeric_series(df, mapping, "planned_investment_amount").sum()), 2)


def _calc_total_revenue(df, mapping, **_kwargs) -> float:
    return round(float(_resolve_numeric_series(df, mapping, "revenue").sum()), 2)


def _calc_total_expenses(df, mapping, **_kwargs) -> float:
    return round(float(_resolve_numeric_series(df, mapping, "expenses").sum()), 2)


def _calc_net_profit(df, mapping, **_kwargs) -> float:
    revenue = float(_resolve_numeric_series(df, mapping, "revenue").sum())
    expenses = float(_resolve_numeric_series(df, mapping, "expenses").sum())
    return round(revenue - expenses, 2)


def _calc_profit_margin_pct(df, mapping, **_kwargs) -> float:
    revenue = float(_resolve_numeric_series(df, mapping, "revenue").sum())
    if revenue <= 0:
        raise KPIError("Total revenue is zero — cannot compute profit margin.")
    expenses = float(_resolve_numeric_series(df, mapping, "expenses").sum())
    return round((revenue - expenses) / revenue * 100, 2)


def _calc_average_monthly_revenue(df, mapping, **_kwargs) -> float:
    date_col = mapping.get("date")
    revenue_col = mapping.get("revenue")
    if date_col is None or revenue_col is None:
        raise KPIError("Required fields 'date' and 'revenue' must both be mapped.")

    monthly: dict[str, float] = {}
    for raw_date, raw_revenue in df.select([date_col, revenue_col]).drop_nulls().iter_rows():
        parsed = raw_date if isinstance(raw_date, dt.date) else _parse_date_cell(str(raw_date))
        if parsed is None:
            continue
        key = f"{parsed.year:04d}-{parsed.month:02d}"
        monthly[key] = monthly.get(key, 0.0) + float(raw_revenue)

    if not monthly:
        raise KPIError("Could not parse any dates to compute a monthly average.")
    return round(sum(monthly.values()) / len(monthly), 2)


def _resolve_paired_numeric(df: pl.DataFrame, mapping: dict[str, str | None], field_a: str, field_b: str) -> pl.DataFrame:
    col_a = mapping.get(field_a)
    col_b = mapping.get(field_b)
    if col_a is None or col_b is None:
        raise KPIError(f"Required fields '{field_a}' and '{field_b}' must both be mapped.")
    return df.select([col_a, col_b]).drop_nulls()


def _calc_total_budget(df, mapping, **_kwargs) -> float:
    return round(float(_resolve_numeric_series(df, mapping, "annual_budget").sum()), 2)


def _calc_total_actual_spend(df, mapping, **_kwargs) -> float:
    return round(float(_resolve_numeric_series(df, mapping, "actual_spend").sum()), 2)


def _calc_total_forecast_outturn(df, mapping, **_kwargs) -> float:
    return round(float(_resolve_numeric_series(df, mapping, "forecast_outturn").sum()), 2)


def _calc_overall_variance_amount(df, mapping, **_kwargs) -> float:
    budget = float(_resolve_numeric_series(df, mapping, "annual_budget").sum())
    outturn = float(_resolve_numeric_series(df, mapping, "forecast_outturn").sum())
    return round(outturn - budget, 2)


def _calc_overall_variance_pct(df, mapping, **_kwargs) -> float:
    budget = float(_resolve_numeric_series(df, mapping, "annual_budget").sum())
    if budget <= 0:
        raise KPIError("Total budget is zero — cannot compute variance percentage.")
    outturn = float(_resolve_numeric_series(df, mapping, "forecast_outturn").sum())
    return round((outturn - budget) / budget * 100, 2)


def _calc_budget_utilisation_rate(df, mapping, **_kwargs) -> float:
    budget = float(_resolve_numeric_series(df, mapping, "annual_budget").sum())
    if budget <= 0:
        raise KPIError("Total budget is zero — cannot compute utilisation rate.")
    actual = float(_resolve_numeric_series(df, mapping, "actual_spend").sum())
    return round(actual / budget * 100, 2)


def _calc_over_budget_line_count(df, mapping, **_kwargs) -> int:
    sub = _resolve_paired_numeric(df, mapping, "annual_budget", "forecast_outturn")
    budget_col = mapping["annual_budget"]
    outturn_col = mapping["forecast_outturn"]
    return int((sub[outturn_col] > sub[budget_col]).sum())


def _calc_top5_overspend_concentration(df, mapping, **_kwargs) -> float:
    service_col = mapping.get("service_area")
    budget_col = mapping.get("annual_budget")
    outturn_col = mapping.get("forecast_outturn")
    if service_col is None or budget_col is None or outturn_col is None:
        raise KPIError("Required fields 'service_area', 'annual_budget' and 'forecast_outturn' must all be mapped.")
    sub = df.select([service_col, budget_col, outturn_col]).drop_nulls()
    grouped = sub.group_by(service_col).agg((pl.col(outturn_col).sum() - pl.col(budget_col).sum()).alias("variance"))
    overspends = sorted((v for v in grouped["variance"].to_list() if v > 0), reverse=True)
    total_overspend = sum(overspends)
    if total_overspend <= 0:
        raise KPIError("No service areas are forecast to overspend.")
    top5_overspend = sum(overspends[:5])
    return round(top5_overspend / total_overspend * 100, 2)


_CALCULATORS = {
    "total_rent_roll": _calc_total_rent_roll,
    "average_rent": _calc_average_rent,
    "occupancy_rate": _calc_occupancy_rate,
    "vacancy_rate": _calc_vacancy_rate,
    "total_arrears": _calc_total_arrears,
    "arrears_pct_of_rent_roll": _calc_arrears_pct_of_rent_roll,
    "total_maintenance_cost": _calc_total_maintenance_cost,
    "leases_expiring_12_months": _calc_leases_expiring_12_months,
    "tenant_concentration_top5": _calc_tenant_concentration_top5,
    "total_properties": _calc_total_properties,
    "properties_overdue_inspection": _calc_properties_overdue_inspection,
    "void_rate": _calc_void_rate,
    "total_repair_cost": _calc_total_repair_cost,
    "average_repair_cost": _calc_average_repair_cost,
    "total_planned_investment": _calc_total_planned_investment,
    "total_revenue": _calc_total_revenue,
    "total_expenses": _calc_total_expenses,
    "net_profit": _calc_net_profit,
    "profit_margin_pct": _calc_profit_margin_pct,
    "average_monthly_revenue": _calc_average_monthly_revenue,
    "total_budget": _calc_total_budget,
    "total_actual_spend": _calc_total_actual_spend,
    "total_forecast_outturn": _calc_total_forecast_outturn,
    "overall_variance_amount": _calc_overall_variance_amount,
    "overall_variance_pct": _calc_overall_variance_pct,
    "budget_utilisation_rate": _calc_budget_utilisation_rate,
    "over_budget_line_count": _calc_over_budget_line_count,
    "top5_overspend_concentration": _calc_top5_overspend_concentration,
}


def compute_kpis(
    df: pl.DataFrame,
    pack: IndustryPack,
    mapping: dict[str, str | None],
    as_of: dt.date | None = None,
    window_months: int = DEFAULT_KPI_WINDOW_MONTHS,
) -> list[KPIResult]:
    results: list[KPIResult] = []
    for kpi in pack.kpis:
        calculator = _CALCULATORS.get(kpi.kpi_id)
        if calculator is None:
            results.append(
                KPIResult(kpi.kpi_id, kpi.name, kpi.format, None, "—", error="No calculator implemented yet.")
            )
            continue
        missing = [f for f in kpi.required_fields if mapping.get(f) is None]
        if missing:
            results.append(
                KPIResult(
                    kpi.kpi_id,
                    kpi.name,
                    kpi.format,
                    None,
                    "—",
                    error=f"Missing required column(s) for: {', '.join(missing)}",
                )
            )
            continue
        try:
            value = calculator(df, mapping, as_of=as_of, window_months=window_months)
            results.append(KPIResult(kpi.kpi_id, kpi.name, kpi.format, value, _format(value, kpi.format)))
        except KPIError as exc:
            results.append(KPIResult(kpi.kpi_id, kpi.name, kpi.format, None, "—", error=str(exc)))
    return results
