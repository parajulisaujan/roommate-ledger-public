import { test, expect } from "@playwright/test";

test("SMTP verification, password recovery, session revocation and deactivation", async ({
  page,
  request,
}) => {
  test.skip(
    !process.env.TEST_MAILBOX_URL,
    "Requires the local fictional SMTP sink or a controlled staging mailbox.",
  );
  const email = `account-${crypto.randomUUID()}@example.test`,
    original = "fictional-account-password",
    replacement = "fictional-reset-password";
  async function link(kind: string) {
    let text = "";
    await expect
      .poll(async () => {
        const messages = (await (
          await request.get(
            `${process.env.TEST_MAILBOX_URL}/?recipient=${encodeURIComponent(email)}`,
          )
        ).json()) as { text: string }[];
        text =
          messages.filter((m) => m.text.includes(`#${kind}=`)).at(-1)?.text ||
          "";
        return text;
      })
      .toContain(`#${kind}=`);
    return text.match(new RegExp(`#${kind}=([A-Za-z0-9_-]{43})`))![0];
  }
  await page.goto("/");
  await page
    .getByRole("button", { name: "Create an account", exact: true })
    .click();
  await page.getByLabel("Your name").fill("Fictional Recovery");
  await page.getByLabel("Email address").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(original);
  await page
    .getByRole("button", { name: "Create account", exact: true })
    .click();
  const verification = await link("verify");
  await page.goto(`/${verification}`);
  await page.getByRole("button", { name: "Verify email", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("Email verified");
  await page
    .getByRole("button", { name: "Continue to RoommateLedger" })
    .click();
  await expect(
    page.getByRole("heading", { name: "A little clarity, Fictional." }),
  ).toBeVisible();
  const priorCookie = await page.context().cookies();
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await page
    .getByRole("button", { name: "Forgot password?", exact: true })
    .click();
  await page.getByLabel("Email address").fill(email);
  await page.getByRole("button", { name: "Send reset link" }).click();
  await expect(page.getByRole("status")).toContainText("If this address");
  await page.goto(`/${await link("reset")}`);
  await page.getByLabel("New password").fill(replacement);
  await page
    .getByRole("button", { name: "Reset password", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText("Password reset");
  const stale = await request.get("/api/auth/me", {
    headers: {
      Cookie: priorCookie.map((c) => `${c.name}=${c.value}`).join("; "),
    },
  });
  expect(stale.status()).toBe(401);
  await page
    .getByRole("button", { name: "Continue to RoommateLedger" })
    .click();
  await page.getByLabel("Email address").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(replacement);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page
    .getByRole("button", { name: "Settings & profile", exact: true })
    .click();
  await expect(page.getByText("Your email is verified.")).toBeVisible();
  await page.getByLabel("Current password", { exact: true }).fill(replacement);
  await page.getByLabel("New password").fill("fictional-changed-password");
  await page
    .getByRole("button", { name: "Change password", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Good to have you back" }),
  ).toBeVisible();
  await page.getByLabel("Email address").fill(email);
  await page
    .getByLabel("Password", { exact: true })
    .fill("fictional-changed-password");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await page
    .getByRole("button", { name: "Settings & profile", exact: true })
    .click();
  await page.getByText("Deactivate account", { exact: true }).click();
  await page
    .getByLabel("Password to deactivate")
    .fill("fictional-changed-password");
  page.once("dialog", (dialog) => dialog.accept());
  await page
    .getByRole("button", { name: "Deactivate my account", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Good to have you back" }),
  ).toBeVisible();
});
