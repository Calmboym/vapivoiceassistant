import { test, expect } from "@playwright/test";
import { loginAsStaff } from "./fixtures";

/**
 * T-7 (WBS-6.1). Covers apps/web/app/admin/layout.tsx's client-side gate —
 * explicitly a UX-only convenience per that file's own docstring, not a
 * security boundary (every admin page's API calls are separately
 * re-checked server-side against real RBAC permissions; see
 * MASTER_RULES.md §2 on never trusting the client for authorization).
 * These tests exist to catch a broken redirect/UX regression, not to
 * prove a permission boundary — that's apps/api/tests/test_admin_core.py
 * and tests/test_security_core.py's job, already covered there.
 */
test.describe("admin auth gate", () => {
  test("visiting /admin while signed out redirects to /login with a next param", async ({ page }) => {
    await page.goto("/admin");
    await expect(page).toHaveURL(/\/login\?next=%2Fadmin/);
  });

  test("logging in from that redirect lands back on /admin, not /account", async ({ page }) => {
    // Regression test for a real bug this task found and fixed (see
    // apps/web/app/login/page.tsx's T-7 comment): the login page used to
    // ignore the `next` param entirely and always land on /account,
    // stranding a staff member who'd been bounced off /admin to sign in.
    await loginAsStaff(page, { landOn: "/admin" });
    await expect(page.getByRole("heading", { name: "Admin dashboard" })).toBeVisible();
  });

  test("logging in with no next param still lands on /account as before", async ({ page }) => {
    // Confirms the T-7 fix didn't change the default (unrelated) login path.
    await loginAsStaff(page);
  });
});
