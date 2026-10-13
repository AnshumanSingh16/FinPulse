import { type NextRequest, NextResponse } from "next/server";

import { formatINR } from "@/lib/format";
import {
  DecideBodySchema,
  prepayVsInvestTool,
  rentVsBuyTool,
} from "@/lib/personal/agents/plan-tools";
import { prepayVsInvest, rentVsBuy } from "@/lib/personal/finance/decisions";
import { FinanceInputError } from "@/lib/personal/finance/errors";
import { jsonError, readJson, refuseCrossOrigin } from "@/lib/personal/http";
import { getSession } from "@/lib/personal/session";
import { audit, consumeRateLimit } from "@/lib/personal/store";

export const dynamic = "force-dynamic";

/** Run one of the decision simulators (rent vs buy, prepay vs invest). */
export async function POST(request: NextRequest) {
  const refused = refuseCrossOrigin(request);
  if (refused) return refused;
  const parsed = DecideBodySchema.safeParse(await readJson(request));
  if (!parsed.success)
    return jsonError(
      400,
      "Invalid comparison",
      parsed.error.issues.map((i) => `${i.path.join(".")}: ${i.message}`),
    );
  const session = await getSession();
  if (!consumeRateLimit(session, 60))
    return jsonError(429, "Too many requests. Wait a minute and try again.");
  try {
    const body = parsed.data;
    if (body.kind === "rent_vs_buy") {
      const result = rentVsBuy(body.input);
      audit(
        session,
        "decision_compared",
        "user",
        `Rent vs buy for a ${formatINR(body.input.price)} home: ${rentVsBuyTool.summarize(result)}`,
      );
      return NextResponse.json({ kind: body.kind, input: body.input, result });
    }
    const result = prepayVsInvest(body.input);
    audit(
      session,
      "decision_compared",
      "user",
      `Prepay vs invest ${formatINR(body.input.lumpSum)}: ${prepayVsInvestTool.summarize(result)}`,
    );
    return NextResponse.json({ kind: body.kind, input: body.input, result });
  } catch (error) {
    if (error instanceof FinanceInputError) return jsonError(400, error.message);
    throw error;
  }
}
