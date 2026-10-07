import { describe, expect, it } from "vitest";

import { isAllowed, isSameOrigin } from "./proxy-policy";

const ID = "884d9a57-6d4e-536d-86ad-397f2762ac44";
const APP = "http://localhost:3000";

describe("isAllowed", () => {
  it.each([
    ["GET", "health"],
    ["POST", `api/v1/entities/${ID}/stress-test`],
    ["POST", `api/v1/entities/${ID}/investigations`],
    ["GET", `api/v1/investigations/${ID}/progress`],
    ["POST", "api/v1/demo/reset"],
  ])("lets %s %s through", (method, path) => {
    expect(isAllowed(method, path)).toBe(true);
  });

  it.each([
    ["GET", "api/v1/entities"],
    ["GET", `api/v1/investigations/${ID}/audit`],
    ["POST", `api/v1/entities/${ID}/investigate`],
    ["DELETE", `api/v1/investigations/${ID}/progress`],
    ["GET", `api/v1/investigations/${ID}/progress/../audit`],
    ["POST", "api/v1/entities/not-a-uuid/stress-test"],
    ["GET", "docs"],
  ])("refuses %s %s", (method, path) => {
    expect(isAllowed(method, path)).toBe(false);
  });
});

describe("isSameOrigin", () => {
  const h = (values: Record<string, string>) => new Headers(values);

  it("accepts the app's own pages", () => {
    expect(isSameOrigin("POST", h({ "sec-fetch-site": "same-origin", origin: APP }), APP)).toBe(
      true,
    );
    expect(isSameOrigin("GET", h({ "sec-fetch-site": "same-origin" }), APP)).toBe(true);
  });

  it("refuses other sites and headerless requests", () => {
    expect(isSameOrigin("POST", h({ "sec-fetch-site": "cross-site", origin: APP }), APP)).toBe(
      false,
    );
    expect(isSameOrigin("POST", h({ origin: "https://evil.example" }), APP)).toBe(false);
    expect(isSameOrigin("POST", h({ "sec-fetch-site": "same-origin" }), APP)).toBe(false);
    expect(isSameOrigin("GET", h({}), APP)).toBe(false);
  });
});
