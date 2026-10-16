import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AuthProvider, useAuth } from "./auth";

// vi.hoisted is required here, not a plain const — vi.mock's factory
// below is hoisted above normal module-level statements, so a plain
// const would still be in its temporal dead zone when the factory runs.
const mockApi = vi.hoisted(() => ({
  refresh: vi.fn(),
  me: vi.fn(),
  login: vi.fn(),
  mfaVerify: vi.fn(),
  ssoCallback: vi.fn(),
  register: vi.fn(),
  logout: vi.fn(),
}));

// Partial mock: keeps the real isMfaRequired type guard (and ApiError,
// types) so these tests exercise the actual discriminator production
// code uses, not a reimplementation of it — only the network-calling
// api.* methods are replaced.
vi.mock("./api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./api")>();
  return { ...actual, api: mockApi };
});

const REAL_USER = {
  id: "u1",
  email: "jane@example.com",
  full_name: "Jane Doe",
  is_active: true,
  is_verified: true,
  is_platform_admin: false,
  mfa_enabled: false,
};

function renderAuth() {
  return renderHook(() => useAuth(), { wrapper: AuthProvider });
}

beforeEach(() => {
  vi.clearAllMocks();
  mockApi.refresh.mockRejectedValue(new Error("no refresh cookie"));
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("AuthProvider mount behaviour", () => {
  it("restores a session when a valid refresh cookie exists", async () => {
    mockApi.refresh.mockResolvedValue({ access_token: "tok1", refresh_token: "r1", token_type: "bearer" });
    mockApi.me.mockResolvedValue(REAL_USER);

    const { result } = renderAuth();
    expect(result.current.loading).toBe(true);

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.token).toBe("tok1");
    expect(result.current.user).toEqual(REAL_USER);
    expect(mockApi.me).toHaveBeenCalledWith("tok1");
  });

  it("stays logged out when there is no valid refresh cookie", async () => {
    mockApi.refresh.mockRejectedValue(new Error("401"));

    const { result } = renderAuth();
    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.token).toBeNull();
    expect(result.current.user).toBeNull();
    expect(mockApi.me).not.toHaveBeenCalled();
  });
});

describe("login", () => {
  it("logs in directly when the account has no MFA enabled", async () => {
    mockApi.login.mockResolvedValue({ access_token: "tok2", refresh_token: "r2", token_type: "bearer" });
    mockApi.me.mockResolvedValue(REAL_USER);

    const { result } = renderAuth();
    await waitFor(() => expect(result.current.loading).toBe(false));

    let loginResult: Awaited<ReturnType<typeof result.current.login>> | undefined;
    await act(async () => {
      loginResult = await result.current.login("jane@example.com", "correct-horse-battery");
    });

    expect(loginResult).toEqual({ mfaRequired: false });
    expect(result.current.token).toBe("tok2");
    expect(result.current.user).toEqual(REAL_USER);
  });

  it("pauses without setting a session when the account requires MFA", async () => {
    mockApi.login.mockResolvedValue({ mfa_required: true, challenge_token: "chal1" });

    const { result } = renderAuth();
    await waitFor(() => expect(result.current.loading).toBe(false));

    let loginResult: Awaited<ReturnType<typeof result.current.login>> | undefined;
    await act(async () => {
      loginResult = await result.current.login("jane@example.com", "correct-horse-battery");
    });

    expect(loginResult).toEqual({ mfaRequired: true, challengeToken: "chal1" });
    expect(result.current.token).toBeNull();
    expect(result.current.user).toBeNull();
    expect(mockApi.me).not.toHaveBeenCalled();
  });
});

describe("completeMfaLogin", () => {
  it("verifies the code and establishes the session", async () => {
    mockApi.mfaVerify.mockResolvedValue({ access_token: "tok3", refresh_token: "r3", token_type: "bearer" });
    mockApi.me.mockResolvedValue(REAL_USER);

    const { result } = renderAuth();
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.completeMfaLogin("chal1", "123456");
    });

    expect(mockApi.mfaVerify).toHaveBeenCalledWith("chal1", "123456");
    expect(result.current.token).toBe("tok3");
    expect(result.current.user).toEqual(REAL_USER);
  });
});

describe("register", () => {
  it("registers then logs in — a brand new account never hits the MFA branch", async () => {
    mockApi.register.mockResolvedValue(REAL_USER);
    mockApi.login.mockResolvedValue({ access_token: "tok4", refresh_token: "r4", token_type: "bearer" });
    mockApi.me.mockResolvedValue(REAL_USER);

    const { result } = renderAuth();
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.register("jane@example.com", "correct-horse-battery", "Jane Doe");
    });

    expect(mockApi.register).toHaveBeenCalledWith("jane@example.com", "correct-horse-battery", "Jane Doe", undefined);
    expect(mockApi.login).toHaveBeenCalledWith("jane@example.com", "correct-horse-battery");
    expect(result.current.token).toBe("tok4");
  });
});

describe("logout", () => {
  it("clears the session locally and calls the server logout endpoint", async () => {
    mockApi.login.mockResolvedValue({ access_token: "tok5", refresh_token: "r5", token_type: "bearer" });
    mockApi.me.mockResolvedValue(REAL_USER);
    mockApi.logout.mockResolvedValue(undefined);

    const { result } = renderAuth();
    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(async () => {
      await result.current.login("jane@example.com", "correct-horse-battery");
    });
    expect(result.current.token).toBe("tok5");

    act(() => {
      result.current.logout();
    });

    expect(result.current.token).toBeNull();
    expect(result.current.user).toBeNull();
    expect(mockApi.logout).toHaveBeenCalled();
  });

  it("still clears the session locally even if the server call fails", async () => {
    mockApi.login.mockResolvedValue({ access_token: "tok6", refresh_token: "r6", token_type: "bearer" });
    mockApi.me.mockResolvedValue(REAL_USER);
    mockApi.logout.mockRejectedValue(new Error("network down"));

    const { result } = renderAuth();
    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(async () => {
      await result.current.login("jane@example.com", "correct-horse-battery");
    });

    act(() => {
      result.current.logout();
    });

    expect(result.current.token).toBeNull();
    expect(result.current.user).toBeNull();
  });
});

describe("refreshUser", () => {
  it("re-fetches the current user with the active token", async () => {
    mockApi.login.mockResolvedValue({ access_token: "tok7", refresh_token: "r7", token_type: "bearer" });
    mockApi.me.mockResolvedValue(REAL_USER);

    const { result } = renderAuth();
    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(async () => {
      await result.current.login("jane@example.com", "correct-horse-battery");
    });

    const updatedUser = { ...REAL_USER, mfa_enabled: true };
    mockApi.me.mockResolvedValue(updatedUser);

    await act(async () => {
      await result.current.refreshUser();
    });

    expect(mockApi.me).toHaveBeenLastCalledWith("tok7");
    expect(result.current.user).toEqual(updatedUser);
  });

  it("does nothing when there is no active session", async () => {
    const { result } = renderAuth();
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => {
      await result.current.refreshUser();
    });

    expect(mockApi.me).not.toHaveBeenCalled();
  });
});
