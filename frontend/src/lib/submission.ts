import { api } from "./api";

// Keep this object for the lifetime of the form. A lost response must reuse its key.
export class Submission {
  private key: string | undefined;

  async send<T>(path: string, options: RequestInit): Promise<T> {
    this.key ??= crypto.randomUUID();
    const headers = new Headers(options.headers);
    headers.set("Idempotency-Key", this.key);
    const result = await api<T>(path, { ...options, headers });
    this.key = undefined;
    return result;
  }
}
