# Deployment

This covers what's actually true about deploying DataLume Intelligence
today — not a claim that any particular cloud setup has been tried. The
application is fully environment-variable driven (see
[.env.example](../.env.example)), which is what makes "dedicated
environments" (the brief's phrase) possible at all: a staging, production,
or single-customer-dedicated deployment is the same codebase pointed at a
different `.env` — no code branches or config files to maintain per
environment.

## What's containerized today

`infra/docker-compose.yml` runs Postgres, Redis, MinIO (S3-compatible
object storage), the API, and the web app together — see the root
[README.md](../README.md) for the one-command quickstart. Both
`apps/api/Dockerfile` and `apps/web/Dockerfile` build real, working
images (verified by running them, not just written).

This compose file is a **local development / single-host** setup, not a
production deployment manifest — there's no Kubernetes/ECS/Nomad
definition, no managed-database Terraform, no TLS termination,
and no multi-instance scaling configuration. Building those is a real
infrastructure project of its own, specific to whichever cloud/platform
is chosen — fabricating generic Kubernetes YAML that's never been
deployed anywhere wouldn't be more useful than this document explaining
what matters once you do.

## What a real deployment needs, beyond what's here

1. **A managed Postgres database.** `DATABASE_URL` points at it; run
   `alembic upgrade head` against it before first boot (the Docker
   Compose `api` service does this automatically on every start — mirror
   that in whatever process manager/entrypoint the real deployment uses).
2. **Real object storage** (S3, R2, or another S3-compatible service).
   Set `S3_ACCESS_KEY`/`S3_SECRET_KEY`/`S3_ENDPOINT_URL`/`S3_BUCKET` —
   see docs/CHECKLIST.md: this path is tested against both moto's
   mocked S3 API (which caught and fixed a real region-handling bug in
   bucket auto-creation) and a real local MinIO server
   (`tests/test_s3_storage_minio.py`, which also confirmed MinIO is
   genuinely more lenient than AWS about that same region rule, not
   just assumed to be). Still verify against your actual production
   provider (AWS S3, R2, etc.) before trusting it there — only MinIO
   has been exercised for real so far, and AWS is the strict one moto
   emulates, not MinIO.
3. **A real `JWT_SECRET`.** The default is an insecure placeholder — the
   app will run with it, which is exactly the problem; generate one
   (`python -c "import secrets; print(secrets.token_urlsafe(64))"`) and
   treat it as a real secret (rotating it invalidates every issued
   token).
4. **TLS termination**, at a load balancer or reverse proxy in front of
   the API — this application does not terminate TLS itself.
5. **Real Stripe and LLM provider keys.** Both are now verified against
   real accounts — Stripe against a real **sandbox** (Checkout, webhooks,
   the Billing Portal) and the LLM against a real Anthropic model — see
   docs/CHECKLIST.md for the full account. What's still open: Stripe has
   only ever run in test-mode sandbox, never **live mode** (a real
   production account, real cards) — budget time to re-verify Checkout
   and webhook delivery there specifically before taking real payments,
   since a sandbox and a live account are genuinely separate accounts
   with their own keys (see "Post-Phase-7: Stripe sandbox verification"
   in docs/ARCHITECTURE.md for why that distinction matters here).
6. **A decision about the in-process scheduler.** `app/main.py`'s
   APScheduler job (scheduled reports) runs inside the API process. That
   is fine for exactly one running API instance. Running more than one
   replica means every replica's scheduler fires every due report
   independently — once per replica, not once total. Before scaling the
   API horizontally, either pin the scheduler to a single designated
   instance (e.g. a `SCHEDULER_ENABLED` env var set true on only one
   replica) or move it to a separate worker process with a distributed
   lock. Neither is built yet.
7. **Transactional email.** Now verified against a real Gmail account and
   a real inbox (see docs/CHECKLIST.md's "Email service" entry) — email
   verification, password reset, and org-invites-by-email for
   not-yet-registered users all work against any standard SMTP provider.
   A real Gmail-specific quirk is worth knowing before switching
   providers: an `SMTP_FROM_EMAIL` that isn't the authenticated account
   (and isn't a verified Gmail "Send As" alias) gets silently replaced
   with the authenticated account by Gmail's relay rather than rejected
   — check the actual delivered `From` header after switching providers,
   not just that the send succeeded.
8. **A log/error aggregation service** (Sentry or similar) if you want
   the admin dashboard's "system errors" row to mean anything — it's
   explicitly not implemented today (see
   `app/services/admin_stats.py`'s docstring for exactly what is and
   isn't computed from real data there).

## SSO (OIDC) deployment note

The Phase 7 SSO integration is now verified against a real identity
provider — a real Google Cloud OAuth client, a real consent screen, a
real login through to a real `User` row — see docs/CHECKLIST.md's
"SSO via OIDC" section and `app/services/sso.py`'s module docstring for
the full account, including two real bugs that verification caught
(a missing session cookie on the callback route, and a test suite that
had started silently depending on real credentials once they existed in
local `.env`). Still open before calling this production-ready: only
Google has been tried — Okta and Azure AD haven't, and either can have
its own quirks (non-standard claim names, token endpoint auth method
differences); and the Google OAuth app itself is still in "Testing"
publishing status with a single whitelisted test user, not
verified/published for public sign-in — submitting it for Google's
verification review (required once real users beyond the test-user
allow-list need to sign in) is a separate, unstarted step.

## Scaling notes (honest, not aspirational)

- The API itself is stateless (all state is in Postgres/object storage),
  so horizontal scaling of the API process is architecturally fine —
  **except** for the in-process scheduler caveat above.
- Background/async processing for large file uploads doesn't exist yet
  (uploads are handled synchronously in the request) — see
  docs/CHECKLIST.md's Phase 2 notes. This matters more for scaling than
  the API's own statelessness: a large upload ties up a worker for the
  whole processing time.
- The 7 auth endpoints (`/register`, `/login`, `/verify-email`,
  `/reset-password`, `/resend-verification`, `/forgot-password`, plus
  `/refresh` which is deliberately exempt — it already requires a valid
  refresh token) are rate-limited per client IP (see "Post-Phase-7: auth
  endpoint rate limiting" in docs/CHECKLIST.md), verified live against a
  real running server. Every other endpoint — uploads, dataset
  processing, the AI analyst, report generation, dashboard/workspace
  CRUD — still has no rate limiting of its own; put one at the load
  balancer/API gateway layer before exposing those publicly at any real
  scale.
