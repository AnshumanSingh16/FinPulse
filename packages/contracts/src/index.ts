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

export type EntitySummary = Schemas["EntitySummary"];
export type FinancialMetricsReport = Schemas["FinancialMetricsReport"];
export type Metric = Schemas["Metric"];
export type MetricSeries = Schemas["MetricSeries"];
export type MetricDefinition = Schemas["MetricDefinitionOut"];
export type DataCoverage = Schemas["DataCoverage"];

export type Passport = Schemas["Passport"];
export type PassportHistory = Schemas["PassportHistory"];
export type DimensionScore = Schemas["DimensionScore"];
export type FactorScore = Schemas["FactorScore"];
export type ScoreChange = Schemas["ScoreChange"];

export type ApiPath = keyof paths;
