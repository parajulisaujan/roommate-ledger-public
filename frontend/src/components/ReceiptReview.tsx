"use client";
import { useEffect, useRef, useState } from "react";
import { Upload, Plus, Trash2, ScanLine, LockKeyhole } from "lucide-react";
import { api, body } from "@/lib/api";
import { cents, dollars, money, today } from "@/lib/money";
import {
  categories,
  type Member,
  type Receipt,
  type ReceiptItem,
  type User,
} from "@/lib/types";
import { Empty, ErrorMessage, Field } from "./ui";
const newItem = (): ReceiptItem => ({
  description: "",
  rawDescription: "",
  quantity: 1,
  unitPrice: null,
  amount: 0,
  category: "Groceries",
  confidence: null,
  scope: "PERSONAL",
  participants: [],
});
export default function ReceiptReview({
  user,
  householdId,
  members,
  onConfirmed,
}: {
  user: User;
  householdId: string | null;
  members: Member[];
  onConfirmed: () => void;
}) {
  const editor = useRef<HTMLFieldSetElement>(null);
  const [receipt, setReceipt] = useState<Receipt | null>(null),
    [receipts, setReceipts] = useState<Receipt[]>([]),
    [available, setAvailable] = useState(false);
  const [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [message, setMessage] = useState("");
  useEffect(() => {
    api<{ automatedExtraction: boolean }>("/receipts/capabilities")
      .then((r) => setAvailable(r.automatedExtraction))
      .catch((e) => setError(e.message));
    api<Receipt[]>("/receipts")
      .then(setReceipts)
      .catch((e) => setError(e.message));
  }, []);
  async function task(fn: () => Promise<void>) {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await fn();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function manual() {
    await task(async () => {
      const r = await api<{ id: string }>("/receipts", { method: "POST" });
      const loaded = await api<Receipt>(`/receipts/${r.id}`);
      loaded.draft.householdId = householdId;
      setReceipt(loaded);
    });
  }
  async function upload(file?: File) {
    if (!file) return;
    await task(async () => {
      if (file.size > 8 * 1024 * 1024)
        throw new Error("Use an image smaller than 8 MB.");
      const form = new FormData();
      form.set("file", file);
      const r = await api<Receipt>("/receipts/extract", {
        method: "POST",
        body: form,
      });
      r.draft.householdId = householdId;
      r.draft.payerId = user.id;
      setReceipt(r);
    });
  }
  function changeItem(index: number, patch: Partial<ReceiptItem>) {
    if (!receipt) return;
    setReceipt({
      ...receipt,
      draft: {
        ...receipt.draft,
        items: receipt.draft.items.map((item, i) =>
          i === index ? { ...item, ...patch } : item,
        ),
      },
    });
  }
  function amountChange(value: string, update: (amount: number) => void) {
    try {
      update(cents(value || "0"));
      setError("");
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function save(confirm: boolean) {
    if (!receipt) return;
    await task(async () => {
      for (const input of editor.current?.querySelectorAll<HTMLInputElement>(
        "input[data-money]",
      ) || [])
        cents(input.value || "0");
      const draft = {
        ...receipt.draft,
        subtotal: receipt.draft.items.reduce(
          (sum, item) => sum + item.amount,
          0,
        ),
      };
      const saved = await api<Receipt>(`/receipts/${receipt.id}`, {
        method: "PUT",
        body: body(draft),
      });
      setReceipt(saved);
      if (confirm) {
        setReceipt(
          await api<Receipt>(`/receipts/${receipt.id}/confirm`, {
            method: "POST",
          }),
        );
        setMessage(
          "Receipt confirmed. Your finalized item allocations now appear in the ledger.",
        );
        onConfirmed();
      } else setMessage("Draft saved. It has no effect on balances.");
    });
  }
  if (!receipt)
    return (
      <>
        <section className="panel receipt-intro">
          <div className="scan-icon">
            <ScanLine size={32} />
          </div>
          <span className="eyebrow">ONE RECEIPT. DIFFERENT SHARES.</span>
          <h2>Split the groceries, item by item.</h2>
          <p>
            Rice for everyone. Chicken for two. Shampoo just for you.
            <br />
            Review each item and decide who shares it.
          </p>
          <label className="upload-zone">
            <Upload size={27} />
            <strong>
              {busy ? "Processing your receipt…" : "Choose a receipt photo"}
            </strong>
            <span>JPEG, PNG or WebP · up to 8 MB</span>
            <input
              type="file"
              accept="image/jpeg,image/png,image/webp"
              capture="environment"
              disabled={busy}
              onChange={(e) => upload(e.target.files?.[0])}
            />
          </label>
          <p className="notice">
            {available
              ? "Automated extraction is available. Always review extracted amounts and assignments."
              : "Automated extraction is not configured. You can upload a photo and enter items manually. No extraction results will be invented."}
          </p>
          <button className="secondary" disabled={busy} onClick={manual}>
            <Plus size={17} /> Enter receipt manually
          </button>
          <p className="hint">
            <LockKeyhole size={13} /> Original images are discarded after
            processing. Receipt drafts are private.
          </p>
        </section>
        <ErrorMessage message={error} />
        {receipts.length > 0 && (
          <section className="panel">
            <div className="panel-heading">
              <h2>Your receipts</h2>
            </div>
            {receipts.map((r) => (
              <button
                className="simple-row full-width"
                key={r.id}
                onClick={() =>
                  task(async () =>
                    setReceipt(await api<Receipt>(`/receipts/${r.id}`)),
                  )
                }
              >
                <span>Receipt · {r.created_at.slice(0, 10)}</span>
                <span className="badge">{r.status.replaceAll("_", " ")}</span>
              </button>
            ))}
          </section>
        )}
      </>
    );
  const d = receipt.draft,
    confirmed = receipt.status === "CONFIRMED";
  const eligible = members
    .filter((m) => m.joined_at <= d.date && (!m.left_at || m.left_at >= d.date))
    .filter((m, i, all) => all.findIndex((x) => x.user_id === m.user_id) === i);
  const subtotal = d.items.reduce((sum, i) => sum + i.amount, 0),
    calculated = subtotal - d.discounts + d.tax + d.fees,
    difference = d.total - calculated;
  function patchDraft(patch: Partial<typeof d>) {
    setReceipt({ ...receipt!, draft: { ...d, ...patch } });
  }
  return (
    <section className="panel receipt-editor">
      <div className="panel-heading">
        <div>
          <h2>{confirmed ? "Confirmed receipt" : "Review your receipt"}</h2>
          <p>
            {confirmed
              ? "Finalized item assignments"
              : "Correct the details, assign each item, then confirm."}
          </p>
        </div>
        <span className="badge">{receipt.status.replaceAll("_", " ")}</span>
      </div>
      <ErrorMessage message={error || receipt.error || ""} />
      {message && (
        <p className="success" role="status">
          {message}
        </p>
      )}
      {receipt.duplicate && (
        <p className="notice">
          This exact image was uploaded before. Check your existing receipts
          before confirming another copy.
        </p>
      )}
      <fieldset ref={editor} disabled={busy || confirmed}>
        <div className="form-grid">
          <Field label="Merchant">
            <input
              value={d.merchant}
              maxLength={120}
              onChange={(e) => patchDraft({ merchant: e.target.value })}
            />
          </Field>
          <Field label="Purchase date">
            <input
              type="date"
              value={d.date}
              max={today()}
              onChange={(e) => patchDraft({ date: e.target.value })}
            />
          </Field>
          <Field label="Paid by">
            <select
              value={d.payerId || user.id}
              onChange={(e) => patchDraft({ payerId: e.target.value })}
            >
              <option value={user.id}>{user.name} (you)</option>
              {eligible
                .filter((m) => m.user_id !== user.id)
                .map((m) => (
                  <option key={m.id} value={m.user_id}>
                    {m.name}
                  </option>
                ))}
            </select>
          </Field>
        </div>
        {!d.items.length && (
          <Empty title="Add your first receipt item">
            Item details are editable until you confirm.
          </Empty>
        )}
        {d.items.map((item, index) => (
          <article className="receipt-item" key={index}>
            <div className="item-number">
              {String(index + 1).padStart(2, "0")}
            </div>
            <div className="item-fields">
              <div className="form-grid">
                <Field label="Item">
                  <input
                    aria-label={`Item ${index + 1} name`}
                    value={item.description}
                    maxLength={120}
                    placeholder="e.g. Rice"
                    onChange={(e) =>
                      changeItem(index, { description: e.target.value })
                    }
                  />
                </Field>
                <Field label="Line total (USD)">
                  <input
                    data-money
                    key={`${receipt.id}-${index}-${item.amount}`}
                    aria-label={`Item ${index + 1} amount`}
                    inputMode="decimal"
                    defaultValue={dollars(item.amount)}
                    onBlur={(e) =>
                      amountChange(e.target.value, (amount) =>
                        changeItem(index, { amount }),
                      )
                    }
                  />
                </Field>
              </div>
              <div className="item-meta">
                <Field label="Quantity">
                  <input
                    type="number"
                    min="0.001"
                    max="10000"
                    step="0.001"
                    value={item.quantity}
                    onChange={(e) =>
                      changeItem(index, { quantity: Number(e.target.value) })
                    }
                  />
                </Field>
                <Field label="Category">
                  <select
                    value={item.category}
                    onChange={(e) =>
                      changeItem(index, { category: e.target.value })
                    }
                  >
                    {categories.map((c) => (
                      <option key={c}>{c}</option>
                    ))}
                  </select>
                </Field>
                <button
                  className="icon-button"
                  aria-label={`Remove item ${index + 1}`}
                  onClick={() =>
                    patchDraft({ items: d.items.filter((_, i) => i !== index) })
                  }
                >
                  <Trash2 size={17} />
                </button>
              </div>
              {item.rawDescription && (
                <small>
                  Original: {item.rawDescription}
                  {item.confidence !== null
                    ? ` · Confidence ${Math.round(item.confidence * 100)}%`
                    : ""}
                </small>
              )}
              <div className="item-shortcuts">
                <button
                  className={
                    item.scope === "HOUSEHOLD" ? "chip active" : "chip"
                  }
                  disabled={!householdId}
                  onClick={() =>
                    changeItem(index, {
                      scope: "HOUSEHOLD",
                      participants: eligible.map((m) => m.user_id),
                    })
                  }
                >
                  Everyone
                </button>
                <button
                  className={item.scope === "PERSONAL" ? "chip active" : "chip"}
                  onClick={() =>
                    changeItem(index, {
                      scope: "PERSONAL",
                      participants: [user.id],
                    })
                  }
                >
                  Me only · private
                </button>
                <button
                  className={
                    item.scope === "SELECTED_MEMBERS" ? "chip active" : "chip"
                  }
                  disabled={!householdId}
                  onClick={() =>
                    changeItem(index, {
                      scope: "SELECTED_MEMBERS",
                      participants: [user.id],
                    })
                  }
                >
                  Choose roommates
                </button>
                {index > 0 && (
                  <button
                    className="text-button"
                    onClick={() =>
                      changeItem(index, {
                        scope: d.items[index - 1].scope,
                        participants: [...d.items[index - 1].participants],
                      })
                    }
                  >
                    Same as previous
                  </button>
                )}
                <button
                  className="text-button"
                  onClick={() =>
                    patchDraft({
                      items: d.items.map((x, i) =>
                        i > index
                          ? {
                              ...x,
                              scope: item.scope,
                              participants: [...item.participants],
                            }
                          : x,
                      ),
                    })
                  }
                >
                  Apply to remaining
                </button>
              </div>
              {item.scope === "SELECTED_MEMBERS" && (
                <div className="member-chips">
                  {eligible.map((m) => (
                    <label key={m.id}>
                      <input
                        type="checkbox"
                        checked={item.participants.includes(m.user_id)}
                        onChange={(e) =>
                          changeItem(index, {
                            participants: e.target.checked
                              ? [...item.participants, m.user_id]
                              : item.participants.filter(
                                  (id) => id !== m.user_id,
                                ),
                          })
                        }
                      />
                      {m.name}
                    </label>
                  ))}
                </div>
              )}
            </div>
          </article>
        ))}
        <button
          className="secondary"
          onClick={() => patchDraft({ items: [...d.items, newItem()] })}
        >
          <Plus size={16} /> Add item
        </button>
        <div className="reconciliation">
          <h3>Make sure it adds up</h3>
          <div className="simple-row">
            <span>Items subtotal</span>
            <strong>{money(subtotal)}</strong>
          </div>
          <div className="form-grid">
            {(["discounts", "tax", "fees", "total"] as const).map((key) => (
              <Field
                key={key}
                label={`${key === "total" ? "Printed receipt total" : key === "fees" ? "Fees / tip" : key.charAt(0).toUpperCase() + key.slice(1)} (USD)`}
              >
                <input
                  data-money
                  key={`${key}-${d[key]}`}
                  inputMode="decimal"
                  defaultValue={dollars(d[key])}
                  onBlur={(e) =>
                    amountChange(e.target.value, (amount) =>
                      patchDraft({ [key]: amount, subtotal }),
                    )
                  }
                />
              </Field>
            ))}
          </div>
          <div
            className={`simple-row ${difference === 0 ? "reconciled" : "unreconciled"}`}
          >
            <strong>
              {difference === 0 ? "Totals match" : "Difference to resolve"}
            </strong>
            <strong>{money(difference)}</strong>
          </div>
          <p className="hint">
            Discounts, tax and fees are spread proportionally across item
            prices, then split among each item’s participants. Remaining cents
            use a stable order. Confirming accepts this allocation.
          </p>
        </div>
      </fieldset>
      <footer className="form-actions">
        <button
          className="secondary"
          onClick={() => {
            if (
              confirmed ||
              window.confirm(
                "Leave receipt review? Save your draft first to keep changes.",
              )
            ) {
              setReceipt(null);
              void task(async () =>
                setReceipts(await api<Receipt[]>("/receipts")),
              );
            }
          }}
        >
          Back to receipts
        </button>
        {!confirmed && (
          <>
            <button
              className="secondary"
              disabled={busy}
              onClick={() => save(false)}
            >
              Save draft
            </button>
            <button
              className="primary"
              disabled={busy || difference !== 0 || !d.items.length}
              onClick={() => save(true)}
            >
              {busy ? "Saving…" : "Confirm allocations"}
            </button>
          </>
        )}
      </footer>
    </section>
  );
}
