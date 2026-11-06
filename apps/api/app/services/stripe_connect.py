"""Stripe Connect integration for Rent Collection v1 — pay-by-link only
(see docs/CHECKLIST.md's "Rent Collection v1" section for the full
plan: no recurring billing, no tenant portal, no refunds-through-Connect
in this phase). Gated behind settings.rent_collection_enabled (default
False) — same honest-gating pattern as app/services/malware_scanning.py
and app/services/stripe_billing.py.

IMPORTANT — same caveat as stripe_billing.py: written correctly against
the documented Stripe Connect API (Account, AccountLink, Checkout
Session with stripe_account=), but NOT exercised against a real Stripe
Connect platform application in this environment — Connect additionally
requires the platform's own Connect application to be registered and
(per the property-management brief) approved before any of this can be
verified live, which is a real business step no amount of code can
substitute for. Do not report any of this as "working" until the
account holder has run a real onboarding and a real test-mode Checkout
payment against their own approved platform application.

Not a subclass of StripeBillingClient: that client sets stripe.api_key
once per instance and assumes a single (platform) account for every
call. Connect calls are inherently cross-account — nearly every one
here takes an explicit stripe_account= connected-account id — so there
is no single "the" account to default to the way billing's
single-platform-account assumption allows.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import get_settings


class RentCollectionNotConfiguredError(Exception):
    """Raised when a Connect-backed rent-collection action is invoked
    while settings.rent_collection_enabled is False, or STRIPE_SECRET_KEY
    is unset. Routers should turn this into a 503 — same convention as
    BillingNotConfiguredError / LLMNotConfiguredError / EmailNotConfiguredError."""


@dataclass
class ConnectAccountLinkResult:
    account_id: str
    onboarding_url: str


@dataclass
class ConnectCheckoutSessionResult:
    checkout_session_id: str
    checkout_url: str


class StripeConnectClient:
    def __init__(self, secret_key: str) -> None:
        import stripe

        self._stripe = stripe
        self._stripe.api_key = secret_key

    def create_connected_account(self, *, workspace_id: str) -> str:
        """Express account — Stripe hosts the KYC/bank-details form; a
        "Custom" account would need this app to build that UI itself,
        out of scope for v1. metadata.workspace_id lets an
        account.updated webhook be traced back to the owning workspace
        without a second lookup (see app/services/
        rent_collection_webhook_handlers.py, though in practice the
        webhook handler looks up by stripe_account_id directly since
        that's what's already stored on WorkspaceStripeAccount)."""
        account = self._stripe.Account.create(
            type="express",
            capabilities={"transfers": {"requested": True}, "card_payments": {"requested": True}},
            metadata={"workspace_id": workspace_id},
        )
        return account.id

    def create_onboarding_link(
        self, *, stripe_account_id: str, refresh_url: str, return_url: str
    ) -> ConnectAccountLinkResult:
        link = self._stripe.AccountLink.create(
            account=stripe_account_id,
            refresh_url=refresh_url,
            return_url=return_url,
            type="account_onboarding",
        )
        return ConnectAccountLinkResult(account_id=stripe_account_id, onboarding_url=link.url)

    def get_account_status(self, *, stripe_account_id: str) -> tuple[bool, bool]:
        """Returns (charges_enabled, payouts_enabled). Mainly for an
        on-demand "refresh status" action — the account.updated webhook
        already carries these fields directly in its payload, so this
        isn't required on that path."""
        account = self._stripe.Account.retrieve(stripe_account_id)
        return bool(account.charges_enabled), bool(account.payouts_enabled)

    def create_checkout_session_for_charge(
        self,
        *,
        stripe_account_id: str,
        amount_gbp: float,
        description: str,
        tenant_email: str,
        success_url: str,
        cancel_url: str,
        metadata: dict[str, str],
    ) -> ConnectCheckoutSessionResult:
        """One-off payment (mode="payment", not "subscription" — Rent
        Collection v1 is pay-by-link per charge, not recurring billing;
        see stripe_billing.py's create_checkout_session for the
        subscription-mode sibling this deliberately does not reuse).
        amount_gbp is converted to pence: Stripe's unit_amount is always
        the smallest currency unit, unlike this app's own Numeric(10,2)
        GBP convention everywhere else (see app/models/property.py)."""
        session = self._stripe.checkout.Session.create(
            mode="payment",
            line_items=[
                {
                    "price_data": {
                        "currency": "gbp",
                        "unit_amount": round(amount_gbp * 100),
                        "product_data": {"name": description},
                    },
                    "quantity": 1,
                }
            ],
            customer_email=tenant_email,
            success_url=success_url,
            cancel_url=cancel_url,
            metadata=metadata,
            stripe_account=stripe_account_id,
        )
        return ConnectCheckoutSessionResult(checkout_session_id=session.id, checkout_url=session.url)

    def construct_webhook_event(self, payload: bytes, signature_header: str, webhook_secret: str):
        return self._stripe.Webhook.construct_event(payload, signature_header, webhook_secret)


def get_stripe_connect_client() -> StripeConnectClient:
    # rent_collection_enabled is checked BEFORE stripe_secret_key, so a
    # deployment with real Stripe billing keys but the flag off gets the
    # "disabled by the brief's own instruction" message, not a
    # misleading "not configured" one.
    settings = get_settings()
    if not settings.rent_collection_enabled:
        raise RentCollectionNotConfiguredError(
            "Rent Collection is disabled (RENT_COLLECTION_ENABLED=false). Enable it only after your "
            "Stripe Connect platform application has been approved for the intended setup."
        )
    if not settings.stripe_secret_key:
        raise RentCollectionNotConfiguredError(
            "No STRIPE_SECRET_KEY configured. Rent Collection uses the same Stripe secret key as "
            "billing — see app/services/stripe_billing.py."
        )
    return StripeConnectClient(settings.stripe_secret_key)
