"""connections: created_at and last check meta

Revision ID: d47b2c9a1f30
Revises: c31a5f70e2d1
Create Date: 2026-08-15 12:00:00.000000

Только добавление колонок: старые строки остаются читаемыми как есть, признак
шифрования живёт в самом значении (префикс enc:v1:), поэтому отдельного флага
в схеме не нужно — одна запись не может быть «наполовину зашифрована».
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd47b2c9a1f30'
down_revision: Union[str, Sequence[str], None] = 'c31a5f70e2d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('connections', sa.Column('created_at', sa.DateTime(), nullable=True))
    op.add_column('connections', sa.Column('last_check_at', sa.DateTime(), nullable=True))
    op.add_column('connections', sa.Column('last_check_ok', sa.Boolean(), nullable=True))
    op.add_column('connections', sa.Column('last_check_error', sa.String(), nullable=True))
    # У существующих подключений даты появления нет — берём время последней записи,
    # это ближе к правде, чем пустое поле в интерфейсе.
    op.execute("UPDATE connections SET created_at = updated_at WHERE created_at IS NULL")


def downgrade() -> None:
    op.drop_column('connections', 'last_check_error')
    op.drop_column('connections', 'last_check_ok')
    op.drop_column('connections', 'last_check_at')
    op.drop_column('connections', 'created_at')
