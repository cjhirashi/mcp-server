"""RESOURCE_VECTORIZE espeja RESOURCE_REGISTRY (spec 003, reapertura — RF-010, D-9).

El comentario del registro prohíbe mantener a mano una lista de "qué se indexa";
`RESOURCE_VECTORIZE` es esa fuente única y debe cubrir todo recurso registrado.
"""
import pytest

# Importar la app construye todos los routers -> puebla ambos registros.
from app import app  # noqa: F401

from routes.career_common import RESOURCE_REGISTRY, RESOURCE_VECTORIZE


@pytest.mark.requisito("RF-010")
def test_vectorize_flag_covers_every_registered_resource():
    missing = set(RESOURCE_REGISTRY) - set(RESOURCE_VECTORIZE)
    assert not missing, f"recursos sin flag vectorize: {sorted(missing)}"


@pytest.mark.requisito("RF-010")
def test_known_vectorize_flags():
    assert RESOURCE_VECTORIZE["operational-methodologies"] is True
    assert RESOURCE_VECTORIZE["competencies"] is True
    # tablas de contenido PDF: el agente las lee de Postgres, no de Qdrant
    assert RESOURCE_VECTORIZE["cv-versions"] is False
    assert RESOURCE_VECTORIZE["pdf-output-templates"] is False
    assert RESOURCE_VECTORIZE["pdf-template-styles"] is False


@pytest.mark.requisito("RF-010")
def test_register_resource_sets_both_maps():
    from routes.career_common import register_resource
    from models.operational_methodology import OperationalMethodology

    register_resource("tmp-probe-res", OperationalMethodology, vectorize=False)
    try:
        assert RESOURCE_REGISTRY["tmp-probe-res"] is OperationalMethodology
        assert RESOURCE_VECTORIZE["tmp-probe-res"] is False
    finally:
        RESOURCE_REGISTRY.pop("tmp-probe-res", None)
        RESOURCE_VECTORIZE.pop("tmp-probe-res", None)
