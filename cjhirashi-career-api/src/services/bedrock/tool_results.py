"""
Truncado de resultados de tools — control de tokens de entrada.

Ver docs/BEDROCK-SYSTEM.md § costos.

Estrategia (dos pasos) para un registro único (`{"item": {...}}`):
1. Se reparte el presupuesto de caracteres disponible entre los campos "largos"
   del registro y se recorta cada uno a esa cuota, dejando un marcador. Así el
   modelo ve la forma completa del registro (todas las claves) y sabe qué campo
   pedir con `get_career_record fields=[...]`. Si el modelo ya aisló un único
   campo y este sigue sin caber, el marcador se lo dice explícitamente ("esto es
   todo lo que cabe") para que no repita la llamada.
2. Si la forma no es un registro único (listas, otras tools), se cae al recorte
   ciego histórico: `{truncated, preview, message}`.
"""
import json
from typing import Any, Dict, Optional

from config import settings

# Un campo string/JSON por encima de esto es candidato a recorte por cuota.
_LONG_FIELD_THRESHOLD = 400
# Cuota mínima garantizada por campo largo, aunque el presupuesto sea escaso.
_PER_FIELD_FLOOR = 600
# Holgura reservada para el marcador que se añade a cada campo recortado.
_MARKER_RESERVE = 140


def _serialize_len(obj: Any) -> int:
    return len(json.dumps(obj, ensure_ascii=False, default=str))


def _as_text(value: Any) -> Optional[str]:
    """Texto medible de un valor de campo, o None si es un escalar corto sin interés."""
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, default=str)
    return None


def _cap_record_fields(result: Dict[str, Any], limit: int) -> Optional[Dict[str, Any]]:
    """Recorta por cuota los campos largos de un `{"item": {campo: valor}}`.

    La cuota por campo se calcula a partir del espacio que queda tras descontar
    el andamiaje JSON y los campos cortos, repartido entre los campos largos —
    así, cuando el modelo pide un solo campo con `fields=[...]`, ese campo recibe
    casi todo el presupuesto. Devuelve un dict nuevo con TODAS las claves, o None
    si la forma no encaja (no es un registro único)."""
    item = result.get("item")
    if not isinstance(result, dict) or not isinstance(item, dict):
        return None

    texts = {k: _as_text(v) for k, v in item.items()}
    long_keys = [k for k, t in texts.items() if t is not None and len(t) > _LONG_FIELD_THRESHOLD]
    if not long_keys:
        return None  # nada recortable por campo → que decida el recorte ciego

    # Presupuesto: límite − andamiaje (claves vacías) − campos cortos − reserva de marcadores.
    scaffold = _serialize_len({**result, "item": {k: "" for k in item}})
    short_len = sum(len(t) for k, t in texts.items() if t is not None and k not in long_keys)
    budget = limit - scaffold - short_len - _MARKER_RESERVE * len(long_keys)
    per_field = max(_PER_FIELD_FLOOR, budget // len(long_keys)) if budget > 0 else _PER_FIELD_FLOOR

    isolated = len(long_keys) == 1

    def _build(quota: int) -> Dict[str, Any]:
        capped: Dict[str, Any] = {}
        for key, value in item.items():
            text = texts[key]
            if key not in long_keys or text is None or len(text) <= quota:
                capped[key] = value
                continue
            hidden = len(text) - quota
            prefix = "" if isinstance(value, str) else "[JSON recortado] "
            if isolated:
                note = f"…[+{hidden} caracteres. Es todo lo que cabe en un resultado de tool para este campo.]"
            else:
                note = f"…[+{hidden} caracteres — pídelo aislado: get_career_record fields=['{key}']]"
            capped[key] = prefix + text[:quota] + note
        return {**result, "item": capped}

    # El coste real es sobre el JSON serializado (los escapes de \" y \n inflan
    # los campos tipo JSON). Ajusta la cuota hacia abajo hasta que quepa.
    capped_item = _build(per_field)
    for _ in range(4):
        if _serialize_len(capped_item) <= limit or per_field <= _PER_FIELD_FLOOR:
            break
        per_field = max(_PER_FIELD_FLOOR, int(per_field * 0.7))
        capped_item = _build(per_field)
    return capped_item


def truncate_tool_result(result: Dict[str, Any], limit: Optional[int] = None) -> Dict[str, Any]:
    """Serializa y trunca si supera `limit` (por defecto
    `BEDROCK_MAX_TOOL_RESULT_CHARS`). El caller pasa un `limit` propio para
    lecturas que valen su coste — p.ej. una metodología entera
    (`BEDROCK_MAX_METHODOLOGY_RESULT_CHARS`, spec 003 Bloque J)."""
    if limit is None:
        limit = settings.BEDROCK_MAX_TOOL_RESULT_CHARS
    if _serialize_len(result) <= limit:
        return result

    # Paso 1: recorte por cuota de campos (solo registros únicos).
    capped = _cap_record_fields(result, limit)
    if capped is not None:
        if _serialize_len(capped) <= limit:
            return capped
        result = capped  # sigue grande: el recorte ciego opera sobre la versión ya reducida

    # Paso 2: recorte ciego histórico.
    text = json.dumps(result, ensure_ascii=False, default=str)
    return {
        "truncated": True,
        "preview": text[: limit - 80],
        "message": (
            f"Resultado truncado a {limit} caracteres. Usa filtros más específicos "
            f"o pide campos concretos con get_career_record fields=[...]."
        ),
    }
