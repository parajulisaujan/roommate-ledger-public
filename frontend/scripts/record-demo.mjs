// Disposable local containers, existing fictional fixtures, and a browser-only video.
import { spawn } from "node:child_process";
import { randomBytes, randomUUID } from "node:crypto";
import {
  access,
  mkdir,
  readFile,
  realpath,
  rm,
  stat,
  writeFile,
} from "node:fs/promises";
import { basename, dirname, join, sep } from "node:path";
import { setTimeout as pause } from "node:timers/promises";
import { fileURLToPath, pathToFileURL } from "node:url";
import { chromium, expect } from "@playwright/test";

const root = fileURLToPath(new URL("../../", import.meta.url));
const abort = new AbortController();
let stage = "prerequisites";
process.once("SIGINT", () => abort.abort());
process.once("SIGTERM", () => abort.abort());

function run(command, args, { cleanup = false, timeout = 900000 } = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      cwd: root,
      windowsHide: true,
      stdio: ["ignore", "pipe", "pipe"],
      signal: cleanup ? undefined : abort.signal,
    });
    const deadline = setTimeout(() => child.kill(), timeout);
    deadline.unref();
    let output = "";
    // Consume errors without echoing command arguments, environment or provider text.
    child.stdout.on("data", (chunk) => {
      output = (output + chunk.toString()).slice(-65536);
    });
    child.stderr.resume();
    child.on("error", () => {
      clearTimeout(deadline);
      reject(new Error("Local command unavailable."));
    });
    child.on("close", (code) => {
      clearTimeout(deadline);
      return code === 0
        ? resolve(output.trim())
        : reject(new Error("Local command failed."));
    });
  });
}

const docker = (...args) => run("docker", args);
const sleep = (seconds) =>
  pause(seconds * 1000, undefined, { signal: abort.signal });

