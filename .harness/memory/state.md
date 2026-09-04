---
tipo: memoria
subtipo: state
actualizado: 2026-09-04
---

# Estado del arnés — cjhirashi-career

## ⚠️ Correcciones del usuario (leer SIEMPRE — no borrar)

### [2026-09-04] El arnés no estaba forzando la Fase 1 al pedir "corrige esta falla"
- **Qué pasó:** el usuario reportó que, al pedir corregir fallas, el flujo saltaba
  directo a "arreglar/rediseñar" sin pasar por Specify. Evidencia en este mismo
  archivo: los bugs de sesión/MinIO/imágenes y el retiro del MCP Server se resolvieron
  como "Obstáculos y resolución" con commits directos, sin `spec.md`/`plan.md`/`tasks.md`.
  Causa raíz (`ADR-002`): (1) faltaba `.claude/settings.json` — sin hook `Stop`, el gate
  solo corría si el agente decidía correrlo; (2) `CLAUDE.md` perdió las "reglas duras"
  explícitas que el arnés viejo sí tenía; (3) el código heredado no tiene `spec.md`
  BASELINE (Génesis en alineación nunca sembró uno) — nada que anclar, nada que avise.
- **Corrección:** añadido el hook `Stop` (`.claude/settings.json`), reglas duras en
  `CLAUDE.md`, y dos ramas nuevas en la rúbrica de `method.md §2` (rediseña una decisión
  existente → SDD; área sin ancla + toca negocio/contrato → SDD). Desempate: en duda, SDD.
- **Cómo aplicar:** ante "arregla X"/"corrige X", clasifica con la rúbrica ANTES de
  tocar nada, en voz alta. "Área sin spec.md" no es luz verde — es la señal de que hace
  falta un spec mínimo, no de que se puede saltar Fase 1.

### [2026-09-02] No mezclar documentos del arnés con documentos del proyecto
- **Qué pasó:** se metieron manuales del arnés dentro de `docs/`.
- **Corrección:** `docs/` = producto (arc42, ADRs, diseño). `.harness/` = cómo
  operamos. Al crear un archivo, preguntar cuál de los dos es.
- **Cómo aplicar:** nada del arnés en `docs/`; nada de producto en `.harness/`.

### [2026-09-02] El implementador (sobre todo con modelos flojos) fabrica evidencia
- **Qué pasó:** entregas con "salida esperada y obtenida" en vez de salida ejecutada
  (IDs inventados, resumen de gate falso, conteos de pytest inventados), y tareas
  marcadas hechas con un test en rojo.
- **Corrección:** la evidencia DEBE ser salida de terminal **pegada**, nunca
  "esperada". El verificador re-ejecuta él mismo — no confía en el reporte.
- **Cómo aplicar:** al lanzar al implementador, pásale la evidencia real ya
  capturada; prohíbe explícitamente "salida esperada". Una tarea sin salida real
  se queda `[ ]`.

### [2026-09-02] "FASE X 100%" editando estado no es verificar
- **Qué pasó:** reportes marcaban fases completas actualizando un JSON de estado sin
  arrancar el servicio. `cjhirashi-career-ai` nunca había arrancado pese a estar
  "completo".
- **Cómo aplicar:** `verified` exige arranque real (uvicorn / compose → `GET /health`)
  o endpoint que responde con JWT real. Constitución Art. 3.

### [2026-09-02] La dev DB de Postgres no trackea Alembic del todo
- **Qué pasó:** hay cambios aplicados por `ALTER TABLE` directo.
- **Cómo aplicar:** no asumir que `alembic upgrade head` = estado real del schema.
  Verificar contra la DB. Constitución Art. 4.

## Estado del backlog

- **Génesis en modo alineación completada** (2026-09-04): arquitectura detectada y
  registrada en `constitution.md` Art. 2 + `ADR-001`.
