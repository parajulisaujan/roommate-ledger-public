"use client";
import { useCallback, useEffect, useState } from "react";
import {
  BookOpen,
  LayoutDashboard,
  Wallet,
  House,
  ScanLine,
  ChartNoAxesCombined,
  ArrowLeftRight,
  CalendarDays,
  Settings,
  LogOut,
  Plus,
  LockKeyhole,
  Menu,
  X,
  ArrowRight,
} from "lucide-react";
import { api } from "@/lib/api";
import { money, today } from "@/lib/money";
import type {
  Analytics,
  Balance,
  ExpenseInput,
  Household,
  Member,
  User,
} from "@/lib/types";
import Auth from "./Auth";
import AccountLink from "./AccountLink";
import AccountActions from "./AccountActions";
import AnalyticsView from "./AnalyticsView";
import ExpenseForm from "./ExpenseForm";
import ExpenseHistory from "./ExpenseHistory";
import HouseholdView from "./HouseholdView";
import BalancesView from "./BalancesView";
import BillsView from "./BillsView";
import ProfileView from "./ProfileView";
import ReceiptReview from "./ReceiptReview";
import { Empty, ErrorMessage } from "./ui";
type Tab =
  | "Dashboard"
  | "My finances"
  | "Household"
  | "Receipts"
  | "Balances"
  | "Recurring bills"
  | "Reports"
  | "Settings";
