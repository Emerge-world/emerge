Lo aterrizaría en dos capas: una **matriz operativa** que puedes correr ya con el CLI real del repo, y una **matriz publicable** que exige añadir unos pocos flags de investigación. Ahora mismo `main.py` deja variar sobre todo `--agents`, `--ticks`, `--seed`, `--no-llm`, `--start-hour`, `--width`, `--height`, `--model` y opciones de logging/W&B; `run_batch.py` sólo soporta `name`, `seed`, `agents`, `ticks`, `model`, `no_llm`, `wandb`, `runs`, `width` y `height`. En cambio, planning, memoria semántica, innovación, socialidad, reproducción, modo de oráculo y persistencia todavía no están expuestos como flags, aunque sí existen como mecanismos en código/config. ([GitHub][1])

## 1) Protocolo fijo para todos los benchmarks

Primero, usaría tres paquetes de seeds emparejadas para todas las condiciones: `smoke = [11, 22]`, `dev = [101, 202, 303, 404, 505]` y `eval = [1101, 1202, 1303, 1404, 1505, 1606, 1707, 1808, 1909, 2010]`. La regla sería simple: cada brazo corre exactamente las mismas seeds. Esto no sale del repo; es mi propuesta para estabilizar comparación y revisión.

Segundo, impondría **runs limpias** por defecto. Hoy el engine carga y guarda automáticamente precedentes y lineage en ficheros asociados al seed, por ejemplo `data/precedents_<seed>.json` y `data/lineage_<seed>.json`. Eso significa que “misma seed” no equivale necesariamente a “misma condición inicial” si ya has corrido antes esa seed. Además, cada run escribe sus artefactos en `data/runs/<run_id>/` con `meta.json`, `events.jsonl` y métricas derivadas al cerrar. Para benchmark limpio, el comportamiento correcto debería ser `--persistence none`; hasta que exista, la disciplina experimental tiene que ser borrar esos dos ficheros antes de cada run de benchmark. ([GitHub][2])

Tercero, normalizaría el nombre de run como
`<benchmark>__<scenario>__<arm>__s<seed>`
por ejemplo
`scarcity_v1__hard__full__s1202`.
Ya tienes `meta.json` y eventos suficientemente ricos para reconstruir contexto, y el emisor incluye metadatos como commit y hashes de prompts, lo que te ayuda mucho de cara a reproducibilidad en paper. ([GitHub][3])

Cuarto, distinguiría tres tipos de métricas: las que ya existen en `summary.json`, las que ya se pueden derivar de `timeseries.jsonl` y `events.jsonl`, y las que requieren un builder nuevo. Hoy ya salen automáticamente `summary.json`, `timeseries.jsonl` y `ebs.json`; en `summary.json` tienes, entre otras, `survival_rate`, `oracle_success_rate`, `parse_fail_rate`, `innovations.approval_rate` y `innovations.realization_rate`, y en `ebs.json` ya tienes novelty, utility, realization, stability, autonomy y longevity. ([GitHub][4])

## 2) Flags de investigación que conviene añadir

Esto ya no es “lo que existe hoy”, sino la capa mínima que yo añadiría para que la matriz sea científica y no una colección de pruebas ad hoc:

* `--persistence {none,oracle,lineage,full}`
* `--oracle-mode {live,frozen,symbolic}`
* `--freeze-precedents <path>`
* `--disable-planning`
* `--disable-semantic-memory`
* `--disallow-innovation`
* `--disallow-item-reflection`
* `--disallow-social`
* `--disallow-teach`
* `--disallow-reproduction`

Y, para escasez, reutilizaría casi tal cual la nomenclatura que ya aparece en tu propia documentación de benchmark:

* `--run-id`
* `--benchmark-id`
* `--benchmark-version`
* `--scenario-id`
* `--candidate-label`
* `--initial-resource-scale`
* `--regen-chance-scale`
* `--regen-amount-scale` ([GitHub][5])

Hay una razón fuerte para no dejar esto implícito: hoy el baseline `--no-llm` sí te da una política muy degradada —el agente cae en fallback simple y el planner no produce plan sin LLM—, pero **no** es un control limpio de innovación, porque en la ruta sin LLM el oráculo puede resolver una custom action desconocida como éxito con coste fijo y cachearla como precedente; además, la validación de innovación trata `approved` como verdadero por defecto si el payload no lo trae. Para claims de paper, necesitas un `symbolic_oracle` o al menos un `frozen_oracle` como control serio. ([GitHub][6])

## 3) Brazos de ablación

Ésta sería mi nomenclatura base:

