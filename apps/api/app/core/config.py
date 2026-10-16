from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "DataLume Intelligence API"
    environment: str = "development"
    debug: bool = True

    # Database. Defaults to a local SQLite file so the API and test suite run
    # with zero external dependencies; set DATABASE_URL to a Postgres DSN
    # (postgresql+asyncpg://...) for staging/production.
    database_url: str = "sqlite+aiosqlite:///./datalume.db"

    # Redis is used for background job queues (see app/services/queue.py).
    redis_url: str = "redis://localhost:6379/0"

    # Object storage (S3-compatible). When s3_access_key is unset, uploads
    # fall back to local disk storage under local_storage_dir — fine for dev
    # and tests, but the storage factory (app/services/storage.py) refuses
    # to start that way when environment == "production".
    s3_endpoint_url: str | None = None
    s3_bucket: str = "datalume-uploads"
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    s3_region: str = "eu-west-2"
    local_storage_dir: str = "./var/uploads"

    # Absolute upload safety ceiling — enforced in addition to, and before,
    # the per-plan cap in app/core/plans.py (see app/services/billing.py).
    # This exists to bound worst-case request/memory size regardless of
    # plan, so it must stay >= the highest plan's max_upload_size_bytes
    # (Enterprise: 1024MB) or that plan's larger uploads would be silently
    # rejected here before the plan check ever runs.
    max_upload_size_bytes: int = 1024 * 1024 * 1024  # 1 GB

    # No real malware scanner is wired in yet (would require a ClamAV
    # daemon or a cloud scanning API). Uploads are still validated by file
    # signature, extension allow-list and a zip-bomb guard for XLSX — see
    # app/services/upload_validation.py — but that is not equivalent to AV
    # scanning. Keep this False until a real scanner is integrated.
    malware_scanning_enabled: bool = False

    # Auth / JWT
    jwt_secret: str = "CHANGE_ME_DEV_ONLY_INSECURE_SECRET"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_minutes: int = 60 * 24 * 14

    # Stripe (Phase 4). Left unset until the user supplies real keys — see
    # app/services/stripe_billing.py, which is written against the real
    # Stripe API but unverified without them (same honest-gating pattern
    # as the LLM client).
    stripe_secret_key: str | None = None
    stripe_webhook_secret: str | None = None

    # Where Stripe Checkout/Billing Portal should redirect back to.
    frontend_base_url: str = "http://localhost:3000"

    # Stripe Price IDs for each paid plan, once created in the Stripe
    # Dashboard's product catalog (test mode). Read by app/core/plans.py
    # via get_settings() — NOT raw os.environ — so they load correctly
    # from a local .env file the same way stripe_secret_key does
    # (pydantic-settings' env_file loading does not export into
    # os.environ, so a plans.py that read os.environ directly would
    # silently miss values set only in .env, not the real shell/process
    # environment).
    stripe_price_id_personal_monthly: str | None = None
    stripe_price_id_personal_annual: str | None = None
    stripe_price_id_professional_monthly: str | None = None
    stripe_price_id_professional_annual: str | None = None
    stripe_price_id_business_monthly: str | None = None
    stripe_price_id_business_annual: str | None = None
    stripe_price_id_team_monthly: str | None = None
    stripe_price_id_team_annual: str | None = None

    # Enterprise SSO (OIDC). Written against authlib — a vetted library
    # that owns the actual cryptography (PKCE, JWKS fetch, ID token
    # signature/claims validation) — but NOT exercised against a real
    # identity provider in this environment. See
    # app/services/sso.py's module docstring before trusting this is
    # "working" in any deployment.
    oidc_client_id: str | None = None
    oidc_client_secret: str | None = None
    oidc_discovery_url: str | None = None  # e.g. https://your-idp/.well-known/openid-configuration
    oidc_redirect_uri: str | None = None  # defaults to {frontend_base_url}/sso/callback if unset

    # LLM provider (Phase 3). Left unset until the user supplies real keys.
    llm_provider: str = "anthropic"
    llm_api_key: str | None = None

    # Transactional email (app/services/email.py). Blocks three otherwise-
    # finished features until set: email verification, password reset, and
    # organization invites to not-yet-registered users. Left unset until
    # real SMTP credentials are supplied — same honest-gating pattern as
    # Stripe/LLM/OIDC above. Works with any standard SMTP provider
    # (Postmark, SendGrid's SMTP endpoint, AWS SES SMTP, your own server).
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from_email: str = "no-reply@datalume.example"
    smtp_use_tls: bool = True

    cors_origins: list[str] = ["http://localhost:3000"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
