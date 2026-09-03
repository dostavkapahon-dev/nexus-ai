"""publications: video_url

Revision ID: c31a5f70e2d1
Revises: 64e59c73f0d2
Create Date: 2026-08-15 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c31a5f70e2d1'
down_revision: Union[str, Sequence[str], None] = '64e59c73f0d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('publications', sa.Column('video_url', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('publications', 'video_url')
