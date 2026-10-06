import { describe, expect, it } from "vitest";

import { ConfigError, parseBaseUrl } from "./env";

describe("parseBaseUrl", () => {
  it("accepts http(s) URLs and strips trailing slashes", () => {
    expect(parseBaseUrl("X", "http://localhost:8000/")).toBe("http://localhost:8000");
    expect(parseBaseUrl("X", " https://api.example.com/base// ")).toBe(
      "https://api.example.com/base",
    );
  });

  it.each([undefined, "", "   "])("reports a missing value (%j)", (value) => {
    expect(() => parseBaseUrl("FINPULSE_API_URL", value)).toThrow(
      new ConfigError(
        "FINPULSE_API_URL is not set. Copy .env.example to .env in the repository root.",
      ),
    );
  });

  it("rejects malformed and non-http URLs", () => {
    expect(() => parseBaseUrl("X", "localhost:8000")).toThrow(ConfigError);
    expect(() => parseBaseUrl("X", "not a url")).toThrow(/not a valid URL/);
    expect(() => parseBaseUrl("X", "ftp://example.com")).toThrow(/http or https/);
  });
});
