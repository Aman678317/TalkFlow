"""add user identities

Revision ID: e7150a82b3d1
Revises: d6049c5192e5
Create Date: 2026-10-04 22:20:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from globaltalk.models import GUID


revision = 'e7150a82b3d1'
down_revision = 'd6049c5192e5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'user_identities',
        sa.Column('id', GUID(length=36), nullable=False),
        sa.Column('user_id', GUID(length=36), nullable=False),
        sa.Column('provider', sa.String(length=32), nullable=False),
        sa.Column('provider_user_id', sa.String(length=255), nullable=False),
        sa.Column('email', sa.String(length=320), nullable=True),
        sa.Column('email_verified', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('profile_data', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('provider', 'provider_user_id', name='uq_provider_user'),
    )
    op.create_index('ix_user_identities_provider', 'user_identities', ['provider'], unique=False)
    op.create_index('ix_user_identities_user_id', 'user_identities', ['user_id'], unique=False)
    op.create_index('ix_user_identities_user_provider', 'user_identities', ['user_id', 'provider'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_user_identities_user_provider', table_name='user_identities')
    op.drop_index('ix_user_identities_user_id', table_name='user_identities')
    op.drop_index('ix_user_identities_provider', table_name='user_identities')
    op.drop_table('user_identities')

