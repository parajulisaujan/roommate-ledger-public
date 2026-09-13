let csrf: { token: string; headerName: string } | null = null;
export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const method = options.method || "GET";
  const headers = new Headers(options.headers);
  if (options.body && !(options.body instanceof FormData))
    headers.set("Content-Type", "application/json");
  if (!["GET", "HEAD"].includes(method)) {
    if (!csrf) {
      const response = await fetch("/api/auth/csrf", {
        credentials: "same-origin",
        cache: "no-store",
      });
      if (!response.ok)
        throw new Error("Could not establish a secure session.");
      csrf = await response.json();
    }
    headers.set(csrf!.headerName, csrf!.token);
  }
  const response = await fetch(`/api${path}`, {
    ...options,
    headers,
    credentials: "same-origin",
    cache: "no-store",
  });
  if (!response.ok) {
    if (response.status === 401 || response.status === 403) csrf = null;
    const error = await response.json().catch(() => ({}));
    throw new Error(
      error.message || `Request failed (${response.status}). Please try again.`,
    );
  }
  if (path === "/auth/logout") csrf = null;
  const text = await response.text();
  return text ? (JSON.parse(text) as T) : (undefined as T);
}
export function body(value: unknown): string {
  return JSON.stringify(value);
}
