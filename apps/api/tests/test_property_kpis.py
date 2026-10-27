from datetime import date

from app.models.property import LedgerEntryType, RentFrequency, RentLedgerEntry, Tenancy, TenancyStatus
from app.services.property_kpis import compute_portfolio_kpis, compute_tenancy_balance


def _entry(entry_type: str, amount: float, entry_date: date = date(2026, 1, 1)) -> RentLedgerEntry:
    return RentLedgerEntry(entry_type=entry_type, amount_gbp=amount, entry_date=entry_date)


def test_balance_is_zero_with_no_entries() -> None:
    assert compute_tenancy_balance([]) == 0


def test_charge_then_full_payment_zeroes_balance() -> None:
    entries = [_entry(LedgerEntryType.CHARGE.value, 1000), _entry(LedgerEntryType.PAYMENT.value, 1000)]
    assert compute_tenancy_balance(entries) == 0


def test_partial_payment_leaves_arrears() -> None:
    entries = [_entry(LedgerEntryType.CHARGE.value, 1000), _entry(LedgerEntryType.PAYMENT.value, 600)]
    assert compute_tenancy_balance(entries) == 400


def test_overpayment_leaves_credit_balance() -> None:
    entries = [_entry(LedgerEntryType.CHARGE.value, 1000), _entry(LedgerEntryType.PAYMENT.value, 1200)]
    assert compute_tenancy_balance(entries) == -200


def test_refund_reverses_a_payment() -> None:
    entries = [
        _entry(LedgerEntryType.CHARGE.value, 1000),
        _entry(LedgerEntryType.PAYMENT.value, 1200),
        _entry(LedgerEntryType.REFUND.value, 200),
    ]
    assert compute_tenancy_balance(entries) == 0


def test_adjustment_reduces_balance() -> None:
    entries = [_entry(LedgerEntryType.CHARGE.value, 1000), _entry(LedgerEntryType.ADJUSTMENT.value, 50)]
    assert compute_tenancy_balance(entries) == 950


def _tenancy(rent: float, frequency: str, status: str, tenancy_id: str) -> Tenancy:
    t = Tenancy(
        id=tenancy_id,
        property_id="prop-1",
        tenant_name="Tenant",
        rent_amount_gbp=rent,
        rent_frequency=frequency,
        start_date=date(2026, 1, 1),
        status=status,
    )
    return t


def test_portfolio_kpis_cover_multiple_tenancies() -> None:
    active_monthly = _tenancy(1000, RentFrequency.MONTHLY.value, TenancyStatus.ACTIVE.value, "t1")
    active_weekly = _tenancy(200, RentFrequency.WEEKLY.value, TenancyStatus.ACTIVE.value, "t2")
    ended = _tenancy(500, RentFrequency.MONTHLY.value, TenancyStatus.ENDED.value, "t3")

    entries_by_tenancy = {
        "t1": [
            _entry(LedgerEntryType.CHARGE.value, 1000, date(2026, 1, 1)),
            _entry(LedgerEntryType.PAYMENT.value, 1000, date(2026, 1, 5)),
        ],
        "t2": [
            _entry(LedgerEntryType.CHARGE.value, 200, date(2026, 1, 1)),
        ],
        "t3": [],
    }

    kpis = compute_portfolio_kpis(
        property_count=2,
        tenancies=[active_monthly, active_weekly, ended],
        entries_by_tenancy=entries_by_tenancy,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
    )

    assert kpis.total_properties == 2
    assert kpis.active_tenancies == 2
    assert kpis.expected_monthly_rent_gbp == round(1000 + 200 * 52 / 12, 2)
    assert kpis.collected_this_period_gbp == 1000
    assert kpis.outstanding_balance_gbp == 200
    assert kpis.arrears_count == 1


def test_collections_outside_period_are_excluded() -> None:
    entries_by_tenancy = {
        "t1": [
            _entry(LedgerEntryType.CHARGE.value, 1000, date(2025, 12, 1)),
            _entry(LedgerEntryType.PAYMENT.value, 1000, date(2025, 12, 5)),
        ],
    }
    tenancy = _tenancy(1000, RentFrequency.MONTHLY.value, TenancyStatus.ACTIVE.value, "t1")

    kpis = compute_portfolio_kpis(
        property_count=1,
        tenancies=[tenancy],
        entries_by_tenancy=entries_by_tenancy,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 1, 31),
    )

    assert kpis.collected_this_period_gbp == 0
    assert kpis.outstanding_balance_gbp == 0
