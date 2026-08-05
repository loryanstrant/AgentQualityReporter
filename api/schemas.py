"""Pydantic request/response schemas for the API."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# --- auth ---------------------------------------------------------------
class LoginIn(BaseModel):
    username: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    role: str


class UserOut(BaseModel):
    username: str
    role: str


class AuthModeOut(BaseModel):
    entra_available: bool = False


# --- admin config -------------------------------------------------------
class AppConfigIn(BaseModel):
    tenant_id: str | None = None
    client_id: str | None = None
    client_secret: str | None = None  # write-only
    aoai_base_url: str | None = None
    aoai_model: str | None = None
    aoai_key: str | None = None  # write-only
    report_access_group_id: str | None = None
    schedule_interval_hours: int | None = Field(default=None, ge=1, le=24)
    default_icon_hashes: list[str] | None = None


class AppConfigOut(BaseModel):
    tenant_id: str | None = None
    client_id: str | None = None
    has_client_secret: bool = False
    aoai_base_url: str | None = None
    aoai_model: str | None = None
    has_aoai_key: bool = False
    report_access_group_id: str | None = None
    schedule_interval_hours: int = 24
    default_icon_hashes: list[str] = []
    configured: bool = False
    judge_configured: bool = False
    updated_at: datetime | None = None
    updated_by: str | None = None


class TestConnectionOut(BaseModel):
    ok: bool
    token_acquired: bool = False
    org_reachable: bool = False
    bots_found: int | None = None
    detail: str | None = None


class ScanRunOut(BaseModel):
    status: str
    detail: str
    scan_id: int | None = None
    score: int | None = None
    grade: str | None = None


# --- environments -------------------------------------------------------
class EnvironmentIn(BaseModel):
    display_name: str
    dataverse_url: str | None = None
    app_insights_app_id: str | None = None
    app_insights_key: str | None = None  # write-only
    enabled: bool = True


class EnvironmentOut(BaseModel):
    id: int
    display_name: str
    dataverse_url: str | None = None
    app_insights_app_id: str | None = None
    has_app_insights_key: bool = False
    enabled: bool = True
    created_at: datetime | None = None
    last_scanned: datetime | None = None
    last_agent_count: int | None = None


class RuleConfigIn(BaseModel):
    enabled: bool | None = None
    weight: int | None = Field(default=None, ge=0, le=100)
    explanation: str | None = None


# --- reports ------------------------------------------------------------
class FindingOut(BaseModel):
    rule_id: str
    name: str
    severity: str
    status: str
    manual_review: bool
    weight: int
    scope: str
    agent_name: str | None = None
    details: str | None = None
    pp_reference: str | None = None


class JudgeOut(BaseModel):
    agent_name: str
    skipped: bool = False
    error: str | None = None
    clarity: int | None = None
    scope_discipline: int | None = None
    persona_defined: bool | None = None
    orchestrator_pattern_detected: bool | None = None
    child_pattern_detected: bool | None = None
    output_format_guidance: bool | None = None
    top_strengths: list[str] | None = None
    top_weaknesses: list[str] | None = None
    recommended_changes: list[str] | None = None
    summary: str | None = None


class TelemetryOut(BaseModel):
    agent_name: str
    window_days: int
    run_count: int | None = None
    error_count: int | None = None
    p95_latency_ms: float | None = None
    source: str | None = None


class ScanSummaryOut(BaseModel):
    id: int
    solution_name: str | None = None
    environment_id: int | None = None
    source: str
    trigger: str
    status: str
    score: int | None = None
    grade: str | None = None
    agent_count: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None


class ScanDetailOut(ScanSummaryOut):
    engine_version: str | None = None
    catalogue_hash: str | None = None
    findings: list[FindingOut] = []
    judge_results: list[JudgeOut] = []
    telemetry: list[TelemetryOut] = []


class SeverityBreakdown(BaseModel):
    blocker: int = 0
    major: int = 0
    minor: int = 0
    info: int = 0


class OverviewOut(BaseModel):
    latest: ScanSummaryOut | None = None
    pass_count: int = 0
    fail_count: int = 0
    skipped_count: int = 0
    manual_count: int = 0
    failed_by_severity: SeverityBreakdown = SeverityBreakdown()
    agent_count: int = 0
    trend: list[dict[str, Any]] = []


class StatusOut(BaseModel):
    configured: bool
    judge_configured: bool = False
    environments: int = 0
    scans: int = 0
    agents: int = 0
    last_scan: ScanSummaryOut | None = None
