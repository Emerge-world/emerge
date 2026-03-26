# BENCHMARK_REFACTOR_TRACKER

## Objetivo

Refactorizar la codebase para soportar **benchmarks declarativos definidos sólo por YAML**, con ejecución, agregación, decisión y reporting en W&B, **sin depender en absoluto de `run_batch.py` ni del `experiments.yaml` plano**.

La nueva arquitectura debe permitir:

- definir benchmarks como manifests YAML versionables;
- expandir matrices `seed_sets × scenarios × arms`;
- ejecutar runs individuales y sesiones completas;
- agregar métricas por cohorte;
- evaluar criterios de éxito/fracaso automáticamente;
- subir runs y artefactos de sesión a W&B;
- mantener como fuente de verdad los artefactos locales por run (`data/runs/<run_id>/...`).

## Decisiones de alcance

### Sí entra

- Nuevo runtime experimental tipado.
- Nuevo manifest schema.
- Nuevo runner genérico.
- Nuevos artefactos de benchmark y de sesión.
- Prompt surfaces coherentes con cada ablación.
- Integración W&B a nivel de run y de sesión.
- Testing y documentación del nuevo sistema.

### No entra

- Compatibilidad con `run_batch.py`.
- Compatibilidad con el `experiments.yaml` actual.
- Scripts Python específicos por benchmark.
- Lógica hardcodeada para `survival_v1`, `scarcity_v1`, `affordance_v1`, etc., dentro del runner.

## Política de migración

La migración es **greenfield** para experimentación:

- `run_batch.py` se elimina.
- `experiments.yaml` se elimina.
- No debe quedar código nuevo que dependa de ellos, los lea, los adapte o los envuelva.
- El nuevo sistema debe vivir en módulos nuevos, con una CLI nueva y explícita.

## Principios arquitectónicos

1. **Per-run first**  
   Los artefactos canónicos por run siguen siendo la base de todo: `events.jsonl`, `meta.json`, `summary.json`, `timeseries.jsonl`, `ebs.json`, etc.

2. **W&B como observador, no como fuente de verdad**  
   Las decisiones de benchmark se toman leyendo artefactos locales. W&B sólo refleja runs y artefactos de sesión.

3. **Prompt-surface fidelity**  
   Si un toggle cambia lo que el agente puede hacer o lo que ve, el prompt también debe cambiar.

4. **Sin benchmark-specific Python**  
   Crear un benchmark nuevo debe requerir sólo un nuevo YAML.

5. **Small PRs, runnable repo**  
   Cada PR deja el repo en estado ejecutable y con tests verdes.

## Estructura objetivo recomendada

```text
project-root/
├── benchmark.py                         # nueva CLI genérica
├── benchmarks/
│   ├── manifests/
│   │   ├── survival_v1.yaml
│   │   ├── scarcity_v1.yaml
│   │   └── ...
│   └── sessions/
│       └── <session_id>/
│           ├── expanded_runs.json
│           ├── run_index.csv
│           ├── aggregate.json
│           ├── criteria.json
│           └── summary.md
├── simulation/
│   ├── benchmark/
│   │   ├── __init__.py
│   │   ├── models.py
│   │   ├── schema.py
│   │   ├── loader.py
│   │   ├── expander.py
│   │   ├── runner.py
│   │   ├── aggregator.py
│   │   ├── decider.py
│   │   ├── reporter.py
│   │   ├── wandb_session.py
│   │   └── utils.py
│   ├── runtime_settings.py
│   ├── prompt_surface.py
│   └── ...
└── tests/
    ├── test_benchmark_schema.py
    ├── test_benchmark_expander.py
    ├── test_benchmark_runner.py
    ├── test_benchmark_aggregator.py
    ├── test_benchmark_decider.py
    ├── test_prompt_surface.py
    └── ...
```

## Runtime model objetivo

## `RuntimeSettings`

Debe existir una capa tipada de settings por run, separada de `config.py`, con al menos:

- `use_llm: bool`
- `model: str | None`
- `agents: int`
- `ticks: int`
- `seed: int`
- `width: int`
- `height: int`
- `start_hour: int`

### `capabilities`
- `explicit_planning: bool`
- `semantic_memory: bool`
- `innovation: bool`
- `item_reflection: bool`
- `social: bool`
- `teach: bool`
- `reproduction: bool`

