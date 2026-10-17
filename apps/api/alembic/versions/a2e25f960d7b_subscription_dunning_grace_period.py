"""subscription dunning grace period

Revision ID: a2e25f960d7b
Revises: 6c271b27bbfd
Create Date: 2026-10-17 08:46:23.961716

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a2e25f960d7b'
down_revision: Union[str, None] = '6c271b27bbfd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('subscriptions', sa.Column('past_due_since', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('subscriptions', 'past_due_since')
