"use client";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from "recharts";
import { ArrowDownRight, ArrowUpRight, LockKeyhole } from "lucide-react";
import type { Analytics } from "@/lib/types";
import { money } from "@/lib/money";
import { Empty } from "./ui";
export default function AnalyticsView({
  data,
  household = false,
}: {
  data: Analytics;
  household?: boolean;
}) {
  return (
    <>
      <div className="stats-grid">
        <article className="stat featured">
          <span>
            {household ? "Household spending" : "Your total spending"}
          </span>
          <strong>{money(data.total)}</strong>
          <div className="comparison">
            {data.difference <= 0 ? (
              <ArrowDownRight size={17} />
            ) : (
              <ArrowUpRight size={17} />
            )}{" "}
            {data.percentChange === null
              ? "No previous-month baseline"
              : `${Math.abs(data.percentChange)}% ${data.difference <= 0 ? "less" : "more"} than last month`}
          </div>
        </article>
        <article className="stat">
          <span>{household ? "Previous month" : "Just your expenses"}</span>
          <strong>
            {money(household ? data.previousTotal : data.personal)}
          </strong>
          <small>
            {household ? (
              "Shared spending last month"
            ) : (
              <>
                <LockKeyhole size={13} /> Private to you
              </>
            )}
          </small>
        </article>
        <article className="stat">
          <span>
            {household ? "Month-over-month change" : "Your household share"}
          </span>
          <strong>{money(household ? data.difference : data.shared)}</strong>
          <small>
            {household
              ? "Current month minus previous month"
              : "Your responsibility, not the full bill"}
          </small>
        </article>
      </div>
      <div className="analytics-grid">
        <section className="panel">
          <div className="panel-heading">
            <div>
              <h2>Spending over time</h2>
              <p>Your last six months, at a glance</p>
            </div>
            <span className="legend">
              <i /> {household ? "Shared spending" : "Total spending"}
            </span>
          </div>
          {data.trend.some((t) => t.total) ? (
            <>
              <div
                className="chart"
                role="img"
                aria-label="Monthly spending trend; exact figures in the table below"
              >
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart
                    data={data.trend}
                    margin={{ top: 12, right: 18, bottom: 0, left: 0 }}
                  >
                    <CartesianGrid
                      strokeDasharray="3 5"
                      vertical={false}
                      stroke="#e8ede9"
                    />
                    <XAxis
                      dataKey="month"
                      tickFormatter={(v) =>
                        new Date(`${v}-15T12:00:00`).toLocaleDateString(
                          "en-US",
                          { month: "short" },
                        )
                      }
                      axisLine={false}
                      tickLine={false}
                      tick={{ fill: "#77847e", fontSize: 12 }}
                    />
                    <YAxis
                      tickFormatter={(v) => `$${v / 100}`}
                      axisLine={false}
                      tickLine={false}
                      width={65}
                      tick={{ fill: "#77847e", fontSize: 12 }}
                    />
                    <Tooltip formatter={(value) => money(Number(value))} />
                    <Line
                      type="monotone"
                      dataKey="total"
                      stroke="#347761"
                      strokeWidth={3}
                      dot={{
                        r: 4,
                        fill: "#347761",
                        stroke: "white",
                        strokeWidth: 2,
                      }}
                      isAnimationActive={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
              <details className="chart-data">
                <summary>View monthly figures</summary>
                <table>
                  <tbody>
                    {data.trend.map((t) => (
                      <tr key={t.month}>
                        <th>{t.month}</th>
                        <td>{money(t.total)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </details>
            </>
          ) : (
            <Empty title="Your story starts here">
              Add an expense to see your spending trend.
            </Empty>
          )}
        </section>
        <section className="panel">
          <div className="panel-heading">
            <div>
              <h2>Where it went</h2>
              <p>Spending by category</p>
            </div>
          </div>
          {data.categories.length ? (
            <div className="category-list">
              {data.categories.map((c, i) => {
                const previous =
                  data.previousCategories.find((p) => p.category === c.category)
                    ?.total || 0;
                return (
                  <div key={c.category}>
                    <div>
                      <span>
                        <i
                          style={{
                            background: [
                              "#397b65",
                              "#8ea997",
                              "#b69b6a",
                              "#7d92ad",
                              "#ad8290",
                            ][i % 5],
                          }}
                        />
                        {c.category}
                      </span>
                      <strong>{money(c.total)}</strong>
                    </div>
                    <div className="bar-track">
                      <div
                        style={{
                          width: `${data.total ? (c.total / data.total) * 100 : 0}%`,
                          background: [
                            "#397b65",
                            "#8ea997",
                            "#b69b6a",
                            "#7d92ad",
                            "#ad8290",
                          ][i % 5],
                        }}
                      />
                    </div>
                    <small>
                      {money(previous)} last month · {money(c.total - previous)}{" "}
                      change
                    </small>
                  </div>
                );
              })}
            </div>
          ) : (
            <Empty title="Nothing to break down yet">
              Categories will appear as you add expenses.
            </Empty>
          )}
        </section>
      </div>
    </>
  );
}
