"use client";
import { useState } from "react";
import { api, body } from "@/lib/api";
import type { User } from "@/lib/types";
import { ErrorMessage, Field } from "./ui";
export default function ProfileView({
  user,
  onSaved,
}: {
  user: User;
  onSaved: (u: User) => void;
}) {
  const [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [saved, setSaved] = useState(false);
  return (
    <section className="panel profile-panel">
      <h2>Your profile</h2>
      <p>
        Preferences belong to you. Dietary choices never automatically change a
        split.
      </p>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          const f = new FormData(e.currentTarget);
          setBusy(true);
          setError("");
          try {
            onSaved(
              await api<User>("/profile", {
                method: "PATCH",
                body: body({
                  name: f.get("name"),
                  diet: f.get("diet"),
                  timezone: f.get("timezone"),
                  notifications: false,
                }),
              }),
            );
            setSaved(true);
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <ErrorMessage message={error} />
        {saved && (
          <p className="success" role="status">
            Profile saved.
          </p>
        )}
        <Field label="Name">
          <input name="name" defaultValue={user.name} required maxLength={80} />
        </Field>
        <Field label="Email">
          <input value={user.email} readOnly />
        </Field>
        <Field label="Dietary preference">
          <select name="diet" defaultValue={user.diet}>
            {[
              "No restriction",
              "Vegetarian",
              "Vegan",
              "Other / Prefer not to specify",
            ].map((d) => (
              <option key={d}>{d}</option>
            ))}
          </select>
        </Field>
        <Field label="Timezone">
          <input
            name="timezone"
            defaultValue={user.timezone}
            required
            list="timezones"
          />
          <datalist id="timezones">
            {[
              "America/Chicago",
              "America/New_York",
              "America/Denver",
              "America/Los_Angeles",
              "Asia/Kathmandu",
              "UTC",
            ].map((t) => (
              <option key={t}>{t}</option>
            ))}
          </datalist>
        </Field>
        <p className="hint">
          Currency: USD. Email notifications are not enabled in this release.
        </p>
        <button className="primary" disabled={busy}>
          {busy ? "Saving…" : "Save preferences"}
        </button>
      </form>
    </section>
  );
}
