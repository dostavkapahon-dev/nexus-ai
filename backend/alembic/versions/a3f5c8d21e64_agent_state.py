"""agent_state: память агента переживает деплой

Файлы `backend/data/*` живут на эфемерном диске контейнера: деплой возвращал
skills.json и brand_voice.txt к версии из git, а hook_history.json стирал совсем.
Эта таблица делает базу источником правды, файл — рабочей копией.

Revision ID: a3f5c8d21e64
Revises: f92d4e07c1b8
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'a3f5c8d21e64'
down_revision: Union[str, Sequence[str], None] = 'f92d4e07c1b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if sa.inspect(bind).has_table('agent_state'):
        return          # база уже создана из моделей (create_all) — таблица на месте
    op.create_table(
        'agent_state',
        sa.Column('key', sa.String(), nullable=False),
        sa.Column('value', sa.Text(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('key'),
    )


def downgrade() -> None:
    op.drop_table('agent_state')
