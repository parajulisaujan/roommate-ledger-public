"use client";
import { useEffect, useState } from "react";
import { Search, ArrowLeft, ArrowRight, LockKeyhole } from "lucide-react";
import { api } from "@/lib/api";
import { categories, type Expense, type ExpenseInput } from "@/lib/types";
import { money } from "@/lib/money";
import { Empty, ErrorMessage, Field, Modal } from "./ui";
export default function ExpenseHistory({
  householdId,
  refresh,
  userId,
  onEdit,
  onChanged,
}: {
  householdId: string | null;
  refresh: number;
  userId: string;
  onEdit: (id: string, input: ExpenseInput) => void;
  onChanged: () => void;
}) {
  const [result, setResult] = useState<{ items: Expense[]; total: number }>({
    items: [],
    total: 0,
  });
  const [page, setPage] = useState(0),
    [query, setQuery] = useState(""),
    [category, setCategory] = useState(""),
    [from, setFrom] = useState(""),
    [to, setTo] = useState("");
  const [error, setError] = useState(""),
    [loading, setLoading] = useState(true),
    [detail, setDetail] = useState<Expense | null>(null),
    [revision, setRevision] = useState(0);
  useEffect(() => {
    let active = true;
    const timeout = setTimeout(() => {
      setLoading(true);
      const params = new URLSearchParams({
        page: String(page),
        search: query,
        category,
      });
      if (householdId) params.set("householdId", householdId);
      if (from) params.set("from", from);
      if (to) params.set("to", to);
      api<typeof result>(`/expenses?${params}`)
        .then((r) => {
          if (active) {
            setResult(r);
            setError("");
          }
        })
        .catch((e) => {
          if (active) setError(e.message);
        })
        .finally(() => {
          if (active) setLoading(false);
        });
    }, 200);
    return () => {
      active = false;
      clearTimeout(timeout);
    };
  }, [householdId, page, query, category, from, to, refresh, revision]);
  async function open(id: string) {
    try {
      setDetail(await api<Expense>(`/expenses/${id}`));
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function remove() {
    if (!detail) return;
    try {
      await api(`/expenses/${detail.id}`, { method: "DELETE" });
      setDetail(null);
      setRevision((r) => r + 1);
      onChanged();
    } catch (e) {
      setError((e as Error).message);
    }
  }
  function edit() {
    if (!detail) return;
    onEdit(detail.id, {
      title: detail.title,
      merchant: detail.merchant || "",
      amount: detail.amount,
      category: detail.category,
      scope: detail.scope,
      householdId: detail.household_id,
      payerId: detail.payer_id,
      date: detail.expense_date,
      splitMethod:
        detail.split_method === "PERCENTAGE" ? "FIXED" : detail.split_method,
      participants: detail.allocations?.map((a) => a.user_id) || [],
      values: Object.fromEntries(
        detail.allocations?.map((a) => [a.user_id, a.amount]) || [],
      ),
      notes: detail.notes || "",
      version: detail.version,
    });
    setDetail(null);
  }
  return (
    <section className="panel history">
      <div className="panel-heading">
        <div>
          <h2>
            {householdId ? "Household expenses" : "Your private expenses"}
          </h2>
          <p>
            {householdId
              ? "The shared stuff, all in one place"
              : "Only you can access these records"}
          </p>
        </div>
        <span className="badge">{result.total} records</span>
      </div>
      <div className="filters">
        <label className="search">
          <Search size={17} />
          <input
            aria-label="Search expenses"
            placeholder="Search expenses or merchants"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setPage(0);
            }}
          />
        </label>
        <select
          aria-label="Filter category"
          value={category}
          onChange={(e) => {
            setCategory(e.target.value);
            setPage(0);
          }}
        >
          <option value="">All categories</option>
          {categories.map((c) => (
            <option key={c}>{c}</option>
          ))}
        </select>
        <Field label="From">
          <input
            type="date"
            value={from}
            onChange={(e) => {
              setFrom(e.target.value);
              setPage(0);
            }}
          />
        </Field>
        <Field label="To">
          <input
            type="date"
            value={to}
            onChange={(e) => {
              setTo(e.target.value);
              setPage(0);
            }}
          />
        </Field>
      </div>
      <ErrorMessage message={error} />
      <p>
        <a
          className="text-button"
          href={`/api/export/expenses?${new URLSearchParams({ ...(householdId ? { householdId } : {}), ...(from ? { from } : {}), ...(to ? { to } : {}) })}`}
        >
          Export {householdId ? "household" : "private"} expenses CSV
        </a>
      </p>
      {loading ? (
        <p className="loading">Loading expenses…</p>
      ) : result.items.length ? (
        <div className="expense-table">
          <div className="expense-table-head">
            <span>Expense</span>
            <span>Paid by</span>
            <span>Sharing</span>
            <span>Amount</span>
          </div>
          {result.items.map((e) => (
            <button
              className="expense-row"
              key={e.id}
              onClick={() => open(e.id)}
            >
              <span className="expense-identity">
                <span
                  className={`category-icon ${e.scope === "PERSONAL" ? "private" : ""}`}
                >
                  {e.category.slice(0, 1)}
                </span>
                <span>
                  <strong>{e.title}</strong>
                  <small>
                    {e.expense_date} · {e.category}
                    {e.merchant ? ` · ${e.merchant}` : ""}
                  </small>
                </span>
              </span>
              <span className="payer-cell">{e.payer_name}</span>
              <span className="scope-cell">
                <span
                  className={`badge ${e.scope === "PERSONAL" ? "neutral" : ""}`}
                >
                  {e.scope === "PERSONAL" ? (
                    <>
                      <LockKeyhole size={11} /> Private
                    </>
                  ) : e.scope === "HOUSEHOLD" ? (
                    "Everyone"
                  ) : (
                    "Selected"
                  )}
                </span>
              </span>
              <strong>{money(e.amount)}</strong>
            </button>
          ))}
        </div>
      ) : (
        <Empty title="No expenses here yet">
          Add your first expense, or adjust the filters.
        </Empty>
      )}
      <div className="pagination">
        <span>
          Page {page + 1} of {Math.max(1, Math.ceil(result.total / 25))}
        </span>
        <button
          className="icon-button"
          aria-label="Previous page"
          disabled={!page}
          onClick={() => setPage(page - 1)}
        >
          <ArrowLeft size={17} />
        </button>
        <button
          className="icon-button"
          aria-label="Next page"
          disabled={(page + 1) * 25 >= result.total}
          onClick={() => setPage(page + 1)}
        >
          <ArrowRight size={17} />
        </button>
      </div>
      {detail && (
        <Modal title={detail.title} onClose={() => setDetail(null)}>
          <div className="detail-total">{money(detail.amount)}</div>
          <p>
            {detail.expense_date} · {detail.category} · Paid by{" "}
            {detail.payer_name}
          </p>
          <p>{detail.notes}</p>
          <h3>Final responsibility</h3>
          {detail.allocations?.map((a) => (
            <div className="simple-row" key={a.user_id}>
              <span>{a.name}</span>
              <strong>{money(a.amount)}</strong>
            </div>
          ))}
          {detail.owner_id === userId && !detail.receipt_id && (
            <footer className="form-actions">
              <button className="danger" onClick={remove}>
                Delete expense
              </button>
              <button className="primary" onClick={edit}>
                Edit expense
              </button>
            </footer>
          )}
          {detail.receipt_id && (
            <p className="hint">
              Confirmed receipt item. Its allocation is preserved as part of the
              receipt.
            </p>
          )}
        </Modal>
      )}
    </section>
  );
}
