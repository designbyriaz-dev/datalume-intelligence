import datetime as dt

import polars as pl

from app.core.industry_packs import BUSINESS_FINANCE, COMMERCIAL_PROPERTY, EDUCATION, PUBLIC_SECTOR, SOCIAL_HOUSING
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


def test_public_sector_field_mapping_resolves_messy_headers():
    df = pl.DataFrame(
        {
            "Directorate": ["Adult Social Care"],
            "Budget Head": ["Staffing"],
            "Approved Budget": [1000000],
            "YTD Actual": [650000],
            "Projected Outturn": [1100000],
        }
    )
    mapping = resolve_field_mapping(PUBLIC_SECTOR, df.columns)
    assert mapping["service_area"] == "Directorate"
    assert mapping["budget_line"] == "Budget Head"
    assert mapping["annual_budget"] == "Approved Budget"
    assert mapping["actual_spend"] == "YTD Actual"
    assert mapping["forecast_outturn"] == "Projected Outturn"
    assert missing_required_fields(PUBLIC_SECTOR, mapping) == []


def test_public_sector_kpis_are_numerically_correct():
    # 7 service areas, 6 forecast to overspend by varying amounts and one
    # (G) forecast to underspend — chosen specifically so "top 5
    # overspend concentration" has to actually exclude the smallest
    # overspender (F, +5) rather than trivially summing everyone.
    df = pl.DataFrame(
        {
            "Service Area": ["A", "B", "C", "D", "E", "F", "G"],
            "Budget Line": [f"Line {i}" for i in range(7)],
            "Annual Budget": [100, 100, 100, 100, 100, 100, 100],
            "Actual Spend": [90, 80, 70, 60, 50, 55, 80],
            "Forecast Outturn": [150, 140, 130, 120, 110, 105, 90],
        }
    )
    mapping = resolve_field_mapping(PUBLIC_SECTOR, df.columns)
    assert missing_required_fields(PUBLIC_SECTOR, mapping) == []

    results = {r.kpi_id: r for r in compute_kpis(df, PUBLIC_SECTOR, mapping)}

    assert results["total_budget"].value == 700.0
    assert results["total_actual_spend"].value == 485.0
    assert results["total_forecast_outturn"].value == 845.0
    assert results["overall_variance_amount"].value == 145.0
    assert round(results["overall_variance_pct"].value, 2) == 20.71
    assert round(results["budget_utilisation_rate"].value, 2) == 69.29
    # A-F all forecast to overspend (150>100, ..., 105>100); only G
    # (90<100) doesn't.
    assert results["over_budget_line_count"].value == 6
    # Overspends by service area: A=50, B=40, C=30, D=20, E=10, F=5.
    # Top 5 (A-E) = 150 of a total overspend of 155 -> 96.77%.
    assert round(results["top5_overspend_concentration"].value, 2) == 96.77
    assert all(r.error is None for r in results.values())

    assert PUBLIC_SECTOR.compliance_caveat is not None
    assert "indicative only" in PUBLIC_SECTOR.compliance_caveat


def test_public_sector_kpi_reports_error_for_unmapped_field():
    df = pl.DataFrame({"Service Area": ["A", "B"], "Annual Budget": [100, 200]})
    mapping = resolve_field_mapping(PUBLIC_SECTOR, df.columns)
    assert missing_required_fields(PUBLIC_SECTOR, mapping) != []

    results = {r.kpi_id: r for r in compute_kpis(df, PUBLIC_SECTOR, mapping)}
    assert results["total_forecast_outturn"].error is not None
    assert "forecast_outturn" in results["total_forecast_outturn"].error
    # total_budget's only required field (annual_budget) WAS mapped, so
    # it should still compute even though other fields are missing.
    assert results["total_budget"].value == 300.0


def test_public_sector_variance_kpis_handle_no_overspending_areas():
    """Everyone's under budget — top5_overspend_concentration should
    error clearly rather than divide by zero or silently return 0."""
    df = pl.DataFrame(
        {
            "Service Area": ["A", "B"],
            "Budget Line": ["Line 1", "Line 2"],
            "Annual Budget": [100, 100],
            "Actual Spend": [50, 60],
            "Forecast Outturn": [90, 95],
        }
    )
    mapping = resolve_field_mapping(PUBLIC_SECTOR, df.columns)
    results = {r.kpi_id: r for r in compute_kpis(df, PUBLIC_SECTOR, mapping)}

    assert results["over_budget_line_count"].value == 0
    assert results["top5_overspend_concentration"].error is not None
    assert "overspend" in results["top5_overspend_concentration"].error.lower()


