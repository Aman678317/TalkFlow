"""Notes: DeepL-style saved translations table

Revision ID: 7c3ad5e19b42
Revises: f4e2a9c1d8b7
Create Date: 2026-10-24 00:00:00.000000
"""
from __future__ import annotations

import app.db.base  # noqa: F401
from alembic import op
import sqlalchemy as sa


revision = '7c3ad5e19b42'
down_revision = 'f4e2a9c1d8b7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('translation_notes',
    sa.Column('org_id', sa.Uuid(), nullable=True),
    sa.Column('user_id', sa.Uuid(), nullable=True),
    sa.Column('translation_id', sa.Uuid(), nullable=True),
    sa.Column('title', sa.String(length=255), nullable=False),
    sa.Column('source_text', sa.Text(), nullable=False),
    sa.Column('translated_text', sa.Text(), nullable=False),
    sa.Column('source_lang', sa.String(length=16), nullable=False),
    sa.Column('target_lang', sa.String(length=16), nullable=False),
    sa.Column('note', sa.Text(), nullable=False),
    sa.Column('tags_json', sa.JSON(), nullable=False),
    sa.Column('annotations_json', sa.JSON(), nullable=False),
    sa.Column('is_favorite', sa.Boolean(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', app.db.base.TZDateTime(timezone=True), nullable=False),
    sa.Column('updated_at', app.db.base.TZDateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['org_id'], ['organizations.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['translation_id'], ['translation_segments.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('translation_notes', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_translation_notes_is_favorite'), ['is_favorite'], unique=False)
        batch_op.create_index(batch_op.f('ix_translation_notes_org_id'), ['org_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_translation_notes_source_lang'), ['source_lang'], unique=False)
        batch_op.create_index(batch_op.f('ix_translation_notes_target_lang'), ['target_lang'], unique=False)
        batch_op.create_index(batch_op.f('ix_translation_notes_translation_id'), ['translation_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_translation_notes_user_id'), ['user_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('translation_notes', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_translation_notes_user_id'))
        batch_op.drop_index(batch_op.f('ix_translation_notes_translation_id'))
        batch_op.drop_index(batch_op.f('ix_translation_notes_target_lang'))
        batch_op.drop_index(batch_op.f('ix_translation_notes_source_lang'))
        batch_op.drop_index(batch_op.f('ix_translation_notes_org_id'))
        batch_op.drop_index(batch_op.f('ix_translation_notes_is_favorite'))
    op.drop_table('translation_notes')
