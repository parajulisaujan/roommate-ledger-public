"use client";
import { useEffect, useState } from "react";
import { CalendarDays, Pause, Play } from "lucide-react";
import { api, body } from "@/lib/api";
import { dollars, cents, money, today } from "@/lib/money";
import type { Bill } from "@/lib/types";
import { Empty, ErrorMessage, Field, Modal } from "./ui";
export default function BillsView({
  householdId,
  userId,
  refresh,
  onChanged,
  onAdd,
}: {
  householdId: string | null;
  userId: string;
  refresh: number;
  onChanged: () => void;
  onAdd: () => void;
}) {
  const [bills, setBills] = useState<Bill[]>([]),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [editing, setEditing] = useState<Bill | null>(null);
  useEffect(() => {
    api<Bill[]>(`/recurring${householdId ? `?householdId=${householdId}` : ""}`)
      .then(setBills)
      .catch((e) => setError(e.message));
  }, [householdId, refresh]);
  async function run(fn: () => Promise<unknown>) {
    setBusy(true);
    setError("");
    try {
      await fn();
      onChanged();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function pause(b: Bill) {
    return run(() =>
      api(`/recurring/${b.id}`, {
        method: "PATCH",
        body: body({
          expense: b.expense,
          nextDue: b.next_due,
          frequency: b.frequency,
          active: !b.active,
        }),
      }),
    );
  }
  return (
    <section className="panel">
      <div className="panel-heading">
        <div>
          <h2>
            {householdId
              ? "Household recurring bills"
              : "Your private recurring bills"}
          </h2>
          <p>Templates keep future bills separate from past spending.</p>
        </div>
        <button className="secondary" onClick={onAdd}>
          Add recurring bill
        </button>
      </div>
      <ErrorMessage message={error} />
      {bills.length ? (
        bills.map((b) => (
          <article className="bill-row" key={b.id}>
            <span className="category-icon">
              <CalendarDays size={19} />
            </span>
            <div>
              <strong>{b.expense.title}</strong>
              <small>
                {b.frequency.toLowerCase()} · due {b.next_due} ·{" "}
                {b.active ? "Active" : "Paused"}
              </small>
            </div>
            <strong>{money(b.expense.amount)}</strong>
            {b.owner_id === userId && (
              <div className="row-actions">
                <button
                  className="icon-button"
                  aria-label={`${b.active ? "Pause" : "Resume"} ${b.expense.title}`}
                  disabled={busy}
                  onClick={() => pause(b)}
                >
                  {b.active ? <Pause size={16} /> : <Play size={16} />}
                </button>
                <button className="text-button" onClick={() => setEditing(b)}>
                  Edit
                </button>
                <button
                  className="secondary"
                  disabled={busy || !b.active || b.next_due > today()}
                  onClick={() =>
                    run(() =>
                      api(`/recurring/${b.id}/record`, { method: "POST" }),
                    )
                  }
                >
                  Record due bill
                </button>
              </div>
            )}
          </article>
        ))
      ) : (
        <Empty title="Stay ahead of the regular stuff">
          Save rent, internet or a personal subscription as a recurring bill.
          <br />
          <button className="text-button" onClick={onAdd}>
            Create your first recurring bill
          </button>
        </Empty>
      )}
      <p className="hint">
        Bills are never charged automatically. Recording creates one expense and
        advances the due date. Edits affect the template only.
      </p>
      {editing && (
        <Modal title="Edit recurring bill" onClose={() => setEditing(null)}>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const f = new FormData(e.currentTarget);
              void run(async () => {
                await api(`/recurring/${editing.id}`, {
                  method: "PATCH",
                  body: body({
                    expense: {
                      ...editing.expense,
                      title: f.get("title"),
                      amount: cents(String(f.get("amount"))),
                    },
                    nextDue: f.get("due"),
                    frequency: f.get("frequency"),
                    active: editing.active,
                  }),
                });
                setEditing(null);
              });
            }}
          >
            <Field label="Title">
              <input
                name="title"
                defaultValue={editing.expense.title}
                required
                maxLength={120}
              />
            </Field>
            <Field label="Amount (USD)">
              <input
                name="amount"
                defaultValue={dollars(editing.expense.amount)}
                required
                inputMode="decimal"
              />
            </Field>
            <Field label="Next due">
              <input
                name="due"
                type="date"
                defaultValue={editing.next_due}
                required
              />
            </Field>
            <Field label="Frequency">
              <select name="frequency" defaultValue={editing.frequency}>
                <option value="MONTHLY">Monthly</option>
                <option value="WEEKLY">Weekly</option>
                <option value="YEARLY">Yearly</option>
              </select>
            </Field>
            <p className="hint">
              For custom fixed splits, recreate the template when changing
              amounts so allocations stay explicit.
            </p>
            <button className="primary" disabled={busy}>
              Save template
            </button>
          </form>
        </Modal>
      )}
    </section>
  );
}