* `A0_full`: LLM + planning + memoria + innovación + reflexión sobre ítems + social + reproducción, con `persistence=none` para benchmark limpio.
* `A1_no_llm`: coarse baseline de supervivencia.
* `A2_no_planning`: igual que full, pero sin planner explícito.
* `A3_no_semantic_memory`: igual que full, pero sin compresión a memoria semántica.
* `A4_no_innovation`: sin `innovate`.
* `A5_no_item_reflection`: sin `reflect_item_uses`.
* `A6_no_social`: sin `communicate`, `give_item`, `teach`.
* `A6b_no_teach`: deja socialidad básica pero quita enseñanza.
* `A7_no_reproduction`: sin `reproduce`.
* `A8_frozen_oracle`: igual que full, pero oráculo sin expansión online de precedentes.
* `A9_symbolic_oracle`: control duro; sólo física/recetas explícitas, nada de novedad abierta.

La motivación empírica de estas ablaciones sí está ya en el repo: planning explícito está activado por config, la memoria semántica se comprime cada ciertos ticks, `innovate` y `reflect_item_uses` son acciones iniciales, `communicate/give_item/teach` también, y `reproduce` se desbloquea tarde. ([GitHub][7])

## 4) Benchmark 1: `survival_v1` — corre hoy

Éste lo usaría como benchmark de sanidad experimental, no como pieza central del paper. El mundo actual no es tan simple como el README antiguo: el default sigue siendo 15×15, pero ya hay múltiples tiles, recursos por bioma, regeneración al amanecer y costes/bonos energéticos por terreno. Eso basta para un primer benchmark de supervivencia comparativa. ([GitHub][8])

**Escenarios**

* `default_day`: `--agents 3 --ticks 300 --width 15 --height 15 --start-hour 8`
* `night_start`: `--agents 3 --ticks 300 --width 15 --height 15 --start-hour 20`
* `large_map`: `--agents 3 --ticks 500 --width 25 --height 25 --start-hour 8`

**Brazos**

* Hoy mismo: `A0_full`, `A1_no_llm`
* Con flags mínimos nuevos: añadir `A2_no_planning`, `A3_no_semantic_memory`

**Seeds**

* smoke: 2
* dev: 5
* eval: 10

**Métricas primarias**

* `summary.agents.survival_rate`
* `alive_auc = Σ alive_t / (initial_agents * total_ticks)` derivada de `timeseries.jsonl`

**Métricas secundarias**

* `summary.actions.oracle_success_rate`
* `summary.actions.parse_fail_rate`
* media de `mean_hunger` y `mean_energy` en el último 20% de ticks

**Criterios de éxito**

* `A0_full` supera a `A1_no_llm` en `survival_rate` por al menos `+0.15` absolutos en eval.
* `A0_full` supera a `A1_no_llm` en `alive_auc` por al menos `+20%`.
* `parse_fail_rate <= 0.05` de mediana.
* `oracle_success_rate >= 0.75` de mediana.

Estas métricas base ya están o bien en `summary.json` o bien derivables directamente de `timeseries.jsonl`. ([GitHub][4])

## 5) Benchmark 2: `scarcity_v1` — el benchmark central del primer paper

Éste sí lo tomaría como benchmark principal, porque ya existe una línea documental muy clara en el repo: tu plan de `scarcity-adaptation-benchmark` propone una suite versionada, escenarios congelados, `metrics/scarcity.json`, un runner de benchmark y un report comparativo sobre `data/runs/`. La propia doc ya plantea métricas como `survival_auc`, `starvation_pressure` y `food_conversion_efficiency`, además de flags de benchmark y escalado de recursos/regeneración. ([GitHub][5])

**Escenarios**
Los tres son mi propuesta, siguiendo tu esquema de escalado:

* `mild`: `initial_resource_scale=0.60`, `regen_chance_scale=0.80`, `regen_amount_scale=0.80`
* `hard`: `0.35`, `0.60`, `0.60`
* `shock`: `0.60`, `0.30`, `0.50`

**Flags**

* existentes: `--agents 3 --ticks 400 --width 15 --height 15 --start-hour 8`
* nuevos:
  `--benchmark-id scarcity_v1 --benchmark-version scarcity_v1 --scenario-id <id> --candidate-label <arm> --initial-resource-scale <x> --regen-chance-scale <y> --regen-amount-scale <z>`

**Brazos**

* `A0_full`
* `A2_no_planning`
* `A3_no_semantic_memory`
* `A4_no_innovation`
* `A8_frozen_oracle`

**Métricas primarias**

* `scarcity.survival_auc`
* `scarcity.starvation_pressure`
* `scarcity.food_conversion_efficiency`

**Métricas secundarias**

* `summary.innovations.approval_rate`
* `summary.innovations.realization_rate`
* `ebs.utility.score`
* `ebs.realization.score`

**Criterios de éxito**

