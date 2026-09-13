import { cp } from "node:fs/promises";
// Next's standalone output does not copy static assets automatically.
await cp(
  new URL("../.next/static", import.meta.url),
  new URL("../.next/standalone/.next/static", import.meta.url),
  { recursive: true },
);
process.env.HOSTNAME = "0.0.0.0";
await import("../.next/standalone/server.js");
