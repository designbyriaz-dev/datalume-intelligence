from pydantic import BaseModel, ConfigDict

from app.models.rent_collection import ConnectAccountStatus, RentPaymentRequestStatus


class ConnectAccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workspace_id: str
    stripe_account_id: str
    status: str
    charges_enabled: bool
    payouts_enabled: bool


class ConnectOnboardingLinkOut(BaseModel):
    onboarding_url: str


class PaymentRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    ledger_entry_id: str
    tenancy_id: str
    amount_gbp: float
    status: str
    tenant_email: str
    checkout_url: str
    resulting_ledger_entry_id: str | None


# Re-exported for callers that only need the enums, not the schemas —
# mirrors app/schemas/property.py importing its models' enums directly
# rather than redefining them.
__all__ = [
    "ConnectAccountOut",
    "ConnectOnboardingLinkOut",
    "PaymentRequestOut",
    "ConnectAccountStatus",
    "RentPaymentRequestStatus",
]
