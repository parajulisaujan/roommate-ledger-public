"use client";
import { useState } from "react";
import { api, body } from "@/lib/api";
import { ErrorMessage, Field } from "./ui";

export default function AccountLink({
  kind,
  token,
}: {
  kind: "reset" | "verify";
  token: string;
}) {
  const [error, setError] = useState(""),
    [message, setMessage] = useState(""),
    [busy, setBusy] = useState(false);
  return (
    <main className="app-loading">
      <section className="panel profile-panel">
        <h1>
          {kind === "reset" ? "Reset your password" : "Verify your email"}
        </h1>
        <p>
          {kind === "reset"
            ? "Choose a new password. All existing sessions will be signed out."
            : "Confirm that this email address belongs to you."}
        </p>
        <ErrorMessage message={error} />
        {message ? (
          <>
            <p role="status">{message}</p>
            <button
              className="text-button"
              onClick={() => window.location.reload()}
            >
              Continue to RoommateLedger
            </button>
          </>
        ) : (
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              setBusy(true);
              setError("");
              const data = new FormData(e.currentTarget);
              try {
                const result = await api<{ message: string }>(
                  `/auth/${kind === "reset" ? "reset-password" : "verify-email"}`,
                  {
                    method: "POST",
                    body: body({
                      token,
                      ...(kind === "reset"
                        ? { password: data.get("password") }
                        : {}),
                    }),
                  },
                );
                setMessage(result.message);
              } catch (e) {
                setError((e as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          >
            {kind === "reset" && (
              <Field label="New password">
                <input
                  name="password"
                  type="password"
                  autoComplete="new-password"
                  minLength={12}
                  maxLength={72}
                  required
                />
              </Field>
            )}
            <button className="primary" disabled={busy}>
              {busy
                ? "Working…"
                : kind === "reset"
                  ? "Reset password"
                  : "Verify email"}
            </button>
          </form>
        )}
        <p>
          <button
            className="text-button"
            onClick={() => window.location.reload()}
          >
            Return to sign in
          </button>
        </p>
      </section>
    </main>
  );
}
