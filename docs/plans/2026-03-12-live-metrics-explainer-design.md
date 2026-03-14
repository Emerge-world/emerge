# Live Metrics Explainer Design

- **Date:** 2026-03-12
- **Status:** Approved
- **Audience:** Readers who want a shareable explanation of Emerge metrics with the option to inspect real run artifacts
- **Primary goal:** Build a standalone docs page that explains how population metrics and EBS work while optionally loading real run metric artifacts
- **Supersedes:** `docs/plans/2026-03-11-metrics-explainer-design.md` for product direction

## 1. Problem Statement

The repository already has a live React dashboard for operating the simulation and separate builders for post-run metrics. What it does not have is a shareable surface that explains the metrics in plain language and lets readers inspect the artifacts those builders produce.

The new page needs to solve both jobs at once:

- explain the metrics system without requiring code literacy
- stay separate from the operator dashboard in `UI/`
- feel more like an interactive editorial dashboard than a static article
- support real run artifacts without depending on the live WebSocket app

## 2. Product Decision

The metrics explainer will be a standalone docs-owned page under `docs/metrics-explainer/`.

### Chosen location

```text
docs/
└── metrics-explainer/
    ├── index.html
    ├── styles.css
    ├── script.js
    ├── fixtures/
    │   ├── sample_summary.json
    │   ├── sample_timeseries.jsonl
    │   └── sample_ebs.json
    └── assets/
```

### Why this location

- keeps the explainer shareable and easy to publish
- avoids coupling explanatory content to the live simulation shell
- allows the page to work with static hosting and local file serving
- preserves a clear boundary between narrative docs and operational controls

## 3. Sources Of Truth

The page must describe the metrics system exactly as implemented today.

### Canonical artifacts

The canonical run artifact flow is:

```text
Agent actions during a run
        |
        v
Recorded events in data/runs/<run_id>/events.jsonl
        |
        v
metrics_builder -> summary.json + timeseries.jsonl
        |
        v
ebs_builder -> ebs.json
        |
        v
Reader-facing explainer views
```

### Implemented metrics to explain

1. **Run summary metrics** from `simulation/metrics_builder.py`
   - initial population
   - final survivors
   - deaths
   - survival rate
   - total actions
   - actions by type
   - oracle success rate
   - parse fail rate
   - innovation attempts
   - innovation approvals
   - innovation reuse

2. **Tick metrics** from `simulation/metrics_builder.py`
   - alive
   - mean life
   - mean hunger
   - mean energy
   - deaths
   - actions
   - oracle success rate
   - innovations attempted
   - innovations approved

3. **EBS scoring** from `simulation/ebs_builder.py`
   - Novelty
   - Utility
   - Realization
   - Stability
   - Autonomy
   - weighted final EBS score

4. **W&B telemetry** from `simulation/wandb_logger.py`
   - present only as an optional observer
   - explicitly not the canonical scoring layer

## 4. Page Architecture

The page will have two layers that coexist in one interface.

### Editorial layer

This layer explains the system whether or not any data is loaded.

It includes:

- a hero section introducing the metrics system
- an event-to-score flow diagram
- metric definition cards with formulas
- a whole-run vs per-tick explanation
- an EBS breakdown with weights and sub-signals
- a limitations section calling out heuristic and partial areas

### Data layer

This layer adapts the page to whichever artifacts are available.

It includes:

- headline stat cards sourced from `summary.json`
- trend charts sourced from `timeseries.jsonl`
- weighted EBS panels sourced from `ebs.json`
- state badges that indicate whether a section is showing sample data, real run data, or no data

The page must remain readable when artifacts are absent. Missing artifact files should disable only the dependent views, never the whole page.

## 5. Artifact Loading Model

The loader in `script.js` will support three source modes behind one small normalized API.

### Mode 1: Bundled sample data

Default mode.

The page ships with fixture artifacts under `docs/metrics-explainer/fixtures/` so it always renders a meaningful example.

### Mode 2: Run directory path

The reader can provide a base path pointing to a run directory or metrics directory. The loader then attempts to fetch:

- `summary.json`
- `timeseries.jsonl`
- `ebs.json`

This path is intended for local serving from the repository, for example:

```text
../data/runs/<run_id>/metrics/
```

### Mode 3: Query parameter preset

The page may accept a linkable parameter such as:

