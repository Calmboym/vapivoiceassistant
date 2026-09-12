"use client";

import { useEffect, useState } from "react";
import { api, ApiRequestError } from "@/lib/api";
import type { AnalyticsSummaryOut } from "@/lib/adminTypes";
import { ErrorNotice } from "@/components/admin/ErrorNotice";

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-panel/60 border border-mist/20 rounded-lg p-4">
      <p className="text-mist text-xs tracking-widest2 uppercase mb-2">{label}</p>
      <p className="text-paper text-2xl font-display font-extrabold">{value}</p>
    </div>
  );
}

function formatPct(rate: number): string {
  return `${(rate * 100).toFixed(1)}%`;
}

function formatMoneyByCurrency(byCurrency: Record<string, number>): string {
  const entries = Object.entries(byCurrency);
  if (entries.length === 0) return "—";
  return entries.map(([currency, amount]) => `${amount.toFixed(2)} ${currency}`).join(" · ");
}

export default function AdminOverviewPage() {
  const [summary, setSummary] = useState<AnalyticsSummaryOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await api.get<AnalyticsSummaryOut>("/api/v1/admin/analytics");
        if (!cancelled) setSummary(data);
      } catch (err) {
        if (!cancelled) setError(err instanceof ApiRequestError ? err.message : "Failed to load analytics.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (loading) return <p className="text-mist text-sm">Loading…</p>;
  if (error) return <ErrorNotice message={error} />;
  if (!summary) return null;

  const statusEntries: [string, number][] = Object.entries(summary.bookings_by_status).sort((a, b) => b[1] - a[1]);
  const revenueRows = [...summary.revenue_by_day].sort((a, b) => (a.day < b.day ? 1 : -1)).slice(0, 14);

  return (
    <div className="space-y-8">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Total bookings" value={String(summary.total_bookings)} />
        <StatCard label="Paid bookings" value={String(summary.paid_bookings)} />
        <StatCard label="Payment conversion" value={formatPct(summary.payment_conversion_rate)} />
        <StatCard label="Cancellation rate" value={formatPct(summary.cancellation_rate)} />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <StatCard label="Gross revenue (captured)" value={formatMoneyByCurrency(summary.gross_revenue_by_currency)} />
        <StatCard label="Net revenue (after refunds)" value={formatMoneyByCurrency(summary.net_revenue_by_currency)} />
      </div>

      <section className="bg-panel/60 border border-mist/20 rounded-lg p-6">
        <h2 className="text-paper text-sm tracking-widest2 uppercase mb-4">Bookings by status</h2>
        {statusEntries.length === 0 ? (
          <p className="text-mist text-sm">No bookings yet.</p>
        ) : (
          <div className="space-y-2">
            {statusEntries.map(([status, count]) => (
              <div key={status} className="flex items-center justify-between text-sm">
                <span className="text-mist uppercase tracking-wide text-xs">{status.replace(/_/g, " ")}</span>
                <span className="text-paper">{count}</span>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="bg-panel/60 border border-mist/20 rounded-lg p-6">
        <h2 className="text-paper text-sm tracking-widest2 uppercase mb-4">Recent daily revenue (net)</h2>
        {revenueRows.length === 0 ? (
          <p className="text-mist text-sm">No captured payments yet.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-mist text-xs uppercase tracking-wide text-left">
                <th className="font-normal pb-2">Day</th>
                <th className="font-normal pb-2">Currency</th>
                <th className="font-normal pb-2 text-right">Net amount</th>
              </tr>
            </thead>
            <tbody>
              {revenueRows.map((row) => (
                <tr key={`${row.day}-${row.currency}`} className="border-t border-mist/10">
                  <td className="py-2 text-paper">{row.day}</td>
                  <td className="py-2 text-mist">{row.currency}</td>
                  <td className="py-2 text-paper text-right">{row.net_amount.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
