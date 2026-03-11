# Metrics Explainer Page Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a standalone static page under `docs/metrics-explainer/` that explains Emerge's population metrics and full EBS scoring system to a non-technical reader using formulas and diagrams.

**Architecture:** The page is a docs-owned artifact, not part of `UI/`. It uses plain HTML, CSS, and minimal vanilla JavaScript. All copy must map back to the current metrics implementation in `simulation/metrics_builder.py`, `simulation/ebs_builder.py`, and `simulation/wandb_logger.py`, with lightweight pytest checks guarding the critical wording and formulas.

**Tech Stack:** HTML5, CSS3, vanilla JavaScript, Python 3.12, `uv`, `pytest`

**Spec:** `docs/plans/2026-03-11-metrics-explainer-design.md`

---

### Task 1: Scaffold the standalone docs page

**Files:**
- Create: `docs/metrics-explainer/index.html`
- Create: `docs/metrics-explainer/styles.css`
- Create: `docs/metrics-explainer/script.js`
- Create: `tests/test_metrics_explainer_page.py`

**Step 1: Write the failing scaffold tests**

Create `tests/test_metrics_explainer_page.py` with this first test block:

```python
from pathlib import Path


DOCS_DIR = Path("docs/metrics-explainer")


class TestPageScaffold:
    def test_entry_files_exist(self):
        for rel in ("index.html", "styles.css", "script.js"):
            assert (DOCS_DIR / rel).exists(), rel

    def test_index_references_assets(self):
        html = (DOCS_DIR / "index.html").read_text(encoding="utf-8")
        assert 'href="styles.css"' in html
        assert 'src="script.js"' in html

    def test_core_sections_present(self):
        html = (DOCS_DIR / "index.html").read_text(encoding="utf-8")
        for section_id in (
            "intro",
            "population-metrics",
            "time-based-metrics",
            "ebs-score",
            "limits",
        ):
            assert f'id="{section_id}"' in html
```

**Step 2: Run the scaffold tests and verify they fail**

Run:

```bash
uv run pytest tests/test_metrics_explainer_page.py::TestPageScaffold -v
```

Expected:
- `FAIL` because `docs/metrics-explainer/` does not exist yet

**Step 3: Create the minimal static page files**

Add a minimal `index.html` that includes:

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
    <main>
      <section id="intro"></section>
      <section id="population-metrics"></section>
      <section id="time-based-metrics"></section>
      <section id="ebs-score"></section>
      <section id="limits"></section>
    </main>
    <script src="script.js" defer></script>
  </body>
</html>
```

Create empty-but-valid `styles.css` and `script.js` files at the same time.

**Step 4: Run the scaffold tests and verify they pass**

Run:

```bash
uv run pytest tests/test_metrics_explainer_page.py::TestPageScaffold -v
```

Expected:
- `PASS` for all three scaffold tests

**Step 5: Commit**

```bash
git add docs/metrics-explainer/index.html docs/metrics-explainer/styles.css docs/metrics-explainer/script.js tests/test_metrics_explainer_page.py
git commit -m "feat: scaffold standalone metrics explainer page"
```

---

### Task 2: Add the narrative structure and population metrics content

**Files:**
- Modify: `docs/metrics-explainer/index.html`
- Modify: `tests/test_metrics_explainer_page.py`

**Step 1: Write failing tests for the narrative sections and population formulas**

Append this test block to `tests/test_metrics_explainer_page.py`:

```python
class TestPopulationMetricsContent:
    def test_intro_heading_present(self):
        html = (DOCS_DIR / "index.html").read_text(encoding="utf-8")
        assert "How Emerge Measures Population Behavior" in html

    def test_population_formulas_present(self):
        html = (DOCS_DIR / "index.html").read_text(encoding="utf-8")
        assert "Survival rate = final survivors / initial population" in html
        assert "Oracle success rate = successful oracle resolutions / total oracle resolutions" in html
        assert "Innovation approval rate = approved innovations / innovation attempts" in html
        assert "Innovation realization rate = approved innovations later used / approved innovations" in html

    def test_population_metric_labels_present(self):
        html = (DOCS_DIR / "index.html").read_text(encoding="utf-8")
        for label in (
            "initial population",
            "final survivors",
            "deaths",
            "actions by type",
            "parse fail rate",
            "innovation attempts",
            "innovation approvals",
            "innovation reuse",
        ):
            assert label in html

    def test_run_vs_tick_explanation_present(self):
        html = (DOCS_DIR / "index.html").read_text(encoding="utf-8")
        assert "Whole run metrics" in html
        assert "Per-tick metrics" in html
        assert "alive agents" in html
        assert "mean hunger" in html
        assert "mean energy" in html
