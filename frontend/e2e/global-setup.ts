import { expect, request } from "@playwright/test";

export default async function setup() {
  const client = await request.newContext({
    baseURL: process.env.E2E_BASE_URL || "http://127.0.0.1:3000",
  });
  try {
    await expect
      .poll(
        async () => {
          try {
            return (
              await client.get("/api/health", { timeout: 3000 })
            ).status();
          } catch {
            return 0;
          }
        },
        { timeout: 60000, intervals: [1000] },
      )
      .toBe(200);
  } finally {
    await client.dispose();
  }
}
