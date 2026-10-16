import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "./api";

// api.ts's internal `request`/`requestMultipart` helpers aren't exported —
// tested here through real `api.*` methods (login/me/logout/uploadDataset)
// instead, which exercises the actual public surface every page calls
// rather than reimplementation-coupled internals.

function mockFetchOnce(response: {
  ok: boolean;
  status: number;
  statusText?: string;
  json?: () => Promise<unknown>;
}) {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: response.ok,
    status: response.status,
    statusText: response.statusText ?? "",
    json: response.json ?? (() => Promise.reject(new Error("no body"))),
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("api request()", () => {
  it("returns parsed JSON on success", async () => {
    mockFetchOnce({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ access_token: "t", refresh_token: "r", token_type: "bearer" }),
    });
    const result = await api.login("a@b.com", "pw");
    expect(result.access_token).toBe("t");
  });

  it("calls the configured API base URL with credentials included and a JSON content-type", async () => {
    const fetchMock = mockFetchOnce({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ access_token: "t", refresh_token: "r", token_type: "bearer" }),
    });
    await api.login("a@b.com", "pw");
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toBe("http://localhost:8000/api/v1/auth/login");
    expect(options.credentials).toBe("include");
    expect(options.headers["Content-Type"]).toBe("application/json");
  });

  it("adds an Authorization bearer header when a token is given", async () => {
    const fetchMock = mockFetchOnce({
      ok: true,
      status: 200,
      json: () =>
        Promise.resolve({ id: "1", email: "a@b.com", full_name: "A", is_active: true, is_verified: true }),
    });
    await api.me("tok123");
    const [, options] = fetchMock.mock.calls[0];
    expect(options.headers.Authorization).toBe("Bearer tok123");
  });

  it("omits the Authorization header when no token is given", async () => {
    const fetchMock = mockFetchOnce({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ access_token: "t", refresh_token: "r", token_type: "bearer" }),
    });
    await api.login("a@b.com", "pw");
    const [, options] = fetchMock.mock.calls[0];
    expect(options.headers.Authorization).toBeUndefined();
  });

  it("returns undefined for a 204 response without parsing a body", async () => {
    const jsonSpy = vi.fn();
    mockFetchOnce({ ok: true, status: 204, json: jsonSpy });
    const result = await api.logout();
    expect(result).toBeUndefined();
    expect(jsonSpy).not.toHaveBeenCalled();
  });

  it("throws a real ApiError carrying the server's detail message on a JSON error body", async () => {
    mockFetchOnce({ ok: false, status: 401, json: () => Promise.resolve({ detail: "Invalid credentials" }) });
    try {
      await api.login("a@b.com", "wrong");
      expect.fail("expected api.login to throw");
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError);
      expect((err as ApiError).status).toBe(401);
      expect((err as ApiError).message).toBe("Invalid credentials");
    }
  });

  it("falls back to statusText when the error body isn't valid JSON", async () => {
    mockFetchOnce({
      ok: false,
      status: 500,
      statusText: "Internal Server Error",
      json: () => Promise.reject(new Error("not json")),
    });
    await expect(api.login("a@b.com", "pw")).rejects.toMatchObject({
      status: 500,
      message: "Internal Server Error",
    });
  });

  it("stringifies a non-string detail (e.g. FastAPI 422 validation errors)", async () => {
    const detail = [{ loc: ["body", "email"], msg: "field required" }];
    mockFetchOnce({ ok: false, status: 422, json: () => Promise.resolve({ detail }) });
    await expect(api.login("a@b.com", "pw")).rejects.toMatchObject({
      status: 422,
      message: JSON.stringify(detail),
    });
  });
});

describe("api requestMultipart()", () => {
  it("sends the file as multipart form data without a manual Content-Type header", async () => {
    const fetchMock = mockFetchOnce({ ok: true, status: 201, json: () => Promise.resolve({ id: "v1" }) });
    const file = new File(["a,b\n1,2\n"], "data.csv", { type: "text/csv" });
    await api.uploadDataset("tok123", "ws1", file, "My Dataset");

    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toBe("http://localhost:8000/api/v1/workspaces/ws1/datasets");
    expect(options.headers.Authorization).toBe("Bearer tok123");
    expect(options.headers["Content-Type"]).toBeUndefined();
    expect(options.body).toBeInstanceOf(FormData);
  });

  it("throws ApiError on a failed upload", async () => {
    mockFetchOnce({ ok: false, status: 413, json: () => Promise.resolve({ detail: "File too large" }) });
    const file = new File(["x"], "big.csv");
    await expect(api.uploadDataset("tok", "ws1", file, "Name")).rejects.toMatchObject({
      status: 413,
      message: "File too large",
    });
  });
});
