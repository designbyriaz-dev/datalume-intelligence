# Feature completion checklist

Status as of 2026-10-13. All 7 of the brief's phases are complete, plus
a substantial round of post-Phase-7 work (see the "Post-Phase-7:" ✅
sections throughout this document — transactional email, 7 more
cleaning operations completing the brief's entire list, S3Storage
verification against a mocked S3 API, AI conversation-history replay
fidelity, three more specialist report templates covering every
industry pack, industry field mapping confirmation, scheduled report
email delivery and its frontend UI, a distributed lock for the
scheduler, rate limiting on every auth endpoint, moving the auth
refresh token out of localStorage into an httpOnly cookie with CSRF
protection, and two billing audit-log gaps closed). All four of the
credential-gated integrations are now off the "unverified against a
real account" list: Stripe (Checkout, webhooks, and the Billing Portal
all run end-to-end against a real sandbox account — see Phase 4's
updated section), the AI analyst (two real questions, a real multi-turn
conversation, correct tool calls and figures verified by hand against a
real Anthropic API key — see Phase 3's updated section), transactional
email (a real Gmail account and a real inbox — see "Post-Phase-7:
transactional email"'s updated "Email service" bullet), and SSO/OIDC
(a real Google OAuth client, a real consent screen, a real login
end-to-end through a newly-built frontend callback page — see Phase 7's
updated "SSO via OIDC" section, which also caught and fixed two real
bugs: a missing auth cookie on the SSO login path, and a test suite
that had started silently depending on real credentials in
`apps/api/.env`). This is the authoritative "what's actually done"
list — treat any conflicting claim elsewhere (including the website
copy) as aspirational, not current.

Legend: ✅ done & tested · 🚧 in progress · ⬜ not started

## Phase 1 — Foundation

- ✅ Monorepo structure (`apps/api`, `apps/web`, `infra`)
- ✅ Backend: FastAPI + SQLAlchemy async + Alembic, running on SQLite (dev)
  or Postgres (prod) via one `DATABASE_URL`
- ✅ Frontend: Next.js 14 + TypeScript + Tailwind, responsive, light/dark
  mode (via `prefers-color-scheme`)
- ✅ User registration, login, JWT access/refresh tokens
- ✅ Personal workspaces (owned by a user)
- ✅ Organization accounts with role-based membership
  (owner/administrator/analyst/viewer/auditor)
- ✅ Organization workspaces, invite-by-email (existing users get an
  immediate membership; not-yet-registered users get an emailed invite
  — see the Post-Phase-7 "transactional email" section below. Requires
  `SMTP_HOST` configured; falls back to the original "ask them to
  register first" 404 without it.)
- ✅ Server-side tenant isolation (not just hidden UI) — tested
- ✅ Docker Compose dev environment (Postgres, Redis, MinIO, api, web)
- ✅ Basic public website: homepage, pricing (static), login, register
- ✅ Automated backend test suite: 14/14 passing, covering:
  - Journey: register → login → fetch own profile
  - Journey: create a personal workspace
  - Journey: organization owner creates a shared workspace; a non-member
    is denied (Journey 5 / Journey 7 from the brief)
  - Journey: a non-manager cannot invite members to an organization
- ✅ Email verification delivery and password reset — built after Phase
  7, not in this phase's original pass; see the Post-Phase-7
  "transactional email" section below.
- ⬜ MFA
- ⬜ Onboarding "what do you want to analyse" flow (industry is currently
  just a dropdown on workspace creation, not a guided first-run flow)
- ⬜ Full public page set from the brief (Features, How It Works,
  Solutions sub-pages, Security page, About, Contact, FAQs, ToS, Privacy
  Policy, Cookie Preferences) — only a homepage and a static pricing page
  exist today

## Phase 2 — Data Intelligence Engine

- ✅ Secure CSV/XLSX upload (`POST /api/v1/workspaces/{id}/datasets`):
  extension allow-list, magic-byte verification (rejects a disguised
  executable/zip/PDF even if renamed to `.csv`), a platform-wide size cap,
  and a zip-bomb guard on `.xlsx` (rejects before fully inflating).
  Macro-enabled workbooks are rejected outright.
- ✅ Multi-sheet XLSX support — one `DatasetTable` per worksheet, verified
  with a 2-sheet workbook producing 2 independently-profiled tables.
- ✅ Encoding + delimiter detection for CSV (`charset-normalizer` +
  `csv.Sniffer`, with sane fallbacks) — doesn't assume UTF-8/comma.
- ✅ Schema inference per column (integer/float/boolean/date/datetime/text)
  via Polars, plus a text-pattern heuristic that flags numbers or dates
  stored as text (`numeric_stored_as_text` / `date_stored_as_text`)
  **without silently nulling out values that don't match one format** —
  this was deliberately chosen over Polars' native date parsing, which
  does silently null mismatched values in a mixed-format column (see
  docs/ARCHITECTURE.md and the comment in `app/services/profiling.py`).
- ✅ Data quality scoring: a documented, deterministic 0–100 formula
  (missing data, duplicate rows, flagged-format columns) — not an LLM
  guess. Per-column and per-table issue lists with severity.
- ✅ Statistical calculations per column: min/max/mean/median/std-dev for
  numeric columns, true/false counts for booleans, min/max length for
  text.
- ✅ Analytical result storage: versioned `Dataset` → `DatasetVersion` →
  `DatasetTable` model. Raw upload + a Parquet copy of each table are
  written to object storage (local disk in dev, S3-compatible via
  `boto3` once `S3_ACCESS_KEY` is set — see Known limitations on the S3
  path's test status).
- ✅ Schema confirmation: `PATCH /api/v1/dataset-tables/{id}/schema` lets a
  user override inferred column types (validates against known columns
  and the allowed type set).
- ✅ First real cleaning operation — **deduplicate rows**
  (`POST /api/v1/dataset-tables/{id}/deduplicate`): produces a *new*
  `DatasetVersion` (every sheet in the version, not just the one
  deduplicated, so each version is a complete snapshot) and a
  `Transformation` audit row recording who did it, when, and how many
  rows were removed. The source version is never mutated — verified by a
  test that re-reads the original version after deduplicating and
  confirms its row count is unchanged.
- ✅ Tenant isolation extended to datasets: an outsider gets 403 on
  upload/read; an org **Viewer**/**Auditor** can read a workspace's
  datasets but is blocked (403) from uploading or running transformations
  — tested.
- ✅ Verified against a real running server (not just the test client):
  manual `curl` upload with mixed date formats and a duplicate row, then
  a live browser session (register → create workspace → upload → see
  profile → deduplicate → see version 2) — see session transcript. Both
  matched the automated test expectations exactly.
- ✅ Automated backend tests: 8 new (22/22 total passing) covering upload
  profiling correctness, disguised-file rejection, oversized-file
  rejection, multi-sheet XLSX, schema confirmation (incl. invalid
  column/type rejection), deduplicate + original-preserved, and the two
  tenant-isolation cases above.
- ✅ **Four more cleaning operations**, built after Phase 7 alongside
  transactional email — see the "Post-Phase-7: more cleaning operations"
  section below for the full list (handle missing values, normalise
  text, filter rows, calculated fields). Each follows deduplicate's
  exact pattern (new version, original preserved, Transformation audit
  row) via a shared helper extracted from it.
- ✅ **Three more cleaning operations** — standardise dates/currencies,
  merge columns, and split column — built in a later round; see the
  "Post-Phase-7: date/currency standardisation and merge/split columns"
  section below.
- ✅ **Pivot and unpivot** — built in a later round after all, on
  reflection the "bigger design question" concern (data-dependent
  column count) turned out to be the same shape of problem
  split-column already solved, not a new one. See "Post-Phase-7:
  pivot and unpivot" below.
- ✅ **Group-by as a persisted cleaning operation** — built in a later
  round, see "Post-Phase-7: persisted group-by" below. This completes
  every cleaning operation the brief's Phase 2 gap list named —
  compare-datasets is covered by Phase 6's version comparison.
- ✅ **"Detect invalid values" as its own category** — a `ColumnProfile`
  now carries `invalid_count`/`invalid_ratio` alongside `null_count`, and
  a new `invalid_values` issue type is raised distinct from
  `missing_values`. The real mechanism this closes: `parse_csv`'s
  `ignore_errors=True` only silently nulls a cell when it falls outside
  the first `infer_schema_length` (10,000) rows used to infer that
  column's type — within that window Polars already widens the column to
  text if anything doesn't fit, so this specifically catches large
  exports where a bad value shows up later in the file. Detected by
  re-reading the same CSV with every column forced to text and comparing:
  a cell that's null in the typed read but non-blank in the text read is
  "invalid"; one that's blank in both stays "missing"
  (`_detect_coercion_failures` in `app/services/profiling.py`). Scoped to
  CSV only — Excel cells arrive already typed by the spreadsheet app, so
  there's no equivalent coercion-failure mode to detect there. Verified
  with a real >10,000-row upload (not just a small in-memory fixture,
  which Polars would infer as text and never exercise this path) through
  the real API, and confirmed live in the browser: the workspace page's
  per-column table shows a distinct "Invalid" count next to "Missing".
- ⬜ Async/background processing for large files — uploads are processed
  synchronously in the request. Fine for the brief's ~30s small-file
  target; large files will block the request. Redis is in
  docker-compose but no worker process consumes it yet.
- ⬜ Real malware/AV scanning (`MALWARE_SCANNING_ENABLED` is a documented
  no-op flag, not a scanner — see docs/SECURITY.md). Structural
  validation (magic bytes, zip-bomb guard) is real; antivirus is not.

## Phase 3 — AI and Reporting

- ✅ Deterministic analytical tools engine (`app/services/analytics.py`):
  descriptive stats, frequency tables, Pearson correlation, IQR outlier
  detection, group-by aggregation, month/year trend, and a simple
  linear-trend forecast baseline. Every number is a reproducible
  calculation — no LLM involved. A single tool registry
  (`app/services/tools.py`) is the source of truth for both the direct
  API and the AI planner below, so "AI must not execute arbitrary code"
  is structural, not a policy statement.
- ✅ `POST /dataset-tables/{id}/analyze` + `GET .../analyses`: run any
  tool directly via the API (no AI needed) and list saved runs — this
  *is* "saved analyses": running one saves it, nothing extra needed.
  Available to Viewers/Auditors (read-only, doesn't mutate the dataset).
- ✅ PDF report generation (`app/services/reports.py`, reportlab, no
  system dependencies): a real "Data Quality Report" — quality score,
  column profile table, a missing-values bar chart, issue list,
  methodology footnote. Deterministic, no AI narrative.
  `POST /dataset-tables/{id}/reports/data-quality` +
  `GET /reports/{id}/download`. Verified by reading the actual rendered
  PDF output, not just checking the file is non-empty.
- ✅ AI query planner — the orchestration harness (`app/services/ai/`):
  a standard agentic tool-calling loop restricted to the tool registry
  above, a grounding system prompt (never state a figure without a tool
  call backing it, state forecast caveats, cite columns), an iteration
  cap so a misbehaving model can't loop forever, and full conversation
  persistence (`AIConversation`/`AIMessage`, with the tool-call evidence
  trail stored alongside each assistant message).
- ✅ The orchestration harness has real automated test coverage — 5 tests
  in `tests/test_ai_planner.py` using a scripted fake LLM client verify
  tool execution, correct message threading, error handling, and that
  the iteration cap actually bounds the loop (10 scripted tool-calls in,
  only 5 executed). Plus 4 API-level tests including a real security fix
  caught during this build: the route originally resolved the "is the
  LLM configured" dependency before the "does this user have access"
  dependency, meaning an outsider would get a 503 revealing server
  config before ever being told "no". Fixed by making authorization its
  own dependency ordered first — FastAPI resolves `Depends()` in
  signature order and stops at the first one that raises. Verified with
  a test asserting the outsider gets 403, not 503.
- ✅ `POST /dataset-tables/{id}/ask` + conversation endpoints are fully
  wired and return a clean `503` with a clear message when no LLM key is
  configured — which is this environment's real, current state. The
  frontend surfaces that 503 honestly too ("The AI analyst isn't
  connected to a model yet") rather than hiding the feature or faking a
  response.
- ✅ **`AnthropicLLMClient` (`app/services/ai/llm_client.py`) verified
  against a real API key and a real model, closing the gap this bullet
  used to describe.** A real user uploaded a real 3-row CSV
  (unit/rent/tenant) through the real API and asked two real questions
  through `POST /dataset-tables/{id}/ask`. Turn 1 ("What is the total
  rent across all units?") correctly called `descriptive_stats` and
  answered £4,500, matching a hand-computed sum. Turn 2, in the *same*
  conversation ("What percentage of that total does Acme Ltd account
  for?"), correctly referenced "that total" from turn 1 without being
  retold it, called only `group_aggregate` (not `descriptive_stats`
  again — it already had the total from context), and answered 55.6%
  (2,500/4,500) and 44.4% (2,000/4,500) — both correct. This is also
  the first real-model confirmation of the "Post-Phase-7: conversation
  history replay fidelity" fix below: it had previously only been
  proven against `FakeLLMClient` in tests, never against the real
  Anthropic API actually using replayed prior-turn tool_use/tool_result
  blocks to answer correctly. A human read both real transcripts and
  checked the figures by hand — not just confirmed a `200` status.
- ✅ **Conversation history replay fidelity** — fixed post-Phase-7 (see
  the section below). Earlier turns now replay with their original
  tool_use/tool_result block structure intact, not flattened to plain
  text.
- ✅⚠️ **Dashboard chart widgets now render a real chart** — see
  "Post-Phase-7: real chart rendering for dashboard chart widgets"
  below. Caught mid-session: the earlier "Add a chart widget" feature
  (Phase 6 section) was misleadingly named — it added the ability to
  pick any of the 7 analytics tools as a widget, but every one of them
  rendered as a raw `JSON.stringify` dump, never an actual chart. Still
  no AI/LLM "chart-spec generation" layer, and still only a bar-chart
  renderer for 3 of the 7 operations (`group_aggregate`,
  `frequency_table`, `time_trend`) — `correlation`'s scatter data,
  `descriptive_stats`' flat scalars, `detect_outliers`, and
  `simple_forecast`'s two-series shape still fall back to JSON.
- ⬜ Most of the brief's report templates that need AI-generated
  narrative (Executive Intelligence Report, Financial Performance
  Report, etc.) — only the deterministic Data Quality Report exists at
  Phase 3. (Four more deterministic, non-narrative reports — one per
  industry pack — were added post-Phase-7; see the Phase 5 section
  below. Those don't need this point's AI-narrative gap resolved, since
  they were deliberately built without any AI involvement.)
- ⬜ Statistical rigor gaps, documented in `app/services/analytics.py`:
  `simple_forecast` is an explicit linear-trend baseline (not
  seasonality-aware, documented in its own output as a caveat) — the
  brief's "appropriate forecasting libraries" (statsmodels etc.) aren't
  used.
- ✅⚠️ **Date parsing for analytics tools** — was 4 strptime formats
  (not actually regex, despite this bullet previously saying so), now
  11, see "Post-Phase-7: written-month date formats for analytics
  tools" below. Still not a general date parser — a fixed format list,
  same approach as before, just longer.

## Phase 4 — Commercial SaaS

- ✅ Configurable entitlement system (`app/core/plans.py`): all 6 plans
  from the brief (Free/Personal/Professional/Business/Team/Enterprise)
  with their stated prices and limits, in one registry — changing a
  limit doesn't touch application code. Two numbers the brief didn't
  specify are flagged inline as explicit assumptions (Business's saved-
  dataset cap, Team's pooled monthly allowance) rather than silently
  invented.
- ✅ Every account gets a Subscription automatically (lazily, on first
  access) on the Free plan — no "no subscription" state exists anywhere
  else in the app to special-case.
- ✅ Server-side quota enforcement — genuinely server-side, not a
  frontend check the API would still allow past:
  - Upload blocked (`402`) over the plan's file-size cap, independent of
    the platform-wide safety ceiling (see the bug fixed below).
  - Upload blocked (`402`) once the account's saved-dataset count
    (summed across every workspace it owns) reaches the plan cap.
  - Analysis blocked (`402`) once the monthly analyses quota is used —
    and only consumed on a *successful* analysis; a bad request (unknown
    column, wrong type) costs nothing.
- ✅ **A real bug caught and fixed during this build**: the platform-wide
  upload safety ceiling (from Phase 2) defaulted to 50MB — lower than
  Business (250MB), Team (500MB) and Enterprise (1GB)'s plan limits.
  Those plans' larger uploads would have been silently rejected by the
  flat ceiling before the plan-specific check ever ran. Fixed by raising
  the ceiling to 1GB (documented as needing to stay ≥ the largest plan)
  and covered by a regression test that lowers it again to prove the
  right layer reports the rejection.
- ✅ Stripe integration code (`app/services/stripe_billing.py`): Checkout
  Session creation (subscription mode), Billing Portal session creation,
  webhook signature verification — written against the documented
  Stripe API. Gated behind `STRIPE_SECRET_KEY` the same way the LLM
  client is gated: a clean `503` with a clear message, not a fake
  response, when unconfigured (verified against a real running server).
- ✅ **Webhook event handling has real test coverage without a live
  Stripe account** (`app/services/webhook_handlers.py`,
  `tests/test_billing_webhook.py`, 5 tests): payloads are signed with
  Stripe's publicly documented HMAC scheme using a secret we control,
  then sent through the real verification code path
  (`stripe.Webhook.construct_event`). Covers `checkout.session.completed`
  activating a subscription, `customer.subscription.updated` changing
  plan/billing-period/status from the Stripe price ID, cancellation
  downgrading to Free (which actually removes entitlements, not just
  flips a status flag), an invalid signature being rejected, and unknown
  event types being safely ignored.
- ✅ Another dependency-ordering security fix, same shape as Phase 3's:
  Checkout/Portal session creation originally resolved "is Stripe
  configured" before "is this user allowed to manage this org's
  billing," meaning a non-manager could learn server configuration via
  a 503 before being told no. Fixed the same way — authorization as its
  own dependency, ordered first — and covered by a test that would have
  caught it (`test_non_manager_gets_403_not_503_on_checkout`).
- ✅ Public pricing page and dashboard usage widget both call the real
  API — no more static marketing copy. The pricing page's Subscribe
  button, when Stripe isn't configured, shows "Billing isn't connected
  to Stripe yet" rather than a dead button or a fake checkout. Verified
  live in the browser.
- ✅ **Checkout, webhooks, and the Billing Portal verified end-to-end
  against a real Stripe sandbox account** (not a mock, not a simulated
  payload this time) — closing the gap this bullet used to describe.
  A real test-mode product catalog (4 plans × monthly/annual = 8 real
  `price_` IDs) was created in the Stripe Dashboard; `STRIPE_SECRET_KEY`,
  `STRIPE_WEBHOOK_SECRET`, and all 8 `STRIPE_PRICE_ID_*` are live in
  `apps/api/.env` (gitignored, never committed). With a real server
  running and the Stripe CLI (`stripe listen --forward-to
  localhost:8000/api/v1/billing/webhook`) actually forwarding, a real
  Checkout session was created via the real API, completed in a real
  browser with Stripe's published `4242 4242 4242 4242` test card, and
  confirmed: a real signed `customer.subscription.updated` webhook
  (among others — `checkout.session.completed`, `invoice.paid`, etc.,
  all genuinely HMAC-verified, not pre-signed test fixtures) arrived
  and was processed correctly, `GET /billing/subscription` showed
  `plan_id: "personal"`, `status: "active"`, the Personal plan's real
  25-analyses-per-month limit — an actual entitlement unlock, not a
  database row checked in isolation. `POST /billing/portal-session`
  was separately confirmed returning a real `billing.stripe.com` URL.
  Still true: this was a **sandbox** (test mode) account, not a real
  production Stripe account processing real cards — that distinction
  stands the same way it does for every other "verified" integration
  in this project.
- ⬜ No failed-payment dunning flow beyond marking the subscription
  `past_due` on `invoice.payment_failed` — no retry scheduling, no
  customer email, no automatic downgrade after repeated failures.
- ⬜ VAT handling — not implemented; Stripe Tax or manual VAT
  configuration would need to be set up in the Stripe Dashboard and
  wired through Checkout Session creation (`automatic_tax` parameter).
- ✅ Admin visibility into subscriptions/MRR exists as of Phase 7's
  admin dashboard (`subscriptions_by_plan`, `estimated_mrr_gbp`) — see
  the Phase 7 section below. Churn specifically (subscriptions lost
  over time) still isn't tracked — the dashboard shows a point-in-time
  snapshot, not a trend.
- ✅⚠️ **"Usage resets in N days" countdown** — done, see "Post-Phase-7:
  usage reset countdown" below. Still true: usage is tracked per
  calendar month only, with no usage-history view and no proration
  display for mid-cycle plan changes (Stripe handles proration on its
  side once Checkout/Portal are live, but nothing surfaces that to the
  user yet).

## Phase 5 — Specialist Intelligence

Scope note: built the four packs named in the brief's own Phase 5
"Create" list (commercial property, residential property, business
finance, social housing). Public sector and education/health are
described in section 9 but weren't in that list — not started, and
public sector in particular needs real domain input before its KPIs
could be written honestly rather than guessed.

- ✅ Industry pack registry (`app/core/industry_packs.py`): all four
  packs with real column-alias lists, KPI definitions, suggested AI
  questions, and a terminology glossary — one source of truth, same
  registry pattern as `app/core/plans.py` and `app/services/tools.py`.
- ✅ Column alias matching (`app/services/industry_matching.py`): maps
  real-world messy headers ("Rent (PCM)", "Lease Expiry Date") onto
  canonical fields via exact-match then whole-word-token matching —
  deliberately not raw substring matching, so "Parent Company" doesn't
  false-match the alias "rent" (tested explicitly).
- ✅ KPI calculation engine (`app/services/industry_kpis.py`): 26 KPIs
  across the four packs (8 commercial property, 7 residential, 6 social
  housing, 5 business finance), each a real deterministic calculation,
  each independently numerically verified in tests against hand-computed
  expected values — not just "runs without crashing."
- ✅ **A real bug caught by writing the tests, not by inspection**: three
  social housing KPIs (total_repair_cost, average_repair_cost,
  total_planned_investment) were defined in the pack but had no
  calculator registered — they would have silently returned "No
  calculator implemented yet." for every user, forever, with no error
  surfaced anywhere. Fixed, and a standing regression test
  (`test_every_pack_kpi_has_a_registered_calculator`) now asserts every
  KPI in every pack has a calculator, so a future pack addition can't
  repeat this unnoticed.
- ✅ `POST /dataset-tables/{id}/industry-kpis`: resolves the workspace's
  industry, matches columns, computes every KPI for that pack, reports
  which required fields couldn't be matched (without refusing to compute
  the KPIs that *can* still be answered), and saves the result as an
  `AnalysisRun` — reusing Phase 3's "saved analyses" storage rather than
  inventing a parallel concept. Consumes the plan's monthly analysis
  quota, same as `/analyze`.
- ✅ Social housing responses always carry the brief's explicit
  compliance warning ("do NOT constitute legal compliance certification")
  — enforced by a test, not just present in the pack's text.
- ✅ One specialist PDF report, **Commercial Property Portfolio Report**
  (`generate_commercial_property_report_pdf`): KPI summary, rent-by-
  category breakdown, and a lease-expiry schedule sorted by date — built
  from and sharing the exact same KPI calculation code as the API
  endpoint above, so the two can never disagree with each other.
  Verified by reading the actual rendered PDF output.
- ✅ "Generate dashboard automatically" exists as the `/industry-kpis`
  response itself — a flat list of ready-to-render KPI cards the
  frontend turns into a stat-card grid, with no manual widget
  configuration needed. Verified live in the browser: uploaded a rent
  roll to a commercial_property workspace and got real computed KPIs on
  screen, matching the unit tests and the PDF exactly.
- ✅ **Residential Property Portfolio Report** — the second specialist
  report template, built in a later round; see "Post-Phase-7: second
  specialist report template" below.
- ✅ **Social Housing Asset Report** — the third specialist report
  template, built in a later round still; see "Post-Phase-7: third
  specialist report template (social housing)" below. The first PDF
  report to render the brief-required compliance caveat.
- ✅ **Business Performance Report** — the fourth specialist report
  template, built in a later round still; see "Post-Phase-7: fourth
  specialist report template (business finance)" below. Every industry
  pack from the brief's Phase 5 "Create" list now has a report.
- ⬜ ~~The other 8 report templates~~ 6 remain from the brief's list
  (Investment Planning Report, Executive Intelligence Report, etc.) —
  Compliance Exceptions and Repairs and Maintenance are now built too,
  see "Post-Phase-7: fifth specialist report template (social housing
  compliance exceptions)" and "Post-Phase-7: sixth specialist report
  template (residential repairs and maintenance)" below (each attached
  to an existing pack as a second report, not a new pack —
  `commercial_property` and `business_finance` are the two packs that
  still have only one report each: the former has no capex/valuation
  field an Investment Planning report could use without inventing data,
  the latter's one report already covers revenue/expenses/trends/top-
  customers fairly completely). Each remaining template would follow
  the exact same pattern (KPI engine + a PDF layout, now proven six
  times), so adding one is a template-writing task, not an architecture
  problem — a third report on an existing pack, or a new pack (public
  sector/education), the latter needing real domain input first (see
  `app/core/industry_packs.py`'s module docstring).
- ✅ Dashboards moved well past "KPI stat-cards only" — persisted
  dashboards with drag-and-drop reorder and chart widgets (not just the
  PDF report's static table) now exist; see "Post-Phase-7: dashboard
  drag-and-drop reorder, add, and remove widgets" below for the full
  Phase 6 build-out. Widget resizing and multiple saved layouts per
  table are still not built (see that section's own remaining gaps).
- ⬜ Public sector and education/health packs — not started (see scope
  note above).
- ✅ Column matching is still a heuristic (word-token overlap), not a
  certified parser — ambiguous short aliases (e.g. "status") can still
  mismatch on unusual real-world data. But a user can now review and
  correct the automatic mapping before KPIs/reports are computed,
  extending Phase 2's schema-confirmation pattern — see "Post-Phase-7:
  industry field mapping confirmation" below.
- ✅ **"Overdue inspection" (social housing) and "leases expiring within 12
  months" (commercial property) are now configurable per workspace** —
  see "Post-Phase-7: configurable KPI date window" below. Still a
  12-month default, not a value the brief specified, but no longer fixed.

## Phase 6 — Advanced Analytics

- ✅⚠️ **Historical comparison** (`app/services/version_compare.py`,
  `POST /datasets/{id}/compare-versions`): compares two versions of the
  same dataset — row-count delta, added/removed columns, and per-column
  before/after stats (sum/mean deltas for numeric columns, distinct-count
  and most-common-value for categorical ones). Reuses Phase 2's existing
  version chain; no new storage concept needed. Tested against two real
  uploaded CSVs with known deltas. **Built this phase but never wired to
  the frontend until post-Phase-7** — the workspace page showed "N
  versions · original data preserved at every step" without any way to
  actually see what changed between them; see "Post-Phase-7: dataset
  version comparison UI" below.
- ✅ **Scenario modeling** (`app/services/scenario.py`,
  `POST /dataset-tables/{id}/scenario`): "what if rent increases 10%?" —
  applies percentage/fixed-amount/set-value adjustments to a copy of the
  data, then recomputes baseline and scenario KPIs through the *exact
  same* Phase 5 KPI engine, so the two numbers can never drift apart from
  independent calculation paths. Returns a delta + % change per KPI.
- ✅ **A second instance of the Phase 3/4 commit bug, caught the same
  way**: the scenario endpoint checked and incremented the analysis
  quota but never called `db.commit()`, so the increment was silently
  discarded at the end of the request — a quota-exhaustion test (4
  calls, expecting the 4th blocked) caught it immediately by returning
  200 instead of 402. Fixed; same lesson as Phase 4's billing bug,
  this time in a different router — worth grepping for the same pattern
  (`check_and_increment_analysis_quota` followed by no `db.commit()`) if
  more quota-gated endpoints are added later.
- ✅ **Dashboard builder** (`app/models/dashboard.py`,
  `app/services/dashboards.py`, `/workspaces/{id}/dashboards*`,
  `/dashboards/{id}*`): persisted, named dashboards made of widgets
  (`kpi` or `chart` type). Only widget *configuration* is stored — every
  value is computed live on read, from the same KPI engine and tool
  registry as their single-shot counterparts (`/industry-kpis`,
  `/analyze`), so a dashboard can never show a number those endpoints
  would disagree with. Full CRUD (create, add/remove widget, delete),
  tested including graceful per-widget error handling (one broken widget
  doesn't take down the rest of the dashboard).
  **Honesty note**: at the time this was built, "advanced" meant
  configurable and persisted, not drag-and-drop — there was no visual
  layout editor, just an ordered widget list. Since fixed — see
  "Post-Phase-7: dashboard drag-and-drop reorder" below.
- ✅ **"Generate Dashboard Automatically"** (the brief's literal phrase,
  section 10): one KPI widget per metric for an industry-pack workspace,
  or a profile-driven set of chart widgets (numeric column summaries,
  plus a category breakdown) for a general workspace — inspecting
  `DatasetTable.profile` the same way Phase 2's schema confirmation
  does. Verified live in the browser: uploaded a commercial property CSV
  and got 8 real computed KPI widgets with no manual configuration.
- ✅ **Scheduled reporting** with a real in-process scheduler
  (`app/services/scheduled_reports.py`, APScheduler job registered in
  `app/main.py`'s lifespan, 5-minute tick): `ScheduledReport` rows with
  daily/weekly/monthly frequency: a correct `compute_next_run` (handles
  month-length clamping, e.g. Jan 31 → Feb 28, and year rollover) and a
  `run_due_scheduled_reports` function that generates the report,
  advances `next_run_at`, and records `last_error` without crashing the
  whole batch if one schedule's workspace/table no longer exists.
  Verified both ways: unit-tested directly (set `next_run_at` into the
  past, call the function, assert a real PDF was generated and the
  schedule advanced — no waiting on wall-clock time) AND confirmed the
  server boots cleanly with the real APScheduler job running (not just
  under the test client, which skips FastAPI's lifespan entirely).
- ✅ **Organisation collaboration**: dashboard comments
  (`DashboardComment`, `/dashboards/{id}/comments*`). The specific,
  deliberate test here: an org **Viewer** — who cannot upload data, run
  transformations, or manage billing (Phases 2/4) — *can* post a comment,
  because discussing a shared dashboard is a read-level activity, not a
  data mutation. Comment deletion is restricted to the comment's own
  author (no moderation roles in this first pass).
- ~~In-process scheduler is single-instance only~~ — done, see
  "Post-Phase-7: distributed scheduler lock" below.
- ~~No actual report *delivery*~~ — done, see "Post-Phase-7: scheduled
  report email delivery" above. Scheduled reports now email the
  creator with the PDF attached whenever `SMTP_HOST` is configured.
- ~~Dashboards have no drag-and-drop layout editor~~ — reordering is
  done, see "Post-Phase-7: dashboard drag-and-drop reorder" below.
  Widget *resizing* and multiple saved layouts per table are still not
  built — only reorder-within-a-list, no freeform/2D grid placement.
- ✅⚠️ **Saved/named scenarios** — done, see "Post-Phase-7: saved
  scenarios and a scenario modeling UI" below, which also closed a
  much bigger gap found along the way: no frontend UI for scenario
  modeling existed at all before this round, ad-hoc or saved. Still
  true: no multi-variable "preset" concept beyond a saved scenario's
  own adjustment list, and no comparison across more than one
  adjustment set at a time in a single view.
- ✅⚠️ Picking two versions from a dropdown is done — see "Post-Phase-7:
  dataset version comparison UI" below. Still true: no "what changed"
  notification when a new version is uploaded (the brief's "offer
  updated dashboards and reports" is not automatic; comparison must
  still be requested, just no longer by knowing raw version numbers).
- ⬜ SQLite vs. Postgres datetime quirk, newly relevant for scheduled
  reports: SQLite drops timezone info from `DateTime(timezone=True)`
  columns on round-trip (returns naive datetimes); Postgres preserves
  it. Functionally harmless (comparisons within one DB are consistent),
  but a test or any code comparing a DB-read datetime against a
  freshly-constructed timezone-aware one needs to normalize first — see
  the comment in `tests/test_scheduled_reports.py`.

## Phase 7 — Enterprise

Scope note: built API keys, audit logging, an admin dashboard, outbound
webhooks, and SSO (OIDC) — the core of the brief's "enterprise
administration" and "advanced governance" asks. SCIM provisioning,
custom roles beyond the fixed five, and a production deployment
manifest (Kubernetes/Terraform/etc.) are explicitly not started — see
below for why.

- ✅ **API keys** (`app/models/api_key.py`, `app/services/api_keys.py`,
  `/api-keys*`): `dlk_`-prefixed keys (GitHub PAT pattern), SHA-256
  hashed at rest, raw value shown exactly once at creation. `get_current_user`
  checks for the `dlk_` prefix before attempting JWT decode, so a key
  authenticates against every existing protected endpoint with no
  per-route changes. Full create/list/revoke tested, plus a live E2E
  check against a real running server (create a key, call a protected
  endpoint with it as a bearer token, confirm it works; revoke it,
  confirm it stops working).
- ✅ **Audit logging** (`app/models/audit_log.py`, `app/services/audit.py`):
  an explicit `EVENT_TYPES` allowlist — `record_audit_event()` raises
  `ValueError` for any event type not in the set, so a future typo in a
  call site fails loudly in tests rather than silently writing an
  unqueryable event. Wired at real decision points: user registration,
  login success/failure (failed-login events record no `actor_user_id`
  when the email doesn't match a user, so the log can't be used to probe
  which emails are registered), organization creation, member invites,
  and billing plan changes for both organization and personal
  subscriptions (closed post-Phase-7, see "Post-Phase-7: personal
  subscription plan changes now audit-logged" below — originally only
  org subscriptions were covered). `GET /organizations/{id}/audit-log`
  supports `format=json` or `format=csv`; `GET /users/me/audit-log`
  is the personal-account equivalent.
- ✅ **Admin dashboard** (`app/services/admin_stats.py`, `/admin/stats`,
  `/admin/users`): real aggregate SQL only — total/active users, 30-day
  signups, counts of organizations/workspaces/datasets/analysis runs/
  reports, total storage bytes, subscriptions-by-plan, an estimated MRR
  figure (computed only from active monthly non-free subscriptions —
  annual plans are deliberately excluded from a *monthly* figure, not
  forgotten), and failed-logins-in-24h (from the audit log above).
  `is_platform_admin` has no API path that sets it — only
  `scripts/grant_admin.py`, a standalone script — so no privilege
  escalation surface exists through the API itself. Verified live: 403
  before running the grant script, real computed stats after.
  **Explicitly not included** (no real data source exists for these
  yet, documented in the module's own docstring rather than faked): AI
  API costs, system error rates, support ticket counts.
  **Had no frontend at all until a later round** — see "Post-Phase-7:
  admin dashboard UI" below; the "verified live" above meant direct API
  calls, not a page anyone could actually open.
- ✅ **Outbound webhooks** (`app/models/webhook.py`, `app/services/webhooks.py`,
  `/webhooks*`): per-workspace subscriptions firing on `dataset.uploaded`
  and `report.generated`, signed with the same HMAC-SHA256 scheme Stripe
  itself uses (`X-DataLume-Signature: t=<ts>,v1=<hex>`) so a receiving
  server can verify authenticity with publicly documented logic. A
  delivery failure (timeout, non-2xx, DNS failure) is caught per-subscription
  and recorded on the subscription row (`last_delivery_status`/`last_delivery_error`)
  — never raised back to the triggering request, so a broken webhook
  endpoint can't break uploads or report generation. `POST
  /webhooks/{id}/test` sends a synthetic test delivery on demand. Tested
  with `httpx.MockTransport`, including the signature-verification math
  itself (sign, then independently recompute and compare).
- ✅ **SSO via OIDC** (`app/services/sso.py`, `app/models/sso_state.py`,
  `/sso/login`, `/sso/callback`) — now verified end-to-end against a real
  identity provider, not just the fake one in `tests/test_sso.py`.
  `tests/test_sso.py` builds a complete fake-but-spec-shaped OIDC
  provider: a real generated RSA keypair, a real signed ID token, served
  over `httpx.MockTransport`, driving the actual `/sso/login` →
  `/sso/callback` flow through authlib's real JWKS-fetch and
  signature/claims validation code (not a mock of that part). A second
  test signs a token with the *wrong* key and confirms it's rejected —
  this caught a real bug (see below). PKCE (S256) is used throughout.
  New-account creation from an IdP claim refuses to proceed unless the
  IdP asserts `email_verified: true`.
  **Real-provider verification**: a real Google Cloud OAuth client was
  created (`DataLume` project, External/Testing publishing status, one
  whitelisted test user), and a full login was driven through the actual
  `GET /api/v1/sso/login` → Google's real consent screen → the app's own
  (newly built) `/sso/callback` frontend page → `POST
  /api/v1/sso/callback` → `/dashboard` flow in a real browser, twice
  (once to prove the flow, once fresh after a backend fix below). The
  frontend had no `/sso/callback` page before this — `app/services/sso.py`
  was backend-complete but nothing on the frontend ever caught Google's
  redirect, so this also means SSO went from "backend built, unreachable
  from the UI" to "usable" (`apps/web/src/app/sso/callback/page.tsx`, new
  `api.ssoLogin`/`api.ssoCallback`/`useAuth().completeSso`, and a
  "Continue with Google" button on `/login`). A real `User` row was
  confirmed created in the database with the Google account's real name
  and email, and the session was confirmed to survive a full page reload
  (proving the cookie fix below actually works, not just the initial
  redirect).
  **A real bug caught by this verification pass**: `/sso/callback`
  created access/refresh tokens and returned them in the response body,
  but — unlike `/auth/login` and `/auth/refresh` — never called
  `set_auth_cookies()`. A password-login session survives a page reload
  via the httpOnly refresh cookie; an SSO-login session wouldn't have —
  the user would've looked logged in until the next reload, then been
  silently logged out, with no error to explain why. Caught by actually
  reloading the page after a real login rather than stopping at "the API
  call returned 200." Fixed by adding the same `response: Response` +
  `set_auth_cookies(...)` call `/auth/login` already makes.
  **A second real bug, found while re-running the full test suite after
  the above**: 140 of 268 backend tests started failing. Root cause:
  `apps/api/.env` now holds real Stripe/LLM/SMTP/OIDC credentials (all
  verified against real accounts this round), and `Settings` loads
  `apps/api/.env` by default — so the test suite, which was built
  assuming those integrations start "not configured" unless a test
  explicitly opts in via `monkeypatch`/`os.environ`, silently started
  picking up the real ones. Concretely: any test that registers a user
  (most of the suite, via a shared helper) now triggered a real SMTP
  connection attempt to Gmail during registration's best-effort
  verification-email send, which isn't wrapped in `try`/`except` —
  turning a working registration into an unhandled 500. Two fixes:
  (1) `apps/api/app/api/v1/routers/auth.py`'s `register()` now catches
  send failures around that best-effort email, matching what its own
  comment already claimed ("registration succeeds either way"); (2)
  `tests/conftest.py` now disables `Settings`' `.env` loading for the
  whole test session (`Settings.model_config["env_file"] = None`,
  set before `app.main` — and therefore `get_settings()` — is ever
  imported), so the suite only ever sees configuration a test explicitly
  sets, the same pattern `test_billing.py`/`test_sso.py` already used
  per-test. All 268 tests pass again after both fixes.
  **A real bug caught by the tampered-token test (test suite, found
  earlier)**: authlib raises its own `JoseError` subclasses (e.g.
  `BadSignatureError`) for anything wrong with a token, and the callback
  route originally didn't catch them — a tampered or expired ID token
  would have surfaced as a raw, uncaught 500 instead of a clean 400.
  Fixed by catching `JoseError` around the decode/validate call and
  re-raising as the route's own `SSOError`.
  **Also discovered while building this**: `authlib`'s
  `AsyncOAuth2Client` is itself an `httpx.AsyncClient` subclass with no
  way to inject an existing (or test-mocked) client/transport into it.
  Using it as initially written for the token-exchange call would have
  silently made a second, real, unmocked HTTP request in tests —
  exactly the kind of thing that makes a test pass while hiding a bug.
  Fixed by doing that one call as a plain `httpx` POST instead (it's a
  form-encoded exchange with no cryptography in it, so there's no
  real loss), while keeping authlib's `jose` module for every
  security-critical step.
  **What's still not verified**: only Google has been tried — a real
  Okta/Azure AD login hasn't, and those providers can have their own
  quirks (different claim names, different token-endpoint auth methods).
  The Google app is also still in "Testing" publishing status with one
  whitelisted test user, not verified/published — fine for this
  verification pass, not yet a production-ready SSO setup. See
  docs/DEPLOYMENT.md.
- ⬜ **SCIM provisioning** — not started. Automated user
  provisioning/deprovisioning from an IdP is a distinct protocol
  (SCIM 2.0) from the OIDC login flow above; building it would mean a
  new set of endpoints and a mapping from SCIM's user/group schema onto
  this app's User/Organization/membership models. Realistically its own
  multi-day feature, not an extension of what's here.
- ⬜ **Custom roles** — the role set is still the fixed five from Phase 1
  (owner/administrator/analyst/viewer/auditor). The brief's enterprise
  tier implies configurable/custom roles; that needs a real permissions
  model (a roles-to-permissions mapping table, UI to define one) rather
  than the current hardcoded-enum checks scattered through the
  authorization dependencies — a bigger refactor than bolting on a new
  role name.
- ⬜ **Deployment options / IaC** — docs/DEPLOYMENT.md was written this
  phase covering what a real deployment needs (managed Postgres, real
  object storage, TLS termination, the scheduler's single-instance
  caveat, etc.), but there is no actual Kubernetes/ECS/Terraform
  manifest — only the existing `infra/docker-compose.yml`, which is a
  local/single-host setup, not a production one. Writing real IaC for a
  specific cloud/platform is a project of its own once that choice is
  made; a generic manifest that's never been deployed anywhere wouldn't
  be more trustworthy than the written explanation.
- ✅ Automated backend tests: 136/136 passing (up from 100 at the end of
  Phase 6) — 36 new tests across API keys, audit logging, admin stats,
  webhooks, and SSO (11 of those in `test_sso.py` alone, including the
  fake-IdP end-to-end flow and the tampered-signature rejection).

### Post-Phase-7: transactional email

Not part of the brief's original 7 phases, but built immediately after
as the single highest-leverage follow-up: one missing integration
(flagged repeatedly through Phases 1, 4, and 6) was blocking three
otherwise-finished features. Same honest-gating pattern as Stripe/LLM/
OIDC above.

- ✅ **Email service** (`app/services/email.py`): a plain `smtplib`
  wrapper (no third-party SDK — every SMTP provider speaks the same
  protocol) behind an `EmailSender` protocol injected via FastAPI
  `Depends()`, the same shape as `get_http_client`
  (app/api/deps.py). `tests/test_email.py` verifies the real
  HELO/STARTTLS/LOGIN/SENDMAIL call sequence and its arguments by
  mocking `smtplib.SMTP` at the class level — genuine verification of
  the integration code. **Since also verified against a real mail
  provider and a real mailbox, closing the gap this bullet used to
  describe**: with real Gmail SMTP credentials (`smtp.gmail.com`, an
  app password) configured, a real account registration through the
  real API sent a real verification email that was confirmed arriving
  in a real inbox by the account holder directly reading it — not
  just a clean HTTP response or a local throwaway listener. The first
  attempt used a custom `From` address that wasn't a verified sender
  on that Gmail account; Gmail accepted the SMTP transaction anyway but
  silently substituted the authenticated account as the visible sender
  — a real, observed quirk of Gmail's relay behavior, caught only by
  checking the actual delivered email rather than trusting a successful
  SMTP handshake.
- ✅ **Email verification**: `POST /auth/register` now sends a
  verification email best-effort (registration still succeeds without
  one configured — `is_verified` just stays `false`, as before this
  feature existed). `POST /auth/verify-email` consumes a one-time token;
  `POST /auth/resend-verification` returns the identical response
  whether or not the email belongs to a real account (prevents account
  enumeration) and a clean `503` when SMTP isn't configured at all (that
  fact isn't account-specific, so there's no enumeration risk in saying
  so honestly).
- ✅ **Password reset**: `POST /auth/forgot-password` (same generic-
  response-regardless-of-account-existence pattern, 1-hour token expiry)
  and `POST /auth/reset-password`. Verified end-to-end: request reset →
  extract token from the captured email → reset → old password rejected,
  new password accepted → replaying the same token rejected.
- ✅ **Organization invites for not-yet-registered users** — the gap
  explicitly called out since Phase 1. `POST /organizations/{id}/invite`
  now emails an invite (7-day expiry token) instead of 404ing when the
  invitee has no account and SMTP is configured; falls back to the
  original 404 when it isn't. `GET /organizations/invites/{token}`
  (deliberately unauthenticated — the invitee has no account yet) lets
  the frontend preview "you've been invited to join X as Y" before
  registering. `RegisterRequest.invite_token` consumes the invite and
  creates the matching `Membership` atomically with account creation —
  rejects a mismatched email or an expired/reused token.
- ✅ One shared `EmailToken` model/table covers all three token purposes
  (verify, reset, invite) rather than three near-identical tables — same
  one-time-use-via-delete-or-mark-used pattern as `SSOLoginState`
  (Phase 7), including the same SQLite-naive/Postgres-aware datetime
  handling.
- ✅ Automated backend tests: 153/153 passing (17 new: 4 for the SMTP
  integration itself, 8 for register/verify/resend/forgot/reset, 5 for
  the org-invite-by-email flow including an expired-token case).
  Additionally smoke-tested against a real running server (not just the
  test client): registration, a garbage verify-token, an unconfigured
  forgot-password/resend-verification both correctly 503ing, and an
  invite to an unknown email correctly 404ing without SMTP configured.
- ~~Scheduled report delivery still doesn't email anything~~ — done,
  see "Post-Phase-7: scheduled report email delivery" further down.
- ~~No real mailbox has received a message from this integration~~ —
  done, see the updated "Email service" bullet above.
- ✅ **Frontend pages for all of the above**, built in the same round as
  a follow-up to the initial backend-only pass: `/forgot-password`,
  `/reset-password`, `/verify-email`, `/accept-invite` (the last one
  previews the invite via `GET /organizations/invites/{token}`, then
  registers with a locked email field and the invite token attached), a
  "Forgot password?" link on the login page. Verified live end-to-end
  against a real local SMTP listener spun up for this session (not a
  mock): a genuine `smtplib` session carried a real email to a real
  socket, the real token was extracted from the captured message, and
  the full accept-invite and reset-password flows were driven through
  the actual browser UI — including a separate API call afterward
  confirming the resulting `Membership` and password change were real,
  not just a UI state change. The dashboard does not yet prompt an
  unverified user to check their email (no banner/reminder) — the only
  remaining frontend gap.

## Post-Phase-7: more cleaning operations

Phase 2's biggest acknowledged gap was cleaning operations: the brief
listed 12, only deduplicate was built. This round added four more,
chosen for breadth of coverage (a missing-data operation, a text
operation, a row operation, a column-adding operation) rather than
depth in any one area.

- ✅ **Shared transformation helper**
  (`_apply_table_transformation` in `app/services/datasets.py`):
  extracted from the original `apply_deduplicate` so all five cleaning
  operations (deduplicate plus the four below) share one code path for
  "load every sibling sheet, run the operation against the target
  sheet, write a new version only if it succeeds, record a
  Transformation." A mutation that fails (unknown column, wrong dtype,
  ...) raises before any new version/table/storage write happens —
  verified by a test that confirms a rejected request leaves the
  dataset at exactly one version, not a half-written one.
- ✅ **Fill missing values**
  (`POST /dataset-tables/{id}/fill-missing-values`): drop the row,
  fill with a given constant, or fill with the column's mean/median
  (numeric columns only — rejects a non-numeric column with a clear
  error, tested) or mode (any column type). Filling with the mean
  provably leaves the column's mean unchanged — tested by asserting the
  post-fill profile's mean stat against the pre-fill mean, not just "no
  nulls remain."
- ✅ **Normalize text**
  (`POST /dataset-tables/{id}/normalize-text`): trim, collapse repeated
  internal whitespace, and/or change case (lower/upper/title). Rejects
  a non-text column rather than silently stringifying it.
- ✅ **Filter rows**
  (`POST /dataset-tables/{id}/filter-rows`): keep only rows matching a
  condition (eq/ne/gt/gte/lt/lte/contains/is_null/not_null) — unlike the
  Phase 3 analytics tools (read-only queries), this is a persisted
  cleaning step with its own new version and audit trail, same as
  deduplicate. `contains` is rejected on a non-text column.
- ✅ **Calculated field**
  (`POST /dataset-tables/{id}/calculated-field`): add a new column via
  arithmetic (add/subtract/multiply/divide) between two numeric columns
  or a numeric column and a constant, or text concatenation (with a
  configurable separator) between two text columns or a text column and
  a constant. Rejects a column-name collision and a dtype mismatch
  (e.g. adding a number to a text column) with a clear error.
- ✅ Every sibling sheet in a multi-sheet dataset is carried through
  unchanged when only one sheet is targeted — tested explicitly (filter
  one sheet of a 2-sheet XLSX, assert the other sheet's row count is
  untouched), the same guarantee deduplicate already had.
- ✅ **Frontend**: a "Clean this data" panel per table on the workspace
  page, with one form that adapts its fields to the selected operation.
  Verified live in the browser against a real uploaded CSV: ran
  fill-missing-values (drop_rows on an age column with a null — row
  count dropped from 4 to 3, confirmed via the profile table) and
  calculated-field (salary + 1000 as a new column — appeared correctly,
  including a correctly-propagated null for the row whose salary was
  already null) back-to-back, each producing a new version exactly as
  the API tests predict.
- ✅ Automated backend tests: 174/174 passing (21 new, in
  `tests/test_cleaning_operations.py`).
- ✅ Standardise dates/currencies, merge/split columns, and pivot/unpivot
  weren't built in this round, but all five were added in later rounds
  — see the Post-Phase-7 sections below.

## Post-Phase-7: date/currency standardisation and merge/split columns

Three more cleaning operations, built in a later round, bringing the
total to 8 (pivot and unpivot were added in a later round still — see
"Post-Phase-7: pivot and unpivot" below).

- ✅ **Standardize column**
  (`POST /dataset-tables/{id}/standardize-column`): fixes the two
  things `app/services/profiling.py`'s data-quality profiler only ever
  *detected* and flagged — `date_stored_as_text` and
  `numeric_stored_as_text` — but never corrected. `kind="date"` parses
  against an explicit strptime format the caller supplies (deliberately
  not auto-detected: the same DD/MM-vs-MM/DD ambiguity documented in
  profiling.py's own `_DATE_PATTERNS` means guessing wrong would
  silently corrupt every date in the column) and promotes the column to
  a real `pl.Date` dtype, not just a differently-formatted string —
  verified by asserting the post-standardize profile reports
  `inferred_type: "date"`. `kind="currency"` strips `£`/`$`/`€`,
  thousands separators, and a trailing `%`, then parses as a float
  (`"12.5%"` becomes `12.5`, deliberately not `0.125` — no assumption
  about whether the caller wants a fraction). A value that still
  doesn't parse becomes null (reported as `values_unparsed`) rather
  than failing the whole operation, consistent with every other
  cleaning operation's "don't crash on a few bad rows in otherwise-good
  data" philosophy.
- ✅ **Merge columns**
  (`POST /dataset-tables/{id}/merge-columns`): combines 2+ columns
  (cast to text first, so it works across mixed types — e.g. a numeric
  "year" column merged with a text "quarter" column) into one new
  column with a configurable separator, optionally dropping the
  sources. Distinct from calculated-field's `concat` operator, which
  only ever handles exactly two columns and never drops anything.
- ✅ **Split column**
  (`POST /dataset-tables/{id}/split-column`): splits one text column by
  a literal delimiter into as many columns as the row with the most
  delimiter occurrences actually needs — a real, data-dependent count,
  not a fixed number. Rows with fewer parts get null in the extra
  columns rather than the operation failing. If explicit
  `new_column_names` are given, their count must exactly match that
  data-dependent number — tested, including the exact-mismatch error
  message reporting the real count.
- ✅ **Frontend**: all three added to the "Clean this data" panel —
  merge-columns uses checkboxes (not a dropdown) since it takes
  multiple columns; split-column takes an optional comma-separated
  names field; standardize-column's date-format picker only appears
  when "date" is selected. Verified live in the browser against a real
  uploaded CSV: standardize-column turned a `date_stored_as_text`
  column into a real `date`-typed column (quality score rose to
  100/100), and split-column turned a "full name" column into
  separately-named `first_name`/`last_name` columns with the original
  dropped — both confirmed via the live profile table, not just the API
  response.
- ✅ Automated backend tests: 200/200 passing (14 new, in
  `tests/test_more_cleaning_operations.py`).

## Post-Phase-7: S3Storage verification against a mocked S3 API

`S3Storage` (`app/services/storage.py`) was flagged since Phase 2 as
"written but not exercised." This round raised that bar — not all the
way to a real bucket, but further than mocking boto3 directly would
have:

- ✅ `tests/test_s3_storage.py` (7 tests) runs the real `S3Storage` class
  — real boto3 client, real request signing — against
  [moto](https://github.com/getmoto/moto)'s mocked S3 backend, which
  implements the actual S3 API/XML semantics rather than stubbing this
  app's own code. Covers bucket auto-creation, write, read,
  read-of-a-missing-key (raises `StorageError`), delete,
  delete-then-read, and overwrite.
- ✅ **A real bug caught by this, not by inspection**: bucket
  auto-creation called `create_bucket(Bucket=...)` with no
  `CreateBucketConfiguration`. Real AWS S3 rejects that for every region
  except `us-east-1` — and this app's own default `S3_REGION` is
  `eu-west-2`. First-run bucket creation against a real AWS bucket in
  the app's own default configuration would have failed outright. Fixed
  by conditionally setting `CreateBucketConfiguration.LocationConstraint`
  for any non-`us-east-1` region. Verified the fix actually matters by
  reverting it and confirming 6 of the 7 tests fail with the exact AWS
  error (`IllegalLocationConstraintException`) a real deployment would
  have hit.
- ⬜ **Still not run against MinIO or a real AWS/R2 bucket.** moto
  emulates AWS's own documented behavior, not any specific
  S3-compatible service's — and MinIO is known to be lenient about
  exactly the kind of region strictness the bug above depended on,
  which is plausibly why a MinIO-only test pass would have missed it
  entirely. This is a genuine step up in rigor, not a substitute for
  running it against MinIO per docs/DEPLOYMENT.md.

## Post-Phase-7: conversation history replay fidelity

Phase 3 flagged this as a known simplification: a multi-turn AI analyst
conversation replayed earlier turns to the model as flattened plain
text, dropping the original tool_use/tool_result block structure.
Fixed and originally verified the same way the rest of the AI planner
always had been — a scripted fake client, checking the exact message
structure sent on a second turn, not just the response shape — since no
`LLM_API_KEY` was configured at the time. Since confirmed against a
real model too: see Phase 3's updated section above, where a real
second-turn question ("What percentage of that total does Acme Ltd
account for?") correctly used the first turn's replayed
`tool_use`/`tool_result` blocks to answer without needing to re-run
`descriptive_stats`.

- ✅ `PlannerResult` (`app/services/ai/planner.py`) now returns
  `message_delta`: the exact sequence of Anthropic-API-shaped messages
  one turn produced — the user question, one `{assistant, user(tool_result)}`
  pair per tool-calling iteration, and a closing assistant message.
  `run_conversation_turn` always closes a turn on an assistant-role
  message now, including the no-tool-use and iteration-limit paths
  (previously the no-tool-use path didn't append anything further, and
  the iteration-limit path ended on a tool_result) — without that, the
  *next* turn's user message would follow directly after another
  user-role message, which Anthropic's API rejects outright (two
  consecutive same-role messages).
- ✅ `AIMessage` gained a `replay_messages` JSON column (migration
  `4eb5f6f2794d`) storing that delta on the assistant row for each turn.
  `tool_calls` and `content` are unchanged and still drive the API
  response/display — `replay_messages` is purely for reconstructing
  history server-side, never exposed via `AIMessageOut`.
- ✅ `_history_to_anthropic_messages` (`app/api/v1/routers/ai_analyst.py`)
  rewritten to use each turn's `replay_messages` when present, falling
  back to the old flattened `{role, content}` pair for any row
  persisted before this column existed (graceful degradation, not a
  hard requirement that every row have it).
- ✅ Automated tests: 4 new in `tests/test_ai_planner.py` (message_delta
  shape for the text-only, tool-use, and iteration-limit paths, plus one
  that feeds turn 1's `message_delta` back in as turn 2's `history` and
  asserts the second scripted client actually received the first turn's
  real `tool_use`/`tool_result` blocks — not their text description) and
  1 new in `tests/test_ai_analyst_api.py` (the same proof through the
  real `/ask` endpoint and real database persistence, not just in
  memory).
- ✅ **A real bug caught while writing these tests, in the test
  infrastructure itself**: `ScriptedLLMClient`/`_ScriptedClient` recorded
  `messages` as a live reference, not a copy — since `planner.py` keeps
  appending to that same list after the call returns, a recorded call's
  "what was sent" would silently change after the fact once a test
  inspected it later. Fixed by storing `list(messages)` at record time.
  This had already been in the codebase since Phase 3 without being
  caught, because no earlier test happened to inspect a `.calls` entry
  after a later mutation — exactly the kind of latent bug that a new
  cross-turn test was likely to surface.

## Post-Phase-7: second specialist report template

Phase 5 built exactly one of the brief's 12 described report templates
(Commercial Property Portfolio) to prove the KPI-engine-plus-PDF-layout
pattern end-to-end. This round built the second, for the
`residential_property` pack — whose `report_templates` tuple in
`app/core/industry_packs.py` had been empty since Phase 5.

- ✅ **Residential Property Portfolio Report**
  (`POST /dataset-tables/{id}/reports/residential-property-portfolio`,
  `generate_residential_property_report_pdf` in `app/services/reports.py`):
  built from the exact same `compute_kpis` call the `/industry-kpis`
  endpoint uses, so the two can never disagree — same guarantee as the
  commercial property report. All 7 of the pack's existing KPIs were
  already calculable (every residential KPI id reuses a calculator
  already registered for commercial property in
  `app/services/industry_kpis.py` — no new calculation code needed),
  so this report was purely a template-writing exercise, exactly as the
  Phase 5 note predicted.
- ✅ **Two sections genuinely specific to residential**, not a
  copy-paste of the commercial report: "Tenancies ending within 12
  months" (same date-window logic as commercial's lease-expiry
  section, renamed) and "Properties in arrears" (sorted by amount
  owed — new, since the residential pack has no category field to
  build commercial's rent-by-category breakdown from, but does have
  arrears data worth surfacing on its own).
- ✅ Rejects generation for any workspace industry other than
  `residential_property` — including `commercial_property`
  specifically, not just "some other industry" (tested as its own
  case, since a copy-pasted check could plausibly accept the wrong
  pack by mistake).
- ✅ **Verified by reading the actual rendered PDF output**, not just
  checking the file is non-empty: generated a report from a 4-row
  sample dataset with a temporarily-installed PDF text extractor
  (removed again afterward — not a project dependency), and confirmed
  every figure against hand-computed values — total rent roll
  (£2,900.00), average rent, occupancy/vacancy rate, arrears, the one
  correctly-included tenancy expiring within 12 months (and the two
  correctly excluded — one already past its end date, one too far in
  the future), and the one property correctly listed in arrears.
- ✅ **Frontend**: the existing `IndustryKpiPanel`'s "Download portfolio
  report" button, previously hardcoded to the commercial-property
  endpoint, now branches by workspace industry. Verified live in the
  browser: uploaded a residential rent roll, clicked the button, and
  confirmed both the real `POST .../residential-property-portfolio`
  (201) and the real `GET /reports/{id}/download` (200) calls through
  the browser's own network panel — not just that the API test passes.
- ✅ Automated backend tests: 204/204 passing (4 new, in
  `tests/test_industry_reports.py`).

## Post-Phase-7: industry field mapping confirmation

The last-remaining honesty gap Phase 5 itself flagged: "there's no UI
yet to let a user review and correct the automatic mapping before KPIs
are computed." Closed by extending Phase 2's schema-confirmation
pattern (confirm column types once reviewed) to industry field mapping.

- ✅ **`DatasetTable.confirmed_field_mapping`** (migration
  `743212b50087`): a new nullable JSON column, same shape as the
  existing `confirmed_schema`. `get_effective_field_mapping()`
  (`app/services/industry_matching.py`) is the one function every
  caller now goes through — it returns the confirmed mapping when one
  exists, falling back to the automatic alias/token matching
  (`resolve_field_mapping`) otherwise. All 6 call sites that used to
  call `resolve_field_mapping` directly (`/industry-kpis`, `/scenario`,
  both specialist PDF reports, the scheduled-report generator, and KPI
  dashboard widgets) now go through it — so confirming a mapping once
  changes every one of those consistently, not just a subset.
- ✅ **`GET /dataset-tables/{id}/field-mapping`**: the effective mapping
  (confirmed or automatic), each canonical field's description and
  required-for-pack flag, which columns are actually available on this
  table, and `is_confirmed` so the frontend can show "automatic guess"
  vs. "confirmed."
- ✅ **`PATCH /dataset-tables/{id}/field-mapping`**: saves a full
  replacement mapping (not a merge into the automatic guess — any
  canonical field the caller doesn't mention goes back to unmapped,
  same "this is complete, stop guessing" semantics as
  `confirmed_schema`). Validates every submitted canonical field is one
  the pack actually defines, and every submitted column name actually
  exists on the table. Write access required (same as schema
  confirmation); reading the mapping only needs read access.
- ✅ **A confirmed mapping is carried forward across cleaning
  operations** (same as `confirmed_schema` already was) via
  `_apply_table_transformation` — confirming a mapping once doesn't get
  silently lost the next time the data is cleaned. Tested explicitly:
  confirm a mapping, deduplicate, confirm the new version's mapping is
  still there.
- ✅ **Real end-to-end proof, not just a round-trip check**: a test
  uploads a CSV with a rent column named "Amount Due Monthly" —
  deliberately chosen because it doesn't match any of
  `rent_amount`'s known aliases, so the automatic matcher leaves it
  unmapped and `total_rent_roll` genuinely errors. Confirming
  `rent_amount → "Amount Due Monthly"` makes that same KPI compute
  correctly afterward — proving the confirmed mapping actually changes
  what `/industry-kpis` returns, not just what the mapping endpoint
  reports back.
- ✅ **Frontend**: a "Review field mapping" panel in the industry KPI
  section of the workspace page — one dropdown per canonical field,
  pre-filled from the effective mapping, required fields marked with
  `*`, a header that reads "(automatic guess — not yet confirmed)" or
  "(confirmed)". Verified live in the browser with the exact
  mismatched-column scenario above: KPIs showed "Not available" for
  rent-derived metrics before confirming, the dropdown correctly
  pre-filled every other field from the automatic match, and after
  mapping the ambiguous column and saving, recomputing KPIs showed
  real figures (Total Rent Roll £2,150.00) — not a simulated result,
  the actual `/industry-kpis` response.
- ✅ Automated backend tests: 212/212 passing (8 new, in
  `tests/test_field_mapping.py`).

## Post-Phase-7: pivot and unpivot

The last two of the brief's originally-named cleaning operations.
Initially scoped out (see the Phase 2 section above, pre-edit) as a
"bigger design question" than the other operations because the
resulting column *count* is data-dependent rather than fixed — on
reflection, that's the same kind of problem split-column already
solved (its resulting column count is also data-dependent, validated
against the real count rather than assumed), so the concern didn't
hold up as a reason to scope it out entirely.

- ✅ **Pivot** (`POST /dataset-tables/{id}/pivot`): long-to-wide
  reshape — one row per distinct combination of `index_columns`, one
  new column per distinct value in `pivot_column`, populated by
  aggregating `value_column`. Unlike every other cleaning operation,
  this **replaces the table's column set entirely** rather than adding
  to or filtering it (any column not named in `index_columns`,
  `pivot_column`, or `value_column` is dropped) — inherent to what
  "pivot" means, not a limitation of the implementation, and documented
  as such in `apply_pivot`'s own docstring.
  - An `aggregate_function` (default `sum`; also mean/min/max/first/
    last/median/len) is always required rather than letting polars
    raise when two source rows share the same index+pivot-value
    combination — real spreadsheet data routinely has duplicates (two
    expense rows in the same month/category), and erroring on that
    would make pivot unusable for exactly the messy-data case it needs
    to handle.
  - A hard cap (50 distinct pivot values) guards against an
    unreasonable column explosion from a high-cardinality pivot column
    — tested explicitly with 51 distinct values, asserting the clean
    400 rather than a slow/huge response.
  - A pivoted value that happens to equal an index column's name (e.g.
    a category literally called "date") is a genuine naming collision
    — polars itself rejects it, surfaced as a clean 400 via the same
    generic `except Exception` wrapper every other cleaning operation
    uses, not a 500.
- ✅ **Unpivot** (`POST /dataset-tables/{id}/unpivot`): wide-to-long
  reshape — for each row, one output row per column named in
  `value_columns`, carrying that column's name (`variable_name`) and
  value (`value_name`) alongside the unchanged `id_columns`. Simpler
  than pivot: the resulting column count is always fixed
  (`len(id_columns) + 2`), only the row count grows.
- ✅ **Verified as a real round-trip in the browser, not just two
  isolated operations**: uploaded a long-format dataset (date,
  category, amount with a duplicate index+category combination),
  pivoted it to wide (date, rent, fees — confirming the aggregate
  summed the duplicate correctly), then unpivoted that *result* back to
  long (date, variable, value) — each step producing a new version with
  the data quality profile correctly recomputed for the new shape, not
  stale from before.
- ✅ Automated backend tests: 224/224 passing (12 new, in
  `tests/test_pivot_unpivot.py`).
- ✅ **Frontend**: both added to the "Clean this data" panel — pivot
  uses checkboxes for `index_columns` (multiple) plus dropdowns for
  `pivot_column`/`value_column`/`aggregate_function`; unpivot uses
  checkboxes for both `id_columns` and `value_columns` plus text inputs
  for the two new column names.
- ✅ 10 cleaning operations existed after this round (deduplicate,
  fill-missing-values, normalize-text, filter-rows, calculated-field,
  standardize-column, merge-columns, split-column, pivot, unpivot).
  Group-by still only existed as a read-only analytics tool
  (`group_aggregate`, Phase 3) at this point — closed in the next
  round, see "Post-Phase-7: persisted group-by" below.

## Post-Phase-7: persisted group-by

The last cleaning operation named in the brief's "filter/group"
pairing — filter-rows was built earlier; group-by only existed as the
read-only `group_aggregate` analytics tool (Phase 3), which returns a
query result, never a new dataset version.

- ✅ **Group-by** (`POST /dataset-tables/{id}/group-by`): one row per
  distinct combination of `group_by_columns` (one or more), with one or
  more named aggregate columns per request
  (`{column, function, output_name}`, function one of sum/mean/min/max/
  median/count). Like pivot, this replaces the table's column set
  entirely (group_by_columns plus the aggregate columns) rather than
  extending or filtering it — inherent to what grouping means, the same
  reasoning documented for pivot.
  - Supports **multiple aggregations in one call** (e.g. both
    `sum(amount) as total_amount` and `count() as row_count` in the
    same request) — genuinely more capable than the read-only
    `group_aggregate` tool it complements, which only ever computes one
    aggregation at a time.
  - `count` is the one function that doesn't take a `column` (it counts
    rows per group); every other function requires one and rejects a
    non-numeric column for sum/mean/median, mirroring
    fill-missing-values' same numeric-only guard for those functions.
  - An `output_name` colliding with a `group_by_column` (or with
    another aggregation's `output_name`) is rejected with a clear
    error, same "catch the naming collision before any write happens"
    pattern as every other `_apply_table_transformation`-based
    operation.
- ✅ **Frontend**: added to the "Clean this data" panel — checkboxes for
  `group_by_columns`, one aggregation row (function + column + output
  name; the API supports more than one aggregation, the UI scopes to
  one for simplicity). Verified live in the browser: grouped a 5-row
  dataset (category, amount, region) by `category` with
  `sum(amount) as total_amount`, producing the correct 2-row result
  (rent: 2200, fees: 180 — matching the sum of the source rows by
  hand).
- ✅ Automated backend tests: 233/233 passing (9 new, in
  `tests/test_group_by.py`).
- ✅ **This closes the brief's entire Phase 2 cleaning-operations gap
  list.** 11 operations now exist via `_apply_table_transformation`
  (deduplicate, fill-missing-values, normalize-text, filter-rows,
  calculated-field, standardize-column, merge-columns, split-column,
  pivot, unpivot, group-by) — every operation the brief named, including
  both halves of "filter/group." Compare-datasets is covered separately
  by Phase 6's version comparison.

## Post-Phase-7: third specialist report template (social housing)

The third specialist report template, for the `social_housing` pack —
whose `report_templates` tuple in `app/core/industry_packs.py` had been
empty since Phase 5, same as residential property's was before its
report was built.

- ✅ **Social Housing Asset Report**
  (`POST /dataset-tables/{id}/reports/social-housing-asset`,
  `generate_social_housing_report_pdf` in `app/services/reports.py`):
  built from the same `compute_kpis` call `/industry-kpis` uses, same
  guarantee as the other two reports. Zero new calculation code was
  needed — every social-housing KPI already had a registered calculator
  since Phase 5.
- ✅ **The first PDF report to render a compliance caveat.** The
  social_housing pack's brief-required disclaimer ("do NOT constitute
  legal compliance certification...") has been shown in the
  `/industry-kpis` API response and the dashboard UI since Phase 5, but
  never in PDF form until this report — rendered prominently right
  after the title/metadata, in a highlighted box, not buried in a
  footnote, since it qualifies every figure that follows it.
- ✅ **Two sections specific to this pack**: "Properties overdue
  inspection (>12 months)" (reuses the same date-window logic pattern
  as the commercial report's lease-expiry section, inverted — properties
  whose last inspection is *older* than the cutoff rather than newer
  than it — sorted most-overdue first) and "EPC rating distribution"
  (reuses the existing `group_aggregate` analytics tool in count mode,
  the same function the commercial report's rent-by-category breakdown
  uses in sum mode — first reuse of that tool from inside a PDF report
  generator for a different aggregation).
- ✅ **Verified by reading the actual rendered PDF text**, not just
  checking the file is non-empty: generated a report from a 3-property
  sample dataset with a temporarily-installed PDF text extractor
  (removed again afterward, not a project dependency) and confirmed
  every figure — total properties, 2 correctly-identified overdue
  inspections (and the one correctly excluded, inspected one month
  ago), total/average repair cost, void rate, and the 3-way EPC
  distribution — against hand-computed values, and confirmed the
  compliance caveat text renders verbatim and appears before the key
  metrics table.
- ✅ **Frontend**: the existing "Download portfolio report" button
  (already branching between commercial and residential) now also
  covers social housing. Verified live in the browser: uploaded a
  social-housing stock list, clicked the button, and confirmed both the
  real `POST .../social-housing-asset` (201) and the real
  `GET /reports/{id}/download` (200) calls through the browser's own
  network panel.
- ✅ Automated backend tests: 236/236 passing (3 new, in
  `tests/test_industry_reports.py`).

## Post-Phase-7: fourth specialist report template (business finance)

The fourth and (for now) last specialist report template, for the
`business_finance` pack — whose `report_templates` tuple had been
empty since Phase 5. This completes report coverage for every industry
pack the brief's Phase 5 "Create" list named (commercial property,
residential property, social housing, business finance).

- ✅ **Business Performance Report**
  (`POST /dataset-tables/{id}/reports/business-performance`,
  `generate_business_finance_report_pdf` in `app/services/reports.py`):
  built from the same `compute_kpis` call `/industry-kpis` uses, same
  guarantee as the other three reports. Zero new calculation code
  needed.
- ✅ **First report with a month-by-month trend section**, reusing
  `time_trend` from the Phase 3 analytics engine rather than writing new
  trend logic — the same function `/analyze` already exposes directly,
  now also driving a report section. Wrapped in a try/except for
  `AnalyticsError` (raised when fewer than 2 dates parse) so a dataset
  too sparse to trend still produces a report, just without that
  section's data, rather than failing the whole generation.
- ✅ **First report with a "top N" ranked section** (top 5 customers by
  revenue) — reuses `group_aggregate`'s existing descending sort rather
  than adding new ranking logic, just takes the first 5 of an
  already-sorted list.
- ✅ **Two independent category breakdowns from the same `category`
  column** (revenue by category, expenses by category) — each a
  separate `group_aggregate` call with a different `value_column`,
  demonstrating the same grouping column can drive more than one
  section when the pack has more than one numeric field worth breaking
  down by it.
- ✅ **Verified by reading the actual rendered PDF text**, not just
  checking the file is non-empty: generated a report from a 4-row
  sample dataset (2 months, 2 categories, 3 customers) with a
  temporarily-installed PDF text extractor (removed again afterward)
  and confirmed every figure — total revenue/expenses/net profit/profit
  margin, the monthly trend (two equal months, a coincidence of the
  sample data, not a bug), both category breakdowns, and all three
  customers correctly ranked by revenue — against hand-computed values.
- ✅ **Frontend**: the "Download portfolio report" button's per-industry
  branching was refactored from a growing nested ternary into a lookup
  map (`industry -> generator function`) now that it covers all four
  packs — clearer than a fourth nested ternary branch would have been.
  Verified live in the browser: uploaded a business-finance transaction
  list, clicked the button, and confirmed both the real
  `POST .../business-performance` (201) and the real
  `GET /reports/{id}/download` (200) calls through the browser's own
  network panel.
- ✅ Automated backend tests: 239/239 passing (3 new, in
  `tests/test_industry_reports.py`).

## Post-Phase-7: scheduled report email delivery

Closes the gap flagged since Phase 6: scheduled reports generated and
stored a PDF but never emailed it anywhere. Now that
`app/services/email.py` exists (Phase 7.1), this wires the two together.

- ✅ **Attachment support in the email layer first**
  (`EmailAttachment`/`EmailMessage.attachments`,
  `apps/api/app/services/email.py`): `SMTPEmailSender.send()` now wraps
  the text/html body in an outer `multipart/mixed` envelope with
  `MIMEApplication` parts when attachments are present. Attaching the
  PDF directly (not linking to it) is deliberate — this app has no
  unauthenticated download route, and building a magic-token scheme just
  for this one email would be disproportionate.
- ✅ **`ScheduledReport.last_email_sent_at` / `last_email_error`**
  (migration `fa7defa9369e`): tracked separately from
  `last_run_at`/`last_error`, which mean "generation succeeded/failed."
  Delivery is a separate concern — a report can generate successfully
  and still fail to send (SMTP outage, bad address), and that must not
  look like the schedule itself is broken. Modeled on
  `WebhookSubscription.last_delivery_error`'s existing record-don't-crash
  pattern.
- ✅ **All specialist reports are schedulable** (six now — a fifth and
  sixth, `social_housing_compliance_exceptions` and
  `residential_repairs_maintenance`, were added later and slotted into
  this same mapping with no changes needed here, see "Post-Phase-7:
  fifth specialist report template" and "Post-Phase-7: sixth specialist
  report template" below — four at the time this was built, not just
  `data_quality` and `commercial_property_portfolio`).
  `REPORT_TYPE_REQUIRED_INDUSTRY` (`app/services/scheduled_reports.py`)
  is the one source of truth for which report type needs which industry
  pack, used both by `_generate_report_bytes` (enforced every run, in
  case a workspace's industry changed after the schedule was created)
  and the router's create-time validation — previously only
  `commercial_property_portfolio` was checked at creation time; the
  other three could be scheduled against the wrong industry and would
  only fail at run time.
- ✅ **`run_due_scheduled_reports(..., email_sender: EmailSender | None)`**:
  after a report generates successfully, if an `email_sender` was
  passed, it emails the schedule's creator with the PDF attached. A send
  failure is caught, recorded in `last_email_error`, and does **not**
  roll back the already-generated and already-stored report, touch
  `last_error`, or stop the loop processing other due schedules.
  `app/main.py`'s scheduler tick resolves a real `EmailSender` via
  `get_email_sender()` each run (catching `EmailNotConfiguredError` ->
  `None`, same honest-gating pattern as everywhere else SMTP isn't
  configured), so this activates automatically once `SMTP_HOST` is set —
  no separate feature flag.
- ✅ Automated tests (`tests/test_scheduled_reports.py`, 11 new, 245/245
  passing project-wide): successful generation-and-send with the PDF
  attached and correct recipient; a send failure recorded in
  `last_email_error` without undoing the generated report or touching
  `last_error`; omitting `email_sender` entirely still works exactly as
  before (regression guard); each of the three newly-schedulable report
  types generating correctly through the scheduler; all three newly
  added report types rejected at creation time for a mismatched
  workspace industry.
- ✅ **Live end-to-end verification**: ran the real API server with
  `SMTP_HOST` pointed at a small hand-rolled local SMTP listener
  (Python's stdlib `smtpd` module was removed in 3.12, so this was a
  ~70-line raw-socket script implementing just enough of the protocol —
  EHLO/MAIL FROM/RCPT TO/DATA/QUIT — to accept one real `smtplib`
  connection). Registered a real user, uploaded a real dataset, created
  a real scheduled report via the API, forced it due, and invoked the
  real scheduler tick function with a real `SMTPEmailSender`. The
  listener received an actual multipart MIME message over a real TCP
  socket; parsing it with Python's own `email` module confirmed a
  `data_quality.pdf` attachment starting with `%PDF-1.4`, exactly
  matching the generated report's byte size (2643 bytes). This is the
  same mocked-vs-real split used throughout this project: automated
  tests mock `smtplib.SMTP` to verify the integration code path on every
  run; this one-off live pass is the first time in this project a
  message produced by `SMTPEmailSender` was actually sent over a socket
  and received — SMTP itself was exercised for real, even though the
  recipient is this ad-hoc script rather than a production mail
  provider (Postmark/SendGrid/SES/Gmail), which still has never been
  confirmed and remains the honest caveat in
  `app/services/email.py`'s docstring.
- ~~No scheduled-reports UI exists in `apps/web`~~ — done, see
  "Post-Phase-7: scheduled reports frontend" below.

## Post-Phase-7: scheduled reports frontend

Closes the gap flagged immediately above: the scheduled-report-email
feature was API-only, with nothing in `apps/web` to create, list, or
delete a schedule, or to see whether its last email actually sent.

- ✅ **`ScheduledReportsPanel`** (`apps/web/src/app/dashboard/workspaces/
  [id]/page.tsx`), one per dataset table, following the same
  open/closed toggle-panel pattern as `FieldMappingReview` right next to
  it. Lists the schedules that target this specific table (filtered
  client-side from the workspace-level `GET
  /workspaces/{id}/scheduled-reports` — the API has no per-table list
  endpoint, and adding one for a single frontend panel wasn't
  justified), shows next-run time, last generation result, and last
  email result, and has a small form to create a new schedule and a
  remove button on each row.
- ✅ **Report-type choices are industry-gated**, mirroring the backend's
  `REPORT_TYPE_REQUIRED_INDUSTRY`: a `data_quality` schedule is always
  offered; the matching specialist report (e.g. Commercial Property
  Portfolio) is only offered when the workspace's industry matches —
  the same gating the backend enforces, so the form can't offer a
  choice the API would reject.
- ✅ **Delivery status surfaced directly, not just generation status**:
  a schedule row shows "Last emailed {time}" in green when
  `last_email_sent_at` is set and `last_email_error` is clear, or the
  error in red otherwise — distinguishing "this schedule works but the
  last email bounced" from "this schedule hasn't generated successfully
  at all," the same distinction the backend's two separate field-pairs
  were built to make.
- ✅ **`api.ts`** gained a `ScheduledReport` type and
  `listScheduledReports`/`createScheduledReport`/`deleteScheduledReport`,
  following the exact call shape every other endpoint wrapper in the
  file already uses.
- ✅ Verified live in the browser against the real API, not just typed:
  registered a user, created a `commercial_property` workspace, uploaded
  a dataset, opened the panel (empty state correct), created a
  "Commercial Property Portfolio · weekly" schedule and confirmed both
  the real `POST` (201) and the list refresh in the network panel, then
  removed it and confirmed the real `DELETE` (204) and — independently,
  via a direct API call, not just trusting the UI — that the workspace's
  schedule list was actually empty afterward. `npx tsc --noEmit` also
  passes with zero errors.
- ✅⚠️ A first real frontend test suite now exists — see "Post-Phase-7:
  first frontend test suite" below. This feature itself (the scheduled
  reports panel) still has no dedicated test, just like every other
  page component; the gap closed is "the `vitest run` script runs real
  tests" at all, not "every page has coverage."

## Post-Phase-7: distributed scheduler lock

Closes the gap flagged since Phase 6: running more than one API replica
would have had each replica's in-process APScheduler job fire every due
scheduled report independently — generating (and, now that delivery
exists, emailing) the same report once per replica rather than once
total.

- ✅ **`SchedulerLock`** (`app/models/scheduler_lock.py`, migration
  `d4fa7086e3e4`): a tiny single-table lease lock — `id`, `locked_until`,
  `locked_by` — not tied to scheduled reports specifically, so any
  future recurring job this app adds can reuse it by picking its own
  `lock_id`.
- ✅ **`app/services/distributed_lock.py`**: `try_acquire_lock`/
  `release_lock`, implemented as a single conditional `UPDATE`
  (`WHERE id=:id AND (locked_until IS NULL OR locked_until < :now)`),
  not a `SELECT` followed by an `UPDATE` — the database itself
  serializes the row-level write, so the pattern is atomic under real
  concurrent transactions from separate processes, not just safe against
  interleaved coroutines in one process. This holds under both SQLite
  (dev/tests) and Postgres (staging/prod), which is why the tests
  exercise the exact code path production runs rather than mocking
  locking out. Lease-based (`DEFAULT_LEASE_SECONDS = 240`, shorter than
  the 5-minute tick interval): a replica that crashes mid-tick without
  releasing doesn't lock every other replica out forever.
- ✅ **A real bug, caught and fixed before any test exercised it**: the
  first draft of `release_lock` unconditionally cleared the lock row.
  Tracing through a caller whose `try_acquire_lock` *failed* and then
  (incorrectly) called `release_lock` anyway showed it would silently
  wipe out whichever other replica legitimately held the lease —
  the exact failure mode this feature exists to prevent, self-inflicted
  by careless cleanup code. Fixed by having `try_acquire_lock` return a
  per-acquisition holder token and `release_lock` only clear the row
  when `locked_by` still matches that token — a release from a caller
  that never truly held the lock, or whose lease already expired and
  was reacquired by someone else, is now a safe no-op. Covered by
  `test_release_with_stale_holder_token_does_not_clobber_the_new_holder`
  in `tests/test_distributed_lock.py`.
- ✅ **`run_due_scheduled_reports` acquires the lock first** and skips
  the entire tick (returns `[]`, touches no `ScheduledReport` row at
  all) if another holder has a live lease — rather than, say, acquiring
  per-schedule, which would let two replicas each process *different*
  due schedules in the same tick and only protect against the narrower
  case of both processing the *same* one. The whole tick is one unit of
  work.
- ✅ Automated tests: 7 new (5 in `tests/test_distributed_lock.py`
  covering the lock primitive standalone — blocked-while-live,
  recovers-after-expiry, release-allows-reacquire, the stale-holder
  case above, and independent lock ids; 2 integration tests in
  `tests/test_scheduled_reports.py` proving `run_due_scheduled_reports`
  itself skips cleanly when locked and releases properly afterward).
  252/252 passing project-wide.
- ✅ **Live concurrency proof, not just sequential test assertions**: a
  one-off script created a real due `ScheduledReport` via the real API
  against a real on-disk SQLite file (not the tests' in-memory
  per-test database), then launched two independent SQLAlchemy
  engines/sessions — standing in for two separate API processes, not
  two coroutines sharing one connection — and raced them against the
  same due report with `asyncio.gather`. Exactly one generated a report
  (confirmed by both the function's own return value and, independently,
  by counting `Report` rows in the database afterward); the other
  returned `[]` having touched nothing. This is the one place in this
  round where only a real concurrent race, not a unit test, could prove
  the claim — a sequential test calling the function twice in a row
  can't distinguish "the lock works" from "nothing happened to race
  with yet."

## Post-Phase-7: auth endpoint rate limiting

Closes a gap flagged since the first version of this checklist: none of
the authentication endpoints had any request throttling, leaving
`/auth/login` open to unbounded password-guessing and
`/auth/register`/`/auth/forgot-password`/`/auth/resend-verification`
open to spam or email-bombing.

- ✅ **`RateLimitWindow`** (`app/models/rate_limit.py`, migration
  `7e67f32d568b`): a single table (`bucket_key`, `window_start`,
  `count`) serving every rate-limited endpoint — each endpoint just
  picks its own `bucket_key` prefix — rather than one table per
  endpoint.
- ✅ **`app/services/rate_limit.py`**: fixed-window counting, backed by
  the same database as everything else in this app — not Redis.
  `redis_url` exists in `app/core/config.py`, but nothing in this
  codebase actually connects to a real Redis instance (its own comment
  points at an `app/services/queue.py` that was never built), and a
  security-relevant feature like this shouldn't depend on unconfirmed
  infrastructure. `check_rate_limit` reuses the exact atomic
  conditional-UPDATE-then-insert-with-IntegrityError-fallback idiom
  proven correct for `app/services/distributed_lock.py` immediately
  above, rather than a plain `SELECT` then write — the scenario being
  defended against (many near-simultaneous requests from one client) is
  exactly the scenario a read-then-write race would fail under, so this
  one specifically needed to be concurrency-safe, not just "probably
  fine."
- ✅ **Wired onto 6 of the 7 auth endpoints** via a
  `rate_limit_dependency(bucket_prefix, max_requests, window_seconds)`
  factory in `app/api/deps.py`, keyed per client IP:
  `/register` and `/verify-email`/`/reset-password` at 10/hour,
  `/login` at 10/5 minutes, `/resend-verification` and
  `/forgot-password` (the two email-bombing-prone ones) at 5/hour.
  `/refresh` is deliberately exempt — it already requires a valid
  refresh token to reach, which is a stronger gate than an IP-based
  limit would add.
- ✅ **Limits sized against this project's own test suite, not
  guessed**: before picking numbers, checked how many times any single
  existing test function calls `/register` or `/login` in a row (the
  worst case across 250+ tests was 4) and chose limits comfortably
  above that — confirmed afterward by the full suite still passing
  unmodified (`259/259`) with rate limiting now live on every test's
  auth calls, not just the new tests for this feature.
- ✅ **A periodic cleanup job** (`app/main.py`,
  `_purge_expired_rate_limit_windows_tick`, hourly) deletes window rows
  older than 6 hours, via `purge_expired_windows`, so the table doesn't
  grow forever — an expired window is already inert (never matched by
  `check_rate_limit`'s query again) the moment it ends, so this is
  purely housekeeping, not a correctness requirement.
- ✅ Automated tests (`tests/test_rate_limit.py`, 7 new): the counting
  primitive itself (within-limit allowed, over-limit rejected, a new
  window resets the count, independent bucket keys don't interfere,
  cleanup only removes rows past the cutoff), plus two integration
  tests hitting the real `/auth/login` endpoint through the full HTTP
  stack — one proving the 11th rapid login attempt gets a real 429, one
  proving all 10 within the limit get a real 200.
- ✅ **Live verification against a real running server**: registered a
  real user, then fired 12 rapid real HTTP login requests at a real
  uvicorn process. Attempts 1-10 returned `200`, attempts 11-12
  returned `429` with the exact configured message — and, independently
  of the endpoint's behavior, queried the database afterward and found
  the `auth_login` bucket's row with `count=13` (12 attempts plus one
  extra check), confirming the counting itself, not just the HTTP
  response, matched what actually happened. Also confirmed a
  completely unrelated bucket (`auth_register`, hit by a second,
  different registration in the same session) was unaffected — hitting
  one endpoint's limit doesn't throttle a different endpoint.
- ⬜ Keyed on `request.client.host` directly — this app isn't behind a
  reverse proxy that sets a trustworthy `X-Forwarded-For` in this
  environment, so there's nothing to prefer over the direct connection
  address yet. Behind a real load balancer/proxy in production, every
  request would arrive from the proxy's own IP, collapsing every real
  client into one shared bucket — that translation (reading a trusted
  proxy header instead) would need to be added at that point, not
  before it's actually true.

## Post-Phase-7: httpOnly cookie refresh + CSRF protection

Closes the "Token storage" known limitation that had been flagged since
the first version of this checklist: the frontend kept the JWT in
`localStorage`, readable by any script that managed to run on the
page — the classic XSS-to-token-theft path. This was explicitly asked
for by name, and reviewed for scope before starting given how
cross-cutting an auth change like this is.

- ✅ **Minimal-blast-radius design, deliberately.** Only the refresh
  token moved: it's now an httpOnly cookie, never read or written by
  any frontend code. The access token the frontend uses for every
  other request is still sent as a plain `Authorization: Bearer`
  header exactly as before — now held only in memory (React state),
  never persisted to any browser storage. This meant
  `app/api/deps.py`'s `get_current_user` — the dependency every one of
  this app's 70+ other endpoints relies on — needed **zero changes**;
  only `/login`, `/refresh`, and a new `/logout` touch cookies at all.
- ✅ **`app/core/cookies.py`**: `set_auth_cookies`/`clear_auth_cookies`.
  Two cookies, not one — `refresh_token` (httpOnly, `Secure` gated on
  `environment == "production"` the same way `app/services/storage.py`
  already gates S3-vs-local-disk, `SameSite=Lax`) and `csrf_token`
  (deliberately **not** httpOnly, so frontend JS can read it back for
  the double-submit CSRF pattern below — its secrecy from the page
  itself was never the point, only an attacker's *cross-site* page
  being unable to read it is).
- ✅ **CSRF protection scoped to exactly where it's needed, not applied
  broadly.** `/auth/refresh` is the one endpoint a browser client
  authenticates purely via an ambient cookie, with no explicit
  credential a forged cross-site request couldn't also trigger —
  that's precisely the scenario CSRF protection defends against, and
  the *only* scenario it's needed for here, since every other endpoint
  still requires an explicit `Authorization` header a forged request
  can't produce. `/refresh` now requires a matching `X-CSRF-Token`
  header whenever it's relying on the cookie (not when a token is
  passed explicitly in the body — see next bullet) — checked by
  comparing it to the `csrf_token` cookie value, the standard
  double-submit pattern.
- ✅ **Fully backward compatible for non-browser callers.**
  `RefreshRequest.refresh_token` became optional rather than being
  replaced: a script, a mobile app, or this project's own test suite
  can still POST `{"refresh_token": "..."}` exactly as before and skip
  the cookie/CSRF path entirely (that's an explicit bearer-style
  submission, not an ambient-credential one, so CSRF doesn't apply to
  it). `/login` still returns `refresh_token` in the response body too,
  for the same reason. Proven, not just claimed: all 8 pre-existing
  `tests/test_auth.py` tests pass completely unmodified.
- ✅ **A real gap caught during live browser verification, not
  invented in the abstract**: after the backend and the core frontend
  change were both done and tested, a live check of `localStorage` in
  a real browser session found the *old* `datalume.access_token` key
  still sitting there from before this migration — inert (nothing
  reads it anymore) but still a lingering credential in exactly the
  disk-backed, script-readable storage this whole feature exists to
  get rid of. Fixed with a one-time cleanup
  (`window.localStorage.removeItem` on `AuthProvider` mount) — verified
  by re-checking `localStorage` in the browser afterward and confirming
  it was empty. A real, if minor, security gap this migration would
  otherwise have silently left behind for any already-logged-in user.
- ✅ Automated tests: 7 new in `tests/test_auth.py` — httpOnly/Secure/
  SameSite flags actually present on the Set-Cookie headers (not just
  "a cookie was set"); refresh via cookie with no CSRF header rejected
  (403); refresh via cookie with the wrong CSRF header rejected (403);
  refresh via cookie with the correct CSRF header succeeds *and*
  rotates both cookies to new values; refresh via an explicit body
  token needs no CSRF header; refresh with neither a cookie nor a body
  token is rejected (401); logout clears both cookies, verified by then
  attempting a refresh against the (now-cleared) cookie and confirming
  it fails. 266/266 passing project-wide — the full existing suite
  needed no changes at all.
- ✅ **Live end-to-end browser verification**, not just backend tests:
  registered and logged in through the real UI against a real running
  server; confirmed the real `/auth/refresh` call on page load returns
  `200` purely from the httpOnly cookie (no `localStorage` involved);
  navigated directly to `/dashboard` on a fresh page load and confirmed
  "Welcome, Cookie Verify" rendered — proving session persistence works
  with zero script-readable token storage; clicked "Log out" and
  confirmed the real `/auth/logout` call, that `document.cookie` was
  empty afterward, and that navigating back to `/dashboard` correctly
  bounced to `/login` rather than silently staying authenticated; then
  logged back in to confirm the full cycle isn't one-way broken.
- ⬜ CSRF/refresh cookies are `SameSite=Lax`, which assumes the
  frontend and backend stay same-site (same registrable domain, as
  `localhost:3000`/`localhost:8000` are in this environment, and as a
  typical `app.example.com`/`api.example.com` production split would
  be). If they ever end up on genuinely different registrable domains,
  this would need `SameSite=None; Secure` instead — not built
  speculatively ahead of an actual deployment topology that needs it.

## Post-Phase-7: billing audit-log gaps closed

Two gaps, found and closed together while reading
`app/services/webhook_handlers.py` end to end rather than just the one
function the first gap was originally flagged against.

- ✅ **Gap 1 — personal (non-org) subscription plan changes weren't
  audit-logged at all**, flagged since the Phase 7 audit-logging
  section was first written. The fix was one `if` statement, not a new
  feature.
  `AuditLog.actor_user_id` and `AuditLog.organization_id` were already
  both nullable, and `GET /users/me/audit-log` (`app/api/v1/routers/
  users.py`) already existed, querying by `actor_user_id == current_user
  .id` with no requirement that `organization_id` be unset — it would
  already have shown this event correctly. The only actual gap was in
  `app/services/webhook_handlers.py`'s `handle_subscription_updated`:
  the `record_audit_event` call was wrapped in `if
  subscription.organization_id:`, so a personal subscription's change
  silently recorded nothing at all. Removed the conditional and pass
  `actor_user_id=subscription.owner_user_id` unconditionally —
  `Subscription` already guarantees exactly one of `owner_user_id` /
  `organization_id` is set (see that model's own docstring), so this is
  behaviorally identical to before for org subscriptions
  (`owner_user_id` is `None` there, same as the old hardcoded `None`)
  and newly correct for personal ones.
- ✅ Automated tests: 1 new in `tests/test_billing_webhook.py`, proven
  through the real endpoint, not just a database check — registers a
  personal account, drives it through the same
  `checkout.session.completed` → `customer.subscription.updated`
  webhook sequence the existing plan-change test already exercises,
  then calls the real `GET /users/me/audit-log` and asserts the
  `billing.plan_changed` event is actually there with the right
  `old_plan_id`/`new_plan_id` metadata and `organization_id: null`.
- ✅ **Gap 2 — subscription cancellation wasn't audit-logged at all,
  for *either* personal or organization accounts** — not previously
  flagged anywhere, found by reading the very next function
  (`handle_subscription_deleted`) in the same file while fixing Gap 1
  above. Unlike Gap 1, this wasn't a broken conditional on an existing
  call; there was no `record_audit_event` call at all. Added a new
  `billing.subscription_canceled` event type (registered in
  `app/services/audit.py`'s `EVENT_TYPES`) and wired it in, capturing
  `previous_plan_id` *before* the handler resets `plan_id` to `"free"`
  — a subtlety specifically covered by a new test that cancels from a
  paid plan rather than from free, where a before/after capture-order
  bug would otherwise be invisible (canceling an already-free account
  can't distinguish "captured before" from "captured after").
- ✅ Automated tests: 2 new test functions in `tests/test_billing_webhook.py`
  (1 for Gap 1; 1 for Gap 2's capture-order case — Gap 2's basic
  coverage was added as new assertions in the existing cancellation
  test rather than a separate function), both proven through the real
  `GET /users/me/audit-log` endpoint, not just a database check.
  268/268 passing project-wide — every pre-existing test needed no
  changes.

## Post-Phase-7: fifth specialist report template (social housing compliance exceptions)

The first new report added since all four industry packs already had
one (see "Post-Phase-7: fourth specialist report template" above,
which completed that initial coverage). Every pack already having a
report meant this one had to be a *second* report on an existing pack,
not a first report on a new one — attaching it to `social_housing`
specifically since that pack already has the exact fields a compliance
audit needs (`last_inspection_date`, `epc_rating`, `void_status`,
`planned_investment_amount`) and already has a `compliance_caveat` to
reuse. A new pack (public sector/education) was the other option the
"Immediate next steps" list named, but `app/core/industry_packs.py`'s
own module docstring already flags that public sector specifically
"would need real domain input before the KPI definitions... could be
written honestly" — not something to invent unprompted.

- ✅ **Social Housing Compliance Exceptions Report**
  (`POST /dataset-tables/{id}/reports/social-housing-compliance-exceptions`,
  `generate_social_housing_compliance_exceptions_report_pdf` in
  `app/services/reports.py`) — deliberately not a copy of the existing
  Social Housing Asset Report with a new title. That report is a
  portfolio *overview* (aggregate KPIs, the full EPC distribution across
  every band); this one is a row-level *exceptions audit* — only the
  properties that need action. Two of its four sections don't exist in
  the Asset Report at all: properties with no inspection date recorded
  (a data gap that is itself a compliance risk, since an ungraded
  property can't be shown compliant either), and void properties with no
  planned investment recorded. The other two (overdue inspection, poor
  EPC rating) reuse the exact same cutoff/marker logic as
  `app/services/industry_kpis.py`'s `properties_overdue_inspection`
  calculator and `_VACANT_MARKERS` constant — imported directly, not
  redefined a second, possibly-drifting way.
- ✅ **No KPI table** — the only one of the five specialist reports that
  doesn't open with a "Key metrics" table from `compute_kpis`. An
  exceptions audit's job is the exception list itself, not a portfolio
  summary (the Asset Report already covers that for this same pack), so
  there was nothing honest to put in a metrics table here that wasn't
  already the exception counts shown in its own "Exception summary"
  section.
- ✅ **Wired into scheduling** (`REPORT_TYPE_REQUIRED_INDUSTRY` in
  `app/services/scheduled_reports.py`), same as all four other industry
  reports — a social_housing workspace can schedule this to email itself
  daily/weekly/monthly exactly like its Asset Report sibling.
- ✅ **Frontend**: the "Download portfolio report" button's per-industry
  lookup map (added for the fourth report, see above) only had room for
  one report per industry — insufficient now that social_housing has
  two. Changed from `Record<industry, generator>` to
  `Record<industry, ReportDescriptor[]>` so a pack can list any number of
  reports, each rendering its own button — not a one-off hack specific
  to social_housing, so a sixth report on any pack won't need this
  rewritten again. The scheduling dropdown's report-type options
  (`INDUSTRY_REPORT_TYPE` → `INDUSTRY_REPORT_TYPES`) needed the same
  single-value-to-list change for the same reason.
- ✅ **Verified by reading the actual rendered PDF text**, not just
  checking the file is non-empty — twice: once via a temporarily
  installed PDF text extractor (removed again afterward) against a
  6-row dataset purpose-built to hit all four exception categories plus
  two control cases (a void property *with* planned investment, and a
  recently-inspected property), confirming each exception list contained
  exactly the right property and nothing else; and a second time via a
  real click on the real "Download compliance exceptions report" button
  in a real browser session (registered a real account, created a real
  social_housing workspace, uploaded a 5-row dataset through the real
  upload API), reading the real `POST .../social-housing-compliance-exceptions`
  (201) and `GET /reports/{id}/download` (200) calls via the browser's
  own network panel, then downloading and hand-verifying that exact PDF
  — 2 overdue (correctly sorted oldest-first), 1 missing inspection
  date, 2 poor EPC ratings, 1 void-without-investment — against the
  source CSV by hand.
- ✅ Automated backend tests: 271/271 passing (3 new in
  `tests/test_industry_reports.py` for the new endpoint, matching the
  existing generate+download/wrong-industry/outsider-403 pattern; the
  scheduling tests for "requires matching industry" and "scheduler
  generates every industry report type" were extended to cover the new
  report_type rather than duplicated into new test functions).

## Post-Phase-7: sixth specialist report template (residential repairs and maintenance)

The second pack (after social_housing, see the fifth-report section
above) to get a second report. Checked each of the other three packs'
fields before picking one: `commercial_property` has no capex/valuation
field an "Investment Planning" report could use, and `business_finance`
already covers revenue/expenses/trends/top-customers in its one report —
a second report there would have mostly repeated it. `residential_property`
had a genuinely unused field: `maintenance_cost` already drives one
aggregate KPI (`total_maintenance_cost`) but was never shown per
property anywhere in the app.

- ✅ **Residential Repairs & Maintenance Report**
  (`POST /dataset-tables/{id}/reports/residential-repairs-maintenance`,
  `generate_residential_repairs_maintenance_report_pdf` in
  `app/services/reports.py`) — the same KPI table as the existing
  Portfolio Report, plus two sections that report doesn't have: a
  per-property maintenance-spend breakdown sorted highest-first, and a
  separate list of properties with no recorded maintenance spend.
  Unlike the compliance-exceptions report's missing-data sections, this
  one is deliberately *not* styled or worded as a problem — the report
  says outright that a property with no recorded spend may simply not
  have needed any repairs yet, since nothing in this pack's fields can
  tell "nothing needed fixing" apart from "nothing was logged."
- ✅ **Wired into scheduling**
  (`REPORT_TYPE_REQUIRED_INDUSTRY` in
  `app/services/scheduled_reports.py`) — a residential_property
  workspace can schedule this alongside its Portfolio Report.
- ✅ **Frontend**: slotted into the `Record<industry, ReportDescriptor[]>`
  / `Record<industry, string[]>` structures the fifth report's section
  above already generalized to — no further rewrite needed, confirming
  that generalization was the right call the first time a second pack
  needed it, not just a one-off for social_housing.
- ✅ **Verified by reading the actual rendered PDF text**, twice: a
  4-property dataset (two spenders, one zero, one null) through a
  temporarily-installed PDF text extractor confirming the sort order and
  the null/zero split were both handled correctly; and a second real
  pass — real account, real `residential_property` workspace, real
  upload, real click on "Download repairs & maintenance report" — with
  the real `POST .../residential-repairs-maintenance` (201) and
  `GET /reports/{id}/download` (200) calls confirmed via the browser's
  network panel, then the downloaded PDF's figures (total maintenance
  cost, the per-property ranking, which properties had no spend
  recorded, and every KPI in the metrics table) hand-checked against the
  source CSV.
- ✅ Automated backend tests: 274/274 passing (3 new in
  `tests/test_industry_reports.py`, same generate+download/
  wrong-industry/outsider-403 pattern; the two scheduling tests extended
  again rather than duplicated).

## Post-Phase-7: dashboard drag-and-drop reorder, add, and remove widgets

Closes the gap this document had flagged since Phase 6: the dashboard
builder was "configurable and persisted, not drag-and-drop." Scoped
deliberately to what the brief and this project's own docs actually
promised — drag-to-reorder, persisted — not resizing or a freeform 2D
grid, neither of which was ever described as missing.

Building the reorder UI surfaced a second, undocumented gap in the same
page: `POST /dashboards/{id}/widgets` and `DELETE
/dashboards/{id}/widgets/{widget_id}` were fully built and tested on
the backend since Phase 6, but `apps/web` never called either one —
the dashboard viewer page had no add-widget or remove-widget UI at
all. A dashboard's widget set could only ever be set once, by "Generate
Dashboard Automatically," and never edited afterward. Fixed in the same
pass, since a reorder feature is of limited use if a user can't also
change *which* widgets are on the dashboard in the first place.

- ✅ **Backend**: `PATCH /dashboards/{id}/widgets/reorder`
  (`app/api/v1/routers/dashboards.py`) takes the dashboard's full new
  widget order as a list of ids, not a single moved-widget delta —
  validated as an exact match to the dashboard's current widget set (no
  duplicates, nothing missing, nothing from another dashboard) before
  writing anything, so a stale or tampered client request can't leave
  some widgets with out-of-sync positions. No migration needed —
  `DashboardWidget.position` already existed as a plain integer column
  from Phase 6 (it was always "ordered list," just never reorderable),
  so this is a pure logic addition, not a schema change.
- ✅ **Frontend**: `@dnd-kit/core` + `@dnd-kit/sortable` added as a new
  dependency (`apps/web/package.json`) — nothing comparable was
  installed before. `apps/web/src/app/dashboard/dashboards/[dashboardId]/page.tsx`
  now renders widgets through a `DndContext`/`SortableContext`
  (`rectSortingStrategy`, so it reflows through the existing responsive
  CSS grid rather than a new freeform canvas), with a visible drag
  handle per widget card (keyboard-accessible via `dnd-kit`'s
  `KeyboardSensor`, not mouse-only). Reordering is optimistic — the
  local order updates immediately on drop — and reverts with an error
  message if the `PATCH` fails, rather than leaving the UI showing an
  order the server never actually saved.
- ✅ **Dependency audit checked before and after**: `npm audit` shows 15
  pre-existing vulnerabilities (5 moderate, 7 high, 3 critical) in this
  project's existing dev/build tooling (Next.js, Vitest, Tailwind's
  PostCSS chain) — all present before this change, none introduced by
  `@dnd-kit`, confirmed by checking which package each advisory actually
  names. Not fixed here — upgrading `next`/`vitest`/`tailwindcss` is a
  separate, likely breaking-change maintenance task, out of scope for a
  reorder feature.
- ✅ **Verified with a real drag gesture, not a simulated API call**:
  registered a real account, created a real commercial_property
  workspace, auto-generated a real 8-widget dashboard, then performed an
  actual pointer drag in the browser moving "Total Rent Roll" from
  position 1 to position 3. Confirmed the real `PATCH
  .../widgets/reorder` (200) fired, confirmed the new order survived a
  full page reload, and confirmed it directly against the
  `dashboard_widgets` table's `position` column in the database — not
  just trusting the UI's own re-render.
- ✅ Automated backend tests: 276/276 passing (3 new in
  `tests/test_dashboards.py`: persists a full reversed order and
  confirms it via a fresh `GET`; rejects a submitted widget set that's
  missing a widget, contains an unknown id, or duplicates one, leaving
  the dashboard unchanged in all three cases; an outsider gets
  403/422 on the new endpoint, extending the existing
  `test_outsider_cannot_access_dashboards`).
- ✅ **Add/remove widget UI**: a "Remove" (×) button on every widget
  card, and an "Add a KPI widget" picker below the grid for workspaces
  on one of the four industry packs — the picker is built from
  `GET /industry-packs/{industry_id}`'s real KPI list (`app/schemas/
  industry.py`'s `IndustryPackOut`, already existed and was already
  tested via `/industry-kpis`), not a hardcoded frontend list, so it can
  never drift from what the backend actually supports. No backend
  changes needed — `add_widget`/`remove_widget` already existed and
  were already tested (`test_manual_dashboard_crud_lifecycle`); this was
  purely the missing frontend wiring. A general (no-pack) workspace's
  dashboard correctly has no "add KPI widget" picker — there's no fixed
  KPI set to pick from, so it correctly 404s from `/industry-packs/{id}`
  — but it now has a chart-widget picker instead, see below. **Chart
  widgets were scoped out of this bullet and built immediately after**,
  see the "Add a chart widget" bullet just below.
- ✅ **Verified live**: created a dashboard with zero widgets, added two
  real KPI widgets through the picker (confirmed the real computed
  values — e.g. Total Rent Roll summing to the real uploaded data's
  rent), removed one through its × button, confirmed the real `POST`/
  `DELETE` calls via the browser's network panel, and confirmed the
  final one-widget state survived a full page reload and matched the
  database directly.
- ✅ **Add a chart widget**: closes the gap the add/remove bullet above
  explicitly deferred. Fully generic, not limited to the 3 operations
  "Generate Dashboard Automatically" happens to use — built from
  `GET /tools`' real `ToolSpec` metadata (`app/services/tools.py`,
  already existed, already powers `/analyze` and the AI planner), so
  all 7 registered operations are addable, and an 8th added to that
  registry later needs no frontend change to become addable here too.
  Every `ToolParameter` in that registry is one of three shapes — an
  `enum` (→ a dropdown of those choices), an `"integer"` type (→ a
  number input), or a plain `"string"` with no enum (→ always a column
  reference in this registry, never free text, so a dropdown of the
  table's real column names, not a text box a user has to get exactly
  right). One new backend endpoint was needed to support this:
  `GET /dataset-tables/{id}` (`app/api/v1/routers/datasets.py`) —
  oddly, the only `/dataset-tables/{id}/*` endpoint that had never
  existed is the one returning the table itself; every other such
  endpoint already loaded the same row internally to act on it. General
  (no-pack) workspaces — previously limited to auto-generate only, with
  zero manual add capability of any kind — get their first-ever
  manual-add widget UI through this, since chart tools need no industry
  pack. Verified live with three different parameter shapes, not just
  one: `descriptive_stats` (a single required column; sum/mean/etc. all
  matched hand-computed values), `group_aggregate` (a required
  `group_by` plus two optional parameters, one with a default — the
  real grouped sums matched the source CSV), and `correlation` (two
  required columns, no optional parameters or defaults at all — a real
  Pearson coefficient computed and returned, with the exact underlying
  data pairs in `scatter_sample`). All three added through a real
  general-industry dashboard that had never had a manually-added widget
  before, confirmed via the real `POST .../widgets` (201) calls, and
  confirmed surviving a full page reload.
- ✅ Automated backend tests: 279/279 passing (3 new in
  `tests/test_datasets.py` for `GET /dataset-tables/{id}`: returns the
  real profile including real column names; 404s for an unknown id; 403
  for an outsider).

## Post-Phase-7: dataset version comparison UI

Found by systematically cross-referencing every backend route against
every frontend API-client call, after the dashboard-widgets gap (above)
turned up twice in a row from the same kind of check done ad hoc. The
full sweep found two bigger gaps of the same shape — a complete,
tested, multi-endpoint **Organizations** feature (create/list an org,
invite members, an audit-log export) and a complete, tested
**Webhooks** feature (subscribe/list/delete/test) — both with literally
zero frontend trace, not even an orphaned `api.ts` method. Neither was
built in this round: each is its own multi-page feature with real
product/UX decisions attached (what does team onboarding look like?
does workspace creation need an org picker?), not a self-contained
wiring fix — flagged for a deliberate decision rather than built
unprompted. Both were since built in later rounds — see "Post-Phase-7:
webhooks UI" and "Post-Phase-7: organizations UI" below. Version
comparison was the clearest *contained* case in this round: `POST
/datasets/{id}/compare-versions` was fully built and tested in Phase 6
(see the updated bullet above), and the workspace page already
referenced the fact that multiple versions exist without ever letting
a user act on it.

- ✅ **Frontend**: a "compare versions" toggle next to the existing "N
  versions" text on each dataset card
  (`apps/web/src/app/dashboard/workspaces/[id]/page.tsx`) expands into
  a From/To version picker defaulting to the two most recent versions
  (the most common comparison — "what did my last cleaning operation
  change?") and a results view: row-count delta with % change,
  columns added/removed, and a per-column before/after table (sum,
  mean, distinct count). No backend changes — purely the missing
  frontend wiring, same shape as the dashboard add/remove gap.
- ✅ **Verified live with a real, meaningful diff**: uploaded a 5-row
  CSV with one exact-duplicate row, ran `/deduplicate` to create a real
  version 2 (4 rows), then used the new UI to compare v1 → v2. Every
  figure matched hand-computed values from the source data exactly: row
  count 5 → 4 (-1, -20.0%), Revenue sum £4,250 → £3,250 (mean £850 →
  £812.50), Units sum 39 → 29 (mean 7.8 → 7.25), both categorical
  columns' distinct counts correctly unchanged at 2 → 2. Confirmed via
  the real `POST .../compare-versions` (200) call in the browser's
  network panel.
- No new backend tests needed — `tests/test_version_compare.py` already
  covered the endpoint itself; this was purely frontend wiring to an
  already-tested capability.

## Post-Phase-7: webhooks UI

The second sweep-discovered gap closed (see "Post-Phase-7: dataset
version comparison UI" above for the first, and the sweep itself).
Unlike Organizations — the sweep's other finding, left alone because it
needs real product/UX decisions — webhooks turned out to be exactly the
self-contained wiring task predicted: a workspace-scoped settings page
with no open design questions, closely following the account-scoped API
keys settings page's already-established pattern.

- ✅ **Frontend**: a "Webhooks" section on the workspace page
  (`apps/web/src/app/dashboard/workspaces/[id]/page.tsx`) — a create
  form (URL + event-type checkboxes, reusing `event_types` straight
  from the existing `WEBHOOK_EVENT_TYPES` set so the UI can never list
  an event the backend doesn't actually support), a "copy this secret
  now" banner matching the API keys page's exact pattern (same amber
  styling, same "shown once" framing), and a list with per-subscription
  delivery status (`last_delivery_at`/`status`/`error`, already tracked
  server-side since the feature was first built) plus Send-test and
  Delete actions. No backend changes — `create`/`list`/`delete`/`test`
  all already existed and were already tested
  (`tests/test_webhooks.py`).
- ✅ **A real UI bug caught and fixed during verification, not after**:
  the "secret shown once" banner and the last test-delivery result both
  used component state that nothing cleared on delete — deleting a
  webhook left its secret banner and stale test result visibly
  attached to a subscription that no longer existed. Caught by actually
  deleting a webhook during verification and looking at the resulting
  screen, not by reading the code. Fixed by clearing both on delete (and
  the test-result on creating a new one, same gap).
- ✅ **Verified against a real external HTTP delivery, both directions**:
  created a subscription pointed at `https://httpbin.org/post`, clicked
  "Send test," and confirmed a real `last_delivery_status: 200` came
  back — a genuine outbound HTTP request over the real internet, not a
  mock. Then created a second subscription pointed at
  `https://httpbin.org/status/500` and confirmed the UI surfaced the
  real failure ("Test delivery failed: HTTP 500") correctly — proving
  both the success and failure display paths, not just the happy path.
  Confirmed the real `POST .../webhooks` (201) and
  `POST .../webhooks/{id}/test` (200) calls via the browser's network
  panel throughout.
- No new backend tests needed — `tests/test_webhooks.py` already
  covered the endpoint behavior; this was frontend wiring plus the one
  stale-state bug found and fixed along the way.

## Post-Phase-7: organizations UI

The gap left deliberately unbuilt when webhooks and dataset version
comparison were closed — flagged at the time as needing real
product/UX decisions before it was a wiring task. A dedicated
investigation (not guesswork) found those decisions mostly already had
answers in the existing backend:

- **Workspace creation's org picker wasn't a new design question — the
  code path already existed.** `POST /workspaces` already accepts
  `organization_id` and was already exercised by real tests
  (`test_create_organization_workspace_requires_membership`,
  `test_outsider_cannot_read_other_orgs_workspace`); the frontend
  simply never sent it. Added an "Owner" dropdown (Personal / each
  organization the user belongs to) to the workspace-creation form on
  `/dashboard`.
- **Billing-per-org wasn't a new design question either — it's fully
  built.** `Subscription` is keyed to a user XOR an organization
  (mirroring `Workspace` exactly), `get_subscription_for_workspace`
  already resolves an org workspace's quota against the *organization's*
  shared subscription, and every `/billing/*` endpoint already accepts
  an `organization_id` with membership/manager-gated authorization,
  tested (`test_outsider_cannot_read_org_subscription`,
  `test_non_manager_gets_403_not_503_on_checkout`). Nothing new was
  built here — this round deliberately didn't touch billing/pricing UI,
  since an org-aware billing page is its own separate surface.
- **The one genuine gap**: no endpoint existed to list an organization's
  members — `GET /organizations` lists orgs *I'm* in, not who else is
  in a given org, and there's no `MembershipOut` variant with the
  member's email/name (only `user_id`, not useful to render directly).
  Added `GET /organizations/{id}/members`
  (`app/api/v1/routers/organizations.py`), readable by any member (not
  manager-only — matching the existing "any member reads, owner/admin
  governs" split `require_workspace_access`/`require_workspace_write_access`
  already use for workspaces), returning a new `MembershipDetailOut`
  (`id, user_id, organization_id, role, user_email, user_full_name`).
- ✅ **Frontend**: a new `/dashboard/organizations` page — create an
  organization, and per-organization (expandable, same pattern as the
  webhooks/compare-versions panels): a member list, an invite form
  (email + role), and an audit-log view. Linked from `/dashboard`
  alongside the existing API keys/Upgrade plan links. The workspace
  list on `/dashboard` now also shows which organization owns a shared
  workspace, not just personal ones.
- ✅ **A real bug caught live, not in review**: the invite form's
  success message read `${result.user_email} added as ${result.role}`
  — but the invite endpoint's response for an existing user
  (`MembershipOut`) has no `user_email` field at all (only
  `GET .../members`'s `MembershipDetailOut` does), so it rendered
  "undefined added as analyst." Caught immediately by actually clicking
  Invite during verification, not by reading the TypeScript. Fixed by
  using the email the admin had just typed (already known locally)
  instead of a field the API response was never going to have, and by
  splitting the client type in two (`Membership`, from `GET .../members`,
  vs. `MembershipCreated`, from the invite endpoint) so the mismatch
  can't recur silently.
- ✅ **Verified live, both invite paths and real cross-user access**:
  created an organization as one real account, invited a second
  already-registered real account directly (immediate membership, real
  `201`), invited a third address with no account yet (real `202`,
  a genuine email sent through the already-verified Gmail SMTP
  integration), confirmed the audit log showed all three real events
  in order, created a workspace under the organization, then logged in
  as the *second* account and confirmed that workspace was visible and
  fully usable — proving organization membership actually grants shared
  workspace access end-to-end, not just that the invite UI renders.
- ✅ Automated backend tests: 282/282 passing (3 new in
  `tests/test_organization_members.py`: lists the owner alone right
  after creation, then both members with correct roles after a direct
  invite, and confirms any member — not just the owner — can read the
  list; a non-member gets 403; an unauthenticated request gets 401).

## Post-Phase-7: detect invalid values as their own category

See the Phase 2 section above (now ✅) for the full description.

- ✅ Automated backend tests: 283/283 passing (1 new,
  `test_upload_distinguishes_invalid_values_from_missing` in
  `tests/test_datasets.py` — uses a >10,000-row generated CSV so the
  real `ignore_errors` coercion-failure path is actually exercised, not
  a small fixture Polars would just widen to text).

## Post-Phase-7: configurable KPI date window

Closes the Phase 5 gap on "overdue inspection" / "leases expiring"
always using a fixed 12-month window. The real scope turned out to be
6 independent hardcoded locations, not the 2 KPI calculators alone: the
4 specialist PDF report generators (commercial property, residential
property, both social housing reports) had each separately re-derived
the identical `today.replace(year=today.year ± 1)` cutoff inline,
contradicting `docs/ARCHITECTURE.md`'s claim that the PDF reports reuse
the KPI engine's exact date logic.

- ✅ **`Workspace.kpi_window_months`** (new nullable `Integer` column,
  migration `25297cfd1b0e`): `NULL` means "use the 12-month default"
  (`app/services/industry_kpis.py`'s `DEFAULT_KPI_WINDOW_MONTHS`). Lives
  on `Workspace` rather than `Organization` since a personal
  (user-owned) workspace has no organization row to hold it.
- ✅ **`PATCH /workspaces/{id}/settings`**: sets or resets (via explicit
  `null`) the window, validated to 1-60 months, gated behind
  `require_workspace_write_access` (same bar as cleaning operations —
  a Viewer/Auditor can't change it).
- ✅ **`_add_months` helper** replaces the two calculators' and four
  report generators' `date.replace(year=year ± 1)` arithmetic — besides
  being parameterizable to N months instead of a fixed 12, this also
  fixes a latent crash the old code had: `date.replace(year=...)` raises
  `ValueError` on 29 Feb in a non-leap target year, which `_add_months`
  instead clamps to 28 Feb (same clamping approach already used by
  `scheduled_reports.compute_next_run`'s monthly cadence).
  `window_months` is threaded through `compute_kpis` and all ~9 call
  sites (the `/industry-kpis` and `/scenario` endpoints, dashboard KPI
  widgets, scheduled reports, and all 6 on-demand specialist report
  endpoints) as `workspace.kpi_window_months or DEFAULT_KPI_WINDOW_MONTHS`.
- ✅ **A real UI/PDF inconsistency caught by generating and reading an
  actual report, not by inspection**: the `leases_expiring_12_months`
  KPI's *name* is a fixed string ("Leases Expiring Within 12 Months")
  set at pack-definition time — it doesn't know what window a given
  workspace actually configured. With a 1-month window set, the
  commercial property report's "Key metrics" table still read "Leases
  Expiring Within 12 Months: 1" directly above a "Lease expiry schedule
  (next 1 month)" section — numerically correct but visibly
  self-contradictory. Fixed by re-deriving that one label dynamically
  from `window_months_used` in both the frontend KPI panel
  (`apps/web/src/app/dashboard/workspaces/[id]/page.tsx`) and the PDF's
  Key Metrics table (`generate_commercial_property_report_pdf`) — the
  `properties_overdue_inspection` KPI's name has no number baked in, so
  it didn't need the same fix. Caught by actually calling the real
  `/reports/commercial-property-portfolio` endpoint, downloading the
  PDF, and reading its extracted text — not by just confirming a `200`
  with a nonzero `Content-Length`.
- ✅ **`_months_label` helper** (`app/services/reports.py`) fixes a
  grammar bug the first pass of this feature introduced: naively
  interpolating `window_months` into report section headers produced
  "next 1 months" for a 1-month window. Every PDF section header
  touched by this feature (`Lease expiry schedule`, `Tenancies ending`,
  `Properties overdue inspection` ×2, plus their "no results" fallback
  sentences) now goes through this helper instead.
- ✅ **Frontend**: a workspace-page control ("Lease/inspection
  date-window KPIs use N months. Change") next to the industry label,
  shown only for the three industries whose KPIs/reports actually use
  the window (`commercial_property`, `residential_property`,
  `social_housing` — `business_finance` has no such KPI, so the control
  would be a no-op there). The KPI results panel also states which
  window was actually used (`window_months_used` on
  `IndustryKPIResponse`), so a user re-reading an old result isn't
  misled if the setting has since changed.
- ✅ Automated backend tests: 288/288 passing (5 new, in
  `tests/test_workspace_kpi_window.py`) — proves the setting actually
  changes both calculators' real output, in opposite directions:
  narrowing the window drops the leases-expiring count but raises the
  overdue-inspection count, each against a date fixture with enough
  margin (20/90-day and 14/40-day offsets) to be robust to whatever
  calendar month the suite happens to run in. Plus settings-endpoint
  tests for range validation (422 outside 1-60) and write-access
  enforcement (403 for an outsider).
- ✅ **Verified live against a real running server**: changed the
  setting via the browser UI from 12→1 month, recomputed KPIs, watched
  "Leases Expiring Within 12 Months: 2" become "Leases Expiring Within 1
  Month: 1" — and separately generated the real PDF report via the API
  and read its extracted text, confirming both the KPI-table label fix
  and the grammar fix actually render correctly, not just that the
  underlying numbers were right.

## Post-Phase-7: first frontend test suite

`apps/web`'s `package.json` has had a `"test": "vitest run"` script
with `vitest` as a dependency since early in this project, but zero
test files behind it anywhere — every frontend change instead relied
entirely on live browser verification (real, but leaves no regression
net). Closed by starting where the leverage is highest rather than
picking an arbitrary page.

- ✅ **`apps/web/src/lib/api.ts`'s `request`/`requestMultipart`
  helpers** — not exported, so tested through the real public `api.*`
  methods every page actually calls (`login`, `me`, `logout`,
  `uploadDataset`) rather than against reimplementation-coupled
  internals. Chosen as the starting point because literally every one
  of this file's ~40 exported methods funnels through these two
  functions — the single most load-bearing piece of logic in the
  entire frontend, and the one most pages would silently break under if
  it regressed.
- ✅ `vitest.config.ts` (new, `environment: "node"` — no DOM needed for
  this file, so no `jsdom`/`happy-dom`/`@testing-library/react`
  dependency was added; a future suite testing actual page components
  would need one of those).
- ✅ Covers: successful JSON parsing, the base URL + `credentials:
  "include"` + `Content-Type` sent on every request, the `Authorization`
  header present when a token is given and absent when it isn't, a
  `204` response returned as `undefined` without ever calling
  `res.json()`, a thrown `ApiError` (real `instanceof` check, not just
  a shape match) carrying the server's `detail` message, falling back
  to `statusText` when the error body isn't valid JSON, stringifying a
  non-string `detail` (FastAPI's 422 validation-error array shape), and
  `requestMultipart` sending a real `FormData` body with no manual
  `Content-Type` header (the browser must set its own boundary).
- ✅ **Verified these tests actually catch a regression, not just that
  they pass once**: temporarily broke the `detail` body-parsing line
  (ignoring the server's error message), re-ran the suite, watched 3 of
  10 tests fail with the exact expected diffs, then restored the
  original code and confirmed all 10 pass again — the same
  "prove a reverted bug would be caught" discipline used for the S3
  region bug and the invalid-values coercion detection earlier in this
  document, applied to frontend tests for the first time.
- ✅ **Wired into CI**: `.github/workflows/ci.yml`'s `frontend-build`
  job now runs `npm test` between the typecheck and build steps (fails
  fast before spending time on a full Next.js build) — the step didn't
  exist in the original CI workflow because there was nothing real for
  it to run yet.
- ⬜ Still only `lib/api.ts` and (since the next round below) `lib/format.ts`
  covered — `lib/auth.tsx` (the auth context/hook) and every page
  component remain untested. A page/component suite would need `jsdom`
  or `happy-dom` plus `@testing-library/react`, neither installed yet —
  a reasonable next step, not done here to keep this round's dependency
  footprint at zero new packages.

## Post-Phase-7: usage reset countdown

Closes one part of the Phase 4 "no usage-history view, no 'usage
resets in N days' countdown" gap — the countdown specifically, not
usage history or proration display (still open, see Phase 4 above).

- ✅ **`next_usage_reset`** (`app/services/billing.py`): the real
  Stripe billing-cycle boundary (`Subscription.current_period_end`,
  synced from the `customer.subscription.updated` webhook) when it's
  set and still in the future; otherwise the first of next calendar
  month at UTC midnight — the same boundary `current_period_key()`
  already uses to decide when a new `UsageCounter` row starts. Falls
  back to the calendar-month boundary (rather than trusting a stale
  date) if `current_period_end` has already passed — covers a
  cancelled/downgraded-to-free subscription whose last real Stripe
  period ended with nothing clearing that field.
- ✅ **A real cross-backend datetime bug caught by writing the tests,
  not by inspection**: `current_period_end` is a `DateTime(timezone=True)`
  column that Postgres returns timezone-aware but SQLite returns naive
  on read (even though it's always written as UTC) — the exact quirk
  already documented in this file's Phase 6 section for
  `scheduled_reports.py`, now hit a second time. Comparing a naive
  SQLite-read value against a fresh `datetime.now(timezone.utc)`
  without normalizing first raises `TypeError`. Fixed by treating a
  naive `current_period_end` as UTC before comparing or returning it —
  covered by a dedicated test
  (`test_naive_period_end_from_sqlite_is_treated_as_utc`).
  `UsageOut.resets_at` added to the `GET /billing/subscription`
  response schema.
- ✅ **Frontend**: `apps/web/src/lib/format.ts` (new, `daysUntil` +
  `resetCountdownLabel`) renders "resets today" / "resets in 1 day" /
  "resets in N days" next to the existing usage text on the dashboard.
  Extracted into `lib/format.ts` rather than kept as page-local
  functions specifically so it could be unit tested the same way
  `lib/api.ts` was in the previous round, rather than needing
  `@testing-library/react` just to test two pure date functions.
- ✅ Automated backend tests: 293/293 passing (5 new in
  `tests/test_usage_reset.py` — pure unit tests constructing a
  `Subscription` in memory with no DB session, covering the free-plan
  calendar boundary, December→January rollover, a future real Stripe
  period end, a stale past one falling back correctly, and the
  naive/SQLite datetime case — plus one existing `test_billing.py`
  assertion extended to check the free-plan response's `resets_at`).
- ✅ Automated frontend tests: 17/17 passing (7 new in
  `lib/format.test.ts`, using `vi.useFakeTimers()` to pin "now" so the
  day-rounding and pluralization assertions are deterministic rather
  than depending on when the suite happens to run).
- ✅ **Verified live against a real running server**: registered a
  real user on 16 October 2026, confirmed the dashboard read "Free
  plan · 0 / 3 analyses used this month · resets in 16 days" (16
  October → 1 November is exactly 16 days), and independently queried
  `GET /billing/subscription` directly, confirming
  `resets_at: "2026-11-01T00:00:00Z"` in the raw JSON — not just that
  the UI showed a plausible-looking number.

## Post-Phase-7: real chart rendering for dashboard chart widgets

Found while scanning for the next gap to close: the Phase 6 "Add a
chart widget" feature's own name turned out to be aspirational.
`apps/web/src/app/dashboard/dashboards/[dashboardId]/page.tsx`'s
`WidgetCard` rendered every non-KPI widget's result as
`JSON.stringify(value.result, null, 2)` inside a `<pre>` tag — a chart
*tool* picker with no chart *rendering* behind it, for any of the 7
operations. Confirmed by reading the actual component code, not by
trusting the feature's name.

- ✅ **`apps/web/src/lib/charts.ts`** (new): `extractChartData(operation,
  result)` dispatches on `widget.config.operation` (already flowed to
  the frontend unchanged, no backend change needed) to turn 3 of the 7
  tool-result shapes into a generic `{label, value}[]` bar series —
  `group_aggregate`'s `groups`, `frequency_table`'s `top_values`,
  `time_trend`'s `points` (kept to the most recent 10 — it's
  chronologically ascending, so the tail is "most recent"). Every
  other operation (`correlation`, `descriptive_stats`,
  `detect_outliers`, `simple_forecast`) returns `null` and keeps the
  existing JSON view — a deliberately incomplete dispatch rather than
  inventing a misleading chart for a scatter/flat-scalar/two-series
  shape that doesn't fit a single bar series.
- ✅ **`MiniBarChart`**: a hand-rolled inline `<svg>` (horizontal bars,
  so long category labels don't need rotation) — no charting library
  added. Confirmed no existing chart library or CSP restriction in the
  repo before choosing this over adding a dependency.
- ✅ Automated frontend tests: 10 new in `lib/charts.test.ts` (37/37
  total passing) — covers all three chartable shapes, non-numeric
  values filtered out rather than crashing the chart, the 10-bar cap,
  `time_trend` correctly keeping the *last* N points (not the first),
  and `null` returned for both an unrecognized operation and a result
  missing the expected array field entirely.
- ✅ **Verified live against a real running server, both code paths**:
  created a real workspace, uploaded a 6-row CSV, created a dashboard,
  and added a `group_aggregate` widget (rent summed by category)
  through the real `POST /dashboards/{id}/widgets` endpoint — the
  browser rendered a real SVG bar chart with bars in the exact
  descending order and proportions the API response's `groups` array
  specified (Retail 2,700 longest, Office/Industrial 2,000 tied,
  Residential 700 shortest). Then added a `descriptive_stats` widget
  through the live "Add a chart widget" form in the UI and confirmed it
  correctly fell back to the JSON view rather than a broken or
  misleading chart — proving the dispatch's fallback path works
  end-to-end, not just in the unit tests.

## Post-Phase-7: written-month date formats for analytics tools

Closes one half of the Phase 3 "statistical rigor gaps" bullet — date
parsing specifically, not the separate (larger, model-choice) forecast
seasonality gap, which stays open.

- ✅ **`app/services/analytics.py`'s `_DATE_FORMATS`** grew from 4 to
  11: added `%Y/%m/%d` (unambiguous, same year-first logic as the
  existing ISO format) plus six written-month formats (`15 March
  2026`, `15 Mar 2026`, `March 15, 2026`, `Mar 15, 2026`, `March 15
  2026`, `Mar 15 2026`). Deliberately scoped to formats with **no
  DD/MM-vs-MM/DD ambiguity** — a month name can't be mistaken for a day
  number, unlike the existing numeric slash/dash formats (which already
  accept that ambiguity, trying DD/MM first) — so this doesn't carry
  the silent-misinterpretation risk `profiling.py`'s numeric-text
  heuristic deliberately avoids by not auto-converting.
  Case-insensitive by Python's own `strptime` behavior (confirmed:
  `%b`/`%B` match "mar"/"MARCH" equally), verified directly rather than
  assumed.
- ✅ Purely additive to the format list (appended, not reordered), so
  no string that already parsed under the first 4 formats could start
  matching a different one — confirmed by the full suite still passing
  unmodified (293/293 before this round's 20 new tests).
- ✅ Automated backend tests: 313/313 passing (20 new,
  `tests/test_date_parsing.py` — direct unit tests of
  `_parse_date_cell`, parametrized over all 13 now-supported formats
  plus 5 cases that should still correctly return `None` rather than
  raising, e.g. an ordinal "15th of March 2026" or an invalid month).
- ✅ **Verified live against a real running server**: uploaded a real
  CSV with four rows in four different written-month formats (`15
  January 2026`, `February 10, 2026`, `5 Mar 2026`, `Apr 20 2026`) and
  ran the real `time_trend` tool against it through
  `POST /dataset-tables/{id}/analyze` — `rows_excluded_unparseable_date:
  0` and all four rows landed in the correct month buckets
  (2026-01 through 2026-04) with the right summed values. Before this
  change all four would have been silently excluded.

## Post-Phase-7: saved scenarios and a scenario modeling UI

Set out to close "no saved/named scenarios" (Phase 6). Investigation
found a much bigger gap first: `apps/web/src/lib/api.ts` had a
`runScenario` client method and `POST /dataset-tables/{id}/scenario`
was fully built and tested on the backend, but **nothing in the
frontend ever called it** — zero scenario UI existed anywhere, ad-hoc
or saved. So this round builds both: the scenario-running UI that
should have shipped with the Phase 6 backend, and saved/named
scenarios on top of it.

- ✅ **`run_scenario_computation`** (`app/api/v1/routers/industry.py`):
  the body of the ad-hoc `/scenario` endpoint extracted into a shared
  function so a saved scenario's "run" endpoint can never compute a
  different result than running the same adjustments fresh — same
  discipline as the KPI engine being shared between `/industry-kpis`
  and the specialist reports.
- ✅ **`SavedScenario` model** (migration `8ce6893b37a6`): `workspace_id`
  + `dataset_table_id` (both CASCADE FKs, same pattern as
  `ScheduledReport`), `name`, `adjustments` (JSON array of
  `{column, adjustment_type, value}` — the same shape
  `ScenarioAdjustmentIn` already validates for the ad-hoc endpoint, so
  a saved row can never hold an adjustment the computation layer
  wouldn't also accept fresh), `created_by_user_id`.
  `app/api/v1/routers/saved_scenarios.py`: create/list (filterable by
  `dataset_table_id`)/delete (write access for mutations, read access
  for list/run — same split `ScheduledReport` uses) plus
  `POST /saved-scenarios/{id}/run`, which resolves the table fresh from
  the saved `dataset_table_id` and calls `run_scenario_computation` —
  re-running a saved scenario goes through the exact same quota check
  and KPI engine as running it ad-hoc.
- ✅ **Frontend `ScenarioPanel`** (new, in the workspace page, shown for
  the same three industries with a pack): adjustment rows (numeric
  column, percentage/fixed-amount/set-value, a value), "Run scenario"
  showing a baseline/scenario/% change table per KPI, a name field +
  "Save scenario", and a "Saved scenarios" list with per-scenario
  Run/Delete. Column dropdown is filtered to the table's numeric
  columns only (scenario adjustments reject non-numeric columns
  server-side anyway — filtering client-side avoids a round-trip just
  to find that out). Also fixed a frontend/backend type drift caught
  while touching this file: `apps/web/src/lib/api.ts`'s
  `ScenarioResponse` interface was missing `baseline_kpis`/
  `scenario_kpis`, which the backend schema had always returned.
- ✅ Automated backend tests: 318/318 passing (5 new in
  `tests/test_saved_scenarios.py` — create+list, delete (and confirms
  a deleted scenario's `/run` 404s), a saved scenario's run producing
  the exact same numbers as the equivalent ad-hoc `/scenario` test
  elsewhere in the suite, a `dataset_table_id` belonging to a different
  workspace rejected with 400, and an outsider 403d on every one of
  create/list/run/delete).
- ✅ **Verified live against a real running server, the full loop**:
  created a real commercial_property workspace, uploaded a 2-row rent
  roll, entered a 10% rent increase in the real UI, ran it (Total Rent
  Roll £3,000 → £3,300, +10%; Occupancy Rate correctly unaffected at
  0.0% change), saved it as "Rent +10%", confirmed the real
  `POST .../saved-scenarios` (201) in the network panel, clicked
  &ldquo;Run&rdquo; on the saved entry and confirmed the real
  `POST /saved-scenarios/{id}/run` (200) reproduced the identical
  numbers, then deleted it and confirmed the "Saved scenarios" section
  correctly disappeared once the list was empty again.

## Post-Phase-7: admin dashboard UI

Found by a systematic audit of this session: grepped every backend
route path against every frontend `request<T>(...)` call in
`apps/web/src/lib/api.ts`. `/admin/stats` and `/admin/users` (Phase 7,
tested, "verified live" via direct API calls per the section above)
had zero frontend trace — same shape of gap as the scenario modeling
UI closed earlier this round, and the Organizations/Webhooks UI gaps
closed in earlier rounds still. (The same audit also turned up
`/ai-conversations/{id}`, `/datasets/{id}/conversations`, and
`/users/me/audit-log` with no frontend trace either — flagged, not
built here; each is a smaller, more self-contained addition than this
one, worth a future round.)

- ✅ **`UserOut` (`app/schemas/user.py`) now exposes
  `is_platform_admin`** on `/users/me` — the one piece of this field
  every user is allowed to know about themselves (never about anyone
  else; `AdminUserOut`, a separate schema already gated behind
  `require_platform_admin`, is what exposes it for other users). Lets
  the frontend decide whether to show an "Admin" nav link at all,
  rather than showing a dead link every non-admin would hit a 403
  behind.
- ✅ **New `/dashboard/admin` page**: stat cards for every
  `PlatformStatsOut` field (storage formatted via a new
  `apps/web/src/lib/format.ts#formatBytes`, not raw bytes), a
  subscriptions-by-plan breakdown, and the full user list table.
  Fetches both `/admin/stats` and `/admin/users` on load; a `403`
  (non-admin) renders a plain "Not authorized" page rather than a
  broken one. `NavBar` shows an "Admin" link only when
  `user.is_platform_admin` is true.
- ✅ Automated backend tests: 319/319 passing (1 new,
  `test_users_me_exposes_own_platform_admin_status` — asserts the
  field is `false` for a fresh user and flips to `true` after really
  running `scripts/grant_admin.py` against the test database, not just
  toggling the field directly).
- ✅ Automated frontend tests: 33/33 passing (6 new, in
  `lib/format.test.ts`, covering `formatBytes` across B/KB/MB/GB and
  confirming it doesn't overflow past TB for very large values).
- ✅ **Verified live against a real running server, both the gate and
  the real page**: a regular test account saw no "Admin" link and got
  a real "Not authorized" page when navigating to `/dashboard/admin`
  directly (the backend's real 403, not a client-side guess); a second
  account was granted admin via the actual `scripts/grant_admin.py`
  script (not a database edit), logged in, saw the "Admin" link appear,
  and the page rendered real aggregate numbers (8 users, 7 workspaces,
  7 datasets, 136.8 KB storage) matching the dev database's actual
  accumulated state from this session's many prior verification
  rounds. Independently confirmed via a direct API call that visiting
  the user list had written a real `admin.user_data_accessed` audit
  event with the real `returned_count` — not just that the page showed
  data, but that the access-logging the backend promises actually fired
  from a real page view, not only from a test client.

## Known limitations in what's built

- ~~Token storage: the frontend stores the JWT in `localStorage`~~ —
  done, see "Post-Phase-7: httpOnly cookie refresh + CSRF protection"
  below.
- ~~No rate limiting on auth endpoints~~ — done, see "Post-Phase-7:
  auth endpoint rate limiting" below.
- **SQLite in dev**: fine for this stage, but Postgres-specific behaviour
  (e.g. case sensitivity, concurrent write behaviour) is not exercised by
  the current test suite. Recommend adding a CI job that runs the same
  tests against a real Postgres container before Phase 2 lands.
- **`JWT_SECRET` has an insecure default** — the app will run with it, but
  anyone deploying beyond localhost must override it (see docs/SECURITY.md).
- **Organizations: no way to remove a member or change their role once
  invited** — `app/api/v1/routers/organizations.py` has create/list/
  invite/members/audit-log but no `PATCH`/`DELETE` on a `Membership`.
  Also, `PlanLimits.max_team_members` (`app/core/plans.py`) is defined
  and shown on the pricing page but nothing enforces it against a live
  `Membership` count — an organization can invite past its plan's team
  size with no backend pushback. Both are real gaps in a feature that's
  otherwise verified end-to-end (see "Post-Phase-7: organizations UI"
  above), not yet built.
- **S3Storage is tested against a mocked S3 API, not a real bucket**:
  `tests/test_s3_storage.py` runs the real boto3 client code (bucket
  auto-creation, write, read, read-of-missing-key, delete, overwrite)
  against moto — a fake AWS backend that implements the actual S3 API
  semantics, not a hand-rolled stub. This caught and fixed a real bug:
  bucket auto-creation called `create_bucket` with no
  `CreateBucketConfiguration`, which real AWS S3 rejects for any region
  other than `us-east-1` — including `eu-west-2`, this app's own default
  region (see `app/services/storage.py`). What's still not proven: moto
  emulates AWS's behavior, not any specific S3-compatible service's —
  MinIO in particular is known to be lenient about exactly the kind of
  region strictness that bug depended on, which is likely why it would
  have gone unnoticed there too. Still run it against a real MinIO
  container (`docker compose up minio`, set `S3_*` env vars) or a real
  bucket before fully trusting it — only `LocalFilesystemStorage` has
  been verified against something real, repeatedly, including through
  the browser.
- **Upload processing is synchronous (inside the request), not a
  background job** — a deliberate Phase 2 scope cut, not an oversight:
  a real async pipeline needs a worker process, a job-status API, and a
  way for the frontend to poll or subscribe, each a feature of its own.
  `redis_url` exists in `app/core/config.py` for when this is built, but
  — same as the rate limiter found (see "Post-Phase-7: auth endpoint
  rate limiting" above) — nothing in this codebase connects to a real
  Redis instance yet. Fine for realistic business spreadsheets; would
  matter for very large or very numerous concurrent uploads. See also
  docs/ARCHITECTURE.md and docs/DEPLOYMENT.md.
- **Profiling reads a bounded sample** (`MAX_PROFILED_ROWS` = 200,000) of
  very large files rather than the whole thing, to keep synchronous
  request processing bounded (see the synchronous-upload limitation
  just above). Not an issue for realistic business spreadsheets; would
  matter for a multi-million-row CSV.
- **Mixed numeric formats** (e.g. a column mixing `"1,200"` and `"1200.5"`
  and `"N/A"`) are detected via a single regex, not a full parser — edge
  cases may be mis-flagged. Good enough for a first pass; revisit if real
  user data shows it misfiring.
- ~~SSO has never been run against a real identity provider~~ — done
  against a real Google account, see the updated Phase 7 "SSO via OIDC"
  section above. Okta/Azure AD remain untried (only Google verified so
  far), and the Google app itself is still in "Testing" publishing
  status with a single whitelisted test user — see docs/DEPLOYMENT.md.
- ~~Personal (non-org) subscription plan changes aren't audit-logged~~ —
  done, see "Post-Phase-7: personal subscription plan changes now
  audit-logged" below.
- **No SCIM provisioning, no custom roles beyond the fixed five, no
  production deployment manifest** (Kubernetes/Terraform/etc.) — see the
  Phase 7 section above for why each was scoped out this round.

## Immediate next steps (suggested, not started)

1. ~~Set `STRIPE_SECRET_KEY` + `STRIPE_WEBHOOK_SECRET` and run a
   Checkout → webhook → entitlement-unlocked flow end-to-end~~ — done
   against a real Stripe sandbox account, see the updated Phase 4
   section above. Still open: the same flow has never run against
   Stripe **live mode** (a real production account, real cards) — only
   ever the test-mode sandbox.
2. ~~Set `LLM_API_KEY` and actually run the AI analyst~~ — done, see the
   updated Phase 3 section above: two real questions, a real
   multi-turn conversation, correct tool calls, correct figures
   verified by hand.
3. Public-page content (Features, Solutions, Security, legal pages) —
   content and copy decisions needed from the product owner, not just
   engineering.
4. ~~Group-by as a persisted cleaning operation~~ — done, see
   "Post-Phase-7: persisted group-by" above. Every cleaning operation
   the brief named is now built (11 via `_apply_table_transformation`).
5. Verify `S3Storage` against the real MinIO container in docker-compose,
   then against a real AWS S3 / R2 bucket, before depending on it
   anywhere that matters — it's now tested against a mocked S3 API
   (moto) and a real region-handling bug was caught and fixed that way
   (see Known limitations), but no real bucket of any kind has received
   a request yet.
6. ~~Fix the conversation-history replay simplification~~ — done, see
   "Post-Phase-7: conversation history replay fidelity" above.
7. ~~A distributed lock for the scheduled-report scheduler~~ — done,
   see "Post-Phase-7: distributed scheduler lock" above.
8. ~~A drag-and-drop dashboard layout editor~~ — done (reorder-only, no
   resize or freeform grid), see "Post-Phase-7: dashboard drag-and-drop
   reorder" above.
9. ~~Point `SMTP_HOST` at a real provider and confirm a real message
   reaches a real inbox~~ — done, see "Post-Phase-7: transactional
   email"'s updated "Email service" bullet above. Real Gmail SMTP, a
   real account registration, a real verification email landing in a
   real inbox — confirmed by the account holder reading it directly,
   not just a
   clean HTTP response.
10. ~~A scheduled-reports UI in `apps/web`~~ — done, see "Post-Phase-7:
    scheduled reports frontend" above.
11. VAT/tax handling via Stripe Tax once Checkout is live — not started.
12. ~~More specialist report templates~~ — two more done: a Compliance
    Exceptions Report for social_housing and a Repairs & Maintenance
    Report for residential_property (each pack's second report — see
    "Post-Phase-7: fifth specialist report template" and "Post-Phase-7:
    sixth specialist report template" above). Still open: Investment
    Planning, Executive Intelligence, etc. — the pattern is now proven
    six times; each remaining one is a template-writing task on top of
    the existing KPI engine, attached to an existing pack as a second
    (or third) report, or to a new pack (public sector/education) once
    that pack has real domain input to define its KPIs from.
13. ~~A schema-confirmation UI for industry field mappings~~ — done, see
    "Post-Phase-7: industry field mapping confirmation" above.
14. ~~Set `OIDC_CLIENT_ID`/`OIDC_CLIENT_SECRET`/`OIDC_DISCOVERY_URL` against
    a real identity provider and complete one real login end-to-end~~ —
    done against a real Google OAuth client, see the updated Phase 7
    "SSO via OIDC" section above: a real consent screen, a real
    `/sso/callback` page (newly built — didn't exist before), a real
    `User` row, and a session confirmed to survive a reload. This also
    caught and fixed two real bugs (a missing auth cookie on the SSO
    login path, and a test suite that had started silently depending on
    real credentials in `apps/api/.env`) — see that section for detail.
    All four of the credential-gated integrations identified at the
    start of Phase 8 (Stripe, the LLM, SMTP, OIDC) are now verified
    against real accounts.
15. SCIM provisioning, custom/configurable roles, and a real deployment
    manifest for a specific cloud/platform — all scoped out of Phase 7,
    see that section above for why each is a substantial project of its
    own rather than an extension of what's here.
16. ~~**Organizations UI**~~ — done, see "Post-Phase-7: organizations UI"
    below. The open questions turned out to have real answers already
    in the codebase rather than needing new product decisions: a
    dedicated investigation found `Workspace.organization_id` was
    already a live, tested code path (just never sent by the frontend),
    and billing already fully supports organizations (a `Subscription`
    is keyed to a user XOR an organization, with membership/role-gated
    authorization on every billing endpoint) — nothing new to design
    there, only to expose. One real gap remained and was closed: no
    endpoint existed to list an organization's members, so `GET
    /organizations/{id}/members` was added.
17. ~~**Webhooks UI**~~ — done, see "Post-Phase-7: webhooks UI" below.
    Confirmed smaller and more self-contained than Organizations, as
    predicted — closely followed the existing API keys settings page's
    pattern (create, show a secret once, list, revoke/delete), just
    workspace-scoped instead of account-scoped.