### `oracle`
- `mode: live | frozen | symbolic`
- `freeze_precedents_path: str | None`

### `persistence`
- `mode: none | oracle | lineage | full`
- `clean_before_run: bool`

### `benchmark`
- `benchmark_id: str`
- `benchmark_version: str`
- `scenario_id: str`
- `arm_id: str`
- `seed_set: str | None`
- `session_id: str | None`
- `tags: list[str]`

### `world_overrides`
- `initial_resource_scale: float | None`
- `regen_chance_scale: float | None`
- `regen_amount_scale: float | None`
- `world_fixture: str | None`

## Política de prompts

Debe existir un `PromptSurfaceBuilder` o equivalente.

### Regla dura

Si un flag elimina una capacidad o un bloque de estado interno, el prompt no puede seguir mostrándolo.

### Reglas concretas

- `explicit_planning=false`
  - quitar bloques `CURRENT GOAL`, `ACTIVE SUBGOAL`, `PLAN STATUS`;
  - no invocar planner.

- `semantic_memory=false`
  - quitar bloque `KNOWLEDGE`;
  - mantener `RECENT EVENTS` si la memoria episódica sigue activa;
  - no comprimir episódica a semántica.

- `innovation=false`
  - quitar `innovate` de acciones;
  - quitar instrucciones y ejemplos de innovación;
  - bloquear backend.

- `item_reflection=false`
  - quitar `reflect_item_uses`;
  - bloquear backend.

- `social=false`
  - quitar `communicate`, `give_item`, `teach`;
  - quitar `nearby_agents`, `incoming_messages`, `relationships`;
  - bloquear backend social.

- `teach=false`
  - quitar sólo `teach` del prompt y backend.

- `reproduction=false`
  - quitar `reproduce`;
  - quitar `family` y `reproduction_hint`;
  - bloquear backend.

## Manifest schema objetivo

Cada benchmark debe vivir en un YAML independiente, por ejemplo `benchmarks/manifests/survival_v1.yaml`.

### Estructura mínima

```yaml
version: 1

benchmark:
  id: survival_v1
  version: survival_v1
  description: Comparative survival sanity benchmark

defaults:
  runtime:
    agents: 3
    ticks: 300
    width: 15
    height: 15
    start_hour: 8
    use_llm: true
    model: qwen2.5:3b
  persistence:
    mode: none
    clean_before_run: true
  oracle:
    mode: live
  capabilities:
    explicit_planning: true
    semantic_memory: true
    innovation: true
    item_reflection: true
    social: true
    teach: true
    reproduction: true

seed_sets:
  smoke: [11, 22]
  dev: [101, 202, 303, 404, 505]
  eval: [1101, 1202, 1303, 1404, 1505, 1606, 1707, 1808, 1909, 2010]

scenarios:
  default_day: {}
  night_start:
    runtime:
      start_hour: 20
  large_map:
    runtime:
      ticks: 500
      width: 25
      height: 25

arms:
  A0_full: {}
  A1_no_llm:
    runtime:
      use_llm: false
  A2_no_planning:
    capabilities:
      explicit_planning: false
  A3_no_semantic_memory:
    capabilities:
      semantic_memory: false

matrix:
  scenarios: [default_day, night_start, large_map]
  arms: [A0_full, A1_no_llm, A2_no_planning, A3_no_semantic_memory]

metrics:
  primary:
    - summary.agents.survival_rate
    - derived.alive_auc
  secondary:
    - summary.actions.oracle_success_rate
    - summary.actions.parse_fail_rate
    - derived.mean_hunger_last_20pct
    - derived.mean_energy_last_20pct

criteria:
  - id: full_beats_no_llm_survival_rate
    scenario: default_day
    compare: A0_full > A1_no_llm
    metric: summary.agents.survival_rate
    min_delta_abs: 0.15
  - id: full_beats_no_llm_alive_auc
    scenario: default_day
    compare: A0_full > A1_no_llm
    metric: derived.alive_auc
    min_delta_rel: 0.20

wandb:
  enabled: true
  project: emerge
  group_by:
    - benchmark_id
    - scenario_id
    - arm_id
    - session_id
```

