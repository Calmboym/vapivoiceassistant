import { test, expect } from "@playwright/test";
import { loginAsStaff } from "./fixtures";

/**
 * T-7 (WBS-6.1). Table headers and the search placeholder below are
 * copied verbatim from apps/web/app/admin/{customers,bookings,calls}/
 * page.tsx. Row-click-through-to-detail tests are conditional on at
 * least one row existing — this suite has no fixture/seed step of its
 * own (see ../README.md: it's written against whatever data the target
 * environment's database already has), so asserting a specific row
 * would make the suite depend on data it doesn't control.
 */

test.describe("customers section", () => {
  test.beforeEach(async ({ page }) => {
    await loginAsStaff(page, { landOn: "/admin/customers" });
  });

  test("search box and table columns render", async ({ page }) => {
    await expect(page.getByPlaceholder("Search by name, email, or phone…")).toBeVisible();
    const headerRow = page.locator("thead tr");
    for (const column of ["Name", "Email", "Phone", "Customer since"]) {
      await expect(headerRow.getByRole("columnheader", { name: column })).toBeVisible();
    }
  });

  test("clicking a customer name opens their detail page", async ({ page }) => {
    const firstRowLink = page.locator("tbody tr a").first();
    test.skip((await firstRowLink.count()) === 0, "no customers in this environment's database yet");
    await firstRowLink.click();
    await expect(page).toHaveURL(/\/admin\/customers\/[^/]+$/);
    await expect(page.getByRole("link", { name: "← Back to customers" })).toBeVisible();
  });
});

test.describe("bookings section", () => {
  test.beforeEach(async ({ page }) => {
    await loginAsStaff(page, { landOn: "/admin/bookings" });
  });

  test("table columns render", async ({ page }) => {
    const headerRow = page.locator("thead tr");
    for (const column of ["PNR", "Route", "Status", "Payment", "Customer", "Total"]) {
      await expect(headerRow.getByRole("columnheader", { name: column })).toBeVisible();
    }
  });

  test("clicking a PNR opens that booking's detail page", async ({ page }) => {
    const firstRowLink = page.locator("tbody tr a").first();
    test.skip((await firstRowLink.count()) === 0, "no bookings in this environment's database yet");
    const pnrText = (await firstRowLink.textContent())?.trim();
    await firstRowLink.click();
    await expect(page).toHaveURL(/\/admin\/bookings\/[^/]+$/);
    if (pnrText) {
      await expect(page.getByRole("heading", { name: pnrText })).toBeVisible();
    }
  });
});

test.describe("calls section", () => {
  test.beforeEach(async ({ page }) => {
    await loginAsStaff(page, { landOn: "/admin/calls" });
  });

  test("table columns render", async ({ page }) => {
    const headerRow = page.locator("thead tr");
    for (const column of ["Call", "Direction", "Status", "Phone", "Started", "Ended reason"]) {
      await expect(headerRow.getByRole("columnheader", { name: column })).toBeVisible();
    }
  });

  test("clicking a call opens that call's detail page", async ({ page }) => {
    const firstRowLink = page.locator("tbody tr a").first();
    test.skip((await firstRowLink.count()) === 0, "no calls in this environment's database yet");
    await firstRowLink.click();
    await expect(page).toHaveURL(/\/admin\/calls\/[^/]+$/);
  });
});
