"""create_career_record debe rechazar campos NOT NULL faltantes antes del
flush — si no, Postgres lanza un IntegrityError que deja la sesión en
pending-rollback para el resto del turno (ver agent_loop.py, catch de
tool execution). Regresión real: el agente creó una competencia con
category='Herramientas' pero sin `type` (NOT NULL, columna separada de
category) y la petición siguiente del mismo turno reventó con un
PendingRollbackError genérico que ocultaba la causa."""
from models.competencies import Competency
from repositories.career_repository import CareerRepository
from services.bedrock_service import _invalid_fields_error


def _competency_repo() -> CareerRepository:
    return CareerRepository(Competency, resource_key="competencies")


def test_required_columns_includes_not_null_without_default():
    repo = _competency_repo()
    assert "type" in repo._required_columns
    assert "name" in repo._required_columns


def test_required_columns_excludes_nullable_and_id_fields():
    repo = _competency_repo()
    assert "category" not in repo._required_columns  # nullable=True
    assert "id" not in repo._required_columns
    assert "user_id" not in repo._required_columns


def test_create_rejects_missing_required_field():
    repo = _competency_repo()
    # Reproduce el caso real: category presente, type ausente.
    invalid = _invalid_fields_error(
        repo, {"name": "AWS Bedrock", "category": "Herramientas"}, require_all=True
    )
    assert invalid is not None
    assert "type" in invalid["error"]


def test_create_accepts_when_all_required_fields_present():
    repo = _competency_repo()
    invalid = _invalid_fields_error(
        repo, {"name": "AWS Bedrock", "type": "technical", "category": "Herramientas"}, require_all=True
    )
    assert invalid is None


def test_update_does_not_require_all_fields():
    # Un update parcial (solo category, p.ej. reclasificar) sigue siendo
    # válido: require_all solo aplica a create.
    repo = _competency_repo()
    invalid = _invalid_fields_error(repo, {"category": "Herramientas"})
    assert invalid is None


def test_unknown_field_still_wins_over_missing_required():
    repo = _competency_repo()
    invalid = _invalid_fields_error(repo, {"bogus": "x"}, require_all=True)
    assert invalid is not None
    assert "bogus" in invalid["error"]
    assert "valid_fields" in invalid
