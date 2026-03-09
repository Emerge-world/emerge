"""Weights & Biases experiment logger for Emerge simulation.

Passive observer: receives tick data from the engine and logs per-tick
aggregate metrics. Zero impact on the simulation when --wandb is not set.
"""
import hashlib
import statistics
from pathlib import Path
from typing import Optional

import wandb


class WandbLogger:
    """Logs per-tick aggregate metrics to Weights & Biases."""

    def __init__(
        self,
        project: str,
        entity: Optional[str],
        run_config: dict,
        prompts_dir: Path,
    ) -> None:
        prompt_hashes = self._hash_prompts(prompts_dir)
        config = {
            **run_config,
            **{f"prompt/{k}": v["sha256"] for k, v in prompt_hashes.items()},
        }
        wandb.init(project=project, entity=entity, config=config)
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

    def log_tick(
        self,
        tick: int,
        alive_agents: list,
        world,
        oracle,
        tick_data: dict,
    ) -> None:
        """Compute per-tick aggregates and log to W&B."""
        # Filled in Task 3
        pass

    def finish(self) -> None:
        """Signal end of run to W&B."""
        wandb.finish()