```

**Step 2: Run the new tests and verify they fail**

Run:

```bash
uv run pytest tests/test_metrics_explainer_page.py::TestPopulationMetricsContent -v
```

Expected:
- `FAIL` because the page does not have the required copy yet

**Step 3: Implement the narrative and metric sections**

Expand `docs/metrics-explainer/index.html` so it includes:

- a hero section with the heading `How Emerge Measures Population Behavior`
- a short intro paragraph for non-technical readers
- a "What the simulation records" section
- a "Population metrics" section with readable cards
- a "Time-based reading" section that explains whole-run vs per-tick metrics

Add the population formulas verbatim:

```text
Survival rate = final survivors / initial population
Oracle success rate = successful oracle resolutions / total oracle resolutions
Innovation approval rate = approved innovations / innovation attempts
Innovation realization rate = approved innovations later used / approved innovations
```

Keep the copy grounded in implemented behavior:
- `summary.json` style run metrics
- `timeseries.jsonl` style tick metrics
- no claims about live loading or dashboards

**Step 4: Run the new tests and verify they pass**

Run:

```bash
uv run pytest tests/test_metrics_explainer_page.py::TestPopulationMetricsContent -v
```

Expected:
- `PASS` for all population-content tests

**Step 5: Commit**

```bash
git add docs/metrics-explainer/index.html tests/test_metrics_explainer_page.py
git commit -m "feat: add population metrics narrative to explainer page"
```

---

### Task 3: Add the full EBS explanation and trust notes

**Files:**
- Modify: `docs/metrics-explainer/index.html`
- Modify: `tests/test_metrics_explainer_page.py`

**Step 1: Write failing tests for the EBS section**

Append this test block:

```python
class TestEbsContent:
    def test_ebs_formula_present(self):
        html = (DOCS_DIR / "index.html").read_text(encoding="utf-8")
        assert "EBS =" in html
        assert "0.30 * Novelty" in html
        assert "0.20 * Utility" in html
        assert "0.20 * Realization" in html
        assert "0.15 * Stability" in html
        assert "0.15 * Autonomy" in html

    def test_ebs_components_present(self):
        html = (DOCS_DIR / "index.html").read_text(encoding="utf-8")
        for label in ("Novelty", "Utility", "Realization", "Stability", "Autonomy"):
            assert label in html

    def test_trust_notes_present(self):
        html = (DOCS_DIR / "index.html").read_text(encoding="utf-8")
        assert "heuristic" in html.lower()
        assert "self_generated_subgoals" in html
        assert "0.0" in html
        assert "Weights & Biases" in html
        assert "optional observer" in html
```

**Step 2: Run the EBS tests and verify they fail**

Run:

```bash
uv run pytest tests/test_metrics_explainer_page.py::TestEbsContent -v
```

Expected:
- `FAIL` because the EBS section and trust notes are not complete yet

**Step 3: Implement the EBS and interpretation sections**

Add to `docs/metrics-explainer/index.html`:

- a dedicated `ebs-score` section
- the full weighted EBS formula
- five component blocks with plain-English explanations
- a limits/interpretation section

Important content requirements:

- explain EBS as a weighted summary, not an absolute truth
- distinguish direct counts from heuristic scoring
- mention that `self_generated_subgoals` is currently fixed at `0.0`
- explain that Weights & Biases is an optional observer, not the canonical scoring source

Recommended EBS panel copy outline:

```text
Novelty: Are agents inventing new and meaningfully different behaviors?
Utility: Do those innovations produce useful outcomes?
Realization: Do approved innovations get used and succeed?
Stability: Are the agents coherent and reliable?
Autonomy: Do the agents act proactively rather than only reactively?
```

**Step 4: Run the EBS tests and verify they pass**

Run:

```bash
uv run pytest tests/test_metrics_explainer_page.py::TestEbsContent -v
```

Expected:
- `PASS` for all EBS-content tests

**Step 5: Commit**

```bash
git add docs/metrics-explainer/index.html tests/test_metrics_explainer_page.py
git commit -m "feat: add EBS explanation and interpretation notes"
```

---

### Task 4: Add diagrams, visual styling, and minimal progressive enhancement

**Files:**
- Modify: `docs/metrics-explainer/index.html`
- Modify: `docs/metrics-explainer/styles.css`
- Modify: `docs/metrics-explainer/script.js`
- Modify: `tests/test_metrics_explainer_page.py`

**Step 1: Write failing tests for presentation hooks**

Append this test block:

```python
class TestPresentationHooks:
    def test_css_has_key_selectors(self):
        css = (DOCS_DIR / "styles.css").read_text(encoding="utf-8")
        for selector in (
            ".hero",
            ".metric-card",
            ".formula-block",
            ".diagram-flow",
            ".ebs-grid",
            ".limits-panel",
        ):
            assert selector in css
        assert "@media (max-width:" in css

    def test_js_has_progressive_enhancement_hooks(self):
        js = (DOCS_DIR / "script.js").read_text(encoding="utf-8")
        assert "data-scroll-target" in js
        assert "IntersectionObserver" in js
