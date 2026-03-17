"""
RunAnalyzer: aggregates run data from data/runs/<run_id>/ into a structured
summary suitable for the WorldEvolver prompt.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class RunSummary:
    """Aggregated data from one or more runs of a world variant."""
    run_ids: list[str] = field(default_factory=list)
    # EBS
    mean_ebs: float = 0.0
    std_ebs: float = 0.0
    ebs_components: dict = field(default_factory=dict)  # averaged across runs
    # Agent statistics
    mean_survival_rate: float = 0.0
    mean_ticks: float = 0.0
    # Action distribution (averaged proportions)
    action_distribution: dict[str, float] = field(default_factory=dict)
    innovation_approval_rate: float = 0.0
    # Resource utilization
    resource_utilization: dict[str, float] = field(default_factory=dict)
    # Qualitative insights from LLM digest (if available)
    digest_insights: list[str] = field(default_factory=list)
    # Parse failures / errors
    parse_fail_rate: float = 0.0

    def to_prompt_text(self) -> str:
        """Format as human-readable text for the evolver prompt."""
        lines = [
            f"RUNS ANALYZED: {len(self.run_ids)}",
            f"",
            f"PERFORMANCE:",
            f"  Mean EBS: {self.mean_ebs:.1f} (std: {self.std_ebs:.1f})",
            f"  Mean survival rate: {self.mean_survival_rate:.1%}",
            f"  Mean ticks survived: {self.mean_ticks:.0f}",
            f"",
        ]
        if self.ebs_components:
            lines.append("EBS COMPONENTS (mean scores, 0-100):")
            for name, info in self.ebs_components.items():
                if isinstance(info, dict):
                    score = info.get("score", info.get("mean_score", 0))
                else:
                    score = info
                lines.append(f"  {name}: {score:.1f}")
            lines.append("")

        if self.action_distribution:
            lines.append("ACTION DISTRIBUTION (% of all actions):")
            total = sum(self.action_distribution.values()) or 1
            for action, count in sorted(self.action_distribution.items(), key=lambda x: -x[1]):
                pct = count / total * 100
                lines.append(f"  {action}: {pct:.1f}%")
            lines.append("")

        if self.innovation_approval_rate > 0:
            lines.append(f"INNOVATION: approval rate {self.innovation_approval_rate:.1%}")
            lines.append("")

        if self.digest_insights:
            lines.append("QUALITATIVE INSIGHTS (from LLM digest):")
            for insight in self.digest_insights[:5]:
                lines.append(f"  - {insight}")
            lines.append("")

        return "\n".join(lines)


class RunAnalyzer:
    """
    Reads run output directories and aggregates statistics.

    Usage:
        analyzer = RunAnalyzer(run_dirs)
        summary = analyzer.analyze()
    """

    def __init__(self, run_dirs: list[Path | str]):
        self.run_dirs = [Path(d) for d in run_dirs]

    def analyze(self) -> RunSummary:
        """Aggregate data from all run dirs into a RunSummary."""
        ebs_scores: list[float] = []
        survival_rates: list[float] = []
        tick_counts: list[float] = []
        action_totals: dict[str, float] = {}
        ebs_component_lists: dict[str, list[float]] = {}
        innovation_rates: list[float] = []
        digest_insights: list[str] = []
        parse_fail_rates: list[float] = []
        run_ids: list[str] = []

        for run_dir in self.run_dirs:
            run_dir = Path(run_dir)
            run_id = run_dir.name
            run_ids.append(run_id)

            # EBS
            ebs_path = run_dir / "metrics" / "ebs.json"
            if ebs_path.exists():
                try:
                    with ebs_path.open() as f:
                        ebs_data = json.load(f)
                    ebs_scores.append(float(ebs_data.get("ebs", 0)))
                    for comp_name, comp_data in ebs_data.get("components", {}).items():
                        score = float(comp_data.get("score", 0))
                        ebs_component_lists.setdefault(comp_name, []).append(score)
                except Exception as exc:
                    logger.warning("Failed to read EBS from %s: %s", ebs_path, exc)

            # Summary
            summary_path = run_dir / "metrics" / "summary.json"
            if summary_path.exists():
                try:
                    with summary_path.open() as f:
                        summary = json.load(f)
                    agents = summary.get("agents", {})
                    survival_rates.append(float(agents.get("survival_rate", 0)))
                    tick_counts.append(float(summary.get("total_ticks", 0)))

                    actions = summary.get("actions", {})
                    by_type = actions.get("by_type", {})
                    for action, count in by_type.items():
                        action_totals[action] = action_totals.get(action, 0) + float(count)
                    parse_fail_rates.append(float(actions.get("parse_fail_rate", 0)))

                    innovations = summary.get("innovations", {})
                    if innovations.get("attempts", 0) > 0:
                        innovation_rates.append(float(innovations.get("approval_rate", 0)))
                except Exception as exc:
                    logger.warning("Failed to read summary from %s: %s", summary_path, exc)

            # LLM digest
            digest_path = run_dir / "llm_digest" / "run_digest.json"
            if digest_path.exists():
                try:
                    with digest_path.open() as f:
                        digest_data = json.load(f)
                    # Extract narrative insights
                    narrative = digest_data.get("narrative", "")
                    if narrative:
                        # Take first 2 sentences as insight
                        sentences = narrative.split(".")[:2]
                        insight = ". ".join(s.strip() for s in sentences if s.strip())
                        if insight:
                            digest_insights.append(insight)
                except Exception as exc:
                    logger.debug("Could not read digest from %s: %s", digest_path, exc)

        # Aggregate
        import math

        def _mean(vals: list) -> float:
            return sum(vals) / len(vals) if vals else 0.0

        def _std(vals: list) -> float:
            if len(vals) < 2:
                return 0.0
            m = _mean(vals)
            variance = sum((v - m) ** 2 for v in vals) / len(vals)
            return math.sqrt(variance)

        ebs_components_avg = {
            name: {"score": _mean(scores)}
            for name, scores in ebs_component_lists.items()
        }

        return RunSummary(
            run_ids=run_ids,
            mean_ebs=_mean(ebs_scores),
            std_ebs=_std(ebs_scores),
            ebs_components=ebs_components_avg,
            mean_survival_rate=_mean(survival_rates),
            mean_ticks=_mean(tick_counts),
            action_distribution=action_totals,
            innovation_approval_rate=_mean(innovation_rates) if innovation_rates else 0.0,
            digest_insights=digest_insights,
            parse_fail_rate=_mean(parse_fail_rates),
        )
