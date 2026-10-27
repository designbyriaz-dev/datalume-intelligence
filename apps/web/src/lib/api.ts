const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, options: RequestInit = {}, token?: string): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string> | undefined),
  };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  // Needed so the browser sends/receives the httpOnly refresh_token and
  // readable csrf_token cookies (see api.refresh/api.logout below) —
  // frontend (:3000) and backend (:8000) are different origins in dev,
  // and fetch doesn't include cookies cross-origin by default.
  const res = await fetch(`${API_BASE_URL}${path}`, { ...options, headers, credentials: "include" });

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      // response had no JSON body
    }
    throw new ApiError(res.status, typeof detail === "string" ? detail : JSON.stringify(detail));
  }

  if (res.status === 204) {
    return undefined as T;
  }
  return res.json() as Promise<T>;
}

async function requestMultipart<T>(path: string, formData: FormData, token: string): Promise<T> {
  // Deliberately no Content-Type header — the browser sets
  // multipart/form-data with the correct boundary itself.
  const res = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    credentials: "include",
    body: formData,
  });

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      // response had no JSON body
    }
    throw new ApiError(res.status, typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return res.json() as Promise<T>;
}

function readCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

export interface User {
  id: string;
  email: string;
  full_name: string;
  is_active: boolean;
  is_verified: boolean;
  is_platform_admin: boolean;
  mfa_enabled: boolean;
}

export interface PlatformStats {
  generated_at: string;
  total_users: number;
  active_users: number;
  signups_last_30_days: number;
  total_organizations: number;
  total_workspaces: number;
  total_datasets: number;
  total_dataset_versions: number;
  total_analysis_runs: number;
  total_reports_generated: number;
  total_storage_bytes: number;
  subscriptions_by_plan: Record<string, number>;
  estimated_mrr_gbp: number;
  failed_logins_last_24h: number;
}

export interface AdminUser {
  id: string;
  email: string;
  full_name: string;
  is_active: boolean;
  is_verified: boolean;
  is_platform_admin: boolean;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface MfaRequired {
  mfa_required: true;
  challenge_token: string;
}

export function isMfaRequired(result: TokenResponse | MfaRequired): result is MfaRequired {
  return "mfa_required" in result;
}

export interface MfaSetup {
  secret: string;
  otpauth_url: string;
}

export interface Workspace {
  id: string;
  name: string;
  industry: string;
  owner_user_id: string | null;
  organization_id: string | null;
  kpi_window_months: number | null;
}

export interface Property {
  id: string;
  workspace_id: string;
  address_line1: string;
  address_line2: string | null;
  city: string;
  postcode: string;
  country: string;
  property_type: string | null;
  created_by_user_id: string | null;
}

export interface Tenancy {
  id: string;
  property_id: string;
  tenant_name: string;
  tenant_email: string | null;
  rent_amount_gbp: number;
  rent_frequency: "weekly" | "monthly" | "quarterly";
  start_date: string;
  end_date: string | null;
  status: "upcoming" | "active" | "ended";
  created_by_user_id: string | null;
}

export interface RentLedgerEntry {
  id: string;
  tenancy_id: string;
  entry_type: "charge" | "payment" | "adjustment" | "refund";
  amount_gbp: number;
  entry_date: string;
  description: string | null;
  created_by_user_id: string | null;
}

export interface TenancyBalance {
  tenancy_id: string;
  balance_gbp: number;
}

export interface PropertyKPIs {
  total_properties: number;
  active_tenancies: number;
  expected_monthly_rent_gbp: number;
  collected_this_period_gbp: number;
  outstanding_balance_gbp: number;
  arrears_count: number;
}

export type DocumentType =
  | "tenancy_agreement"
  | "gas_safety_certificate"
  | "eicr"
  | "epc"
  | "deposit_protection_certificate"
  | "right_to_rent_check"
  | "insurance_certificate"
  | "inventory_report"
  | "other";

export interface PropertyDocument {
  id: string;
  property_id: string;
  tenancy_id: string | null;
  document_type: DocumentType;
  title: string;
  filename: string;
  content_type: string;
  file_size_bytes: number;
  expiry_date: string | null;
  uploaded_by_user_id: string | null;
}

export interface ColumnProfile {
  name: string;
  inferred_type: string;
  suggested_type: string;
  null_count: number;
  null_ratio: number;
  distinct_count: number;
  sample_values: unknown[];
  stats: Record<string, unknown>;
  flags: string[];
  invalid_count: number;
  invalid_ratio: number;
}

export interface DataQualityIssue {
  severity: "info" | "warning";
  issue_type: string;
  column: string | null;
  detail: string;
}

export interface TableProfile {
  sheet_name: string;
  row_count: number;
  column_count: number;
  duplicate_row_count: number;
  columns: ColumnProfile[];
  issues: DataQualityIssue[];
  quality_score: number;
}

export interface DatasetTable {
  id: string;
  sheet_name: string;
  row_count: number;
  column_count: number;
  profile: TableProfile;
  confirmed_schema: Record<string, string> | null;
}

export interface DatasetVersion {
  id: string;
  dataset_id: string;
  version_number: number;
  status: string;
  source_filename: string | null;
  file_size_bytes: number | null;
  derived_from_version_id: string | null;
  error_message: string | null;
  tables: DatasetTable[];
}

export interface ColumnComparison {
  column: string;
  type: string;
  sum_before: number | null;
  sum_after: number | null;
  sum_delta: number | null;
  sum_pct_change: number | null;
  mean_before: number | null;
  mean_after: number | null;
  distinct_before: number | null;
  distinct_after: number | null;
  most_common_before: string | null;
  most_common_after: string | null;
}

export interface VersionComparison {
  version_a: number;
  version_b: number;
  sheet_name: string;
  row_count_before: number;
  row_count_after: number;
  row_count_delta: number;
  row_count_pct_change: number | null;
  columns_added: string[];
  columns_removed: string[];
  common_columns: string[];
  column_comparisons: ColumnComparison[];
}

export interface Dataset {
  id: string;
  workspace_id: string;
  name: string;
  created_by_user_id: string;
}

export interface DatasetDetail extends Dataset {
  versions: DatasetVersion[];
}

export interface ReportMeta {
  id: string;
  dataset_table_id: string;
  report_type: string;
  file_size_bytes: number;
  generated_by_user_id: string;
}

export interface ScheduledReport {
  id: string;
  workspace_id: string;
  dataset_table_id: string;
  report_type: string;
  frequency: string;
  next_run_at: string;
  last_run_at: string | null;
  last_error: string | null;
  last_email_sent_at: string | null;
  last_email_error: string | null;
  is_active: boolean;
}

export interface ToolCall {
  name: string;
  input: Record<string, unknown>;
  result: Record<string, unknown> | null;
  error: string | null;
}

export interface AskResponse {
  conversation_id: string;
  answer: string;
  tool_calls: ToolCall[];
  hit_iteration_limit: boolean;
}

export interface AIMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  tool_calls: ToolCall[] | null;
  created_at: string;
}

