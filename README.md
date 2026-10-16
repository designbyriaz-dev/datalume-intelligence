# DataLume Intelligence

[![CI](https://github.com/designbyriaz-dev/datalume-intelligence/actions/workflows/ci.yml/badge.svg)](https://github.com/designbyriaz-dev/datalume-intelligence/actions/workflows/ci.yml)

Turn Your Data Into Decisions.

This repository is being built incrementally against the phased plan in the
original product brief. See [docs/CHECKLIST.md](docs/CHECKLIST.md) for what
is actually implemented and tested today versus what is still backlog —
treat that file as the source of truth over any marketing copy on the
website itself.

## Repository layout

```
apps/
  api/   FastAPI backend (Python 3.12, SQLAlchemy async, Alembic, pytest)
  web/   Next.js frontend (TypeScript, Tailwind CSS, App Router)
infra/
  docker-compose.yml   Postgres + Redis + MinIO + api + web, for local dev
docs/
  ARCHITECTURE.md
  CHECKLIST.md
  SECURITY.md
```

## Quickstart (local development, no Docker)

Requires Python 3.12 and Node 20+.

```bash
# Backend
cd apps/api
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp ../../.env.example ../../.env   # optional — defaults work out of the box
python -m alembic upgrade head     # creates ./datalume.db (SQLite, dev only)
uvicorn app.main:app --reload --port 8000
```

```bash
# Frontend, in a second terminal
cd apps/web
npm install
npm run dev
```

Visit http://localhost:3000. The API is at http://localhost:8000, with
interactive OpenAPI docs at http://localhost:8000/docs.

### Running the backend test suite

```bash
cd apps/api
source .venv/bin/activate
python -m pytest -q
```

282/282 tests currently pass, covering registration, login, token
refresh, workspace creation, tenant isolation, the Phase 2 dataset
pipeline (upload validation, CSV/XLSX profiling, schema confirmation,
deduplicate + versioning), Phase 3 (the analytics engine, PDF reports,
and the AI planner's orchestration loop — now also verified against a
real Anthropic model, not just a scripted fake LLM client, see the
Post-Phase-7 bullet below), Phase 4 (quota enforcement across all plan
limits, and Stripe webhook handling — now also verified end-to-end
against a real Stripe **sandbox** account, not just self-signed test
payloads, see the Post-Phase-7 bullet below), Phase 5 (26 industry KPIs across
4 sectors, each independently verified against hand-computed values,
plus the Commercial Property Portfolio PDF report), Phase 6 (version
comparison, scenario modeling, the dashboard builder, and a scheduled-
report scheduler tested by calling its real job function directly),
Phase 7 (API keys, audit logging, admin stats, outbound webhooks, and an
SSO/OIDC flow tested end-to-end against a self-built fake identity
provider — now also verified end-to-end against a real Google OAuth
client, including a frontend callback page that didn't exist before
this round, see the Post-Phase-7 bullet below), a post-Phase-7 transactional email
integration (email verification, password reset, and organization
invites to not-yet-registered users — now verified against a real
Gmail account and a real inbox, not just a local throwaway listener,
see the Post-Phase-7 bullet below), ten more cleaning
operations in total (fill missing values, normalize text, filter rows,
calculated fields, standardize dates/currency, merge columns, split
column, pivot, unpivot, group-by — every cleaning operation the brief
named) built on a shared transformation helper extracted from Phase 2's
original deduplicate, `S3Storage` verification against moto's
mocked S3 backend (real AWS API semantics, not a hand-rolled stub —
this caught and fixed a real region-handling bug, but still isn't the
same as a real bucket), a conversation-history replay fidelity fix
for the AI analyst (multi-turn conversations now replay prior turns'
real tool_use/tool_result blocks to the model, not flattened text), a
a second, third, and fourth specialist report template — Residential
Property Portfolio, Social Housing Asset Report (the first PDF report
to render the brief-required compliance caveat), and Business
Performance Report, completing report coverage for every industry pack
— all four sharing every KPI calculation with the `/industry-kpis`
endpoint, industry field mapping confirmation (a user can now review
and correct the automatic column-matching before trusting the
KPIs/reports it drives, the last honesty gap Phase 5 itself had
flagged), and pivot/unpivot/group-by (completing every cleaning
operation the brief named) — see docs/CHECKLIST.md for exactly what is
and isn't verified in the unconnected pieces.

## Quickstart (Docker)

```bash
cp .env.example .env
docker compose -f infra/docker-compose.yml up --build
```

This runs Postgres, Redis, MinIO, the API (migrated automatically on
startup) and the web app together.

## Configuration

All configuration is environment-variable driven — see
[.env.example](.env.example) for the full list. Nothing in that file is a
real credential. Four integrations are fully built but require you to
supply real keys/provider details before they're connected to anything real:

- **Stripe** (`STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, plus
  `STRIPE_PRICE_ID_*` once you've created a product catalog) — for
  subscription billing (Checkout, Billing Portal).
- **LLM provider** (`LLM_API_KEY`) — for the AI data analyst.
- **OIDC identity provider** (`OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`,
  `OIDC_DISCOVERY_URL`) — for enterprise SSO.
- **SMTP** (`SMTP_HOST`, + `SMTP_USERNAME`/`SMTP_PASSWORD` if your
  provider needs auth) — for email verification, password reset, and
  organization invites to not-yet-registered users. Any standard
  provider works (Postmark, SendGrid, SES, Gmail, your own server).

All four correctly return `503 Service Unavailable` with a clear
message when unset, rather than a fake success (registration itself
still succeeds without SMTP configured — it just stays unverified, as
it always has). See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for what
else a real deployment needs beyond local development.

## Current status

Phases 1-7 are implemented and tested — Phase 7 is the brief's final
phase:

- **Phase 1 — Foundation**: authentication, personal and organisation
  workspaces, role-based membership, tenant isolation.
- **Phase 2 — Data Intelligence Engine**: secure CSV/XLSX upload (content
  validated, not just extension/trust), multi-sheet profiling, schema
  inference, a documented data-quality score, versioned dataset storage,
  and eleven working cleaning operations — deduplicate, fill missing
  values, normalize text, filter rows, calculated fields, standardize
  dates/currency, merge columns, split column, pivot, unpivot, group-by
  (the last ten added post-Phase-7) — every operation the brief named,
  each producing a new version with a full audit trail and leaving the
  source version untouched.
- **Phase 3 — AI and Reporting**: a deterministic analytics engine
  (descriptive stats, correlation, outliers, group/time aggregation, a
  linear-trend forecast baseline) usable directly via the API; PDF data
  quality reports; and an AI query-planner harness (grounding prompt,
  tool-calling loop, conversation persistence) that's fully built,
  tested, and — as of post-Phase-7 — verified against a real Anthropic
  model: real questions, real tool calls, real correct answers checked
  by hand (see the Post-Phase-7 bullet below). Without an `LLM_API_KEY`
  configured, it still correctly returns `503` rather than faking an
  answer, which remains the behavior for anyone running this without
  one set.
- **Phase 4 — Commercial SaaS**: all 6 plans from the brief in a
  configurable entitlement registry, with quota limits enforced
  server-side (upload size, saved-dataset count, monthly analyses — not
  just shown in the UI); every account auto-provisioned onto the Free
  plan; Stripe Checkout/Portal/webhook integration code that's fully
  built, with webhook *handling* genuinely tested via self-signed test
  payloads, but **Checkout/Portal themselves not connected to a real
  Stripe account** — no `STRIPE_SECRET_KEY` in this environment, so
  those correctly return `503` too.
- **Phase 5 — Specialist Intelligence**: four industry packs (commercial
  property, residential property, social housing, business finance)
  with real column-alias matching (handles messy real-world headers like
  "Rent (PCM)"), 26 deterministic KPIs total, and one full specialist
  PDF report (Commercial Property Portfolio). Social housing KPIs always
  carry the brief's required compliance disclaimer. This phase proved
  the report-template pattern with one, end-to-end — three more
  (Residential Property Portfolio, Social Housing Asset Report,
  Business Performance Report) were added post-Phase-7, completing
  report coverage for every pack, and a fifth and sixth (Social Housing
  Compliance Exceptions, Residential Repairs & Maintenance) each added a
  second report to their pack; 6 more templates from the brief's
  original list of 12 still aren't built.
- **Phase 6 — Advanced Analytics**: dataset version comparison (row/
  column deltas between two uploads); scenario ("what if rent rises
  10%?") modeling that reuses the Phase 5 KPI engine for both baseline
  and scenario, so the two numbers can't disagree; a persisted dashboard
  builder with live-computed widgets and "Generate Dashboard
  Automatically"; scheduled PDF reports driven by a real in-process
  APScheduler job, safe to run behind more than one API replica since a
  post-Phase-7 distributed lock (a lease row in the database, not a
  Postgres-only primitive) ensures only one replica's tick processes due
  reports at a time, now also emailing the generated PDF to the
  schedule's creator whenever SMTP is configured (both added
  post-Phase-7); and dashboard comments as the
  collaboration piece, specifically verified that a read-only org Viewer
  can comment despite being blocked from uploading or changing data.
- **Phase 7 — Enterprise**: API keys (`dlk_`-prefixed, SHA-256 hashed,
  authenticate against every existing endpoint with no per-route
  changes); an allowlisted audit log wired to real decisions
  (registration, login, org/membership changes, billing plan changes)
  with a JSON/CSV export; an admin dashboard computing real platform
  stats from aggregate SQL only, gated behind an `is_platform_admin` flag
  with no API path that can set it; outbound webhooks signed with
  Stripe's own HMAC scheme; and SSO via OIDC, tested end-to-end against
  a self-built fake identity provider (real generated RSA keys, real
  signed tokens, authlib's actual JWKS-fetch and signature/claims
  validation code) and since also verified against a real Google OAuth
  client — see the dedicated Post-Phase-7 bullet further down.
  SCIM provisioning, custom roles beyond the fixed five, and a
  production deployment manifest are explicitly scoped out — see
  docs/CHECKLIST.md and docs/DEPLOYMENT.md.
- **Post-Phase-7 — Transactional email**: the single integration most
  repeatedly flagged as a blocker (Phases 1, 4, and 6) is now built:
  email verification, password reset, and organization invites to
  not-yet-registered users, all behind one `EmailSender` abstraction,
  plus the frontend pages for all four flows (forgot-password,
  reset-password, verify-email, accept-invite), plus scheduled report
  email delivery (see its own bullet below). Registration still
  succeeds without `SMTP_HOST` set (same as always); the email-dependent
  endpoints correctly return `503` instead. Since verified against a
  real Gmail account and a real inbox too, not just a mocked or local
  throwaway listener — see the dedicated Post-Phase-7 bullet further
  down.
- **Post-Phase-7 — Seven more cleaning operations**: fill missing
  values, normalize text, filter rows, calculated fields, standardize
  dates/currency, merge columns, and split column, each producing a
  new dataset version with a full audit trail (same guarantee as
  deduplicate) via a shared transformation helper extracted from
  deduplicate itself. Standardize-column fixes the two issues
  profiling.py only ever flagged, never corrected
  (`date_stored_as_text`/`numeric_stored_as_text`) — turning a text
  column into a genuine `date` or `float` dtype, not just a
  reformatted string. A "Clean this data" panel on the workspace page
  exposes all eight operations. Verified live in the browser across two
  rounds: dropped null-age rows, added a calculated column, standardized
  a text date column into a real date type (quality score rose to
  100/100), and split a "full name" column into explicitly-named
  `first_name`/`last_name` columns — all producing correct new versions
  matching the automated tests exactly.
- **Post-Phase-7 — S3Storage verified against a mocked S3 API**:
  `tests/test_s3_storage.py` runs the real boto3-backed storage class
  against [moto](https://github.com/getmoto/moto), which emulates AWS
  S3's actual API semantics rather than stubbing this app's own code.
  Caught a real bug: bucket auto-creation didn't pass
  `CreateBucketConfiguration`, which real AWS S3 requires for any region
  other than `us-east-1` — including this app's own default region —
  so first-run bucket creation against a real AWS bucket would have
  failed outright. Fixed, and confirmed the fix matters by reverting it
  and watching 6 of 7 tests fail with the real AWS error. Still not run
  against MinIO or a real bucket — see docs/CHECKLIST.md.
- **Post-Phase-7 — Conversation history replay fidelity**: the AI
  analyst's multi-turn conversations now replay earlier turns to the
  model with their original tool_use/tool_result block structure
  intact, instead of flattening them to plain text (a Phase 3-documented
  simplification). A turn now always closes on an assistant-role
  message — required because Anthropic's API rejects two consecutive
  same-role messages, a bug only a cross-turn test could catch. Verified
  with a scripted fake client (no real model involved, same as the rest
  of the AI planner): a second turn demonstrably receives the first
  turn's actual tool call and result, not a text summary of it — proven
  both in-memory and through the real `/ask` endpoint with real database
  persistence.
- **Post-Phase-7 — Residential Property Portfolio Report**: the second
  specialist report template, proving the KPI-engine-plus-PDF-layout
  pattern a second time. Built from the exact same KPI calculations the
  `/industry-kpis` endpoint already uses — zero new calculation code,
  only a new PDF layout and router endpoint. Verified by extracting and
  reading the actual rendered PDF text (not just checking the file is
  non-empty) and checking every figure against hand-computed values,
  and live in the browser: the existing "Download portfolio report"
  button, previously hardcoded to commercial property, now correctly
  branches by workspace industry.
- **Post-Phase-7 — Industry field mapping confirmation**: a user can
  now review and correct the automatic column-matching
  (`GET`/`PATCH /dataset-tables/{id}/field-mapping`) before trusting the
  KPIs/reports it drives — the last honesty gap Phase 5 itself had
  flagged. Every call site that computes industry KPIs now goes through
  one shared `get_effective_field_mapping()` function, so confirming a
  mapping once applies consistently everywhere (KPIs, scenarios, both
  specialist reports, scheduled reports, dashboard widgets), and it
  survives a later cleaning operation rather than resetting. Proven
  end-to-end, not just a round-trip check: a CSV with a rent column
  named "Amount Due Monthly" (deliberately unrecognizable to the
  automatic matcher) leaves `total_rent_roll` erroring until the mapping
  is confirmed — verified both by an automated test and live in the
  browser, where confirming the mapping turned "Not available" into a
  real £2,150.00 figure.
- **Post-Phase-7 — Pivot and unpivot**: two of the brief's
  originally-named cleaning operations. Pivot (long-to-wide) is the one
  cleaning operation that replaces the table's column set entirely
  rather than extending or filtering it — inherent to what "pivot"
  means. A required `aggregate_function` (default `sum`) handles
  duplicate index+pivot-value combinations gracefully rather than
  erroring, and a 50-distinct-value cap guards against an unreasonable
  column explosion. Verified as a real round-trip in the browser: a
  long-format dataset pivoted to wide (correctly summing a duplicate
  combination), then that *result* unpivoted back to long — each step
  producing a new version with the data quality profile correctly
  recomputed for the new shape.
- **Post-Phase-7 — Persisted group-by**: the last cleaning operation
  named in the brief, completing the entire list. Unlike the read-only
  `group_aggregate` analytics tool it complements, supports multiple
  aggregations in one call (e.g. a sum and a row count, by category, in
  a single request). Verified live in the browser: grouped a 5-row
  dataset by category with `sum(amount)`, producing the correct 2-row
  result matching the source data summed by hand.
- **Post-Phase-7 — Social Housing Asset Report**: the third specialist
  report template, and the first to render the brief-required
  compliance caveat in PDF form (previously shown only in the API
  response and dashboard UI) — prominently, in a highlighted box before
  the data it qualifies, not buried in a footnote. Built from the same
  KPI engine as `/industry-kpis`, so it can't disagree with it; adds an
  "overdue inspection" section (properties whose last inspection is
  more than 12 months old) and an EPC rating distribution. Verified by
  reading the actual rendered PDF text and checking every figure by
  hand, and live in the browser through the real generate-and-download
  flow.
- **Post-Phase-7 — Business Performance Report**: the fourth specialist
  report template, completing report coverage for every industry pack
  the brief named. The first report with a month-by-month trend section
  (reusing `time_trend` from the Phase 3 analytics engine) and a "top N"
  ranked section (top 5 customers by revenue, reusing
  `group_aggregate`'s existing sort). Four reports in, and still zero
  report-specific calculation code — every number in every report comes
  from a function that already existed before any report needed it.
  Verified the same way as the other three: real rendered PDF text
  checked by hand, and a live browser pass confirming the real
  generate-and-download calls.
- **Post-Phase-7 — Social Housing Compliance Exceptions Report**: the
  fifth specialist report template, and the first to be a *second*
  report on a pack rather than a first — every pack already had one by
  this point, so this attached to social_housing (whose existing fields
  already fit a compliance audit) rather than inventing a new industry
  pack. Deliberately not a copy of the existing Asset Report: that one
  is a portfolio overview, this one is a row-level exceptions list
  (overdue inspections, missing inspection dates, poor EPC ratings, void
  properties with no planned investment) — the first of the five reports
  with no KPI table, since an exceptions audit's job is the exception
  list itself. Reuses the KPI engine's own overdue-inspection cutoff and
  void-status markers rather than redefining either. The frontend's
  per-industry report button, previously one generator per industry,
  became a list per industry to support a pack with more than one
  report. Verified twice: a purpose-built dataset hitting all four
  exception categories (plus two control cases) through a temporary PDF
  text extractor, and a full real-browser pass — real account, real
  workspace, real upload, real button click — with the downloaded PDF's
  exception lists hand-checked against the source CSV.
- **Post-Phase-7 — Residential Repairs & Maintenance Report**: the
  sixth specialist report template, and the second pack to get a second
  report. Checked all three remaining packs' fields first rather than
  picking one arbitrarily: `commercial_property` has no capex/valuation
  field an Investment Planning report could use without inventing data,
  and `business_finance`'s one report already covers most of what a
  second report there could say; `residential_property`'s
  `maintenance_cost` field, by contrast, already fed one aggregate KPI
  but had never been shown per property anywhere. Adds a per-property
  maintenance-spend ranking and a list of properties with no recorded
  spend — worded as informational, not an exception, since (unlike the
  compliance-exceptions report) nothing in this pack's fields can tell
  "nothing needed fixing" apart from "nothing was logged." Slotted
  straight into the report-button list and scheduling-options structures
  the fifth report already generalized — no frontend rework needed, the
  actual proof that generalization was correctly timed. Verified the
  same way as the fifth report: a crafted dataset through a temporary
  PDF text extractor, then a full real-browser pass with every figure in
  the downloaded PDF hand-checked against the source CSV.
- **Post-Phase-7 — Scheduled report email delivery**: closes a gap
  flagged since Phase 6 — scheduled reports generated a PDF but never
  emailed it anywhere. Now, whenever `SMTP_HOST` is configured, a
  successful scheduled run emails the schedule's creator with the PDF
  attached directly (this app has no public download link to send
  instead); a send failure is recorded (`last_email_error`) without
  undoing the already-generated report. All specialist reports are
  schedulable (six now, four at the time this was built — the fifth and
  sixth, Social Housing Compliance Exceptions and Residential Repairs &
  Maintenance, each slotted into the same `REPORT_TYPE_REQUIRED_INDUSTRY`
  wiring with no changes needed here). Verified beyond mocked `smtplib`: ran
  the real API, a real scheduled report, and a small hand-rolled local
  SMTP listener (Python removed the stdlib `smtpd` module in 3.12), and
  confirmed a real multipart email with a genuine `%PDF-1.4` attachment
  arrived over a real socket.
- **Post-Phase-7 — Scheduled reports frontend**: the one dependent piece
  not addressed in the round above — scheduled report creation, listing,
  deletion, and delivery status now have a UI (a panel per dataset
  table, next to the field-mapping review), not just an API. Report-type
  choices are gated by workspace industry, matching what the backend
  accepts. Verified live in the browser against the real API: created a
  weekly Commercial Property Portfolio schedule, confirmed the real
  `POST`/`GET` calls, removed it, and confirmed the real `DELETE` plus
  an independent API check that it was actually gone.
- **Post-Phase-7 — Distributed scheduler lock**: closes Phase 6's
  "single-instance only" limitation — running more than one API replica
  no longer makes every replica's scheduler fire the same due report.
  A lease-lock row in the database (one conditional `UPDATE`, atomic
  under both SQLite and Postgres, no Postgres-only primitive required)
  ensures only one replica processes due reports per tick; a crashed
  holder's lease self-expires rather than locking every other replica
  out forever. Verified beyond sequential unit tests: a live script
  raced two genuinely independent database connections — standing in
  for two separate API processes — against the same due report with
  `asyncio.gather`, and exactly one of them generated it.
- **Post-Phase-7 — Auth endpoint rate limiting**: closes a known gap
  flagged since the first version of this checklist — `/login` had no
  defense against password-guessing, and `/register`,
  `/forgot-password`, and `/resend-verification` had none against spam
  or email-bombing. A database-backed fixed-window limiter (reusing the
  same atomic-update pattern proven for the scheduler lock above, not
  Redis — this app's `redis_url` setting was never actually connected
  to anything) now gates all six of those endpoints per client IP, with
  limits sized against this project's own test suite so nothing broke.
  Verified against a real running server: 10 rapid real login requests
  succeeded, the 11th and 12th got a real `429`, and a separate
  endpoint's limit was confirmed unaffected.
- **Post-Phase-7 — httpOnly cookie refresh + CSRF protection**: closes
  the last item in "Known limitations" — the frontend stored the JWT in
  `localStorage`, readable by any script that managed to run on the
  page. Now only the refresh token moves to an httpOnly cookie the
  frontend never reads; the access token stays in memory only, sent via
  the same `Authorization` header as before, so every other endpoint
  (70+) needed zero changes. CSRF protection applies to exactly the one
  endpoint that authenticates purely via that cookie
  (`/auth/refresh`'s browser path); every existing `test_auth.py` test
  still passes unmodified. A live browser check after the code was
  written caught a real leftover: the old pre-migration token still
  sitting in `localStorage`, inert but still there — fixed with a
  one-time cleanup on login-state load, confirmed empty afterward.
  Verified end-to-end in a real browser: session survives a fresh page
  load via the cookie alone (no `localStorage` involved), and logging
  out genuinely clears both cookies and ends the session rather than
  leaving it silently valid.
- **Post-Phase-7 — Billing audit-log gaps closed**: two gaps, found and
  fixed together while reading the webhook handler file end to end.
  First, a gap flagged since Phase 7 itself — only organization
  subscriptions had their plan changes recorded in the audit log; a
  personal account's didn't, because of a single conditional skipping
  the call entirely for them (the schema and `GET /users/me/audit-log`
  were already correct). Second, a previously-undocumented one found
  while fixing the first — subscription *cancellation* wasn't
  audit-logged at all, for either personal or organization accounts.
  Both verified through the real `GET /users/me/audit-log` endpoint,
  not just a database check; the cancellation fix's test specifically
  cancels from a paid plan (not from free) so a before/after
  capture-order bug in the "what plan was this before cancellation"
  metadata couldn't hide behind free-to-free being indistinguishable
  either way.
- **Post-Phase-7 — Stripe billing verified against a real sandbox
  account**: the first of this project's credential-gated integrations
  to move from "written and tested against mocks" to "actually run
  against a real account." A real test-mode product catalog (4 plans ×
  monthly/annual) was created in the Stripe Dashboard; a real Checkout
  session was created through the real API and completed in a real
  browser with Stripe's published `4242 4242 4242 4242` test card; the
  Stripe CLI forwarded real signed webhook events
  (`customer.subscription.updated`, `invoice.paid`, and others) to a
  real running server; and `GET /billing/subscription` confirmed the
  actual entitlement unlock — `plan_id: "personal"`, the real 25
  analyses/month limit, not just a database row checked in isolation.
  The Billing Portal was verified separately, returning a real
  `billing.stripe.com` session URL. Still unverified: Stripe **live
  mode** (a real production account, real cards) — this was a sandbox,
  the same honest distinction kept for every other "verified"
  integration in this project.
- **Post-Phase-7 — AI analyst verified against a real model**: the
  second credential-gated integration to cross that same line. A real
  user uploaded a real dataset and asked two real questions through
  `POST /dataset-tables/{id}/ask`. Turn 1 correctly called
  `descriptive_stats` and answered £4,500 total rent, matching a
  hand-computed sum. Turn 2, in the same conversation ("What percentage
  of that total does Acme Ltd account for?"), correctly used turn 1's
  replayed context — no re-running `descriptive_stats`, just
  `group_aggregate` — and answered 55.6%/44.4%, both correct. That
  second question also doubles as the first real-model proof of the
  conversation-history-replay-fidelity fix below, previously only
  checked against a scripted fake client.
- **Post-Phase-7 — Transactional email verified against a real
  mailbox**: the third credential-gated integration verified end-to-end
  — real Gmail SMTP credentials, a real account registration through
  the real API, a real verification email confirmed landing in a real
  inbox by actually reading it, not just a clean HTTP response or a
  local throwaway listener. A real Gmail quirk surfaced along the way:
  an unverified custom `From` address was silently replaced with the
  authenticated account by Gmail's relay rather than rejected outright
  — caught only because the actual delivered email was checked, not
  just the SMTP call's success.
- **Post-Phase-7 — SSO verified against a real identity provider**: the
  fourth and last credential-gated integration — a real Google OAuth
  client, a real consent screen, a real login driven all the way through
  to a real `User` row in the database. This one also meant actually
  finishing the feature, not just confirming it: the frontend had no
  `/sso/callback` page at all (Google's redirect 404'd), so this added
  that page plus a "Continue with Google" button on `/login`. Verifying
  it for real also caught two bugs confirmation alone wouldn't have: the
  callback route built valid tokens but never set the httpOnly session
  cookie `/auth/login` sets (an SSO session would've looked logged in,
  then silently logged out on the next page reload — caught only by
  actually reloading the page), and a test suite that had quietly started
  depending on the real Stripe/LLM/SMTP/OIDC credentials this round added
  to `apps/api/.env` (140 of 268 tests failed before this was found and
  fixed). All four credential-gated integrations identified at the start
  of this round are now verified against real accounts.
- **Post-Phase-7 — Dashboard drag-and-drop reorder, add, and remove
  widgets**: closes the gap flagged since Phase 6 — the dashboard
  builder was configurable and persisted but not visually rearrangeable.
  Scoped to exactly what was documented as missing (drag-to-reorder,
  persisted) rather than resizing or a freeform 2D grid, neither of
  which was ever promised. `DashboardWidget.position` already existed
  from Phase 6, so this needed no migration — just a new
  `PATCH .../widgets/reorder` endpoint that validates the submitted
  order is exactly the dashboard's current widget set before writing
  anything, plus a new `@dnd-kit` frontend dependency (the first
  drag-and-drop library this project has used). Building it surfaced a
  second gap nothing had flagged: `POST`/`DELETE .../widgets` were real,
  tested backend endpoints since Phase 6 that the frontend simply never
  called — a dashboard's widget set could only ever be set once, by
  auto-generate, never edited after. Closed in the same pass: a remove
  button per widget, and an "Add a KPI widget" picker (for the four
  industry packs) built from the real `/industry-packs/{id}` KPI list,
  not a hardcoded frontend copy of it. Chart widgets were scoped out of
  that first cut and built immediately after, as a single fully generic
  form rather than one form per operation — driven entirely by
  `GET /tools`' existing metadata (the same registry `/analyze` and the
  AI planner already use), so all 7 registered operations are addable
  through one component, and an 8th tool added later needs no frontend
  change to become addable too. The one new backend piece this needed —
  `GET /dataset-tables/{id}`, for real column names instead of free-text
  input — turned out to be a genuine, slightly surprising gap: every
  other `/dataset-tables/{id}/*` endpoint already loaded that row
  internally, but none had ever returned the table itself. General
  (no-pack) workspaces get their first manual widget-add capability of
  any kind through this, since chart widgets need no industry pack.
  Verified with real browser interactions throughout: an actual pointer
  drag reorder; real KPI and chart widgets (three different parameter
  shapes — one required column, a required-plus-optional-with-default
  mix, and two required columns with no defaults at all) added and
  removed through the new UI with their real computed values checked by
  hand; all confirmed via the network panel and a database check, not
  just the UI's own re-render.
- **Post-Phase-7 — Dataset version comparison UI, webhooks UI, and a
  systematic gap sweep**: after finding the same "backend endpoint,
  zero frontend trace" bug twice by hand (the two bullets above), the
  next step was mechanical rather than manual — cross-referencing every
  backend route against every frontend API call. That sweep found two
  gaps bigger than anything built up to that point: a complete, tested
  **Organizations** feature (create/list/invite/audit-log — only invite
  *acceptance* is wired) and a complete, tested **Webhooks** feature
  (subscribe/list/delete/test), neither with a single line of frontend
  code. Organizations looked like it needed real product/UX decisions
  first (team onboarding, whether workspace creation needs an org
  picker) and was flagged rather than built in this pass — see the
  Organizations bullet below for how that turned out. Webhooks and
  dataset version comparison were the two gaps that *were*
  self-contained wiring fixes, and both got built: version comparison
  (`POST /datasets/{id}/compare-versions`,
  built and tested back in Phase 6, that the workspace page's own "N
  versions" copy advertised without ever exposing) got a compare toggle
  defaulting to the two most recent versions with a row-count/column/
  per-column diff view, verified against a real duplicate row removed
  via a real `/deduplicate` call with every figure hand-checked against
  the source CSV. Webhooks got a workspace-scoped settings page
  following the existing API-keys page's pattern exactly (create, show
  a secret once, list with delivery status, delete, plus a "send test"
  action) — verified against two genuine external HTTP deliveries, a
  success (`https://httpbin.org/post`, real `200`) and a failure
  (`https://httpbin.org/status/500`, real `500` correctly surfaced in
  the UI), which also caught a real bug: deleting a webhook left its
  one-time secret banner and last test result stuck on screen, fixed by
  clearing both on delete.
- **Post-Phase-7 — Organizations UI**: the gap left deliberately unbuilt
  above — a dedicated investigation (not guesswork) found the "needs
  product decisions" questions mostly already had answers sitting
  unused in the codebase. `POST /workspaces` already accepted
  `organization_id`, tested, just never sent by the frontend. Billing
  was already fully org-aware — `Subscription` is keyed to a user XOR
  an organization, with every `/billing/*` endpoint already
  membership/manager-gated — nothing new to design, only to expose (and
  deliberately not exposed in this pass: an org-aware billing/pricing
  page is its own separate surface). The one real gap: no endpoint
  existed to list an organization's members, so `GET
  /organizations/{id}/members` was added. Built a new
  `/dashboard/organizations` page (create an org, per-org member list,
  invite-by-email with a role picker, an audit-log view) plus an
  "Owner" dropdown on workspace creation. Verified both invite paths —
  a real `201` for an already-registered user added immediately, a real
  `202` for a new email that actually got sent through the
  already-verified Gmail SMTP integration — and, critically, the
  feature's actual point rather than just its CRUD surface: logged in
  as the invited member's real account and confirmed a workspace
  created by someone else in the same organization was visible and
  fully usable, not just that the invite UI renders. Also caught a real
  bug live: the invite success message assumed a response field
  (`user_email`) that endpoint never actually returns — a different one
  does — producing "undefined added as analyst" until fixed.

See docs/CHECKLIST.md for exactly what is and isn't verified in the
unconnected pieces — including real bugs caught and fixed during this
build: an authorization-ordering flaw that could leak server config to
unauthorized callers (found independently in the AI and billing
routers), an upload size ceiling that would have silently capped the
higher-tier plans below their stated limits, three Phase 5 KPIs that
were defined but had no calculator wired up, a missing `db.commit()` in
the Phase 6 scenario endpoint that silently discarded quota increments,
an uncaught token-validation exception in Phase 7's SSO flow that would
have surfaced a tampered ID token as a raw 500 instead of a clean 400,
a missing auth cookie on the SSO login path that would have silently
logged a real SSO user out on their next page reload, and a test suite
that had started silently depending on real third-party credentials
once they were added to local `.env` — each one caught by actually
checking an outcome (a reload, a re-run of the full suite, a number) 
rather than stopping at "no error."

Try it: register → create a workspace (pick an industry) → open it →
upload a .csv or .xlsx file → click "Clean this data" to drop missing
rows, normalize text, filter, pivot/unpivot, group by, or add a
calculated column → download its PDF data quality report → compute
industry KPIs and see them as stat cards, reviewing/correcting the
automatic field mapping first if something looks wrong → generate a
dashboard automatically and leave a comment on it → for any of the four
industry workspaces (commercial property, residential property, social
housing, business finance), download that pack's specialist portfolio
report too, or schedule it to run (and email itself to you, if
`SMTP_HOST` is set) daily/weekly/monthly → check the usage widget on
the dashboard, click through to
API keys and create one → hit the Free plan's 3-analyses/month limit.
The "Ask the AI analyst" box, the pricing page's "Subscribe" buttons,
and SSO login are there too — all three honestly tell you they're not
configured yet rather than faking a response. "Forgot password?" on the
login page works end-to-end once `SMTP_HOST` is set.

Everything else in the original brief (6 of 12 report templates,
public sector/education packs, SCIM provisioning, custom roles, and a
production deployment manifest) is **not yet built**. See
[docs/CHECKLIST.md](docs/CHECKLIST.md) for the detailed, honest
breakdown of every phase, including what's deliberately cut or
unverified within what's listed as done.
