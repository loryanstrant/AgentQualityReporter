"""deep-link ids: environment GUID + owning solution id

Revision ID: 0006_deep_link_ids
Revises: 0005_rule_configs
Create Date: 2026-08-05
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0006_deep_link_ids"
down_revision: str | None = "0005_rule_configs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("environments", sa.Column("environment_guid", sa.Text(), nullable=True))
    op.add_column("agent_scores", sa.Column("solution_id", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("agent_scores", "solution_id")
    op.drop_column("environments", "environment_guid")
