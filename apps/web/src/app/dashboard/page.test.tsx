import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import DashboardPage from "./page";

const { mockPush } = vi.hoisted(() => ({ mockPush: vi.fn() }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
}));

const REAL_USER = {
  id: "u1",
  email: "jane@example.com",
  full_name: "Jane Doe",
  is_active: true,
  is_verified: true,
  is_platform_admin: false,
  mfa_enabled: false,
};

const { mockUseAuth } = vi.hoisted(() => ({ mockUseAuth: vi.fn() }));
vi.mock("@/lib/auth", () => ({
  useAuth: mockUseAuth,
}));

const mockApi = vi.hoisted(() => ({
  listWorkspaces: vi.fn(),
  getSubscription: vi.fn(),
  listOrganizations: vi.fn(),
  listIndustryPacks: vi.fn(),
  createWorkspace: vi.fn(),
  createPortalSession: vi.fn(),
}));

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, api: mockApi };
});

const COMMERCIAL_PACK = {
  industry_id: "commercial_property",
  name: "Commercial Property Intelligence",
  kpis: [],
  suggested_questions: ["What's our total rent roll?", "Which leases are expiring soon?"],
  report_templates: ["commercial_property_portfolio"],
};

function authedState(overrides: Partial<ReturnType<typeof mockUseAuth>> = {}) {
  return { user: REAL_USER, token: "tok1", loading: false, ...overrides };
}

beforeEach(() => {
  vi.clearAllMocks();
  mockApi.listWorkspaces.mockResolvedValue([]);
  mockApi.getSubscription.mockResolvedValue(null);
  mockApi.listOrganizations.mockResolvedValue([]);
  mockApi.listIndustryPacks.mockResolvedValue([COMMERCIAL_PACK]);
});

describe("DashboardPage auth gating", () => {
  it("shows a loading state while auth is resolving", () => {
    mockUseAuth.mockReturnValue({ user: null, token: null, loading: true });
    render(<DashboardPage />);
    expect(screen.getByText("Loading…")).toBeInTheDocument();
  });

  it("redirects to /login when there is no authenticated user", async () => {
    mockUseAuth.mockReturnValue({ user: null, token: null, loading: false });
    render(<DashboardPage />);
    await waitFor(() => expect(mockPush).toHaveBeenCalledWith("/login"));
  });
});

