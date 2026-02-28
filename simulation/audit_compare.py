"""
Comparison CLI for behavioral audit data.

Usage:
    uv run -m simulation.audit_compare logs/sim_<baseline> logs/sim_<variant>

Reads audit/meta.json + audit/summary.json from two runs and prints
a terminal report showing prompt diffs, metrics deltas, behavioral
fingerprints, and stat sparklines.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional


# ------------------------------------------------------------------
# Data loading
# ------------------------------------------------------------------

def load_run(run_dir: str) -> dict:
    """Load meta.json and summary.json from a run's audit/ directory."""
    audit_dir = Path(run_dir) / "audit"
    if not audit_dir.exists():
        print(f"Error: no audit/ directory in {run_dir}", file=sys.stderr)
        print("Did you run with --audit?", file=sys.stderr)
        sys.exit(1)

    meta_path = audit_dir / "meta.json"
    summary_path = audit_dir / "summary.json"

    if not meta_path.exists() or not summary_path.exists():
        print(f"Error: missing meta.json or summary.json in {audit_dir}", file=sys.stderr)
        sys.exit(1)

    with open(meta_path, encoding="utf-8") as f:
        meta = json.load(f)
    with open(summary_path, encoding="utf-8") as f:
        summary = json.load(f)

    return {"meta": meta, "summary": summary, "path": run_dir}


# ------------------------------------------------------------------
# Section 1: Prompt Diff
# ------------------------------------------------------------------

def print_prompt_diff(baseline: dict, variant: dict):
    """Show which prompt files changed between runs."""
    print("\n" + "=" * 70)
    print("  PROMPT DIFF")
    print("=" * 70)

    b_prompts = baseline["meta"].get("prompts", {})
    v_prompts = variant["meta"].get("prompts", {})

    all_keys = sorted(set(b_prompts.keys()) | set(v_prompts.keys()))
    changed = []
    unchanged = []

    for key in all_keys:
        b_hash = b_prompts.get(key, {}).get("sha256", "")
        v_hash = v_prompts.get(key, {}).get("sha256", "")
        if b_hash != v_hash:
            changed.append(key)
        else:
            unchanged.append(key)

    if not changed:
        print("\n  No prompt files changed between runs.\n")
    else:
        for key in changed:
            print(f"\n  CHANGED: {key}")
            b_text = b_prompts.get(key, {}).get("text", "(not present)")
            v_text = v_prompts.get(key, {}).get("text", "(not present)")
            # Show first few lines of each version
            b_preview = _preview(b_text, label="Baseline")
            v_preview = _preview(v_text, label="Variant")
            print(b_preview)
            print(v_preview)

    if unchanged:
        print(f"\n  Unchanged: {', '.join(unchanged)}")
    print()


def _preview(text: str, label: str, max_lines: int = 5) -> str:
    """Show a truncated preview of prompt text."""
    lines = text.strip().splitlines()
    preview_lines = lines[:max_lines]
    suffix = f"  ... (+{len(lines) - max_lines} more lines)" if len(lines) > max_lines else ""
    body = "\n".join(f"    | {line}" for line in preview_lines)
    return f"    [{label}]:\n{body}{suffix}"


# ------------------------------------------------------------------
# Section 2: Metrics Table
# ------------------------------------------------------------------

METRIC_KEYS = [
    ("Survival rate", "survival_rate", "agg"),
    ("Oracle success rate", "oracle_success_rate", "agg"),
    ("Ate when hungry", "ate_when_hungry", "agg"),
    ("Rested when exhausted", "rested_when_exhausted", "agg"),
    ("Ate when food adjacent", "ate_when_food_adjacent", "agg"),
    ("Unique tiles (mean)", "unique_tiles_visited", "agg"),
    ("Max distance from spawn", "max_distance_from_spawn", "agg"),
]


