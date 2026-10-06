import "server-only";

import { cache } from "react";

import type {
  EntitySummary,
  EvidencePack,
  FinancialMetricsReport,
  Investigation,
  InvestigationSummary,
  MetricHistory,
  Passport,
  PassportHistory,
  RiskSummary,
  ScenarioCatalogue,
  WarningsReport,
} from "@finpulse/contracts";

import { unwrap } from "./client";
import { getServerApiClient } from "./server";

/**
 * Server-side reads of the FinPulse API. Every number the UI shows comes from these calls —
 * the frontend formats and lays out, it never calculates or invents financial values.
 */

type AsOf = string | undefined;
const asOfQuery = (asOf: AsOf) => (asOf ? { as_of: asOf } : {});
// Investigation-scale responses can take a while to compute; reads elsewhere are fast.
const api = () => getServerApiClient();

export const getEntities = cache(function getEntities(): Promise<EntitySummary[]> {
  return unwrap(api().GET("/api/v1/entities"));
});

export const getMetrics = cache(function getMetrics(
  entityId: string,
  asOf?: AsOf,
): Promise<FinancialMetricsReport> {
  return unwrap(
    api().GET("/api/v1/entities/{entity_id}/financial-metrics", {
      params: { path: { entity_id: entityId }, query: asOfQuery(asOf) },
    }),
  );
});

export const getMetricHistory = cache(function getMetricHistory(
  entityId: string,
  asOf: AsOf,
  codes: string[],
  months = 12,
): Promise<MetricHistory> {
  return unwrap(
    api().GET("/api/v1/entities/{entity_id}/financial-metrics/history", {
      params: { path: { entity_id: entityId }, query: { ...asOfQuery(asOf), codes, months } },
    }),
  );
});

export const getPassport = cache(function getPassport(
  entityId: string,
  asOf?: AsOf,
): Promise<Passport> {
  return unwrap(
    api().GET("/api/v1/entities/{entity_id}/passport", {
      params: { path: { entity_id: entityId }, query: asOfQuery(asOf) },
    }),
  );
});

export const getPassportHistory = cache(function getPassportHistory(
  entityId: string,
  asOf?: AsOf,
  months = 12,
): Promise<PassportHistory> {
  return unwrap(
    api().GET("/api/v1/entities/{entity_id}/passport/history", {
      params: { path: { entity_id: entityId }, query: { ...asOfQuery(asOf), months } },
    }),
  );
});

export const getPassportModel = cache(function getPassportModel() {
  return unwrap(api().GET("/api/v1/meta/passport-model"));
});

export const getWarnings = cache(function getWarnings(
  entityId: string,
  asOf?: AsOf,
): Promise<WarningsReport> {
  return unwrap(
    api().GET("/api/v1/entities/{entity_id}/warnings", {
      params: { path: { entity_id: entityId }, query: asOfQuery(asOf) },
    }),
  );
});

export const getRiskSummary = cache(function getRiskSummary(
  entityId: string,
  asOf?: AsOf,
): Promise<RiskSummary> {
  return unwrap(
    api().GET("/api/v1/entities/{entity_id}/risk-summary", {
      params: { path: { entity_id: entityId }, query: asOfQuery(asOf) },
    }),
  );
});

export const getStressCatalogue = cache(function getStressCatalogue(): Promise<ScenarioCatalogue> {
  return unwrap(api().GET("/api/v1/meta/stress-scenarios"));
});

export const getEvidencePack = cache(function getEvidencePack(
  entityId: string,
  asOf?: AsOf,
): Promise<EvidencePack> {
  return unwrap(
    api().GET("/api/v1/entities/{entity_id}/evidence-pack", {
      params: { path: { entity_id: entityId }, query: asOfQuery(asOf) },
    }),
  );
});

export const listInvestigations = cache(function listInvestigations(
  entityId: string,
): Promise<InvestigationSummary[]> {
  return unwrap(
    api().GET("/api/v1/investigations", { params: { query: { entity_id: entityId } } }),
  );
});

export const getInvestigation = cache(function getInvestigation(
  investigationId: string,
): Promise<Investigation> {
  return unwrap(
    api().GET("/api/v1/investigations/{investigation_id}", {
      params: { path: { investigation_id: investigationId } },
    }),
  );
});
