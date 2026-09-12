"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { api, ApiRequestError } from "@/lib/api";
import type { AdminBookingDetailOut } from "@/lib/adminTypes";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { ErrorNotice } from "@/components/admin/ErrorNotice";

export default function AdminBookingDetailPage() {
  const params = useParams<{ id: string }>();
  const [detail, setDetail] = useState<AdminBookingDetailOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await api.get<AdminBookingDetailOut>(`/api/v1/admin/bookings/${params.id}`);
        if (!cancelled) setDetail(data);
      } catch (err) {
        if (!cancelled) setError(err instanceof ApiRequestError ? err.message : "Failed to load booking.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [params.id]);

  if (loading) return <p className="text-mist text-sm">Loading…</p>;
  if (error) return <ErrorNotice message={error} />;
  if (!detail) return null;

  const { booking, payments, audit_trail } = detail;

  return (
    <div className="space-y-8">
      <div>
        <Link href="/admin/bookings" className="text-mist text-xs hover:text-paper">
          ← Back to bookings
        </Link>
      </div>

      <section className="bg-panel/60 border border-mist/20 rounded-lg p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-display font-extrabold text-xl text-paper">{booking.pnr}</h2>
          <div className="flex gap-2">
            <StatusBadge status={booking.status} />
            <StatusBadge status={booking.payment_status} />
          </div>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
          <Field label="Route" value={`${booking.origin} → ${booking.destination}`} />
          <Field label="Flight" value={`${booking.flight_number} · ${booking.aircraft_type}`} />
          <Field label="Departure" value={new Date(booking.departure_time).toLocaleString()} />
          <Field label="Arrival" value={new Date(booking.arrival_time).toLocaleString()} />
          <Field label="Total price" value={`${booking.total_price.toFixed(2)} ${booking.currency}`} />
          <Field
            label="Customer"
            value={
              <Link href={`/admin/customers/${booking.customer_id}`} className="text-brass-soft hover:text-brass">
                {booking.customer_email ?? booking.customer_id}
              </Link>
            }
          />
          <Field
            label="Cancellation deadline"
            value={booking.cancellation_deadline ? new Date(booking.cancellation_deadline).toLocaleString() : "—"}
          />
        </div>
      </section>

      <section className="bg-panel/60 border border-mist/20 rounded-lg p-6">
        <h3 className="text-paper text-sm tracking-widest2 uppercase mb-4">
          Passengers ({booking.passengers.length})
        </h3>
        <div className="space-y-2">
          {booking.passengers.map((p) => (
            <div key={p.id} className="flex items-center justify-between text-sm border-t border-mist/10 pt-2 first:border-0 first:pt-0">
              <span className="text-paper">
                {p.first_name} {p.last_name} <span className="text-mist text-xs">({p.passenger_type})</span>
              </span>
              <span className="text-mist text-xs">
                {p.passport_on_file ? `Passport ${p.passport_number_masked ?? "on file"}` : "No passport on file"}
              </span>
            </div>
          ))}
        </div>
      </section>

      <section className="bg-panel/60 border border-mist/20 rounded-lg p-6">
        <h3 className="text-paper text-sm tracking-widest2 uppercase mb-4">
          Payment attempts ({payments.length})
        </h3>
        {payments.length === 0 ? (
          <p className="text-mist text-sm">No payment attempts recorded.</p>
        ) : (
          <div className="space-y-3">
            {payments.map((p) => (
              <div key={p.id} className="border-t border-mist/10 pt-3 first:border-0 first:pt-0 text-sm">
                <div className="flex items-center justify-between">
                  <StatusBadge status={p.status} />
                  <span className="text-paper">
                    {p.amount.toFixed(2)} {p.currency}
                  </span>
                </div>
                <p className="text-mist text-xs mt-1">
                  {p.provider_name} · {new Date(p.created_at).toLocaleString()}
                  {p.completed_at ? ` · completed ${new Date(p.completed_at).toLocaleString()}` : ""}
                </p>
                {p.refunded_amount != null && (
                  <p className="text-warn text-xs mt-1">
                    Refunded {p.refunded_amount.toFixed(2)} {p.currency} ({p.refund_status ?? "unknown"})
                    {p.refund_reason ? ` — ${p.refund_reason}` : ""}
                  </p>
                )}
                {p.failure_message && <p className="text-warn text-xs mt-1">{p.failure_message}</p>}
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="bg-panel/60 border border-mist/20 rounded-lg p-6">
        <h3 className="text-paper text-sm tracking-widest2 uppercase mb-4">
          Audit trail ({audit_trail.length})
        </h3>
        {audit_trail.length === 0 ? (
          <p className="text-mist text-sm">No audit events recorded for this booking.</p>
        ) : (
          <ol className="space-y-2 text-sm">
            {audit_trail.map((entry) => (
              <li key={entry.id} className="border-t border-mist/10 pt-2 first:border-0 first:pt-0 flex items-start justify-between gap-4">
                <div>
                  <span className="text-paper">{entry.action}</span>
                  <span className="text-mist text-xs ml-2">
                    by {entry.actor} ({entry.actor_type})
                  </span>
                </div>
                <span className="text-mist text-xs whitespace-nowrap">{new Date(entry.created_at).toLocaleString()}</span>
              </li>
            ))}
          </ol>
        )}
      </section>
    </div>
  );
}

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <p className="text-mist text-xs uppercase tracking-widest2 mb-1">{label}</p>
      <p className="text-paper">{value}</p>
    </div>
  );
}