export interface AIConversation {
  id: string;
  workspace_id: string;
  dataset_id: string;
  title: string | null;
  created_by_user_id: string;
  created_at: string;
  messages: AIMessage[];
}

export interface Plan {
  plan_id: string;
  name: string;
  monthly_price_gbp: number | null;
  max_analyses_per_month: number | null;
  max_upload_size_bytes: number;
  max_saved_datasets: number | null;
  max_team_members: number | null;
  self_serve: boolean;
}

export interface Subscription {
  id: string;
  owner_user_id: string | null;
  organization_id: string | null;
  plan_id: string;
  status: string;
  billing_period: string | null;
  current_period_end: string | null;
  cancel_at_period_end: boolean;
  past_due_since: string | null;
  downgrade_scheduled_for: string | null;
  usage: {
    period_key: string;
    analyses_used: number;
    analyses_limit: number | null;
    resets_at: string;
  };
}

export interface UsageHistoryEntry {
  period_key: string;
  analyses_count: number;
}

export interface KPIResult {
  kpi_id: string;
  name: string;
  format: string;
  value: number | null;
  formatted: string;
  error: string | null;
}

export interface IndustryKPIResponse {
  analysis_run_id: string;
  industry_id: string;
  pack_name: string;
  field_mapping: Record<string, string | null>;
  missing_required_fields: string[];
  kpis: KPIResult[];
  compliance_caveat: string | null;
  window_months_used: number;
}

export interface FieldMappingEntry {
  canonical_field: string;
  description: string;
  required_for_pack: boolean;
  matched_column: string | null;
}

export interface FieldMapping {
  industry_id: string;
  pack_name: string;
  fields: FieldMappingEntry[];
  available_columns: string[];
  missing_required_fields: string[];
  is_confirmed: boolean;
}

export interface WidgetValue {
  kind?: string;
  value?: number | null;
  formatted?: string;
  result?: Record<string, unknown>;
  error?: string | null;
}

export interface DashboardWidgetOut {
  id: string;
  widget_type: "kpi" | "chart";
  title: string;
  config: Record<string, unknown>;
  position: number;
  value: WidgetValue | null;
}

export interface Dashboard {
  id: string;
  workspace_id: string;
  dataset_table_id: string;
  name: string;
  widgets: DashboardWidgetOut[];
}

export interface DashboardSummary {
  id: string;
  workspace_id: string;
  dataset_table_id: string;
  name: string;
  widget_count: number;
}

