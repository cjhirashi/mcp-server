"""feature 002 · RF-004 — la migración que alinea `file_uploads.related_evidence_id`
al modelo ORM (`String(20)`) es DDL puro, sin conversión de datos, y encadena de
forma lineal. Mismo patrón que test_admin_section_migration.py (op mockeado, sin
Postgres real): la aserción es sobre el SQL emitido, no sobre una ejecución real.
"""
import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest

_MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "e1f2a3b4c5d6_fix_file_upload_related_evidence_id_type.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("_mig_e1f2a3b4c5d6", _MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.requisito("RF-004")
def test_revision_chains_linearly():
    mod = _load()
    assert mod.revision == "e1f2a3b4c5d6"
    assert mod.down_revision == "c4d5e6f7a8b9"
    assert mod.branch_labels is None


@pytest.mark.requisito("RF-004")
def test_upgrade_changes_column_to_varchar():
    mod = _load()
    with patch.object(mod, "op") as op:
        mod.upgrade()
    op.execute.assert_called_once()
    sql = op.execute.call_args.args[0].upper()
    assert "FILE_UPLOADS" in sql
    assert "RELATED_EVIDENCE_ID" in sql
    assert "VARCHAR(20)" in sql
    op.drop_column.assert_not_called()
    op.add_column.assert_not_called()


@pytest.mark.requisito("RF-004")
def test_downgrade_reverts_to_integer():
    mod = _load()
    with patch.object(mod, "op") as op:
        mod.downgrade()
    op.execute.assert_called_once()
    sql = op.execute.call_args.args[0].upper()
    assert "FILE_UPLOADS" in sql
    assert "RELATED_EVIDENCE_ID" in sql
    assert "INTEGER" in sql
