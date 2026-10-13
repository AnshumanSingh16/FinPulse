/**
 * The agent runtime: a typed tool registry and an executor that validates every tool call,
 * enforces per-run limits, and records each call and event on the workflow run. The UI's agent
 * activity feed is exactly this event list — nothing is animated or invented client-side.
 */
import "server-only";

import type { z } from "zod";

import { newId } from "../store";
import type { AgentEvent, AgentName, ToolCallRecord, WorkflowRun } from "./types";

export type ToolDef<I, O> = {
  name: string;
  agent: AgentName;
  description: string;
  input: z.ZodType<I>;
  run: (input: I, signal: AbortSignal) => Promise<O> | O;
  summarize: (output: O) => string;
  /** Tool results the UI does not need verbatim (e.g. 240-row schedules) can be slimmed. */
  slim?: (output: O) => unknown;
};

// The registry stores heterogeneous tools; their types are recovered at the call site.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type AnyTool = ToolDef<any, any>;

/** Anything an agent run records into: a workflow run, a strategy run… */
export type TracedRun = Pick<WorkflowRun, "events" | "toolCalls" | "plan" | "limits">;

export class LimitExceededError extends Error {}
export class ToolInputError extends Error {}

export class RunContext<R extends TracedRun = WorkflowRun> {
  private readonly started = Date.now();
  readonly controller = new AbortController();

  constructor(
    readonly run: R,
    private readonly listener: (event: AgentEvent) => void,
  ) {}

  emit(
    agent: AgentName,
    kind: AgentEvent["kind"],
    message: string,
    extra: Partial<Pick<AgentEvent, "stepId" | "toolCallId" | "level" | "plan">> = {},
  ): AgentEvent {
    const event: AgentEvent = {
      id: newId("evt"),
      at: new Date().toISOString(),
      agent,
      kind,
      message,
      ...extra,
    };
    this.run.events.push(event);
    this.listener(event);
    return event;
  }

  get elapsedMs(): number {
    return Date.now() - this.started;
  }

  checkLimits(): void {
    const { maxDurationMs, maxToolCalls } = this.run.limits;
    if (this.elapsedMs > maxDurationMs) throw new LimitExceededError("Workflow time limit reached");
    if (this.run.toolCalls.length >= maxToolCalls)
      throw new LimitExceededError("Tool-call limit reached");
  }

  useLlmCall(): boolean {
    if (this.run.limits.llmCalls >= this.run.limits.maxLlmCalls) return false;
    this.run.limits.llmCalls += 1;
    return true;
  }

  /** Validate, execute and record one tool call. Throws on invalid input or tool failure. */
  async callTool<I, O>(tool: ToolDef<I, O>, rawInput: unknown, stepId?: string): Promise<O> {
    this.checkLimits();
    const record: ToolCallRecord = {
      id: newId("call"),
      tool: tool.name,
      agent: tool.agent,
      stepId,
      input: rawInput,
      status: "ok",
      startedAt: new Date().toISOString(),
      durationMs: 0,
    };
    this.run.toolCalls.push(record);
    const step = stepId ? this.run.plan.find((s) => s.id === stepId) : undefined;
    step?.toolCallIds.push(record.id);
    this.emit(tool.agent, "tool_call", `Calling ${tool.name}`, { stepId, toolCallId: record.id });

    const parsed = tool.input.safeParse(rawInput);
    if (!parsed.success) {
      record.status = "rejected";
      record.error = parsed.error.issues
        .map((i) => `${i.path.join(".") || "input"}: ${i.message}`)
        .join("; ");
      this.emit(tool.agent, "tool_error", `${tool.name} rejected invalid input: ${record.error}`, {
        stepId,
        toolCallId: record.id,
        level: "error",
      });
      throw new ToolInputError(record.error);
    }
    const t0 = Date.now();
    try {
      const output = await tool.run(parsed.data, this.controller.signal);
      record.durationMs = Date.now() - t0;
      record.output = tool.slim ? tool.slim(output) : output;
      record.outputSummary = tool.summarize(output);
      this.emit(tool.agent, "tool_result", `${tool.name}: ${record.outputSummary}`, {
        stepId,
        toolCallId: record.id,
      });
      return output;
    } catch (error) {
      record.durationMs = Date.now() - t0;
      record.status = "error";
      record.error = error instanceof Error ? error.message : "Tool failed";
      this.emit(tool.agent, "tool_error", `${tool.name} failed: ${record.error}`, {
        stepId,
        toolCallId: record.id,
        level: "error",
      });
      throw error;
    }
  }
}
