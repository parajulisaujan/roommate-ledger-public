import type { NextConfig } from "next";
const deployed = ["production", "staging"].includes(
  process.env.APP_ENV || "development",
);
if (
  deployed &&
  ((!process.env.API_INTERNAL_URL &&
    process.env.DEPLOYMENT_PROXY_REQUIRED !== "true") ||
    !process.env.FRONTEND_URL?.startsWith("https://"))
)
  throw new Error(
    "Set an HTTPS FRONTEND_URL and either API_INTERNAL_URL or the fail-closed deployment proxy before building for staging/production.",
  );
const config: NextConfig = {
  output: process.env.VERCEL ? undefined : "standalone",
  async rewrites() {
    if (process.env.DEPLOYMENT_PROXY_REQUIRED === "true") return [];
    return [
      {
        source: "/api/:path*",
        destination: `${process.env.API_INTERNAL_URL || "http://127.0.0.1:8080"}/api/:path*`,
      },
    ];
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          {
            key: "Content-Security-Policy",
            value: `default-src 'self'; script-src 'self' 'unsafe-inline'${process.env.NODE_ENV === "development" ? " 'unsafe-eval'" : ""}; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'`,
          },
          ...(deployed
            ? [{ key: "Strict-Transport-Security", value: "max-age=31536000" }]
            : []),
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "same-origin" },
          { key: "X-Frame-Options", value: "DENY" },
          {
            key: "Permissions-Policy",
            value: "camera=(self), microphone=(), geolocation=()",
          },
        ],
      },
    ];
  },
};
export default config;