def print_metrics_table(baseline: dict, variant: dict):
    """Side-by-side metrics with deltas."""
    print("=" * 70)
    print("  METRICS COMPARISON")
    print("=" * 70)

    b_agg = baseline["summary"].get("aggregate", {})
    v_agg = variant["summary"].get("aggregate", {})

    # Header
    print(f"\n  {'Metric':<30s} {'Baseline':>10s} {'Variant':>10s} {'Delta':>12s}")
    print(f"  {'-' * 30} {'-' * 10} {'-' * 10} {'-' * 12}")

    # Standard metrics
    for label, key, _ in METRIC_KEYS:
        b_val = b_agg.get(key)
        v_val = v_agg.get(key)
        _print_metric_row(label, b_val, v_val)

    # Action distribution
    b_actions = b_agg.get("action_distribution", {})
    v_actions = v_agg.get("action_distribution", {})
    all_actions = sorted(set(b_actions.keys()) | set(v_actions.keys()))
    for act in all_actions:
        b_val = b_actions.get(act)
        v_val = v_actions.get(act)
        _print_metric_row(f"Action: {act}", b_val, v_val, pct=True)

    print()


def _print_metric_row(label: str, b_val, v_val, pct: bool = False):
    """Print a single metric row with delta and directional arrows."""
    b_str = _fmt_val(b_val, pct)
    v_str = _fmt_val(v_val, pct)

    if b_val is not None and v_val is not None:
        delta = v_val - b_val
        arrow = _delta_arrow(delta)
        if pct:
            delta_str = f"{delta:+.0%} {arrow}"
        else:
            delta_str = f"{delta:+.2f} {arrow}"
    else:
        delta_str = "---"

    print(f"  {label:<30s} {b_str:>10s} {v_str:>10s} {delta_str:>12s}")


def _fmt_val(val, pct: bool = False) -> str:
    if val is None:
        return "---"
    if pct:
        return f"{val:.0%}"
    if isinstance(val, float):
        return f"{val:.2f}"
    return str(val)


def _delta_arrow(delta: float) -> str:
    """Return directional arrows based on magnitude."""
    abs_d = abs(delta)
    if abs_d < 0.01:
        return "="
    if abs_d < 0.1:
        return "^" if delta > 0 else "v"
    return "^^" if delta > 0 else "vv"


# ------------------------------------------------------------------
# Section 3: Behavioral Fingerprint
# ------------------------------------------------------------------

FINGERPRINT_KEYS = [
    ("Survival", "survival_rate"),
    ("Reactivity", None),  # computed from ate_when_hungry + rested_when_exhausted
    ("Success", "oracle_success_rate"),
    ("Mobility", None),  # computed from unique_tiles / max reasonable
    ("Innovation", None),  # computed from action distribution
]


def print_fingerprint(baseline: dict, variant: dict):
    """Compact bar visualization per run."""
    print("=" * 70)
    print("  BEHAVIORAL FINGERPRINT")
    print("=" * 70)

    b_agg = baseline["summary"].get("aggregate", {})
    v_agg = variant["summary"].get("aggregate", {})

    b_fp = _compute_fingerprint(b_agg)
    v_fp = _compute_fingerprint(v_agg)

    print(f"\n  {'':20s} {'Baseline':^12s}   {'Variant':^12s}")
    for label, _, _ in b_fp:
        b_bar = ""
        v_bar = ""
        for l, val, _ in b_fp:
            if l == label:
                b_bar = _bar(val)
                break
        for l, val, _ in v_fp:
            if l == label:
                v_bar = _bar(val)
                break
        print(f"  {label:<20s} {b_bar}   {v_bar}")
    print()


