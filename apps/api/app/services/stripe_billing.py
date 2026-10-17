"""Stripe integration for subscription billing.

IMPORTANT — same caveat as app/services/ai/llm_client.py: this module is
written correctly against the documented Stripe API, but has NOT been
exercised against a real Stripe account in this environment — there is
no STRIPE_SECRET_KEY configured. Checkout Session creation and Billing
Portal session creation cannot be tested without one (there's no local
fake for a real payment flow). Webhook *handling* (the business logic of
reacting to an event) is a separate story — see
app/services/webhook_handlers.py, which IS tested, by constructing
correctly-HMAC-signed test payloads the same way Stripe signs them for
real, without needing a live account.

Do not report Checkout/Portal as "working" until someone has run it
against a real Stripe test-mode account and completed a real checkout.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import get_settings


class BillingNotConfiguredError(Exception):
    """Raised when Stripe-backed billing is invoked but no
    STRIPE_SECRET_KEY is set. Routers should turn this into a 503."""


@dataclass
class CheckoutSessionResult:
    checkout_url: str
    stripe_session_id: str


@dataclass
class PortalSessionResult:
    portal_url: str


class StripeBillingClient:
    """Thin wrapper around the stripe-python SDK. Assumes a single Stripe
    account for the whole deployment (sets the module-level stripe.api_key
    once per call) — fine for one DataLume instance; would need the
    newer per-request StripeClient object if this ever served multiple
    Stripe accounts from one process."""

    def __init__(self, secret_key: str, *, tax_enabled: bool = False):
        import stripe

        self._stripe = stripe
        self._stripe.api_key = secret_key
        self._tax_enabled = tax_enabled

    def create_checkout_session(
        self,
        *,
        price_id: str,
        customer_email: str,
        client_reference_id: str,
        success_url: str,
        cancel_url: str,
        existing_stripe_customer_id: str | None = None,
    ) -> CheckoutSessionResult:
        kwargs = {
            "mode": "subscription",
            "line_items": [{"price": price_id, "quantity": 1}],
            "success_url": success_url,
            "cancel_url": cancel_url,
            "client_reference_id": client_reference_id,
        }
        if self._tax_enabled:
            # Stripe Tax: automatically calculates and applies the
            # correct VAT/sales tax for the customer's location on this
            # subscription and every future renewal invoice — this is
            # the app's whole VAT story (see docs/CHECKLIST.md's
            # "Post-Phase-7: dunning flow and VAT via Stripe Tax"
            # section), not a per-request choice. Gated behind
            # settings.stripe_tax_enabled (see app/core/config.py for
            # why: it requires a one-time Stripe Dashboard step first).
            # billing_address_collection="required" is what lets Stripe
            # determine the correct tax jurisdiction in the first place;
            # tax_id_collection lets a B2B customer supply their own
            # VAT/tax ID, which is how Stripe Tax applies EU
            # reverse-charge automatically rather than this app having
            # to implement that logic itself.
            kwargs["automatic_tax"] = {"enabled": True}
            kwargs["billing_address_collection"] = "required"
            kwargs["tax_id_collection"] = {"enabled": True}
        if existing_stripe_customer_id:
            kwargs["customer"] = existing_stripe_customer_id
        else:
            kwargs["customer_email"] = customer_email

        session = self._stripe.checkout.Session.create(**kwargs)
        return CheckoutSessionResult(checkout_url=session.url, stripe_session_id=session.id)

    def create_billing_portal_session(self, *, stripe_customer_id: str, return_url: str) -> PortalSessionResult:
        session = self._stripe.billing_portal.Session.create(
            customer=stripe_customer_id, return_url=return_url
        )
        return PortalSessionResult(portal_url=session.url)

    def cancel_subscription(self, *, stripe_subscription_id: str) -> None:
        """Cancels immediately (not at period end) — used by the dunning
        flow (app/services/dunning.py) once the grace period has already
        expired, so there's no remaining period to honor. Letting Stripe
        keep retrying/billing after this app has already downgraded the
        account locally would mean Stripe and this app disagree about
        whether the customer is still subscribed."""
        self._stripe.Subscription.cancel(stripe_subscription_id)

    def construct_webhook_event(self, payload: bytes, signature_header: str, webhook_secret: str):
        return self._stripe.Webhook.construct_event(payload, signature_header, webhook_secret)


def get_stripe_client() -> StripeBillingClient:
    settings = get_settings()
    if not settings.stripe_secret_key:
        raise BillingNotConfiguredError(
            "No STRIPE_SECRET_KEY configured. Billing is scaffolded (plans, quota enforcement, "
            "webhook handling) but not connected to a real Stripe account — see docs/CHECKLIST.md."
        )
    return StripeBillingClient(settings.stripe_secret_key, tax_enabled=settings.stripe_tax_enabled)
