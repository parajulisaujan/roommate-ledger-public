import { test, expect, type Page } from "@playwright/test";
import { verifyIfRequired } from "./support";

async function register(page: Page, name: string) {
  await page.goto("/");
  await page
    .getByRole("button", { name: "Create an account", exact: true })
    .click();
  await page.getByLabel("Your name").fill(name);
  await page
    .getByLabel("Email address")
    .fill(`e2e-${crypto.randomUUID()}@example.test`);
  await page
    .getByLabel("Password", { exact: true })
    .fill("fictional-e2e-password");
  const responsePromise = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/auth/register") && r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Create account", exact: true })
    .click();
  const user = await (await responsePromise).json();
  await verifyIfRequired(page.request, user);
  if (user.verification_required) await page.reload();
  await expect(
    page.getByRole("heading", { name: `A little clarity, ${name}.` }),
  ).toBeVisible();
}
async function navigate(page: Page, name: string) {
  const menu = page.getByRole("button", {
    name: "Open navigation",
    exact: true,
  });
  if (await menu.isVisible()) await menu.click();
  await page.locator("nav").getByRole("button", { name, exact: true }).click();
}
test("registration, household, private expense, receipt confirmation and responsive layouts", async ({
  page,
}) => {
  const consoleErrors: string[] = [];
  const serverErrors: string[] = [];
  page.on("response", (response) => {
    if (response.url().includes("/api/") && response.status() >= 500)
      serverErrors.push(
        `${response.status()} ${new URL(response.url()).pathname}`,
      );
  });
  page.on("pageerror", (e) => consoleErrors.push(e.message));
  await register(page, "Fictional");
  await navigate(page, "Household");
  await page
    .getByLabel("Household name", { exact: true })
    .fill("Fictional Apartment 204");
  await page
    .getByRole("button", { name: "Create household", exact: true })
    .click();
  await expect(
    page
      .getByRole("heading", { name: "Fictional Apartment 204", exact: true })
      .first(),
  ).toBeVisible();
  await navigate(page, "My finances");
  await page.getByRole("button", { name: "Add expense", exact: true }).click();
  await page.getByLabel("What was it for?").fill("Private insurance");
  await page.getByLabel("Amount (USD)", { exact: true }).fill("165.00");
  await page.getByLabel("Category", { exact: true }).selectOption("Insurance");
  await page.getByRole("button", { name: "Save expense", exact: true }).click();
  await expect(
    page.getByRole("button", { name: /Private insurance/ }),
  ).toBeVisible();
  await expect(page.locator(".stat.featured strong")).toHaveText("$165.00");
  await navigate(page, "Household");
  await expect(
    page.getByRole("button", { name: /Private insurance/ }),
  ).toHaveCount(0);
  await navigate(page, "Receipts SCAN");
  await page
    .getByRole("button", { name: "Enter receipt manually", exact: true })
    .click();
  await page.getByLabel("Merchant", { exact: true }).fill("Fictional Grocer");
  await page.getByRole("button", { name: "Add item", exact: true }).click();
  await page.getByLabel("Item 1 name", { exact: true }).fill("Personal rice");
  await page.getByLabel("Item 1 amount", { exact: true }).fill("12.99");
  await page.getByLabel("Printed receipt total (USD)").fill("12.99");
  await page.getByLabel("Merchant", { exact: true }).click();
  await page.getByRole("button", { name: "Save draft", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("Draft saved");
  await page
    .getByRole("button", { name: "Confirm allocations", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Confirmed receipt", exact: true }),
  ).toBeVisible();
  await navigate(page, "Dashboard");
  await expect(page.locator(".stat.featured strong")).toHaveText("$177.99");
  for (const width of [375, 430, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 950 });
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.mouse.move(0, 0);
    await expect(
      page.getByRole("heading", { name: "A little clarity, Fictional." }),
    ).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBeTruthy();
    await page.screenshot({
      path: `test-results/dashboard-${width}.png`,
      fullPage: true,
    });
  }
  await page.getByRole("button", { name: /Private insurance/ }).click();
  await page.getByRole("button", { name: "Edit expense", exact: true }).click();
  await page.getByLabel("Amount (USD)", { exact: true }).fill("160.00");
  await page.getByRole("button", { name: "Save expense", exact: true }).click();
  await expect(page.locator(".stat.featured strong")).toHaveText("$172.99");
  await page.getByRole("button", { name: /Private insurance/ }).click();
  await page
    .getByRole("button", { name: "Delete expense", exact: true })
    .click();
  await expect(page.locator(".stat.featured strong")).toHaveText("$12.99");
  await navigate(page, "Recurring bills");
  await page
    .getByRole("button", { name: "Add recurring bill", exact: true })
    .click();
  await page.getByLabel("What was it for?").fill("Fictional subscription");
  await page.getByLabel("Amount (USD)", { exact: true }).fill("9.99");
  await page
    .getByRole("button", { name: "Save recurring bill", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Record due bill", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Record due bill", exact: true }),
  ).toBeDisabled();
  await navigate(page, "Dashboard");
  await expect(page.locator(".stat.featured strong")).toHaveText("$22.98");
  expect(consoleErrors).toEqual([]);
  expect(serverErrors).toEqual([]);
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Good to have you back" }),
  ).toBeVisible();
});
