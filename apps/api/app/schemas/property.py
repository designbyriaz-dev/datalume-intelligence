from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from app.models.property import LedgerEntryType, RentFrequency, TenancyStatus


class PropertyCreate(BaseModel):
    address_line1: str = Field(min_length=1, max_length=255)
    address_line2: str | None = None
    city: str = Field(min_length=1, max_length=255)
    postcode: str = Field(min_length=1, max_length=20)
    country: str = Field(default="United Kingdom", max_length=100)
    property_type: str | None = Field(default=None, max_length=100)


class PropertyUpdate(BaseModel):
    address_line1: str = Field(min_length=1, max_length=255)
    address_line2: str | None = None
    city: str = Field(min_length=1, max_length=255)
    postcode: str = Field(min_length=1, max_length=20)
    country: str = Field(max_length=100)
    property_type: str | None = Field(default=None, max_length=100)


class PropertyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    address_line1: str
    address_line2: str | None
    city: str
    postcode: str
    country: str
    property_type: str | None
    created_by_user_id: str | None


class TenancyCreate(BaseModel):
    tenant_name: str = Field(min_length=1, max_length=255)
    tenant_email: str | None = None
    rent_amount_gbp: float = Field(gt=0)
    rent_frequency: RentFrequency = RentFrequency.MONTHLY
    start_date: date
    end_date: date | None = None
    status: TenancyStatus = TenancyStatus.ACTIVE


class TenancyUpdate(BaseModel):
    # Only status/end_date are editable directly — a rent *amount* change
    # is itself an adjustment ledger entry (POST .../ledger-entries), not
    # a silent field edit, to keep the ledger the single source of truth
    # for anything financial. See app/models/property.py's module docstring.
    status: TenancyStatus
    end_date: date | None = None


class TenancyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    property_id: str
    tenant_name: str
    tenant_email: str | None
    rent_amount_gbp: float
    rent_frequency: str
    start_date: date
    end_date: date | None
    status: str
    created_by_user_id: str | None


class RentLedgerEntryCreate(BaseModel):
    entry_type: LedgerEntryType
    amount_gbp: float = Field(gt=0)
    entry_date: date
    description: str | None = Field(default=None, max_length=2000)


class RentLedgerEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    tenancy_id: str
    entry_type: str
    amount_gbp: float
    entry_date: date
    description: str | None
    created_by_user_id: str | None


class TenancyBalanceOut(BaseModel):
    tenancy_id: str
    balance_gbp: float = Field(
        description="Positive means the tenant owes rent (in arrears); negative means a credit balance."
    )


class PropertyKPIsOut(BaseModel):
    total_properties: int
    active_tenancies: int
    expected_monthly_rent_gbp: float
    collected_this_period_gbp: float
    outstanding_balance_gbp: float
    arrears_count: int