* En `hard`, `A0_full` supera a `A2_no_planning` y `A3_no_semantic_memory` en `survival_auc` por al menos `+0.10`.
* En `shock`, `A0_full` supera a `A4_no_innovation` en `survival_auc` por al menos `+0.08` y mejora `food_conversion_efficiency`.
* `A8_frozen_oracle` conserva al menos el `80%` del rendimiento de `A0_full`; si cae por debajo, tu claim tendrá que formularse como “adaptación en sistema agente+oráculo”, no como adaptación puramente del agente.

## 6) Benchmark 3: `affordance_v1` — donde de verdad pruebas progreso abierto

Aquí yo dejaría de usar mundos puramente aleatorios y pasaría a **fixtures**. Tu sistema ya tiene `reflect_item_uses`, el oráculo puede descubrir affordances derivadas de ítems, y el schema de descubrimiento limita los candidatos a 3; además, los eventos ya registran innovaciones validadas y ejecución de custom actions. Eso es suficiente para medir si aparece progreso instrumental, pero sólo si el escenario presenta una oportunidad bloqueada de forma consistente. ([GitHub][7])

**Escenarios fijados**

* `stone_to_tool`: spawn cerca de montaña/cueva con piedra accesible
* `river_access`: spawn con agua visible pero explotación eficiente bloqueada
* `craft_then_use`: escenario de dos pasos gather → craft → use

**Flags**

* nuevos: `--benchmark-id affordance_v1 --scenario-id <id> --world-fixture <fixture>`
* toggles: `--disallow-innovation`, `--disallow-item-reflection`, `--oracle-mode live|frozen|symbolic`

**Brazos**

* `A0_full`
* `A4_no_innovation`
* `A5_no_item_reflection`
* `A8_frozen_oracle`

**Métricas primarias**

* `item_derived_approval_rate`: porcentaje de runs con al menos una innovación aprobada donde `origin_item != null`
* `item_derived_realization_rate`
* `first_successful_custom_tick`

**Métricas secundarias**

* `ebs.utility.score`
* `ebs.realization.score`

**Criterios de éxito**

* `A0_full` produce al menos una innovación aprobada derivada de ítem en `>= 50%` de runs eval.
* `A0_full` supera a `A5_no_item_reflection` en `item_derived_realization_rate` por `>= 0.15`.
* `A8_frozen_oracle` retiene `>= 70%` del `item_derived_approval_rate` de `A0_full`; si no, la mayor parte de la creatividad la está poniendo el oráculo.

## 7) Benchmark 4: `culture_v1` — difusión, no sólo invención

Aquí hay una sutileza importante de framing. En tu implementación actual, `teach` no es una negociación emergente: si se cumplen las condiciones, el teacher gasta energía, el learner gasta energía y se hace `target.actions.append(skill)`; además se añaden memorias y cambia la confianza. Eso está muy bien como **primitiva de transmisión**, pero en paper debes presentarlo así, no como “pedagogía emergente” en sentido fuerte. ([GitHub][9])

**Escenarios**

* `dense_4a`: `--agents 4 --ticks 600 --width 15 --height 15`
* `sparse_5a`: `--agents 5 --ticks 800 --width 25 --height 25`
* `scarce_social_4a`: igual que `dense_4a`, pero sobre `scarcity_v1/hard`

**Brazos**

* `A0_full`
* `A6_no_social`
* `A6b_no_teach`
* `A3_no_semantic_memory`

**Métricas primarias**

* `teaching_success_rate`
* `non_inventor_use_rate`: proporción de innovaciones ejecutadas con éxito por un agente distinto del inventor
* `diffusion_rate`

**Métricas secundarias**

* `survival_rate`
* `alive_auc`
* `ebs.autonomy.detail.plan_completion_rate`

**Criterios de éxito**

* `A0_full` supera a `A6b_no_teach` en `diffusion_rate` por `>= 2x`.
* En `scarce_social_4a`, `A0_full` supera a `A6_no_social` en `survival_rate` por `>= 0.10`.
* `non_inventor_use_rate >= 0.30` en al menos un escenario de eval.

**Cambio mínimo necesario**

* Añadir o bien un evento `skill_taught`, o bien campos de procedencia (`inventor_id`, `teacher_id`, `learner_id`) a `innovation_validated`/`custom_action_executed`. Hoy el stream ya emite muchos eventos de planes, memoria e innovación, pero no te deja medir difusión con la limpieza que te hará falta para paper. ([GitHub][3])

## 8) Benchmark 5: `lineage_v1` — lo dejaría para la segunda fase

Aquí sí sería conservador. La reproducción actual está duramente restringida: requiere al menos 100 ticks de vida, `life >= 70`, `hunger <= 30`, `energy >= 50`, proximidad, cooldown y además ambos progenitores pagan `30/30/30`; el hijo nace con estado intermedio y puede heredar memorias semánticas. Eso está bien para un benchmark de linaje, pero demasiado tarde y demasiado caro como para usarlo como KPI principal del primer paper. ([GitHub][7])

