/**
 * Shared API types. `schema.gen.ts` is generated from `openapi.json`, which is exported from the
 * FastAPI app — run `npm run contracts:generate` after changing any backend schema. Never edit the
 * generated file by hand.
 */
import type { components, paths } from "./schema.gen";

export type { components, operations, paths } from "./schema.gen";

type Schemas = components["schemas"];

export type HealthResponse = Schemas["HealthResponse"];
export type ReadinessResponse = Schemas["ReadinessResponse"];
export type DependencyCheck = Schemas["DependencyCheck"];
export type ProblemDetails = Schemas["ProblemDetails"];
export type FieldError = Schemas["FieldError"];

export type ApiPath = keyof paths;
