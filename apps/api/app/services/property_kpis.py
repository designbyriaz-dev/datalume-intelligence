"""Rent ledger balance and portfolio-level property KPIs — Phase 1 of the
property-management brief (see app/models/property.py's module docstring).

Deliberately small, pure functions over already-fetched rows (the same
shape app/services/industry_kpis.py's _CALCULATORS registry uses), not one
large function — makes the ledger-balance math independently unit-testable
without a database, the exact reasoning industry_kpis.py's own docstring
gives for the same pattern there.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models.property import LedgerEntryType, RentFrequency, RentLedgerEntry, TenancyStatus

# A tenancy's balance is "what the tenant owes" — positive means arrears,
# negative means a credit in the tenant's favour. Each entry type's effect
# on that balance, fixed and documented here (not left to be guessed from
# the sign of amount_gbp, which schemas/property.py requires to always be
# positive):
#   CHARGE      +amount  rent falling due increases what's owed
#   PAYMENT     -amount  money received reduces what's owed
#   REFUND      +amount  money returned to the tenant undoes a prior
#                        payment, so it moves the balance back the way a
#                        charge does (a refund of an overpayment returns
#                        the tenant's credit balance back towards zero)
#   ADJUSTMENT  -amount  the common manual case (a waived fee, a goodwill
#                        credit) reduces what's owed; an adjustment that
#                        should *increase* the balance (e.g. a late fee) is
#                        recorded as a CHARGE instead, with a description
#                        explaining why, rather than overloading
#                        ADJUSTMENT's sign per-entry
_BALANCE_SIGN: dict[str, int] = {
    LedgerEntryType.CHARGE.value: 1,
    LedgerEntryType.PAYMENT.value: -1,
    LedgerEntryType.REFUND.value: 1,
    LedgerEntryType.ADJUSTMENT.value: -1,
}


def compute_tenancy_balance(entries: list[RentLedgerEntry]) -> float:
    """Positive = arrears (tenant owes rent). Negative = credit balance."""
    return round(sum(_BALANCE_SIGN[e.entry_type] * float(e.amount_gbp) for e in entries), 2)


_FREQUENCY_TO_MONTHLY: dict[str, float] = {
    RentFrequency.WEEKLY.value: 52 / 12,
    RentFrequency.MONTHLY.value: 1,
    RentFrequency.QUARTERLY.value: 1 / 3,
}


def _monthly_equivalent(rent_amount_gbp: float, frequency: str) -> float:
    return float(rent_amount_gbp) * _FREQUENCY_TO_MONTHLY[frequency]


@dataclass
class PropertyKPIs:
    total_properties: int
    active_tenancies: int
    expected_monthly_rent_gbp: float
    collected_this_period_gbp: float
    outstanding_balance_gbp: float
    arrears_count: int


def compute_portfolio_kpis(
    *,
    property_count: int,
    tenancies: list,
    entries_by_tenancy: dict[str, list[RentLedgerEntry]],
    period_start,
    period_end,
) -> PropertyKPIs:
    """tenancies: every Tenancy row in the workspace (any status).
    entries_by_tenancy: every tenancy's ledger entries, keyed by tenancy
    id — a KPI covering "this period's collections" still needs every
    historical entry to compute each tenancy's running balance correctly
    (the balance isn't period-scoped, only the "collected this period"
    figure is), so this takes the full entry set rather than a
    pre-filtered one and does its own period filtering internally."""
    active = [t for t in tenancies if t.status == TenancyStatus.ACTIVE.value]
    expected_monthly = round(
        sum(_monthly_equivalent(t.rent_amount_gbp, t.rent_frequency) for t in active), 2
    )

    collected_this_period = 0.0
    outstanding_total = 0.0
    arrears_count = 0
    for tenancy in tenancies:
        entries = entries_by_tenancy.get(tenancy.id, [])
        balance = compute_tenancy_balance(entries)
        outstanding_total += balance
        if balance > 0:
            arrears_count += 1
        collected_this_period += sum(
            float(e.amount_gbp)
            for e in entries
            if e.entry_type == LedgerEntryType.PAYMENT.value and period_start <= e.entry_date <= period_end
        )

    return PropertyKPIs(
        total_properties=property_count,
        active_tenancies=len(active),
        expected_monthly_rent_gbp=expected_monthly,
        collected_this_period_gbp=round(collected_this_period, 2),
        outstanding_balance_gbp=round(outstanding_total, 2),
        arrears_count=arrears_count,
    )
