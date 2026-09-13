"use client";
import { useState, useRef } from "react";
import { Submission } from "@/lib/submission";
import { api, body } from "@/lib/api";
import { cents, dollars, equalPreview, today } from "@/lib/money";
import {
  categories,
  type ExpenseInput,
  type Member,
  type Scope,
  type User,
} from "@/lib/types";
import { ErrorMessage, Field, Modal } from "./ui";
export default function ExpenseForm({
  user,
  householdId,
  members,
  onClose,
  onSaved,
  initial,
  expenseId,
  defaultRecurring = false,
}: {
  user: User;
  householdId: string | null;
  members: Member[];
  onClose: () => void;
  onSaved: () => void;
  initial?: ExpenseInput;
  expenseId?: string;
  defaultRecurring?: boolean;
}) {
  const submission = useRef(new Submission());
  const [scope, setScope] = useState<Scope>(
    initial?.scope || (householdId ? "HOUSEHOLD" : "PERSONAL"),
  );
  const [date, setDate] = useState(initial?.date || today()),
    [amount, setAmount] = useState(initial ? dollars(initial.amount) : "");
  const [method, setMethod] = useState(initial?.splitMethod || "EQUAL"),
    [selected, setSelected] = useState<string[]>(initial?.participants || []);
  const [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [recurring, setRecurring] = useState(defaultRecurring);
  const eligible = members
    .filter((m) => m.joined_at <= date && (!m.left_at || m.left_at >= date))
    .filter((m, i, all) => all.findIndex((x) => x.user_id === m.user_id) === i);
  const participants =
    scope === "PERSONAL"
      ? [user.id]
      : scope === "HOUSEHOLD"
        ? eligible.map((m) => m.user_id)
        : selected.filter((id) => eligible.some((m) => m.user_id === id));
  let preview = "Enter an amount";
  try {
    preview = equalPreview(cents(amount), participants.length);
  } catch {
    /* Incomplete input has no preview. */
  }
  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError("");
    setBusy(true);
    const f = new FormData(e.currentTarget);
    try {
      const values: Record<string, number> = {};
      if (method !== "EQUAL" && scope !== "PERSONAL")
        for (const id of participants)
          values[id] = cents(String(f.get(`share-${id}`) || "0"));
      const input: ExpenseInput = {
        title: String(f.get("title")),
        merchant: String(f.get("merchant")),
        amount: cents(amount),
        category: String(f.get("category")),
        scope,
        householdId: scope === "PERSONAL" ? null : householdId,
        payerId: scope === "PERSONAL" ? user.id : String(f.get("payer")),
        date,
        splitMethod: scope === "PERSONAL" ? "EQUAL" : method,
        participants,
        values,
        notes: String(f.get("notes")),
        version: initial?.version,
      };
      if (recurring)
        await api("/recurring", {
          method: "POST",
          body: body({
            expense: input,
            nextDue: f.get("due"),
            frequency: f.get("frequency"),
            active: true,
          }),
        });
      else
        await (
          expenseId ? api : submission.current.send.bind(submission.current)
        )(expenseId ? `/expenses/${expenseId}` : "/expenses", {
          method: expenseId ? "PATCH" : "POST",
          body: body(input),
        });
      onSaved();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal
      title={expenseId ? "Edit expense" : "Add an expense"}
      onClose={onClose}
    >
      <form onSubmit={submit}>
        <ErrorMessage message={error} />
        <div className="segmented">
          {(["PERSONAL", "HOUSEHOLD", "SELECTED_MEMBERS"] as Scope[]).map(
            (s) => (
              <button
                type="button"
                key={s}
                disabled={(s !== "PERSONAL" && !householdId) || !!expenseId}
                className={scope === s ? "active" : ""}
                onClick={() => setScope(s)}
              >
                {s === "PERSONAL"
                  ? "Just me"
                  : s === "HOUSEHOLD"
                    ? "Everyone"
                    : "Selected people"}
              </button>
            ),
          )}
        </div>
        <p className="hint">
          {scope === "PERSONAL"
            ? "Private. Only you can see this expense."
            : "Visible to household members. Shares use membership on the expense date."}
        </p>
        <Field label="What was it for?">
          <input
            name="title"
            required
            maxLength={120}
            placeholder="e.g. Weekly groceries"
            defaultValue={initial?.title}
          />
        </Field>
        <div className="form-grid">
          <Field label="Amount (USD)">
            <input
              inputMode="decimal"
              required
              value={amount}
              placeholder="0.00"
              onChange={(e) => setAmount(e.target.value)}
            />
          </Field>
          <Field label="Expense date">
            <input
              type="date"
              required
              value={date}
              max={today()}
              onChange={(e) => setDate(e.target.value)}
            />
          </Field>
          <Field label="Category">
            <select
              name="category"
              defaultValue={initial?.category || "Groceries"}
            >
              {categories.map((c) => (
                <option key={c}>{c}</option>
              ))}
            </select>
          </Field>
          <Field label="Merchant (optional)">
            <input
              name="merchant"
              maxLength={120}
              defaultValue={initial?.merchant}
            />
          </Field>
        </div>
        {scope !== "PERSONAL" && (
          <>
            <Field label="Paid by">
              <select name="payer" defaultValue={initial?.payerId || user.id}>
                {eligible.map((m) => (
                  <option value={m.user_id} key={m.id}>
                    {m.name}
                    {m.user_id === user.id ? " (you)" : ""}
                  </option>
                ))}
              </select>
            </Field>
            {scope === "SELECTED_MEMBERS" && (
              <fieldset>
                <legend>Who shares this expense?</legend>
                <div className="member-chips">
                  {eligible.map((m) => (
                    <label key={m.id}>
                      <input
                        type="checkbox"
                        checked={selected.includes(m.user_id)}
                        onChange={(e) =>
                          setSelected(
                            e.target.checked
                              ? [...selected, m.user_id]
                              : selected.filter((id) => id !== m.user_id),
                          )
                        }
                      />
                      {m.name}
                    </label>
                  ))}
                </div>
              </fieldset>
            )}
            <Field label="Split method">
              <select
                value={method}
                onChange={(e) => setMethod(e.target.value)}
              >
                <option value="EQUAL">Equally</option>
                <option value="FIXED">Custom fixed amounts</option>
                <option value="PERCENTAGE">Percentages</option>
              </select>
            </Field>
            {method !== "EQUAL" && (
              <div className="form-grid">
                {participants.map((id) => (
                  <Field
                    key={id}
                    label={`${eligible.find((m) => m.user_id === id)?.name || "You"} (${method === "FIXED" ? "USD" : "%"})`}
                  >
                    <input
                      name={`share-${id}`}
                      inputMode="decimal"
                      required
                      defaultValue={
                        initial?.values[id] !== undefined
                          ? dollars(initial.values[id])
                          : ""
                      }
                    />
                  </Field>
                ))}
              </div>
            )}
            {method === "EQUAL" && (
              <div className="split-preview">
                <span>
                  {participants.length}{" "}
                  {participants.length === 1 ? "person" : "people"}
                </span>
                <strong>{preview}</strong>
                <small>
                  Any remaining cents are assigned in a stable member order.
                </small>
              </div>
            )}
          </>
        )}
        <Field label="Notes (optional)">
          <textarea
            name="notes"
            rows={2}
            maxLength={2000}
            defaultValue={initial?.notes}
          />
        </Field>
        {!expenseId && (
          <label className="check-row">
            <input
              type="checkbox"
              checked={recurring}
              onChange={(e) => setRecurring(e.target.checked)}
            />{" "}
            Save as a recurring bill instead
          </label>
        )}
        {recurring && (
          <>
            <p className="hint">
              A template creates no spending until you record a due bill.
            </p>
            <div className="form-grid">
              <Field label="Next due">
                <input name="due" type="date" required defaultValue={today()} />
              </Field>
              <Field label="Frequency">
                <select name="frequency">
                  <option value="MONTHLY">Monthly</option>
                  <option value="WEEKLY">Weekly</option>
                  <option value="YEARLY">Yearly</option>
                </select>
              </Field>
            </div>
          </>
        )}
        <footer className="form-actions">
          <button type="button" className="secondary" onClick={onClose}>
            Cancel
          </button>
          <button className="primary" disabled={busy}>
            {busy
              ? "Saving…"
              : recurring
                ? "Save recurring bill"
                : "Save expense"}
          </button>
        </footer>
      </form>
    </Modal>
  );
}
