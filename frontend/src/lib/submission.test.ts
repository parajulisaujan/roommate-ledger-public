import { afterEach, expect, it, vi } from "vitest";
import { Submission } from "./submission";
import { api } from "./api";

vi.mock("./api", () => ({ api: vi.fn() }));
afterEach(() => vi.resetAllMocks());

it("reuses a key after a lost response and rotates only after success", async () => {
  const send = vi.mocked(api);
  send.mockRejectedValueOnce(new Error("Lost response"));
  send.mockResolvedValue({ id: "fictional" });
  const form = new Submission();
  const options = { method: "POST", body: JSON.stringify({ amount: 101 }) };
  await expect(form.send("/expenses", options)).rejects.toThrow(
    "Lost response",
  );
  await form.send("/expenses", options);
  await form.send("/expenses", options);
  const keys = send.mock.calls.map(([, options]) =>
    new Headers(options?.headers).get("Idempotency-Key"),
  );
  expect(keys[0]).toBeTruthy();
  expect(keys[1]).toBe(keys[0]);
  expect(keys[2]).not.toBe(keys[0]);
});

it("does not issue a fresh key when details change after an ambiguous failure", async () => {
  const send = vi.mocked(api).mockRejectedValue(new Error("Lost response"));
  const form = new Submission();
  await expect(form.send("/expenses", { body: "first" })).rejects.toThrow();
  await expect(form.send("/expenses", { body: "changed" })).rejects.toThrow();
  const keys = send.mock.calls.map(([, options]) =>
    new Headers(options?.headers).get("Idempotency-Key"),
  );
  expect(keys[0]).toBe(keys[1]);
});
