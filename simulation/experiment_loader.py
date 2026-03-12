import json
from dataclasses import dataclass, field
from pathlib import Path

from simulation.metrics_builder import MetricsBuilder


@dataclass
class RunMetricsResult:
    run_dir: Path
    summary: dict = field(default_factory=dict)
    rebuilt: bool = False
    invalid: bool = False


def load_run_metrics(run_dir: Path) -> RunMetricsResult:
    run_dir = Path(run_dir)
    summary_path = run_dir / "metrics" / "summary.json"
    rebuilt = False

    if not summary_path.exists() and (run_dir / "events.jsonl").exists():
        MetricsBuilder(run_dir).build()
        rebuilt = True

    if not summary_path.exists():
        return RunMetricsResult(run_dir=run_dir, rebuilt=rebuilt, invalid=True)

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    return RunMetricsResult(run_dir=run_dir, summary=summary, rebuilt=rebuilt)