## CLI objetivo

Nueva CLI única:

```bash
uv run python benchmark.py validate benchmarks/manifests/survival_v1.yaml
uv run python benchmark.py expand benchmarks/manifests/survival_v1.yaml --seed-set smoke
uv run python benchmark.py run benchmarks/manifests/survival_v1.yaml --seed-set smoke
uv run python benchmark.py summarize benchmarks/manifests/survival_v1.yaml --session <session_id>
uv run python benchmark.py compare benchmarks/manifests/survival_v1.yaml --session <session_id>
```

## Artefactos que deben existir

### Por run
- `data/runs/<run_id>/meta.json`
- `data/runs/<run_id>/events.jsonl`
- `data/runs/<run_id>/metrics/summary.json`
- `data/runs/<run_id>/metrics/timeseries.jsonl`
- `data/runs/<run_id>/metrics/ebs.json` si aplica

### Por sesión
- `benchmarks/sessions/<session_id>/expanded_runs.json`
- `benchmarks/sessions/<session_id>/run_index.csv`
- `benchmarks/sessions/<session_id>/aggregate.json`
- `benchmarks/sessions/<session_id>/criteria.json`
- `benchmarks/sessions/<session_id>/summary.md`

## Backlog de issues

## EPIC 1 — Runtime experimental

### ISSUE 1.1
Introducir `RuntimeSettings` y `ExperimentProfile`.

**Done when**
- existen modelos tipados;
- se pueden construir desde YAML expandido;
- `config.py` queda como defaults, no como fuente única.

### ISSUE 1.2
Inyectar runtime settings en `SimulationEngine`, `Agent`, `Oracle`, `World`, `Memory`.

**Done when**
- el comportamiento depende del profile;
- no quedan lecturas encubiertas de flags experimentales desde globals.

### ISSUE 1.3
Añadir `persistence.mode`.

**Done when**
- soporta `none|oracle|lineage|full`;
- benchmark limpio no reutiliza persistencia previa.

### ISSUE 1.4
Añadir `oracle.mode`.

**Done when**
- soporta `live|frozen|symbolic`;
- existe path de precedentes congelados.

## EPIC 2 — Prompt surfaces coherentes

### ISSUE 2.1
Crear `PromptSurfaceBuilder`.

### ISSUE 2.2
Hacer el system prompt capability-aware.

### ISSUE 2.3
Hacer el decision prompt capability-aware.

### ISSUE 2.4
Separar memoria episódica y semántica en placeholders distintos.

**Done when**
- snapshots de prompts cambian correctamente por profile;
- no aparecen acciones o contextos imposibles.

## EPIC 3 — Manifests declarativos

### ISSUE 3.1
Crear schema v1 de manifests de benchmark.

### ISSUE 3.2
Crear loader + validador.

### ISSUE 3.3
Crear expansor de matriz.

**Done when**
- un benchmark nuevo requiere sólo YAML;
- `validate` y `expand` funcionan sin ejecutar simulación.

## EPIC 4 — Runner genérico

### ISSUE 4.1
Crear `benchmark.py` con `validate|expand|run|summarize|compare`.

### ISSUE 4.2
Generar artefactos de sesión.

### ISSUE 4.3
Gestionar limpieza de persistencia.

**Done when**
- no existe código de benchmark específico por suite.

## EPIC 5 — Agregación y decisión

### ISSUE 5.1
Crear `aggregator.py`.

### ISSUE 5.2
Crear `decider.py`.

### ISSUE 5.3
Crear `reporter.py`.

### ISSUE 5.4
Añadir métricas derivadas mínimas necesarias.

**Done when**
- `aggregate.json`, `criteria.json`, `summary.md` salen de una sesión real.

## EPIC 6 — W&B

### ISSUE 6.1
Subir `ExperimentProfile` completo a `wandb.config`.

### ISSUE 6.2
Agrupar runs por benchmark/scenario/arm/session.

### ISSUE 6.3
Subir artifacts de sesión a W&B.

**Done when**
- W&B refleja la sesión sin sustituir la lógica local de decisión.

## EPIC 7 — Testing

### ISSUE 7.1
Tests de schema y expansión.

### ISSUE 7.2
Integration tests con MockLLM.