describe("the guided workspace-creation flow", () => {
  beforeEach(() => {
    mockUseAuth.mockReturnValue(authedState());
  });

  it("renders a card per real industry pack plus a Something else card", async () => {
    render(<DashboardPage />);

    expect(await screen.findByText("Commercial Property Intelligence")).toBeInTheDocument();
    expect(screen.getByText("“What's our total rent roll?”")).toBeInTheDocument();
    expect(screen.getByText("Something else")).toBeInTheDocument();
  });

  it("picking a pack advances to step two with no industry dropdown", async () => {
    const user = userEvent.setup();
    render(<DashboardPage />);

    await user.click(await screen.findByText("Commercial Property Intelligence"));

    expect(screen.getByRole("heading", { name: "Commercial Property Intelligence" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Industry")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Workspace name")).toBeInTheDocument();
  });

  it("creates a workspace for the chosen pack and resets to step one", async () => {
    const created = {
      id: "ws1",
      name: "My Portfolio",
      industry: "commercial_property",
      owner_user_id: "u1",
      organization_id: null,
      kpi_window_months: null,
    };
    mockApi.createWorkspace.mockResolvedValue(created);
    const user = userEvent.setup();
    render(<DashboardPage />);

    await user.click(await screen.findByText("Commercial Property Intelligence"));
    await user.type(screen.getByLabelText("Workspace name"), "My Portfolio");
    await user.click(screen.getByRole("button", { name: "Create workspace" }));

    await waitFor(() =>
      expect(mockApi.createWorkspace).toHaveBeenCalledWith("tok1", "My Portfolio", "commercial_property", undefined)
    );
    // Back to the step-one picker.
    expect(await screen.findByText("What do you want to analyse?")).toBeInTheDocument();
    // The new workspace shows up in the list below.
    const workspaceList = screen.getByRole("heading", { name: "Your workspaces" }).closest("div")!;
    expect(within(workspaceList).getByText("My Portfolio")).toBeInTheDocument();
  });

  it("'Something else' shows the free-form industry dropdown and submits its value", async () => {
    // public_sector moved out of this fallback dropdown once it got its
    // own dedicated pack card (see OTHER_INDUSTRIES's comment) — uses
    // "education" instead, still a plain fallback option, to keep
    // testing the same free-form-dropdown behavior.
    mockApi.createWorkspace.mockResolvedValue({
      id: "ws2",
      name: "General Thing",
      industry: "education",
      owner_user_id: "u1",
      organization_id: null,
      kpi_window_months: null,
    });
    const user = userEvent.setup();
    render(<DashboardPage />);

    await user.click(await screen.findByText("Something else"));
    expect(screen.getByLabelText("Industry")).toBeInTheDocument();

    await user.type(screen.getByLabelText("Workspace name"), "General Thing");
    await user.selectOptions(screen.getByLabelText("Industry"), "education");
    await user.click(screen.getByRole("button", { name: "Create workspace" }));

    await waitFor(() =>
      expect(mockApi.createWorkspace).toHaveBeenCalledWith("tok1", "General Thing", "education", undefined)
    );
  });

  it("shows an error and stays on step two when creation fails", async () => {
    mockApi.createWorkspace.mockRejectedValue(new Error("boom"));
    const user = userEvent.setup();
    render(<DashboardPage />);

    await user.click(await screen.findByText("Commercial Property Intelligence"));
    await user.type(screen.getByLabelText("Workspace name"), "My Portfolio");
    await user.click(screen.getByRole("button", { name: "Create workspace" }));

    expect(await screen.findByText("Could not create workspace.")).toBeInTheDocument();
    // Still on step two, not reset.
    expect(screen.getByRole("heading", { name: "Commercial Property Intelligence" })).toBeInTheDocument();
  });

  it("'Choose a different type' returns to step one without creating anything", async () => {
    const user = userEvent.setup();
    render(<DashboardPage />);

    await user.click(await screen.findByText("Commercial Property Intelligence"));
    await user.click(screen.getByRole("button", { name: "← Choose a different type" }));

    expect(screen.getByText("What do you want to analyse?")).toBeInTheDocument();
    expect(mockApi.createWorkspace).not.toHaveBeenCalled();
  });
});

function pastDueSubscription(daysUntilDowngrade: number) {
  const now = Date.now();
  return {
    id: "sub1",
    owner_user_id: "u1",
    organization_id: null,
    plan_id: "professional",
    status: "past_due",
    billing_period: "monthly",
    current_period_end: null,
    cancel_at_period_end: false,
    past_due_since: new Date(now - 2 * 24 * 60 * 60 * 1000).toISOString(),
    downgrade_scheduled_for: new Date(now + daysUntilDowngrade * 24 * 60 * 60 * 1000).toISOString(),
    usage: { period_key: "2026-10", analyses_used: 3, analyses_limit: 100, resets_at: new Date(now).toISOString() },
  };
}

describe("DashboardPage past-due billing banner", () => {
  beforeEach(() => {
    mockUseAuth.mockReturnValue(authedState());
  });

  it("shows a warning banner with the days remaining when the subscription is past_due", async () => {
    mockApi.getSubscription.mockResolvedValue(pastDueSubscription(5));
    render(<DashboardPage />);

    expect(await screen.findByText(/couldn't process your last payment/i)).toBeInTheDocument();
    expect(screen.getByText(/downgraded to Free in 5 days/)).toBeInTheDocument();
  });

  it("does not show the banner for an active subscription", async () => {
    mockApi.getSubscription.mockResolvedValue({ ...pastDueSubscription(5), status: "active" });
    render(<DashboardPage />);

    await screen.findByText("Your workspaces");
    expect(screen.queryByText(/couldn't process your last payment/i)).not.toBeInTheDocument();
  });

  it("'Update payment method' opens the real Stripe billing portal", async () => {
    mockApi.getSubscription.mockResolvedValue(pastDueSubscription(1));
    mockApi.createPortalSession.mockResolvedValue({ portal_url: "https://billing.stripe.com/session/test" });
    const user = userEvent.setup();
    render(<DashboardPage />);

    await screen.findByText(/downgraded to Free in 1 day\b/);
    await user.click(screen.getByRole("button", { name: "Update payment method" }));

    await waitFor(() => expect(mockApi.createPortalSession).toHaveBeenCalledWith("tok1"));
  });

  it("shows an error if opening the billing portal fails", async () => {
    mockApi.getSubscription.mockResolvedValue(pastDueSubscription(1));
    mockApi.createPortalSession.mockRejectedValue(new Error("Stripe not configured"));
    const user = userEvent.setup();
    render(<DashboardPage />);

    await screen.findByText(/downgraded to Free/);
    await user.click(screen.getByRole("button", { name: "Update payment method" }));

    expect(await screen.findByText("Could not open billing portal.")).toBeInTheDocument();
  });
});
