"""scan progress counter

Revision ID: 0003_scan_progress
Revises: 0002_agent_scores
Create Date: 2026-08-04
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0003_scan_progress"
down_revision: str | None = "0002_agent_scores"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("scans", sa.Column("agents_done", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("scans", "agents_done")
