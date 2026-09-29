"""forecasts.example_paths: Beispielpfade der Simulation neben dem Korridor

Revision ID: 0009
Revises: 0008
"""
from alembic import op
import sqlalchemy as sa


revision = '0009'
down_revision = '0008'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('forecasts') as batch:
        batch.add_column(sa.Column('example_paths', sa.JSON(), nullable=False, server_default='[]'))


def downgrade() -> None:
    with op.batch_alter_table('forecasts') as batch:
        batch.drop_column('example_paths')
