"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, ApiRequestError } from "@/lib/api";
import type { AdminBookingListOut } from "@/lib/adminTypes";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { Pagination } from "@/components/admin/Pagination";
import { ErrorNotice } from "@/components/admin/ErrorNotice";

const LIMIT = 20;
const STATUS_OPTIONS = [
  "", "QUOTE", "PENDING", "CONFIRMED", "TICKETED", "CHECKED_IN", "COMPLETED",
  "CANCEL_REQUESTED", "CANCELLED", "MODIFICATION_PENDING", "MODIFIED", "FAILED", "EXPIRED",
];

export default function AdminBookingsPage() {
  const [status, setStatus] = useState("");
  const [offset, setOffset] = useState(0);
  const [result, setResult] = useState<AdminBookingListOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    const params = new URLSearchParams({ limit: String(LIMIT), offset: String(offset) });
    if (status) params.set("status", status);
    (async () => {
      try {
        const data = await api.get<AdminBookingListOut>(`/api/v1/admin/bookings?${params.toString()}`);
        if (!cancelled) setResult(data);
      } catch (err) {
        if (!cancelled) setError(err instanceof ApiRequestError ? err.message : "Failed to load bookings.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [status, offset]);

  return (
    <div>
      <div className="flex items-center gap-3 mb-4">
        <label className="text-mist text-xs uppercase tracking-widest2">Status</label>
        <select
          value={status}
          onChange={(e) => {
            setStatus(e.target.value);
            setOffset(0);
          }}
          className="bg-panel border border-mist/30 rounded px-3 py-1.5 text-sm text-paper"
        >
          {STATUS_OPTIONS.map((opt) => (
            <option key={opt || "all"} value={opt}>
              {opt || "All"}
            </option>
          ))}
        </select>
      </div>

      {error && <ErrorNotice message={error} />}

      {!error && (
        <div className="bg-panel/60 border border-mist/20 rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-mist text-xs uppercase tracking-wide text-left border-b border-mist/20">
                <th className="font-normal px-4 py-3">PNR</th>
                <th className="font-normal px-4 py-3">Route</th>
                <th className="font-normal px-4 py-3">Status</th>
                <th className="font-normal px-4 py-3">Payment</th>
                <th className="font-normal px-4 py-3">Customer</th>
                <th className="font-normal px-4 py-3 text-right">Total</th>
              </tr>
            </thead>
            <tbody>
              {loading && (
                <tr>
                  <td colSpan={6} className="px-4 py-6 text-mist text-center">
                    Loading…
                  </td>
                </tr>
              )}
              {!loading && result && result.items.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-4 py-6 text-mist text-center">
                    No bookings found.
                  </td>
                </tr>
              )}
              {!loading &&
                result?.items.map((b) => (
                  <tr key={b.id} className="border-t border-mist/10 hover:bg-midnight/40">
                    <td className="px-4 py-3">
                      <Link href={`/admin/bookings/${b.id}`} className="text-brass-soft hover:text-brass">
                        {b.pnr}
                      </Link>
                    </td>
                    <td className="px-4 py-3 text-paper">
                      {b.origin} → {b.destination}
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={b.status} />
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={b.payment_status} />
                    </td>
                    <td className="px-4 py-3 text-mist">{b.customer_email ?? "—"}</td>
                    <td className="px-4 py-3 text-paper text-right">
                      {b.total_price.toFixed(2)} {b.currency}
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      )}

      {result && <Pagination page={result.page} onPrev={() => setOffset(Math.max(0, offset - LIMIT))} onNext={() => setOffset(offset + LIMIT)} />}
    </div>
  );
}
