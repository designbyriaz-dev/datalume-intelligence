"""PDF report generation. Deterministic — built entirely from a
DatasetTable's stored profile (app/services/profiling.py) and, where
included, saved AnalysisRun results. No LLM narrative is generated here;
once the AI analyst (app/services/ai/) is wired to a real model, its
grounded explanations can be composed into a report alongside this, but
that's explicitly not what this module does today.
"""

from __future__ import annotations

import datetime as dt
import io
from datetime import datetime, timezone

import polars as pl
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.models.dataset import DatasetTable
from app.services.analytics import AnalyticsError, _parse_date_cell, group_aggregate, time_trend
from app.services.industry_kpis import DEFAULT_KPI_WINDOW_MONTHS, _VACANT_MARKERS, _add_months, KPIResult

_POOR_EPC_RATINGS = {"E", "F", "G"}

_STYLES = getSampleStyleSheet()
_TITLE_STYLE = ParagraphStyle("DLTitle", parent=_STYLES["Title"], fontSize=20, spaceAfter=4)
_META_STYLE = ParagraphStyle("DLMeta", parent=_STYLES["Normal"], textColor=colors.grey, spaceAfter=16)
_H2_STYLE = ParagraphStyle("DLH2", parent=_STYLES["Heading2"], spaceBefore=16, spaceAfter=8)
_BODY_STYLE = _STYLES["BodyText"]

_SEVERITY_COLOR = {"warning": colors.HexColor("#b45309"), "info": colors.HexColor("#475569")}


def _months_label(n: int) -> str:
    return f"{n} month" if n == 1 else f"{n} months"


def _quality_badge_color(score: float) -> colors.Color:
    if score >= 85:
        return colors.HexColor("#15803d")
    if score >= 60:
        return colors.HexColor("#b45309")
    return colors.HexColor("#b91c1c")


def _missing_percentage_chart(columns: list[dict]) -> Drawing | None:
    flagged = [c for c in columns if c["null_ratio"] > 0]
    if not flagged:
        return None

    labels = [c["name"][:14] for c in flagged]
    values = [round(c["null_ratio"] * 100, 1) for c in flagged]

    drawing = Drawing(450, 180)
    chart = VerticalBarChart()
    chart.x = 40
    chart.y = 30
    chart.height = 130
    chart.width = 380
    chart.data = [values]
    chart.categoryAxis.categoryNames = labels
    chart.categoryAxis.labels.angle = 30
    chart.categoryAxis.labels.dy = -10
    chart.categoryAxis.labels.fontSize = 7
    chart.valueAxis.valueMin = 0
    chart.valueAxis.valueMax = max(100, max(values) + 10)
    chart.bars[0].fillColor = colors.HexColor("#3b6dfb")
    drawing.add(chart)
    return drawing


