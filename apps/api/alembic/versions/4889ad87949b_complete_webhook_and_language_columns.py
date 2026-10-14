"""complete webhook and language capability columns

The apps/api lineage was authored before those columns landed in the models, so
`alembic upgrade head` produced a schema the ORM does not match. `init_db()` hid
the gap by ALTER-ing tables at boot; production (DB_AUTOCREATE=false) never did,
so a migrated apps/api database was missing every column below.

Revision ID: 4889ad87949b
Revises: e7150a82b3d1
Create Date: 2026-10-14 13:31:45.105079
"""
from alembic import op
import sqlalchemy as sa
from globaltalk.models import GUID


revision = '4889ad87949b'
down_revision = 'e7150a82b3d1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('language_capabilities', schema=None) as batch_op:
        batch_op.add_column(sa.Column('script', sa.String(length=16), nullable=True))
        batch_op.add_column(sa.Column('rtl', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('translation_status', sa.String(length=16), nullable=True))
        batch_op.add_column(sa.Column('speech_input_status', sa.String(length=16), nullable=True))
        batch_op.add_column(sa.Column('speech_output_status', sa.String(length=16), nullable=True))
        batch_op.add_column(sa.Column('realtime_status', sa.String(length=16), nullable=True))
        batch_op.add_column(sa.Column('document_status', sa.String(length=16), nullable=True))
        batch_op.add_column(sa.Column('wer_benchmark', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('mt_quality_score', sa.Float(), nullable=True))

    with op.batch_alter_table('webhook_deliveries', schema=None) as batch_op:
        batch_op.add_column(sa.Column('endpoint_id', GUID(length=36), nullable=True))
        # NOT NULL on a table that may already hold rows, so the default is server-side.
        batch_op.add_column(sa.Column('payload_json', sa.JSON(), nullable=False,
                                      server_default=sa.text("'{}'")))
        batch_op.add_column(sa.Column('last_status_code', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('next_retry_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.alter_column('webhook_id',
                              existing_type=sa.VARCHAR(length=36),
                              nullable=True)
        batch_op.alter_column('event_type',
                              existing_type=sa.VARCHAR(length=40),
                              type_=sa.String(length=60),
                              existing_nullable=False)
        batch_op.create_index(batch_op.f('ix_webhook_deliveries_endpoint_id'),
                              ['endpoint_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('webhook_deliveries', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_webhook_deliveries_endpoint_id'))
        batch_op.alter_column('event_type',
                              existing_type=sa.String(length=60),
                              type_=sa.VARCHAR(length=40),
                              existing_nullable=False)
        batch_op.alter_column('webhook_id',
                              existing_type=sa.VARCHAR(length=36),
                              nullable=False)
        batch_op.drop_column('next_retry_at')
        batch_op.drop_column('last_status_code')
        batch_op.drop_column('payload_json')
        batch_op.drop_column('endpoint_id')

    with op.batch_alter_table('language_capabilities', schema=None) as batch_op:
        batch_op.drop_column('mt_quality_score')
        batch_op.drop_column('wer_benchmark')
        batch_op.drop_column('document_status')
        batch_op.drop_column('realtime_status')
        batch_op.drop_column('speech_output_status')
        batch_op.drop_column('speech_input_status')
        batch_op.drop_column('translation_status')
        batch_op.drop_column('rtl')
        batch_op.drop_column('script')
