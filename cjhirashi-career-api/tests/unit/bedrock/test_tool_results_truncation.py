"""Truncado por cuota de campos en resultados de tools (control de tokens)."""
import json

from config import settings
from services.bedrock.tool_results import truncate_tool_result


def _len(obj) -> int:
    return len(json.dumps(obj, ensure_ascii=False, default=str))


def test_small_result_passes_through_unchanged():
    result = {"item": {"id": "prj-1", "title": "Corto"}}
    assert truncate_tool_result(result) is result


def test_oversized_record_caps_each_long_field_and_keeps_all_keys(monkeypatch):
    monkeypatch.setattr(settings, "BEDROCK_MAX_TOOL_RESULT_CHARS", 4000)
    item = {
        "id": "prj-43",
        "title": "Proyecto grande",
        "problem": "P" * 4000,
        "architecture": "A" * 4000,
        "notes": "corto",
    }
    out = truncate_tool_result({"item": item})

    assert set(out["item"].keys()) == set(item.keys())
    assert out["item"]["id"] == "prj-43"
    assert out["item"]["notes"] == "corto"
    assert "get_career_record fields=['problem']" in out["item"]["problem"]
    assert "get_career_record fields=['architecture']" in out["item"]["architecture"]
    assert "truncated" not in out
    assert _len(out) <= 4000


def test_isolated_field_gets_the_budget_and_a_terminal_marker(monkeypatch):
    # El modelo ya pidió fields=['content']: un solo campo largo debe recibir
    # casi todo el presupuesto y un marcador que NO invita a repetir la llamada.
    monkeypatch.setattr(settings, "BEDROCK_MAX_TOOL_RESULT_CHARS", 8000)
    out = truncate_tool_result({"item": {"id": "prj-43", "content": "X" * 20000}})

    assert "truncated" not in out
    assert _len(out) <= 8000
    # Recibió una porción grande, no la cuota mínima.
    assert len(out["item"]["content"]) > 6000
    assert "Es todo lo que cabe" in out["item"]["content"]
    assert "fields=[" not in out["item"]["content"]


def test_large_json_field_is_capped_with_marker(monkeypatch):
    monkeypatch.setattr(settings, "BEDROCK_MAX_TOOL_RESULT_CHARS", 3000)
    item = {"id": "prj-7", "results": [{"k": "v" * 200} for _ in range(60)]}
    out = truncate_tool_result({"item": item})

    assert "truncated" not in out
    assert isinstance(out["item"]["results"], str)
    assert out["item"]["results"].startswith("[JSON recortado] ")
    assert _len(out) <= 3000


def test_many_long_fields_still_too_big_fall_back_to_blind_preview(monkeypatch):
    monkeypatch.setattr(settings, "BEDROCK_MAX_TOOL_RESULT_CHARS", 8000)
    item = {"id": "prj-9", **{f"campo_{i}": "Z" * 3000 for i in range(30)}}
    out = truncate_tool_result({"item": item})

    assert out["truncated"] is True
    assert len(out["preview"]) <= 8000
    assert "fields=[...]" in out["message"]


def test_list_shaped_result_is_not_field_capped(monkeypatch):
    monkeypatch.setattr(settings, "BEDROCK_MAX_TOOL_RESULT_CHARS", 500)
    big_list = {"items": [{"id": f"p-{i}", "summary": "S" * 100} for i in range(50)]}
    out = truncate_tool_result(big_list)

    assert out["truncated"] is True
    assert "preview" in out


import pytest


@pytest.mark.requisito("RF-017")
def test_explicit_limit_overrides_global_setting(monkeypatch):
    """Un `limit` explícito manda sobre BEDROCK_MAX_TOOL_RESULT_CHARS."""
    monkeypatch.setattr(settings, "BEDROCK_MAX_TOOL_RESULT_CHARS", 8000)
    big = {"item": {"id": "opm-61", "content": "X" * 15000}}

    # Con el tope global se recorta.
    capped = truncate_tool_result(big)
    assert len(capped["item"]["content"]) < 15000

    # Con un limit de 24000 cabe entero.
    whole = truncate_tool_result(big, limit=24000)
    assert whole["item"]["content"] == "X" * 15000
    assert _len(whole) <= 24000


@pytest.mark.requisito("RF-017")
def test_limit_none_uses_global_setting(monkeypatch):
    monkeypatch.setattr(settings, "BEDROCK_MAX_TOOL_RESULT_CHARS", 3000)
    out = truncate_tool_result({"item": {"id": "p-1", "content": "Y" * 9000}}, limit=None)
    assert _len(out) <= 3000