def generate_data_quality_report_pdf(
    *, dataset_name: str, table: DatasetTable, generated_by_name: str
) -> bytes:
    profile = table.profile
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
    )

    story = []
    story.append(Paragraph("Data Quality Report", _TITLE_STYLE))
    story.append(
        Paragraph(
            f"{dataset_name} &mdash; {table.sheet_name}<br/>"
            f"Generated {datetime.now(timezone.utc).strftime('%d %B %Y, %H:%M UTC')} by {generated_by_name}",
            _META_STYLE,
        )
    )

    score = profile["quality_score"]
    summary_rows = [
        ["Quality score", f"{score}/100"],
        ["Rows", str(profile["row_count"])],
        ["Columns", str(profile["column_count"])],
        ["Duplicate rows", str(profile["duplicate_row_count"])],
        ["Issues found", str(len(profile["issues"]))],
    ]
    summary_table = Table(summary_rows, colWidths=[6 * cm, 6 * cm])
    summary_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("TEXTCOLOR", (1, 0), (1, 0), _quality_badge_color(score)),
                ("FONTNAME", (1, 0), (1, 0), "Helvetica-Bold"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LINEBELOW", (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ]
        )
    )
    story.append(summary_table)

    story.append(Paragraph("Column profile", _H2_STYLE))
    column_header = ["Column", "Type", "Looks like", "Missing", "Distinct", "Flags"]
    column_rows = [column_header]
    for col in profile["columns"]:
        column_rows.append(
            [
                col["name"],
                col["inferred_type"],
                col["suggested_type"] if col["suggested_type"] != col["inferred_type"] else "",
                f"{col['null_ratio']:.0%}",
                str(col["distinct_count"]),
                ", ".join(col["flags"]),
            ]
        )
    column_table = Table(column_rows, colWidths=[3.2 * cm, 2.2 * cm, 2.4 * cm, 2 * cm, 2 * cm, 4.2 * cm])
    column_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    story.append(column_table)

    chart = _missing_percentage_chart(profile["columns"])
    if chart is not None:
        story.append(Paragraph("Missing values by column (%)", _H2_STYLE))
        story.append(chart)

    if profile["issues"]:
        story.append(Paragraph("Data quality issues", _H2_STYLE))
        for issue in profile["issues"]:
            color = _SEVERITY_COLOR.get(issue["severity"], colors.black)
            column_part = f"<b>{issue['column']}</b>: " if issue["column"] else ""
            story.append(
                Paragraph(
                    f'<font color="{color.hexval()}">[{issue["severity"].upper()}]</font> '
                    f"{column_part}{issue['detail']}",
                    _BODY_STYLE,
                )
            )
            story.append(Spacer(1, 4))
    else:
        story.append(Paragraph("No data quality issues detected.", _BODY_STYLE))

    story.append(Spacer(1, 20))
    story.append(
        Paragraph(
            "Methodology: the quality score is a deterministic calculation from missing-value "
            "ratio, duplicate-row ratio and columns with detected formatting issues (see "
            "docs/ARCHITECTURE.md for the exact formula). This report contains no AI-generated "
            "narrative or figures.",
            ParagraphStyle("DLFootnote", parent=_STYLES["Normal"], fontSize=7, textColor=colors.grey),
        )
    )

    doc.build(story)
    return buffer.getvalue()


def _simple_table(rows: list[list[str]], col_widths: list[float]) -> Table:
    table = Table(rows, colWidths=col_widths)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ]
        )
    )
    return table


