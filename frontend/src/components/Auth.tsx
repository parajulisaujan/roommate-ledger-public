"use client";
import { useState } from "react";
import { BookOpen, LockKeyhole, Users, Check } from "lucide-react";
import { api, body } from "@/lib/api";
import type { User } from "@/lib/types";
import { ErrorMessage, Field } from "./ui";
export default function Auth({ onLogin }: { onLogin: (user: User) => void }) {
  const [register, setRegister] = useState(false),
    [forgot, setForgot] = useState(false),
    [message, setMessage] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const data = new FormData(event.currentTarget);
    try {
      if (forgot) {
        const result = await api<{ message: string }>("/auth/forgot-password", {
          method: "POST",
          body: body({ email: data.get("email") }),
        });
        const capability = await api<{ emailDeliveryAvailable: boolean }>(
          "/auth/capabilities",
        );
        setMessage(
          capability.emailDeliveryAvailable
            ? result.message
            : "Email delivery is not configured in this environment. Password recovery cannot send a link yet.",
        );
        return;
      }
      onLogin(
        await api<User>(`/auth/${register ? "register" : "login"}`, {
          method: "POST",
          body: body(Object.fromEntries(data)),
        }),
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="auth-layout">
      <section className="auth-story">
        <div className="brand">
          <BookOpen /> Roommate<span>Ledger</span>
        </div>
        <div>
          <span className="eyebrow">
            A LITTLE LESS AWKWARD. A LOT MORE CLEAR.
          </span>
          <h1>
            Share a home.
            <br />
            Make sense of
            <br />
            <em>the expenses.</em>
          </h1>
          <p>
            Your groceries aren’t always everyone’s groceries. Keep personal
            spending private, share bills fairly, and know exactly where you
            stand.
          </p>
          <div className="auth-points">
            <span>
              <LockKeyhole size={18} /> Your personal spending stays yours
            </span>
            <span>
              <Users size={18} /> Split each item with the right people
            </span>
            <span>
              <Check size={18} /> Clear balances, down to the cent
            </span>
          </div>
        </div>
        <small>
          Personal finances. Shared household costs. Clear balances.
        </small>
      </section>
      <section className="auth-form">
        <span className="eyebrow">WELCOME TO YOUR LEDGER</span>
        <h2>
          {forgot
            ? "Forgot your password?"
            : register
              ? "Make yourself at home"
              : "Good to have you back"}
        </h2>
        <p>
          {register
            ? "Create your private account. Invite your roommates when you’re ready."
            : "Sign in to see your spending and settle the shared stuff."}
        </p>
        <form onSubmit={submit}>
          <ErrorMessage message={error} />
          {message && <p role="status">{message}</p>}
          {register && (
            <Field label="Your name">
              <input name="name" autoComplete="name" required maxLength={80} />
            </Field>
          )}
          <Field label="Email address">
            <input
              name="email"
              type="email"
              autoComplete="email"
              required
              maxLength={254}
            />
          </Field>
          {!forgot && (
            <Field label="Password">
              <input
                name="password"
                type="password"
                autoComplete={register ? "new-password" : "current-password"}
                required
                minLength={12}
                maxLength={72}
              />
            </Field>
          )}
          {register && <small>Use at least 12 characters.</small>}
          <button className="primary" disabled={busy}>
            {busy
              ? "Please wait…"
              : forgot
                ? "Send reset link"
                : register
                  ? "Create account"
                  : "Sign in"}
          </button>
        </form>
        <p className="auth-switch">
          {register ? "Already have an account?" : "New here?"}{" "}
          <button
            className="text-button"
            onClick={() => {
              setRegister(!register);
              setForgot(false);
              setMessage("");
              setError("");
            }}
          >
            {register ? "Sign in" : "Create an account"}
          </button>
        </p>
        <button
          className="text-button"
          onClick={() => {
            setForgot(!forgot);
            setRegister(false);
            setError("");
            setMessage("");
          }}
        >
          {forgot ? "Back to sign in" : "Forgot password?"}
        </button>
        <div className="privacy-note">
          <LockKeyhole size={16} />
          <span>
            Your roommates can see shared expenses. Your private finances are
            only visible to you.
          </span>
        </div>
      </section>
    </main>
  );
}
