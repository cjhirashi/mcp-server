---
titulo: Método del arnés — SDD Anchored (simplificado)
tipo: metodo
estado: approved
fecha: 2026-09-04
---

# Método del arnés — `.harness/`

## §0 · Qué es esto

Este repo trabaja con **Spec-Anchored Development**: la especificación vive versionada
junto al código y **no muere tras el primer commit**. Un cambio de comportamiento
exige actualizar **primero** la spec; el gate (`gate/check.sh`) impide que código y
spec se divorcien.

**Navegación:** lee **sólo la sección que necesitas**, nunca el archivo entero.
- Vas a clasificar una petición → §2 (rúbrica).
- Vas a redactar/tocar una spec → §3 y §4.
- Vas a revisar un gate → §7.
- Dudas de un término → §9.

**Artefactos** (Constitución Art. 12): por proyecto `constitution.md`, `method.md`,
`memory/{state.md,history.md}`, `decisions/ADR-*`. Por feature `specs/NNN-slug/{spec.md,
plan.md, tasks.md}` (+ `contracts/` si aplica). **Nada más.**

---

## §1 · Génesis del proyecto  *(hecha — modo alineación)*

La arquitectura de cjhirashi-career **ya existía**; se **detectó y registró** el
2026-09-04 en `constitution.md` Art. 2 + `ADR-001`. No hay que re-elegirla.

Si en el futuro se arranca un proyecto de cero: el agente **recomienda** el patrón
interno + estilo de despliegue + sustratos que mejor encajan con las necesidades
(con contrapartidas), el **usuario decide**, se registra en la Constitución + un `ADR-`.
Principio permanente: **el agente siempre recomienda la mejor alternativa; el usuario
decide.**

---

## §2 · Rúbrica de decisión (Fase 0) — ¿entra al arnés?

**Se responde SIEMPRE, en voz alta, antes de tocar un archivo** — incluida una
petición que suena a "arregla esto"/"corrige esta falla". Que algo suene urgente o
pequeño no exime de aplicar la rúbrica.

```
¿La corrección exige cambiar una decisión ya tomada en un spec/ADR
 existente (rediseño), no solo el síntoma?                → SÍ → CARRIL SDD.
¿El área tocada NO tiene spec.md que la cubra (sin ancla)
 Y el cambio toca lógica de negocio o un contrato
 (no solo config/infra)?                                  → SÍ → CARRIL SDD
                                                                (spec mínimo primero
                                                                 — ver nota abajo).
¿Cruza servicios, esquema de BD, un endpoint/contrato,
 o toca una capa/frontera nueva?                          → SÍ → CARRIL SDD.
¿Revertir un malentendido costaría > 4 h,
 o el trabajo dura más de una sesión,
 o hay exigencia de auditoría?                            → SÍ → CARRIL SDD.
¿Trivial / bajo riesgo / parche de < 5 min,
 y ninguna de las anteriores aplica?                      → SÍ → PROMPT DIRECTO.
en caso de DUDA                                           → CARRIL SDD.
```

- **Prompt directo:** implementa → `gate/check.sh` → listo. Cero artefactos.
- **Carril SDD:** §3.
- **Área sin ancla (sin `spec.md` que la cubra):** es el estado normal del código
  heredado (Génesis en modo alineación, sin baseline sembrado) — no una licencia para
  saltarse Fase 1. Un spec mínimo (aunque sea de un `RF-` y tres líneas) es más barato
  que un fix que después hay que deshacer.

Regla de oro: **el mínimo rigor que elimina la ambigüedad en este contexto — y en la
duda, el rigor gana.** Frenar en Fase 1 cuesta minutos; deshacer código cuesta sesiones.

---

## §3 · Flujo de 4 fases (carril SDD)

```
[1 Specify] → ⏸ GATE 1 → [2 Plan] → ⏸ GATE 2 → [3 Tasks] → [4 Implement & Validate] → CIERRE
     ▲                                                                │
     └──────────────── Directiva de Pausa (§5) ────────────────────────┘
```

Iterar en Fase 1–2 es **barato**; refactorizar código es caro.

### Fase 1 · Specify — elicitación interactiva con el usuario

La spec **se define con el usuario**, no la redacta el agente en solitario. Bucle
hasta converger:

1. El usuario expone su intención (informal).
2. El agente responde con **tres cosas, no un borrador silencioso**:
   - **Preguntas enfocadas** en tandas cortas, por áreas: dominio · alcance / fuera de
     alcance · actores · datos y contratos de E/S · criterios de aceptación · casos
     límite y errores · no funcionales · seguridad. **Nunca 30 preguntas de golpe.**
   - **Propuestas de mejora** sobre lo que el usuario dijo: mejor formulación (a EARS
     booleano y testeable), un "fuera de alcance" que conviene fijar, un caso límite
     que falta, un antipatrón a evitar.
   - **Buenas prácticas y alternativas** con su porqué (RFC 9457, idempotencia,
     versionado, principios de la Constitución, qué será frontera entre capas).
