import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  timeout: 180_000,
  expect: { timeout: 20_000 },
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    actionTimeout: 20_000,
    baseURL: process.env.GEOPOL_E2E_URL ?? "http://127.0.0.1:5174",
    browserName: "chromium",
    viewport: { width: 1440, height: 1000 },
    locale: "es-PE",
    reducedMotion: "reduce",
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
    launchOptions: { args: ["--enable-unsafe-swiftshader"] },
  },
});
