"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-08-04
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "app_config",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Text()),
        sa.Column("client_id", sa.Text()),
        sa.Column("client_secret_encrypted", sa.Text()),
        sa.Column("aoai_base_url", sa.Text()),
        sa.Column("aoai_model", sa.Text()),
        sa.Column("aoai_key_encrypted", sa.Text()),
        sa.Column("report_access_group_id", sa.Text()),
        sa.Column("schedule_interval_hours", sa.Integer(), nullable=False, server_default="24"),
        sa.Column("default_icon_hashes", postgresql.JSONB(), server_default="[]"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_by", sa.Text()),
    )

    op.create_table(
        "environments",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("dataverse_url", sa.Text()),
        sa.Column("app_insights_app_id", sa.Text()),
        sa.Column("app_insights_key_encrypted", sa.Text()),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "agents",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("environment_id", sa.Integer(), sa.ForeignKey("environments.id")),
        sa.Column("bot_id", sa.Text()),
        sa.Column("display_name", sa.Text()),
        sa.Column("schema_name", sa.Text()),
        sa.Column("description", sa.Text()),
        sa.Column("model_hint", sa.Text()),
        sa.Column("publish_state", sa.Text()),
        sa.Column("icon_hash", sa.Text()),
        sa.Column("last_seen", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_agents_environment_id", "agents", ["environment_id"])
    op.create_index("ix_agents_bot_id", "agents", ["bot_id"])

    op.create_table(
        "scans",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("environment_id", sa.Integer(), sa.ForeignKey("environments.id")),
        sa.Column("solution_name", sa.Text()),
        sa.Column("source", sa.Text(), nullable=False, server_default="dataverse"),
        sa.Column("trigger", sa.Text(), nullable=False, server_default="manual"),
        sa.Column("status", sa.Text(), nullable=False, server_default="running"),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("score", sa.Integer()),
        sa.Column("grade", sa.String(length=1)),
        sa.Column("agent_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("engine_version", sa.Text()),
        sa.Column("catalogue_hash", sa.Text()),
        sa.Column("detail", sa.Text()),
    )
    op.create_index("ix_scans_environment_id", "scans", ["environment_id"])

    op.create_table(
        "findings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("scan_id", sa.Integer(), sa.ForeignKey("scans.id"), nullable=False),
        sa.Column("rule_id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("manual_review", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("weight", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("scope", sa.Text(), nullable=False, server_default="solution"),
        sa.Column("agent_name", sa.Text()),
        sa.Column("details", sa.Text()),
        sa.Column("pp_reference", sa.Text()),
    )
    op.create_index("ix_findings_scan_id", "findings", ["scan_id"])
    op.create_index("ix_findings_rule_id", "findings", ["rule_id"])
    op.create_index("ix_findings_agent_name", "findings", ["agent_name"])

    op.create_table(
        "judge_results",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("scan_id", sa.Integer(), sa.ForeignKey("scans.id"), nullable=False),
        sa.Column("agent_name", sa.Text(), nullable=False),
        sa.Column("clarity", sa.Integer()),
        sa.Column("scope_discipline", sa.Integer()),
        sa.Column("persona_defined", sa.Boolean()),
        sa.Column("orchestrator_pattern_detected", sa.Boolean()),
        sa.Column("child_pattern_detected", sa.Boolean()),
        sa.Column("output_format_guidance", sa.Boolean()),
        sa.Column("top_strengths", postgresql.JSONB()),
        sa.Column("top_weaknesses", postgresql.JSONB()),
        sa.Column("recommended_changes", postgresql.JSONB()),
        sa.Column("summary", sa.Text()),
        sa.Column("skipped", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("error", sa.Text()),
    )
    op.create_index("ix_judge_results_scan_id", "judge_results", ["scan_id"])
    op.create_index("ix_judge_results_agent_name", "judge_results", ["agent_name"])

    op.create_table(
        "telemetry_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("scan_id", sa.Integer(), sa.ForeignKey("scans.id"), nullable=False),
        sa.Column("agent_name", sa.Text(), nullable=False),
        sa.Column("window_days", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("run_count", sa.Integer()),
        sa.Column("error_count", sa.Integer()),
        sa.Column("p95_latency_ms", sa.Float()),
        sa.Column("source", sa.Text()),
        sa.Column("captured_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_telemetry_snapshots_scan_id", "telemetry_snapshots", ["scan_id"])
    op.create_index("ix_telemetry_snapshots_agent_name", "telemetry_snapshots", ["agent_name"])

    op.create_table(
        "job_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("job_name", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.Text(), nullable=False, server_default="running"),
        sa.Column("stats", postgresql.JSONB()),
    )
    op.create_index("ix_job_runs_job_name", "job_runs", ["job_name"])

    op.create_table(
        "app_users",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("username", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False, server_default="viewer"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_app_users_username", "app_users", ["username"], unique=True)


def downgrade() -> None:
    op.drop_table("app_users")
    op.drop_table("job_runs")
    op.drop_table("telemetry_snapshots")
    op.drop_table("judge_results")
    op.drop_table("findings")
    op.drop_table("scans")
    op.drop_table("agents")
    op.drop_table("environments")
    op.drop_table("app_config")
