"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/contexts/AuthContext";

// A "protected route" in the sense §35 means: the PAGE redirects an
// unauthenticated visitor away for a decent UX. It is not what makes
// this account's data safe — every fetch this page makes still goes
// through the backend's own require_authenticated_user()/ownership
// checks (app/api/deps_auth.py), which is what actually matters. If
// this redirect were deleted entirely, the worst that happens is a
// logged-out visitor sees a blank page instead of being sent to
// /login — they still could not fetch anyone's data.
export default function AccountPage() {
  const { user, loading, logout } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) {
      router.replace("/login");
    }
  }, [loading, user, router]);

  if (loading || !user) {
    return (
      <main className="min-h-screen flex items-center justify-center">
        <p className="text-mist text-sm">Loading…</p>
      </main>
    );
  }

  return (
    <main className="min-h-screen flex flex-col items-center justify-center px-6 py-24">
      <p className="text-brass text-xs tracking-widest2 uppercase mb-4">Charter123</p>
      <h1 className="font-display font-extrabold text-3xl text-paper mb-8">My account</h1>

      <div className="w-full max-w-sm bg-panel/60 border border-mist/20 rounded-lg p-6 space-y-3">
        <Row label="Name" value={[user.first_name, user.last_name].filter(Boolean).join(" ") || "—"} />
        <Row label="Email" value={user.email} />
        <Row label="Status" value={user.status} />
        <Row label="Roles" value={user.roles.join(", ") || "customer"} />

        <button
          onClick={async () => {
            await logout();
            router.replace("/login");
          }}
          className="w-full mt-4 border border-mist/30 hover:border-brass text-paper rounded py-2 transition-colors"
        >
          Sign out
        </button>
      </div>
    </main>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between text-sm">
      <span className="text-mist tracking-widest2 uppercase text-xs">{label}</span>
      <span className="text-paper">{value}</span>
    </div>
  );
}
