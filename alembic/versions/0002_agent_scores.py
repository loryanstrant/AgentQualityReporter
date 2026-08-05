"""agent scores + finding.agent_score

Revision ID: 0002_agent_scores
Revises: 0001_initial
Create Date: 2026-08-04
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0002_agent_scores"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "agent_scores",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("scan_id", sa.Integer(), sa.ForeignKey("scans.id"), nullable=False),
        sa.Column("environment_id", sa.Integer(), sa.ForeignKey("environments.id")),
        sa.Column("bot_id", sa.Text()),
        sa.Column("agent_name", sa.Text(), nullable=False),
        sa.Column("solution_name", sa.Text()),
        sa.Column("publish_state", sa.Text()),
        sa.Column("score", sa.Integer()),
        sa.Column("grade", sa.String(length=1)),
        sa.Column("captured_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_agent_scores_scan_id", "agent_scores", ["scan_id"])
    op.create_index("ix_agent_scores_environment_id", "agent_scores", ["environment_id"])
    op.create_index("ix_agent_scores_bot_id", "agent_scores", ["bot_id"])
    op.create_index("ix_agent_scores_agent_name", "agent_scores", ["agent_name"])


def downgrade() -> None:
    op.drop_table("agent_scores")
