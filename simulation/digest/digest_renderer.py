"""DigestRenderer: writes digest JSON and markdown files. No analysis logic."""

from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path


class DigestRenderer:
    """Serializes RunDigest and AgentDigests to JSON + markdown files."""

    def __init__(self, run_dir: Path):
        self._run_dir = Path(run_dir)
        self._digest_dir = self._run_dir / "llm_digest"
        self._agents_dir = self._digest_dir / "agents"

    def render(
        self,
        run_digest: dict,
        agent_digests: dict[str, dict],
        evidence_index: dict,
        manifest: dict,
    ) -> None:
        """Write all digest files to llm_digest/."""
        self._digest_dir.mkdir(exist_ok=True)
        self._agents_dir.mkdir(exist_ok=True)

        # run_digest.json
        self._write_json("run_digest.json", run_digest)

        # run_digest.md
        (self._digest_dir / "run_digest.md").write_text(
            self._render_run_md(run_digest), encoding="utf-8"
        )

        # per-agent files
        for agent_id, agent_digest in agent_digests.items():
            self._write_json(f"agents/{agent_id}.json", agent_digest)
            (self._agents_dir / f"{agent_id}.md").write_text(
                self._render_agent_md(agent_digest), encoding="utf-8"
            )

        # evidence_index.json
        self._write_json("evidence_index.json", evidence_index)

        # generation_manifest.json
        self._write_json("generation_manifest.json", manifest)

    # --- JSON helpers ---

    def _write_json(self, rel_path: str, data: dict) -> None:
        path = self._digest_dir / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    @staticmethod
    def _display(value, fallback: str = "unknown") -> str:
        return fallback if value is None or value == "" else str(value)

    # --- Markdown templates ---

    def _render_run_md(self, d: dict) -> str:
        meta = d.get("meta", {})
        outcomes = d.get("outcomes", {})
        agents = d.get("agents", [])
        anomalies = d.get("anomalies", [])

        survivors = ", ".join(outcomes.get("survivors", [])) or "none"
        deaths = ", ".join(outcomes.get("deaths", [])) or "none"

        agent_rows = "\n".join(
            f"| {a['agent_id']} | {a['status']} | "
            f"{self._display(a.get('generation'))} | {self._display(a.get('born_tick'))} | "
            f"{a['dominant_mode']} | {a['phase_count']} | "
            f"{a['innovation_count']} | {a['anomaly_count']} |"
            for a in agents
        )

        anomaly_section = ""
        if anomalies:
            rows = "\n".join(
                f"| {a['type']} | {a['severity']} | tick {a['tick']} | "
                f"{a.get('agent_id') or 'run'} | {a['description'][:60]} |"
                for a in anomalies
            )
            anomaly_section = f"""
## Anomalies

| Type | Severity | When | Agent | Description |
|------|----------|------|-------|-------------|
{rows}
"""

        return f"""# Run Digest: {d.get('run_id', 'unknown')}

Generated: {d.get('generated_at', '')}

## Meta

| Key | Value |
|-----|-------|
| Seed | {meta.get('seed', '?')} |
| Ticks | {meta.get('ticks', '?')} |
| Agents | {meta.get('agent_count', '?')} |
| Model | {meta.get('model_id', '?')} |
| Commit | {meta.get('git_commit', '?')} |

## Outcomes

- **Survivors:** {survivors}
- **Deaths:** {deaths}
- **Innovations approved:** {outcomes.get('total_innovations_approved', 0)}
- **Innovations attempted:** {outcomes.get('total_innovations_attempted', 0)}
- **Total anomalies:** {outcomes.get('total_anomalies', 0)}

## Agents

| Agent | Status | Generation | Born Tick | Dominant Mode | Phases | Innovations | Anomalies |
|-------|--------|------------|-----------|---------------|--------|-------------|-----------|
{agent_rows}
{anomaly_section}
"""

    def _render_agent_md(self, d: dict) -> str:
        agent_id = d.get("agent_id", "unknown")
        lineage = d.get("lineage", {})
        final = d.get("final_state", {})
        extrema = d.get("state_extrema", {})
        action_mix = d.get("action_mix", {})
        phases = d.get("phases", [])
        innovations = d.get("innovations", [])
        contradictions = d.get("contradictions", [])
        anomalies = d.get("anomalies", [])
        critical = d.get("critical_events", [])

        # Action mix table
        mix_rows = "\n".join(f"| {k} | {v:.1%} |" for k, v in sorted(action_mix.items(), key=lambda x: -x[1]))

        # Phases table
        phase_rows = "\n".join(
            f"| {p['phase_id']} | {p['mode']} | {p['tick_start']}–{p['tick_end']} | "
            f"{p['confidence']:.2f} | {', '.join(p.get('dominant_signals', [])[:3])} |"
            for p in phases
        )

        # Innovation section
        inno_section = ""
        if innovations:
            rows = "\n".join(
                f"| {i['name']} | tick {i.get('tick_attempted', '?')} | "
                f"{'✓' if i.get('approved') else '✗'} | {i.get('category', '')} |"
                for i in innovations
            )
            inno_section = f"""
| Name | Attempted | Approved | Category |
|------|-----------|----------|----------|
{rows}
"""
        else:
            inno_section = "\n_No innovations attempted._\n"

        # Critical events
        crit_section = ""
        if critical:
            crit_section = "\n".join(
                f"- **Tick {c['tick']}:** {c['description']}"
                for c in critical
            )
        else:
            crit_section = "_No critical events._"

        # Contradictions
        contra_section = ""
        if contradictions:
            contra_section = "\n".join(
                f"- **Tick {c['tick']}:** \"{c['learning'][:80]}\" — contradicted by: {c['contradicted_by']}"
                for c in contradictions
            )
        else:
            contra_section = "_No contradictions detected._"

        pos = final.get("pos", None)
        if isinstance(pos, list) and len(pos) >= 2:
            pos_str = f"({pos[0]}, {pos[1]})"
        elif isinstance(pos, dict):
            pos_str = f"({pos.get('x', '?')}, {pos.get('y', '?')})"
        else:
            pos_str = "unknown"

        min_life = extrema.get("min_life", {})
        max_hunger = extrema.get("max_hunger", {})
        generation = lineage.get("generation")
        born_tick = lineage.get("born_tick")
        parent_ids = lineage.get("parent_ids", [])
        if generation == 0 and not parent_ids:
            parents_str = "Original settler"
        elif parent_ids:
            parents_str = ", ".join(str(parent_id) for parent_id in parent_ids)
        else:
            parents_str = "unknown"

        return f"""# Agent Digest: {agent_id}

**Run:** {d.get('run_id', 'unknown')}
**Status:** {d.get('status', 'unknown')}

## Lineage

- Generation: {self._display(generation)}
- Born tick: {self._display(born_tick)}
- Parents: {parents_str}

## Final State

| Stat | Value |
|------|-------|
| Life | {final.get('life', '?')} |
| Hunger | {final.get('hunger', '?')} |
| Energy | {final.get('energy', '?')} |
| Position | {pos_str} |

**State extrema:**
- Lowest life: {min_life.get('value', '?')} at tick {min_life.get('tick', '?')}
- Peak hunger: {max_hunger.get('value', '?')} at tick {max_hunger.get('tick', '?')}

## Action Mix

| Action | Frequency |
|--------|-----------|
{mix_rows}

## Phases

| # | Mode | Ticks | Confidence | Top Signals |
|---|------|-------|------------|-------------|
{phase_rows}

## Innovations
{inno_section}
## Critical Events

{crit_section}

## Contradictions

{contra_section}
"""
