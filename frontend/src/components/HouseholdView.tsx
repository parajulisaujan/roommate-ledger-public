"use client";
import { useEffect, useState } from "react";
import { Copy, Plus, Users } from "lucide-react";
import { api, body } from "@/lib/api";
import { type Household, type Member, type User } from "@/lib/types";
import { ErrorMessage, Field } from "./ui";
export default function HouseholdView({
  user,
  household,
  members,
  onChanged,
}: {
  user: User;
  household: Household | null;
  members: Member[];
  onChanged: () => void;
}) {
  const [error, setError] = useState(""),
    [invite, setInvite] = useState(""),
    [message, setMessage] = useState(""),
    [busy, setBusy] = useState(false);
  const [activity, setActivity] = useState<
    { action: string; name: string; created_at: string }[]
  >([]);
  const owner = members.some(
    (m) => m.user_id === user.id && m.role === "OWNER" && !m.left_at,
  );
  useEffect(() => {
    if (household)
      api<typeof activity>(`/households/${household.id}/activity`)
        .then(setActivity)
        .catch((e) => setError(e.message));
  }, [household, members]);
  async function run(fn: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await fn();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function submit(e: React.FormEvent<HTMLFormElement>, create: boolean) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    await run(async () => {
      await api(create ? "/households" : "/invitations/accept", {
        method: "POST",
        body: create
          ? body({ name: f.get("name") })
          : body({ token: String(f.get("token")).trim() }),
      });
      setMessage(create ? "Household created." : "You joined the household.");
      onChanged();
    });
  }
  return (
    <>
      <ErrorMessage message={error} />
      {message && (
        <p role="status" className="success">
          {message}
        </p>
      )}
      {household && (
        <>
          <section className="panel">
            <div className="panel-heading">
              <div>
                <h2>{household.name}</h2>
                <p>People who make this place home</p>
              </div>
              {owner && (
                <button
                  className="secondary"
                  disabled={busy}
                  onClick={() =>
                    run(async () =>
                      setInvite(
                        (
                          await api<{ token: string }>(
                            `/households/${household.id}/invitations`,
                            { method: "POST" },
                          )
                        ).token,
                      ),
                    )
                  }
                >
                  <Plus size={16} /> Invite roommate
                </button>
              )}
            </div>
            {invite && (
              <div className="invite-code">
                <p>
                  Single-use invite · expires in 7 days. Share this code with
                  your roommate.
                </p>
                <code>{invite}</code>
                <button
                  className="icon-button"
                  aria-label="Copy invitation code"
                  onClick={() =>
                    run(async () => {
                      await navigator.clipboard.writeText(invite);
                      setMessage("Invite copied.");
                    })
                  }
                >
                  <Copy size={17} />
                </button>
              </div>
            )}
            {owner && (
              <form
                className="inline-form"
                onSubmit={(e) => {
                  e.preventDefault();
                  const f = new FormData(e.currentTarget);
                  void run(async () => {
                    await api(`/households/${household.id}/invitations/email`, {
                      method: "POST",
                      body: body({ email: f.get("email") }),
                    });
                    setMessage("Invitation email sent.");
                  });
                }}
              >
                <Field label="Roommate email">
                  <input name="email" type="email" required maxLength={254} />
                </Field>
                <button className="secondary" disabled={busy}>
                  Email invitation
                </button>
              </form>
            )}
            <div className="members-list">
              {members.map((m) => (
                <div className="member-row" key={m.id}>
                  <span className="avatar">{m.name.slice(0, 1)}</span>
                  <div>
                    <strong>
                      {m.name}
                      {m.user_id === user.id ? " (you)" : ""}
                    </strong>
                    <small>
                      {m.diet} · {m.joined_at} → {m.left_at || "Present"}
                    </small>
                  </div>
                  <span className="badge neutral">
                    {m.left_at
                      ? "Former member"
                      : m.role === "OWNER"
                        ? "Owner"
                        : "Member"}
                  </span>
                  {owner && m.role !== "OWNER" && !m.left_at && (
                    <button
                      className="text-button danger-text"
                      disabled={busy}
                      onClick={() => {
                        if (
                          window.confirm(
                            `End ${m.name}’s membership today? Historical expenses stay intact. They lose household access.`,
                          )
                        )
                          void run(async () => {
                            await api(
                              `/households/${household.id}/members/${m.id}`,
                              { method: "DELETE" },
                            );
                            onChanged();
                          });
                      }}
                    >
                      Remove
                    </button>
                  )}
                </div>
              ))}
            </div>
            <p className="hint">
              Membership dates preserve past allocations. Dietary preferences
              never create financial obligations.
            </p>
            {owner && (
              <form
                className="inline-form"
                onSubmit={(e) => {
                  e.preventDefault();
                  const f = new FormData(e.currentTarget);
                  void run(async () => {
                    await api(`/households/${household.id}`, {
                      method: "PATCH",
                      body: body({ name: f.get("name") }),
                    });
                    onChanged();
                  });
                }}
              >
                <Field label="Household name">
                  <input
                    name="name"
                    defaultValue={household.name}
                    required
                    maxLength={80}
                  />
                </Field>
                <button className="secondary" disabled={busy}>
                  Update name
                </button>
              </form>
            )}
          </section>
          <section className="panel">
            <div className="panel-heading">
              <h2>Household activity</h2>
              <span className="badge neutral">Latest 50 events</span>
            </div>
            {activity.map((a, i) => (
              <div className="simple-row" key={i}>
                <span>
                  {a.name} · {a.action.toLowerCase().replaceAll("_", " ")}
                </span>
                <small>{a.created_at.slice(0, 10)}</small>
              </div>
            ))}
          </section>
        </>
      )}
      <div className="two-columns">
        <section className="panel">
          <Users className="section-icon" />
          <h2>Create a household</h2>
          <p>A shared space for bills, groceries and clear balances.</p>
          <form onSubmit={(e) => submit(e, true)}>
            <Field label="Household name">
              <input
                name="name"
                placeholder="e.g. Apartment 204"
                required
                maxLength={80}
              />
            </Field>
            <button className="primary" disabled={busy}>
              Create household
            </button>
          </form>
        </section>
        <section className="panel">
          <h2>Have an invitation?</h2>
          <p>
            Sign in with your own account, then enter the code your roommate
            shared.
          </p>
          <form onSubmit={(e) => submit(e, false)}>
            <Field label="Invitation code">
              <input name="token" required maxLength={100} autoComplete="off" />
            </Field>
            <button className="secondary" disabled={busy}>
              Join household
            </button>
          </form>
        </section>
      </div>
    </>
  );
}
