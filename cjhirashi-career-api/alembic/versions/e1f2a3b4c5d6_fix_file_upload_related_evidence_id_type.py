"""Alinea ``file_uploads.related_evidence_id`` al modelo ORM (feature 002, RF-004).

``file_uploads`` predate el tracking de Alembic (nunca hubo migración de creación,
ver ``d1e2f3a4b5c6``): la tabla real quedó con ``related_evidence_id INTEGER`` de
cuando el modelo lo declaraba así, pero ``models/file_upload.py`` usa
``Column(String(20))`` desde siempre. El `INSERT` de un `file_uploads` (p.ej. desde
el tool `generate_image`) revienta con `DatatypeMismatchError` al mandar `NULL` con
tipo `VARCHAR` contra una columna `INTEGER`.

DDL puro, sin conversión de datos: 0 filas no-`NULL` en `related_evidence_id` a la
fecha de esta migración (ninguna ruta de código lo escribe). En un entorno nuevo
``init_db`` (``create_all``) ya crea la columna como `VARCHAR(20)` con el modelo
actual — esta migración es solo para reconciliar bases de datos existentes.

Nota de deploy: esto NO corre en ``init_db``; ``alembic upgrade head`` tras rebuild.

Revision ID: e1f2a3b4c5d6
Revises: c4d5e6f7a8b9
Create Date: 2026-09-04
"""
from typing import Sequence, Union

from alembic import op

revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, Sequence[str], None] = "c4d5e6f7a8b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "file_uploads"
_COLUMN = "related_evidence_id"


def upgrade() -> None:
    op.execute(
        f"ALTER TABLE {_TABLE} ALTER COLUMN {_COLUMN} TYPE VARCHAR(20) "
        f"USING {_COLUMN}::varchar(20)"
    )


def downgrade() -> None:
    op.execute(
        f"ALTER TABLE {_TABLE} ALTER COLUMN {_COLUMN} TYPE INTEGER "
        f"USING NULLIF({_COLUMN}, '')::integer"
    )
