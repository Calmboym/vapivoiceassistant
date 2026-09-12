import { test, expect } from "@playwright/test";
import { loginAsStaff } from "./fixtures";

/** T-7 (WBS-6.1). Selectors below match apps/web/app/admin/{layout,page}.tsx
 * verbatim (nav labels, dashboard section headings) — nothing guessed. */
test.describe("admin navigation", () => {
  test.beforeEach(async ({ page }) => {
    await loginAsStaff(page, { landOn: "/admin" });
  });

  test("dashboard shows the bookings-by-status and revenue sections", async ({ page }) => {
    await expect(page.getByRole("heading", { name: "Bookings by status" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Recent daily revenue (net)" })).toBeVisible();
  });

  test("nav links move between the four admin sections and mark the active one", async ({ page }) => {
    const nav = page.getByRole("navigation");

    await nav.getByRole("link", { name: "Bookings" }).click();
    await expect(page).toHaveURL(/\/admin\/bookings$/);
    await expect(nav.getByRole("link", { name: "Bookings" })).toHaveClass(/border-brass/);

    await nav.getByRole("link", { name: "Customers" }).click();
    await expect(page).toHaveURL(/\/admin\/customers$/);
    await expect(nav.getByRole("link", { name: "Customers" })).toHaveClass(/border-brass/);

    await nav.getByRole("link", { name: "Calls" }).click();
    await expect(page).toHaveURL(/\/admin\/calls$/);
    await expect(nav.getByRole("link", { name: "Calls" })).toHaveClass(/border-brass/);

    await nav.getByRole("link", { name: "Overview" }).click();
    await expect(page).toHaveURL(/\/admin$/);
  });
});
