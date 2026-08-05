"""rule configs

Revision ID: 0005_rule_configs
Revises: 0004_agent_meta
Create Date: 2026-08-05
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0005_rule_configs"
down_revision: str | None = "0004_agent_meta"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "rule_configs",
        sa.Column("rule_id", sa.Text(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column("pp_reference", sa.Text()),
        sa.Column("scope", sa.Text()),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("weight", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("explanation", sa.Text()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_by", sa.Text()),
    )


def downgrade() -> None:
    op.drop_table("rule_configs")
