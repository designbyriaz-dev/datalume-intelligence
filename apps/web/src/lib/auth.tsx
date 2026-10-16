"use client";

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, isMfaRequired, type User } from "./api";

// The access token lives in memory only (React state) — never
// localStorage, never any other on-disk browser storage. The refresh
// token that can mint new access tokens is kept entirely server-side,
// in an httpOnly cookie the backend sets on login/refresh; this
// frontend code never reads or stores it. See apps/api's
// app/core/cookies.py and app/api/v1/routers/auth.py for the other
// half of this. A page reload loses the in-memory access token by
// design — it's recovered via api.refresh(), which relies on that
// cookie, not on anything this code persisted itself.
type LoginResult = { mfaRequired: true; challengeToken: string } | { mfaRequired: false };

interface AuthContextValue {
  user: User | null;
  token: string | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<LoginResult>;
  completeMfaLogin: (challengeToken: string, code: string) => Promise<void>;
  refreshUser: () => Promise<void>;
  completeSso: (code: string, state: string) => Promise<void>;
  register: (email: string, password: string, fullName: string, inviteToken?: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

// Pre-migration versions of this app stored the access token under this
// key. Nothing reads or writes it anymore, but a browser that was
// logged in before this change shipped still has it sitting on disk —
// exactly the exposure this migration exists to remove — until
// something actively clears it. One-time cleanup, not an ongoing
// mechanism: safe to call even when the key was never set.
const LEGACY_TOKEN_STORAGE_KEY = "datalume.access_token";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    try {
      window.localStorage.removeItem(LEGACY_TOKEN_STORAGE_KEY);
    } catch {
      // Storage inaccessible (private browsing, blocked site data) —
      // nothing to clean up for this visitor either way.
    }

    api
      .refresh()
      .then(async (tokens) => {
        setToken(tokens.access_token);
        setUser(await api.me(tokens.access_token));
      })
      .catch(() => {
        // No valid refresh cookie (never logged in, it expired, or the
        // user logged out elsewhere) — stay logged out, same as before
        // this feature existed finding nothing in localStorage.
        setToken(null);
      })
      .finally(() => setLoading(false));
  }, []);

  const login = useCallback(async (email: string, password: string): Promise<LoginResult> => {
    const result = await api.login(email, password);
    if (isMfaRequired(result)) {
      return { mfaRequired: true, challengeToken: result.challenge_token };
    }
    setToken(result.access_token);
    setUser(await api.me(result.access_token));
    return { mfaRequired: false };
  }, []);

  const completeMfaLogin = useCallback(async (challengeToken: string, code: string) => {
    const tokens = await api.mfaVerify(challengeToken, code);
    setToken(tokens.access_token);
    setUser(await api.me(tokens.access_token));
  }, []);

  const refreshUser = useCallback(async () => {
    if (!token) return;
    setUser(await api.me(token));
  }, [token]);

  const completeSso = useCallback(async (code: string, state: string) => {
    const tokens = await api.ssoCallback(code, state);
    setToken(tokens.access_token);
    setUser(await api.me(tokens.access_token));
  }, []);

  const register = useCallback(
    async (email: string, password: string, fullName: string, inviteToken?: string) => {
      await api.register(email, password, fullName, inviteToken);
      await login(email, password);
    },
    [login]
  );

  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
    api.logout().catch(() => {
      // Best-effort: even if clearing server-side cookies fails (e.g.
      // the network drops), the user is already logged out locally —
      // worst case a stale refresh cookie lingers until it expires on
      // its own.
    });
  }, []);

  return (
    <AuthContext.Provider
      value={{ user, token, loading, login, completeMfaLogin, refreshUser, completeSso, register, logout }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return ctx;
}
