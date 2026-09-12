"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import Link from "next/link";
import { useAuth } from "@/contexts/AuthContext";
import { ApiRequestError } from "@/lib/api";

const schema = z.object({
  email: z.string().email("Enter a valid email address."),
  password: z.string().min(1, "Enter your password."),
});
type FormValues = z.infer<typeof schema>;

function LoginForm() {
  const { login } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema) });

  const onSubmit = async (values: FormValues) => {
    setFormError(null);
    try {
      await login(values.email, values.password);
      // T-7 (WBS-6.1) fix: this used to always push to "/account" and
      // ignore `next` entirely, even though app/admin/layout.tsx sends an
      // unauthenticated staff member here via `/login?next=/admin` — so a
      // staff member who got bounced off /admin to log in landed back on
      // /account instead, needing an extra manual click. Found while
      // writing this task's admin Playwright suite, which needs a real
      // login -> land-on-/admin path to test against. `next` is only
      // honored when it's an internal path (starts with "/", not the
      // protocol-relative-URL open-redirect shape "//...") — anything
      // else falls back to the original "/account" default.
      const next = searchParams.get("next");
      const isSafeInternalPath = !!next && next.startsWith("/") && !next.startsWith("//");
      router.push(isSafeInternalPath ? next! : "/account");
    } catch (err) {
      // Deliberately the SAME message no matter what the backend's code
      // was (INVALID_CREDENTIALS covers "no such account" and "wrong
      // password" alike — §18/§28) — the UI doesn't add a distinction
      // the backend chose not to make.
      if (err instanceof ApiRequestError && err.code === "RATE_LIMITED") {
        setFormError("Too many attempts. Please wait a moment and try again.");
      } else {
        setFormError("That email or password isn't right.");
      }
    }
  };

  return (
    <main className="min-h-screen flex flex-col items-center justify-center px-6 py-24">
      <p className="text-brass text-xs tracking-widest2 uppercase mb-4">Charter123</p>
      <h1 className="font-display font-extrabold text-3xl text-paper mb-8">Sign in</h1>

      <form onSubmit={handleSubmit(onSubmit)} className="w-full max-w-sm bg-panel/60 border border-mist/20 rounded-lg p-6 space-y-4">
        <div>
          <label className="block text-xs tracking-widest2 uppercase text-mist mb-1" htmlFor="email">
            Email
          </label>
          <input
            id="email"
            type="email"
            autoComplete="email"
            className="w-full bg-midnight border border-mist/30 rounded px-3 py-2 text-paper focus:outline-none focus:border-brass"
            {...register("email")}
          />
          {errors.email && <p className="text-red-400 text-xs mt-1">{errors.email.message}</p>}
        </div>

        <div>
          <label className="block text-xs tracking-widest2 uppercase text-mist mb-1" htmlFor="password">
            Password
          </label>
          <input
            id="password"
            type="password"
            autoComplete="current-password"
            className="w-full bg-midnight border border-mist/30 rounded px-3 py-2 text-paper focus:outline-none focus:border-brass"
            {...register("password")}
          />
          {errors.password && <p className="text-red-400 text-xs mt-1">{errors.password.message}</p>}
        </div>

        {formError && <p className="text-red-400 text-sm">{formError}</p>}

        <button
          type="submit"
          disabled={isSubmitting}
          className="w-full bg-brass hover:bg-brass-soft transition-colors text-midnight font-semibold rounded py-2 disabled:opacity-50"
        >
          {isSubmitting ? "Signing in…" : "Sign in"}
        </button>

        <p className="text-mist text-sm text-center">
          No account?{" "}
          <Link href="/register" className="text-brass hover:text-brass-soft">
            Register
          </Link>
        </p>
      </form>
    </main>
  );
}

export default function LoginPage() {
  // useSearchParams() requires a Suspense boundary in the App Router
  // (Next.js bails a page relying on it out of static rendering
  // otherwise) — no other page in this codebase used useSearchParams()
  // before this fix, so there was no existing precedent to match; this
  // is Next.js's own documented pattern for it.
  return (
    <Suspense
      fallback={
        <main className="min-h-screen flex items-center justify-center">
          <p className="text-mist text-sm">Loading…</p>
        </main>
      }
    >
      <LoginForm />
    </Suspense>
  );
}
