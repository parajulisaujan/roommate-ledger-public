import { test, expect, type APIRequestContext } from "@playwright/test";
import { today } from "../src/lib/money";
import { verifyIfRequired } from "./support";

async function mutate(client: APIRequestContext, path: string, data?: unknown) {
  const token = await (await client.get("/api/auth/csrf")).json();
  return client.post(`/api${path}`, {
    data,
    headers: { [token.headerName]: token.token },
  });
}
async function account(client: APIRequestContext, name: string) {
  const response = await mutate(client, "/auth/register", {
    name,
    email: `api-${crypto.randomUUID()}@example.test`,
    password: "fictional-api-password",
  });
  expect(response.status()).toBe(200);
  const user = await response.json();
  await verifyIfRequired(client, user);
  return user;
}
test("real API rejects private access and produces exact four-member balances", async ({
  playwright,
  baseURL,
}) => {
  const clients: APIRequestContext[] = [];
  try {
    for (let i = 0; i < 4; i++)
      clients.push(await playwright.request.newContext({ baseURL }));
    const users: { id: string }[] = [];
    for (let i = 0; i < 4; i++)
      users.push(await account(clients[i], `Fictional ${i}`));
    const household = await (
      await mutate(clients[0], "/households", {
        name: "API fictional household",
      })
    ).json();
    for (let i = 1; i < 4; i++) {
      const invite = await (
        await mutate(clients[0], `/households/${household.id}/invitations`)
      ).json();
      expect(
        (
          await mutate(clients[i], "/invitations/accept", {
            token: invite.token,
          })
        ).status(),
      ).toBe(200);
    }
    const date = today();
    const expense = {
      title: "Private insurance",
      merchant: "",
      amount: 16500,
      category: "Insurance",
      scope: "PERSONAL",
      householdId: null,
      payerId: users[0].id,
      date,
      splitMethod: "EQUAL",
      participants: [],
      values: {},
      notes: "Fictional test",
    };
    const created = await mutate(clients[0], "/expenses", expense);
    expect(created.status()).toBe(200);
    const personal = await created.json();
    const roommatePrivate = await (
      await mutate(clients[1], "/expenses", {
        ...expense,
        amount: 4000,
        payerId: users[1].id,
      })
    ).json();
    expect(
      (await clients[0].get(`/api/expenses/${roommatePrivate.id}`)).status(),
    ).toBe(403);
    const roommateAnalytics = await (
      await clients[1].get(`/api/analytics/personal?userId=${users[0].id}`)
    ).json();
    expect(roommateAnalytics.total).toBe(4000);
    const csv = await (await clients[1].get("/api/export/expenses")).text();
    expect(csv).toContain(roommatePrivate.id);
    expect(csv).not.toContain(personal.id);
    expect(
      (await clients[1].get(`/api/expenses/${personal.id}`)).status(),
    ).toBe(403);
    expect(
      (
        await clients[1].get(`/api/households/${household.id}/analytics`)
      ).status(),
    ).toBe(200);
    expect(
      (
        await (
          await clients[1].get(`/api/households/${household.id}/analytics`)
        ).json()
      ).total,
    ).toBe(0);
    const bill = await mutate(clients[0], "/expenses", {
      ...expense,
      title: "Electricity",
      amount: 16000,
      category: "Utilities",
      scope: "HOUSEHOLD",
      householdId: household.id,
    });
    expect(bill.status()).toBe(200);
    const balances = await (
      await clients[0].get(`/api/households/${household.id}/balances`)
    ).json();
    expect(
      balances.find((b: { id: string }) => b.id === users[0].id).balance,
    ).toBe(12000);
    expect(
      balances.find((b: { id: string }) => b.id === users[1].id).balance,
    ).toBe(-4000);
    expect(
      (
        await mutate(clients[1], `/households/${household.id}/settlements`, {
          fromUser: users[1].id,
          toUser: users[0].id,
          amount: 4000,
          method: "Cash",
          date,
        })
      ).status(),
    ).toBe(200);
    const after = await (
      await clients[1].get(`/api/households/${household.id}/balances`)
    ).json();
    expect(
      after.find((b: { id: string }) => b.id === users[1].id).balance,
    ).toBe(0);
    expect(
      (await clients[1].post("/api/expenses", { data: expense })).status(),
    ).toBe(403);
  } finally {
    for (const client of clients) await client.dispose();
  }
});
