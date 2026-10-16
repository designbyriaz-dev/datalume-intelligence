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

## Not yet implemented (do not claim otherwise)

- Email verification delivery (accounts are created unverified and stay
  that way — there's no email provider wired up).
- MFA.
- Password reset flow.
- Rate limiting / brute-force protection on login.
- TLS termination (this is the application's responsibility to require at
  the infrastructure layer, e.g. a load balancer or reverse proxy — not
  something the application itself provides).
- Encryption at rest for the database or object storage (inherit this
  from the managed Postgres / S3-compatible provider you deploy to —
  don't assume it for granted).
- Malware/structural scanning of uploads (no upload pipeline exists yet).
- Audit logging of data access.
- Any compliance certification (ISO 27001, SOC 2, etc.) — none has been
  obtained, and nothing in this codebase should imply otherwise.

## UK GDPR

No personal data beyond account email/name is collected or processed yet.
Before building the dataset upload pipeline (Phase 2) and AI analyst
(Phase 3), the following need explicit decisions and documentation before
go-live, not after:

- A lawful basis and retention policy for uploaded customer datasets.
- Whether/how uploaded data is sent to a third-party LLM provider, and
  what that provider's data retention/training policy is — this must be
  disclosed to customers, and the brief's instruction to not use customer
  data to train general-purpose models by default must be enforced in the
  LLM integration code itself (e.g. provider-level opt-out flags), not
  just stated in a policy document.
- A data processing agreement with any sub-processor (LLM provider, cloud
  host, email provider) before real customer data touches them.
