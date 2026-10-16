"""The configurable entitlement system — a single registry of plan
limits, so "limits can change without rewriting application code" (per
the brief). This is read by app/services/billing.py to enforce quotas
server-side; nothing about these limits is enforced client-side only.

Prices and limits below are taken directly from the product brief, with
two explicit assumptions flagged where the brief didn't give a number —
search for "ASSUMPTION" if you need to revisit those.

Stripe price IDs are intentionally blank: they only exist once a real
Stripe account's product catalog has been created (Stripe Dashboard ->
Products). Set them via env vars once that's done — see .env.example.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import get_settings


@dataclass(frozen=True)
class PlanLimits:
    plan_id: str
    name: str
    monthly_price_gbp: float | None  # None = custom/contact sales
    max_analyses_per_month: int | None  # None = unlimited
    max_upload_size_bytes: int
    max_saved_datasets: int | None  # None = unlimited
    max_team_members: int | None  # None = not applicable (personal plan)
    stripe_price_id_monthly: str | None
    stripe_price_id_annual: str | None


def _settings_price_id(plan_id: str, period: str) -> str | None:
    settings = get_settings()
    return getattr(settings, f"stripe_price_id_{plan_id}_{period}", None)


_MB = 1024 * 1024

PLANS: dict[str, PlanLimits] = {
    "free": PlanLimits(
        plan_id="free",
        name="Free",
        monthly_price_gbp=0,
        max_analyses_per_month=3,
        max_upload_size_bytes=5 * _MB,
        max_saved_datasets=2,
        max_team_members=None,
        stripe_price_id_monthly=None,  # Free plan never goes through Stripe
        stripe_price_id_annual=None,
    ),
    "personal": PlanLimits(
        plan_id="personal",
        name="Personal",
        monthly_price_gbp=12,
        max_analyses_per_month=25,
        max_upload_size_bytes=25 * _MB,
        max_saved_datasets=10,
        max_team_members=None,
        stripe_price_id_monthly=_settings_price_id("personal", "monthly"),
        stripe_price_id_annual=_settings_price_id("personal", "annual"),
    ),
    "professional": PlanLimits(
        plan_id="professional",
        name="Professional",
        monthly_price_gbp=29,
        max_analyses_per_month=100,
        max_upload_size_bytes=100 * _MB,
        max_saved_datasets=50,
        max_team_members=None,
        stripe_price_id_monthly=_settings_price_id("professional", "monthly"),
        stripe_price_id_annual=_settings_price_id("professional", "annual"),
    ),
    "business": PlanLimits(
        plan_id="business",
        name="Business",
        monthly_price_gbp=79,
        max_analyses_per_month=400,
        max_upload_size_bytes=250 * _MB,
        # ASSUMPTION: the brief doesn't give a saved-dataset cap for
        # Business — left unlimited (shared workspaces are the stated
        # feature, not a dataset count ceiling).
        max_saved_datasets=None,
        max_team_members=5,
        stripe_price_id_monthly=_settings_price_id("business", "monthly"),
        stripe_price_id_annual=_settings_price_id("business", "annual"),
    ),
    "team": PlanLimits(
        plan_id="team",
        name="Team",
        monthly_price_gbp=199,
        # ASSUMPTION: the brief says "pooled analysis allowance" for Team
        # but gives no number. 1000/month is a placeholder pool size,
        # not a brief-specified figure — revisit with real usage data.
        max_analyses_per_month=1000,
        max_upload_size_bytes=500 * _MB,
        max_saved_datasets=None,
        max_team_members=15,
        stripe_price_id_monthly=_settings_price_id("team", "monthly"),
        stripe_price_id_annual=_settings_price_id("team", "annual"),
    ),
    "enterprise": PlanLimits(
        plan_id="enterprise",
        name="Enterprise",
        monthly_price_gbp=None,  # custom pricing — contact sales, not self-serve Checkout
        max_analyses_per_month=None,
        max_upload_size_bytes=1024 * _MB,
        max_saved_datasets=None,
        max_team_members=None,
        stripe_price_id_monthly=None,
        stripe_price_id_annual=None,
    ),
}

DEFAULT_PLAN_ID = "free"


def get_plan(plan_id: str) -> PlanLimits:
    plan = PLANS.get(plan_id)
    if plan is None:
        raise ValueError(f"Unknown plan_id: {plan_id}")
    return plan
