from datetime import datetime

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
    resets_at: datetime = Field(
        description="When the analyses count resets to 0 — the real Stripe billing-cycle boundary for a "
        "paid subscription, or the first of next calendar month (UTC) for a free one."
    )


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
    past_due_since: object | None = Field(
        description="Set while status is 'past_due' — when the current grace period started. "
        "None otherwise."
    )
    downgrade_scheduled_for: object | None = Field(
        description="past_due_since + the dunning grace period (app/services/dunning.py) — when "
        "this subscription will be downgraded to Free if payment isn't resolved first. None "
        "unless status is 'past_due'. Computed server-side so the frontend doesn't need to know "
        "the grace period's length."
    )
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
