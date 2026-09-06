# Registro de Decisiones Arquitectónicas (ADR) - cjhirashi-career

**ARCHITECTURE DECISION RECORDS**

[![Document Type](https://img.shields.io/badge/type-architecture-blue)]()
[![Audience](https://img.shields.io/badge/audiencia-arquitectos%20%7C%20developers%20%7C%20stakeholders-informational)]()
[![Estado](https://img.shields.io/badge/estado-diseño%20en%20validación-yellow)]()

---

**Última actualización**: 2026-08-16
**Resumen rápido**: 6 decisiones de diseño identificadas para el nuevo alcance de portafolio · 0 ADR formalizados como archivo individual todavía · las 6 documentadas hoy de forma provisional en [04-SOLUTION-STRATEGY.md](../04-SOLUTION-STRATEGY.md)

---

## 📋 Tabla de Contenidos

- [Cómo Leer Este Documento](#-cómo-leer-este-documento)
- [Qué es un ADR](#-qué-es-un-adr)
- [Cuándo Crear (y Cuándo No) un ADR](#-cuándo-crear-y-cuándo-no-un-adr)
- [Template Estándar](#-template-estándar)
- [Registro de Decisiones](#-registro-de-decisiones)
- [Cómo Crear un Nuevo ADR](#-cómo-crear-un-nuevo-adr)
- [Inmutabilidad y Depreciación](#-inmutabilidad-y-depreciación)

---

## 📖 Cómo Leer Este Documento

Este documento es la sección 9 de la documentación Arc42 y **no es en sí mismo un ADR** — es el marco y el índice bajo el cual se redactan los ADR individuales de este proyecto, uno por archivo, en esta misma carpeta (`docs/09-DECISIONS/`).

Este registro reemplaza por completo el alcance anterior de este proyecto (servidor de generación de documentos vía MCP). Las seis decisiones catalogadas aquí corresponden al **nuevo alcance de portafolio profesional** — tres canales convergentes (Portal Público, Admin Panel, MCP Server), Agent Bedrock como asistente interno, y PostgreSQL centralizado como única fuente de verdad —, ya introducido en [01-INTRODUCTION.md](../01-INTRODUCTION.md) y formalizado como decisiones de alto nivel en [04-SOLUTION-STRATEGY.md — Decisiones Arquitectónicas de Alto Nivel](../04-SOLUTION-STRATEGY.md#-decisiones-arquitectónicas-de-alto-nivel), tal como ese mismo documento advierte explícitamente: *"Ninguna decisión aquí descrita está aún formalizada como Architecture Decision Record; esa formalización es un trabajo pendiente"*. Este documento formaliza ese compromiso: define el template, lista qué decisiones deben convertirse en ADR y en qué orden, y explica cómo hacerlo. Cuando el Arquitecto de Soluciones redacte cada ADR, [04-SOLUTION-STRATEGY.md](../04-SOLUTION-STRATEGY.md) debe actualizarse para enlazar al ADR en lugar de repetir la justificación completa.

**Nota de continuidad**: cualquier ADR formalizado bajo el alcance anterior de este proyecto (generador de documentos) queda implícitamente superado por el rediseño documentado en `01-INTRODUCTION.md` a `08-CROSSCUTTING-CONCEPTS.md`. Como no existía ningún archivo `ADR-XXX-*.md` individual en esta carpeta antes de este rediseño, no hay ADRs previos que depreciar formalmente — este registro comienza en `ADR-001` para el nuevo alcance.

## 📌 Qué es un ADR

Un **Architecture Decision Record (ADR)** es un documento corto e inmutable que registra una decisión arquitectónica importante: qué se decidió, **por qué** (no solo qué), qué alternativas se consideraron y qué consecuencias trae. Su propósito no es documentar el sistema — para eso están las secciones 1 a 8 de este Arc42 — sino preservar el razonamiento detrás de una decisión, para que alguien en el futuro (incluido uno mismo) entienda por qué el sistema es como es y no de otra forma.

## 🚦 Cuándo Crear (y Cuándo No) un ADR

**Crear un ADR cuando:**
- La decisión es arquitectónicamente importante (afecta la estructura, las dependencias o las restricciones del sistema).
- Se consideraron alternativas significativamente distintas antes de decidir.
- El impacto se extiende al mediano o largo plazo del proyecto.
- Es razonable esperar que alguien en el futuro se pregunte "¿por qué hicieron esto así?".

**No crear un ADR para:**
- Decisiones tácticas pequeñas (nombre de una variable, estructura interna de una función).
- Cambios menores de código sin impacto estructural.
- Corrección de bugs rutinaria.

## 📐 Template Estándar

Copiar el siguiente contenido como `ADR-XXX-título-descriptivo.md` dentro de esta misma carpeta (`docs/09-DECISIONS/`):

```markdown
# ADR-[NÚMERO]: [Título Descriptivo]

## Estado

[Propuesto | Aceptado | Deprecado | Rechazado]

## Contexto

[Explicar la situación que requería una decisión. Qué problema teníamos. Por qué fue importante decidir esto. Listar alternativas consideradas brevemente.]

## Decisión

[QUÉ se decidió, de forma clara y concisa]

### Por Qué

[El POR QUÉ es lo importante — explicar las razones detrás de la decisión, por qué fue mejor que las alternativas]

- Razón 1: [Explicación]
- Razón 2: [Explicación]

## Consecuencias

### ✅ Positivas
- [Beneficio 1]
- [Beneficio 2]

### ⚠️ Negativas
- [Costo/Desventaja 1]

### 🤷 Neutras
- [Aspecto que no es ni bueno ni malo]

## Alternativas Consideradas

### Alternativa 1: [Nombre]
[Descripción breve]
- ✅ Pro: [Ventaja]
- ❌ Contra: [Por qué se rechazó]

### Alternativa 2 (ELEGIDA): [Nombre]
[Descripción breve]
- ✅ Pro: [Ventaja principal]

## Referencias

- [Link a PR, commit o documento relacionado]

## Implicaciones

- [ ] [Acción que debe hacerse como consecuencia de esta decisión]

## Seguimiento

[Si esta decisión lleva a otras decisiones, mencionarlas aquí. Ej: "ADR-008 describe cómo se implementa esto en detalle"]

---

**Creado por**: [Nombre]
**Aprobado por**: [Nombre del revisor]
**Fecha de creación**: YYYY-MM-DD
**Última revisión**: YYYY-MM-DD
**Estado de vigencia**: [Vigente | Revisar próximo trimestre | Pendiente implementación]
```

## 🗂️ Registro de Decisiones

Las siguientes seis decisiones ya están **tomadas y en vigor** en el diseño objetivo del sistema (ver [04-SOLUTION-STRATEGY.md — Decisiones Arquitectónicas de Alto Nivel](../04-SOLUTION-STRATEGY.md#-decisiones-arquitectónicas-de-alto-nivel)), pero **ninguna existe todavía como archivo ADR individual** en esta carpeta. La tabla siguiente es el plan de formalización, en el mismo orden en que aparecen en `04-SOLUTION-STRATEGY.md`:

| # | Título | Estado del ADR | Documentado provisionalmente en |
|---|--------|-----------------|----------------------------------|
| 001 | Tres canales independientes (Portal Público + Admin Panel + MCP Server) frente a una arquitectura unificada | 🕓 Pendiente de redactar | [04-SOLUTION-STRATEGY — Decisión 1](../04-SOLUTION-STRATEGY.md#1-tres-canales-independientes-en-lugar-de-uno-único), [01-INTRODUCTION — Diagrama del Sistema](../01-INTRODUCTION.md#-diagrama-del-sistema) |
| 002 | SPA en React para el Admin Panel (CRUD de carrera + panel de métricas + chat con Agent Bedrock) | 🕓 Pendiente de redactar | [04-SOLUTION-STRATEGY — Decisión 2](../04-SOLUTION-STRATEGY.md#2-spa-en-react-para-el-admin-panel), [05-BUILDING-BLOCK-VIEW — Admin Panel Detallado](../05-BUILDING-BLOCK-VIEW.md#-admin-panel-detallado) |
| 003 | PostgreSQL centralizado con nuevas tablas de métricas, eventos y auditoría, en lugar de un almacén de observabilidad dedicado | 🕓 Pendiente de redactar | [04-SOLUTION-STRATEGY — Decisión 3](../04-SOLUTION-STRATEGY.md#3-postgresql-centralizado-con-nuevas-tablas-de-métricas-eventos-y-auditoría), [05-BUILDING-BLOCK-VIEW — Nivel 2 PostgreSQL](../05-BUILDING-BLOCK-VIEW.md#-nivel-2--descomposición-de-postgresql) |
| 004 | API REST como orquestador único — Admin Panel, MCP Server y Portal Público convergen exclusivamente aquí | 🕓 Pendiente de redactar | [04-SOLUTION-STRATEGY — Decisión 4](../04-SOLUTION-STRATEGY.md#4-api-rest-como-orquestador-único), [05-BUILDING-BLOCK-VIEW — Interfaces entre Módulos](../05-BUILDING-BLOCK-VIEW.md#-interfaces-entre-módulos) |
| 005 | Agent Bedrock como asistente interno del Admin Panel, sin puerto ni exposición propia — no es un canal | 🕓 Pendiente de redactar | [04-SOLUTION-STRATEGY — Decisión 5](../04-SOLUTION-STRATEGY.md#5-agent-bedrock-como-asistente-interno-no-como-canal), [01-INTRODUCTION — Componente 4️⃣](../01-INTRODUCTION.md#4️⃣-agent-bedrock-asistente-interno-del-admin-panel) |
| 006 | MCP Server expuesto como canal independiente y autosuficiente para agentes de IA externos | 🕓 Pendiente de redactar | [04-SOLUTION-STRATEGY — Decisión 6](../04-SOLUTION-STRATEGY.md#6-mcp-server-expuesto-para-agentes-externos), [01-INTRODUCTION — Componente 5️⃣](../01-INTRODUCTION.md#5️⃣-mcp-server-canal-independiente-para-agentes-de-ia-externos) |
| 011 | Descubrimiento de vacantes por adaptadores (Indeed vía Adzuna, LinkedIn por URL oficial, sin scraping) | ✅ Aceptado — ver `011-job-discovery-adapters.md` | [011-job-discovery-adapters.md](./011-job-discovery-adapters.md) |
| 012 | Jerarquía de agentes Bedrock en 3 niveles (L1 orquestador, L2 área, L3 tarea; delegación solo hacia abajo) | ✅ Aceptado — ver `012-bedrock-three-level-agents.md` | [012-bedrock-three-level-agents.md](./012-bedrock-three-level-agents.md) |
| 013 | L3 consulta web (`agent_web_search`) y L3 GitHub solo lectura (`agent_github`) | ✅ Aceptado — ver `013-l3-web-and-github-agents.md` | [013-l3-web-and-github-agents.md](./013-l3-web-and-github-agents.md) |
| 015 | Tareas de primer nivel y ejecución autónoma de agentes a `scheduled_at` (scheduler in-process) | ✅ Aceptado — ver `015-scheduled-agent-tasks.md` | [015-scheduled-agent-tasks.md](./015-scheduled-agent-tasks.md) |
| 016 | Subtareas, orquestación por turno (bloqueo) y notificaciones al usuario | ✅ Aceptado — ver `016-task-subtasks-orchestration.md` | [016-task-subtasks-orchestration.md](./016-task-subtasks-orchestration.md) |
| 017 | L2 `agent_settings` — catálogo de agentes, secciones del Admin y prompts globales | ✅ Aceptado — ver `017-l2-agent-settings.md` | [017-l2-agent-settings.md](./017-l2-agent-settings.md) |
| 018 | Registro centralizado de fallas del sistema (`error_reports`) + agente `revisor-fallas` | ✅ Aceptado — ver `018-error-reports-registry.md` | [018-error-reports-registry.md](./018-error-reports-registry.md) |
| 019 | Prompt caching de Bedrock (`cachePoint`) + proyección de campos (`fields`) y truncado por campo | ✅ Aceptado — ver `019-bedrock-prompt-caching.md` | [019-bedrock-prompt-caching.md](./019-bedrock-prompt-caching.md) |
| 020 | Plantilla compartida para las secciones de tabla del Admin (`components/section/`) | ✅ Aceptado — ver `020-admin-section-templates.md` | [020-admin-section-templates.md](./020-admin-section-templates.md) |
| 021 | PK sintético `sec-N` para las secciones del Admin (`system_name` como nombre legible) | ✅ Aceptado — ver `021-admin-sections-synthetic-pk.md` | [021-admin-sections-synthetic-pk.md](./021-admin-sections-synthetic-pk.md) |
| 022 | División del L2 `agent_settings` en `agent_configuration` (metaconfiguración) e `agent_settings` (incidencias + bitácora) | ✅ Aceptado — ver `022-l2-split-configuration-vs-incidents.md` | [022-l2-split-configuration-vs-incidents.md](./022-l2-split-configuration-vs-incidents.md) |
| 023 | Retirar el MCP Server del alcance activo (de tres canales a dos; revisa parcialmente ADR-014) | ✅ Aceptado — ver `023-retirar-mcp-server.md` | [023-retirar-mcp-server.md](./023-retirar-mcp-server.md) |
| 026 | Configuración de agentes desde la App (override de herramientas por agente + catálogo de tools) | ✅ Aceptado — ver `026-configuracion-agentes-app.md` | [026-configuracion-agentes-app.md](./026-configuracion-agentes-app.md) |

**Sobre por qué son exactamente estas seis y no más**: `04-SOLUTION-STRATEGY.md` es hoy la única fuente de decisiones de alto nivel ya tomadas para este alcance; su propia sección de [Trazabilidad hacia ADRs](../04-SOLUTION-STRATEGY.md#-trazabilidad-hacia-adrs) marca como candidatas mínimas la 1, la 3 y la ligada a la 6 (mecanismo de autenticación del MCP Server). Este registro amplía esa lista mínima a las seis decisiones completas porque las seis cumplen los criterios de la sección [Cuándo Crear un ADR](#-cuándo-crear-y-cuándo-no-un-adr): afectan la estructura del sistema, se compararon contra alternativas concretas (ver la tabla comparativa en `04-SOLUTION-STRATEGY.md`), y su impacto es de largo plazo. No se agregan decisiones adicionales especulativas — las preguntas de validación abiertas listadas en [01-INTRODUCTION.md](../01-INTRODUCTION.md#-preguntas-de-validación-abiertas) (por ejemplo, el mecanismo exacto de autenticación del MCP Server) **no son ADRs todavía** porque aún no son decisiones tomadas; se convertirán en un séptimo ADR (o más) una vez resueltas.

Cuando cualquiera de estas seis decisiones se formalice, el archivo resultante se debe agregar a esta tabla (columna "Estado del ADR" pasa a "✅ Aceptado — ver `ADR-XXX-título.md`") y enlazarse como archivo real en esta carpeta.

## 🆕 Cómo Crear un Nuevo ADR

1. Confirmar que la decisión cumple los criterios de la sección [Cuándo Crear un ADR](#-cuándo-crear-y-cuándo-no-un-adr).
2. Copiar el [Template Estándar](#-template-estándar) a un archivo nuevo: `ADR-XXX-título-descriptivo.md`, dentro de `docs/09-DECISIONS/`.
3. Usar el siguiente número secuencial disponible — nunca reutilizar un número, incluso si un ADR anterior fue rechazado.
4. Redactar enfatizando el **por qué**, no el qué — el qué ya suele estar documentado en las secciones 1-8 de este Arc42.
5. Agregar la fila correspondiente a la tabla de [Registro de Decisiones](#-registro-de-decisiones) de este README, con el estado real (`Propuesto`, `Aceptado`, etc.).
6. Si el ADR reemplaza una decisión ya documentada en [04-SOLUTION-STRATEGY.md](../04-SOLUTION-STRATEGY.md), actualizar ese documento para enlazar al ADR en vez de repetir la justificación.

## 🔒 Inmutabilidad y Depreciación

- **Un ADR aceptado no se edita.** Si la decisión cambia, se crea un **nuevo ADR** con el siguiente número secuencial que referencia y deprecia al anterior (campo `Seguimiento` del template).
- El ADR depreciado **permanece en el repositorio** con su estado actualizado a `Deprecado` y una referencia al ADR que lo reemplaza — no se elimina, porque sigue explicando por qué se tomó esa decisión en su momento.
- La numeración es secuencial y global para todo el proyecto — no se reinicia por categoría ni por módulo, y no se reutiliza aunque el rediseño de alcance haya dejado sin ADRs previos que continuar.

---

**Relacionado**: [01-INTRODUCTION.md](../01-INTRODUCTION.md) · [02-ARCHITECTURE-GOALS.md](../02-ARCHITECTURE-GOALS.md) · [04-SOLUTION-STRATEGY.md](../04-SOLUTION-STRATEGY.md) · [10-QUALITY-SCENARIOS.md](../10-QUALITY-SCENARIOS.md) · [11-TECHNICAL-RISKS.md](../11-TECHNICAL-RISKS.md) · [CLAUDE.md](../../CLAUDE.md)
**Contacto**: Carlos Jiménez Hirashi (cjhirashi@gmail.com)