- **[2026-09-04] Feature `001-sidebar-contextual-por-seccion` — `verified` + DESPLEGADA**
  a `main` (`ea94840` la punta; commits `ffac40a` gate api · `6d948f7` feature ·
  `4ec56f8` tests admin/portfolio · `cba8f98d` .claude+gate · `ea94840` migración
  idempotente; `anchor_commit` = `6d948f7`). `main` == `origin/main`. Stack recreado
  (`docker compose build/up` api+admin); `career_db.admin_section_overrides` sin la
  columna `description` (`alembic_version` = `c4d5e6f7a8b9`). Verificado en vivo por
  Caddy: `admin.cjhirashi.com/api/health` 200, `/admin/sections` con el shape nuevo.
  `agent_profile_id` de una sección del Admin = agente **L2** del chat contextual del
  sidebar derecho (selector sólo L2, `NULL` = sin chat); se retiran
  `chat_agent_id()`/`_L3_CHAT_FALLBACK`; `resolve_profile_for_turn` contextual sale del
  catálogo con fallback al orquestador. `sidebar_body` por vista → Markdown. Se elimina
  la columna/override `description` (migración `c4d5e6f7a8b9` — **no** corre en
  `init_db`; `alembic upgrade head` tras rebuild). Sidebar derecho condicional (sin
  chat ni instrucciones → ni panel ni botón). ADR-024. **Pendiente:** merge del PR +
  `alembic upgrade head` en el deploy.
- **[2026-09-04] Mensajes de `caddy.json` — los 4 cerrados (`resuelto`):** MSG-0002
  (API `:8001`→`:8000` en `Dockerfile`+`docker-compose.yml`), MSG-0001 (`net-cjhirashi-career`
  `external` en los 5 contenedores), MSG-0004 (esa red también en postgres/qdrant, luego
  `network-cjhirashi-srv` retirada de los 6 + de `networks:`). Verificado runtime: los 6
  solo en `net-cjhirashi-career`, api resuelve postgres/qdrant/minio, `admin`/`portafolio`/
  `/api/health`/`/api/public/home` 200, `mcp.cjhirashi.com` sin respuesta (host retirado).
- Repo en la rama `recover/pre-section-tables` (commit base 8227848). El backlog del
  arnés anterior **no** se importó: era sobre trabajo posterior a este commit o
  revertido. Las features nuevas las prioriza el humano.
- **[2026-09-04] MCP Server retirado** — `ADR-023`. Decisión del humano: borrar carpeta
  + pedir retiro del host + ADR/docs. Hecho en código: `git rm -r cjhirashi-career-mcp/`;
  fuera de `docker-compose.yml` y `caddy.json → servicios`; contenedor `cjhirashi-career-mcp`
  parado, borrado y sus imágenes eliminadas; CORS sin `:8004` (`.env`, `.env.example`,
  `api/src/config.py`); `AGENTS.md`/`README`/`constitution.md` (Art. 1/2/6 + enmienda)
  actualizados; `ADR-014` revisado; banner de estado en arc42 01/04/05/07/08/10/12.
  **MSG-0003 cerrado (`resuelto`)** por cjhirashi-srv: retiró `hosts.mcp`, regeneró la
  conf de Caddy sin la ruta a `cjhirashi-career-mcp` y sacó el host de DNS_RECORDS
  (la baja del registro A en Cloudflare la hace el operador a mano). `mcp.cjhirashi.com`
  ya no da 502. **Pendiente:** reescritura narrativa completa del arc42 sin el Canal 3
  (tarea de doc aparte, anotada en ADR-023).

## Decisiones tomadas (esta sesión)

- Adoptar el arnés SDD Anchored **simplificado** (repo `harness`). `ADR-001`.
- Patrón interno detectado: **por capas** (no hexagonal).
- **Retirar el MCP Server** del alcance activo (`ADR-023`): coste de mantener > valor;
  nunca implementó tools de carrera, PDF ya está in-process en la API, sin tráfico.

## Obstáculos y resolución

- **[2026-09-04] Compuerta `api`/`admin`/`portfolio` reparada** (fallos
  pre-existentes, no de la feature 001): shim JSONB→SQLite en fixtures, camino
  `TEST_DATABASE_URL` a Postgres desechable, aserción `test_auth` obsoleta,
  lockfile/`react-router-dom` faltantes en `admin`. `api` `309 passed`; `admin`
  `435 passed`; `portfolio` `309 passed`.