### ISSUE 7.3
Golden tests de prompt surface.

### ISSUE 7.4
Golden tests de `aggregate.json` y `criteria.json`.

### ISSUE 7.5
Checks de determinismo para `oracle.mode=frozen|symbolic`.

## Plan de PRs

### PR 1 — `feat(benchmark): runtime settings and profile`
Scope:
- modelos tipados;
- wiring básico en `main.py`;
- sin tocar todavía prompts ni CLI nueva.

### PR 2 — `feat(benchmark): manifest schema, loader and expander`
Scope:
- schema;
- validador;
- expansión de matrices;
- tests.

### PR 3 — `feat(runtime): persistence and oracle modes`
Scope:
- `persistence.mode`;
- `oracle.mode`;
- limpieza de estado persistido;
- tests.

### PR 4 — `feat(prompts): capability-aware prompt surface`
Scope:
- `PromptSurfaceBuilder`;
- placeholders separados;
- limpieza de prompt por flags;
- snapshot tests.

### PR 5 — `feat(benchmark): generic benchmark cli`
Scope:
- `benchmark.py`;
- `validate|expand|run`;
- creación de sesión y `run_index.csv`.

### PR 6 — `feat(benchmark): aggregation and decision artifacts`
Scope:
- agregación;
- criterios;
- reportes locales.

### PR 7 — `feat(wandb): benchmark session integration`
Scope:
- grouping;
- session artifacts;
- configs completos por run.

### PR 8 — `test(benchmark): goldens, integration and docs`
Scope:
- goldens;
- MockLLM integration;
- manifests ejemplo;
- guía de autoría.

## Checklist de supervisión

## Arquitectura
- [ ] Existe `RuntimeSettings`.
- [ ] Existe `ExperimentProfile`.
- [ ] `config.py` no es la única fuente de verdad.
- [ ] `SimulationEngine`, `Agent`, `Oracle`, `World`, `Memory` reciben settings.
- [ ] No queda dependencia de `run_batch.py`.
- [ ] No queda dependencia de `experiments.yaml`.

## Prompts
- [ ] Planning off elimina goal/subgoal/plan status.
- [ ] Semantic memory off elimina `KNOWLEDGE` y mantiene episódica si corresponde.
- [ ] Innovation off elimina `innovate` del sistema y backend.
- [ ] Item reflection off elimina `reflect_item_uses`.
- [ ] Social off elimina acciones sociales y contexto social.
- [ ] Reproduction off elimina `reproduce`, `family`, `reproduction_hint`.
- [ ] Existen snapshot tests de prompts.

## Manifests
- [ ] Hay schema validado.
- [ ] Hay expansión de matriz.
- [ ] Un benchmark nuevo sólo requiere YAML.
- [ ] El naming de runs es estable.

## Reproducibilidad
- [ ] `persistence.mode` funciona.
- [ ] `oracle.mode` funciona.
- [ ] Benchmark limpio no reutiliza precedentes/lineage.
- [ ] `meta.json` guarda profile suficiente para replay.

## Artefactos
- [ ] Existen artefactos de sesión.
- [ ] No se rompe `data/runs/<run_id>/...`.
- [ ] `aggregate.json` y `criteria.json` salen de runs reales.

## W&B
- [ ] Cada run sube config completa.
- [ ] Las sesiones quedan agrupadas correctamente.
- [ ] Los artifacts agregados se suben al final.
- [ ] W&B no es la fuente de verdad para pass/fail.

## Testing
- [ ] Tests de schema.
- [ ] Tests de expander.
- [ ] Tests de runner.
- [ ] Tests de prompt surface.
- [ ] Tests de aggregation/decision.
- [ ] Tests con MockLLM.
- [ ] Suite rápida pasa sin modelos reales.

## Exit criteria globales

El refactor se considera terminado cuando:

1. `run_batch.py` y `experiments.yaml` ya no existen ni son necesarios.
2. Se puede crear `benchmarks/manifests/survival_v1.yaml` y ejecutarlo sin código Python específico.
3. Las ablaciones alteran backend y prompt surface de manera coherente.
4. Se generan artefactos de sesión locales.
5. W&B refleja runs y sesión.
6. La suite de tests del nuevo sistema pasa.