def generate_commercial_property_report_pdf(
    *,
    dataset_name: str,
    table_sheet_name: str,
    generated_by_name: str,
    df: pl.DataFrame,
    mapping: dict[str, str | None],
    kpi_results: list[KPIResult],
    window_months: int = DEFAULT_KPI_WINDOW_MONTHS,
) -> bytes:
    """The one specialist report template actually implemented in Phase 5
    (see docs/CHECKLIST.md for the other 11 the brief describes). Built
    from the same deterministic KPI engine as the /industry-kpis API —
    this report and that endpoint can never disagree with each other
    because they share the exact same calculation code."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, topMargin=2 * cm, bottomMargin=2 * cm, leftMargin=2 * cm, rightMargin=2 * cm
    )

    story = []
    story.append(Paragraph("Commercial Property Portfolio Report", _TITLE_STYLE))
    story.append(
        Paragraph(
            f"{dataset_name} &mdash; {table_sheet_name}<br/>"
            f"Generated {datetime.now(timezone.utc).strftime('%d %B %Y, %H:%M UTC')} by {generated_by_name}",
            _META_STYLE,
        )
    )

    story.append(Paragraph("Key metrics", _H2_STYLE))
    kpi_rows = [["Metric", "Value"]]
    for kpi in kpi_results:
        # The KPI's stable name always says "12 Months" (see
        # app/core/industry_packs.py) since it's a fixed identifier, not
        # workspace-aware — rename it here so it never contradicts the
        # window actually used, same fix as the frontend KPI panel.
        label = (
            f"Leases Expiring Within {_months_label(window_months).title()}"
            if kpi.kpi_id == "leases_expiring_12_months"
            else kpi.name
        )
        kpi_rows.append([label, kpi.formatted if kpi.error is None else "Not available"])
    kpi_table = Table(kpi_rows, colWidths=[9 * cm, 6 * cm])
    kpi_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ]
        )
    )
    story.append(kpi_table)

    category_col = mapping.get("category")
    rent_col = mapping.get("rent_amount")
    if category_col and rent_col:
        story.append(Paragraph("Rent roll by category", _H2_STYLE))
        breakdown = group_aggregate(df, group_by=category_col, agg="sum", value_column=rent_col)
        rows = [["Category", "Rent"]] + [
            [g["label"], f"£{g['value']:,.2f}"] for g in breakdown["groups"]
        ]
        cat_table = Table(rows, colWidths=[9 * cm, 6 * cm])
        cat_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
                ]
            )
        )
        story.append(cat_table)

    tenant_col = mapping.get("tenant")
    lease_end_col = mapping.get("lease_end_date")
    if tenant_col and lease_end_col and rent_col:
        today = dt.date.today()
        cutoff = _add_months(today, window_months)
        expiring = []
        for row in df.select([tenant_col, rent_col, lease_end_col]).to_dicts():
            raw_date = row[lease_end_col]
            parsed = raw_date if isinstance(raw_date, dt.date) else _parse_date_cell(str(raw_date)) if raw_date else None
            if parsed is not None and today <= parsed <= cutoff:
                expiring.append((parsed, row[tenant_col], row[rent_col]))
        expiring.sort(key=lambda r: r[0])

        story.append(Paragraph(f"Lease expiry schedule (next {_months_label(window_months)})", _H2_STYLE))
        if expiring:
            rows = [["Lease End Date", "Tenant", "Rent"]] + [
                [d.isoformat(), tenant, f"£{rent:,.2f}"] for d, tenant, rent in expiring
            ]
            lease_table = Table(rows, colWidths=[4 * cm, 7 * cm, 4 * cm])
            lease_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("FONTSIZE", (0, 0), (-1, -1), 9),
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
                    ]
                )
            )
            story.append(lease_table)
        else:
            story.append(Paragraph(f"No leases expire within the next {_months_label(window_months)}.", _BODY_STYLE))

    story.append(Spacer(1, 20))
    story.append(
        Paragraph(
            "Methodology: all figures are deterministic calculations over the uploaded data — see "
            "app/services/industry_kpis.py for the exact formula behind each metric. This report "
            "contains no AI-generated narrative or figures.",
            ParagraphStyle("DLFootnote2", parent=_STYLES["Normal"], fontSize=7, textColor=colors.grey),
        )
    )

    doc.build(story)
    return buffer.getvalue()


def generate_social_housing_compliance_exceptions_report_pdf(
    *,
    dataset_name: str,
    table_sheet_name: str,
    generated_by_name: str,
    df: pl.DataFrame,
    mapping: dict[str, str | None],
    compliance_caveat: str | None,
    window_months: int = DEFAULT_KPI_WINDOW_MONTHS,
) -> bytes:
    """The fifth specialist report template, and the first to be a
    second report on an existing pack rather than a first report on a
    new one (social_housing already had "Social Housing Asset Report"
    — see generate_social_housing_report_pdf above). Every existing
    pack already has exactly one report; adding a 5th report meant
    extending a pack, not starting a new one (see docs/CHECKLIST.md's
    "Immediate next steps" item 12 — a new pack like public sector would
    need real domain input to write its KPIs honestly, which this
    doesn't need since it reuses social_housing's already-tested fields).

    Deliberately NOT a copy of the Asset Report with a new title: that
    report is a portfolio *overview* (aggregate KPIs, the full EPC
    distribution across every band). This one is a row-level *exceptions
    audit* — only the properties that need action, nothing else — which
    is why it has two sections the Asset Report doesn't: properties with
    no inspection date recorded at all (a data gap that is itself a
    compliance risk, since an ungraded property can't be shown compliant
    either), and void properties with no planned investment recorded.
    The overdue-inspection cutoff and void-status detection reuse the
    exact same logic as the KPI engine
    (app/services/industry_kpis.py's properties_overdue_inspection
    calculator and _VACANT_MARKERS) rather than redefining "overdue" or
    "void" a second, possibly-drifting way."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, topMargin=2 * cm, bottomMargin=2 * cm, leftMargin=2 * cm, rightMargin=2 * cm
    )

    story = []
    story.append(Paragraph("Social Housing Compliance Exceptions Report", _TITLE_STYLE))
    story.append(
        Paragraph(
            f"{dataset_name} &mdash; {table_sheet_name}<br/>"
            f"Generated {datetime.now(timezone.utc).strftime('%d %B %Y, %H:%M UTC')} by {generated_by_name}",
            _META_STYLE,
        )
    )

    if compliance_caveat:
        caveat_style = ParagraphStyle(
            "DLComplianceCaveat2",
            parent=_STYLES["Normal"],
            textColor=colors.HexColor("#92400e"),
            backColor=colors.HexColor("#fffbeb"),
            borderColor=colors.HexColor("#fcd34d"),
            borderWidth=0.5,
            borderPadding=8,
            spaceAfter=16,
        )
        story.append(Paragraph(compliance_caveat, caveat_style))

    property_col = mapping.get("property_id")
    inspection_col = mapping.get("last_inspection_date")
    epc_col = mapping.get("epc_rating")
    void_col = mapping.get("void_status")
    investment_col = mapping.get("planned_investment_amount")

    today = dt.date.today()
    cutoff = _add_months(today, -window_months)

    overdue: list[tuple[dt.date, str]] = []
    no_inspection_date: list[str] = []
    if property_col and inspection_col:
        for row in df.select([property_col, inspection_col]).to_dicts():
            raw_date = row[inspection_col]
            if raw_date is None:
                no_inspection_date.append(str(row[property_col]))
                continue
            parsed = raw_date if isinstance(raw_date, dt.date) else _parse_date_cell(str(raw_date))
            if parsed is None:
                no_inspection_date.append(str(row[property_col]))
            elif parsed < cutoff:
                overdue.append((parsed, str(row[property_col])))
        overdue.sort(key=lambda r: r[0])

    poor_epc: list[tuple[str, str]] = []
    if property_col and epc_col:
        for row in df.select([property_col, epc_col]).to_dicts():
            rating = row[epc_col]
            if rating is not None and str(rating).strip().upper() in _POOR_EPC_RATINGS:
                poor_epc.append((str(row[property_col]), str(rating).strip().upper()))
        poor_epc.sort(key=lambda r: r[1], reverse=True)  # worst (G) first

    void_no_investment: list[str] = []
    if property_col and void_col:
        for row in df.select(
            [property_col, void_col] + ([investment_col] if investment_col else [])
        ).to_dicts():
            status = row[void_col]
            if status is None or not any(m in str(status).lower() for m in _VACANT_MARKERS):
                continue
            planned = row[investment_col] if investment_col else None
            if planned is None or planned == 0:
                void_no_investment.append(str(row[property_col]))

    story.append(Paragraph("Exception summary", _H2_STYLE))
    summary_rows = [
        ["Exception", "Count"],
        [f"Overdue inspection (>{_months_label(window_months)})", str(len(overdue))],
        ["No inspection date recorded", str(len(no_inspection_date))],
        ["Poor EPC rating (E, F or G)", str(len(poor_epc))],
        ["Void with no planned investment", str(len(void_no_investment))],
    ]
    story.append(_simple_table(summary_rows, [11 * cm, 4 * cm]))

    story.append(Paragraph(f"Properties overdue inspection (>{_months_label(window_months)})", _H2_STYLE))
    if overdue:
        rows = [["Last Inspection", "Property"]] + [[d.isoformat(), p] for d, p in overdue]
        story.append(_simple_table(rows, [4 * cm, 11 * cm]))
    else:
        story.append(Paragraph("No properties are overdue an inspection.", _BODY_STYLE))

    story.append(Paragraph("Properties with no inspection date recorded", _H2_STYLE))
    if no_inspection_date:
        rows = [["Property"]] + [[p] for p in no_inspection_date]
        story.append(_simple_table(rows, [15 * cm]))
    else:
        story.append(Paragraph("Every property has a recorded inspection date.", _BODY_STYLE))

    story.append(Paragraph("Properties with poor EPC ratings (E, F or G)", _H2_STYLE))
    if poor_epc:
        rows = [["Property", "EPC Rating"]] + [[p, rating] for p, rating in poor_epc]
        story.append(_simple_table(rows, [11 * cm, 4 * cm]))
    else:
        story.append(Paragraph("No properties have a poor EPC rating.", _BODY_STYLE))

    story.append(Paragraph("Void properties with no planned investment", _H2_STYLE))
    if void_no_investment:
        rows = [["Property"]] + [[p] for p in void_no_investment]
        story.append(_simple_table(rows, [15 * cm]))
    else:
        story.append(Paragraph("No void properties are missing a planned investment figure.", _BODY_STYLE))

    story.append(Spacer(1, 20))
    story.append(
        Paragraph(
            "Methodology: all figures are deterministic calculations over the uploaded data — see "
            "app/services/industry_kpis.py for the exact overdue-inspection and void-status logic "
            "this report reuses. This report contains no AI-generated narrative or figures. It does "
            "not constitute legal compliance certification — see the caveat above.",
            ParagraphStyle("DLFootnote6", parent=_STYLES["Normal"], fontSize=7, textColor=colors.grey),
        )
    )

    doc.build(story)
    return buffer.getvalue()


