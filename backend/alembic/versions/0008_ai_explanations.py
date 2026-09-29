"""ai_explanations: zwischengespeicherte Erklärtexte (KI oder Vorlage)

Revision ID: 0008
Revises: 0007
"""
from alembic import op
import sqlalchemy as sa


revision = '0008'
down_revision = '0007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'ai_explanations',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('subject_kind', sa.String(10), nullable=False),
        sa.Column('subject_id', sa.Integer(), nullable=False),
        sa.Column('input_hash', sa.String(64), nullable=False),
        sa.Column('method', sa.String(10), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('model_name', sa.String(100), nullable=True),
        sa.Column('model_version', sa.String(50), nullable=True),
        sa.Column('cost_usd', sa.Float(), nullable=False, server_default='0'),
        sa.Column('fallback_reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('subject_kind', 'subject_id', 'input_hash'),
    )


def downgrade() -> None:
    op.drop_table('ai_explanations')
