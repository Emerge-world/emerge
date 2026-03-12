# Live Metrics Explainer Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a standalone docs-owned metrics explainer that teaches Emerge's metrics system and can render bundled sample artifacts or real run metric artifacts.

**Architecture:** The explainer lives outside `UI/` in `docs/metrics-explainer/` as a small client-side page. It combines an editorial narrative with an artifact loader that reads `summary.json`, `timeseries.jsonl`, and `ebs.json` independently and degrades gracefully when any file is missing.

**Tech Stack:** HTML5, CSS3, vanilla JavaScript, Python 3.12, `uv`, `pytest`

---

### Task 1: Lock the data contract with sample artifact fixtures

**Files:**
- Create: `docs/metrics-explainer/fixtures/sample_summary.json`
- Create: `docs/metrics-explainer/fixtures/sample_timeseries.jsonl`
- Create: `docs/metrics-explainer/fixtures/sample_ebs.json`
- Create: `tests/test_metrics_explainer_page.py`

**Step 1: Write the failing tests**

Create `tests/test_metrics_explainer_page.py` with:

```python
import json
from pathlib import Path


DOCS_DIR = Path("docs/metrics-explainer")
FIXTURES_DIR = DOCS_DIR / "fixtures"


class TestExplainerFixtures:
    def test_fixture_files_exist(self):
        for rel in (
            "sample_summary.json",
            "sample_timeseries.jsonl",
            "sample_ebs.json",
        ):
            assert (FIXTURES_DIR / rel).exists(), rel

    def test_summary_fixture_matches_metrics_shape(self):
        summary = json.loads((FIXTURES_DIR / "sample_summary.json").read_text())
        assert set(summary.keys()) == {"run_id", "total_ticks", "agents", "actions", "innovations"}
        assert set(summary["agents"].keys()) == {
            "initial_count",
            "final_survivors",
            "deaths",
            "survival_rate",
        }
        assert set(summary["actions"].keys()) == {
            "total",
            "by_type",
            "oracle_success_rate",
            "parse_fail_rate",
        }
        assert set(summary["innovations"].keys()) == {
            "attempts",
            "approved",
            "rejected",
            "used",
            "approval_rate",
            "realization_rate",
        }

    def test_timeseries_fixture_rows_match_metrics_shape(self):
        lines = (FIXTURES_DIR / "sample_timeseries.jsonl").read_text().splitlines()
        assert lines
        row = json.loads(lines[0])
        assert set(row.keys()) == {
            "tick",
            "sim_time",
            "alive",
            "mean_life",
            "mean_hunger",
            "mean_energy",
            "deaths",
            "actions",
            "oracle_success_rate",
            "innovations_attempted",
            "innovations_approved",
        }

    def test_ebs_fixture_matches_builder_shape(self):
        ebs = json.loads((FIXTURES_DIR / "sample_ebs.json").read_text())
        assert set(ebs.keys()) == {"run_id", "ebs", "components", "innovations"}
        assert set(ebs["components"].keys()) == {
            "novelty",
            "utility",
            "realization",
            "stability",
            "autonomy",
        }
        assert ebs["components"]["autonomy"]["sub_scores"]["self_generated_subgoals"] == 0.0
```

**Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_metrics_explainer_page.py::TestExplainerFixtures -v`

Expected: `FAIL` because the fixtures do not exist yet

**Step 3: Create the sample artifacts**

Create the three fixture files with realistic values matching the current builders.

Use this minimal `sample_summary.json` structure:

```json
{
  "run_id": "sample-run",
  "total_ticks": 12,
  "agents": {
    "initial_count": 3,
    "final_survivors": ["Ada", "Bruno"],
    "deaths": 1,
    "survival_rate": 0.6667
  },
  "actions": {
    "total": 36,
    "by_type": {
      "move": 12,
      "eat": 8,
      "rest": 7,
      "innovate": 3,
      "forage": 6
    },
    "oracle_success_rate": 0.7778,
    "parse_fail_rate": 0.0556
  },
  "innovations": {
    "attempts": 3,
    "approved": 2,
    "rejected": 1,
    "used": 1,
    "approval_rate": 0.6667,
    "realization_rate": 0.5
  }
}
```

Populate `sample_timeseries.jsonl` with at least 5 rows following the exact timeseries schema, and `sample_ebs.json` with all five components, weights, sub-scores, and an `innovations` list.

**Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_metrics_explainer_page.py::TestExplainerFixtures -v`

