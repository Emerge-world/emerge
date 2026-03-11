"""Weights & Biases experiment logger for Emerge simulation.

Passive observer: receives tick data from the engine and logs per-tick
aggregate metrics. Zero impact on the simulation when --wandb is not set.
"""
import hashlib
import statistics
from pathlib import Path
from typing import Optional

import wandb

from simulation.config import BASE_ACTIONS


class WandbLogger:
    """Logs per-tick aggregate metrics to Weights & Biases."""

    def __init__(
        self,
        project: str,
        entity: Optional[str],
        run_config: dict,
        prompts_dir: Path,
        run_name: Optional[str] = None,
    ) -> None:
        prompt_hashes = self._hash_prompts(prompts_dir)
        config = {
            **run_config,
            **{f"prompt/{k}": v["sha256"] for k, v in prompt_hashes.items()},
        }
        wandb.init(project=project, entity=entity, config=config, name=run_name)
        if prompt_hashes:
            self._upload_prompt_artifact(prompts_dir, prompt_hashes)

    def _hash_prompts(self, prompts_dir: Path) -> dict[str, dict]:
        """Return {relative_path: {"sha256": ..., "text": ...}} for each .txt file."""
        result = {}
        if prompts_dir.exists():
            for txt_file in sorted(prompts_dir.rglob("*.txt")):
                key = str(txt_file.relative_to(prompts_dir))
                content = txt_file.read_text(encoding="utf-8")
                result[key] = {
                    "sha256": hashlib.sha256(content.encode()).hexdigest(),
                    "text": content,
                }
        return result

    def _upload_prompt_artifact(self, prompts_dir: Path, prompt_hashes: dict) -> None:
        """Upload all prompt .txt files as a versioned W&B Artifact."""
        artifact = wandb.Artifact("emerge-prompts", type="prompt")
        for txt_file in sorted(prompts_dir.rglob("*.txt")):
            artifact.add_file(
                str(txt_file),
                name=str(txt_file.relative_to(prompts_dir)),
            )
        wandb.log_artifact(artifact)

    BASE_ACTION_TYPES = BASE_ACTIONS

    def log_tick(
        self,
        tick: int,
        alive_agents: list,
        world,
        oracle,
        tick_data: dict,
    ) -> None:
        """Compute per-tick aggregates and log to W&B."""
        metrics: dict = {}

        # --- Agent aggregates ---
        metrics["agents/alive"] = len(alive_agents)
        if alive_agents:
            lives = [a.life for a in alive_agents]
            hungers = [a.hunger for a in alive_agents]
            energies = [a.energy for a in alive_agents]
            metrics["agents/mean_life"] = statistics.mean(lives)
            metrics["agents/min_life"] = min(lives)
            metrics["agents/max_life"] = max(lives)
            metrics["agents/mean_hunger"] = statistics.mean(hungers)
            metrics["agents/min_hunger"] = min(hungers)
            metrics["agents/max_hunger"] = max(hungers)
            metrics["agents/mean_energy"] = statistics.mean(energies)
            metrics["agents/min_energy"] = min(energies)
            metrics["agents/max_energy"] = max(energies)
        else:
            for stat in ("life", "hunger", "energy"):
                metrics[f"agents/mean_{stat}"] = 0
                metrics[f"agents/min_{stat}"] = 0
                metrics[f"agents/max_{stat}"] = 0

        metrics["agents/deaths_this_tick"] = tick_data.get("deaths", 0)
        metrics["agents/births_this_tick"] = tick_data.get("births", 0)

        # --- Actions ---
        actions = tick_data.get("actions", [])
        oracle_results = tick_data.get("oracle_results", [])
        metrics["actions/total"] = len(actions)
        metrics["actions/oracle_success_rate"] = (
            sum(oracle_results) / len(oracle_results) if oracle_results else 0.0
        )
        metrics["actions/innovations"] = tick_data.get("innovations", 0)
        for action_type in self.BASE_ACTION_TYPES:
            metrics[f"actions/by_type/{action_type}"] = sum(
                1 for a in actions if a == action_type
            )
        metrics["actions/by_type/other"] = sum(
            1 for a in actions if a not in self.BASE_ACTION_TYPES
        )

        # --- World ---
        metrics["world/total_resources"] = sum(
            res["quantity"] for res in world.resources.values()
        )

        # --- Oracle ---
        metrics["oracle/precedent_count"] = len(oracle.precedents)

        # --- Day/night ---
        metrics["sim/is_daytime"] = 1 if tick_data.get("is_daytime", True) else 0

        wandb.log(metrics, step=tick)

    def finish(self) -> None:
        """Signal end of run to W&B."""
        wandb.finish()
