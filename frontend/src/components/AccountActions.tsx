"use client";
import { useEffect, useState } from "react";
import { api, body } from "@/lib/api";
import { ErrorMessage, Field } from "./ui";

export default function AccountActions({ verified }: { verified: boolean }) {
  const [available, setAvailable] = useState(false),
    [error, setError] = useState(""),
    [message, setMessage] = useState(""),
    [busy, setBusy] = useState(false);
  useEffect(() => {
    api<{ emailDeliveryAvailable: boolean }>("/auth/capabilities")
      .then((c) => setAvailable(c.emailDeliveryAvailable))
      .catch((e) => setError(e.message));
  }, []);
  async function action(path: string, data?: unknown, logout = false) {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const result = await api<{ message?: string } | undefined>(path, {
        method: "POST",
        body: data ? body(data) : undefined,
      });
      if (logout) window.location.reload();
      else setMessage(result?.message || "Saved.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="panel profile-panel">
      <h2>Account security</h2>
      <ErrorMessage message={error} />
      {message && (
        <p role="status" className="success">
          {message}
        </p>
      )}
      <p>
        {verified
          ? "Your email is verified."
          : "Your email has not been verified."}
      </p>
      {!available && (
        <p className="notice">
          Email delivery is not configured in this environment. Email
          verification and password recovery cannot send links yet.
        </p>
      )}
      {!verified && (
        <button
          className="secondary"
          disabled={busy || !available}
          onClick={() => action("/account/resend-verification")}
        >
          Resend verification email
        </button>
      )}
      <h3>Change password</h3>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void action(
            "/account/password",
            Object.fromEntries(new FormData(e.currentTarget)),
            true,
          );
        }}
      >
        <Field label="Current password">
          <input
            name="currentPassword"
            type="password"
            autoComplete="current-password"
            required
            maxLength={72}
          />
        </Field>
        <Field label="New password">
          <input
            name="password"
            type="password"
            autoComplete="new-password"
            required
            minLength={12}
            maxLength={72}
          />
        </Field>
        <p className="hint">
          Changing your password signs out every existing session.
        </p>
        <button className="primary" disabled={busy}>
          Change password
        </button>
      </form>
      <details>
        <summary>Deactivate account</summary>
        <p>
          Deactivation ends your memberships and signs you out. Your existing
          expenses, shares and settlement records remain to preserve household
          history. This does not erase your data or forgive balances. Owners
          must first remove active roommates from households they own.
        </p>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (
              window.confirm(
                "Deactivate your account? You will lose sign-in access. Historical records remain.",
              )
            )
              void action(
                "/account/deactivate",
                Object.fromEntries(new FormData(e.currentTarget)),
                true,
              );
          }}
        >
          <Field label="Password to deactivate">
            <input
              name="password"
              type="password"
              autoComplete="current-password"
              maxLength={72}
              required
            />
          </Field>
          <button className="secondary danger-text" disabled={busy}>
            Deactivate my account
          </button>
        </form>
      </details>
    </section>
  );
}
