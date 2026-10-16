"""Industry pack registry — the brief's "recognised data schemas, column
aliases, validation rules, KPI definitions, ... suggested AI questions,
industry terminology, required input fields, calculation methodologies"
per pack, in one place (same registry pattern as app/core/plans.py and
app/services/tools.py).

Scope: the four packs named in the brief's Phase 5 deliverable list —
commercial property, residential property, business finance, and social
housing (section 9 also describes public sector and education/health
packs, but those weren't in the Phase 5 "Create" list, so they're not
built here; public sector in particular would need real domain input
before the KPI definitions below could be written honestly).

KPI counts here are a representative subset of each pack's brief
section, not an exhaustive implementation of every metric mentioned —
each one is a real, tested calculation (see app/services/industry_kpis.py),
not a stub, but the brief describes more analysis per industry than one
phase should build in one pass. See docs/CHECKLIST.md for exactly which
KPIs exist.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ColumnAlias:
    canonical_field: str
    description: str
    # Lowercase, normalized variants to match against actual column
    # names — see app/services/industry_matching.py for how these are
    # compared (not exact-string-only; see that module's docstring).
    aliases: tuple[str, ...]
    required_for_pack: bool


@dataclass(frozen=True)
class KPIDefinition:
    kpi_id: str
    name: str
    description: str
    format: str  # "currency_gbp" | "percentage" | "number" | "count"
    required_fields: tuple[str, ...]  # canonical_field names this KPI needs


@dataclass(frozen=True)
class IndustryPack:
    industry_id: str  # matches app.models.workspace.IndustryType values
    name: str
    column_aliases: tuple[ColumnAlias, ...]
    kpis: tuple[KPIDefinition, ...]
    suggested_questions: tuple[str, ...]
    terminology: dict[str, str]
    report_templates: tuple[str, ...]  # names of templates defined for this pack
    compliance_caveat: str | None = None  # shown wherever this pack's KPIs are displayed


COMMERCIAL_PROPERTY = IndustryPack(
    industry_id="commercial_property",
    name="Commercial Property Intelligence",
    column_aliases=(
        ColumnAlias("tenant", "Tenant / occupier name", ("tenant", "tenant name", "occupier", "lessee"), True),
        ColumnAlias(
            "rent_amount",
            "Rent (any period — treated as-is, not annualised)",
            ("rent", "rent pcm", "rent (pcm)", "monthly rent", "annual rent", "passing rent", "rent amount"),
            True,
        ),
        ColumnAlias(
            "lease_end_date",
            "Lease expiry date",
            ("lease end", "lease end date", "lease expiry", "expiry date", "term end", "lease expiry date"),
            True,
        ),
        ColumnAlias(
            "lease_start_date", "Lease start date", ("lease start", "lease start date", "term start"), False
        ),
        ColumnAlias(
            "status",
            "Occupancy status",
            ("status", "occupancy status", "occupied", "void status"),
            True,
        ),
        ColumnAlias(
            "arrears_amount", "Rent arrears outstanding", ("arrears", "rent arrears", "amount owed", "arrears amount"), False
        ),
        ColumnAlias(
            "category", "Property / use class category", ("category", "use class", "sector", "property type"), False
        ),
        ColumnAlias("unit", "Unit / property identifier", ("unit", "property id", "unit id", "property"), False),
    ),
    kpis=(
        KPIDefinition("total_rent_roll", "Total Rent Roll", "Sum of rent across all units", "currency_gbp", ("rent_amount",)),
        KPIDefinition(
            "average_rent", "Average Rent", "Mean rent per unit", "currency_gbp", ("rent_amount",)
        ),
        KPIDefinition(
            "occupancy_rate",
            "Occupancy Rate",
            "Share of units marked occupied",
            "percentage",
            ("status",),
        ),
        KPIDefinition("vacancy_rate", "Vacancy Rate", "Share of units marked vacant", "percentage", ("status",)),
        KPIDefinition(
            "total_arrears", "Total Arrears", "Sum of outstanding rent arrears", "currency_gbp", ("arrears_amount",)
        ),
        KPIDefinition(
            "arrears_pct_of_rent_roll",
            "Arrears as % of Rent Roll",
            "Total arrears divided by total rent roll",
            "percentage",
            ("arrears_amount", "rent_amount"),
        ),
        KPIDefinition(
            "leases_expiring_12_months",
            "Leases Expiring Within 12 Months",
            "Count of leases with an expiry date within 12 months of the latest date in the data",
            "count",
            ("lease_end_date",),
        ),
        KPIDefinition(
            "tenant_concentration_top5",
            "Top 5 Tenant Concentration",
            "Share of total rent roll from the 5 largest tenants by rent",
            "percentage",
            ("tenant", "rent_amount"),
        ),
    ),
    suggested_questions=(
        "What's our total rent roll and how is it split by category?",
        "Which leases are expiring in the next 12 months?",
        "How concentrated is our income among our top tenants?",
        "What's our current vacancy rate?",
        "Which units have the highest arrears?",
    ),
    terminology={
        "Rent Roll": "The total rental income across a portfolio of units.",
        "Void": "A unit with no tenant in occupation, generating no rent.",
        "Break Clause": "A contractual right for either party to end a lease before its natural expiry.",
        "NOI": "Net Operating Income — rental income minus operating expenses, before debt service.",
    },
    report_templates=("commercial_property_portfolio",),
)

RESIDENTIAL_PROPERTY = IndustryPack(
    industry_id="residential_property",
    name="Residential Property & Lettings Intelligence",
    column_aliases=(
        ColumnAlias("tenant", "Tenant name", ("tenant", "tenant name", "resident"), True),
        ColumnAlias(
            "rent_amount", "Rent (any period)", ("rent", "rent pcm", "monthly rent", "rent amount"), True
        ),
        ColumnAlias(
            "status", "Occupancy status", ("status", "occupancy status", "void status", "occupied"), True
        ),
        ColumnAlias(
            "tenancy_end_date", "Tenancy end date", ("tenancy end", "tenancy end date", "lease end"), False
        ),
        ColumnAlias(
            "arrears_amount", "Rent arrears outstanding", ("arrears", "rent arrears", "arrears amount"), False
        ),
        ColumnAlias(
            "maintenance_cost", "Maintenance spend", ("maintenance cost", "repair cost", "maintenance"), False
        ),
        ColumnAlias("unit", "Property identifier", ("unit", "property id", "address", "property"), False),
    ),
    kpis=(
        KPIDefinition("total_rent_roll", "Total Rent Roll", "Sum of rent across all properties", "currency_gbp", ("rent_amount",)),
        KPIDefinition("average_rent", "Average Rent", "Mean rent per property", "currency_gbp", ("rent_amount",)),
        KPIDefinition("occupancy_rate", "Occupancy Rate", "Share of properties occupied", "percentage", ("status",)),
        KPIDefinition("vacancy_rate", "Vacancy Rate", "Share of properties vacant", "percentage", ("status",)),
        KPIDefinition(
            "total_arrears", "Total Arrears", "Sum of outstanding rent arrears", "currency_gbp", ("arrears_amount",)
        ),
        KPIDefinition(
            "arrears_pct_of_rent_roll",
            "Arrears as % of Rent Roll",
            "Total arrears divided by total rent roll",
            "percentage",
            ("arrears_amount", "rent_amount"),
        ),
        KPIDefinition(
            "total_maintenance_cost",
            "Total Maintenance Cost",
            "Sum of maintenance/repair spend",
            "currency_gbp",
            ("maintenance_cost",),
        ),
    ),
    suggested_questions=(
        "What's our current occupancy rate?",
        "Which properties have the highest arrears?",
        "How much have we spent on maintenance?",
        "Which tenancies are ending soon?",
    ),
    terminology={
        "Void Period": "The time a residential property sits empty between tenancies.",
        "Arrears": "Rent owed by a tenant that is overdue.",
    },
    report_templates=("residential_property_portfolio", "residential_repairs_maintenance"),
)

SOCIAL_HOUSING = IndustryPack(
    industry_id="social_housing",
    name="Social Housing & Asset Management Intelligence",
    column_aliases=(
        ColumnAlias("property_id", "Property / asset identifier", ("property id", "address", "asset id", "property"), True),
        ColumnAlias(
            "stock_type", "Stock type (house, flat, bungalow, ...)", ("stock type", "property type", "dwelling type"), False
        ),
        ColumnAlias("epc_rating", "EPC energy rating", ("epc", "epc rating", "energy rating"), False),
        ColumnAlias(
            "last_inspection_date",
            "Date of the most recent stock condition inspection",
            ("last inspection", "last inspection date", "inspection date"),
            True,
        ),
        ColumnAlias(
            "repair_cost", "Repair spend for this property", ("repair cost", "repairs cost", "maintenance cost"), False
        ),
        ColumnAlias(
            "planned_investment_amount",
            "Planned/budgeted investment for this property",
            ("planned investment", "investment amount", "planned works cost"),
            False,
        ),
        ColumnAlias("void_status", "Whether the property is currently void", ("void status", "status", "occupied"), False),
    ),
    kpis=(
        KPIDefinition("total_properties", "Total Properties", "Count of properties in the dataset", "count", ("property_id",)),
        KPIDefinition(
            "properties_overdue_inspection",
            "Properties Overdue Inspection",
            "Count of properties whose last inspection was more than 12 months before the latest date in "
            "the data — a configurable assumption, not a certified compliance deadline (see caveat)",
            "count",
            ("last_inspection_date",),
        ),
        KPIDefinition(
            "total_repair_cost", "Total Repair Cost", "Sum of repair spend", "currency_gbp", ("repair_cost",)
        ),
        KPIDefinition(
            "total_planned_investment",
            "Total Planned Investment",
            "Sum of planned/budgeted investment",
            "currency_gbp",
            ("planned_investment_amount",),
        ),
        KPIDefinition(
            "average_repair_cost", "Average Repair Cost per Property", "Mean repair spend", "currency_gbp", ("repair_cost",)
        ),
        KPIDefinition("void_rate", "Void Rate", "Share of properties currently void", "percentage", ("void_status",)),
    ),
    suggested_questions=(
        "How many properties are overdue an inspection?",
        "What's our total planned investment this year?",
        "Which properties have the highest repair costs?",
        "What's the distribution of EPC ratings across our stock?",
    ),
    terminology={
        "EPC": "Energy Performance Certificate — a rating of a property's energy efficiency (A-G).",
        "Stock Condition Survey": "A periodic inspection recording a property's physical condition.",
        "Planned Investment": "Budgeted capital works, as distinct from reactive repairs.",
    },
    report_templates=("social_housing_asset", "social_housing_compliance_exceptions"),
    compliance_caveat=(
        "These figures are calculated from the data you uploaded and do NOT constitute legal compliance "
        "certification. 'Overdue inspection' uses a 12-month assumption that may not match your "
        "regulatory or contractual inspection cycle — verify against your actual compliance framework "
        "before acting on this data."
    ),
)

BUSINESS_FINANCE = IndustryPack(
    industry_id="business_finance",
    name="Business & Financial Intelligence",
    column_aliases=(
        ColumnAlias("date", "Transaction or period date", ("date", "transaction date", "period"), True),
        ColumnAlias("revenue", "Revenue / income", ("revenue", "income", "sales"), True),
        ColumnAlias("expenses", "Expenses / costs", ("expenses", "costs", "expenditure", "cost"), False),
        ColumnAlias("category", "Expense or revenue category", ("category", "type", "expense category"), False),
        ColumnAlias("customer", "Customer name", ("customer", "client", "account"), False),
    ),
    kpis=(
        KPIDefinition("total_revenue", "Total Revenue", "Sum of revenue", "currency_gbp", ("revenue",)),
        KPIDefinition("total_expenses", "Total Expenses", "Sum of expenses", "currency_gbp", ("expenses",)),
        KPIDefinition(
            "net_profit", "Net Profit", "Total revenue minus total expenses", "currency_gbp", ("revenue", "expenses")
        ),
        KPIDefinition(
            "profit_margin_pct",
            "Profit Margin",
            "Net profit as a percentage of total revenue",
            "percentage",
            ("revenue", "expenses"),
        ),
        KPIDefinition(
            "average_monthly_revenue",
            "Average Monthly Revenue",
            "Mean revenue per calendar month present in the data",
            "currency_gbp",
            ("date", "revenue"),
        ),
    ),
    suggested_questions=(
        "What's our net profit this period?",
        "How has revenue trended month to month?",
        "Which expense categories are largest?",
        "What's our profit margin?",
    ),
    terminology={
        "Net Profit": "Revenue remaining after all expenses are deducted.",
        "Profit Margin": "Net profit expressed as a percentage of revenue.",
    },
    report_templates=("business_performance",),
)

INDUSTRY_PACKS: dict[str, IndustryPack] = {
    p.industry_id: p
    for p in (COMMERCIAL_PROPERTY, RESIDENTIAL_PROPERTY, SOCIAL_HOUSING, BUSINESS_FINANCE)
}


def get_industry_pack(industry_id: str) -> IndustryPack | None:
    return INDUSTRY_PACKS.get(industry_id)
