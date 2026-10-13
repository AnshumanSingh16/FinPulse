import { beforeEach, describe, expect, it, vi } from "vitest";

import type * as LlmModule from "./llm";

vi.mock("server-only", () => ({}));

// A scripted stand-in for the model: first asks for a tool, then answers using its output.
const create = vi.fn();
const requests: { messages: { role: string; content: unknown }[] }[] = [];
const snapshot = (fn: typeof create) => (req: unknown) => {
  requests.push(JSON.parse(JSON.stringify(req)));
  return fn(req);
};
vi.mock("./llm", async (orig) => {
  const real = await orig<typeof LlmModule>();
  return {
    ...real,
    aiStatus: () => ({ enabled: true, model: "test-model", reason: "test" }),
    liveResearchEnabled: () => false,
    getClient: () => ({ messages: { create: snapshot(create) } }),
  };
});

import { DEMO_PROFILE } from "../schemas";
import { loadSession, resetSession } from "../store";
import { copilotTurn, type CopilotStreamItem } from "./copilot";

describe("copilot AI tool-use loop (mocked model)", () => {
  beforeEach(() => {
    create.mockReset();
    requests.length = 0;
    resetSession("cp");
  });

  it("runs the requested tool, returns its result to the model, and checks the reply's figures", async () => {
    const session = loadSession("cp");
    session.profile = { values: { ...DEMO_PROFILE }, sources: {}, isDemo: true, updatedAt: null };
    create
      .mockResolvedValueOnce({
        stop_reason: "tool_use",
        content: [
          {
            type: "tool_use",
            id: "tu_1",
            name: "calculate_emi",
            input: { principal: 6_000_000, annual_interest_rate: 8.5, tenure_months: 240 },
          },
        ],
      })
      .mockResolvedValueOnce({
        stop_reason: "end_turn",
        content: [
          { type: "text", text: "The EMI would be ₹52,069 a month; a lender might offer ₹49,000." },
        ],
      });

    const items: CopilotStreamItem[] = [];
    await copilotTurn(session, "EMI on 60 lakh at 8.5% for 20 years?", (i) => items.push(i));

    const tool = items.find((i) => i.type === "tool");
    expect(tool?.type === "tool" && tool.call.tool).toBe("calculate_emi");
    // the second model call received the tool result
    const last = requests[1]!.messages.at(-1)!;
    expect(JSON.stringify(last.content)).toContain("52069.39");
    const msg = items.find((i) => i.type === "message");
    expect(msg?.type === "message" && msg.mode).toBe("ai");
    // ₹52,069 matches a tool output; the invented ₹49,000 is flagged
    expect(msg?.type === "message" && msg.unverifiedFigures).toEqual(["₹49,000"]);
  });

  it("rejects invalid tool input without running the tool", async () => {
    const session = loadSession("cp");
    create
      .mockResolvedValueOnce({
        stop_reason: "tool_use",
        content: [
          { type: "tool_use", id: "tu_1", name: "calculate_emi", input: { principal: -5 } },
        ],
      })
      .mockResolvedValueOnce({
        stop_reason: "end_turn",
        content: [{ type: "text", text: "I need valid loan details." }],
      });
    const items: CopilotStreamItem[] = [];
    await copilotTurn(session, "emi?", (i) => items.push(i));
    const tool = items.find((i) => i.type === "tool");
    expect(tool?.type === "tool" && tool.call.status).toBe("error");
    const content = requests[1]!.messages.at(-1)!.content as { is_error?: boolean }[];
    expect(content[0]!.is_error).toBe(true);
  });

  it("falls back to the rule-based router when the provider fails", async () => {
    const session = loadSession("cp");
    create.mockRejectedValueOnce(new Error("network down"));
    const items: CopilotStreamItem[] = [];
    await copilotTurn(session, "hello", (i) => items.push(i));
    const msg = items.find((i) => i.type === "message");
    expect(msg?.type === "message" && msg.mode).toBe("rule_based");
    expect(msg?.type === "message" && msg.notice).toMatch(/rule-based fallback/);
  });
});

describe("copilot rule-based answers for the home prompts", () => {
  beforeEach(() => resetSession("rb"));
  const ask = async (q: string) => {
    const items: CopilotStreamItem[] = [];
    await copilotTurn(loadSession("rb"), q, (i) => items.push(i));
    return items;
  };

  it("plans an emergency fund from the profile", async () => {
    const s = loadSession("rb");
    s.profile = { values: { ...DEMO_PROFILE, liquidSavings: 300_000 }, sources: {}, isDemo: true, updatedAt: null };
    const items = await ask("Build an emergency fund");
    const tool = items.find((i) => i.type === "tool");
    expect(tool?.type === "tool" && tool.call.tool).toBe("plan_emergency_fund");
    const msg = items.find((i) => i.type === "message");
    // 6 × (70,000 + 15,000) = 5,10,000 target; gap 2,10,000; 17,500 a month over 12 months
    expect(msg?.type === "message" && msg.text).toContain("₹5,10,000");
    expect(msg?.type === "message" && msg.text).toContain("₹17,500");
  });

  it("stress-tests today's finances without a purchase", async () => {
    const s = loadSession("rb");
    s.profile = { values: { ...DEMO_PROFILE }, sources: {}, isDemo: true, updatedAt: null };
    const items = await ask("Stress-test my finances");
    const msg = items.find((i) => i.type === "message");
    // 25,00,000 / 85,000 = 29.4 months; income −20%: 1,60,000 − 85,000 = 75,000
    expect(msg?.type === "message" && msg.text).toContain("29.4 months");
    expect(msg?.type === "message" && msg.text).toContain("₹75,000");
  });

  it("asks for missing figures instead of guessing", async () => {
    const items = await ask("Build an emergency fund");
    const msg = items.find((i) => i.type === "message");
    expect(msg?.type === "message" && msg.text).toMatch(/missing/);
  });
});