Expected: `PASS`

**Step 5: Commit**

```bash
git add docs/metrics-explainer/fixtures tests/test_metrics_explainer_page.py
git commit -m "test: add fixtures for metrics explainer data contract"
```

### Task 2: Scaffold the standalone explainer page and source picker

**Files:**
- Create: `docs/metrics-explainer/index.html`
- Create: `docs/metrics-explainer/styles.css`
- Create: `docs/metrics-explainer/script.js`
- Modify: `tests/test_metrics_explainer_page.py`

**Step 1: Write the failing scaffold tests**

Append:

```python
class TestExplainerScaffold:
    def test_entry_files_exist(self):
        for rel in ("index.html", "styles.css", "script.js"):
            assert (DOCS_DIR / rel).exists(), rel

    def test_core_sections_present(self):
        html = (DOCS_DIR / "index.html").read_text(encoding="utf-8")
        for section_id in (
            "hero",
            "flow",
            "population-metrics",
            "time-based-metrics",
            "ebs-score",
            "limits",
        ):
            assert f'id="{section_id}"' in html

    def test_run_explorer_controls_present(self):
        html = (DOCS_DIR / "index.html").read_text(encoding="utf-8")
        assert 'id="artifact-source-form"' in html
        assert 'name="artifact-mode"' in html
        assert 'id="artifact-path"' in html
        assert 'id="artifact-status"' in html
```

**Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_metrics_explainer_page.py::TestExplainerScaffold -v`

Expected: `FAIL`

**Step 3: Create the minimal page**

Create `index.html` with:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Emerge Metrics Explainer</title>
    <link rel="stylesheet" href="styles.css" />
  </head>
  <body>
    <main class="page-shell">
      <section id="hero"></section>
      <section id="flow"></section>
      <section id="population-metrics"></section>
      <section id="time-based-metrics"></section>
      <section id="ebs-score"></section>
      <section id="limits"></section>
    </main>
    <script src="script.js" defer></script>
  </body>
</html>
```

Then expand the hero section so it includes:

```html
<form id="artifact-source-form">
  <input type="radio" name="artifact-mode" value="sample" checked />
  <input type="radio" name="artifact-mode" value="path" />
  <input id="artifact-path" name="artifact-path" type="text" />
  <button type="submit">Load artifacts</button>
</form>
<p id="artifact-status" aria-live="polite"></p>
```

Create valid empty `styles.css` and `script.js`.

**Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_metrics_explainer_page.py::TestExplainerScaffold -v`

Expected: `PASS`

**Step 5: Commit**

```bash
git add docs/metrics-explainer/index.html docs/metrics-explainer/styles.css docs/metrics-explainer/script.js tests/test_metrics_explainer_page.py
git commit -m "feat: scaffold live metrics explainer page"
```

### Task 3: Add the narrative copy and formula-backed metric sections

**Files:**
- Modify: `docs/metrics-explainer/index.html`
- Modify: `tests/test_metrics_explainer_page.py`

**Step 1: Write the failing content tests**

Append:

```python
class TestExplainerContent:
    def test_primary_heading_present(self):
        html = (DOCS_DIR / "index.html").read_text(encoding="utf-8")
        assert "How Emerge Measures Population Behavior" in html

    def test_population_formulas_present(self):
        html = (DOCS_DIR / "index.html").read_text(encoding="utf-8")
        assert "Survival rate = final survivors / initial population" in html
        assert "Oracle success rate = successful oracle resolutions / total oracle resolutions" in html
        assert "Innovation approval rate = approved innovations / innovation attempts" in html
        assert "Innovation realization rate = approved innovations later used / approved innovations" in html

    def test_ebs_formula_present(self):
        html = (DOCS_DIR / "index.html").read_text(encoding="utf-8")
        assert "0.30 * Novelty" in html
        assert "0.20 * Utility" in html
        assert "0.20 * Realization" in html
        assert "0.15 * Stability" in html
        assert "0.15 * Autonomy" in html

    def test_limits_copy_present(self):
        html = (DOCS_DIR / "index.html").read_text(encoding="utf-8")
        assert "self_generated_subgoals" in html
        assert "0.0" in html
        assert "Weights & Biases" in html
        assert "optional observer" in html
