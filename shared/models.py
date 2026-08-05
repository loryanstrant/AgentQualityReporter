"""SQLAlchemy 2.0 ORM models for the Agent Quality Platform.

Postgres-specific column types (JSONB) fall back to portable JSON under SQLite so
the test-suite can run without a Postgres instance.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.db import Base

# Portable JSON: JSONB on Postgres, plain JSON on SQLite (tests).
JsonType = JSONB().with_variant(JSON(), "sqlite")


class AppConfig(Base):
    """Single-row global settings. Secrets stored Fernet-encrypted.

    Holds the shared service-principal credentials used to read Dataverse / BAP /
    App Insights, the Azure OpenAI (Foundry) judge configuration, the Entra report
    access group, the scan schedule, and the seeded default-icon hashes.
    """

    __tablename__ = "app_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)

    # Service principal (Dataverse Web API + BAP + Graph group checks).
    tenant_id: Mapped[str | None] = mapped_column(Text)
    client_id: Mapped[str | None] = mapped_column(Text)
    client_secret_encrypted: Mapped[str | None] = mapped_column(Text)

    # Azure OpenAI (Foundry) LLM judge.
    aoai_base_url: Mapped[str | None] = mapped_column(Text)
    aoai_model: Mapped[str | None] = mapped_column(Text)
    aoai_key_encrypted: Mapped[str | None] = mapped_column(Text)

    # Entra security group whose members may view the reports (optional).
    report_access_group_id: Mapped[str | None] = mapped_column(Text)

    # Scan cadence: run every N hours (1..24; 24 = daily).
    schedule_interval_hours: Mapped[int] = mapped_column(Integer, default=24)

    # Known-default Copilot Studio icon SHA-256 hashes (auto-fills AGT-009).
    default_icon_hashes: Mapped[list] = mapped_column(JsonType, default=list)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    updated_by: Mapped[str | None] = mapped_column(Text)


class Environment(Base):
    """A Power Platform / Dataverse environment to scan."""

    __tablename__ = "environments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    display_name: Mapped[str] = mapped_column(Text)
    # Dataverse Web API org URL, e.g. https://org.crm.dynamics.com
    dataverse_url: Mapped[str | None] = mapped_column(Text)
    # Power Platform environment GUID (resolved at scan time) — used to build
    # deep links into Copilot Studio and the Power Apps maker portal.
    environment_guid: Mapped[str | None] = mapped_column(Text)
    # Application Insights Application ID (for the query API), optional.
    app_insights_app_id: Mapped[str | None] = mapped_column(Text)
    app_insights_key_encrypted: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    scans: Mapped[list["Scan"]] = relationship(back_populates="environment")


class Agent(Base):
    """A Copilot Studio agent (bot) seen during scanning. Latest-known metadata."""

    __tablename__ = "agents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    environment_id: Mapped[int | None] = mapped_column(
        ForeignKey("environments.id"), index=True
    )
    bot_id: Mapped[str | None] = mapped_column(Text, index=True)
    display_name: Mapped[str | None] = mapped_column(Text)
    schema_name: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    model_hint: Mapped[str | None] = mapped_column(Text)
    publish_state: Mapped[str | None] = mapped_column(Text)
    icon_hash: Mapped[str | None] = mapped_column(Text)
    created_on: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    modified_on: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_name: Mapped[str | None] = mapped_column(Text)
    created_by_upn: Mapped[str | None] = mapped_column(Text)
    last_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Scan(Base):
    """One quality scan run over an environment (or the bundled demo/zip source)."""

    __tablename__ = "scans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    environment_id: Mapped[int | None] = mapped_column(
        ForeignKey("environments.id"), index=True
    )
    solution_name: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text, default="dataverse")  # dataverse|zip|demo
    trigger: Mapped[str] = mapped_column(Text, default="manual")  # manual|scheduled
    status: Mapped[str] = mapped_column(Text, default="running")  # running|complete|failed
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    score: Mapped[int | None] = mapped_column(Integer)
    grade: Mapped[str | None] = mapped_column(String(1))
    agent_count: Mapped[int] = mapped_column(Integer, default=0)
    agents_done: Mapped[int] = mapped_column(Integer, default=0)
    engine_version: Mapped[str | None] = mapped_column(Text)
    catalogue_hash: Mapped[str | None] = mapped_column(Text)
    detail: Mapped[str | None] = mapped_column(Text)

    environment: Mapped["Environment | None"] = relationship(back_populates="scans")
    findings: Mapped[list["Finding"]] = relationship(
        back_populates="scan", cascade="all, delete-orphan"
    )
    judge_results: Mapped[list["JudgeResult"]] = relationship(
        back_populates="scan", cascade="all, delete-orphan"
    )
    telemetry: Mapped[list["TelemetrySnapshot"]] = relationship(
        back_populates="scan", cascade="all, delete-orphan"
    )


class Finding(Base):
    """A single rule outcome within a scan."""

    __tablename__ = "findings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scan_id: Mapped[int] = mapped_column(ForeignKey("scans.id"), index=True)
    rule_id: Mapped[str] = mapped_column(Text, index=True)
    name: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)  # pass|fail|skipped
    manual_review: Mapped[bool] = mapped_column(Boolean, default=False)
    weight: Mapped[int] = mapped_column(Integer, default=0)
    scope: Mapped[str] = mapped_column(Text, default="solution")
    agent_name: Mapped[str | None] = mapped_column(Text, index=True)
    details: Mapped[str | None] = mapped_column(Text)
    pp_reference: Mapped[str | None] = mapped_column(Text)

    scan: Mapped["Scan"] = relationship(back_populates="findings")


class JudgeResult(Base):
    """LLM-judge verdict for one agent within a scan."""

    __tablename__ = "judge_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scan_id: Mapped[int] = mapped_column(ForeignKey("scans.id"), index=True)
    agent_name: Mapped[str] = mapped_column(Text, index=True)
    clarity: Mapped[int | None] = mapped_column(Integer)
    scope_discipline: Mapped[int | None] = mapped_column(Integer)
    persona_defined: Mapped[bool | None] = mapped_column(Boolean)
    orchestrator_pattern_detected: Mapped[bool | None] = mapped_column(Boolean)
    child_pattern_detected: Mapped[bool | None] = mapped_column(Boolean)
    output_format_guidance: Mapped[bool | None] = mapped_column(Boolean)
    top_strengths: Mapped[list | None] = mapped_column(JsonType)
    top_weaknesses: Mapped[list | None] = mapped_column(JsonType)
    recommended_changes: Mapped[list | None] = mapped_column(JsonType)
    summary: Mapped[str | None] = mapped_column(Text)
    skipped: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[str | None] = mapped_column(Text)

    scan: Mapped["Scan"] = relationship(back_populates="judge_results")


class TelemetrySnapshot(Base):
    """Application Insights evidence for one agent within a scan (AGT-007)."""

    __tablename__ = "telemetry_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scan_id: Mapped[int] = mapped_column(ForeignKey("scans.id"), index=True)
    agent_name: Mapped[str] = mapped_column(Text, index=True)
    window_days: Mapped[int] = mapped_column(Integer, default=30)
    run_count: Mapped[int | None] = mapped_column(Integer)
    error_count: Mapped[int | None] = mapped_column(Integer)
    p95_latency_ms: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str | None] = mapped_column(Text)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    scan: Mapped["Scan"] = relationship(back_populates="telemetry")


class AgentScore(Base):
    """Per-agent score within a scan — powers the agent list and daily history."""

    __tablename__ = "agent_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scan_id: Mapped[int] = mapped_column(ForeignKey("scans.id"), index=True)
    environment_id: Mapped[int | None] = mapped_column(
        ForeignKey("environments.id"), index=True
    )
    bot_id: Mapped[str | None] = mapped_column(Text, index=True)
    agent_name: Mapped[str] = mapped_column(Text, index=True)
    solution_name: Mapped[str | None] = mapped_column(Text)
    # Owning-solution GUID (for a maker-portal deep link), when known.
    solution_id: Mapped[str | None] = mapped_column(Text)
    publish_state: Mapped[str | None] = mapped_column(Text)
    score: Mapped[int | None] = mapped_column(Integer)
    grade: Mapped[str | None] = mapped_column(String(1))
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class JobRun(Base):
    """One record per scan/collector run for observability."""

    __tablename__ = "job_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_name: Mapped[str] = mapped_column(Text, index=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(Text, default="running")
    stats: Mapped[dict | None] = mapped_column(JsonType)


class RuleConfig(Base):
    """Editable per-rule configuration overlaid on the markdown catalogue.

    Seeded from ``rule-catalogue.md`` on first run; admins can then toggle a rule
    on/off, adjust its scoring weight, and edit its explanation without touching
    the markdown. The scan engine reads these at scan time.
    """

    __tablename__ = "rule_configs"

    rule_id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(Text)
    pp_reference: Mapped[str | None] = mapped_column(Text)
    scope: Mapped[str | None] = mapped_column(Text)  # solution | agent
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    weight: Mapped[int] = mapped_column(Integer, default=0)
    explanation: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    updated_by: Mapped[str | None] = mapped_column(Text)


class AppUser(Base):
    """Local login account for the password gate."""

    __tablename__ = "app_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(Text, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(Text, default="viewer")  # admin | viewer
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