def _compute_fingerprint(agg: dict) -> list[tuple[str, float, str]]:
    """Compute normalized 0-1 values for each fingerprint dimension."""
    survival = agg.get("survival_rate", 0.0)

    # Reactivity: mean of ate_when_hungry and rested_when_exhausted
    react_vals = []
    if agg.get("ate_when_hungry") is not None:
        react_vals.append(agg["ate_when_hungry"])
    if agg.get("rested_when_exhausted") is not None:
        react_vals.append(agg["rested_when_exhausted"])
    reactivity = sum(react_vals) / len(react_vals) if react_vals else 0.0

    success = agg.get("oracle_success_rate", 0.0)

    # Mobility: normalize unique_tiles to a 0-1 scale (cap at 50)
    unique = agg.get("unique_tiles_visited", 0)
    mobility = min(unique / 50.0, 1.0) if isinstance(unique, (int, float)) else 0.0

    # Innovation: fraction of innovate actions
    innovate_pct = agg.get("action_distribution", {}).get("innovate", 0.0)
    # Normalize (10% innovation is high)
    innovation = min(innovate_pct / 0.10, 1.0)

    return [
        ("Survival", survival, _bar(survival)),
        ("Reactivity", reactivity, _bar(reactivity)),
        ("Success", success, _bar(success)),
        ("Mobility", mobility, _bar(mobility)),
        ("Innovation", innovation, _bar(innovation)),
    ]


def _bar(val: float, width: int = 10) -> str:
    """Render a 0-1 value as a filled bar."""
    filled = int(val * width)
    return "\u2588" * filled + "\u2591" * (width - filled)


# ------------------------------------------------------------------
# Section 4: Stat Sparklines
# ------------------------------------------------------------------

SPARKLINE_CHARS = " \u2581\u2582\u2583\u2584\u2585\u2586\u2587\u2588"


def print_sparklines(baseline: dict, variant: dict):
    """ASCII trajectory of each stat over time."""
    print("=" * 70)
    print("  STAT TRAJECTORIES")
    print("=" * 70)

    b_traj = baseline["summary"].get("aggregate", {}).get("mean_trajectories", {})
    v_traj = variant["summary"].get("aggregate", {}).get("mean_trajectories", {})

    for stat in ("life", "hunger", "energy"):
        b_data = b_traj.get(stat, [])
        v_data = v_traj.get(stat, [])

        if not b_data and not v_data:
            continue

        print(f"\n  {stat.title()} (mean):")
        if b_data:
            spark = _sparkline(b_data)
            print(f"    Baseline: {spark}  {b_data[0]:.0f}\u2192{b_data[-1]:.0f}")
        if v_data:
            spark = _sparkline(v_data)
            print(f"    Variant:  {spark}  {v_data[0]:.0f}\u2192{v_data[-1]:.0f}")

    print()


def _sparkline(data: list[float], width: int = 40) -> str:
    """Render a list of values as a sparkline, resampled to width."""
    if not data:
        return ""

    # Resample to width
    if len(data) > width:
        step = len(data) / width
        resampled = [data[int(i * step)] for i in range(width)]
    else:
        resampled = data

    lo = min(resampled)
    hi = max(resampled)
    span = hi - lo if hi != lo else 1.0

    chars = []
    for v in resampled:
        idx = int((v - lo) / span * (len(SPARKLINE_CHARS) - 1))
        chars.append(SPARKLINE_CHARS[idx])
    return "".join(chars)


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Compare behavioral audit data between two simulation runs"
    )
    parser.add_argument("baseline", help="Path to baseline run directory (logs/sim_...)")
    parser.add_argument("variant", help="Path to variant run directory (logs/sim_...)")
    args = parser.parse_args()

    baseline = load_run(args.baseline)
    variant = load_run(args.variant)

    print("\n" + "=" * 70)
    print("  AUDIT COMPARISON")
    print(f"  Baseline: {args.baseline}")
    print(f"  Variant:  {args.variant}")
    print("=" * 70)

    print_prompt_diff(baseline, variant)
    print_metrics_table(baseline, variant)
    print_fingerprint(baseline, variant)
    print_sparklines(baseline, variant)

    print("=" * 70)


if __name__ == "__main__":
    main()
