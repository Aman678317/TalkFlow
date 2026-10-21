"""§E2 escalation transport: durable agent_escalations table

Revision ID: f4e2a9c1d8b7
Revises: b4e8f1c2d7a9
Create Date: 2026-10-20 00:00:00.000000
"""
from __future__ import annotations

import app.db.base  # noqa: F401
from alembic import op
import sqlalchemy as sa


revision = 'f4e2a9c1d8b7'
down_revision = 'b4e8f1c2d7a9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('agent_escalations',
    sa.Column('org_id', sa.Uuid(), nullable=False),
    sa.Column('ticket_id', sa.String(length=64), nullable=False),
    sa.Column('call_sid', sa.String(length=64), nullable=False),
    sa.Column('reason', sa.String(length=120), nullable=True),
    sa.Column('summary', sa.Text(), nullable=True),
    sa.Column('turns', sa.Integer(), nullable=False),
    sa.Column('claimed_by', sa.String(length=80), nullable=True),
    sa.Column('claimed_at', app.db.base.TZDateTime(timezone=True), nullable=True),
    sa.Column('resolved_by', sa.String(length=80), nullable=True),
    sa.Column('resolved_at', app.db.base.TZDateTime(timezone=True), nullable=True),
    sa.Column('resolution', sa.String(length=120), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', app.db.base.TZDateTime(timezone=True), nullable=False),
    sa.Column('updated_at', app.db.base.TZDateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('call_sid', name='uq_agent_escalation_call'),
    sa.UniqueConstraint('ticket_id', name='uq_agent_escalation_ticket'),
    )
    with op.batch_alter_table('agent_escalations', schema=None) as batch_op:
        batch_op.create_index('ix_agent_escalations_org_id', ['org_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('agent_escalations', schema=None) as batch_op:
        batch_op.drop_index('ix_agent_escalations_org_id')
    op.drop_table('agent_escalations')
