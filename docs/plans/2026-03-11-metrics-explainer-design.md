# Metrics Explainer Static Page Design

- **Date:** 2026-03-11
- **Status:** Approved
- **Audience:** Non-technical readers who want to understand how Emerge measures population behavior
- **Primary goal:** Explain the repository's current population metrics and full EBS scoring system in a way that is readable without code knowledge

## 1. Problem Statement

The repository already computes several layers of metrics, but the current explanations are spread across builder code, tests, and planning notes. That makes the system understandable to developers, but not to a non-technical reader who wants to know what is being measured across the population and how those measurements become a score.

The project needs a standalone explainer that:

- translates the implemented metrics into plain language
- shows the formulas behind each metric
- uses diagrams to make the flow easier to follow
- stays faithful to the code that is currently shipped

## 2. Existing Metrics System To Explain

The explainer must describe the metrics system as it exists in the repository today.

### Canonical source of truth

Each simulation run writes a canonical event stream under:

```text
data/runs/<run_id>/
```

The explainer should communicate this flow in simple terms:

```text
Agent actions during a run
        |
        v
Recorded events
        |
        v
Population summaries and time trends
        |
        v
EBS component scores
        |
        v
Overall emergence score
```

### Metrics layers in current code

1. **Run summary metrics**
   Produced by `simulation/metrics_builder.py`.

   These describe the full outcome of a run:

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

2. **Tick-by-tick metrics**
   Also produced by `simulation/metrics_builder.py`.

   These show population state over time:

   - alive agents
   - mean life
   - mean hunger
   - mean energy
   - deaths this tick
   - actions this tick
   - oracle success rate this tick
   - innovations attempted this tick
   - innovations approved this tick

3. **EBS scoring**
   Produced by `simulation/ebs_builder.py`.

   This is the interpretation layer built on top of the event stream:

   - Novelty
   - Utility
   - Realization
   - Stability
   - Autonomy
   - final EBS weighted score

4. **Live experiment tracking**
   Produced separately by `simulation/wandb_logger.py`.

   This is not the canonical scoring layer. It is an optional observer that streams aggregate metrics to Weights & Biases during a run.

## 3. Product Decision

The explainer will be a standalone static page in a docs-owned folder, not part of the existing `UI/` frontend.

### Chosen location

```text
docs/
└── metrics-explainer/
    ├── index.html
    ├── styles.css
    ├── script.js
    └── assets/
```

### Why this location

- keeps the explainer editorial and separate from the operator dashboard
- avoids coupling documentation to the live simulation frontend
- makes the page easier to publish, share, and review as documentation
- removes any dependency on the app's websocket or server behavior

## 4. Page Type

The page will be a single static explainer designed like a guided article.

It must feel easier to read than a plain markdown document while still preserving formulas and accuracy. The page should help a reader answer these questions:

- What does Emerge measure across the agent population?
- Which metrics are direct counts, and which are higher-level interpretations?
- How does the system turn recorded events into population summaries?
- What does the EBS score actually mean?

## 5. Information Architecture

The page will use a narrative structure with short visual blocks.

### Section 1: Intro / Purpose

Purpose:
- explain in one screen what the metrics system is for
- establish that the system studies population behavior, not only individual agents

Content:
- short introductory paragraph
- simple flow diagram
- one sentence defining EBS as a weighted summary, not a magical intelligence score

### Section 2: What The Simulation Records

Purpose:
- explain that the system first records events from the run
- show that all later metrics come from those recorded events

Content:
- short explanation of event recording in plain language
- diagram from actions -> events -> metrics -> scores
- small trust note that the builders read the recorded run after completion

### Section 3: Population Metrics

Purpose:
- explain the direct metrics computed from the run

Content:
- cards for survival, actions, and innovation
- each card includes:
  - the plain-English question
  - what is counted
  - a compact formula

Example formulas:

```text
Survival rate = final survivors / initial population

Oracle success rate = successful oracle resolutions / total oracle resolutions

Innovation approval rate = approved innovations / innovation attempts

Innovation realization rate = approved innovations later used / approved innovations
```

### Section 4: Time-Based Reading

Purpose:
- teach the reader the difference between full-run summaries and per-tick trends

Content:
- simple split view:

```text
Whole run metrics -> tell you how the run ended
Per-tick metrics  -> tell you how the population changed over time
```

- examples using alive count, average hunger, and average energy

### Section 5: EBS Score Breakdown

Purpose:
- explain the full scoring system clearly enough for a non-technical reader

Content:
- one intro block with the full equation
- five component panels
- each panel shows:
  - what the component means in human terms
  - the sub-signals used
  - the component weight in the final score

Core formula:

```text
EBS =
0.30 * Novelty
+ 0.20 * Utility
+ 0.20 * Realization
+ 0.15 * Stability
+ 0.15 * Autonomy
```

Component summaries:

- **Novelty:** measures whether agents create new behaviors and whether those behaviors are varied and structurally different
- **Utility:** measures whether approved innovations lead to useful results
- **Realization:** measures whether approved innovations are actually used and succeed
- **Stability:** measures how coherent and reliable agent behavior is
- **Autonomy:** measures whether agents show proactive and environment-contingent behavior

### Section 6: Limits And Interpretation

Purpose:
- prevent overclaiming

Content:
- direct counts are simpler and more concrete than EBS heuristics
- EBS is a structured interpretation layer, not absolute truth
- some parts are intentionally partial in the current implementation
- example: `self_generated_subgoals` is currently fixed at `0.0`

## 6. Visual Direction

The page should feel more like an editorial explainer than an operational dashboard.

### Design principles

- reading-first layout with generous spacing
- strong section hierarchy
- formulas highlighted in dedicated blocks
- diagrams embedded as lightweight HTML/CSS or inline SVG
- restrained motion only where it helps orientation
- mobile and desktop friendly

### Visual tone

- brighter and more readable than the current dashboard
- not a clone of the simulation UI
- intentional typography suitable for narrative reading
- clear color coding for EBS components

## 7. Interaction Model

The page is static and documentation-oriented.

### Behavior rules

- no backend calls
- no websocket connection
- no live simulation dependency
- no run loading
- no dynamic analytics requirement

JavaScript, if used, should stay minimal and support reading only, such as:

- section navigation
- diagram enhancement
- formula toggles or small progressive reveal patterns

## 8. Accuracy Rules

The page must stay grounded in the repository's actual behavior.

### Content rules

- describe only metrics that are implemented in current builders
- clearly separate direct counts from heuristic scoring
- label examples as illustrative, not live data
- do not claim that every metric is a perfect proxy for emergence

### Verification sources

The implementation should verify copy and formulas against:

- `simulation/metrics_builder.py`
- `simulation/ebs_builder.py`
- `simulation/wandb_logger.py`
- `tests/test_metrics_builder.py`
- `tests/test_ebs_builder.py`
- `tests/test_wandb_logger.py`

## 9. Out Of Scope

The following are intentionally excluded:

- integrating the explainer into `UI/`
- fetching live run data
- adding new simulation metrics
- changing `MetricsBuilder`, `EBSBuilder`, or `WandbLogger`
- building a replay tool or analytics dashboard

## 10. Acceptance Criteria

The work is successful when:

- a non-technical reader can understand what is measured across the population
- the page explains both direct metrics and the full EBS score
- formulas are visible and readable
- diagrams make the flow easier to understand
- the page lives under a docs-owned standalone folder
- the content matches the repository's current metrics implementation
