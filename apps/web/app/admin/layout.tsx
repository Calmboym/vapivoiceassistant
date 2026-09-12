"use client";

import { useEffect } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/contexts/AuthContext";

// UX-only gate (§35 — same disclaimer as app/account/page.tsx and
// middleware.ts). "Staff" here mirrors the backend's own is_staff
// definition exactly (app/core/security/actor.py: any role other than
// bare CUSTOMER) — but this is still just a friendlier redirect for a
// customer who wandered onto /admin by typing the URL; it grants
// nothing. Each admin page's own API calls are re-checked server-side
// against the SPECIFIC permission that page needs (admin.read,
// calls.read, customers.read, ...) — a SUPPORT_AGENT staff member who
// passes this coarse gate can still get a real 403 from, say,
// /api/v1/admin/analytics, which needs admin.read specifically. Pages
// handle that themselves (see ErrorNotice usage throughout).
const NAV_ITEMS = [
  { href: "/admin", label: "Overview" },
  { href: "/admin/bookings", label: "Bookings" },
  { href: "/admin/customers", label: "Customers" },
  { href: "/admin/calls", label: "Calls" },
];

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (!loading && !user) {
      router.replace("/login?next=/admin");
    }
  }, [loading, user, router]);

  if (loading || !user) {
    return (
      <main className="min-h-screen flex items-center justify-center">
        <p className="text-mist text-sm">Loading…</p>
      </main>
    );
  }

  const isStaff = user.roles.some((r) => r !== "CUSTOMER");
  if (!isStaff) {
    return (
      <main className="min-h-screen flex flex-col items-center justify-center px-6 text-center">
        <p className="text-brass text-xs tracking-widest2 uppercase mb-4">Charter123</p>
        <h1 className="font-display font-extrabold text-2xl text-paper mb-3">Staff access only</h1>
        <p className="text-mist text-sm max-w-sm">
          This dashboard is for Charter123 staff. If you believe you should have access, contact an administrator.
        </p>
      </main>
    );
  }

  return (
    <main className="min-h-screen px-6 py-10 max-w-6xl mx-auto">
      <p className="text-brass text-xs tracking-widest2 uppercase mb-2">Charter123 — Staff</p>
      <h1 className="font-display font-extrabold text-3xl text-paper mb-6">Admin dashboard</h1>

      <nav className="flex gap-1 border-b border-mist/20 mb-8">
        {NAV_ITEMS.map((item) => {
          const active = item.href === "/admin" ? pathname === "/admin" : pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`px-4 py-2 text-sm border-b-2 -mb-px transition-colors ${
                active ? "border-brass text-paper" : "border-transparent text-mist hover:text-paper"
              }`}
            >
              {item.label}
            </Link>
          );
        })}
      </nav>

      {children}
    </main>
  );
}
