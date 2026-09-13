import { expect, type APIRequestContext } from "@playwright/test";
export async function verifyIfRequired(
  client: APIRequestContext,
  user: { email: string; verification_required?: boolean },
) {
  if (!user.verification_required) return;
  if (!process.env.TEST_MAILBOX_URL)
    throw new Error(
      "Verification is enabled: configure a controlled TEST_MAILBOX_URL for the staging test accounts.",
    );
  let text = "";
  await expect
    .poll(async () => {
      const response = await client.get(
        `${process.env.TEST_MAILBOX_URL}/?recipient=${encodeURIComponent(user.email)}`,
        {
          headers: process.env.TEST_MAILBOX_TOKEN
            ? { Authorization: `Bearer ${process.env.TEST_MAILBOX_TOKEN}` }
            : {},
        },
      );
      const messages = (await response.json()) as { text: string }[];
      text =
        messages.filter((m) => m.text.includes("#verify=")).at(-1)?.text || "";
      return text.includes("#verify=");
    })
    .toBe(true);
  const token = text.match(/#verify=([A-Za-z0-9_-]{43})/)![1];
  const csrf = await (await client.get("/api/auth/csrf")).json();
  expect(
    (
      await client.post("/api/auth/verify-email", {
        data: { token },
        headers: { [csrf.headerName]: csrf.token },
      })
    ).status(),
  ).toBe(200);
}
