from pydantic import BaseModel, ConfigDict, Field


class PlanOut(BaseModel):
    plan_id: str
    name: str
    monthly_price_gbp: float | None
    max_analyses_per_month: int | None
    max_upload_size_bytes: int
    max_saved_datasets: int | None
    max_team_members: int | None
    self_serve: bool = Field(description="Whether this plan can be purchased via Checkout, vs contact-sales")


class UsageOut(BaseModel):
    period_key: str
    analyses_used: int
    analyses_limit: int | None


class SubscriptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    owner_user_id: str | None
    organization_id: str | None
    plan_id: str
    status: str
    billing_period: str | None
    current_period_end: object | None
    cancel_at_period_end: bool
    usage: UsageOut


class CheckoutSessionRequest(BaseModel):
    plan_id: str
    billing_period: str = Field(default="monthly", pattern="^(monthly|annual)$")
    organization_id: str | None = None


class CheckoutSessionResponse(BaseModel):
    checkout_url: str


class PortalSessionRequest(BaseModel):
    organization_id: str | None = None


class PortalSessionResponse(BaseModel):
    portal_url: str
