/**
 * Turns a stress shock's parameter JSON Schema (from GET /meta/stress-scenarios) into form fields
 * and back. Unit conversion for display only (0.2 ↔ "20" %); the API does all calculation.
 */

type JsonSchema = {
  type?: string;
  format?: string;
  anyOf?: JsonSchema[];
  title?: string;
  description?: string;
  default?: unknown;
  properties?: Record<string, JsonSchema>;
  required?: string[];
  minimum?: number;
  maximum?: number;
};

export type FieldKind = "percent" | "decimal" | "integer" | "boolean" | "uuid";
export type Field = {
  key: string;
  label: string;
  help?: string;
  kind: FieldKind;
  required: boolean;
  nullable: boolean;
  defaultValue: unknown;
  min?: number;
  max?: number;
};
export type FormValue = string | boolean;

const PERCENT_KEYS = /(_pct|^annual_rate)$/;

function variants(s: JsonSchema): JsonSchema[] {
  return s.anyOf ?? [s];
}

export function fieldsOf(schema: unknown): Field[] {
  const s = schema as JsonSchema;
  const required = new Set(s.required ?? []);
  return Object.entries(s.properties ?? {})
    .filter(([key]) => key !== "type")
    .map(([key, prop]) => {
      const vs = variants(prop);
      const types = vs.map((v) => v.type);
      const nullable = types.includes("null");
      let kind: FieldKind;
      if (types.includes("boolean")) kind = "boolean";
      else if (vs.some((v) => v.format === "uuid")) kind = "uuid";
      else if (types.includes("number")) kind = PERCENT_KEYS.test(key) ? "percent" : "decimal";
      else kind = "integer";
      const bounded = vs.find((v) => v.minimum !== undefined || v.maximum !== undefined);
      return {
        key,
        label: (prop.title ?? key).replace(/ Pct$/, "").replace(/ Bps$/, " (bps)"),
        help: prop.description,
        kind,
        required: required.has(key),
        nullable,
        defaultValue: prop.default,
        min: bounded?.minimum,
        max: bounded?.maximum,
      };
    });
}

function trimNumber(n: number): string {
  return String(Number.parseFloat(n.toFixed(6)));
}

/** API value → form input. */
export function toInput(field: Field, value: unknown): FormValue {
  if (field.kind === "boolean")
    return value === undefined || value === null ? Boolean(field.defaultValue) : Boolean(value);
  if (value === undefined || value === null || value === "") return "";
  if (field.kind === "percent") return trimNumber(Number(value) * 100);
  return String(value);
}

/** Form input → API value; `undefined` means "leave it to the API's default". */
export function toParam(field: Field, input: FormValue): unknown {
  if (field.kind === "boolean") return input;
  const text = String(input).trim();
  if (text === "") return undefined;
  if (field.kind === "integer") return Number.parseInt(text, 10);
  if (field.kind === "percent") return trimNumber(Number(text) / 100);
  return text;
}

export function initialInputs(
  fields: Field[],
  params: Record<string, unknown> = {},
): Record<string, FormValue> {
  return Object.fromEntries(
    fields.map((f) => [f.key, toInput(f, params[f.key] ?? f.defaultValue)]),
  );
}

export function shockPayload(type: string, fields: Field[], inputs: Record<string, FormValue>) {
  const out: Record<string, unknown> = { type };
  for (const f of fields) {
    const v = toParam(f, inputs[f.key] ?? "");
    if (v !== undefined) out[f.key] = v;
  }
  return out;
}

/** Missing required values, by field label. */
export function missing(fields: Field[], inputs: Record<string, FormValue>): string[] {
  return fields
    .filter((f) => f.required && toParam(f, inputs[f.key] ?? "") === undefined)
    .map((f) => f.label);
}
