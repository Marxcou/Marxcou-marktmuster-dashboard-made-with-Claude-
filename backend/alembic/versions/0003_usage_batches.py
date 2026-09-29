"""api usage counters and sentiment batches

Revision ID: 0003
Revises: 0002
"""
from alembic import op
import sqlalchemy as sa


revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('api_usage',
    sa.Column('source_key', sa.String(length=50), nullable=False),
    sa.Column('day', sa.Date(), nullable=False),
    sa.Column('calls', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('source_key', 'day')
    )
    op.create_table('sentiment_batches',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('batch_id', sa.String(length=100), nullable=False),
    sa.Column('status', sa.String(length=15), nullable=False),
    sa.Column('reserved_usd', sa.Float(), nullable=False),
    sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('batch_id')
    )
    op.create_table('sentiment_batch_items',
    sa.Column('batch_id', sa.Integer(), nullable=False),
    sa.Column('cluster_id', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=10), nullable=False),
    sa.ForeignKeyConstraint(['batch_id'], ['sentiment_batches.id'], ),
    sa.ForeignKeyConstraint(['cluster_id'], ['news_clusters.id'], ),
    sa.PrimaryKeyConstraint('batch_id', 'cluster_id')
    )
    with op.batch_alter_table('sentiment_batch_items', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_sentiment_batch_items_cluster_id'), ['cluster_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('sentiment_batch_items', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_sentiment_batch_items_cluster_id'))
    op.drop_table('sentiment_batch_items')
    op.drop_table('sentiment_batches')
    op.drop_table('api_usage')
