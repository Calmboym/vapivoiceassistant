"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import Link from "next/link";
import { useAuth } from "@/contexts/AuthContext";
import { ApiRequestError } from "@/lib/api";

// Mirrors the floor enforced server-side in
// app/core/security/password_policy.py (MIN_LENGTH=12) — this is a UX
// nicety so the person sees the problem before submitting, not the
// actual control. The backend re-validates everything here regardless
// (§35: never trust client-side validation as the real check).
const schema = z.object({
  email: z.string().email("Enter a valid email address."),
  password: z.string().min(12, "Use at least 12 characters."),
  first_name: z.string().optional(),
  last_name: z.string().optional(),
});
type FormValues = z.infer<typeof schema>;

export default function RegisterPage() {
  const { register: registerUser } = useAuth();
  const router = useRouter();
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema) });

  const onSubmit = async (values: FormValues) => {
    setFormError(null);
    try {
      await registerUser(values);
      router.push("/account");
    } catch (err) {
      if (err instanceof ApiRequestError) {
        setFormError(err.message);
      } else {
        setFormError("Something went wrong. Please try again.");
      }
    }
  };

  return (
    <main className="min-h-screen flex flex-col items-center justify-center px-6 py-24">
      <p className="text-brass text-xs tracking-widest2 uppercase mb-4">Charter123</p>
      <h1 className="font-display font-extrabold text-3xl text-paper mb-8">Create an account</h1>

      <form onSubmit={handleSubmit(onSubmit)} className="w-full max-w-sm bg-panel/60 border border-mist/20 rounded-lg p-6 space-y-4">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs tracking-widest2 uppercase text-mist mb-1" htmlFor="first_name">
              First name
            </label>
            <input
              id="first_name"
              className="w-full bg-midnight border border-mist/30 rounded px-3 py-2 text-paper focus:outline-none focus:border-brass"
              {...register("first_name")}
            />
          </div>
          <div>
            <label className="block text-xs tracking-widest2 uppercase text-mist mb-1" htmlFor="last_name">
              Last name
            </label>
            <input
              id="last_name"
              className="w-full bg-midnight border border-mist/30 rounded px-3 py-2 text-paper focus:outline-none focus:border-brass"
              {...register("last_name")}
            />
          </div>
        </div>

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
            autoComplete="new-password"
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
          {isSubmitting ? "Creating account…" : "Create account"}
        </button>

        <p className="text-mist text-sm text-center">
          Already have an account?{" "}
          <Link href="/login" className="text-brass hover:text-brass-soft">
            Sign in
          </Link>
        </p>
      </form>
    </main>
  );
}