3. El usuario **decide** cada propuesta (acepta / ajusta / rechaza). El agente
   registra la decisión **y el descarte** (→ `spec.md §6`).
4. El agente refleja el delta de `spec.md` y marca lo abierto como
   `[NEEDS CLARIFICATION: …]`.
5. Se repite hasta: `[NEEDS CLARIFICATION] = 0` · cada `RF-` en EARS booleano · alcance
   y fuera-de-alcance cerrados · **el usuario confirma "así es"**.

El agente **cuestiona y mejora, no transcribe.** Salida: `spec.md` co-definida, con
`covers` borrador en su front-matter.

**`spec.md` — scaffold (6 secciones):**
1. **Contexto del dominio** — problema en una frase; límites y dependencias de infra.
2. **Alcance** — En alcance / **Fuera de alcance** (explícito, evita *feature creep*).
3. **Modelo de datos y contratos de E/S** — inventario de **fronteras** (entrada/salida)
   con su contrato previsto en `contracts/`; esquemas JSON; nulabilidad; errores RFC 9457.
4. **Criterios de aceptación (EARS)** — cada uno un `RF-NNN`, booleano y testeable (§4).
5. **Casos límite y manejo de errores** — fallos parciales, timeouts, límites, reintentos,
   idempotencia; cada uno con su `RF-` (normalmente `SI…ENTONCES`).
6. **Registro de decisiones y descartes** — qué se decidió, por qué, y qué se descartó.
7. *(opcional)* **Requisitos no funcionales** — `RNF-NNN`, medibles.

**⏸ GATE 1** — §7.

### Fase 2 · Plan

`plan.md` traduce cada `RF-` al patrón **por capas** (Art. 1), de forma concreta:
- Modelo/repositorio, servicio, ruta/endpoint, frontend afectados.
- **Fronteras de salida** (repos, cliente Bedrock, cliente MCP, otro servicio) con su
  implementación concreta.
- Contratos: qué archivos en `contracts/` y qué gates de CI aplican.
- Estrategia de pruebas **por capa**.
- Secuenciación: **tests antes que código**.
- Una sección `### Implementación de RF-NNN` por cada `RF-`.
- **§ Impacto en documentación** *(obligatorio, Art. 11):* qué documentos del mapa
  vuelve obsoletos esta feature y cómo se actualizan → una fila = una tarea `[doc]`.
  Si no toca doc: declararlo explícito.
- Fija `covers` (front-matter de `spec.md`): globs de archivos que la feature poseerá
  — código, tests **y rutas de doc**.

**⏸ GATE 2** — §7.

### Fase 3 · Tasks

`tasks.md`: tareas atómicas (≤ 30 min), ordenadas por dependencia, **test antes que
código**, cada una `(cubre RF-NNN)` + su capa (o `[doc]`). Al final, la **tabla de
cobertura** — que **es** la trazabilidad de la feature:

```
## Cobertura (el gate exige 100 %; `Estado` lo rellena el gate)
| RF / doc | Tareas | Test(s) | Estado |
|---|---|---|---|
| RF-001 | T-001, T-002 | test_rf_001_* | Pass |
| doc: 05-building-block-view | T-010 | — | hecho |
```

Chequeo automático: 100 % de `RF-`/`RNF-` con ≥ 1 tarea; cada fila de `plan.md
§Impacto` con su tarea `[doc]`.

### Fase 4 · Implement & Validate

Ciclo **TDD, una tarea a la vez**: escribe el test (debe fallar) → código mínimo →
refactor. La IA **no se autoaprueba**.

Tras cada tarea: `gate/check.sh` (§6). El verificador es **adversarial**: su meta es
**demostrar que la tarea está mal** (aserción débil, cobertura baja, contrato roto,
spec no sincronizado, parche). Evidencia = **salida de terminal pegada**.

### Cierre (Session-End)

- `gate/check.sh` verde · `anchor_commit` (front-matter de `spec.md`) movido al commit
  de cierre · tabla de cobertura al día · docs del proyecto sincronizadas.
- Entrada **Session-End** en `memory/history.md` (formato fijo, §10).
- `memory/state.md` reescrito (correcciones arriba, backlog, próximo paso).
- `estado:` de `spec.md`/`plan.md` → `implemented`/`verified`.
- **Aprobación humana** del PR.

---

## §4 · EARS — sintaxis de los criterios de aceptación

