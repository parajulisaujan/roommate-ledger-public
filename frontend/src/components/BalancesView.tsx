"use client";
import { useEffect, useState, useRef } from "react";
import { ArrowUpRight, Check, Plus } from "lucide-react";
import { Submission } from "@/lib/submission";
import { api, body } from "@/lib/api";
import { cents, money, today } from "@/lib/money";
import type { Balance, User } from "@/lib/types";
import { Empty, ErrorMessage, Field, Modal } from "./ui";
type Settlement = {
  id: string;
  from_name: string;
  to_name: string;
  amount: number;
  method: string;
  payment_date: string;
};
export default function BalancesView({
  user,
  householdId,
  refresh,
  onChanged,
}: {
  user: User;
  householdId: string;
  refresh: number;
  onChanged: () => void;
}) {
  const submission = useRef(new Submission());
  const [balances, setBalances] = useState<Balance[]>([]),
    [history, setHistory] = useState<Settlement[]>([]),
    [error, setError] = useState(""),
    [open, setOpen] = useState(false),
    [busy, setBusy] = useState(false);
  useEffect(() => {
    let live = true;
    Promise.all([
      api<Balance[]>(`/households/${householdId}/balances`),
      api<Settlement[]>(`/households/${householdId}/settlements`),
    ])
      .then(([b, s]) => {
        if (live) {
          setBalances(b);
          setHistory(s);
        }
      })
      .catch((e) => {
        if (live) setError(e.message);
      });
    return () => {
      live = false;
    };
  }, [householdId, refresh]);
  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    setBusy(true);
    setError("");
    try {
      await submission.current.send(`/households/${householdId}/settlements`, {
        method: "POST",
        body: body({
          fromUser: user.id,
          toUser: f.get("to"),
          amount: cents(String(f.get("amount"))),
          method: f.get("method"),
          date: f.get("date"),
        }),
      });
      setOpen(false);
      onChanged();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <ErrorMessage message={error} />
      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>Everyone’s balance</h2>
            <p>Calculated from expenses, finalized shares and repayments</p>
          </div>
          <button className="primary" onClick={() => setOpen(true)}>
            <Plus size={16} /> Record a payment
          </button>
        </div>
        <div className="balance-cards">
          {balances.map((b) => (
            <article key={b.id}>
              <span className="avatar">{b.name.slice(0, 1)}</span>
              <h3>
                {b.name}
                {b.id === user.id ? " (you)" : ""}
              </h3>
              <strong className={b.balance < 0 ? "owed" : "receivable"}>
                {money(Math.abs(b.balance))}
              </strong>
              <span>
                {b.balance === 0
                  ? "All settled up"
                  : b.balance > 0
                    ? "is owed by the household"
                    : "owes the household"}
              </span>
            </article>
          ))}
        </div>
        <p className="hint">
          Positive balances mean money is owed to that member. These are
          household net positions, not a claim against a specific roommate.
        </p>
      </section>
      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>Settlement history</h2>
            <a href={`/api/export/settlements?householdId=${householdId}`}>
              Export settlements CSV
            </a>
            <p>Record keeping only. RoommateLedger never moves money.</p>
          </div>
        </div>
        {history.length ? (
          history.map((s) => (
            <div className="settlement-row" key={s.id}>
              <span className="category-icon">
                <ArrowUpRight size={20} />
              </span>
              <div>
                <strong>
                  {s.from_name} → {s.to_name}
                </strong>
                <small>
                  {s.payment_date} · {s.method}
                </small>
              </div>
              <strong>{money(s.amount)}</strong>
              <span className="badge">
                <Check size={12} /> Recorded
              </span>
            </div>
          ))
        ) : (
          <Empty title="No repayments recorded">
            After paying a roommate, record it here to update the ledger.
          </Empty>
        )}
      </section>
      {open && (
        <Modal title="Record a payment you made" onClose={() => setOpen(false)}>
          <form onSubmit={submit}>
            <ErrorMessage message={error} />
            <p>
              Record money you already sent outside this app. This does not
              initiate a transfer.
            </p>
            <Field label="Paid to">
              <select name="to" required>
                {balances
                  .filter((b) => b.id !== user.id)
                  .map((b) => (
                    <option key={b.id} value={b.id}>
                      {b.name}
                    </option>
                  ))}
              </select>
            </Field>
            <div className="form-grid">
              <Field label="Amount (USD)">
                <input name="amount" inputMode="decimal" required />
              </Field>
              <Field label="Payment date">
                <input
                  name="date"
                  type="date"
                  defaultValue={today()}
                  max={today()}
                  required
                />
              </Field>
            </div>
            <Field label="Method">
              <select name="method">
                {["Cash", "Zelle", "Venmo", "Bank transfer", "Other"].map(
                  (m) => (
                    <option key={m}>{m}</option>
                  ),
                )}
              </select>
            </Field>
            <button className="primary" disabled={busy || balances.length < 2}>
              {busy ? "Recording…" : "Confirm payment record"}
            </button>
          </form>
        </Modal>
      )}
    </>
  );
}
