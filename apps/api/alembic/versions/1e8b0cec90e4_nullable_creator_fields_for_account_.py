"""nullable creator fields for account deletion

Revision ID: 1e8b0cec90e4
Revises: a2e25f960d7b
Create Date: 2026-10-18 00:41:45.248766

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '1e8b0cec90e4'
down_revision: Union[str, None] = 'a2e25f960d7b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Each entry: (table, column, old-FK-action-is-nullable-already).
# audit_logs.actor_user_id was already nullable — only its FK action changes.
_TABLES = [
    ("ai_conversations", "created_by_user_id", True),
    ("analysis_runs", "created_by_user_id", True),
    ("audit_logs", "actor_user_id", False),
    ("dashboard_comments", "author_user_id", True),
    ("dashboards", "created_by_user_id", True),
    ("dataset_versions", "created_by_user_id", True),
    ("datasets", "created_by_user_id", True),
    ("reports", "generated_by_user_id", True),
    ("saved_scenarios", "created_by_user_id", True),
    ("scheduled_reports", "created_by_user_id", True),
    ("transformations", "performed_by_user_id", True),
    ("webhook_subscriptions", "created_by_user_id", True),
]

# Real Postgres names a FK constraint automatically as
# "<table>_<column>_fkey" when SQLAlchemy doesn't give it an explicit
# name, so drop_constraint can reference that name directly there. Real
# SQLite stores FK constraints completely unnamed (confirmed by reading
# a real local dev.db's own `sqlite_master` DDL directly), so
# batch_alter_table needs a naming_convention to assign the *same*
# deterministic name to that anonymous constraint during reflection
# before drop_constraint can target it — the officially documented
# Alembic pattern for altering an unnamed SQLite constraint. Using one
# convention that happens to match Postgres's own default naming keeps
# the one hardcoded name list above correct for both dialects.
_NAMING_CONVENTION = {"fk": "%(table_name)s_%(column_0_name)s_fkey"}


def upgrade() -> None:
    # batch_alter_table (not op.alter_column/op.drop_constraint directly):
    # SQLite can't ALTER a constraint in place — Alembic's SQLite dialect
    # requires the "create new table, copy data, swap in" batch-mode
    # strategy instead. Postgres supports direct ALTER fine, and batch
    # mode still produces correct, efficient DDL there too, so this one
    # code path works for both — proven by actually running this
    # migration (not just the test suite's Base.metadata.create_all,
    # which builds the schema directly from current models and bypasses
    # Alembic/this migration file entirely) against both a real local
    # SQLite dev.db and a real local Postgres instance.
    for table, column, make_nullable in _TABLES:
        fk_name = f"{table}_{column}_fkey"
        with op.batch_alter_table(table, naming_convention=_NAMING_CONVENTION) as batch_op:
            if make_nullable:
                batch_op.alter_column(column, existing_type=sa.VARCHAR(), nullable=True)
            batch_op.drop_constraint(fk_name, type_="foreignkey")
            batch_op.create_foreign_key(fk_name, "users", [column], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    for table, column, was_nullable in reversed(_TABLES):
        fk_name = f"{table}_{column}_fkey"
        with op.batch_alter_table(table, naming_convention=_NAMING_CONVENTION) as batch_op:
            batch_op.drop_constraint(fk_name, type_="foreignkey")
            batch_op.create_foreign_key(fk_name, "users", [column], ["id"])
            if was_nullable:
                batch_op.alter_column(column, existing_type=sa.VARCHAR(), nullable=False)
