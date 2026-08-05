export interface Finding {
  rule_id: string;
  name: string;
  severity: "blocker" | "major" | "minor" | "info";
  status: "pass" | "fail" | "skipped";
  manual_review: boolean;
  weight: number;
  scope: string;
  details: string | null;
  pp_reference: string | null;
}

export interface Judge {
  skipped: boolean;
  error: string | null;
  clarity: number | null;
  scope_discipline: number | null;
  persona_defined: boolean | null;
  orchestrator_pattern_detected: boolean | null;
  child_pattern_detected: boolean | null;
  output_format_guidance: boolean | null;
  top_strengths: string[] | null;
  top_weaknesses: string[] | null;
  recommended_changes: string[] | null;
  summary: string | null;
}

export interface Telemetry {
  window_days: number;
  run_count: number | null;
  error_count: number | null;
  p95_latency_ms: number | null;
  source: string | null;
}

export interface EnvironmentCard {
  environment_id: number | null;
  name: string;
  latest_scan_id: number;
  agent_count: number;
  avg_score: number | null;
  grade: string | null;
  scanned_at: string | null;
}

export interface AgentListItem {
  bot_id: string | null;
  agent_name: string;
  solution_name: string | null;
  publish_state: string | null;
  score: number | null;
  grade: string | null;
  scan_id: number;
  environment_id: number | null;
  environment_name?: string | null;
}

export interface RuleItem {
  rule_id: string;
  name: string;
  severity: string;
  scope: string | null;
  pp_reference: string | null;
  enabled: boolean;
  weight: number;
  explanation: string | null;
  updated_at: string | null;
  updated_by: string | null;
}

export interface AgentDetail {
  bot_id: string;
  agent_name: string;
  solution_name: string | null;
  solution_id: string | null;
  solution_url: string | null;
  agent_url: string | null;
  publish_state: string | null;
  score: number | null;
  grade: string | null;
  scan_id: number;
  environment_id: number | null;
  environment_name: string | null;
  environment_guid: string | null;
  schema_name: string | null;
  model_hint: string | null;
  created_on: string | null;
  modified_on: string | null;
  created_by_name: string | null;
  created_by_upn: string | null;
  findings: Finding[];
  judge: Judge | null;
  telemetry: Telemetry | null;
}

export interface HistoryPoint {
  scan_id: number;
  score: number | null;
  grade: string | null;
  captured_at: string | null;
}

export interface ScanRow {
  id: number;
  environment: string;
  source: string;
  trigger: string;
  agent_count: number;
  avg_score: number | null;
  grade: string | null;
  started_at: string | null;
}

export interface AppConfig {
  tenant_id: string | null;
  client_id: string | null;
  has_client_secret: boolean;
  aoai_base_url: string | null;
  aoai_model: string | null;
  has_aoai_key: boolean;
  report_access_group_id: string | null;
  schedule_interval_hours: number;
  configured: boolean;
  judge_configured: boolean;
  updated_at: string | null;
  updated_by: string | null;
}

export interface Environment {
  id: number;
  display_name: string;
  dataverse_url: string | null;
  app_insights_app_id: string | null;
  has_app_insights_key: boolean;
  enabled: boolean;
  created_at: string | null;
  last_scanned?: string | null;
  last_agent_count?: number | null;
}

export interface ScanProgress {
  scan_id: number;
  environment_id: number | null;
  source: string;
  agents_done: number;
  agent_count: number;
  started_at: string | null;
}

export function cleanPP(value: string | null | undefined): string {
  return (value || "").replace(/^\s*slide\s+\d+\s*[-–—:]\s*/i, "").trim();
}

export const GRADE_COLORS: Record<string, string> = {
  A: "#2A9D8F",
  B: "#52B788",
  C: "#E9C46A",
  D: "#F4A261",
  F: "#E63946",
};
