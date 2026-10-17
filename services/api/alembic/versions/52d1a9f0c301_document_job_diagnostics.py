"""Persist document-job diagnostics used by translation coverage QA.

Revision ID: 52d1a9f0c301
Revises: 2202ca7dc080
Create Date: 2026-10-17
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "52d1a9f0c301"
down_revision = "2202ca7dc080"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "document_jobs",
        sa.Column("diagnostics_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )


def downgrade() -> None:
    op.drop_column("document_jobs", "diagnostics_json")
