"""settings_site_config_json

Revision ID: d1e2f3a4b5c6
Revises: d0e1f2a3b4c5
Create Date: 2026-08-23 12:00:00.000000

Agrega Settings.site_config_json (TEXT, nullable) para almacenar la
configuracion completa del storefront como JSON estructurado (SiteConfig).
Cuando es NULL, el renderer genera un default a partir de storefront_template.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d1e2f3a4b5c6"
down_revision: Union[str, None] = "d0e1f2a3b4c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("settings", sa.Column("site_config_json", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("settings", "site_config_json")
