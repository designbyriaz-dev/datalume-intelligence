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
- Large file uploads are processed via a FastAPI `BackgroundTasks`
  callback (see docs/CHECKLIST.md's "Post-Phase-7: async upload
  processing" section), so the HTTP response returns immediately — but
  the parsing/profiling work still runs afterward in the same API
  process, not a separate worker. A large upload no longer holds open
  the client's own request, but it still occupies that API worker's
  event loop for the whole processing time, which can delay other
  requests that worker is handling concurrently. A real job queue
  (Celery/RQ against the already-provisioned Redis) would be the next
  step if this becomes a bottleneck under real concurrent load.
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

## Railway deployment (first real deployment — a runbook, not a claim it's been done)

The account holder chose Railway for the first real deployment, deliberately
scoped as a **private** environment first (a real URL to test and share, not
a public launch) — Stripe live mode, legal review, and Google OAuth
verification are all still open, see docs/CHECKLIST.md. This section is the
exact runbook, written so it can actually be followed, not generic advice.

**What an AI agent cannot do here, by design**: create the Railway account,
enter billing details, or type real secret values (API keys, passwords,
tokens) into Railway's dashboard. Those steps below are explicitly the
account holder's own actions. Two code changes *were* made and committed to
make this deployment actually work once those manual steps are done:

- `apps/web/Dockerfile` now accepts `NEXT_PUBLIC_API_URL` as a Docker build
  `ARG` — Next.js inlines `NEXT_PUBLIC_*` variables into the client bundle
  at *build* time, not read at container runtime, so a plain Railway runtime
  variable would have silently had no effect, leaving the deployed frontend
  still calling `localhost:8000`. This was caught by reading how Next.js
  actually handles these variables, not assumed.
- `apps/api/railway.json` and `apps/web/railway.json` set each service's
  real start command. The API's matters most: `uvicorn` doesn't read
  Railway's injected `$PORT` automatically the way `next start` does, so it
  has to be passed explicitly, and migrations have to run before the server
  starts accepting traffic — mirroring `infra/docker-compose.yml`'s
  `api` service command exactly: `python -m alembic upgrade head && uvicorn
  app.main:app --host 0.0.0.0 --port $PORT`.

### 1. Create the project and the two services

1. Create a Railway account and a new project (account holder's own step).
2. Add a service from the GitHub repo, **Root Directory** = `apps/api`.
   Railway will detect `apps/api/railway.json` and `apps/api/Dockerfile`
   automatically.
3. Add a second service from the same repo, **Root Directory** =
   `apps/web`.
4. Add a **Postgres** database to the project (Railway's own managed
   Postgres plugin, one click — this is the "managed Postgres" DEPLOYMENT.md
   already calls for above).

### 2. Database URL — the one real gotcha

Railway's Postgres plugin gives you `DATABASE_URL` in `postgresql://...`
form. This app uses **async** SQLAlchemy and needs the `+asyncpg` dialect
in the scheme, or it will fail to connect. On the API service, set:

```
DATABASE_URL=postgresql+asyncpg://${{Postgres.PGUSER}}:${{Postgres.PGPASSWORD}}@${{Postgres.PGHOST}}:${{Postgres.PGPORT}}/${{Postgres.PGDATABASE}}
```

(Railway's variable-reference syntax — adjust the reference names to
whatever your Postgres service is actually named in the project.) Do not
just reference `${{Postgres.DATABASE_URL}}` directly — its scheme is
`postgresql://`, not `postgresql+asyncpg://`.

### 3. Environment variables — API service

Reuse the real values already in `apps/api/.env` where noted; generate new
ones where noted. Never paste real secret values into a chat with an AI
agent — this list says *which* key to set and *where its value comes
from*, not the value itself.

| Variable | Value |
|---|---|
| `ENVIRONMENT` | `production` |
| `DATABASE_URL` | built per step 2 above |
| `JWT_SECRET` | a **new**, real secret — generate with `python3 -c "import secrets; print(secrets.token_urlsafe(64))"` and use that, not the local dev value (there isn't one set locally — the app silently runs on an insecure placeholder otherwise, see this file's "A real `JWT_SECRET`" note above) |
| `S3_ENDPOINT_URL`, `S3_BUCKET`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_REGION` | the real Cloudflare R2 values already in `apps/api/.env` — reusable as-is |
| `LLM_PROVIDER`, `LLM_API_KEY` | the real Anthropic values already in `apps/api/.env` |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL`, `SMTP_USE_TLS` | the real Gmail SMTP values already in `apps/api/.env` |
| `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_ID_*` | **use the test-mode values**, not the live ones currently active in local `.env` — the real live Stripe account's business verification (KYC) is still incomplete (most payment methods disabled), and this is a private deployment, not a public launch. The test-mode values are the commented-out lines at the top of `apps/api/.env`. Switch to the real live values only once KYC is done and you're ready for Stripe webhooks to point at this deployment for real. |
| `STRIPE_TAX_ENABLED` | `false` |
| `FRONTEND_BASE_URL` | the web service's Railway URL once it's deployed (step 5) |
| `CORS_ORIGINS` | `["https://<web service's Railway domain>"]` — a JSON array, pydantic-settings parses list env vars this way |
| `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, `OIDC_DISCOVERY_URL` | decide which IdP you want live here — local `.env` currently has the Microsoft Entra ID test app's values, not Google's; either works, but whichever you choose needs its redirect URI updated (step 6) |
| `OIDC_REDIRECT_URI` | `https://<web service's Railway domain>/sso/callback` |
| `MALWARE_SCANNING_ENABLED` | leave `false` unless a clamd daemon is also deployed — not provisioned on Railway here |

### 4. Environment variables — web service

| Variable | Value |
|---|---|
| `NEXT_PUBLIC_API_URL` | the API service's Railway domain, e.g. `https://<api-service>.up.railway.app` — set this as a **Build Variable**, not just a runtime variable, per the Dockerfile change above. Deploy the API service first so you have its real URL before building web. |

### 5. Deploy order

Deploy the API service first (it needs no dependency on web). Once it's up,
copy its public Railway domain into the web service's `NEXT_PUBLIC_API_URL`
build variable and `FRONTEND_BASE_URL`/`CORS_ORIGINS` on the API service
once web's own domain is known, then deploy web. A second redeploy of
whichever service's dependency changed is normal here — this is a
circular-ish dependency (API needs web's URL for CORS, web needs API's URL
to build), not a mistake.

### 6. Update third-party redirect/webhook URLs (manual, provider dashboards)

- **OIDC provider** (Google Cloud Console or Entra ID app registration,
  whichever you chose in step 3): add
  `https://<web domain>/sso/callback` to the app's authorized redirect
  URIs. The existing registration's redirect URI is `localhost:3000` —
  real SSO login will fail here until this is added.
- **Stripe webhook** (Stripe Dashboard → Developers → Webhooks, in test
  mode since step 3 uses test keys): add an endpoint at
  `https://<api domain>/api/v1/billing/webhook`, and copy its signing
  secret into `STRIPE_WEBHOOK_SECRET` on the API service (replacing the
  local dev one).

### 7. After deploying

- Visit `https://<api domain>/api/v1/health` — should return
  `{"status": "ok"}`. If it doesn't, check the API service's deploy logs
  in Railway for an `alembic upgrade head` failure before assuming the app
  itself is broken.
- Register a real account through the deployed web app and confirm a
  verification email actually arrives (real SMTP, real inbox — don't trust
  "send succeeded" logs alone, the Gmail quirk noted above is real).
- This is a **private** deployment per the account holder's own choice —
  don't link it from the real `datalume.co.uk` DNS or announce it
  publicly until Stripe live mode, legal review, and Google OAuth
  verification are actually resolved (see docs/CHECKLIST.md's "Immediate
  next steps" list for the current state of each).
