# Contrato — Herramientas por agente y catálogo de tools

Feature 003. Referencia humana de los endpoints nuevos (el gate no ancla OpenAPI todavía).

## GET `/bedrock/agent-profiles/{profile_id}/tools`

Estado de herramientas de un agente.

Respuesta `200`:

```json
{
  "profile_id": "agent_pdf_design",
  "default_tools": ["describe_resource_schema", "delegate_to_specialist", "pdf_style", "pdf_template", "search_knowledge_base"],
  "override_tools": null,
  "effective_tools": ["describe_resource_schema", "delegate_to_specialist", "pdf_style", "pdf_template", "search_knowledge_base"]
}
```

- `override_tools` es `null` cuando no hay override (se usa el default de código).

## PUT `/bedrock/agent-profiles/{profile_id}/tools`

Configura (reemplaza) el set de herramientas. Body:

```json
{ "tool_names": ["pdf_template", "pdf_style"] }
```

- `tool_names: null` restaura el default de código (borra el override).
- Respuesta `200`: mismo shape que el GET (con el override recién guardado).
- `400` si algún nombre no existe en el catálogo de tools.
- `404` si el `profile_id` no corresponde a un agente conocido.

## GET `/bedrock/tools/catalog`

Catálogo read-only de herramientas (integradas + MCP).

```json
{
  "builtin": [{"name": "list_career_record", "description": "…"}],
  "mcp": [{"id": "bct-1", "name": "…", "url": "…", "is_enabled": true, "created_at": "…"}]
}
```

- `builtin` proviene de `services/bedrock/tools.py` (`_RAW_TOOLS`).
- `mcp` proviene de `bedrock_custom_tools`.
- Solo lectura: no hay endpoint de escritura para la definición de una tool.
