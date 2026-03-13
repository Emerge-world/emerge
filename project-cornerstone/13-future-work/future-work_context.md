# 13 — Future Work by Project Dimension

This file proposes next steps that are consistent with the current implementation.

## 1) World & Ecology

- Add weather states (clear/rain/drought/storm) integrated with `day_cycle` + resource regeneration.
- Introduce seasonal regimes (longer scarcity/abundance windows) for adaptation pressure.
- Model renewable vs finite resources explicitly in metrics and prompts.

## 2) Agents, Cognition, and Behavior

- Upgrade memory retrieval from recency-based slices to relevance scoring.
- Add explicit goal stacks (short-term needs vs long-term plans).
- Expand personality expression into action priors (risk-taking, prosociality, exploration bias).

## 3) Oracle & Determinism

- Version precedent schema and add migration utility.
- Add deterministic replay checker: recompute outcomes from events and compare with logged state.
- Separate strict-physics validations from social/probabilistic judgments for clearer guarantees.

## 4) Innovation & Knowledge Systems

- [ ] Score innovation usefulness over time (frequency, survival impact, transfer rate).
- Add anti-bloat pruning for rarely used innovations.
- Introduce multi-step craft chains and dependency graph analysis.

## 5) Social Interaction & Culture

- Enable emergent protocol tracking from `communicate` messages (token convergence, shared symbols).
- Add coalition-level trust and reciprocity metrics.
- Test social memory layers (who helped/harmed whom, decay, forgiveness).

## 6) Evolution & Lineage

- Add fitness indicators per lineage branch (descendant count, longevity, innovation productivity).
- Evaluate inheritance experiments (trait heritability controls, mutation schedules).
- Surface kin-selection patterns from family-aware behavior.

## 7) Visualization & UX

- Build run replay UI from `events.jsonl` with timeline controls.
- Add genealogy explorer linked to agent cards and event history.
- Add metrics dashboard (survival, cooperation, innovation effectiveness, precedent growth).

## 8) Experimentation & Evaluation

- Standardize experiment manifest schema (`experiments.yaml`) with validation tooling.
- Add baseline bundles for deterministic smoke comparisons by seed.
- Automate post-run report generation from `metrics_builder` outputs.

## 9) DevOps & Reliability

- Add CI matrix for Python + frontend checks + key regression tests.
- Add schema validation for emitted events to prevent downstream breakage.
- Add run-retention and artifact-cleanup policies for `data/runs/` growth.

## 10) LLM Integration

- Add provider abstraction layer for local vLLM/Ollama and hosted APIs.
- Add structured-output hardening and fallback retry policies per endpoint.
- Track prompt/version experiments with explicit metadata tags in run outputs.
