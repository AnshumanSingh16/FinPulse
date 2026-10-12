/**
 * Financial Research Agent: financing options for a purchase.
 *
 * Providers implement one interface, so a different search API can be plugged in later:
 *  - IllustrativeResearchProvider: always available; returns clearly labelled illustrative
 *    ranges. Never presented as current lender offers.
 *  - ClaudeWebSearchProvider: live web search through the Anthropic API's server-side web search
 *    tool. A rate is kept only if the URL it cites was actually returned by the search; anything
 *    unsupported is dropped.
 */
import "server-only";

import type Anthropic from "@anthropic-ai/sdk";
import { z } from "zod";

import type { PurchaseType } from "../schemas";
import { describeAiError, effort, getClient, liveResearchEnabled, modelId, UNTRUSTED_DATA_RULE } from "./llm";
import type { FinancingOption, ResearchResult, Source } from "./types";

export type ResearchQuery = { purchaseType: PurchaseType; loanAmount: number; tenureMonths: number | null };

export interface ResearchProvider {
  readonly id: string;
  readonly live: boolean;
  research(query: ResearchQuery, signal?: AbortSignal): Promise<ResearchResult>;
}

/** Illustrative ranges by purchase type. Demonstration assumptions, not market data. */
const ILLUSTRATIVE: Record<PurchaseType, { name: string; min: number; max: number; tenures: number[]; fees: string }> = {
  house: { name: "Home loan (illustrative)", min: 8.0, max: 9.0, tenures: [180, 240, 300], fees: "Processing fees often apply; check each lender" },
  car: { name: "Car loan (illustrative)", min: 8.75, max: 10.75, tenures: [36, 60, 84], fees: "Processing fees often apply; check each lender" },
  education: { name: "Education loan (illustrative)", min: 9.5, max: 12.0, tenures: [60, 84, 120], fees: "May need a co-applicant and collateral above some amounts" },
  business: { name: "Business loan (illustrative)", min: 11.0, max: 16.0, tenures: [36, 60, 84], fees: "Terms vary widely with business vintage and collateral" },
  custom: { name: "Personal loan (illustrative)", min: 10.5, max: 16.0, tenures: [24, 36, 60], fees: "Processing fees often apply; check each lender" },
};

export const DEFAULT_TENURE: Record<PurchaseType, number> = {
  house: 240,
  car: 60,
  education: 84,
  business: 60,
  custom: 36,
};

export function illustrativeRate(type: PurchaseType): number {
  const r = ILLUSTRATIVE[type];
  return Math.round(((r.min + r.max) / 2) * 100) / 100;
}

export class IllustrativeResearchProvider implements ResearchProvider {
  readonly id = "illustrative";
  readonly live = false;
  async research(query: ResearchQuery): Promise<ResearchResult> {
    const now = new Date().toISOString();
    const r = ILLUSTRATIVE[query.purchaseType];
    const source: Source = {
      id: "src_illustrative",
      title: "FinPulse illustrative financing assumptions",
      url: null,
      retrievedAt: now,
      kind: "illustrative",
      supports: `${r.name}: ${r.min}%–${r.max}% p.a. Demonstration ranges only — not current lender quotes.`,
    };
    const tenures = [...new Set([...(query.tenureMonths ? [query.tenureMonths] : []), ...r.tenures])].sort((a, b) => a - b);
    const options: FinancingOption[] = [];
    for (const tenure of tenures) {
      for (const [suffix, rate] of [["lower end", r.min], ["upper end", r.max]] as const) {
        options.push({
          id: `opt_${tenure}_${suffix.replace(" ", "_")}`,
          name: `${r.name.replace(" (illustrative)", "")} · ${tenure / 12} yrs · ${suffix} of range`,
          annualRateMin: r.min,
          annualRateMax: r.max,
          rateUsed: rate,
          tenureMonths: tenure,
          feesNote: r.fees,
          basis: "illustrative",
          sourceIds: [source.id],
        });
      }
    }
    return {
      provider: "Illustrative assumptions (live research not configured)",
      live: false,
      retrievedAt: now,
      options,
      sources: [source],
      notes: [
        "Live research is not configured, so these are illustrative ranges, not current offers.",
        "Actual rates depend on the lender, your credit profile, loan amount and the benchmark rate at the time.",
      ],
      warnings: [],
    };
  }
}

const LiveOptionSchema = z.object({
  lender: z.string().min(1).max(80),
  product: z.string().min(1).max(120),
  rate_min: z.number().min(0).max(40),
  rate_max: z.number().min(0).max(40),
  fees_note: z.string().max(200).nullable().optional(),
  source_url: z.string().url(),
  as_of: z.string().max(40).nullable().optional(),
});
const LiveResponseSchema = z.object({ options: z.array(LiveOptionSchema).max(8) });