```text
?run=../data/runs/<run_id>/metrics
```

This enables shareable links when the page is served alongside repository artifacts.

### Loader rules

- each artifact is loaded independently
- `summary.json` powers summary cards and formula examples
- `timeseries.jsonl` powers time-based charts
- `ebs.json` powers the EBS section
- partial success is acceptable and expected
- the UI must surface which files loaded and which failed
- failures should produce readable notices, not thrown errors

## 6. Interaction Model

The page should feel like an interactive dashboard for understanding, not an operator console.

### Primary interactions

- a run explorer panel where the reader chooses sample data or enters a run path
- metric cards with a plain-English question, exact formula, and a toggle to reveal artifact fields
- an event-to-metrics flow diagram that highlights the current stage as the reader scrolls
- lightweight charts for alive agents, mean hunger, mean energy, and innovation counts
- an EBS breakdown with weighted bars and expandable sub-score details
- a section-level toggle between:
  - `What this metric means`
  - `How this run scored`

### Behavior when no artifacts are available

- the editorial copy remains fully visible
- charts collapse into explanatory placeholders
- the run explorer explains how to point the page at real artifacts

## 7. Information Architecture

### Section 1: Hero

Purpose:
- explain what the metrics system is for
- establish that the page explains population behavior rather than individual anecdotes

Content:
- heading
- short introduction
- artifact source panel
- trust note that live W&B telemetry is optional and separate

### Section 2: From Events To Metrics

Purpose:
- explain the event stream as the foundation of every derived metric

Content:
- flow diagram from events to summary, timeseries, and EBS
- concise note that builders run after the simulation and read persisted artifacts

### Section 3: Population Metrics

Purpose:
- explain direct counts and rates from `summary.json`

Content:
- cards for survival, action quality, and innovation
- formulas shown in exact repository language

Core formulas:

```text
Survival rate = final survivors / initial population

Oracle success rate = successful oracle resolutions / total oracle resolutions

Innovation approval rate = approved innovations / innovation attempts

Innovation realization rate = approved innovations later used / approved innovations
```

### Section 4: Time-Based Reading

Purpose:
- distinguish end-of-run summaries from tick-by-tick change

Content:
- side-by-side explanation of whole-run vs per-tick metrics
- trend views for alive count, mean hunger, mean energy, and innovation activity

### Section 5: EBS Breakdown

Purpose:
- explain the weighted interpretation layer in concrete terms

Content:
- full equation
- one panel per component
- expandable sub-score definitions tied to `ebs.json`

Core formula:

```text
EBS =
0.30 * Novelty
+ 0.20 * Utility
+ 0.20 * Realization
+ 0.15 * Stability
+ 0.15 * Autonomy
```

### Section 6: Limits And Interpretation

Purpose:
- prevent overclaiming

Content:
- direct counts are more concrete than heuristic layers
- EBS is a structured interpretation, not a truth oracle
- `self_generated_subgoals` is currently fixed at `0.0`
- W&B is an observer, not the source of official scores

## 8. Visual Direction

The page should be brighter and more editorial than the dark live dashboard.

### Design principles

- reading-first layout with deliberate visual hierarchy
- expressive typography that does not reuse the default UI stack
- background depth through gradients, panels, and subtle structure
- strong color mapping per EBS component
- restrained motion for reveal and emphasis only
- responsive layout for desktop and mobile

### Anti-goals

- do not clone the operator dashboard in `UI/`
- do not add live simulation controls
- do not make the page depend on WebSockets or FastAPI routes
- do not overstate features that are not implemented in the builders

## 9. Testing Strategy

The page should be guarded by repository tests, not only manual browser review.

### Required automated checks

- file existence and section scaffold tests for `docs/metrics-explainer/`
- copy and formula assertions tied to current builder outputs
- fixture structure tests that validate sample artifacts against current JSON shapes
- loader behavior tests for:
  - full success
  - missing `summary.json`
  - missing `timeseries.jsonl`
  - missing `ebs.json`
  - malformed JSON or JSONL

### Manual verification

- serve the page locally and verify sample mode works
- verify a real run path loads when artifacts exist
- verify mobile and desktop layouts remain readable

## 10. Non-Goals For This Iteration

- integrating the explainer into `UI/`
- live replay from `events.jsonl`
- timeline scrubbing
- genealogy visualization
- cross-run comparison
- backend API changes for the explainer
