import { defineConfig, devices } from "@playwright/test";

/**
 * T-7 (docs/TASK_BOARD.md, WBS-6.1). WRITTEN, NEVER EXECUTED — see
 * ../README.md. Deliberately does NOT define a `webServer` block: apps/web
 * alone isn't enough to make these tests meaningful — they also need the
 * FastAPI stack (apps/api), a real Postgres with staff-role data, and a
 * bootstrapped staff account (see apps/api/app/db/bootstrap_admin.py) all
 * already running, which is exactly the multi-service stack
 * .github/workflows/t1-verify.yml's separate `docker-compose-stack` job
 * brings up for WBS-1. Auto-starting just `next dev` here without that
 * would let this suite claim to be self-contained when it isn't — point
 * BASE_URL at wherever that real stack is already listening instead.
 */
export default defineConfig({
  testDir: "./tests",
  fullyParallel: false, // staff dashboard reads shared fixture data; avoid cross-test races over the same rows
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  reporter: [["html", { open: "never" }]],
  use: {
    baseURL: process.env.BASE_URL || "http://localhost:3000",
    trace: "on-first-retry",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
});
