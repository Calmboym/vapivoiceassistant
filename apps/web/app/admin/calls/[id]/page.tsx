"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { api, ApiRequestError } from "@/lib/api";
import type { CallDetailOut } from "@/lib/adminTypes";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { ErrorNotice } from "@/components/admin/ErrorNotice";

export default function AdminCallDetailPage() {
  const params = useParams<{ id: string }>();
  const [call, setCall] = useState<CallDetailOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await api.get<CallDetailOut>(`/api/v1/calls/${params.id}`);
        if (!cancelled) setCall(data);
      } catch (err) {
        if (!cancelled) setError(err instanceof ApiRequestError ? err.message : "Failed to load call.");
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
  if (!call) return null;

  return (
    <div className="space-y-8">
      <div>
        <Link href="/admin/calls" className="text-mist text-xs hover:text-paper">
          ← Back to calls
        </Link>
      </div>

      <section className="bg-panel/60 border border-mist/20 rounded-lg p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-display font-extrabold text-lg text-paper font-mono">{call.vapi_call_id}</h2>
          <StatusBadge status={call.status} />
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
          <Field label="Direction" value={call.direction ?? "—"} />
          <Field label="Phone" value={call.customer_phone_number ?? "—"} />
          <Field label="Started" value={call.started_at ? new Date(call.started_at).toLocaleString() : "—"} />
          <Field label="Ended" value={call.ended_at ? new Date(call.ended_at).toLocaleString() : "—"} />
          <Field label="Ended reason" value={call.ended_reason ?? "—"} />
          <Field label="Assistant" value={call.assistant_id ?? "—"} />
        </div>
      </section>

      <section className="bg-panel/60 border border-mist/20 rounded-lg p-6">
        <h3 className="text-paper text-sm tracking-widest2 uppercase mb-4">
          Tool calls ({call.tool_executions.length})
        </h3>
        {call.tool_executions.length === 0 ? (
          <p className="text-mist text-sm">No tool calls recorded on this call.</p>
        ) : (
          <div className="space-y-3">
            {call.tool_executions.map((t) => (
              <div key={t.id} className="border-t border-mist/10 pt-3 first:border-0 first:pt-0 text-sm">
                <div className="flex items-center justify-between">
                  <span className="text-paper font-mono">{t.tool_name}</span>
                  <div className="flex gap-2">
                    <StatusBadge status={t.authorization_result} />
                    {t.outcome && <StatusBadge status={t.outcome} />}
                  </div>
                </div>
                <p className="text-mist text-xs mt-1">
                  {new Date(t.created_at).toLocaleString()}
                  {t.latency_ms != null ? ` · ${t.latency_ms}ms` : ""}
                  {t.denial_reason ? ` · denied: ${t.denial_reason}` : ""}
                  {t.error_code ? ` · error: ${t.error_code}` : ""}
                </p>
                {Object.keys(t.arguments).length > 0 && (
                  <pre className="mt-2 bg-midnight/60 border border-mist/10 rounded p-2 text-xs text-mist overflow-x-auto">
                    {JSON.stringify(t.arguments, null, 2)}
                  </pre>
                )}
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
