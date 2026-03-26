# CODEX_BENCHMARK_REFACTOR_PROMPTS

Estos prompts están diseñados para pasárselos a Codex **en secuencia**.  
Están redactados para una migración **greenfield**, sin compatibilidad con `run_batch.py` ni con `experiments.yaml`.

## Cómo usarlos

- Pásalos **uno por uno**, no todos a la vez.
- Exige siempre:
  - cambios pequeños y revisables;
  - repo ejecutable tras cada entrega;
  - tests incluidos;
  - resumen de archivos tocados;
  - lista de riesgos o deuda residual.

---

## Prompt 0 — Kickoff y limpieza de alcance

```text
Quiero refactorizar esta codebase para soportar benchmarks declarativos definidos sólo por YAML, con ejecución, agregación, decisión y reporting en W&B.

Importante:
- El nuevo sistema debe ser greenfield para experimentación.

Objetivo final:
- un benchmark nuevo se define sólo con un YAML;
- existe una CLI nueva y genérica para validate / expand / run / summarize / compare;
- las ablaciones afectan backend y prompts;
- W&B refleja runs y sesiones, pero la fuente de verdad siguen siendo los artefactos locales por run.

Antes de tocar código:
1) inspecciona la arquitectura actual;
2) propone el árbol de archivos nuevo para el sistema de benchmarks;
3) enumera exactamente qué archivos legacy vas a dejar de usar o eliminar;
4) propone un plan por PRs pequeños;
5) no implementes nada todavía hasta devolver ese plan.

Quiero una propuesta concreta, orientada a implementación, no una explicación genérica.
```

---

## Prompt 1 — Crear el runtime experimental y el profile

```text
Implementa la primera capa del refactor: runtime experimental tipado.

Quiero:
- un `RuntimeSettings` tipado;
- un `ExperimentProfile` tipado;
- separación clara entre defaults globales (`config.py`) y overrides por run;
- wiring inicial para que `main.py` pueda construir un profile y pasarlo al runtime;
- ningún acoplamiento a `run_batch.py` ni `experiments.yaml`.

Alcance:
- añade modelos para runtime, capabilities, persistence, oracle, benchmark metadata y world overrides;
- no implementes todavía la CLI nueva de benchmark;
- no implementes todavía aggregation ni W&B de sesión;
- no metas lógica específica de survival/scarcity.

Restricciones:
- mantén el repo ejecutable;
- no rompas la simulación base;
- deja `config.py` como defaults, no como fuente única;
- evita dicts ad hoc: usa dataclasses o modelos tipados coherentes.

Entrega:
1) código;
2) tests unitarios básicos del profile;
3) resumen de archivos modificados;
```

---

## Prompt 2 — Implementar manifest schema, loader y expander