**Escenarios**

* `longrun_5a_15x15`: `--agents 5 --ticks 1200 --width 15 --height 15`
* `longrun_5a_25x25`: `--agents 5 --ticks 1500 --width 25 --height 25`

**Brazos**

* `A0_full`
* `A7_no_reproduction`
* `A7b_no_inheritance`
* `A0_full_persist_lineage` vs `A0_full_persist_none`

**Métricas primarias**

* `births_per_run`
* `max_generation`
* `descendant_survival_rate`

**Métricas secundarias**

* `ebs.longevity.score`

**Criterios de éxito**

* `A0_full` con herencia supera a `A7b_no_inheritance` en `max_generation` y `descendant_survival_rate`.
* La persistencia de lineage mejora continuidad intergeneracional sin contaminar los benchmarks limpios de adaptación.

## 9) Qué correría ya mismo, con el repo actual

Sin tocar todavía nada del engine, correría sólo `survival_v1` en dos brazos (`full` y `no_llm`) y tres escenarios. Eso sí es totalmente compatible con el CLI y el `run_batch.py` actuales. ([GitHub][1])

Ejemplo de comandos:

```bash
uv run main.py --agents 3 --ticks 300 --seed 101 --width 15 --height 15 --start-hour 8 --model qwen2.5:3b --wandb --wandb-run-name survival_v1__default_day__full__s101

uv run main.py --agents 3 --ticks 300 --seed 101 --width 15 --height 15 --start-hour 8 --no-llm --wandb --wandb-run-name survival_v1__default_day__no_llm__s101

uv run main.py --agents 3 --ticks 300 --seed 101 --width 15 --height 15 --start-hour 20 --model qwen2.5:3b --wandb --wandb-run-name survival_v1__night_start__full__s101

uv run main.py --agents 3 --ticks 500 --seed 101 --width 25 --height 25 --start-hour 8 --model qwen2.5:3b --wandb --wandb-run-name survival_v1__large_map__full__s101
```

Y antes de cada run de benchmark limpio:

```bash
rm -f data/precedents_101.json data/lineage_101.json
```

Eso último no es opcional si quieres comparabilidad seria, porque el engine hoy persiste ambos artefactos por seed. ([GitHub][2])

## 10) Mi recomendación de priorización

Yo congelaría esto así:

1. `survival_v1` como sanity benchmark.
2. `scarcity_v1` como benchmark principal del paper 1.
3. `affordance_v1` como prueba de progreso instrumental.
4. `culture_v1` como extensión fuerte.
5. `lineage_v1` sólo cuando 1–4 ya sean estables.

La lectura estratégica es ésta: tu paper inicial no debería intentar demostrar “civilización emergente”, sino algo mucho más defendible y ya muy interesante: **planning + memoria + innovación mejoran la adaptación bajo escasez en un mundo LM-mediado, y parte de esa mejora sobrevive cuando congelas el oráculo**.

El siguiente paso lógico es convertir esta matriz en dos artefactos concretos: un `experiments.yaml` corrible hoy para `survival_v1`, y un `benchmarks/scarcity_v1.yaml` junto con el mini set de flags nuevos para que `scarcity_v1` quede publicable.

[1]: https://github.com/Emerge-world/emerge/blob/main/main.py "emerge/main.py at main · Emerge-world/emerge · GitHub"
[2]: https://github.com/Emerge-world/emerge/blob/main/simulation/engine.py "emerge/simulation/engine.py at main · Emerge-world/emerge · GitHub"
[3]: https://github.com/Emerge-world/emerge/blob/main/simulation/event_emitter.py "emerge/simulation/event_emitter.py at main · Emerge-world/emerge · GitHub"
[4]: https://github.com/Emerge-world/emerge/raw/main/simulation/metrics_builder.py "raw.githubusercontent.com"
[5]: https://github.com/Emerge-world/emerge/blob/main/docs/plans/2026-03-12-scarcity-adaptation-benchmark.md "emerge/docs/plans/2026-03-12-scarcity-adaptation-benchmark.md at main · Emerge-world/emerge · GitHub"
[6]: https://github.com/Emerge-world/emerge/blob/main/simulation/agent.py "https://github.com/Emerge-world/emerge/blob/main/simulation/agent.py"
[7]: https://github.com/Emerge-world/emerge/blob/main/simulation/config.py "emerge/simulation/config.py at main · Emerge-world/emerge · GitHub"
[8]: https://raw.githubusercontent.com/Emerge-world/emerge/main/simulation/config.py "raw.githubusercontent.com"
[9]: https://github.com/Emerge-world/emerge/blob/main/simulation/oracle.py "https://github.com/Emerge-world/emerge/blob/main/simulation/oracle.py"