- **[2026-09-04] `check.sh` — robustez, commiteado** (`a8891b6f`): `run_py_tests`
  trata `pytest` exit 5 como SKIP (no cierra la compuerta por `cjhirashi-career-ai`
  sin suite); `source gate/project.sh` opcional; `.harness/gate/` excluido de la
  regla de comentarios pendientes sin ticket.

## Próximo paso concreto

- **001 cerrada y desplegada.** No queda nada de 001.
- **[2026-09-04] Hazard investigado y CERRADO (no hubo pérdida de datos):** el usuario
  reportó tablas vacías en `career_db` (alarma de "se perdió información"). Se auditó
  fila por fila (65 tablas). Conclusión: `admin_sections_l1` (54 filas),
  `admin_sections_l2` (0), `admin_sections_l3` (0) y `admin_views` (123 filas) son
  **restos físicos de `origin/develop`** (`babd50f0`/`61783017`, jerarquía L1/L2/L3 +
  vistas, ADR-023 versión abandonada) — esa rama **nunca se fusionó a `main`**
  (`git merge-base --is-ancestor` = false) y reutilizó por colisión el revision ID
  `c4d5e6f7a8b9` que luego también usó el trabajo real de 001
  (`c4d5e6f7a8b9_drop_admin_section_override_description.py`). El código de `main`
  **no referencia estas 4 tablas en ningún punto** (`grep` de `AdminSectionL1/L2/L3`,
  `AdminView` sobre `src/` → cero resultados); el catálogo de secciones vigente vive
  en código (`services/admin_sections.py`) + `admin_section_overrides` (JSONB). Son
  leftovers inertes de un experimento no fusionado, no datos de producto perdidos.
  Resto de tablas en 0 (`applications`, `interviews`, `events`, `metrics`,
  `search_plans`, `linkedin_posts`, `application_interactions`, `bedrock_custom_tools`,
  `bedrock_agent_delegation`, `bedrock_agent_profile_photos`, `refresh_tokens`,
  `user_sessions`) son features de dominio aún sin uso, no regresiones.
  **Decisión del humano (2026-09-04): dejar las tablas huérfanas tal cual, solo
  documentar** — no se borran por ahora. Si se retoma la jerarquía L1/L2/L3 desde
  `develop`, esa migración debe cambiar de revision ID (ya no puede ser
  `c4d5e6f7a8b9`) y usar DDL con `IF [NOT] EXISTS`.
- **Cuidado al desplegar:** `docker compose up -d` puede recrear `api` con un
  `DATABASE_URL` obsoleto — usar `up -d --force-recreate --no-deps api` y verificar
  `docker inspect ... .Config.Env`.
- Aparte de 001: reescribir `cjhirashi-career-api/tests/integration/test_auth_integration.py`
  contra el esquema de rutas actual (hoy `pytest.mark.skip`); `cjhirashi-career-ai`
  sigue sin suite de tests.
- Reescritura narrativa del arc42 sin el Canal 3 (ADR-023 lo deja anotado).
- **[2026-09-04] Feature `002-generacion-imagenes-agente-visual` — CERRADA
  (`verified`).** Commits `a3c322a6` (ADR-002 arnés) · `dc9aab10` (feature, 12
  `RF-`) · `e78904bd` (anchor + verified). Gate `--full`: 24 ok · 0 warn · 0 error.
  Detalle completo en el Session-End de `history.md` y en
  `.harness/specs/002-generacion-imagenes-agente-visual/`.
  **Falsa alarma corregida:** el "403 en `files.cjhirashi.com`" reportado durante
  el cierre **no era un bug** — era Cloudflare bloqueando el User-Agent por
  defecto de `urllib` de Python (`error code: 1010`, "browser signature banned").
  Confirmado con `curl` y con un User-Agent de navegador real: ambos `200`. Las
  imágenes generadas sí cargan para cualquier cliente normal (frontend, curl,
  navegador). No se abre mensaje en `caddy.json` — no había nada que reportar.
- Antes de tocar nada: correr `.harness/gate/check.sh`.