```

**Step 2: Run the presentation-hook tests and verify they fail**

Run:

```bash
uv run pytest tests/test_metrics_explainer_page.py::TestPresentationHooks -v
```

Expected:
- `FAIL` because the CSS selectors and JS hooks are not present yet

**Step 3: Implement the visual system and minimal JS**

Update `docs/metrics-explainer/index.html` to include:

- a compact top navigation with buttons or links using `data-scroll-target`
- a visual flow diagram for the run -> events -> metrics -> EBS pipeline
- formula callout blocks
- an EBS component grid

Update `docs/metrics-explainer/styles.css` to provide:

- a reading-first layout with generous spacing
- a brighter editorial tone than the main dashboard
- expressive but local-safe font stacks, for example serif headings and cleaner sans body text
- component color coding for the EBS sections
- responsive behavior for mobile
- reduced-motion-safe transitions

Update `docs/metrics-explainer/script.js` to provide only lightweight enhancements, such as:

- smooth scrolling for in-page navigation
- reveal-on-scroll for diagram/cards with an `IntersectionObserver`
- a safe fallback when reduced motion is preferred

**Step 4: Run the page tests and do a manual browser check**

Run:

```bash
uv run pytest tests/test_metrics_explainer_page.py -v
```

Expected:
- `PASS` for the full page test file

Then run:

```bash
uv run python -m http.server 8040 --directory docs/metrics-explainer
```

Expected:
- local static server starts on port `8040`

Manual check in a browser:
- the page reads clearly on desktop and mobile widths
- formulas are visually separated from paragraph text
- diagrams are easy to follow
- the page feels like documentation, not the simulation dashboard

**Step 5: Commit**

```bash
git add docs/metrics-explainer/index.html docs/metrics-explainer/styles.css docs/metrics-explainer/script.js tests/test_metrics_explainer_page.py
git commit -m "feat: style metrics explainer and add progressive enhancements"
```

---

### Task 5: Final accuracy pass against the current metrics implementation

**Files:**
- Modify if needed: `docs/metrics-explainer/index.html`
- Modify if needed: `tests/test_metrics_explainer_page.py`

**Step 1: Cross-check the copy against the actual builders and tests**

Review these files side by side:

- `simulation/metrics_builder.py`
- `simulation/ebs_builder.py`
- `simulation/wandb_logger.py`
- `tests/test_metrics_builder.py`
- `tests/test_ebs_builder.py`
- `tests/test_wandb_logger.py`

Confirm that the explainer:

- does not invent metrics that are not implemented
- keeps W&B clearly separate from canonical scoring
- accurately reflects the current EBS weights and caveats

**Step 2: Run the regression suite for the metrics explanation**

Run:

```bash
uv run pytest tests/test_metrics_builder.py tests/test_ebs_builder.py tests/test_wandb_logger.py tests/test_metrics_explainer_page.py -v
```

Expected:
- `PASS` for all targeted metrics and explainer tests

**Step 3: Review the final diff**

Run:

```bash
git diff -- docs/metrics-explainer tests/test_metrics_explainer_page.py
```

Expected:
- only the standalone docs page and its tests are present

**Step 4: Commit the final accuracy pass**

```bash
git add docs/metrics-explainer tests/test_metrics_explainer_page.py
git commit -m "docs: finalize standalone metrics explainer page"
```

**Step 5: Verification note**

Before claiming completion, make sure the explainer is:

- static and docs-owned
- visually readable
- grounded in the shipped metrics code
- explicit about heuristics and limitations
