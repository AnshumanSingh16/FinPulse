import { type NextRequest, NextResponse } from "next/server";
import { z } from "zod";

import { jsonError, readJson, refuseCrossOrigin, stateView } from "@/lib/personal/http";
import { getSession } from "@/lib/personal/session";
import { audit, transitionActionPlan, TransitionError } from "@/lib/personal/store";

export const dynamic = "force-dynamic";

const Body = z.discriminatedUnion("action", [
  z.object({ action: z.literal("approve"), note: z.string().max(300).optional() }),
  z.object({ action: z.literal("reject"), note: z.string().max(300).optional() }),
  z.object({ action: z.literal("reopen") }),
  z.object({ action: z.literal("complete") }),
  z.object({ action: z.literal("toggle_item"), itemId: z.string().max(40) }),
]);

/**
 * User decisions on an action plan. The state machine in the store enforces the order:
 * review → approve/reject → complete. Items can only be ticked off after approval, and items that
 * need an external integration can never be marked done here.
 */
export async function POST(request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const refused = refuseCrossOrigin(request);
  if (refused) return refused;
  const parsed = Body.safeParse(await readJson(request));
  if (!parsed.success) return jsonError(400, "Invalid action");
  const session = await getSession();
  const { id } = await params;
  const plan = session.actionPlans.find((p) => p.id === id);
  if (!plan) return jsonError(404, "Action plan not found");
  const body = parsed.data;
  try {
    switch (body.action) {
      case "approve":
        transitionActionPlan(plan, "approved", "user", body.note);
        audit(session, "approval_decision", "user", `Approved "${plan.title}"`, plan.runId);
        break;
      case "reject":
        transitionActionPlan(plan, "rejected", "user", body.note);
        audit(session, "approval_decision", "user", `Rejected "${plan.title}"${body.note ? `: ${body.note}` : ""}`, plan.runId);
        break;
      case "reopen":
        transitionActionPlan(plan, "awaiting_review", "user");
        audit(session, "approval_requested", "user", `Reopened "${plan.title}" for review`, plan.runId);
        break;
      case "complete": {
        if (plan.status !== "approved") return jsonError(409, `Cannot complete a plan that is "${plan.status.replace("_", " ")}"; it must be approved first.`);
        const open = plan.items.filter((i) => !i.done && !i.requiresIntegration);
        if (open.length) return jsonError(409, `${open.length} checklist item(s) are still open.`);
        transitionActionPlan(plan, "completed", "user");
        audit(session, "action_completed", "user", `Completed "${plan.title}" (items needing an external integration were not executed)`, plan.runId);
        break;
      }
      case "toggle_item": {
        if (plan.status !== "approved") return jsonError(409, "Approve the plan before ticking off items.");
        const item = plan.items.find((i) => i.id === body.itemId);
        if (!item) return jsonError(404, "Item not found");
        if (item.requiresIntegration) return jsonError(409, "This step needs an external integration FinPulse does not have; do it directly with the provider.");
        item.done = !item.done;
        break;
      }
    }
  } catch (error) {
    if (error instanceof TransitionError) return jsonError(409, error.message);
    throw error;
  }
  return NextResponse.json(stateView(session));
}
