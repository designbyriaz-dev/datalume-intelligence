import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api";
import LoginPage from "./page";

// vi.hoisted is required for every mock referenced inside a vi.mock
// factory below — those factories are hoisted above normal module-level
// statements, so a plain const would still be in its temporal dead zone
// when they run.
const { mockPush, mockLogin, mockCompleteMfaLogin, mockSsoLogin } = vi.hoisted(() => ({
  mockPush: vi.fn(),
  mockLogin: vi.fn(),
  mockCompleteMfaLogin: vi.fn(),
  mockSsoLogin: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
}));

vi.mock("@/lib/auth", () => ({
  useAuth: () => ({
    user: null,
    loading: false,
    logout: vi.fn(),
    login: mockLogin,
    completeMfaLogin: mockCompleteMfaLogin,
  }),
}));

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, api: { ...actual.api, ssoLogin: mockSsoLogin } };
});

beforeEach(() => {
  vi.clearAllMocks();
});

async function fillAndSubmitCredentials(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText("Email"), "jane@example.com");
  await user.type(screen.getByLabelText("Password"), "correct-horse-battery");
  await user.click(screen.getByRole("button", { name: "Log in" }));
}

describe("LoginPage", () => {
  it("submits credentials and redirects to the dashboard on success", async () => {
    mockLogin.mockResolvedValue({ mfaRequired: false });
    const user = userEvent.setup();
    render(<LoginPage />);

    await fillAndSubmitCredentials(user);

    await waitFor(() =>
      expect(mockLogin).toHaveBeenCalledWith("jane@example.com", "correct-horse-battery")
    );
    expect(mockPush).toHaveBeenCalledWith("/dashboard");
  });

  it("shows a login error and does not redirect on invalid credentials", async () => {
    mockLogin.mockRejectedValue(new ApiError(401, "Incorrect email or password"));
    const user = userEvent.setup();
    render(<LoginPage />);

    await fillAndSubmitCredentials(user);

    expect(await screen.findByText("Incorrect email or password")).toBeInTheDocument();
    expect(mockPush).not.toHaveBeenCalled();
  });

  it("shows the MFA code step instead of redirecting when the account requires it", async () => {
    mockLogin.mockResolvedValue({ mfaRequired: true, challengeToken: "chal1" });
    const user = userEvent.setup();
    render(<LoginPage />);

    await fillAndSubmitCredentials(user);

    expect(await screen.findByText("Enter your code")).toBeInTheDocument();
    expect(mockPush).not.toHaveBeenCalled();
  });

  it("completes the MFA step with a code and redirects to the dashboard", async () => {
    mockLogin.mockResolvedValue({ mfaRequired: true, challengeToken: "chal1" });
    mockCompleteMfaLogin.mockResolvedValue(undefined);
    const user = userEvent.setup();
    render(<LoginPage />);

    await fillAndSubmitCredentials(user);
    await screen.findByText("Enter your code");

    await user.type(screen.getByLabelText("Authentication code"), "123456");
    await user.click(screen.getByRole("button", { name: "Verify" }));

    await waitFor(() => expect(mockCompleteMfaLogin).toHaveBeenCalledWith("chal1", "123456"));
    expect(mockPush).toHaveBeenCalledWith("/dashboard");
  });

  it("shows an error and does not redirect when the MFA code is wrong", async () => {
    mockLogin.mockResolvedValue({ mfaRequired: true, challengeToken: "chal1" });
    mockCompleteMfaLogin.mockRejectedValue(new ApiError(401, "Incorrect code"));
    const user = userEvent.setup();
    render(<LoginPage />);

    await fillAndSubmitCredentials(user);
    await screen.findByText("Enter your code");
    await user.type(screen.getByLabelText("Authentication code"), "000000");
    await user.click(screen.getByRole("button", { name: "Verify" }));

    expect(await screen.findByText("Incorrect code")).toBeInTheDocument();
    expect(mockPush).not.toHaveBeenCalled();
  });

  it("strips non-digit characters typed into the MFA code field", async () => {
    mockLogin.mockResolvedValue({ mfaRequired: true, challengeToken: "chal1" });
    const user = userEvent.setup();
    render(<LoginPage />);

    await fillAndSubmitCredentials(user);
    await screen.findByText("Enter your code");

    const codeInput = screen.getByLabelText("Authentication code") as HTMLInputElement;
    await user.type(codeInput, "12a3b456");
    expect(codeInput.value).toBe("123456");
  });

  it("lets the user go back to the login form from the MFA step", async () => {
    mockLogin.mockResolvedValue({ mfaRequired: true, challengeToken: "chal1" });
    const user = userEvent.setup();
    render(<LoginPage />);

    await fillAndSubmitCredentials(user);
    await screen.findByText("Enter your code");

    await user.click(screen.getByRole("button", { name: "Back to log in" }));

    expect(screen.getByRole("heading", { name: "Log in" })).toBeInTheDocument();
    expect(screen.queryByText("Enter your code")).not.toBeInTheDocument();
  });

  it("starts Google SSO redirect when clicked", async () => {
    mockSsoLogin.mockResolvedValue({ authorization_url: "https://accounts.google.com/o/oauth2/auth" });
    const user = userEvent.setup();
    render(<LoginPage />);

    await user.click(screen.getByRole("button", { name: "Continue with Google" }));

    await waitFor(() => expect(mockSsoLogin).toHaveBeenCalled());
  });
});
