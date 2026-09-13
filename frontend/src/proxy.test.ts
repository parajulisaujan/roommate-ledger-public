import { afterEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { proxy } from "./proxy";

afterEach(() => vi.unstubAllEnvs());

function protectedPreview() {
  vi.stubEnv("DEPLOYMENT_PROXY_REQUIRED", "true");
  vi.stubEnv("DEPLOYMENT_PROXY_KEY", "test-only-credential-".repeat(3));
  vi.stubEnv("API_INTERNAL_URL", "https://api.example.test");
  vi.stubEnv("VERCEL", "1");
  vi.stubEnv("VERCEL_ENV", "preview");
}

describe("protected staging origin", () => {
  it("preserves the existing rewrite when protected ingress is disabled", () => {
    vi.stubEnv("DEPLOYMENT_PROXY_REQUIRED", "false");
    expect(
      proxy(new NextRequest("https://app.test/api/health")).headers.get(
        "x-middleware-next",
      ),
    ).toBe("1");
  });

  it("denies accidental Production promotion, including HTML", () => {
    protectedPreview();
    vi.stubEnv("VERCEL_ENV", "production");
    expect(proxy(new NextRequest("https://app.test/")).status).toBe(404);
  });

  it.each([
    "",
    "http://api.test",
    "https://user:secret@api.test",
    "https://api.test/subpath",
  ])("fails closed for invalid upstream %s", (upstream) => {
    protectedPreview();
    vi.stubEnv("API_INTERNAL_URL", upstream);
    expect(proxy(new NextRequest("https://app.test/api/health")).status).toBe(
      503,
    );
  });

  it("fails closed without an origin credential", () => {
    protectedPreview();
    vi.stubEnv("DEPLOYMENT_PROXY_KEY", "");
    expect(proxy(new NextRequest("https://app.test/api/health")).status).toBe(
      503,
    );
  });

  it("overrides forged ingress credentials while preserving session, CSRF, multipart and query", () => {
    protectedPreview();
    const response = proxy(
      new NextRequest("https://app.test/api/receipts/extract?a=1", {
        method: "POST",
        headers: {
          "x-ledger-proxy-key": "forged",
          cookie: "JSESSIONID=fictional",
          "x-csrf-token": "fictional-csrf",
          "idempotency-key": "fictional-request-key",
          "content-type": "multipart/form-data; boundary=test",
          "x-forwarded-for": "203.0.113.1",
        },
      }),
    );
    expect(response.headers.get("x-middleware-rewrite")).toBe(
      "https://api.example.test/api/receipts/extract?a=1",
    );
    expect(
      response.headers.get("x-middleware-request-x-ledger-proxy-key"),
    ).toBe(process.env.DEPLOYMENT_PROXY_KEY);
    expect(response.headers.get("x-middleware-request-cookie")).toBe(
      "JSESSIONID=fictional",
    );
    expect(response.headers.get("x-middleware-request-x-csrf-token")).toBe(
      "fictional-csrf",
    );
    expect(response.headers.get("x-middleware-request-idempotency-key")).toBe(
      "fictional-request-key",
    );
    expect(response.headers.get("x-middleware-request-content-type")).toContain(
      "multipart/form-data",
    );
    expect(response.headers.has("x-middleware-request-x-forwarded-for")).toBe(
      false,
    );
    expect(response.headers.has("x-ledger-proxy-key")).toBe(false);
  });
});
