"""agent_profile: настройки главного агента

Revision ID: e58c3d1b7a92
Revises: d47b2c9a1f30
Create Date: 2026-08-15 13:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e58c3d1b7a92'
down_revision: Union[str, Sequence[str], None] = 'd47b2c9a1f30'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'agent_profile',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('niche', sa.String(), nullable=True),
        sa.Column('brand_name', sa.String(), nullable=True),
        sa.Column('brand_location', sa.String(), nullable=True),
        sa.Column('goals', sa.Text(), nullable=True),
        sa.Column('audience', sa.Text(), nullable=True),
        sa.Column('style', sa.Text(), nullable=True),
        sa.Column('tone_of_voice', sa.String(), nullable=True),
        sa.Column('platforms', sa.JSON(), nullable=True),
        sa.Column('posts_per_day', sa.Integer(), nullable=True),
        sa.Column('rules', sa.Text(), nullable=True),
        sa.Column('constraints', sa.Text(), nullable=True),
        sa.Column('tasks', sa.Text(), nullable=True),
        sa.Column('strategy', sa.Text(), nullable=True),
        sa.Column('timezone', sa.String(), nullable=True),
        sa.Column('brand_voice', sa.Text(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('agent_profile')
