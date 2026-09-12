import { Page, expect } from "@playwright/test";

/**
 * Credentials for a real, already-seeded staff account (any role other
 * than bare CUSTOMER — see apps/web/app/admin/layout.tsx's isStaff check
 * and apps/api/app/core/security/actor.py's matching is_staff definition).
 * Deliberately read from the environment rather than hardcoded: this
 * project's own MASTER_RULES.md discipline is "never fabricate
 * credentials", and a real run needs a real bootstrapped account (see
 * apps/api/app/db/bootstrap_admin.py or apps/api/app/db/seed.py) — there
 * is no default that would work against a fresh, un-seeded database.
 */
export const STAFF_EMAIL = process.env.E2E_STAFF_EMAIL ?? "";
export const STAFF_PASSWORD = process.env.E2E_STAFF_PASSWORD ?? "";

export function requireStaffCredentials() {
  if (!STAFF_EMAIL || !STAFF_PASSWORD) {
    throw new Error(
      "E2E_STAFF_EMAIL and E2E_STAFF_PASSWORD must be set to a real, " +
        "already-seeded staff account before running this suite — see " +
        "../README.md."
    );
  }
}

/** Logs in via the real /login form (never a shortcut/mocked auth state)
 * and waits for the app to land somewhere past the login page. */
export async function loginAsStaff(page: Page, { landOn }: { landOn?: string } = {}) {
  requireStaffCredentials();
  await page.goto(landOn ? `/login?next=${encodeURIComponent(landOn)}` : "/login");
  await page.getByLabel("Email").fill(STAFF_EMAIL);
  await page.getByLabel("Password").fill(STAFF_PASSWORD);
  await page.getByRole("button", { name: /sign in/i }).click();
  await expect(page).toHaveURL(landOn ?? "/account", { timeout: 10_000 });
}