async function main() {
  if (process.argv.includes("--help")) {
    console.log("Usage: node frontend/scripts/record-demo.mjs [--check]");
    console.log(
      "Requires Docker, npm ci in frontend, and npx playwright install chromium.",
    );
    console.log("Creates isolated local resources only. See docs/demo.md.");
    return;
  }
  if (process.argv.slice(2).some((arg) => arg !== "--check")) {
    throw new Error("Unsupported argument.");
  }
  await docker("info", "--format", "{{.ServerVersion}}");
  await access(chromium.executablePath());
  if (process.argv.includes("--check")) {
    const browser = await chromium.launch();
    await browser.close();
    console.log("PASS local Docker and Chromium prerequisites.");
    return;
  }

  const id = randomUUID().slice(0, 8);
  const name = `ledger-demo-${id}`;
  const ingress = `${name}-ingress`;
  const mailbox = `${name}-mailbox`;
  const db = `${name}-db`,
    api = `${name}-api`,
    web = `${name}-web`;
  const apiImage = `${name}-api-image`,
    webImage = `${name}-web-image`;
  const outputDir = join(
    root,
    "artifacts",
    "demo",
    `${new Date().toISOString().replace(/[:.]/g, "-")}-${id}`,
  );
  const captureDir = join(outputDir, "capture");
  const password = randomBytes(24).toString("hex");
  const demoPassword = randomBytes(24).toString("base64url");
  const database = `ledger_demo_${id}`;
  let browser, context, video;
  const chapters = [];
  let started = 0;
  await mkdir(captureDir, { recursive: true });
  if (!(await realpath(outputDir)).startsWith((await realpath(root)) + sep)) {
    throw new Error("Output must stay inside the repository.");
  }

  try {
    stage = "container_build";
    console.log("Building the local demo images from this checkout.");
    await docker(
      "build",
      "-t",
      apiImage,
      "-f",
      "backend/Dockerfile",
      "backend",
    );
    await docker(
      "build",
      "-t",
      webImage,
      "--build-arg",
      "API_INTERNAL_URL=http://api:8080",
      "--build-arg",
      "APP_ENV=development",
      "--build-arg",
      "FRONTEND_URL=http://127.0.0.1",
      "frontend",
    );

    stage = "isolated_database";
    await docker("network", "create", "--internal", name);
    await docker(
      "run",
      "-d",
      "--name",
      db,
      "--network",
      name,
      "--network-alias",
      "db",
      "-e",
      "POSTGRES_USER=ledger_demo",
      "-e",
      `POSTGRES_PASSWORD=${password}`,
      "-e",
      `POSTGRES_DB=${database}`,
      "postgres:17-alpine@sha256:18cfe3ef5e6815560c98237d6216d1e5119702fb0f3894c8785dd58b8bbe5d73",
    );
    let ready = false;
    for (let attempt = 0; attempt < 60; attempt++) {
      try {
        await docker(
          "exec",
          db,
          "pg_isready",
          "-U",
          "ledger_demo",
          "-d",
          database,
        );
        ready = true;
        break;
      } catch {
        await sleep(1);
      }
    }
    if (!ready) throw new Error("Local database did not become ready.");

    stage = "local_application";
    // No root .env or parent provider configuration is forwarded to these containers.
    const settings = {
      APP_ENV: "development",
      DATABASE_URL: `postgresql+psycopg://db:5432/${database}`,
      DATABASE_USER: "ledger_demo",
      DATABASE_PASSWORD: password,
      FRONTEND_URL: "http://127.0.0.1",
      COOKIE_SECURE: "false",
      COOKIE_SAME_SITE: "lax",
      EMAIL_VERIFICATION_REQUIRED: "false",
      SMTP_HOST: "127.0.0.1",
      SMTP_PORT: "2525",
      SMTP_STARTTLS: "false",
      SMTP_USERNAME: "",
      SMTP_PASSWORD: "",
      EMAIL_FROM: "household@example.test",
      RECEIPT_PROVIDER: "adapter",
      RECEIPT_PROVIDER_URL: "",
      RECEIPT_PROVIDER_API_KEY: "",
      OPENAI_API_KEY: "",
      OPENAI_RECEIPT_MODEL: "",
      DEPLOYMENT_PROXY_REQUIRED: "false",
      DEPLOYMENT_PROXY_KEY: "",
      TRUSTED_PROXY_CIDRS: "",
    };
    const envArgs = Object.entries(settings).flatMap(([key, value]) => [
      "-e",
      `${key}=${value}`,
    ]);
    await docker(
      "run",
      "-d",
      "--name",
      api,
      "--network",
      name,
      "--network-alias",
      "api",
      ...envArgs,
      apiImage,
    );
    ready = false;
    for (let attempt = 0; attempt < 90; attempt++) {
      try {
        await docker(
          "exec",
          api,
          "python",
          "-c",
          "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/actuator/health/readiness', timeout=2)",
        );
        ready = true;
        break;
      } catch {
        await sleep(1);
      }
    }
    if (!ready) throw new Error("Local application did not become ready.");
    stage = "local_mailbox";
    await docker(
      "run",
      "-d",
      "--name",
      mailbox,
      "--network",
      `container:${api}`,
      webImage,
      "node",
      "--input-type=module",
      "-e",
      await readFile(join(root, "frontend/scripts/test-mailbox.mjs"), "utf8"),
    );
    await sleep(2);
    await docker(
      "exec",
      api,
      "python",
      "-c",
      "import smtplib, urllib.request, json; s=smtplib.SMTP('127.0.0.1',2525); s.sendmail('household@example.test',['demo-check@example.test'],'Subject: Local mailbox check\\r\\n\\r\\nFictional local message'); s.quit(); assert len(json.load(urllib.request.urlopen('http://127.0.0.1:8025/?recipient=demo-check@example.test')))==1",
    );
    stage = "fictional_seed";
    await docker(
      "exec",
      "-e",
      `DEMO_PASSWORD=${demoPassword}`,
      "-e",
      `DEMO_DATABASE=${database}`,
      api,
      "python",
      "-c",
      await readFile(join(root, "frontend/scripts/demo-seed.py"), "utf8"),
    );
    stage = "local_frontend_start";
    console.log("Fictional data seeded; starting the local frontend.");
    // Docker cannot publish ports from an internal-only network. Only the web
    // container joins this separate bridge; the database and API stay internal.
    await docker("network", "create", ingress);
    await docker(
      "run",
      "-d",
      "--name",
      web,
      "--network",
      ingress,
      "-p",
      "127.0.0.1::3000",
      webImage,
    );
    await docker("network", "connect", name, web);
    const binding = await docker("port", web, "3000/tcp");
    if (!/^127\.0\.0\.1:\d+$/.test(binding))
      throw new Error("Expected loopback binding.");
    const origin = `http://${binding}`;
    stage = "local_frontend_readiness";
    ready = false;
    for (let attempt = 0; attempt < 60; attempt++) {
      try {
        if (
          (
            await fetch(`${origin}/api/health`, {
              signal: AbortSignal.timeout(2000),
            })
          ).ok
        ) {
          ready = true;
          break;
        }
      } catch {
        /* Local container is still starting. */
      }
      await sleep(1);
    }
    if (!ready) throw new Error("Local frontend did not become ready.");

    stage = "browser_recording";
    browser = await chromium.launch();
    context = await browser.newContext({
      viewport: { width: 1280, height: 720 },
      locale: "en-US",
      timezoneId: "America/Chicago",
      recordVideo: { dir: captureDir, size: { width: 1280, height: 720 } },
      serviceWorkers: "block",
    });
    await context.route("**/*", (route) => {
      const url = new URL(route.request().url());
      return url.origin === origin ? route.continue() : route.abort();
    });
    const page = await context.newPage();
    page.setDefaultTimeout(15000);
    video = page.video();
    started = Date.now();
    await page.goto(origin);
    await expect(
      page.getByRole("button", { name: "Sign in", exact: true }),
    ).toBeVisible();

    async function caption(title, detail, full = false) {
      chapters.push({
        atSeconds: Math.round((Date.now() - started) / 1000),
        title,
      });
      console.log(`Recording: ${title}`);
      await page.evaluate(
        ({ title, detail, full }) => {
          document.getElementById("local-demo-caption")?.remove();
          const card = document.createElement("div");
          card.id = "local-demo-caption";
          card.style.cssText = full
            ? "position:fixed;inset:0;z-index:2147483647;background:#f7f5ef;color:#19382c;display:flex;flex-direction:column;justify-content:center;align-items:center;gap:20px;font:24px system-ui;pointer-events:none;"
            : "position:fixed;bottom:18px;left:22px;max-width:570px;z-index:2147483647;background:#19382cf2;color:white;padding:14px 20px;border-radius:12px;font:17px system-ui;pointer-events:none;box-shadow:0 6px 24px #0002;";
          const heading = document.createElement("strong");
          heading.textContent = title;
          heading.style.cssText = `display:block;font-size:${full ? 48 : 20}px;margin-bottom:8px`;
          const text = document.createElement("div");
          text.textContent = detail;
          const label = document.createElement("small");
          label.textContent = "Local demonstration · Fictional data";
          label.style.cssText = "display:block;margin-top:12px;opacity:.75";
          card.append(heading, text, label);
          document.body.append(card);
        },
        { title, detail, full },
      );
    }
    const nav = async (name) => {
      await page
        .locator("aside")
        .getByRole("button", { name, exact: true })
        .click();
      await expect(page.locator("main h1")).toBeVisible();
      await sleep(1);
    };

    await caption(
      "RoommateLedger",
      "Private spending. Shared costs. Clear balances.",
      true,
    );
    await sleep(4);
    await caption(
      "Sign in",
      "A household ledger with private spending and shared costs.",
    );
    await page
      .getByLabel("Email address")
      .fill("saujan.roommateledger@example.test");
    await page.getByLabel("Password", { exact: true }).fill(demoPassword);
    await sleep(3);
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await expect(
      page.getByRole("heading", { name: "A little clarity, Saujan." }),
    ).toBeVisible();
    await caption(
      "Dashboard",
      "Your spending and your household share, in one place.",
    );
    await sleep(10);

    await nav("Household");
    await expect(page.locator(".members-list")).toContainText("Sejal Khadka");
    await page.locator(".members-list").scrollIntoViewIfNeeded();
    await caption(
      "One household, different responsibilities",
      "Four roommates share costs while keeping personal expenses private.",
    );
    await sleep(8);

    await page
      .getByRole("button", { name: "Add expense", exact: true })
      .click();
    await page.getByRole("button", { name: "Just me", exact: true }).click();
    await page.getByLabel("What was it for?").fill("Coffee");
    await page.getByLabel("Amount (USD)", { exact: true }).fill("6.45");
    await page.getByLabel("Category", { exact: true }).selectOption("Dining");
    await caption(
      "Private expense",
      "Only the person who records this expense can see it.",
    );
    await sleep(8);
    await page
      .getByRole("button", { name: "Save expense", exact: true })
      .click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await nav("My finances");
    await expect(page.getByRole("button", { name: /Coffee/ })).toBeVisible();
    await sleep(6);

    await nav("Household");
    await page
      .getByRole("button", { name: "Add expense", exact: true })
      .click();
    await page.getByRole("button", { name: "Everyone", exact: true }).click();
    await page.getByLabel("What was it for?").fill("Weekend groceries");
    await page.getByLabel("Amount (USD)", { exact: true }).fill("86.41");
    await page.getByLabel("Split method").selectOption("EQUAL");
    await page.locator(".split-preview").scrollIntoViewIfNeeded();
    await expect(page.locator(".split-preview")).toContainText("4 people");
    await caption(
      "Every cent is accounted for",
      "$86.41 across four people: one share is $21.61, three are $21.60.",
    );
    await sleep(10);
    await page
      .getByRole("button", { name: "Save expense", exact: true })
      .click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await nav("Household");
    await expect(
      page.getByRole("button", { name: /Weekend groceries/ }),
    ).toBeVisible();
    await sleep(5);

    await nav("Balances");
    await caption(
      "Balances",
      "Calculated from payments, expense shares and recorded repayments. No money is moved.",
    );
    await sleep(10);
    await nav("Reports");
    await caption(
      "Personal spending reports",
      "Monthly comparisons and categories use your own finalized responsibility.",
    );
    await sleep(10);
    await page
      .getByRole("button", { name: "Household spending", exact: true })
      .click();
    await caption(
      "Household reports",
      "Shared totals stay separate from private purchases.",
    );
    await sleep(8);

    await nav("Dashboard");
    await page.evaluate(() =>
      document.getElementById("local-demo-caption")?.remove(),
    );
    await expect(
      page.getByRole("heading", { name: "A little clarity, Saujan." }),
    ).toBeVisible();
    await sleep(1);
    await page.screenshot({
      path: join(outputDir, "roommateledger-demo-poster.png"),
    });
    await sleep(5);
    await context.close();
    context = undefined;

    stage = "video_export";
    const webm = join(outputDir, "roommateledger-demo.webm");
    await video.saveAs(webm);
    // Read actual media duration locally; the inspection itself is not recorded.
    const inspection = await browser.newContext({ offline: true });
    const media = await inspection.newPage();
    await media.goto(pathToFileURL(webm).href);
    await media.waitForFunction(
      () => Number.isFinite(document.querySelector("video")?.duration),
      undefined,
      { timeout: 15000 },
    );
    const duration = await media
      .locator("video")
      .evaluate((element) => element.duration);
    await inspection.close();
    if (duration < 90 || duration > 120)
      throw new Error("Video duration outside the intended range.");
    await browser.close();
    browser = undefined;

    let mp4 = false;
    try {
      await run(
        "ffmpeg",
        [
          "-hide_banner",
          "-loglevel",
          "error",
          "-i",
          webm,
          "-c:v",
          "libx264",
          "-pix_fmt",
          "yuv420p",
          "-movflags",
          "+faststart",
          "-an",
          join(outputDir, "roommateledger-demo.mp4"),
        ],
        { timeout: 120000 },
      );
      mp4 = true;
    } catch {
      await rm(join(outputDir, "roommateledger-demo.mp4"), { force: true });
    }
    await writeFile(
      join(outputDir, "recording.json"),
      JSON.stringify(
        {
          durationSeconds: Number(duration.toFixed(2)),
          viewport: "1280x720",
          fictionalData: true,
          bytes: (await stat(webm)).size,
          localMailboxVerified: true,
          names: [
            "Saujan Parajuli",
            "Sejal Khadka",
            "Bikash Gurung",
            "Binod Tiwari",
          ],
          environment: "isolated local Docker",
          hostedVerification: false,
          mp4,
          chapters,
        },
        null,
        2,
      ) + "\n",
    );
    console.log(`PASS demo video: ${webm}`);
    console.log(
      `Duration: ${duration.toFixed(1)} seconds. MP4: ${mp4 ? "created" : "not created (optional ffmpeg unavailable or unsupported)"}.`,
    );
  } finally {
    if (context) await context.close().catch(() => {});
    if (browser) await browser.close().catch(() => {});
    if (video) await video.delete().catch(() => {});
    const target = await realpath(captureDir);
    if (
      dirname(target) === (await realpath(outputDir)) &&
      basename(target) === "capture"
    ) {
      await rm(target, { recursive: true, force: true });
    }
    // Only the uniquely named resources created by this invocation are targeted.
    await run("docker", ["rm", "-f", "-v", mailbox, web, api, db], {
      cleanup: true,
      timeout: 30000,
    }).catch(() => {});
    await run("docker", ["network", "rm", name, ingress], {
      cleanup: true,
      timeout: 30000,
    }).catch(() => {});
    await run("docker", ["image", "rm", webImage, apiImage], {
      cleanup: true,
      timeout: 30000,
    }).catch(() => {});
  }
}

main().catch(() => {
  console.error(
    `DEMO FAIL ${stage}. Check local prerequisites and docs/demo.md; raw diagnostics are suppressed.`,
  );
  process.exitCode = 1;
});
