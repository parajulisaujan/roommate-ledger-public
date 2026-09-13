import {
  test,
  expect,
  type APIRequestContext,
  type Page,
} from "@playwright/test";
import path from "node:path";
import { verifyIfRequired } from "./support";

async function post(client: APIRequestContext, url: string, data?: unknown) {
  const csrf = await (await client.get("/api/auth/csrf")).json();
  const response = await client.post(`/api${url}`, {
    data,
    headers: { [csrf.headerName]: csrf.token },
  });
  expect(response.status(), `${url}: ${await response.text()}`).toBe(200);
  return response;
}
async function nav(page: Page, name: string) {
  const menu = page.getByRole("button", {
    name: "Open navigation",
    exact: true,
  });
  if (await menu.isVisible()) await menu.click();
  await page
    .locator("aside")
    .getByRole("button", {
      name: name === "Settings" ? "Settings & profile" : name,
      exact: true,
    })
    .click();
}

test("login, invitation, all split methods, payment, upload recovery, preferences and responsive flows", async ({
  page,
  playwright,
  baseURL,
}) => {
  test.setTimeout(150000);
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("response", (r) => {
    if (r.url().includes("/api/") && r.status() >= 500)
      errors.push(`${r.status()} ${r.url()}`);
  });
  const clients: APIRequestContext[] = [];
  try {
    const people: { id: string; name: string; email: string }[] = [];
    for (const name of ["Audit Owner", "Audit Second", "Audit Member"]) {
      const client = await playwright.request.newContext({ baseURL });
      clients.push(client);
      const email = `${crypto.randomUUID()}@example.test`;
      const person = await (
        await post(client, "/auth/register", {
          name,
          email,
          password: "fictional-audit-password",
        })
      ).json();
      await verifyIfRequired(client, person);
      people.push({ ...person, email });
    }
    const house = await (
      await post(clients[0], "/households", { name: "Fictional audit home" })
    ).json();
    const invite = async () =>
      (
        await (
          await post(clients[0], `/households/${house.id}/invitations`)
        ).json()
      ).token;
    await post(clients[1], "/invitations/accept", { token: await invite() });
    const token = await invite();
    await page.goto("/");
    await page.getByLabel("Email address").fill(people[2].email);
    await page
      .getByLabel("Password", { exact: true })
      .fill("fictional-audit-password");
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await expect(
      page.getByRole("heading", { name: "A little clarity, Audit." }),
    ).toBeVisible();
    await nav(page, "Household");
    await page.getByLabel("Invitation code").fill(token);
    await page
      .getByRole("button", { name: "Join household", exact: true })
      .click();
    await expect(page.locator(".members-list")).toContainText("Audit Owner");
    await page
      .getByRole("button", { name: "Add expense", exact: true })
      .click();
    await expect(
      page.getByRole("dialog", { name: "Add an expense" }),
    ).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByRole("dialog")).toHaveCount(0);

    for (const [title, amount, method] of [
      ["Shared equal", "100.00", "EQUAL"],
      ["Selected fixed", "90.00", "FIXED"],
      ["Shared percentage", "100.00", "PERCENTAGE"],
    ]) {
      await page
        .getByRole("button", { name: "Add expense", exact: true })
        .click();
      await page.getByLabel("What was it for?").fill(title);
      await page.getByLabel("Amount (USD)", { exact: true }).fill(amount);
      await page.getByLabel("Paid by").selectOption(people[0].id);
      if (method === "FIXED") {
        await page
          .getByRole("button", { name: "Selected people", exact: true })
          .click();
        for (const person of people)
          await page.getByLabel(person.name, { exact: true }).check();
      }
      await page.getByLabel("Split method").selectOption(method);
      if (method !== "EQUAL") {
        const unit = method === "FIXED" ? "USD" : "%";
        for (const person of people)
          await page
            .getByLabel(`${person.name} (${unit})`, { exact: true })
            .fill("10");
        await page
          .getByRole("button", { name: "Save expense", exact: true })
          .click();
        await expect(page.getByRole("dialog").getByRole("alert")).toBeVisible();
        for (let i = 0; i < people.length; i++)
          await page
            .getByLabel(`${people[i].name} (${unit})`, { exact: true })
            .fill(method === "FIXED" ? "30" : ["50", "30", "20"][i]);
      }
      await page
        .getByRole("button", { name: "Save expense", exact: true })
        .click();
      await expect(page.getByRole("dialog")).toHaveCount(0);
      await expect(
        page.getByRole("button", { name: new RegExp(title) }),
      ).toBeVisible();
    }
    await nav(page, "Reports");
    await page
      .getByRole("button", { name: "Household spending", exact: true })
      .click();
    await expect(page.locator(".stat.featured strong")).toHaveText("$290.00");
    await nav(page, "Balances");
    const before = await (
      await clients[2].get(`/api/households/${house.id}/balances`)
    ).json();
    await page
      .getByRole("button", { name: "Record a payment", exact: true })
      .click();
    await page.getByLabel("Paid to").selectOption(people[0].id);
    await page.getByLabel("Amount (USD)", { exact: true }).fill("10.00");
    await page
      .getByRole("button", { name: "Confirm payment record", exact: true })
      .click();
    await expect(page.locator(".settlement-row")).toContainText("$10.00");
    const after = await (
      await clients[2].get(`/api/households/${house.id}/balances`)
    ).json();
    expect(
      after.find((b: { id: string }) => b.id === people[2].id).balance,
    ).toBe(
      before.find((b: { id: string }) => b.id === people[2].id).balance + 1000,
    );
    await nav(page, "Receipts SCAN");
    await expect(
      page.getByText(/Automated extraction is not configured/),
    ).toBeVisible();
    await page
      .locator('input[type="file"]')
      .setInputFiles(path.resolve("../backend/tests/fixtures/pixel.png"));
    await expect(page.locator("main").getByRole("alert")).toContainText(
      "not configured",
    );
    await page
      .getByLabel("Merchant", { exact: true })
      .fill("Fictional upload recovery");
    await page.getByRole("button", { name: "Add item", exact: true }).click();
    await page.getByLabel("Item 1 name", { exact: true }).fill("Personal soap");
    await page.getByLabel("Item 1 amount", { exact: true }).fill("4.00");
    await page.getByRole("button", { name: "Add item", exact: true }).click();
    await page.getByLabel("Item 2 name", { exact: true }).fill("Shared rice");
    await page.getByLabel("Item 2 amount", { exact: true }).fill("3.00");
    await page
      .getByRole("button", { name: "Everyone", exact: true })
      .nth(1)
      .click();
    await page.getByLabel("Printed receipt total (USD)").fill("7.00");
    await page.getByLabel("Merchant", { exact: true }).click();
    await page
      .getByRole("button", { name: "Confirm allocations", exact: true })
      .click();
    await expect(
      page.getByRole("heading", { name: "Confirmed receipt", exact: true }),
    ).toBeVisible();
    await page
      .getByRole("button", { name: "Back to receipts", exact: true })
      .click();
    await expect(
      page.getByRole("button", { name: /Receipt.*CONFIRMED/ }),
    ).toBeVisible();
    await nav(page, "Reports");
    await page
      .getByRole("button", { name: "Household spending", exact: true })
      .click();
    await expect(page.locator(".stat.featured strong")).toHaveText("$293.00");
    await nav(page, "Settings");
    await page.getByLabel("Dietary preference").selectOption("Vegetarian");
    await page.getByLabel("Timezone").fill("America/Chicago");
    await page
      .getByRole("button", { name: "Save preferences", exact: true })
      .click();
    await expect(page.getByRole("status")).toHaveText("Profile saved.");
    await page.reload();
    await nav(page, "Settings");
    await expect(page.getByLabel("Dietary preference")).toHaveValue(
      "Vegetarian",
    );
    for (const width of [375, 430, 768, 1024, 1440]) {
      await page.setViewportSize({ width, height: 950 });
      for (const tab of [
        "Household",
        "Reports",
        "Balances",
        "Receipts SCAN",
        "Settings",
      ]) {
        await nav(page, tab);
        await expect(page.locator("main h1")).toBeVisible();
        await expect
          .poll(
            () =>
              page.evaluate(
                () => document.documentElement.scrollWidth <= innerWidth,
              ),
            { message: `${tab} overflow at ${width}` },
          )
          .toBe(true);
      }
      await page.screenshot({
        path: `test-results/preferences-${width}.png`,
        fullPage: true,
      });
    }
    expect(errors).toEqual([]);
  } finally {
    for (const client of clients) await client.dispose();
  }
});