Forma genérica (orden fijo): `MIENTRAS <estado>, CUANDO <disparador>, el <sistema>
DEBE <respuesta>`. 0..N precondiciones · 0..1 disparador · 1 sistema · 1..N respuestas.

| Patrón | Plantilla |
|---|---|
| Ubicuo | `El sistema DEBE <respuesta>.` |
| Estado | `MIENTRAS <estado>, el sistema DEBE <respuesta>.` |
| Evento | `CUANDO <disparador>, el sistema DEBE <respuesta>.` |
| Opción | `DONDE <característica presente>, el sistema DEBE <respuesta>.` |
| No deseado | `SI <fallo/condición> ENTONCES el sistema DEBE <respuesta>.` |
| Complejo | combinación de los anteriores. |

Reglas: un `RF-` = un `DEBE` (o `NO DEBE`). Respuesta **observable y booleana**. Sin
"y/o", "etc.", "según corresponda", "rápido", "amigable". Es un **requisito** (qué /
por qué), **no** pseudocódigo (cómo). Varios disparadores → parte en varios `RF-`.

---

## §5 · Reglas transversales

- **Solución de raíz, nunca parche** (Constitución Art. 10). Lo diferido va como
  `RF-`/`ADR-` explícito, no como código que se queda.
- **Documentación del proyecto sincronizada** (Art. 11): se planifica en Fase 2, se
  ejecuta como tareas `[doc]`, el gate falla si el *diff* toca superficie observable
  (endpoints, CLI, env, puertos, esquema) sin tocar su documento del mapa.
- **Directiva de Pausa:** si en Fase 4 una asunción de `spec.md`/`plan.md` resulta
  **inviable**: (1) detén el código; (2) edita `spec.md`/`plan.md` con la restricción
  real **y la solución de raíz**; (3) revisión humana por *git diff*; (4) sólo tras
  aprobación, regenera las tareas afectadas y reanuda. **Prohibido el parche silencioso.**
- **El agente siempre recomienda la mejor alternativa; el usuario decide.**
- **Estado en disco, no en el chat.**

---

## §6 · La compuerta — `gate/check.sh`

Compuerta **ejecutable local** (no CI). Se corre al cerrar cada tarea y antes de
`verified`. `exit 0` abierta · `exit 1` cerrada → nada pasa a `verified`.

**Bloques fijos:**
1. **Integridad** — archivos del arnés presentes · herramientas (git, python3, node) · git.
2. **Trazabilidad** — por cada `spec.md` en `implemented`/`verified`: la tabla de
   cobertura de su `tasks.md` completa (todo `RF-` con ≥1 tarea y ≥1 test) · sin tests
   sin `RF-` · `covers` ⊇ ∪(archivos citados en `plan.md`).
3. **Anclaje + docs + raíz** — drift de `covers` (archivos cambiados desde
   `anchor_commit` sin tocar la spec) · doc del mapa (Art. 11) no actualizada cuando el
   *diff* toca superficie observable · `TODO`/`FIXME` sin ticket.
4. **Presupuesto** — `memory/state.md` ≤ 200 líneas; aviso si `method.md`/`history.md` se inflan.

**Bloques por perfil de arquitectura** (sólo los sustratos del Art. 2):
- `rest-http` → tests de los servicios Python tocados (`venv_test`); si hay
  `openapi.yaml` committeado: Spectral (lint) + oasdiff (breaking vs `/openapi.json`).
- `mcp` → validación del JSON Schema de las *tools* tocadas.
- Frontends → `vitest run` + `type-check` del subproyecto tocado.

**Política dura anti *rubber stamping*:** cobertura ≥ umbral (Art. 3), 0 hallazgos de
lint de contrato, 0 breaking no versionados, 0 filas de cobertura sin `Pass`, 0 parches.

---

## §7 · Gates 0–4 (checklists de revisión)

### Gate 0 — ¿entra al arnés?
Aplicar la rúbrica (§2). Documentar la decisión en una línea.

### Gate 1 — salida de Specify
**Elicitación:** la spec se co-definió con el usuario · el agente propuso mejoras y
buenas prácticas · los rechazos están en §6 · el usuario dijo **"así es"**.
**Value Captain:** impacto en la experiencia en lenguaje natural · decisiones y
descartes explícitos · alcance/fuera-de-alcance sin zonas grises.
**Tech Lead:** cada criterio en EARS booleano con `RF-` único · §3 lista **todas** las
fronteras con su contrato previsto · errores con RFC 9457 · sin conflicto con la
Constitución · `[NEEDS CLARIFICATION] = 0`.

### Gate 2 — salida de Plan
Conforme al patrón **por capas** · lógica de negocio en `services/`, no en `routes/`
ni componentes · un archivo en `contracts/` por frontera que lo requiera · una sección
`### Implementación de RF-NNN` por cada `RF-` · estrategia de pruebas por capa · **§
Impacto en documentación** completo · `covers` cubre código + tests + doc · aserciones
de seguridad (Art. 5) cubiertas.