export interface KPIDefinition {
  kpi_id: string;
  name: string;
  description: string;
  format: string;
}

export interface IndustryPack {
  industry_id: string;
  name: string;
  kpis: KPIDefinition[];
  suggested_questions: string[];
  report_templates: string[];
}

export interface ToolParameter {
  name: string;
  type: "string" | "number" | "integer";
  description: string;
  required: boolean;
  enum: string[] | null;
  default: unknown;
}

export interface ToolSpec {
  name: string;
  description: string;
  parameters: ToolParameter[];
}

export interface DashboardComment {
  id: string;
  dashboard_id: string;
  author_user_id: string;
  content: string;
  created_at: string;
}

export interface ScenarioKPIDelta {
  kpi_id: string;
  name: string;
  format: string;
  baseline_value: number | null;
  scenario_value: number | null;
  delta: number | null;
  pct_change: number | null;
}

export interface ScenarioAdjustment {
  column: string;
  adjustment_type: "percentage" | "fixed_amount" | "set_value";
  value: number;
}

export interface ScenarioResponse {
  industry_id: string;
  adjustments_applied: ScenarioAdjustment[];
  baseline_kpis: KPIResult[];
  scenario_kpis: KPIResult[];
  kpi_deltas: ScenarioKPIDelta[];
}

export interface SavedScenario {
  id: string;
  workspace_id: string;
  dataset_table_id: string;
  name: string;
  adjustments: ScenarioAdjustment[];
  created_by_user_id: string;
  created_at: string;
}

export interface ApiKeyInfo {
  id: string;
  name: string;
  key_prefix: string;
  last_used_at: string | null;
  is_active: boolean;
  created_at: string;
}

export interface ApiKeyCreated {
  id: string;
  name: string;
  key_prefix: string;
  raw_key: string;
  created_at: string;
}

export const WEBHOOK_EVENT_TYPES = ["dataset.uploaded", "report.generated"] as const;

export interface WebhookSubscription {
  id: string;
  url: string;
  event_types: string[];
  is_active: boolean;
  last_delivery_at: string | null;
  last_delivery_status: number | null;
  last_delivery_error: string | null;
  created_at: string;
}

export interface WebhookCreated {
  id: string;
  url: string;
  event_types: string[];
  secret: string;
  created_at: string;
}

export interface InvitePreview {
  organization_name: string;
  role: string;
  email: string;
}

export const MEMBERSHIP_ROLES = ["owner", "administrator", "analyst", "viewer", "auditor"] as const;

export interface Organization {
  id: string;
  name: string;
  slug: string;
}

export interface Membership {
  id: string;
  user_id: string;
  organization_id: string;
  role: string;
  user_email: string;
  user_full_name: string;
}

// What POST /organizations/{id}/invite returns for an existing user —
// MembershipOut on the backend, deliberately narrower than Membership
// above (GET .../members, which joins in the user row) — it has no
// user_email/user_full_name, since the invite endpoint never looked the
// rest of that row up.
export interface MembershipCreated {
  id: string;
  user_id: string;
  organization_id: string;
  role: string;
}

export interface PendingInvite {
  status: string;
  email: string;
  role: string;
}

export interface AuditLogEntry {
  id: string;
  event_type: string;
  actor_user_id: string | null;
  organization_id: string | null;
  workspace_id: string | null;
  created_at: string;
  event_metadata: Record<string, unknown>;
}

