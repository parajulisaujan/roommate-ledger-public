// A new isolated Compose project; cleanup never targets an existing ledger volume.
import { spawnSync } from "node:child_process";
import { randomBytes, randomUUID } from "node:crypto";
import { setTimeout as delay } from "node:timers/promises";
import { fileURLToPath } from "node:url";
const root = fileURLToPath(new URL("../../", import.meta.url));
const project = `ledger-smoke-${Date.now()}`;
const env = {
  ...process.env,
  DATABASE_PASSWORD: randomBytes(24).toString("hex"),
  DATABASE_USER: "smoke",
  APP_ENV: "development",
  EMAIL_VERIFICATION_REQUIRED: "false",
  RECEIPT_PROVIDER: "adapter",
  RECEIPT_PROVIDER_URL: "",
  RECEIPT_PROVIDER_API_KEY: "",
  SMTP_HOST: "",
  FRONTEND_URL: "http://127.0.0.1:3000",
  COOKIE_SECURE: "false",
};
function docker(...args) {
  const r = spawnSync(
    "docker",
    ["compose", "--project-name", project, "--profile", "app", ...args],
    { cwd: root, env, stdio: "inherit" },
  );
  if (r.status !== 0) throw Error(`Docker command failed: ${args[0]}`);
}
async function ready() {
  for (let i = 0; i < 90; i++) {
    try {
      if ((await fetch("http://127.0.0.1:3000/api/health")).ok) return;
    } catch {}
    await delay(1000);
  }
  throw Error("Frontend/API never became ready");
}
function client() {
  let cookie = "";
  return async (path, data) => {
    async function send(url, options = {}) {
      const r = await fetch(`http://127.0.0.1:3000/api${url}`, {
        ...options,
        headers: { ...options.headers, Cookie: cookie },
      });
      for (const c of r.headers.getSetCookie())
        if (c.startsWith("JSESSIONID=")) cookie = c.split(";")[0];
      return r;
    }
    let headers = {};
    if (data !== undefined) {
      const csrf = await (await send("/auth/csrf")).json();
      headers = {
        [csrf.headerName]: csrf.token,
        "Content-Type": "application/json",
      };
    }
    const r = await send(path, {
      method: data === undefined ? "GET" : "POST",
      headers,
      body: data === undefined ? undefined : JSON.stringify(data),
    });
    const raw = await r.text();
    return { status: r.status, data: raw ? JSON.parse(raw) : null };
  };
}
function assert(condition, message) {
  if (!condition) throw Error(message);
}
try {
  docker("up", "--build", "--wait", "--wait-timeout", "180", "-d");
  await ready();
  const a = client(),
    b = client(),
    password = "fictional-smoke-password",
    email = `${randomUUID()}@example.test`;
  const userA = (
    await a("/auth/register", { name: "Fictional A", email, password })
  ).data;
  const userB = (
    await b("/auth/register", {
      name: "Fictional B",
      email: `${randomUUID()}@example.test`,
      password,
    })
  ).data;
  assert(userA.id && userB.id, "Registration failed");
  const house = (await a("/households", { name: "Fictional Docker smoke" }))
    .data;
  const invite = (await a(`/households/${house.id}/invitations`, {})).data;
  assert(
    (await b("/invitations/accept", { token: invite.token })).status === 200,
    "Join failed",
  );
  const input = {
    title: "Fictional $100 bill",
    merchant: "",
    amount: 10000,
    category: "Other",
    scope: "HOUSEHOLD",
    householdId: house.id,
    payerId: userA.id,
    date: new Date().toISOString().slice(0, 10),
    splitMethod: "EQUAL",
    participants: [],
    values: {},
    notes: "",
  };
  const expense = await a("/expenses", input);
  assert(expense.status === 200, "Shared expense failed");
  const detail = (await a(`/expenses/${expense.data.id}`)).data;
  assert(
    detail.allocations.length === 2 &&
      detail.allocations.every((x) => x.amount === 5000),
    "Expected exact $50/$50 shares",
  );
  const personal = await a("/expenses", {
    ...input,
    title: "Private",
    scope: "PERSONAL",
    householdId: null,
    amount: 4000,
  });
  assert(
    (await b(`/expenses/${personal.data.id}`)).status === 403,
    "Private record leaked",
  );
  docker("restart");
  await ready();
  assert(
    (await a("/auth/login", { email, password })).status === 200,
    "Login after restart failed",
  );
  assert(
    (await a(`/expenses/${expense.data.id}`)).data.amount === 10000,
    "Restart lost persisted expense",
  );
  assert((await a("/auth/logout", {})).status === 204, "Logout failed");
  assert((await a("/auth/me")).status === 401, "Logout did not revoke access");
  docker("logs", "--no-color", "api");
  console.log(
    "Docker smoke passed: fresh migrations, two users, exact split, privacy, restart persistence and logout.",
  );
} finally {
  docker("down", "-v", "--remove-orphans");
}
