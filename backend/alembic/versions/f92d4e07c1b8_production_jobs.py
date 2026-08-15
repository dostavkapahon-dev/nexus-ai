"""production_jobs: очередь ТЗ на производство медиа

Revision ID: f92d4e07c1b8
Revises: e58c3d1b7a92
Create Date: 2026-08-15 15:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f92d4e07c1b8'
down_revision: Union[str, Sequence[str], None] = 'e58c3d1b7a92'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'production_jobs',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('kind', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=True),
        sa.Column('brief', sa.JSON(), nullable=True),
        sa.Column('assets', sa.JSON(), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('plan_id', sa.String(), nullable=True),
        sa.Column('task_id', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('taken_at', sa.DateTime(), nullable=True),
        sa.Column('done_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_production_jobs_status'), 'production_jobs', ['status'])
    op.create_index(op.f('ix_production_jobs_task_id'), 'production_jobs', ['task_id'])
    op.create_index(op.f('ix_production_jobs_created_at'), 'production_jobs', ['created_at'])


def downgrade() -> None:
    op.drop_index(op.f('ix_production_jobs_created_at'), table_name='production_jobs')
    op.drop_index(op.f('ix_production_jobs_task_id'), table_name='production_jobs')
    op.drop_index(op.f('ix_production_jobs_status'), table_name='production_jobs')
    op.drop_table('production_jobs')
