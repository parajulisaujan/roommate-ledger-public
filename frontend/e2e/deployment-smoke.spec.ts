import { test, expect, type APIRequestContext } from "@playwright/test";
import { readFileSync } from "node:fs";
import path from "node:path";
import { today } from "../src/lib/money";
import { verifyIfRequired } from "./support";

test("two-user deployment smoke preserves exact shares, privacy, receipt and settlement history", async ({
  playwright,
  baseURL,
}) => {
  const clients: APIRequestContext[] = [];
  async function mutate(
    client: APIRequestContext,
    url: string,
    data?: unknown,
    method = "POST",
  ) {
    const csrf = await (await client.get("/api/auth/csrf")).json();
    const response = await client.fetch(`/api${url}`, {
      method,
      data,
      headers: { [csrf.headerName]: csrf.token },
    });
    expect(response.status(), url).toBe(200);
    const text = await response.text();
    return text ? JSON.parse(text) : undefined;
  }
  try {
    const people: { id: string; email: string }[] = [];
    for (const name of ["Fictional Smoke A", "Fictional Smoke B"]) {
      const client = await playwright.request.newContext({ baseURL });
      clients.push(client);
      const user = await mutate(client, "/auth/register", {
        name,
        email: `${crypto.randomUUID()}@example.test`,
        password: "fictional-smoke-password",
      });
      await verifyIfRequired(client, user);
      people.push(user);
    }
    const [a, b] = clients,
      house = await mutate(a, "/households", {
        name: "Fictional deployment smoke",
      });
    const invite = await mutate(a, `/households/${house.id}/invitations`);
    await mutate(b, "/invitations/accept", { token: invite.token });
    const input = {
      title: "$100 smoke bill",
      merchant: "",
      amount: 10000,
      category: "Other",
      scope: "HOUSEHOLD",
      householdId: house.id,
      payerId: people[0].id,
      date: today(),
      splitMethod: "EQUAL",
      participants: [],
      values: {},
      notes: "Fictional acceptance data",
    };
    const shared = await mutate(a, "/expenses", input),
      detail = await (await a.get(`/api/expenses/${shared.id}`)).json();
    expect(detail.allocations.map((x: { amount: number }) => x.amount)).toEqual(
      [5000, 5000],
    );
    await mutate(a, "/expenses", {
      ...input,
      title: "Selected smoke bill",
      scope: "SELECTED_MEMBERS",
      amount: 9000,
      participants: [people[1].id],
    });
    const personal = await mutate(a, "/expenses", {
      ...input,
      title: "Private smoke bill",
      scope: "PERSONAL",
      householdId: null,
      amount: 4000,
    });
    expect((await b.get(`/api/expenses/${personal.id}`)).status()).toBe(403);
    const before = async () =>
      (await (await a.get(`/api/households/${house.id}/balances`)).json()).find(
        (x: { id: string }) => x.id === people[0].id,
      ).balance;
    expect(await before()).toBe(14000);
    const capabilities = await (
      await a.get("/api/receipts/capabilities")
    ).json();
    if (capabilities.automatedExtraction && !process.env.LIVE_RECEIPT_FILE)
      throw new Error(
        "Live extraction is enabled; provide an authorized LIVE_RECEIPT_FILE for this smoke test.",
      );
    const file =
      process.env.LIVE_RECEIPT_FILE ||
      path.resolve("../backend/tests/fixtures/pixel.png");
    const extension = path.extname(file).toLowerCase();
    const mimeType =
      extension === ".webp"
        ? "image/webp"
        : extension === ".png"
          ? "image/png"
          : "image/jpeg";
    const csrf = await (await a.get("/api/auth/csrf")).json();
    const upload = await a.post("/api/receipts/extract", {
      multipart: {
        file: {
          name: path.basename(file),
          mimeType,
          buffer: readFileSync(file),
        },
      },
      headers: { [csrf.headerName]: csrf.token },
    });
    expect(upload.status()).toBe(200);
    const receipt = await upload.json();
    expect(receipt.status).toBe(
      capabilities.automatedExtraction ? "NEEDS_REVIEW" : "FAILED",
    );
    expect(await before()).toBe(14000);
    await mutate(
      a,
      `/receipts/${receipt.id}`,
      {
        merchant: "Fictional reviewed smoke receipt",
        date: today(),
        currency: "USD",
        householdId: house.id,
        payerId: people[0].id,
        items: [
          {
            description: "Reviewed shared item",
            rawDescription: "Fixture",
            quantity: 1,
            unitPrice: 1200,
            amount: 1200,
            category: "Groceries",
            confidence: null,
            scope: "HOUSEHOLD",
            participants: [],
          },
        ],
        subtotal: 1200,
        discounts: 0,
        tax: 0,
        fees: 0,
        total: 1200,
      },
      "PUT",
    );
    await mutate(a, `/receipts/${receipt.id}/confirm`);
    expect(await before()).toBe(14600);
    await mutate(b, `/households/${house.id}/settlements`, {
      fromUser: people[1].id,
      toUser: people[0].id,
      amount: 5000,
      method: "Cash",
      date: today(),
    });
    expect(await before()).toBe(9600);
    const logoutToken = await (await a.get("/api/auth/csrf")).json();
    expect(
      (
        await a.post("/api/auth/logout", {
          headers: { [logoutToken.headerName]: logoutToken.token },
        })
      ).status(),
    ).toBe(204);
    expect((await a.get("/api/auth/me")).status()).toBe(401);
    await mutate(a, "/auth/login", {
      email: people[0].email,
      password: "fictional-smoke-password",
    });
    expect(await before()).toBe(9600);
    expect(
      (await (await a.get(`/api/expenses/${shared.id}`)).json()).amount,
    ).toBe(10000);
  } finally {
    for (const client of clients) await client.dispose();
  }
});
