import datetime as dt

import polars as pl

from app.core.industry_packs import BUSINESS_FINANCE, COMMERCIAL_PROPERTY, SOCIAL_HOUSING
from app.services.industry_kpis import compute_kpis
from app.services.industry_matching import missing_required_fields, resolve_field_mapping

COMMERCIAL_DF = pl.DataFrame(
    {
        "Unit": ["A1", "A2", "A3", "A4", "A5"],
        "Tenant Name": ["Acme Ltd", "Beta Co", "Acme Ltd", "Gamma Inc", "Delta PLC"],
        "Rent (PCM)": [1200, 950, 2000, 2100, 500],
        "Lease Expiry Date": ["2027-01-15", "2026-03-20", "2026-11-10", "2030-01-01", "2025-06-01"],
        "Occupancy Status": ["Occupied", "Occupied", "Vacant", "Occupied", "Occupied"],
        "Rent Arrears": [0, 100, 0, 50, 0],
        "Use Class": ["Office", "Office", "Retail", "Industrial", "Retail"],
    }
)


def test_commercial_property_field_mapping_resolves_messy_headers():
    mapping = resolve_field_mapping(COMMERCIAL_PROPERTY, COMMERCIAL_DF.columns)
    assert mapping["tenant"] == "Tenant Name"
    assert mapping["rent_amount"] == "Rent (PCM)"
    assert mapping["lease_end_date"] == "Lease Expiry Date"
    assert mapping["status"] == "Occupancy Status"
    assert missing_required_fields(COMMERCIAL_PROPERTY, mapping) == []


def test_commercial_property_kpis_are_numerically_correct():
    mapping = resolve_field_mapping(COMMERCIAL_PROPERTY, COMMERCIAL_DF.columns)
    results = {r.kpi_id: r for r in compute_kpis(COMMERCIAL_DF, COMMERCIAL_PROPERTY, mapping, as_of=dt.date(2026, 10, 9))}

    assert results["total_rent_roll"].value == 6750.0
    assert results["average_rent"].value == 1350.0
    assert results["occupancy_rate"].value == 80.0
    assert results["vacancy_rate"].value == 20.0
    assert results["total_arrears"].value == 150.0
    assert round(results["arrears_pct_of_rent_roll"].value, 2) == 2.22
    # 2027-01-15 and 2026-11-10 fall within [2026-10-09, 2027-10-09]; the
    # other three don't.
    assert results["leases_expiring_12_months"].value == 2
    # Only 4 distinct tenants exist, so the top-5 concentration is 100%.
    assert results["tenant_concentration_top5"].value == 100.0
    assert all(r.error is None for r in results.values())


def test_commercial_property_kpi_reports_error_for_unmapped_field():
    df = pl.DataFrame({"Unit": ["A1", "A2"], "Rent": [1000, 2000]})
    mapping = resolve_field_mapping(COMMERCIAL_PROPERTY, df.columns)
    assert missing_required_fields(COMMERCIAL_PROPERTY, mapping) != []

    results = {r.kpi_id: r for r in compute_kpis(df, COMMERCIAL_PROPERTY, mapping)}
    assert results["occupancy_rate"].error is not None
    assert "status" in results["occupancy_rate"].error
    # total_rent_roll's only required field (rent_amount) WAS mapped, so
    # it should still compute even though other fields are missing.
    assert results["total_rent_roll"].value == 3000.0


def test_social_housing_kpis_are_numerically_correct():
    df = pl.DataFrame(
        {
            "Property ID": ["P1", "P2", "P3", "P4"],
            "Last Inspection": ["2025-01-01", "2026-09-01", "2024-05-01", "2026-10-01"],
            "EPC": ["C", "B", "D", "C"],
            "Repair Cost": [500, 200, 1500, 100],
            "Planned Investment": [2000, 0, 5000, 1000],
            "Void Status": ["Occupied", "Void", "Occupied", "Occupied"],
        }
    )
    mapping = resolve_field_mapping(SOCIAL_HOUSING, df.columns)
    assert missing_required_fields(SOCIAL_HOUSING, mapping) == []

    results = {r.kpi_id: r for r in compute_kpis(df, SOCIAL_HOUSING, mapping, as_of=dt.date(2026, 10, 9))}
    assert results["total_properties"].value == 4
    # Cutoff is 2025-10-09; P1 (2025-01-01) and P3 (2024-05-01) are before it.
    assert results["properties_overdue_inspection"].value == 2
    assert results["total_repair_cost"].value == 2300.0
    assert results["total_planned_investment"].value == 8000.0
    assert results["average_repair_cost"].value == 575.0
    assert results["void_rate"].value == 25.0
    assert SOCIAL_HOUSING.compliance_caveat is not None
    assert "do NOT constitute legal compliance" in SOCIAL_HOUSING.compliance_caveat


def test_business_finance_kpis_are_numerically_correct():
    df = pl.DataFrame(
        {
            "Date": ["2026-01-15", "2026-02-10", "2026-02-20", "2026-03-05"],
            "Revenue": [10000, 5000, 7000, 12000],
            "Expenses": [6000, 3000, 4000, 5000],
        }
    )
    mapping = resolve_field_mapping(BUSINESS_FINANCE, df.columns)
    results = {r.kpi_id: r for r in compute_kpis(df, BUSINESS_FINANCE, mapping)}

    assert results["total_revenue"].value == 34000.0
    assert results["total_expenses"].value == 18000.0
    assert results["net_profit"].value == 16000.0
    assert round(results["profit_margin_pct"].value, 1) == 47.1
    # 3 distinct months: Jan=10000, Feb=12000, Mar=12000 -> avg 11333.33
    assert round(results["average_monthly_revenue"].value, 2) == 11333.33


def test_matching_does_not_false_positive_on_unrelated_words():
    df = pl.DataFrame({"Parent Company": ["X"], "Address": ["Y"]})
    mapping = resolve_field_mapping(COMMERCIAL_PROPERTY, df.columns)
    assert mapping["rent_amount"] is None  # "Parent Company" must not match "rent"


def test_every_pack_kpi_has_a_registered_calculator():
    """Regression test for the bug caught during this build: three social
    housing KPIs (total_repair_cost, average_repair_cost,
    total_planned_investment) were defined in the pack but had no
    calculator registered, silently returning "No calculator implemented
    yet." for every table. This asserts every KPI across every pack has
    one, so a future pack addition can't repeat the mistake unnoticed."""
    from app.core.industry_packs import INDUSTRY_PACKS
    from app.services.industry_kpis import _CALCULATORS

    missing = []
    for pack in INDUSTRY_PACKS.values():
        for kpi in pack.kpis:
            if kpi.kpi_id not in _CALCULATORS:
                missing.append(f"{pack.industry_id}:{kpi.kpi_id}")
    assert missing == [], f"KPIs with no calculator: {missing}"
