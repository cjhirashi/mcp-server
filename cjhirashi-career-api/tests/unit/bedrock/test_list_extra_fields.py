"""Regresión real: se pidió revisar el campo `level` en 69 competencias.
list_career_record solo devolvía {id, title, summary} — sin forma de pedir
una columna puntual, el agente hizo un get_career_record por registro (69
llamadas), agotó max_round_trips antes de llegar a escribir nada, y el turno
terminó en "Se agotaron las vueltas del agente sin respuesta final." Ni el
fix de nudges ni el de maxTokens ayudan aquí: el cuello de botella es de
lecturas, no de escrituras ni de tokens de salida."""
from models.competencies import Competency
from services.bedrock.tools import converse_tool_specs
from services.bedrock_service import _serialize_list_item


def _competency(**overrides):
    base = dict(id="cmp-1", user_id="usr-1", name="AWS Bedrock", type="technical")
    base.update(overrides)
    return Competency(**base)


def test_list_item_includes_requested_extra_field():
    item = _serialize_list_item(_competency(level="avanzado"), extra_fields=["level"])
    assert item["level"] == "avanzado"


def test_list_item_omits_extra_fields_when_not_requested():
    item = _serialize_list_item(_competency(level="avanzado"))
    assert "level" not in item


def test_list_item_ignores_unknown_extra_field():
    item = _serialize_list_item(_competency(), extra_fields=["not_a_real_column"])
    assert "not_a_real_column" not in item


def test_list_item_keeps_default_compact_shape():
    item = _serialize_list_item(_competency(level="avanzado"), extra_fields=["level"])
    assert item["id"] == "cmp-1"
    assert item["title"] == "AWS Bedrock"
    assert set(item.keys()) == {"id", "title", "level"}


def test_list_career_record_schema_exposes_fields_param():
    specs = converse_tool_specs({"list_career_record"})
    schema = specs[0]["toolSpec"]["inputSchema"]["json"]
    assert "fields" in schema["properties"]
    assert schema["properties"]["fields"]["type"] == "array"
