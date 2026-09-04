---
id: ADR-002
tipo: adr
estado: accepted
fecha: 2026-09-04
---

# ADR-002 · Forzar la Fase 1 y el gate automático (corrección de diseño del arnés)

## Contexto y planteamiento del problema

El usuario reportó que, al pedir corregir fallas, el arnés no respetaba el flujo de
Fase 1 (Specify) antes de pasar al rediseño. Investigación (arquitecto de arnés):

1. **No existía `.claude/settings.json`.** El arnés anterior tenía un hook `Stop` que
   corría `init.sh` al cerrar cada turno. Al reestructurar (`ADR-001`) se creó
   `gate/check.sh` pero nunca se recreó el hook — el gate solo corría si el agente
   decidía correrlo.
2. **`CLAUDE.md`/`AGENTS.md` perdieron las "reglas duras" explícitas.** El `CLAUDE.md`
   anterior fijaba un rol por defecto con una regla dura: *"No saltes la fase de spec"*.
   La reescritura al esquema simplificado lo convirtió en un mapa informativo que
   describe el método sin **ordenar** aplicarlo antes de tocar código.
3. **Sin specs BASELINE del código heredado.** La Génesis se hizo en modo alineación
   para detectar la arquitectura, pero nunca se corrió una alineación que sembrara
   `spec.md` del código ya existente. El mecanismo de anclaje/drift no tiene nada
   contra qué comparar en casi todo el repo — un fix ahí es invisible para el gate
   por construcción, no por fallo del gate.
4. **Rúbrica (`method.md §2`) sin una rama para "esto requiere rediseño".** Solo
   preguntaba por tamaño/alcance, nunca por si la corrección revisa una decisión ya
   tomada en un spec/ADR.

## Decisión

1. **`.claude/settings.json`** con hook `Stop` → `bash .harness/gate/check.sh`, igual
   que el arnés anterior (corregido a la ruta nueva).
2. **`CLAUDE.md`** gana una sección "Reglas duras": aplicar la rúbrica siempre, en caso
   de duda ir a carril SDD, prohibido saltar Fase 1 para trabajo no trivial, "sin ancla"
   no es luz verde.
3. **`method.md §2`** gana dos ramas nuevas en la rúbrica: (a) si la corrección exige
   cambiar una decisión ya tomada en spec/ADR → SDD; (b) si el área no tiene `spec.md`
   que la cubra y el cambio toca lógica de negocio/contrato → SDD (spec mínimo antes
   de tocar código). Nuevo desempate: **en caso de duda, SDD.**
4. **Pendiente, no resuelto en este ADR:** correr una pasada de alineación real que
   siembre `spec.md` BASELINE del código existente (empezar por lo que más cambia:
   `api`, `admin`). Sin baseline, la mitigación #3(b) obliga a un spec mínimo cada vez
   que se toca área sin ancla — funciona, pero es más trabajo por feature de lo que
   sería con baseline sembrado una sola vez.

Esta corrección se propaga también a `cjhirashi-srv`, `hira` y al `reference/` del
repo `harness` (es un defecto del esquema, no de este proyecto en particular).

## Opciones consideradas

- **Solo documentar la regla en `memory/state.md`.** Descartada: ya se intentó
  (implícitamente, vía `method.md`) y no bastó — hace falta forzar el comportamiento
  en los archivos que Claude Code carga siempre (`CLAUDE.md`) y un hook que no dependa
  del juicio del agente en el momento.
- **Reintroducir el rol "leader" obligatorio como en el arnés viejo.** Descartada:
  reintroduce la ceremonia de roles que la simplificación quitó a propósito; las
  reglas duras en `CLAUDE.md` logran el mismo efecto sin el andamiaje de roles.

## Consecuencias

- **Buenas:** el gate corre solo, sin depender de que se acuerden de correrlo. La
  rúbrica tiene un desempate explícito y una rama para "esto es en realidad un
  rediseño". Correcciones futuras.
- **Coste:** el hook añade el tiempo de `gate/check.sh --full` de los servicios
  tocados al final de cada turno (antes ya ocurría, solo que manual/opcional).

## Enlaces

- Afecta a: `CLAUDE.md`, `.harness/method.md §2`, `.claude/settings.json` (nuevo).
- Relacionado: `ADR-001` (adopción del esquema simplificado).
