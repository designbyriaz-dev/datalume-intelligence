# Security & data handling notes

This documents what is actually true about the current codebase — not an
aspirational policy. Update it as the implementation changes.

## Implemented

- Passwords are hashed with bcrypt (via passlib); plaintext passwords are
  never stored or logged.
- JWT access tokens expire after 30 minutes; refresh tokens after 14 days.
  `JWT_SECRET` has an insecure placeholder default — **you must set a real
  secret via the `JWT_SECRET` environment variable before deploying
  anywhere beyond a laptop.**
- Tenant isolation is enforced server-side: every workspace read/write
  checks that the requesting user owns the workspace personally, or holds
  an active `Membership` row in the owning organization
  (`app/services/authz.py`). This is covered by automated tests
  (`tests/test_tenant_isolation.py`), including the "outsider denied"
  journey from the original brief.
- Organization-management actions (inviting members) require an
  `owner`/`administrator` role server-side, not just a hidden UI control.
- CORS is restricted to an explicit allow-list (`CORS_ORIGINS`), not `*`.
- Email verification delivery and a password reset flow, both via real
  SMTP (`app/services/email.py`) — see docs/CHECKLIST.md's "Post-Phase-7:
  transactional email" section.
- MFA (TOTP-based, `pyotp`) — see docs/CHECKLIST.md's "Post-Phase-7: MFA
  (TOTP two-factor authentication)" section.
- Rate limiting on every auth endpoint (`/register`, `/login`,
  `/verify-email`, `/reset-password`, `/resend-verification`,
  `/forgot-password`), keyed per client IP — see docs/CHECKLIST.md's
  "Post-Phase-7: auth endpoint rate limiting" section. Keyed on
  `request.client.host` directly: this app isn't deployed behind a
  reverse proxy in this environment, so there's no trusted
  `X-Forwarded-For` to prefer yet — revisit when it is.
- Upload structural validation (`app/services/upload_validation.py`):
  file-extension allow-list, magic-byte signature verification, a
  size cap, and a zip-bomb guard for `.xlsx`.
- Real malware/AV scanning of uploads, via a ClamAV daemon (`clamd`) —
  see `app/services/malware_scanning.py` and docs/CHECKLIST.md's
  "Post-Phase-7: real malware/AV scanning" section. **Off by default**
  (`MALWARE_SCANNING_ENABLED=false`) — set it to `true` and point
  `CLAMD_HOST`/`CLAMD_PORT` at a real running clamd daemon to turn
  real scanning on; until then, uploads still get the structural
  validation above, just not an actual virus scan.
- Audit logging (`app/models/audit_log.py`, `app/services/audit.py`) of
  auth events (login success/failure, registration, MFA enabled/
  disabled, email verification, password reset), billing/subscription-
  plan changes, API key creation/revocation, organization membership
  actions, and platform-admin access to a user's data — not a general
  trail of every ordinary read of customer data by its own owner (see
  the next section). Exportable per-organization (manager-only) and
  viewable as a personal history by any user for their own account.

## Not yet implemented (do not claim otherwise)

- TLS termination (this is the application's responsibility to require at
  the infrastructure layer, e.g. a load balancer or reverse proxy — not
  something the application itself provides).
- Encryption at rest for the database or object storage (inherit this
  from the managed Postgres / S3-compatible provider you deploy to —
  don't assume it for granted).
- A general audit trail of every ordinary data *read* (who viewed which
  dataset, when, as its own owner) — what exists today (see above)
  covers auth/billing/membership/API-key events and platform-admin
  access specifically, not routine self-access to one's own data.
- Any compliance certification (ISO 27001, SOC 2, etc.) — none has been
  obtained, and nothing in this codebase should imply otherwise.

## UK GDPR

Uploaded datasets and AI analyst conversations may contain customer data
beyond account email/name — both the dataset upload pipeline and the AI
analyst are built and in use. The following still need explicit
decisions and documentation before go-live, not after:

- A lawful basis and retention policy for uploaded customer datasets.
- Whether/how uploaded data is sent to a third-party LLM provider, and
  what that provider's data retention/training policy is — this must be
  disclosed to customers, and the brief's instruction to not use customer
  data to train general-purpose models by default must be enforced in the
  LLM integration code itself (e.g. provider-level opt-out flags), not
  just stated in a policy document.
- A data processing agreement with any sub-processor (LLM provider, cloud
  host, email provider) before real customer data touches them.
