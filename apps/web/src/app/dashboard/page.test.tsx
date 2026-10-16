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
    mockApi.createWorkspace.mockResolvedValue({
      id: "ws2",
      name: "General Thing",
      industry: "public_sector",
      owner_user_id: "u1",
      organization_id: null,
      kpi_window_months: null,
    });
    const user = userEvent.setup();
    render(<DashboardPage />);

    await user.click(await screen.findByText("Something else"));
    expect(screen.getByLabelText("Industry")).toBeInTheDocument();

    await user.type(screen.getByLabelText("Workspace name"), "General Thing");
    await user.selectOptions(screen.getByLabelText("Industry"), "public_sector");
    await user.click(screen.getByRole("button", { name: "Create workspace" }));

    await waitFor(() =>
      expect(mockApi.createWorkspace).toHaveBeenCalledWith("tok1", "General Thing", "public_sector", undefined)
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