def generate_residential_property_report_pdf(
    *,
    dataset_name: str,
    table_sheet_name: str,
    generated_by_name: str,
    df: pl.DataFrame,
    mapping: dict[str, str | None],
    kpi_results: list[KPIResult],
    window_months: int = DEFAULT_KPI_WINDOW_MONTHS,
) -> bytes:
    """The second specialist report template (the first, commercial
    property, was built in Phase 5 — see docs/CHECKLIST.md for the
    other 10 the brief describes). Built from the exact same KPI engine
    as /industry-kpis for the residential_property pack, so this report
    and that endpoint can never disagree. Two sections beyond the KPI
    table that commercial property's report doesn't have — tenancies
    ending soon and properties in arrears — since the residential pack
    has no category/lease-start fields to build commercial's
    rent-by-category breakdown from."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, topMargin=2 * cm, bottomMargin=2 * cm, leftMargin=2 * cm, rightMargin=2 * cm
    )

    story = []
    story.append(Paragraph("Residential Property Portfolio Report", _TITLE_STYLE))
    story.append(
        Paragraph(
            f"{dataset_name} &mdash; {table_sheet_name}<br/>"
            f"Generated {datetime.now(timezone.utc).strftime('%d %B %Y, %H:%M UTC')} by {generated_by_name}",
            _META_STYLE,
        )
    )

    story.append(Paragraph("Key metrics", _H2_STYLE))
    kpi_rows = [["Metric", "Value"]]
    for kpi in kpi_results:
        kpi_rows.append([kpi.name, kpi.formatted if kpi.error is None else "Not available"])
    story.append(_simple_table(kpi_rows, [9 * cm, 6 * cm]))

    tenant_col = mapping.get("tenant")
    rent_col = mapping.get("rent_amount")
    tenancy_end_col = mapping.get("tenancy_end_date")
    unit_col = mapping.get("unit")
    if tenant_col and tenancy_end_col and rent_col:
        today = dt.date.today()
        cutoff = _add_months(today, window_months)
        expiring = []
        for row in df.select([tenant_col, rent_col, tenancy_end_col]).to_dicts():
            raw_date = row[tenancy_end_col]
            parsed = raw_date if isinstance(raw_date, dt.date) else _parse_date_cell(str(raw_date)) if raw_date else None
            if parsed is not None and today <= parsed <= cutoff:
                expiring.append((parsed, row[tenant_col], row[rent_col]))
        expiring.sort(key=lambda r: r[0])

        story.append(Paragraph(f"Tenancies ending within {_months_label(window_months)}", _H2_STYLE))
        if expiring:
            rows = [["Tenancy End Date", "Tenant", "Rent"]] + [
                [d.isoformat(), tenant, f"£{rent:,.2f}"] for d, tenant, rent in expiring
            ]
            story.append(_simple_table(rows, [4 * cm, 7 * cm, 4 * cm]))
        else:
            story.append(Paragraph(f"No tenancies end within the next {_months_label(window_months)}.", _BODY_STYLE))

    arrears_col = mapping.get("arrears_amount")
    if arrears_col and (unit_col or tenant_col):
        label_col = unit_col or tenant_col
        label_header = "Property" if unit_col else "Tenant"
        in_arrears = [
            (row[label_col], row[arrears_col])
            for row in df.select([label_col, arrears_col]).to_dicts()
            if row[arrears_col] is not None and row[arrears_col] > 0
        ]
        in_arrears.sort(key=lambda r: r[1], reverse=True)

        story.append(Paragraph("Properties in arrears", _H2_STYLE))
        if in_arrears:
            rows = [[label_header, "Arrears"]] + [
                [str(label), f"£{amount:,.2f}"] for label, amount in in_arrears
            ]
            story.append(_simple_table(rows, [9 * cm, 6 * cm]))
        else:
            story.append(Paragraph("No properties currently in arrears.", _BODY_STYLE))

    story.append(Spacer(1, 20))
    story.append(
        Paragraph(
            "Methodology: all figures are deterministic calculations over the uploaded data — see "
            "app/services/industry_kpis.py for the exact formula behind each metric. This report "
            "contains no AI-generated narrative or figures.",
            ParagraphStyle("DLFootnote3", parent=_STYLES["Normal"], fontSize=7, textColor=colors.grey),
        )
    )

    doc.build(story)
    return buffer.getvalue()


def generate_social_housing_report_pdf(
    *,
    dataset_name: str,
    table_sheet_name: str,
    generated_by_name: str,
    df: pl.DataFrame,
    mapping: dict[str, str | None],
    kpi_results: list[KPIResult],
    compliance_caveat: str | None,
    window_months: int = DEFAULT_KPI_WINDOW_MONTHS,
) -> bytes:
    """The third specialist report template. Built from the exact same
    KPI engine as /industry-kpis for the social_housing pack. Unlike
    the commercial/residential property reports, this is the first PDF
    report to render a compliance caveat — the brief's required
    disclaimer already shown in the API response and dashboard UI, but
    not previously exercised in PDF form. Rendered prominently near the
    top (not buried in a footnote) since it qualifies every figure that
    follows it."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, topMargin=2 * cm, bottomMargin=2 * cm, leftMargin=2 * cm, rightMargin=2 * cm
    )

    story = []
    story.append(Paragraph("Social Housing Asset Report", _TITLE_STYLE))
    story.append(
        Paragraph(
            f"{dataset_name} &mdash; {table_sheet_name}<br/>"
            f"Generated {datetime.now(timezone.utc).strftime('%d %B %Y, %H:%M UTC')} by {generated_by_name}",
            _META_STYLE,
        )
    )

    if compliance_caveat:
        caveat_style = ParagraphStyle(
            "DLComplianceCaveat",
            parent=_STYLES["Normal"],
            textColor=colors.HexColor("#92400e"),
            backColor=colors.HexColor("#fffbeb"),
            borderColor=colors.HexColor("#fcd34d"),
            borderWidth=0.5,
            borderPadding=8,
            spaceAfter=16,
        )
        story.append(Paragraph(compliance_caveat, caveat_style))

    story.append(Paragraph("Key metrics", _H2_STYLE))
    kpi_rows = [["Metric", "Value"]]
    for kpi in kpi_results:
        kpi_rows.append([kpi.name, kpi.formatted if kpi.error is None else "Not available"])
    story.append(_simple_table(kpi_rows, [9 * cm, 6 * cm]))

    property_col = mapping.get("property_id")
    inspection_col = mapping.get("last_inspection_date")
    if property_col and inspection_col:
        today = dt.date.today()
        cutoff = _add_months(today, -window_months)
        overdue = []
        for row in df.select([property_col, inspection_col]).to_dicts():
            raw_date = row[inspection_col]
            parsed = raw_date if isinstance(raw_date, dt.date) else _parse_date_cell(str(raw_date)) if raw_date else None
            if parsed is not None and parsed < cutoff:
                overdue.append((parsed, row[property_col]))
        overdue.sort(key=lambda r: r[0])  # most overdue (oldest inspection) first

        story.append(Paragraph(f"Properties overdue inspection (>{_months_label(window_months)})", _H2_STYLE))
        if overdue:
            rows = [["Last Inspection", "Property"]] + [[d.isoformat(), str(p)] for d, p in overdue]
            story.append(_simple_table(rows, [4 * cm, 11 * cm]))
        else:
            story.append(Paragraph("No properties are overdue an inspection.", _BODY_STYLE))

    epc_col = mapping.get("epc_rating")
    if epc_col:
        story.append(Paragraph("EPC rating distribution", _H2_STYLE))
        breakdown = group_aggregate(df, group_by=epc_col, agg="count")
        rows = [["EPC Rating", "Count"]] + [
            [g["label"] if g["label"] is not None else "(missing)", str(g["value"])] for g in breakdown["groups"]
        ]
        story.append(_simple_table(rows, [9 * cm, 6 * cm]))

    story.append(Spacer(1, 20))
    story.append(
        Paragraph(
            "Methodology: all figures are deterministic calculations over the uploaded data — see "
            "app/services/industry_kpis.py for the exact formula behind each metric. This report "
            "contains no AI-generated narrative or figures. It does not constitute legal compliance "
            "certification — see the caveat above.",
            ParagraphStyle("DLFootnote4", parent=_STYLES["Normal"], fontSize=7, textColor=colors.grey),
        )
    )

    doc.build(story)
    return buffer.getvalue()