const navigation = [
  { name: "Dashboard", icon: LayoutDashboard },
  { name: "My finances", icon: Wallet },
  { name: "Household", icon: House },
  { name: "Receipts", icon: ScanLine },
  { name: "Balances", icon: ArrowLeftRight },
  { name: "Recurring bills", icon: CalendarDays },
  { name: "Reports", icon: ChartNoAxesCombined },
] as const;
export default function LedgerApp() {
  const [accountLink, setAccountLink] = useState<{
    kind: "reset" | "verify";
    token: string;
  } | null>(null);
  const [user, setUser] = useState<User | null>(null),
    [ready, setReady] = useState(false),
    [tab, setTab] = useState<Tab>("Dashboard");
  const [households, setHouseholds] = useState<Household[]>([]),
    [activeId, setActiveId] = useState<string | null>(null),
    [members, setMembers] = useState<Member[]>([]);
  const [analyticsResult, setAnalytics] = useState<{
      key: string;
      data: Analytics;
    } | null>(null),
    [balances, setBalances] = useState<Balance[]>([]),
    [month, setMonth] = useState(today().slice(0, 7));
  const [error, setError] = useState(""),
    [refresh, setRefresh] = useState(0),
    [add, setAdd] = useState(false),
    [edit, setEdit] = useState<{ id: string; input: ExpenseInput } | null>(
      null,
    ),
    [mobile, setMobile] = useState(false),
    [shared, setShared] = useState(false);
  const changed = useCallback(() => setRefresh((r) => r + 1), []);
  useEffect(() => {
    function readAccountLink() {
      const match = window.location.hash.match(
        /^#(reset|verify)=([A-Za-z0-9_-]+)$/,
      );
      if (match) {
        setAccountLink({
          kind: match[1] as "reset" | "verify",
          token: match[2],
        });
        window.history.replaceState(null, "", window.location.pathname);
      }
    }
    window.addEventListener("hashchange", readAccountLink);
    api<User>("/auth/me")
      .then(setUser)
      .catch(() => {})
      .finally(() => {
        readAccountLink();
        setReady(true);
      });
    return () => window.removeEventListener("hashchange", readAccountLink);
  }, []);
  useEffect(() => {
    if (!user || (user.verification_required && !user.email_verified)) return;
    let live = true;
    api<Household[]>("/households")
      .then((h) => {
        if (live) {
          setHouseholds(h);
          setActiveId((old) =>
            h.some((x) => x.id === old) ? old : h[0]?.id || null,
          );
        }
      })
      .catch((e) => {
        if (live) setError(e.message);
      });
    return () => {
      live = false;
    };
  }, [user, refresh]);
  useEffect(() => {
    if (
      !activeId ||
      !user ||
      (user.verification_required && !user.email_verified)
    )
      return;
    let live = true;
    Promise.all([
      api<Member[]>(`/households/${activeId}/members`),
      api<Balance[]>(`/households/${activeId}/balances`),
    ])
      .then(([m, b]) => {
        if (live) {
          setMembers(m);
          setBalances(b);
        }
      })
      .catch((e) => {
        if (live) setError(e.message);
      });
    return () => {
      live = false;
    };
  }, [activeId, user, refresh]);
  const analyticsHousehold =
    (tab === "Reports" && shared) || tab === "Household";
  const analyticsKey = `${user?.id}:${analyticsHousehold ? activeId : "personal"}:${month}:${refresh}`;
  const analytics =
    analyticsResult?.key === analyticsKey ? analyticsResult.data : null;
  useEffect(() => {
    if (!user || (user.verification_required && !user.email_verified)) return;
    let live = true;
    const path =
      analyticsHousehold && activeId
        ? `/households/${activeId}/analytics`
        : "/analytics/personal";
    api<Analytics>(`${path}?month=${month}`)
      .then((a) => {
        if (live) {
          setAnalytics({ key: analyticsKey, data: a });
        }
      })
      .catch((e) => {
        if (live) setError(e.message);
      });
    return () => {
      live = false;
    };
  }, [user, month, activeId, analyticsHousehold, refresh, analyticsKey]);
  async function logout() {
    try {
      await api("/auth/logout", { method: "POST" });
      setUser(null);
      setHouseholds([]);
      setMembers([]);
      setBalances([]);
      setAnalytics(null);
      setActiveId(null);
      setTab("Dashboard");
      setAdd(false);
      setEdit(null);
      setError("");
    } catch (e) {
      setError((e as Error).message);
    }
  }
  if (!ready)
    return (
      <main className="app-loading">
        <BookOpen size={32} />
        <h1>RoommateLedger</h1>
        <p>Opening your ledger…</p>
      </main>
    );
  if (accountLink) return <AccountLink {...accountLink} />;
  if (!user) return <Auth onLogin={setUser} />;
  if (user.verification_required && !user.email_verified)
    return (
      <main className="app-loading">
        <h1>Check your email</h1>
        <p>
          Verify your email address before opening your ledger. Use the link in
          your inbox, or request another below.
        </p>
        <AccountActions verified={false} />
        <button className="secondary" onClick={() => window.location.reload()}>
          I’ve verified my email
        </button>
        <button className="text-button" onClick={logout}>
          Sign out
        </button>
      </main>
    );
  const household = households.find((h) => h.id === activeId) || null,
    net = balances.find((b) => b.id === user.id)?.balance || 0;
  const expenseHousehold =
    tab === "My finances" || (tab === "Recurring bills" && !shared)
      ? null
      : activeId;
  const titles: Record<Tab, [string, string]> = {
    Dashboard: [
      `A little clarity, ${user.name.split(" ")[0]}.`,
      "Your personal finances and shared household costs, together.",
    ],
    "My finances": [
      "Your money. Your space.",
      "Private expenses, visible only to you.",
    ],
    Household: [
      household?.name || "Make room for your roommates.",
      "Shared expenses, thoughtfully divided.",
    ],
    Receipts: [
      "Every item has its people.",
      "Review, assign and confirm. You’re in control.",
    ],
    Balances: [
      "Know where you stand.",
      "Clear balances. Fewer awkward conversations.",
    ],
    "Recurring bills": [
      "Keep the regular stuff in order.",
      "Plan ahead without changing the past.",
    ],
    Reports: [
      "See the bigger picture.",
      "Real spending, useful comparisons, no guesswork.",
    ],
    Settings: ["A few personal details.", "Make this space work for you."],
  };
  function navigate(t: Tab) {
    window.scrollTo(0, 0);
    setTab(t);
    setMobile(false);
    setError("");
  }
  return (
    <div className="app-shell">
      <aside className={`sidebar ${mobile ? "mobile-open" : ""}`}>
        <div className="brand">
          <BookOpen size={25} />
          <span>
            Roommate<strong>Ledger</strong>
          </span>
          <button
            className="mobile-close icon-button"
            aria-label="Close navigation"
            onClick={() => setMobile(false)}
          >
            <X size={20} />
          </button>
        </div>
        <div className="household-switch">
          <span className="house-icon">
            <House size={19} />
          </span>
          <div>
            <small>YOUR HOUSEHOLD</small>
            {households.length ? (
              <select
                aria-label="Active household"
                value={activeId || ""}
                onChange={(e) => {
                  setActiveId(e.target.value);
                  setMembers([]);
                  setBalances([]);
                }}
              >
                {households.map((h) => (
                  <option key={h.id} value={h.id}>
                    {h.name}
                  </option>
                ))}
              </select>
            ) : (
              <button
                className="text-button"
                onClick={() => navigate("Household")}
              >
                Create or join <Plus size={12} />
              </button>
            )}
          </div>
        </div>
        <span className="nav-label">WORKSPACE</span>
        <nav>
          {navigation.map((n) => (
            <button
              key={n.name}
              className={tab === n.name ? "active" : ""}
              onClick={() => navigate(n.name)}
            >
              <n.icon size={19} strokeWidth={1.7} />
              {n.name}
              {n.name === "Receipts" && <span className="nav-new">SCAN</span>}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="privacy-card">
            <LockKeyhole size={18} />
            <strong>Shared home. Private finances.</strong>
            <p>Your personal expenses stay yours, even in a household.</p>
          </div>
          <button
            className="settings-button"
            onClick={() => navigate("Settings")}
          >
            <Settings size={18} /> Settings & profile
          </button>
          <div className="profile">
            <span className="avatar">{user.name.slice(0, 1)}</span>
            <div>
              <strong>{user.name}</strong>
              <small>Personal account</small>
            </div>
            <button
              className="icon-button"
              aria-label="Sign out"
              onClick={logout}
            >
              <LogOut size={17} />
            </button>
          </div>
        </div>
      </aside>
      {mobile && (
        <button
          className="nav-overlay"
          aria-label="Close navigation overlay"
          onClick={() => setMobile(false)}
        />
      )}
      <div className="main-shell">
        <header className="topbar">
          <div>
            <button
              className="mobile-menu icon-button"
              aria-label="Open navigation"
              onClick={() => setMobile(true)}
            >
              <Menu size={22} />
            </button>
            <span>Workspace</span>
            <span className="breadcrumb-separator">/</span>
            <strong>{tab}</strong>
          </div>
          <span className="topbar-private">
            <LockKeyhole size={13} /> A little more peace of mind
          </span>
        </header>
        <main className="workspace">
          <div className="page-heading">
            <div>
              <span className="eyebrow">
                {new Date(`${month}-15T12:00:00`)
                  .toLocaleDateString("en-US", {
                    month: "long",
                    year: "numeric",
                  })
                  .toUpperCase()}
              </span>
              <h1>{titles[tab][0]}</h1>
              <p>{titles[tab][1]}</p>
            </div>
            <div className="heading-actions">
              {["Dashboard", "My finances", "Household", "Reports"].includes(
                tab,
              ) && (
                <input
                  type="month"
                  aria-label="Report month"
                  value={month}
                  onChange={(e) => {
                    if (e.target.value) setMonth(e.target.value);
                  }}
                />
              )}
              <button className="primary" onClick={() => setAdd(true)}>
                <Plus size={17} /> Add expense
              </button>
            </div>
          </div>
          <ErrorMessage message={error} />
          {tab === "Dashboard" && (
            <>
              {analytics ? (
                <AnalyticsView data={analytics} />
              ) : (
                <p className="loading">Loading your dashboard…</p>
              )}
              <div className="dashboard-strip">
                <div>
                  <span className="category-icon">
                    <ArrowLeftRight size={20} />
                  </span>
                  <div>
                    <strong>
                      {activeId
                        ? net === 0
                          ? "You’re all settled up"
                          : net > 0
                            ? `You’re owed ${money(net)}`
                            : `You owe ${money(-net)}`
                        : "A shared home starts with an invitation"}
                    </strong>
                    <p>
                      {activeId
                        ? "Your net position across this household"
                        : "Create a household or join your roommates."}
                    </p>
                  </div>
                </div>
                <button
                  className="text-button"
                  onClick={() => navigate(activeId ? "Balances" : "Household")}
                >
                  {activeId ? "View balances" : "Set up household"}
                  <ArrowRight size={16} />
                </button>
              </div>
              <ExpenseHistory
                householdId={null}
                refresh={refresh}
                userId={user.id}
                onChanged={changed}
                onEdit={(id, input) => setEdit({ id, input })}
              />
            </>
          )}
          {tab === "My finances" && (
            <>
              {analytics && <AnalyticsView data={analytics} />}
              <ExpenseHistory
                householdId={null}
                refresh={refresh}
                userId={user.id}
                onChanged={changed}
                onEdit={(id, input) => setEdit({ id, input })}
              />
            </>
          )}
          {tab === "Household" && (
            <>
              {activeId && (
                <ExpenseHistory
                  key={activeId}
                  householdId={activeId}
                  refresh={refresh}
                  userId={user.id}
                  onChanged={changed}
                  onEdit={(id, input) => setEdit({ id, input })}
                />
              )}
              <HouseholdView
                user={user}
                household={household}
                members={members}
                onChanged={changed}
              />
            </>
          )}
          {tab === "Receipts" && (
            <ReceiptReview
              key={activeId || "private"}
              user={user}
              householdId={activeId}
              members={members}
              onConfirmed={changed}
            />
          )}
          {tab === "Balances" &&
            (activeId ? (
              <BalancesView
                user={user}
                householdId={activeId}
                refresh={refresh}
                onChanged={changed}
              />
            ) : (
              <Empty title="A household makes this useful">
                Create or join a household to see shared balances.
                <br />
                <button
                  className="text-button"
                  onClick={() => navigate("Household")}
                >
                  Set up household
                </button>
              </Empty>
            ))}
          {tab === "Recurring bills" && (
            <>
              <div className="view-tabs">
                <button
                  className={!shared ? "active" : ""}
                  onClick={() => setShared(false)}
                >
                  My private bills
                </button>
                <button
                  className={shared ? "active" : ""}
                  disabled={!activeId}
                  onClick={() => setShared(true)}
                >
                  Household bills
                </button>
              </div>
              <BillsView
                householdId={shared ? activeId : null}
                userId={user.id}
                refresh={refresh}
                onChanged={changed}
                onAdd={() => setAdd(true)}
              />
            </>
          )}
          {tab === "Reports" && (
            <>
              <div className="view-tabs">
                <button
                  className={!shared ? "active" : ""}
                  onClick={() => setShared(false)}
                >
                  My spending
                </button>
                <button
                  className={shared ? "active" : ""}
                  disabled={!activeId}
                  onClick={() => setShared(true)}
                >
                  Household spending
                </button>
              </div>
              {analytics && (
                <AnalyticsView
                  data={analytics}
                  household={shared && !!activeId}
                />
              )}
            </>
          )}
          {tab === "Settings" && (
            <>
              <ProfileView user={user} onSaved={setUser} />
              <AccountActions verified={!!user.email_verified} />
            </>
          )}
          <footer className="workspace-footer">
            <span>RoommateLedger</span>
            <span>Personal finances. Shared costs. Clear balances.</span>
          </footer>
        </main>
      </div>
      {(add || edit) && (
        <ExpenseForm
          user={user}
          householdId={edit ? edit.input.householdId : expenseHousehold}
          members={members}
          initial={edit?.input}
          expenseId={edit?.id}
          defaultRecurring={tab === "Recurring bills" && !edit}
          onClose={() => {
            setAdd(false);
            setEdit(null);
          }}
          onSaved={() => {
            setAdd(false);
            setEdit(null);
            changed();
          }}
        />
      )}
    </div>
  );
}
