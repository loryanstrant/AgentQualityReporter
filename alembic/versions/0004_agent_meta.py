"""agent metadata columns

Revision ID: 0004_agent_meta
Revises: 0003_scan_progress
Create Date: 2026-08-05
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0004_agent_meta"
down_revision: str | None = "0003_scan_progress"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("agents", sa.Column("created_on", sa.DateTime(timezone=True)))
    op.add_column("agents", sa.Column("modified_on", sa.DateTime(timezone=True)))
    op.add_column("agents", sa.Column("created_by_name", sa.Text()))
    op.add_column("agents", sa.Column("created_by_upn", sa.Text()))


def downgrade() -> None:
    op.drop_column("agents", "created_by_upn")
    op.drop_column("agents", "created_by_name")
    op.drop_column("agents", "modified_on")
    op.drop_column("agents", "created_on")