```

**Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_metrics_explainer_page.py::TestExplainerContent -v`

Expected: `FAIL`

**Step 3: Implement the copy**

Expand `index.html` so it includes:

- hero copy introducing the page
- a flow section describing `events.jsonl -> summary/timeseries -> ebs`
- metric cards for survival, action quality, and innovation
- a whole-run vs per-tick explanation
- the full EBS equation and component summaries
- a limits section calling out heuristics and W&B as a separate observer

Keep these formulas verbatim:

```text
Survival rate = final survivors / initial population
Oracle success rate = successful oracle resolutions / total oracle resolutions
Innovation approval rate = approved innovations / innovation attempts
Innovation realization rate = approved innovations later used / approved innovations
```

**Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_metrics_explainer_page.py::TestExplainerContent -v`

Expected: `PASS`

**Step 5: Commit**

```bash
git add docs/metrics-explainer/index.html tests/test_metrics_explainer_page.py
git commit -m "feat: add live metrics explainer narrative"
```

### Task 4: Implement the artifact loader and graceful degradation

**Files:**
- Modify: `docs/metrics-explainer/script.js`
- Modify: `docs/metrics-explainer/index.html`
- Modify: `tests/test_metrics_explainer_page.py`

**Step 1: Write the failing loader tests**

Append:

```python
class TestLoaderHooks:
    def test_script_contains_loader_entrypoints(self):
        script = (DOCS_DIR / "script.js").read_text(encoding="utf-8")
        assert "async function loadArtifacts" in script
        assert "async function loadSummary" in script
        assert "async function loadTimeseries" in script
        assert "async function loadEbs" in script
        assert "function renderArtifactStatus" in script

    def test_script_handles_partial_failures(self):
        script = (DOCS_DIR / "script.js").read_text(encoding="utf-8")
        assert "Promise.allSettled" in script
        assert "summary:" in script
        assert "timeseries:" in script
        assert "ebs:" in script
        assert "unavailable" in script.lower()

    def test_index_contains_render_targets(self):
        html = (DOCS_DIR / "index.html").read_text(encoding="utf-8")
        for element_id in (
            "summary-cards",
            "timeseries-panel",
            "ebs-panels",
            "artifact-field-details",
        ):
            assert f'id="{element_id}"' in html
```

**Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_metrics_explainer_page.py::TestLoaderHooks -v`

Expected: `FAIL`

**Step 3: Implement the loader**

In `script.js`:

- add `loadArtifacts(basePath, mode)`
- add dedicated `loadSummary`, `loadTimeseries`, and `loadEbs` helpers
- use `Promise.allSettled` so partial failures remain renderable
- support `sample` mode by loading from `fixtures/`
- support `?run=...` query parameter and form submission path mode
- normalize results into:

```javascript
{
  summary: { status: 'loaded' | 'missing' | 'invalid', data: ... },
  timeseries: { status: 'loaded' | 'missing' | 'invalid', data: ... },
  ebs: { status: 'loaded' | 'missing' | 'invalid', data: ... },
}
```

- render readable status text into `#artifact-status`

In `index.html`, add container elements with the IDs asserted by the tests.

**Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_metrics_explainer_page.py::TestLoaderHooks -v`

Expected: `PASS`

**Step 5: Commit**

```bash
git add docs/metrics-explainer/index.html docs/metrics-explainer/script.js tests/test_metrics_explainer_page.py
git commit -m "feat: add artifact loader for metrics explainer"
```

### Task 5: Build the interactive views and visual system

**Files:**
- Modify: `docs/metrics-explainer/index.html`
- Modify: `docs/metrics-explainer/styles.css`
- Modify: `docs/metrics-explainer/script.js`
- Modify: `tests/test_metrics_explainer_page.py`

**Step 1: Write the failing presentation tests**

Append:

```python
class TestPresentationHooks:
    def test_index_contains_interactive_view_toggles(self):
        html = (DOCS_DIR / "index.html").read_text(encoding="utf-8")
        assert 'data-view="meaning"' in html
        assert 'data-view="run"' in html
        assert "Show data source" in html

    def test_styles_define_visual_tokens(self):
        css = (DOCS_DIR / "styles.css").read_text(encoding="utf-8")
        for token in (
            "--page-bg",
            "--panel-bg",
            "--novelty",
            "--utility",
            "--realization",
            "--stability",
            "--autonomy",
        ):
            assert token in css

    def test_script_contains_renderers(self):
        script = (DOCS_DIR / "script.js").read_text(encoding="utf-8")
        assert "function renderSummaryCards" in script
        assert "function renderTimeseriesCharts" in script
        assert "function renderEbsPanels" in script
        assert "function renderMetricViewToggle" in script
