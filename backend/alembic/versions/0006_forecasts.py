"""forecasts

Revision ID: 0006
Revises: 0005
"""
from alembic import op
import sqlalchemy as sa


revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('forecasts',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('instrument_id', sa.Integer(), nullable=False),
    sa.Column('timeframe', sa.String(length=3), nullable=False),
    sa.Column('method', sa.String(length=40), nullable=False),
    sa.Column('horizon', sa.Integer(), nullable=False),
    sa.Column('based_on_until', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_close', sa.Float(), nullable=True),
    sa.Column('steps', sa.JSON(), nullable=False),
    sa.Column('params', sa.JSON(), nullable=False),
    sa.Column('params_hash', sa.String(length=16), nullable=False),
    sa.Column('algo_version', sa.String(length=20), nullable=False),
    sa.Column('inputs_hash', sa.String(length=64), nullable=False),
    sa.Column('backtest_run_id', sa.Integer(), nullable=True),
    sa.Column('backtest_reason', sa.Text(), nullable=True),
    sa.Column('pattern_levels', sa.JSON(), nullable=False),
    sa.Column('bars_from', sa.DateTime(timezone=True), nullable=True),
    sa.Column('bar_count', sa.Integer(), nullable=False),
    sa.Column('source_ids', sa.JSON(), nullable=False),
    sa.Column('fetched_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('empty_reason', sa.Text(), nullable=True),
    sa.Column('is_demo', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['backtest_run_id'], ['backtest_runs.id'], ),
    sa.ForeignKeyConstraint(['instrument_id'], ['instruments.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('instrument_id', 'timeframe', 'method')
    )
    with op.batch_alter_table('forecasts', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_forecasts_instrument_id'), ['instrument_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('forecasts', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_forecasts_instrument_id'))
    op.drop_table('forecasts')
