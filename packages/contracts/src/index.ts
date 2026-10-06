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

export type WarningsReport = Schemas["WarningsReport"];
export type EarlyWarning = Schemas["EarlyWarning"];
export type WarningEvidence = Schemas["WarningEvidence"];
export type WarningThreshold = Schemas["Threshold"];
export type RiskSummary = Schemas["RiskSummary"];
export type RiskTimelinePoint = Schemas["TimelinePoint"];
export type EarlyWarningRuleCatalogue = Schemas["RuleCatalogue"];

export type EvidencePack = Schemas["EvidencePack"];
export type EvidenceItem = Schemas["EvidenceItem"];
export type AgentRun = Schemas["AgentRun"];
export type AgentClaim = Schemas["RegisteredClaim"];
export type VerificationReport = Schemas["VerificationReport"];
export type AgentInfo = Schemas["AgentInfo"];
export type SingleAgentResponse = Schemas["SingleAgentResponse"];

export type Investigation = Schemas["Investigation"];
export type InvestigationSummary = Schemas["InvestigationSummary"];
export type InvestigationEvent = Schemas["InvestigationEvent"];
export type InvestigationStage = Schemas["StageRecord"];
export type Disagreement = Schemas["Disagreement"];
export type FinalAssessment = Schemas["FinalAssessment"];

export type StressTestRequest = Schemas["StressTestRequest"];
export type StressTestResult = Schemas["StressTestResult"];
export type StressProjection = Schemas["Projection"];
export type ProjectedMonth = Schemas["ProjectedMonth"];
export type StressComparison = Schemas["Comparison"];
export type RiskChange = Schemas["RiskChange"];
export type FailurePoint = Schemas["FailurePoint"];
export type HealthImpact = Schemas["HealthImpact"];
export type StressEvidence = Schemas["Evidence"];
export type ScenarioCatalogue = Schemas["ScenarioCatalogue"];

export type ApiPath = keyof paths;