```text
Implementa el sistema declarativo de manifests de benchmark, sin relación con `run_batch.py` ni con `experiments.yaml`.

Quiero:
- un schema YAML nuevo para benchmarks;
- loader;
- validador;
- expansor de matrices `seed_sets × scenarios × arms`;
- naming estable de runs;
- tests.

Propón y usa una estructura tipo:
- `benchmarks/manifests/*.yaml` para YAMLs;
- `simulation/benchmark/schema.py`
- `simulation/benchmark/loader.py`
- `simulation/benchmark/expander.py`

El manifest debe soportar como mínimo:
- benchmark.id / benchmark.version
- defaults
- seed_sets
- scenarios
- arms
- matrix
- metrics
- criteria
- wandb

Restricciones:
- no ejecutes simulaciones todavía;
- no metas lógica específica por benchmark;
- no añadas compatibilidad con el YAML plano antiguo;
- errores de validación claros y legibles.

Entrega:
1) código;
2) ejemplos mínimos de manifest;
3) tests de validación y expansión;
4) ejemplo del JSON expandido esperado para una suite pequeña.
```

---

## Prompt 3 — Inyectar el profile en engine/agent/oracle/world/memory

```text
Conecta `ExperimentProfile` al runtime real.

Quiero que `SimulationEngine`, `Agent`, `Oracle`, `World` y `Memory` usen settings del profile en lugar de depender implícitamente de globals para comportamiento experimental.

Alcance:
- inyecta settings en engine y pásalos a los subsistemas necesarios;
- soporta capabilities toggles a nivel de backend;
- todavía no hace falta la CLI de benchmark;
- todavía no hace falta W&B de sesión.

Debes cubrir como mínimo:
- explicit_planning
- semantic_memory
- innovation
- item_reflection
- social
- teach
- reproduction

Restricciones:
- si una capacidad está desactivada, debe estar bloqueada realmente en backend;
- no hagas aún el ajuste fino del prompt surface, eso va en el siguiente paso;
- mantén comportamiento por defecto equivalente al actual cuando todas las capabilities están activas.

Entrega:
1) código;
2) tests de integración mínimos con MockLLM o doubles;
3) explicación breve de qué paths del runtime ya respetan el profile y cuáles quedan para prompts.
```

---

## Prompt 4 — Añadir `persistence.mode` y `oracle.mode`

```text
Implementa modos explícitos de persistencia y oráculo para benchmarking.

Quiero:
- `persistence.mode = none | oracle | lineage | full`
- `persistence.clean_before_run`
- `oracle.mode = live | frozen | symbolic`
- soporte para `freeze_precedents_path`

Objetivo:
- permitir benchmarks limpios sin reutilizar persistencia;
- permitir comparación entre oráculo live, frozen y symbolic.

Restricciones:
- no dependas del seed como política implícita;
- la limpieza de persistencia debe quedar trazada en metadatos;
- `symbolic` debe rechazar o marcar como no resoluble la novedad abierta, no aprobarla por defecto;
- deja claro en tests la diferencia entre live/frozen/symbolic.

Entrega:
1) código;
2) tests para persistence/oracle modes;
3) cambios en `meta.json` o artefactos para que quede trazado el modo usado;
4) nota breve sobre cualquier edge case que quede pendiente.
```

---

## Prompt 5 — Construir `PromptSurfaceBuilder` capability-aware

```text
Ahora implementa la parte crítica del refactor: prompt surfaces coherentes con las ablaciones.

Quiero un `PromptSurfaceBuilder` o equivalente que ensamble prompts por bloques opcionales, sin duplicar templates enteros por benchmark.

Regla dura:
si una capability cambia lo que el agente puede hacer o ver, el prompt debe cambiar también.

Debes cubrir:
- explicit_planning=false  -> quitar goal/subgoal/plan status
- semantic_memory=false    -> quitar KNOWLEDGE y mantener episódica si aplica
- innovation=false         -> quitar innovate del system prompt y de ejemplos
- item_reflection=false    -> quitar reflect_item_uses
- social=false             -> quitar communicate/give_item/teach y contexto social
- teach=false              -> quitar teach
- reproduction=false       -> quitar reproduce, family y reproduction_hint

Restricciones:
- no dupliques `system.txt` y `decision.txt` en variantes completas;
- usa bloques o placeholders opcionales;
- mantén el estilo actual del proyecto;
- añade snapshot tests o golden tests del prompt renderizado.

Entrega:
1) código;
2) tests snapshot/golden;
3) ejemplos before/after de prompts para al menos planning off, innovation off y social off;
4) lista de placeholders o bloques creados.
```

---

## Prompt 6 — Crear la nueva CLI genérica de benchmark

```text
Implementa la nueva CLI genérica de benchmark, independiente de `main.py` batchs legacy.

Quiero un entrypoint nuevo, por ejemplo `benchmark.py`, con subcomandos:
- validate
- expand
- run
- summarize
- compare

Alcance en esta entrega:
- implementa al menos `validate`, `expand` y `run`;
- `run` debe ejecutar una sesión completa a partir de un manifest y un seed-set;
- debe crear `benchmarks/sessions/<session_id>/expanded_runs.json` y `run_index.csv`;
- debe lanzar runs individuales reutilizando la simulación existente de forma limpia;
- no quiero scripts específicos por benchmark.

Restricciones:
- no metas lógica específica para survival/scarcity;
- `run` debe serializar el profile final de cada run;
- naming de runs estable: `<benchmark>__<scenario>__<arm>__s<seed>`;
- soporta clean runs cuando `persistence.mode=none`.

Entrega:
1) código;
2) tests mínimos del CLI o del runner subyacente;
3) ejemplo de comando real y artefactos generados;
4) resumen de cómo encuentra el `run_id` de cada ejecución.
```

---

## Prompt 7 — Agregación, criterios y reportes locales

```text
Implementa la capa de agregación y decisión local de benchmarks.

Quiero:
- `aggregator.py`
- `decider.py`
- `reporter.py`

La sesión debe poder producir:
- `aggregate.json`
- `criteria.json`
- `summary.md`

Requisitos:
- agregar por scenario, arm y seed_set;
- soportar métricas canónicas y derivadas;
- evaluar criterios tipo baseline-vs-candidate;
- mantener machine-readable artifacts como fuente principal;
- `summary.md` debe ser un renderer de esos artefactos, no una fuente separada de lógica.

Restricciones:
- no metas dependencias pesadas si no hacen falta;
- no muevas la lógica a W&B;
- no metas heurísticas LLM para decidir pass/fail.

Entrega:
1) código;
2) tests sobre fixtures sintéticos;
3) ejemplo de `aggregate.json` y `criteria.json`;
4) lista de métricas derivadas implementadas.
```

---

## Prompt 8 — Integración W&B para runs y sesiones

```text
Integra el nuevo sistema de benchmarks con W&B manteniendo a W&B como observador, no como fuente de verdad.

Quiero:
- que cada run individual suba el `ExperimentProfile` completo a `wandb.config`;
- grouping consistente por benchmark/scenario/arm/session;
- upload de artifacts de sesión (`aggregate.json`, `criteria.json`, `summary.md`);
- posibilidad de desactivar W&B sin romper nada.

Restricciones:
- no cambies la regla de que la verdad está en artefactos locales;
- no dependas de W&B para calcular criterios;
- la sesión debe seguir siendo utilizable sin conexión a W&B.

Entrega:
1) código;
2) tests o smoke checks razonables;
3) ejemplo de config/tags/group que vería W&B;
4) nota breve sobre cómo queda la trazabilidad de prompts y profiles.
```

---

## Prompt 9 — Tests finales, ejemplos y documentación

```text
Cierra el refactor con tests y documentación.

Quiero:
- tests unitarios de schema, expander, runner, aggregator y decider;
- tests de integración con MockLLM para capabilities;
- golden tests de prompt surfaces;
- uno o dos manifests ejemplo reales (`survival_v1.yaml`, opcionalmente `scarcity_v1.yaml`);
- documentación para autorar nuevos benchmarks sólo con YAML;
- eliminar o actualizar documentación que haga referencia al sistema legacy de batchs.

Restricciones:
- la suite rápida debe seguir siendo ejecutable sin modelo real;
- no dejes referencias activas a `run_batch.py` ni `experiments.yaml`;
- los ejemplos no deben requerir scripts Python específicos por benchmark.

Entrega:
1) código y docs;
2) lista de comandos para validar el sistema end-to-end;
3) resumen final de arquitectura;
4) lista de deuda residual o siguientes pasos.
```

---

## Prompt 10 — Revisión final enfocada en limpieza metodológica

```text
Haz una revisión final del refactor ya implementado, centrada en limpieza metodológica para benchmarks.

Quiero que verifiques explícitamente:
- que los toggles cambian backend y prompt surface;
- que `persistence.mode=none` produce runs limpios;
- que `oracle.mode=symbolic` no regala novedad abierta;
- que la CLI nueva no contiene lógica específica de un benchmark concreto;
- que crear un benchmark nuevo sólo requiere un YAML;
- que W&B no es la fuente de verdad para pass/fail.

Devuélveme:
1) lista de hallazgos;
2) bugs o inconsistencias encontradas;
3) fixes concretos propuestos;
4) si hace falta, implementa los fixes y añade tests.
```

---

## Prompt único alternativo, si prefieres un solo disparo

```text
Quiero un refactor greenfield de la capa de experimentación/benchmarking de esta codebase.

Objetivo:
- benchmarks declarativos definidos sólo por YAML;
- nueva CLI genérica `benchmark.py` con validate / expand / run / summarize / compare;
- runtime experimental tipado (`RuntimeSettings`, `ExperimentProfile`);
- capabilities toggles que afecten backend y prompt surface;
- modos explícitos `persistence.mode` y `oracle.mode`;
- agregación por sesión, criterios automáticos y reportes locales;
- integración W&B para runs y sesiones;
- manifests ejemplo;
- tests y docs.

Importante:
- NO quiero compatibilidad con `run_batch.py`.
- NO quiero compatibilidad con el `experiments.yaml` actual.
- Voy a borrar ambos.
- No añadas wrappers, adaptadores ni migración legacy.

Quiero que lo implementes por capas, manteniendo el repo ejecutable en todo momento.

Orden deseado:
1) runtime settings + experiment profile
2) manifest schema + loader + expander
3) inyección en engine/agent/oracle/world/memory
4) persistence + oracle modes
5) PromptSurfaceBuilder capability-aware
6) nueva CLI genérica
7) aggregation + criteria + reports
8) W&B integration
9) tests + docs + example manifests

Restricciones:
- no metas lógica específica de survival/scarcity en el runner;
- no dupliques templates completos por benchmark;
- W&B no es la fuente de verdad;
- los artefactos locales por run siguen mandando;
- small PRs, cambios atómicos, tests en cada paso.

Entrega:
- código completo;
- lista de archivos nuevos;
- lista de archivos eliminados;
- comandos para validar el sistema;
- deuda residual si la hay.
```