```

**Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_metrics_explainer_page.py::TestPresentationHooks -v`

Expected: `FAIL`

**Step 3: Implement the page design**

Update `index.html` to include:

- summary card grid
- inline chart containers for alive, hunger, energy, and innovations
- EBS component panels
- per-section view toggles and artifact detail drawers

Update `styles.css` to include:

- custom visual tokens and component colors
- editorial layout and responsive breakpoints
- cards, charts, toggles, and formula block styling
- restrained reveal transitions

Update `script.js` to include:

- summary rendering from `summary.json`
- SVG or div-based sparkline rendering from `timeseries.jsonl`
- weighted bar rendering from `ebs.json`
- meaning/run toggle behavior
- placeholders when data is unavailable

**Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_metrics_explainer_page.py::TestPresentationHooks -v`

Expected: `PASS`

**Step 5: Commit**

```bash
git add docs/metrics-explainer/index.html docs/metrics-explainer/styles.css docs/metrics-explainer/script.js tests/test_metrics_explainer_page.py
git commit -m "feat: render interactive metrics explainer views"
```

### Task 6: Verify the page against metrics docs and cornerstone references

**Files:**
- Modify: `project-cornerstone/00-master-plan/DECISION_LOG.md`
- Modify: `project-cornerstone/09-visualization/visualization_context.md`
- Modify if needed: `docs/plans/2026-03-12-live-metrics-explainer-design.md`
- Modify if needed: `tests/test_metrics_explainer_page.py`

**Step 1: Write the failing documentation consistency test**

Append:

```python
class TestDocumentationConsistency:
    def test_cornerstone_mentions_docs_explainer(self):
        decision_log = Path("project-cornerstone/00-master-plan/DECISION_LOG.md").read_text(encoding="utf-8")
        visualization = Path("project-cornerstone/09-visualization/visualization_context.md").read_text(encoding="utf-8")
        assert "interactive metrics explainer" in decision_log.lower()
        assert "docs/metrics-explainer/" in visualization
```

**Step 2: Run the test to verify it fails if the cornerstone docs are missing updates**

Run: `uv run pytest tests/test_metrics_explainer_page.py::TestDocumentationConsistency -v`

Expected: `FAIL` if the cornerstone docs are not aligned

**Step 3: Update the docs if needed**

Make sure the decision log records the standalone docs page with optional real artifact loading, and the visualization context lists the explainer as a docs-owned visualization surface separate from `UI/`.

**Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/test_metrics_explainer_page.py::TestDocumentationConsistency -v`

Expected: `PASS`

**Step 5: Commit**

```bash
git add project-cornerstone/00-master-plan/DECISION_LOG.md project-cornerstone/09-visualization/visualization_context.md docs/plans/2026-03-12-live-metrics-explainer-design.md tests/test_metrics_explainer_page.py
git commit -m "docs: align cornerstone with metrics explainer"
```

### Task 7: Run the full verification set

**Files:**
- Modify if needed: `docs/metrics-explainer/*`
- Modify if needed: `tests/test_metrics_explainer_page.py`

**Step 1: Run targeted explainer and metrics tests**

Run: `uv run pytest tests/test_metrics_builder.py tests/test_ebs_builder.py tests/test_wandb_logger.py tests/test_metrics_explainer_page.py -v`

Expected: `PASS` for all targeted tests

**Step 2: Serve the page locally**

Run: `uv run python -m http.server 8040 --directory docs/metrics-explainer`

Expected:

- sample mode loads on first render
- query parameter loading works when artifacts are served
- missing artifact files show readable unavailable states
- mobile and desktop layouts remain readable

**Step 3: Run the project smoke test required by the repo**

Run: `uv run pytest -m "not slow"`

Expected: `PASS`

**Step 4: Commit**

```bash
git add docs/metrics-explainer tests/test_metrics_explainer_page.py
git commit -m "feat: finalize live metrics explainer page"
```
