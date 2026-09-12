"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { api, ApiRequestError } from "@/lib/api";
import type { CustomerDetailOut, CustomerUpdateRequest } from "@/lib/adminTypes";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { ErrorNotice } from "@/components/admin/ErrorNotice";

export default function AdminCustomerDetailPage() {
  const params = useParams<{ id: string }>();
  const [customer, setCustomer] = useState<CustomerDetailOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState<CustomerUpdateRequest>({});
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const load = async () => {
    try {
      const data = await api.get<CustomerDetailOut>(`/api/v1/customers/${params.id}`);
      setCustomer(data);
      setForm({
        email: data.email ?? "",
        phone: data.phone ?? "",
        first_name: data.first_name ?? "",
        last_name: data.last_name ?? "",
      });
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : "Failed to load customer.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params.id]);

  const handleSave = async () => {
    setSaving(true);
    setSaveError(null);
    try {
      // Only send fields that actually changed — CustomerUpdateRequest
      // is PATCH semantics (app/schemas/customer.py), and an empty
      // string isn't the same as "leave this field alone."
      const payload: CustomerUpdateRequest = {};
      if (form.email) payload.email = form.email;
      if (form.phone) payload.phone = form.phone;
      if (form.first_name) payload.first_name = form.first_name;
      if (form.last_name) payload.last_name = form.last_name;
      const updated = await api.patch<CustomerDetailOut>(`/api/v1/customers/${params.id}`, payload);
      setCustomer(updated);
      setEditing(false);
    } catch (err) {
      setSaveError(err instanceof ApiRequestError ? err.message : "Failed to save changes.");
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <p className="text-mist text-sm">Loading…</p>;
  if (error) return <ErrorNotice message={error} />;
  if (!customer) return null;

  return (
    <div className="space-y-8">
      <div>
        <Link href="/admin/customers" className="text-mist text-xs hover:text-paper">
          ← Back to customers
        </Link>
      </div>

      <section className="bg-panel/60 border border-mist/20 rounded-lg p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-display font-extrabold text-xl text-paper">
            {[customer.first_name, customer.last_name].filter(Boolean).join(" ") || "Unnamed customer"}
          </h2>
          {!editing && (
            <button
              onClick={() => setEditing(true)}
              className="border border-mist/30 hover:border-brass text-paper rounded px-3 py-1.5 text-sm transition-colors"
            >
              Edit contact info
            </button>
          )}
        </div>

        {!editing ? (
          <div className="grid grid-cols-2 gap-4 text-sm">
            <Field label="Email" value={customer.email ?? "—"} />
            <Field label="Phone" value={customer.phone ?? "—"} />
            <Field label="Preferred language" value={customer.preferred_language} />
            <Field label="Customer since" value={new Date(customer.created_at).toLocaleDateString()} />
          </div>
        ) : (
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-4">
              <LabeledInput label="First name" value={form.first_name ?? ""} onChange={(v) => setForm({ ...form, first_name: v })} />
              <LabeledInput label="Last name" value={form.last_name ?? ""} onChange={(v) => setForm({ ...form, last_name: v })} />
              <LabeledInput label="Email" value={form.email ?? ""} onChange={(v) => setForm({ ...form, email: v })} type="email" />
              <LabeledInput label="Phone" value={form.phone ?? ""} onChange={(v) => setForm({ ...form, phone: v })} />
            </div>
            {saveError && <ErrorNotice message={saveError} />}
            <div className="flex gap-2">
              <button
                onClick={handleSave}
                disabled={saving}
                className="bg-brass hover:bg-brass-soft text-midnight font-semibold rounded px-4 py-1.5 text-sm transition-colors disabled:opacity-50"
              >
                {saving ? "Saving…" : "Save"}
              </button>
              <button
                onClick={() => setEditing(false)}
                disabled={saving}
                className="border border-mist/30 text-paper rounded px-4 py-1.5 text-sm hover:border-mist"
              >
                Cancel
              </button>
            </div>
          </div>
        )}
      </section>

      <section className="bg-panel/60 border border-mist/20 rounded-lg p-6">
        <h3 className="text-paper text-sm tracking-widest2 uppercase mb-4">
          Bookings ({customer.bookings.length})
        </h3>
        {customer.bookings.length === 0 ? (
          <p className="text-mist text-sm">This customer has no bookings.</p>
        ) : (
          <div className="space-y-2">
            {customer.bookings.map((b) => (
              <div key={b.id} className="flex items-center justify-between text-sm border-t border-mist/10 pt-2 first:border-0 first:pt-0">
                <Link href={`/admin/bookings/${b.id}`} className="text-brass-soft hover:text-brass">
                  {b.pnr}
                </Link>
                <span className="text-mist text-xs">
                  {b.origin} → {b.destination}
                </span>
                <StatusBadge status={b.status} />
                <span className="text-paper">
                  {b.total_price.toFixed(2)} {b.currency}
                </span>
              </div>
            ))}
          </div>
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

function LabeledInput({
  label,
  value,
  onChange,
  type = "text",
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
}) {
  return (
    <label className="block">
      <span className="text-mist text-xs uppercase tracking-widest2 mb-1 block">{label}</span>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full bg-midnight border border-mist/30 rounded px-3 py-1.5 text-sm text-paper"
      />
    </label>
  );
}
