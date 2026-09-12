"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, ApiRequestError } from "@/lib/api";
import type { CustomerListOut } from "@/lib/adminTypes";
import { Pagination } from "@/components/admin/Pagination";
import { ErrorNotice } from "@/components/admin/ErrorNotice";

const LIMIT = 20;

export default function AdminCustomersPage() {
  const [searchInput, setSearchInput] = useState("");
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const [result, setResult] = useState<CustomerListOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    const params = new URLSearchParams({ limit: String(LIMIT), offset: String(offset) });
    if (search) params.set("search", search);
    (async () => {
      try {
        const data = await api.get<CustomerListOut>(`/api/v1/customers?${params.toString()}`);
        if (!cancelled) setResult(data);
      } catch (err) {
        if (!cancelled) setError(err instanceof ApiRequestError ? err.message : "Failed to load customers.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [search, offset]);

  return (
    <div>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          setSearch(searchInput.trim());
          setOffset(0);
        }}
        className="flex items-center gap-3 mb-4"
      >
        <input
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          placeholder="Search by name, email, or phone…"
          className="bg-panel border border-mist/30 rounded px-3 py-1.5 text-sm text-paper flex-1 max-w-sm placeholder:text-mist/60"
        />
        <button
          type="submit"
          className="border border-mist/30 hover:border-brass text-paper rounded px-4 py-1.5 text-sm transition-colors"
        >
          Search
        </button>
      </form>

      {error && <ErrorNotice message={error} />}

      {!error && (
        <div className="bg-panel/60 border border-mist/20 rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-mist text-xs uppercase tracking-wide text-left border-b border-mist/20">
                <th className="font-normal px-4 py-3">Name</th>
                <th className="font-normal px-4 py-3">Email</th>
                <th className="font-normal px-4 py-3">Phone</th>
                <th className="font-normal px-4 py-3">Customer since</th>
              </tr>
            </thead>
            <tbody>
              {loading && (
                <tr>
                  <td colSpan={4} className="px-4 py-6 text-mist text-center">
                    Loading…
                  </td>
                </tr>
              )}
              {!loading && result && result.items.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-4 py-6 text-mist text-center">
                    No customers found.
                  </td>
                </tr>
              )}
              {!loading &&
                result?.items.map((c) => (
                  <tr key={c.id} className="border-t border-mist/10 hover:bg-midnight/40">
                    <td className="px-4 py-3">
                      <Link href={`/admin/customers/${c.id}`} className="text-brass-soft hover:text-brass">
                        {[c.first_name, c.last_name].filter(Boolean).join(" ") || "—"}
                      </Link>
                    </td>
                    <td className="px-4 py-3 text-paper">{c.email ?? "—"}</td>
                    <td className="px-4 py-3 text-mist">{c.phone ?? "—"}</td>
                    <td className="px-4 py-3 text-mist">{new Date(c.created_at).toLocaleDateString()}</td>
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