def test_education_field_mapping_resolves_messy_headers():
    df = pl.DataFrame(
        {
            "Pupil ID": ["S1"],
            "Possible Sessions": [50],
            "Attended Sessions": [50],
            "Year": ["Year 7"],
            "FSM": ["Yes"],
            "Grade": [65],
        }
    )
    mapping = resolve_field_mapping(EDUCATION, df.columns)
    assert mapping["student_id"] == "Pupil ID"
    assert mapping["sessions_possible"] == "Possible Sessions"
    assert mapping["sessions_attended"] == "Attended Sessions"
    assert mapping["year_group"] == "Year"
    assert mapping["pupil_premium"] == "FSM"
    assert mapping["attainment_score"] == "Grade"
    assert missing_required_fields(EDUCATION, mapping) == []


def test_education_kpis_are_numerically_correct():
    # S1 is split across two rows (e.g. two terms) specifically to prove
    # per-student aggregation sums across rows rather than treating each
    # row as a separate student. Session totals deliberately vary a lot
    # per student (50 to 200) so overall_attendance_rate (session-
    # weighted) and average_attendance_per_student (student-weighted)
    # are genuinely different numbers, not coincidentally equal.
    df = pl.DataFrame(
        {
            "Student ID": ["S1", "S1", "S2", "S3", "S4", "S5"],
            "Sessions Possible": [50, 50, 50, 200, 100, 150],
            "Sessions Attended": [50, 40, 40, 190, 99, 75],
            "Pupil Premium": ["Yes", "Yes", "Yes", "No", "No", "No"],
            "Attainment Score": [65, 70, 55, 80, 90, 45],
        }
    )
    mapping = resolve_field_mapping(EDUCATION, df.columns)
    assert missing_required_fields(EDUCATION, mapping) == []

    results = {r.kpi_id: r for r in compute_kpis(df, EDUCATION, mapping)}

    assert results["total_students"].value == 5
    # S1: 90/100=90%, S2: 40/50=80%, S3: 190/200=95%, S4: 99/100=99%,
    # S5: 75/150=50%.
    assert round(results["overall_attendance_rate"].value, 2) == 82.33
    assert round(results["average_attendance_per_student"].value, 2) == 82.8
    # S2 (80%) and S5 (50%) are below 90% -> 2 of 5 students = 40%. S1 at
    # exactly 90% is NOT persistently absent (threshold is "below 90").
    assert round(results["persistent_absence_rate"].value, 2) == 40.0
    # PP students S1 (90%) and S2 (80%) average 85%; non-PP S3/S4/S5
    # (95%, 99%, 50%) average 81.33% -> gap = +3.67.
    assert round(results["pupil_premium_attendance_gap"].value, 2) == 3.67
    assert round(results["average_attainment_score"].value, 2) == 67.5
    assert all(r.error is None for r in results.values())

    assert EDUCATION.compliance_caveat is not None
    assert "indicative only" in EDUCATION.compliance_caveat


def test_education_persistent_absence_boundary_is_strictly_below_90():
    """A student at exactly 90% attendance must NOT count as
    persistently absent — the DfE's definition is 'below 90%', not
    'at or below'."""
    df = pl.DataFrame(
        {
            "Student ID": ["S1"],
            "Sessions Possible": [100],
            "Sessions Attended": [90],
            "Pupil Premium": ["No"],
        }
    )
    mapping = resolve_field_mapping(EDUCATION, df.columns)
    results = {r.kpi_id: r for r in compute_kpis(df, EDUCATION, mapping)}
    assert results["persistent_absence_rate"].value == 0.0


def test_education_kpi_reports_error_for_unmapped_field():
    df = pl.DataFrame({"Student ID": ["S1", "S2"], "Sessions Possible": [100, 100]})
    mapping = resolve_field_mapping(EDUCATION, df.columns)
    assert missing_required_fields(EDUCATION, mapping) != []

    results = {r.kpi_id: r for r in compute_kpis(df, EDUCATION, mapping)}
    assert results["overall_attendance_rate"].error is not None
    assert "sessions_attended" in results["overall_attendance_rate"].error
    # total_students's only required field (student_id) WAS mapped, so
    # it should still compute even though other fields are missing.
    assert results["total_students"].value == 2


def test_education_pupil_premium_gap_handles_no_pp_students():
    """Nobody is Pupil Premium — the gap KPI should error clearly
    rather than divide by zero."""
    df = pl.DataFrame(
        {
            "Student ID": ["S1", "S2"],
            "Sessions Possible": [100, 100],
            "Sessions Attended": [90, 80],
            "Pupil Premium": ["No", "No"],
        }
    )
    mapping = resolve_field_mapping(EDUCATION, df.columns)
    results = {r.kpi_id: r for r in compute_kpis(df, EDUCATION, mapping)}
    assert results["pupil_premium_attendance_gap"].error is not None
    assert "Pupil Premium" in results["pupil_premium_attendance_gap"].error


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
