"use client";

import { useEffect, useState } from "react";

type ReadyResponse = {
  success: boolean;
  data?: {
    status: string;
    checks: Record<string, boolean>;
    mode: string;
  };
};

type RowState = { label: string; ok: boolean | null };

const CHECK_LABELS: Record<string, string> = {
  database: "DATABASE",
  redis: "REDIS",
  provider_configured: "AIRLINE PROVIDER",
};

export default function HomePage() {
  const [rows, setRows] = useState<RowState[]>([
    { label: "DATABASE", ok: null },
    { label: "REDIS", ok: null },
    { label: "AIRLINE PROVIDER", ok: null },
  ]);
  const [mode, setMode] = useState<string | null>(null);
  const [unreachable, setUnreachable] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/v1/health/ready")
      .then((r) => r.json())
      .then((body: ReadyResponse) => {
        if (cancelled || !body.data) return;
        setMode(body.data.mode);
        setRows(
          Object.entries(body.data.checks).map(([key, ok]) => ({
            label: CHECK_LABELS[key] ?? key.toUpperCase(),
            ok,
          }))
        );
      })
      .catch(() => {
        if (!cancelled) setUnreachable(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <main className="min-h-screen flex flex-col items-center justify-center px-6 py-24">
      <p className="text-brass text-xs tracking-widest2 uppercase mb-4">AI Voice Concierge &amp; Booking</p>
      <h1 className="font-display font-extrabold text-5xl sm:text-6xl tracking-tight text-paper mb-2">
        CHARTER123
      </h1>
      <p className="text-mist text-sm mb-14">Backend scaffold — Phase 1–3</p>

      <section className="panel-brackets bg-panel border border-white/5 rounded-sm w-full max-w-md px-7 py-6">
        <div className="flex items-baseline justify-between mb-5">
          <h2 className="text-paper text-xs tracking-widest2 uppercase">System Status</h2>
          {mode && (
            <span className="font-mono text-[11px] tracking-wide text-brass uppercase border border-brass/40 rounded-sm px-2 py-0.5">
              {mode} mode
            </span>
          )}
        </div>

        {unreachable ? (
          <p className="font-mono text-sm text-warn">
            API unreachable — start it with <span className="text-paper">docker compose up</span> or{" "}
            <span className="text-paper">uvicorn app.main:app</span>.
          </p>
        ) : (
          <ul className="space-y-3">
            {rows.map((row) => (
              <li key={row.label} className="flex items-center font-mono text-sm">
                <span className="text-mist">{row.label}</span>
                <span className="leader-line" aria-hidden />
                <span
                  className={`flex items-center gap-2 ${row.ok === false ? "text-warn" : "text-ok"}`}
                >
                  <span
                    className={`status-pulse inline-block w-1.5 h-1.5 rounded-full ${
                      row.ok === false ? "bg-warn" : "bg-ok"
                    }`}
                    aria-hidden
                  />
                  {row.ok === null ? "CHECKING" : row.ok ? "ONLINE" : "OFFLINE"}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <p className="text-mist text-xs mt-10 max-w-sm text-center leading-relaxed">
        The customer-facing search, booking, and admin pages (Phase 9) aren&apos;t built yet — this
        placeholder confirms the API, database, and cache are reachable.
      </p>
    </main>
  );
}