const PRODUCT_QUERY: Record<PurchaseType, string> = {
  house: "home loan interest rates India",
  car: "new car loan interest rates India",
  education: "education loan interest rates India",
  business: "MSME business loan interest rates India",
  custom: "personal loan interest rates India",
};

export class ClaudeWebSearchProvider implements ResearchProvider {
  readonly id = "claude_web_search";
  readonly live = true;
  constructor(private readonly fallback: ResearchProvider) {}

  async research(query: ResearchQuery, signal?: AbortSignal): Promise<ResearchResult> {
    const retrievedAt = new Date().toISOString();
    const tenure = query.tenureMonths ?? DEFAULT_TENURE[query.purchaseType];
    const response = await getClient().messages.create(
      {
        model: modelId(),
        max_tokens: 4000,
        output_config: { effort: effort() },
        system: `You are the Financial Research Agent of FinPulse, an Indian personal-finance app. Find CURRENT published interest rates using web search. Prefer official lender pages and reputable aggregators. Report only rates you saw on a page you retrieved, with that exact page URL. If you cannot find reliable figures, return an empty list. ${UNTRUSTED_DATA_RULE}`,
        tools: [{ type: "web_search_20260209", name: "web_search", max_uses: 3 }],
        messages: [
          {
            role: "user",
            content: `Research: ${PRODUCT_QUERY[query.purchaseType]} (${new Date().getFullYear()}). Up to 5 lenders. Reply with ONLY a JSON object: {"options":[{"lender":"","product":"","rate_min":0,"rate_max":0,"fees_note":"","source_url":"","as_of":""}]} with rates in % per annum.`,
          },
        ],
      },
      { signal },
    );
    const seenUrls = new Map<string, string>();
    for (const block of response.content as Anthropic.ContentBlock[]) {
      if (block.type === "web_search_tool_result" && Array.isArray(block.content)) {
        for (const r of block.content) seenUrls.set(normaliseUrl(r.url), r.title);
      }
    }
    const text = response.content
      .filter((b): b is Anthropic.TextBlock => b.type === "text")
      .map((b) => b.text)
      .join("\n");
    const parsed = LiveResponseSchema.safeParse(extractJson(text));
    const warnings: string[] = [];
    if (!parsed.success) warnings.push("The research response could not be parsed; no live figures were used.");
    const kept = (parsed.success ? parsed.data.options : []).filter((o) => {
      const ok = seenUrls.has(normaliseUrl(o.source_url)) && o.rate_min <= o.rate_max;
      if (!ok) warnings.push(`Dropped "${o.lender}": its cited source was not among the pages actually retrieved.`);
      return ok;
    });
    if (kept.length === 0) {
      const fb = await this.fallback.research(query);
      return {
        ...fb,
        warnings: [...warnings, "Live research returned no verifiable figures; illustrative ranges used instead."],
      };
    }
    const sources: Source[] = kept.map((o, i) => ({
      id: `src_web_${i + 1}`,
      title: seenUrls.get(normaliseUrl(o.source_url)) || o.lender,
      url: o.source_url,
      retrievedAt,
      kind: "web",
      supports: `${o.lender} ${o.product}: ${o.rate_min}%–${o.rate_max}% p.a.${o.as_of ? ` (as of ${o.as_of})` : ""}`,
    }));
    const options: FinancingOption[] = kept.map((o, i) => ({
      id: `opt_web_${i + 1}`,
      name: `${o.lender} · ${o.product}`,
      annualRateMin: o.rate_min,
      annualRateMax: o.rate_max,
      rateUsed: o.rate_min,
      tenureMonths: tenure,
      feesNote: o.fees_note ?? null,
      basis: "sourced",
      sourceIds: [`src_web_${i + 1}`],
    }));
    return {
      provider: "Live web research (Anthropic web search)",
      live: true,
      retrievedAt,
      options,
      sources,
      notes: [
        "Published rates are starting rates (\"from\"); the rate offered to you depends on your credit profile and the lender's assessment.",
        "EMIs below use each lender's lowest published rate, so they are best cases.",
      ],
      warnings,
    };
  }
}

function normaliseUrl(url: string): string {
  try {
    const u = new URL(url);
    return `${u.hostname.replace(/^www\./, "")}${u.pathname.replace(/\/+$/, "")}`;
  } catch {
    return url;
  }
}

function extractJson(text: string): unknown {
  const fenced = text.match(/```(?:json)?\s*([\s\S]*?)```/);
  const candidate = fenced?.[1] ?? text.slice(text.indexOf("{"), text.lastIndexOf("}") + 1);
  try {
    return JSON.parse(candidate);
  } catch {
    return null;
  }
}

export function researchProvider(): ResearchProvider {
  const illustrative = new IllustrativeResearchProvider();
  return liveResearchEnabled() ? new ClaudeWebSearchProvider(illustrative) : illustrative;
}

export { describeAiError };