export const api = {
  register: (email: string, password: string, full_name: string, inviteToken?: string) =>
    request<User>("/api/v1/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password, full_name, invite_token: inviteToken ?? null }),
    }),

  login: (email: string, password: string) =>
    request<TokenResponse | MfaRequired>("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  mfaVerify: (challengeToken: string, code: string) =>
    request<TokenResponse>("/api/v1/auth/mfa/verify", {
      method: "POST",
      body: JSON.stringify({ challenge_token: challengeToken, code }),
    }),

  mfaSetup: (token: string) => request<MfaSetup>("/api/v1/auth/mfa/setup", { method: "POST" }, token),

  mfaEnable: (token: string, code: string) =>
    request<User>("/api/v1/auth/mfa/enable", { method: "POST", body: JSON.stringify({ code }) }, token),

  mfaDisable: (token: string, password: string) =>
    request<User>(
      "/api/v1/auth/mfa/disable",
      { method: "POST", body: JSON.stringify({ password }) },
      token
    ),

  // Relies on the httpOnly refresh_token cookie the backend set on
  // login — there's nothing to pass in the body. The CSRF header is
  // required specifically because this is the one request that
  // authenticates itself purely via an ambient cookie (every other
  // request instead carries an explicit Authorization header, which a
  // forged cross-site request can't produce) — see /auth/refresh in
  // app/api/v1/routers/auth.py for the matching server-side check.
  refresh: () => {
    const csrfToken = readCookie("csrf_token");
    return request<TokenResponse>("/api/v1/auth/refresh", {
      method: "POST",
      body: JSON.stringify({}),
      headers: csrfToken ? { "X-CSRF-Token": csrfToken } : {},
    });
  },

  logout: () => request<void>("/api/v1/auth/logout", { method: "POST" }),

  ssoLogin: () => request<{ authorization_url: string }>("/api/v1/sso/login"),

  ssoCallback: (code: string, state: string) =>
    request<TokenResponse>("/api/v1/sso/callback", {
      method: "POST",
      body: JSON.stringify({ code, state }),
    }),

  verifyEmail: (token: string) =>
    request<User>("/api/v1/auth/verify-email", { method: "POST", body: JSON.stringify({ token }) }),

  resendVerification: (email: string) =>
    request<{ message: string }>("/api/v1/auth/resend-verification", {
      method: "POST",
      body: JSON.stringify({ email }),
    }),

  forgotPassword: (email: string) =>
    request<{ message: string }>("/api/v1/auth/forgot-password", {
      method: "POST",
      body: JSON.stringify({ email }),
    }),

  resetPassword: (token: string, newPassword: string) =>
    request<{ message: string }>("/api/v1/auth/reset-password", {
      method: "POST",
      body: JSON.stringify({ token, new_password: newPassword }),
    }),

  previewInvite: (token: string) => request<InvitePreview>(`/api/v1/organizations/invites/${token}`, {}),

  listOrganizations: (token: string) => request<Organization[]>("/api/v1/organizations", {}, token),

  createOrganization: (token: string, name: string) =>
    request<Organization>("/api/v1/organizations", { method: "POST", body: JSON.stringify({ name }) }, token),

  listOrganizationMembers: (token: string, organizationId: string) =>
    request<Membership[]>(`/api/v1/organizations/${organizationId}/members`, {}, token),

  inviteOrganizationMember: (token: string, organizationId: string, email: string, role: string) =>
    request<MembershipCreated | PendingInvite>(
      `/api/v1/organizations/${organizationId}/invite`,
      { method: "POST", body: JSON.stringify({ email, role }) },
      token
    ),

  removeOrganizationMember: (token: string, organizationId: string, membershipId: string) =>
    request<void>(
      `/api/v1/organizations/${organizationId}/members/${membershipId}`,
      { method: "DELETE" },
      token
    ),

  updateMembershipRole: (token: string, organizationId: string, membershipId: string, role: string) =>
    request<MembershipCreated>(
      `/api/v1/organizations/${organizationId}/members/${membershipId}`,
      { method: "PATCH", body: JSON.stringify({ role }) },
      token
    ),

  getOrganizationAuditLog: (token: string, organizationId: string) =>
    request<AuditLogEntry[]>(`/api/v1/organizations/${organizationId}/audit-log`, {}, token),

  getMyAuditLog: (token: string) => request<AuditLogEntry[]>("/api/v1/users/me/audit-log", {}, token),

  me: (token: string) => request<User>("/api/v1/users/me", {}, token),

  getPlatformStats: (token: string) => request<PlatformStats>("/api/v1/admin/stats", {}, token),

  listPlatformUsers: (token: string) => request<AdminUser[]>("/api/v1/admin/users", {}, token),

  listWorkspaces: (token: string) => request<Workspace[]>("/api/v1/workspaces", {}, token),

  createWorkspace: (token: string, name: string, industry: string, organizationId?: string) =>
    request<Workspace>(
      "/api/v1/workspaces",
      { method: "POST", body: JSON.stringify({ name, industry, organization_id: organizationId ?? null }) },
      token
    ),

  getWorkspace: (token: string, workspaceId: string) =>
    request<Workspace>(`/api/v1/workspaces/${workspaceId}`, {}, token),

  updateWorkspaceSettings: (token: string, workspaceId: string, kpiWindowMonths: number | null) =>
    request<Workspace>(
      `/api/v1/workspaces/${workspaceId}/settings`,
      { method: "PATCH", body: JSON.stringify({ kpi_window_months: kpiWindowMonths }) },
      token
    ),

  listDatasets: (token: string, workspaceId: string) =>
    request<Dataset[]>(`/api/v1/workspaces/${workspaceId}/datasets`, {}, token),

  getDataset: (token: string, datasetId: string) =>
    request<DatasetDetail>(`/api/v1/datasets/${datasetId}`, {}, token),

  getDatasetTable: (token: string, tableId: string) =>
    request<DatasetTable>(`/api/v1/dataset-tables/${tableId}`, {}, token),

  listTools: (token: string) => request<ToolSpec[]>("/api/v1/tools", {}, token),

  uploadDataset: (token: string, workspaceId: string, file: File, name: string) => {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("name", name);
    return requestMultipart<DatasetVersion>(`/api/v1/workspaces/${workspaceId}/datasets`, formData, token);
  },

  addDatasetVersion: (token: string, workspaceId: string, datasetId: string, file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("dataset_id", datasetId);
    return requestMultipart<DatasetVersion>(`/api/v1/workspaces/${workspaceId}/datasets`, formData, token);
  },

  confirmSchema: (token: string, tableId: string, columnTypes: Record<string, string>) =>
    request<DatasetVersion>(
      `/api/v1/dataset-tables/${tableId}/schema`,
      { method: "PATCH", body: JSON.stringify({ column_types: columnTypes }) },
      token
    ),

  deduplicateTable: (token: string, tableId: string) =>
    request<DatasetVersion>(`/api/v1/dataset-tables/${tableId}/deduplicate`, { method: "POST" }, token),

  compareVersions: (token: string, datasetId: string, versionA: number, versionB: number, sheetName?: string) =>
    request<VersionComparison>(
      `/api/v1/datasets/${datasetId}/compare-versions`,
      {
        method: "POST",
        body: JSON.stringify({ version_a: versionA, version_b: versionB, sheet_name: sheetName ?? null }),
      },
      token
    ),

  fillMissingValues: (
    token: string,
    tableId: string,
    column: string,
    strategy: string,
    constantValue?: string | number | boolean
  ) =>
    request<DatasetVersion>(
      `/api/v1/dataset-tables/${tableId}/fill-missing-values`,
      { method: "POST", body: JSON.stringify({ column, strategy, constant_value: constantValue ?? null }) },
      token
    ),

  normalizeText: (
    token: string,
    tableId: string,
    column: string,
    options: { case?: string; trim?: boolean; collapse_whitespace?: boolean }
  ) =>
    request<DatasetVersion>(
      `/api/v1/dataset-tables/${tableId}/normalize-text`,
      { method: "POST", body: JSON.stringify({ column, ...options }) },
      token
    ),

  filterRows: (token: string, tableId: string, column: string, operator: string, value?: string | number | boolean) =>
    request<DatasetVersion>(
      `/api/v1/dataset-tables/${tableId}/filter-rows`,
      { method: "POST", body: JSON.stringify({ column, operator, value: value ?? null }) },
      token
    ),

  calculatedField: (
    token: string,
    tableId: string,
    payload: {
      new_column_name: string;
      left_column: string;
      operator: string;
      right_column?: string;
      right_value?: string | number;
      separator?: string;
    }
  ) =>
    request<DatasetVersion>(
      `/api/v1/dataset-tables/${tableId}/calculated-field`,
      { method: "POST", body: JSON.stringify(payload) },
      token
    ),

  mergeColumns: (
    token: string,
    tableId: string,
    payload: { columns: string[]; new_column_name: string; separator?: string; drop_source_columns?: boolean }
  ) =>
    request<DatasetVersion>(
      `/api/v1/dataset-tables/${tableId}/merge-columns`,
      { method: "POST", body: JSON.stringify(payload) },
      token
    ),

  splitColumn: (
    token: string,
    tableId: string,
    payload: { column: string; delimiter: string; new_column_names?: string[]; drop_source_column?: boolean }
  ) =>
    request<DatasetVersion>(
      `/api/v1/dataset-tables/${tableId}/split-column`,
      { method: "POST", body: JSON.stringify(payload) },
      token
    ),

  standardizeColumn: (token: string, tableId: string, column: string, kind: string, dateFormat?: string) =>
    request<DatasetVersion>(
      `/api/v1/dataset-tables/${tableId}/standardize-column`,
      { method: "POST", body: JSON.stringify({ column, kind, date_format: dateFormat ?? null }) },
      token
    ),

  pivotTable: (
    token: string,
    tableId: string,
    payload: { index_columns: string[]; pivot_column: string; value_column: string; aggregate_function?: string }
  ) =>
    request<DatasetVersion>(
      `/api/v1/dataset-tables/${tableId}/pivot`,
      { method: "POST", body: JSON.stringify(payload) },
      token
    ),

  unpivotTable: (
    token: string,
    tableId: string,
    payload: { id_columns: string[]; value_columns: string[]; variable_name?: string; value_name?: string }
  ) =>
    request<DatasetVersion>(
      `/api/v1/dataset-tables/${tableId}/unpivot`,
      { method: "POST", body: JSON.stringify(payload) },
      token
    ),

  groupByTable: (
    token: string,
    tableId: string,
    payload: {
      group_by_columns: string[];
      aggregations: { column?: string; function: string; output_name: string }[];
    }
  ) =>
    request<DatasetVersion>(
      `/api/v1/dataset-tables/${tableId}/group-by`,
      { method: "POST", body: JSON.stringify(payload) },
      token
    ),

  generateDataQualityReport: (token: string, tableId: string) =>
    request<ReportMeta>(`/api/v1/dataset-tables/${tableId}/reports/data-quality`, { method: "POST" }, token),

  downloadReport: async (token: string, reportId: string): Promise<Blob> => {
    const res = await fetch(`${API_BASE_URL}/api/v1/reports/${reportId}/download`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) {
      throw new ApiError(res.status, "Could not download report.");
    }
    return res.blob();
  },

  askQuestion: (token: string, tableId: string, question: string, conversationId?: string) =>
    request<AskResponse>(
      `/api/v1/dataset-tables/${tableId}/ask`,
      { method: "POST", body: JSON.stringify({ question, conversation_id: conversationId ?? null }) },
      token
    ),

  listConversations: (token: string, datasetId: string) =>
    request<AIConversation[]>(`/api/v1/datasets/${datasetId}/conversations`, {}, token),

  getConversation: (token: string, conversationId: string) =>
    request<AIConversation>(`/api/v1/ai-conversations/${conversationId}`, {}, token),

  listPlans: () => request<Plan[]>("/api/v1/billing/plans", {}),

  getSubscription: (token: string) => request<Subscription>("/api/v1/billing/subscription", {}, token),

  getUsageHistory: (token: string) =>
    request<UsageHistoryEntry[]>("/api/v1/billing/usage-history", {}, token),

  createCheckoutSession: (token: string, planId: string, billingPeriod: "monthly" | "annual" = "monthly") =>
    request<{ checkout_url: string }>(
      "/api/v1/billing/checkout-session",
      { method: "POST", body: JSON.stringify({ plan_id: planId, billing_period: billingPeriod }) },
      token
    ),

  createPortalSession: (token: string) =>
    request<{ portal_url: string }>("/api/v1/billing/portal-session", { method: "POST", body: "{}" }, token),

  computeIndustryKpis: (token: string, tableId: string) =>
    request<IndustryKPIResponse>(`/api/v1/dataset-tables/${tableId}/industry-kpis`, { method: "POST" }, token),

  getFieldMapping: (token: string, tableId: string) =>
    request<FieldMapping>(`/api/v1/dataset-tables/${tableId}/field-mapping`, {}, token),

  confirmFieldMapping: (token: string, tableId: string, mapping: Record<string, string | null>) =>
    request<FieldMapping>(
      `/api/v1/dataset-tables/${tableId}/field-mapping`,
      { method: "PATCH", body: JSON.stringify({ mapping }) },
      token
    ),

  generateCommercialPropertyReport: (token: string, tableId: string) =>
    request<ReportMeta>(
      `/api/v1/dataset-tables/${tableId}/reports/commercial-property-portfolio`,
      { method: "POST" },
      token
    ),

  generateResidentialPropertyReport: (token: string, tableId: string) =>
    request<ReportMeta>(
      `/api/v1/dataset-tables/${tableId}/reports/residential-property-portfolio`,
      { method: "POST" },
      token
    ),

  generateResidentialRepairsMaintenanceReport: (token: string, tableId: string) =>
    request<ReportMeta>(
      `/api/v1/dataset-tables/${tableId}/reports/residential-repairs-maintenance`,
      { method: "POST" },
      token
    ),

  generateSocialHousingReport: (token: string, tableId: string) =>
    request<ReportMeta>(
      `/api/v1/dataset-tables/${tableId}/reports/social-housing-asset`,
      { method: "POST" },
      token
    ),

  generateSocialHousingComplianceExceptionsReport: (token: string, tableId: string) =>
    request<ReportMeta>(
      `/api/v1/dataset-tables/${tableId}/reports/social-housing-compliance-exceptions`,
      { method: "POST" },
      token
    ),

  generateBusinessFinanceReport: (token: string, tableId: string) =>
    request<ReportMeta>(
      `/api/v1/dataset-tables/${tableId}/reports/business-performance`,
      { method: "POST" },
      token
    ),

  generatePublicSectorBudgetVarianceReport: (token: string, tableId: string) =>
    request<ReportMeta>(
      `/api/v1/dataset-tables/${tableId}/reports/public-sector-budget-variance`,
      { method: "POST" },
      token
    ),

  generatePupilAttendanceReport: (token: string, tableId: string) =>
    request<ReportMeta>(
      `/api/v1/dataset-tables/${tableId}/reports/pupil-attendance-performance`,
      { method: "POST" },
      token
    ),

  generateExecutiveIntelligenceReport: (token: string, tableId: string) =>
    request<ReportMeta>(
      `/api/v1/dataset-tables/${tableId}/reports/executive-intelligence`,
      { method: "POST" },
      token
    ),

  listDashboards: (token: string, workspaceId: string) =>
    request<DashboardSummary[]>(`/api/v1/workspaces/${workspaceId}/dashboards`, {}, token),

  autoGenerateDashboard: (token: string, workspaceId: string, tableId: string, name: string) =>
    request<Dashboard>(
      `/api/v1/workspaces/${workspaceId}/dashboards/auto-generate`,
      { method: "POST", body: JSON.stringify({ name, dataset_table_id: tableId }) },
      token
    ),

  getDashboard: (token: string, dashboardId: string) =>
    request<Dashboard>(`/api/v1/dashboards/${dashboardId}`, {}, token),

  reorderDashboardWidgets: (token: string, dashboardId: string, widgetIds: string[]) =>
    request<Dashboard>(
      `/api/v1/dashboards/${dashboardId}/widgets/reorder`,
      { method: "PATCH", body: JSON.stringify({ widget_ids: widgetIds }) },
      token
    ),

  addDashboardWidget: (
    token: string,
    dashboardId: string,
    widget: { widget_type: "kpi" | "chart"; title: string; config: Record<string, unknown> }
  ) =>
    request<Dashboard>(
      `/api/v1/dashboards/${dashboardId}/widgets`,
      { method: "POST", body: JSON.stringify(widget) },
      token
    ),

  removeDashboardWidget: (token: string, dashboardId: string, widgetId: string) =>
    request<void>(`/api/v1/dashboards/${dashboardId}/widgets/${widgetId}`, { method: "DELETE" }, token),

  getIndustryPack: (token: string, industryId: string) =>
    request<IndustryPack>(`/api/v1/industry-packs/${industryId}`, {}, token),

  listIndustryPacks: (token: string) => request<IndustryPack[]>("/api/v1/industry-packs", {}, token),

  deleteDashboard: (token: string, dashboardId: string) =>
    request<void>(`/api/v1/dashboards/${dashboardId}`, { method: "DELETE" }, token),

  listComments: (token: string, dashboardId: string) =>
    request<DashboardComment[]>(`/api/v1/dashboards/${dashboardId}/comments`, {}, token),

  addComment: (token: string, dashboardId: string, content: string) =>
    request<DashboardComment>(
      `/api/v1/dashboards/${dashboardId}/comments`,
      { method: "POST", body: JSON.stringify({ content }) },
      token
    ),

  runScenario: (token: string, tableId: string, adjustments: ScenarioAdjustment[]) =>
    request<ScenarioResponse>(
      `/api/v1/dataset-tables/${tableId}/scenario`,
      { method: "POST", body: JSON.stringify({ adjustments }) },
      token
    ),

  listSavedScenarios: (token: string, workspaceId: string, datasetTableId?: string) =>
    request<SavedScenario[]>(
      `/api/v1/workspaces/${workspaceId}/saved-scenarios${datasetTableId ? `?dataset_table_id=${datasetTableId}` : ""}`,
      {},
      token
    ),

  createSavedScenario: (
    token: string,
    workspaceId: string,
    payload: { dataset_table_id: string; name: string; adjustments: ScenarioAdjustment[] }
  ) =>
    request<SavedScenario>(
      `/api/v1/workspaces/${workspaceId}/saved-scenarios`,
      { method: "POST", body: JSON.stringify(payload) },
      token
    ),

  deleteSavedScenario: (token: string, savedScenarioId: string) =>
    request<void>(`/api/v1/saved-scenarios/${savedScenarioId}`, { method: "DELETE" }, token),

  runSavedScenario: (token: string, savedScenarioId: string) =>
    request<ScenarioResponse>(`/api/v1/saved-scenarios/${savedScenarioId}/run`, { method: "POST" }, token),

  listApiKeys: (token: string) => request<ApiKeyInfo[]>("/api/v1/api-keys", {}, token),

  createApiKey: (token: string, name: string) =>
    request<ApiKeyCreated>("/api/v1/api-keys", { method: "POST", body: JSON.stringify({ name }) }, token),

  revokeApiKey: (token: string, keyId: string) =>
    request<void>(`/api/v1/api-keys/${keyId}`, { method: "DELETE" }, token),

  listWebhooks: (token: string, workspaceId: string) =>
    request<WebhookSubscription[]>(`/api/v1/workspaces/${workspaceId}/webhooks`, {}, token),

  createWebhook: (token: string, workspaceId: string, url: string, eventTypes: string[]) =>
    request<WebhookCreated>(
      `/api/v1/workspaces/${workspaceId}/webhooks`,
      { method: "POST", body: JSON.stringify({ url, event_types: eventTypes }) },
      token
    ),

  deleteWebhook: (token: string, webhookId: string) =>
    request<void>(`/api/v1/webhooks/${webhookId}`, { method: "DELETE" }, token),

  testWebhook: (token: string, webhookId: string) =>
    request<WebhookSubscription>(`/api/v1/webhooks/${webhookId}/test`, { method: "POST" }, token),

  listScheduledReports: (token: string, workspaceId: string) =>
    request<ScheduledReport[]>(`/api/v1/workspaces/${workspaceId}/scheduled-reports`, {}, token),

  createScheduledReport: (
    token: string,
    workspaceId: string,
    payload: { dataset_table_id: string; report_type: string; frequency: string }
  ) =>
    request<ScheduledReport>(
      `/api/v1/workspaces/${workspaceId}/scheduled-reports`,
      { method: "POST", body: JSON.stringify(payload) },
      token
    ),

  deleteScheduledReport: (token: string, scheduledReportId: string) =>
    request<void>(`/api/v1/scheduled-reports/${scheduledReportId}`, { method: "DELETE" }, token),

  listProperties: (token: string, workspaceId: string) =>
    request<Property[]>(`/api/v1/workspaces/${workspaceId}/properties`, {}, token),

  getPropertyKpis: (token: string, workspaceId: string) =>
    request<PropertyKPIs>(`/api/v1/workspaces/${workspaceId}/properties/kpis`, {}, token),

  createProperty: (
    token: string,
    workspaceId: string,
    payload: {
      address_line1: string;
      address_line2?: string;
      city: string;
      postcode: string;
      country?: string;
      property_type?: string;
    }
  ) =>
    request<Property>(
      `/api/v1/workspaces/${workspaceId}/properties`,
      { method: "POST", body: JSON.stringify(payload) },
      token
    ),

  getProperty: (token: string, propertyId: string) =>
    request<Property>(`/api/v1/properties/${propertyId}`, {}, token),

  deleteProperty: (token: string, propertyId: string) =>
    request<void>(`/api/v1/properties/${propertyId}`, { method: "DELETE" }, token),

  listTenancies: (token: string, propertyId: string) =>
    request<Tenancy[]>(`/api/v1/properties/${propertyId}/tenancies`, {}, token),

  createTenancy: (
    token: string,
    propertyId: string,
    payload: {
      tenant_name: string;
      tenant_email?: string;
      rent_amount_gbp: number;
      rent_frequency?: "weekly" | "monthly" | "quarterly";
      start_date: string;
      end_date?: string;
      status?: "upcoming" | "active" | "ended";
    }
  ) =>
    request<Tenancy>(
      `/api/v1/properties/${propertyId}/tenancies`,
      { method: "POST", body: JSON.stringify(payload) },
      token
    ),

  updateTenancy: (token: string, tenancyId: string, status: Tenancy["status"], endDate?: string) =>
    request<Tenancy>(
      `/api/v1/tenancies/${tenancyId}`,
      { method: "PATCH", body: JSON.stringify({ status, end_date: endDate ?? null }) },
      token
    ),

  listLedgerEntries: (token: string, tenancyId: string) =>
    request<RentLedgerEntry[]>(`/api/v1/tenancies/${tenancyId}/ledger-entries`, {}, token),

  createLedgerEntry: (
    token: string,
    tenancyId: string,
    payload: { entry_type: RentLedgerEntry["entry_type"]; amount_gbp: number; entry_date: string; description?: string }
  ) =>
    request<RentLedgerEntry>(
      `/api/v1/tenancies/${tenancyId}/ledger-entries`,
      { method: "POST", body: JSON.stringify(payload) },
      token
    ),

  getTenancyBalance: (token: string, tenancyId: string) =>
    request<TenancyBalance>(`/api/v1/tenancies/${tenancyId}/balance`, {}, token),

  listDocuments: (token: string, propertyId: string, tenancyId?: string) =>
    request<PropertyDocument[]>(
      `/api/v1/properties/${propertyId}/documents${tenancyId ? `?tenancy_id=${tenancyId}` : ""}`,
      {},
      token
    ),

  uploadDocument: (
    token: string,
    propertyId: string,
    file: File,
    payload: { title: string; document_type: DocumentType; tenancy_id?: string; expiry_date?: string }
  ) => {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("title", payload.title);
    formData.append("document_type", payload.document_type);
    if (payload.tenancy_id) formData.append("tenancy_id", payload.tenancy_id);
    if (payload.expiry_date) formData.append("expiry_date", payload.expiry_date);
    return requestMultipart<PropertyDocument>(`/api/v1/properties/${propertyId}/documents`, formData, token);
  },

  deleteDocument: (token: string, documentId: string) =>
    request<void>(`/api/v1/documents/${documentId}`, { method: "DELETE" }, token),

  downloadDocument: async (token: string, documentId: string): Promise<Blob> => {
    const res = await fetch(`${API_BASE_URL}/api/v1/documents/${documentId}/download`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) {
      throw new ApiError(res.status, "Could not download document.");
    }
    return res.blob();
  },
};
