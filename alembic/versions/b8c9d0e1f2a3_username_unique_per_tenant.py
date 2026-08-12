"""username_unique_per_tenant

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-08-12 05:30:00.000000

Cambia User.username de unico a nivel de TODA la plataforma a unico POR
TENANT -- con muchos tenants distintos, dos negocios tienen que poder tener
cada uno su propio "admin" sin chocar. Ver database/models.py::User.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b8c9d0e1f2a3'
down_revision: Union[str, Sequence[str], None] = 'a7b8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    is_sqlite = bind.dialect.name == "sqlite"

    # El unique constraint/index viejo sobre username solo (global) se
    # llamaba distinto segun el motor -- lo buscamos dinamicamente en vez
    # de asumir un nombre fijo. Todo dentro de un solo batch_alter_table
    # porque SQLite no soporta ALTER de constraints fuera de "batch mode"
    # (copy-and-move de la tabla).
    #
    # Nota SQLite: cuando el unique(username) viejo es anonimo (creado por
    # Field(unique=True) sin nombre explicito), la reflexion de batch mode
    # no lo expone como constraint "nombrado" y no hay forma portable de
    # dropearlo por nombre (limitacion conocida de SQLAlchemy/Alembic). En
    # SQLite ese constraint viejo queda conviviendo -- es un superset mas
    # estricto del nuevo (unique global implica unique por tenant), asi que
    # no rompe nada, solo no habilita el caso de "dos tenants con el mismo
    # username" en una DB de SQLite preexistente (produccion es Postgres,
    # ahi el drop se hace igual porque el constraint SI tiene nombre real).
    old_unique_constraints = [] if is_sqlite else [
        uc['name'] for uc in inspector.get_unique_constraints('user') if uc['column_names'] == ['username']
    ]
    old_unique_indexes = [
        idx['name'] for idx in inspector.get_indexes('user')
        if idx['unique'] and idx['column_names'] == ['username']
    ]
    # El indice viejo no-unico (tenant_id, username) queda reemplazado por
    # el unique constraint nuevo sobre las mismas columnas.
    old_plain_indexes = [
        idx['name'] for idx in inspector.get_indexes('user')
        if not idx['unique'] and idx['column_names'] == ['tenant_id', 'username']
    ]

    with op.batch_alter_table('user', schema=None) as batch_op:
        for name in old_unique_constraints:
            batch_op.drop_constraint(name, type_='unique')
        for name in old_unique_indexes:
            batch_op.drop_index(name)
        for name in old_plain_indexes:
            batch_op.drop_index(name)
        batch_op.create_unique_constraint('uq_user_tenant_username', ['tenant_id', 'username'])


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_constraint('uq_user_tenant_username', type_='unique')
        batch_op.create_index('ix_user_tenant_username', ['tenant_id', 'username'])
        batch_op.create_unique_constraint('uq_user_username', ['username'])