def generate_business_finance_report_pdf(
    *,
    dataset_name: str,
    table_sheet_name: str,
    generated_by_name: str,
    df: pl.DataFrame,
    mapping: dict[str, str | None],
    kpi_results: list[KPIResult],
) -> bytes:
    """The fourth specialist report template, completing coverage of
    every industry pack from the brief's Phase 5 "Create" list — built
    from the exact same KPI engine as /industry-kpis. The first report
    with a month-by-month trend section (reusing `time_trend` from the
    Phase 3 analytics engine, not new trend logic) and a "top N" ranked
    section (top 5 customers by revenue) — neither of the other three
    reports needed either."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, topMargin=2 * cm, bottomMargin=2 * cm, leftMargin=2 * cm, rightMargin=2 * cm
    )

    story = []
    story.append(Paragraph("Business Performance Report", _TITLE_STYLE))
    story.append(
        Paragraph(
            f"{dataset_name} &mdash; {table_sheet_name}<br/>"
            f"Generated {datetime.now(timezone.utc).strftime('%d %B %Y, %H:%M UTC')} by {generated_by_name}",
            _META_STYLE,
        )
    )

    story.append(Paragraph("Key metrics", _H2_STYLE))
    kpi_rows = [["Metric", "Value"]]
    for kpi in kpi_results:
        kpi_rows.append([kpi.name, kpi.formatted if kpi.error is None else "Not available"])
    story.append(_simple_table(kpi_rows, [9 * cm, 6 * cm]))

    date_col = mapping.get("date")
    revenue_col = mapping.get("revenue")
    expenses_col = mapping.get("expenses")
    category_col = mapping.get("category")
    customer_col = mapping.get("customer")

    if date_col and revenue_col:
        story.append(Paragraph("Monthly revenue trend", _H2_STYLE))
        try:
            trend = time_trend(df, date_col, revenue_col, period="month", agg="sum")
            rows = [["Month", "Revenue"]] + [
                [p["period"], f"£{p['value']:,.2f}"] for p in trend["points"]
            ]
            story.append(_simple_table(rows, [5 * cm, 10 * cm]))
        except AnalyticsError as exc:
            story.append(Paragraph(f"Could not build a trend: {exc}", _BODY_STYLE))

    if category_col and revenue_col:
        story.append(Paragraph("Revenue by category", _H2_STYLE))
        breakdown = group_aggregate(df, group_by=category_col, agg="sum", value_column=revenue_col)
        rows = [["Category", "Revenue"]] + [
            [g["label"] if g["label"] is not None else "(missing)", f"£{g['value']:,.2f}"]
            for g in breakdown["groups"]
        ]
        story.append(_simple_table(rows, [9 * cm, 6 * cm]))

    if category_col and expenses_col:
        story.append(Paragraph("Expenses by category", _H2_STYLE))
        breakdown = group_aggregate(df, group_by=category_col, agg="sum", value_column=expenses_col)
        rows = [["Category", "Expenses"]] + [
            [g["label"] if g["label"] is not None else "(missing)", f"£{g['value']:,.2f}"]
            for g in breakdown["groups"]
        ]
        story.append(_simple_table(rows, [9 * cm, 6 * cm]))

    if customer_col and revenue_col:
        story.append(Paragraph("Top 5 customers by revenue", _H2_STYLE))
        breakdown = group_aggregate(df, group_by=customer_col, agg="sum", value_column=revenue_col)
        top_groups = breakdown["groups"][:5]  # group_aggregate already sorts descending by value
        rows = [["Customer", "Revenue"]] + [
            [g["label"] if g["label"] is not None else "(missing)", f"£{g['value']:,.2f}"] for g in top_groups
        ]
        story.append(_simple_table(rows, [9 * cm, 6 * cm]))

    story.append(Spacer(1, 20))
    story.append(
        Paragraph(
            "Methodology: all figures are deterministic calculations over the uploaded data — see "
            "app/services/industry_kpis.py for the exact formula behind each metric. This report "
            "contains no AI-generated narrative or figures.",
            ParagraphStyle("DLFootnote5", parent=_STYLES["Normal"], fontSize=7, textColor=colors.grey),
        )
    )

    doc.build(story)
    return buffer.getvalue()


def generate_residential_repairs_maintenance_report_pdf(
    *,
    dataset_name: str,
    table_sheet_name: str,
    generated_by_name: str,
    df: pl.DataFrame,
    mapping: dict[str, str | None],
    kpi_results: list[KPIResult],
) -> bytes:
    """The sixth specialist report template, and the second pack
    (after social_housing — see
    generate_social_housing_compliance_exceptions_report_pdf above) to
    get a second report rather than a first. residential_property's
    existing Portfolio Report (generate_residential_property_report_pdf)
    already covers tenancies ending soon and arrears, but never actually
    shows maintenance_cost per property — only its aggregate KPI
    (total_maintenance_cost). That per-property breakdown is genuinely
    new content, not a re-presentation of something the Portfolio Report
    already shows, which is the bar every second report on a pack in
    this codebase is held to (see the compliance-exceptions report's own
    docstring for why that bar exists).

    Unlike the compliance-exceptions report, "no maintenance recorded"
    isn't treated as an exception needing a warning colour — a property
    with zero maintenance spend may simply need no repairs yet. It's
    listed as a plain informational section, not flagged as a problem,
    since nothing in this pack's fields can tell the difference between
    "nothing needed fixing" and "nothing was logged"."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, topMargin=2 * cm, bottomMargin=2 * cm, leftMargin=2 * cm, rightMargin=2 * cm
    )

    story = []
    story.append(Paragraph("Residential Repairs &amp; Maintenance Report", _TITLE_STYLE))
    story.append(
        Paragraph(
            f"{dataset_name} &mdash; {table_sheet_name}<br/>"
            f"Generated {datetime.now(timezone.utc).strftime('%d %B %Y, %H:%M UTC')} by {generated_by_name}",
            _META_STYLE,
        )
    )

    story.append(Paragraph("Key metrics", _H2_STYLE))
    kpi_rows = [["Metric", "Value"]]
    for kpi in kpi_results:
        kpi_rows.append([kpi.name, kpi.formatted if kpi.error is None else "Not available"])
    story.append(_simple_table(kpi_rows, [9 * cm, 6 * cm]))

    unit_col = mapping.get("unit")
    tenant_col = mapping.get("tenant")
    maintenance_col = mapping.get("maintenance_cost")
    label_col = unit_col or tenant_col
    label_header = "Property" if unit_col else "Tenant"

    if label_col and maintenance_col:
        spent: list[tuple[str, float]] = []
        unrecorded: list[str] = []
        for row in df.select([label_col, maintenance_col]).to_dicts():
            cost = row[maintenance_col]
            if cost is None or cost == 0:
                unrecorded.append(str(row[label_col]))
            else:
                spent.append((str(row[label_col]), float(cost)))
        spent.sort(key=lambda r: r[1], reverse=True)

        story.append(Paragraph("Maintenance spend by property (highest first)", _H2_STYLE))
        if spent:
            rows = [[label_header, "Maintenance Spend"]] + [
                [label, f"£{cost:,.2f}"] for label, cost in spent
            ]
            story.append(_simple_table(rows, [9 * cm, 6 * cm]))
        else:
            story.append(Paragraph("No properties have recorded maintenance spend.", _BODY_STYLE))

        story.append(Paragraph("Properties with no recorded maintenance spend", _H2_STYLE))
        if unrecorded:
            story.append(
                Paragraph(
                    "Not necessarily a problem — a property may simply not have needed any repairs yet. "
                    "Listed for completeness, not as an exception.",
                    _BODY_STYLE,
                )
            )
            rows = [[label_header]] + [[label] for label in unrecorded]
            story.append(_simple_table(rows, [15 * cm]))
        else:
            story.append(Paragraph("Every property has recorded maintenance spend.", _BODY_STYLE))

    story.append(Spacer(1, 20))
    story.append(
        Paragraph(
            "Methodology: all figures are deterministic calculations over the uploaded data — see "
            "app/services/industry_kpis.py for the exact formula behind each metric. This report "
            "contains no AI-generated narrative or figures.",
            ParagraphStyle("DLFootnote7", parent=_STYLES["Normal"], fontSize=7, textColor=colors.grey),
        )
    )

    doc.build(story)
    return buffer.getvalue()