### Gate 3 — salida de Tasks *(mayormente automático)*
100 % de `RF-`/`RNF-` en la tabla de cobertura · cada fila de `plan.md §Impacto` con
tarea `[doc]` · tareas ≤ 30 min · orden con test antes que código · `T-NNN` únicos.

### Gate 4 — antes del merge
`gate/check.sh` verde (todos los bloques) · tabla de cobertura sin filas sin `Pass` ·
todo `RF-` con test **anotado** · commits/PR citan los `RF-` · **solución de raíz** (sin
*workarounds*, sin `TODO`/`FIXME` sin ticket) · **docs sincronizadas** (tareas `[doc]`
aplicadas) · Directiva de Pausa (si se usó) con re-aprobación del delta ·
**aprobación humana del PR** · `memory/state.md` y `history.md` actualizados.

---

## §8 · Quién hace qué

No hay manuales de rol aparte. Un mismo agente puede asumir varios roles; el humano es
Value Captain **y** Tech Lead.

| Rol | Hace | No hace |
|---|---|---|
| **Coordinador** | Clasifica (rúbrica), sostiene la puerta humana, consolida `tasks.md`, escribe el Session-End | Código de servicios; marcar `verified` |
| **Autor de spec** | Conduce la elicitación de Fase 1, redacta `spec.md` | Diseño técnico; código |
| **Arquitecto** | `plan.md` conforme al patrón; fija `covers` | Código de implementación |
| **Implementador** | Código + tests, **una tarea a la vez**, TDD. No se autoaprueba | Ampliar el alcance; marcar `done` |
| **Verificador** (adversarial) | Corre el gate y los tests, traza `RF- ↔ test`, busca cómo tumbar la tarea | Editar el código del implementador |

Patrón **CIV** (Coordinator–Implementor–Verifier) como guía **opcional** si se usan
subagentes: el verificador tiene objetivos opuestos al implementador y bloquea el
merge si encuentra inconsistencias.

---

## §9 · Glosario

- **Anchor / `covers`** — globs (en el front-matter de `spec.md`) de los archivos que
  una feature posee. Base de la detección de drift.
- **`anchor_commit`** — último commit al que la spec fue reconciliada.
- **`anchor_mode`** — `advisory` (drift avisa) | `strict` (drift cierra el gate). Nace
  `advisory`; pasa a `strict` al llegar a `implemented`/`verified`.
- **Drift** — el código de `covers` cambió desde `anchor_commit` sin que la spec cambiara.
- **Directiva de Pausa** — protocolo cuando una asunción de la spec resulta inviable (§5).
- **Rúbrica** — el filtro de Fase 0: ¿ceremonia SDD o prompt directo?
- **`RF-` / `RNF-`** — requisito funcional (criterio EARS) / no funcional. Estables.
- **Modo alineación** — reconstruir una `spec.md` BASELINE del código que ya existe.
- **Modo re-anchor** — parchear una spec cuyo código drifteó, sin reconstruirla.
- **Session-End** — la entrada de cierre en `memory/history.md` (formato en §10).

---

## §10 · Eficiencia de tokens (obligatorio)

- **Lee por secciones, no archivos completos.** Cuando el prompt te da una sección
  (`method.md §4`), lee esa.
- **Estado en disco, no en el chat.** El progreso va a `memory/`, no al historial.
- **Retornos de una línea** de los subagentes (referencia a archivo, no volcado).
- **`/clear` entre tareas no relacionadas.** El estado sobrevive en `memory/`.
- **Presupuestos:** `memory/state.md` ≤ 200 líneas; entradas de `history.md` ≤ 200.
- **Un canon por hecho.** No repitas la Constitución ni este método en otros sitios.

### Formato fijo de la entrada Session-End (`memory/history.md`)

Para que el monitoreo del arnés sea barato, **cada** cierre de sesión añade **al
principio** de `history.md` una entrada con esta forma exacta:

```markdown
## [YYYY-MM-DD] <feature o tema> — <resultado>
- **Fase alcanzada:** specify | plan | tasks | implement | verified | (prompt-directo)
- **Rebotes del verificador:** <n>
- **Directiva de Pausa:** no | sí (<qué asunción, cómo se resolvió de raíz>)
- **Drift / re-anchor:** no | sí (<specs afectadas>)
- **Anclas movidas:** <spec → commit> | ninguna
- **Gate:** verde | cerrado por <bloque> (<detalle>)
- **Docs actualizadas:** <lista> | ninguna
- **Decisiones de diseño / límites de integración:** <1-3 líneas>
- **Próximo paso:** <acción concreta>
```
