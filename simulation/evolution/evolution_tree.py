"""
EvolutionTree: lineage tracking for world schema evolution.

Persisted as data/evolution/<tree_id>/tree.json.

Schema:
{
  "tree_id": "evo_2026-03-18_01",
  "config": { "branches_per_gen": 3, "runs_per_variant": 3,
              "max_generations": 10, "selection_top_k": 2 },
  "nodes": {
    "gen0_base": {
      "generation": 0, "parent": null,
      "schema_path": "gen_0/variant_base/world_schema.yaml",
      "runs": ["run_id_1", ...],
      "mean_ebs": 27.5, "std_ebs": 3.2, "selected": true
    }
  }
}
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class EvolutionNode:
    """One world variant in the evolution tree."""
    node_id: str
    generation: int
    parent: Optional[str]             # parent node_id or None
    schema_path: str                   # relative to tree_dir
    runs: list[str] = field(default_factory=list)
    mean_ebs: float = 0.0
    std_ebs: float = 0.0
    selected: bool = False             # True if this node survives to next gen
    agent_prompts_path: Optional[str] = None   # relative to tree_dir, JSON
    oracle_prompts_path: Optional[str] = None  # relative to tree_dir, JSON

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "EvolutionNode":
        # Backward-compatible: ignore unknown keys, fill missing optional fields
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        filtered = {k: v for k, v in d.items() if k in known}
        return cls(**filtered)


class EvolutionTree:
    """
    Tracks the evolution lineage of world schemas.

    Usage:
        tree = EvolutionTree(tree_dir, config)
        tree.save()
        tree.load()
        tree.add_node(...)
        top = tree.select_top_k(generation=1, k=2)
    """

    def __init__(self, tree_dir: Path | str, config: dict):
        self.tree_dir = Path(tree_dir)
        self.tree_id = self.tree_dir.name
        self.config = config  # {branches_per_gen, runs_per_variant, max_generations, selection_top_k}
        self.nodes: dict[str, EvolutionNode] = {}

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self) -> None:
        """Persist tree.json to disk."""
        self.tree_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "tree_id": self.tree_id,
            "config": self.config,
            "nodes": {nid: node.to_dict() for nid, node in self.nodes.items()},
        }
        path = self.tree_dir / "tree.json"
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        logger.debug("EvolutionTree saved to %s (%d nodes)", path, len(self.nodes))

    def load(self) -> None:
        """Load tree.json from disk if it exists."""
        path = self.tree_dir / "tree.json"
        if not path.exists():
            logger.debug("No tree.json at %s — starting fresh", path)
            return
        try:
            data = json.loads(path.read_text())
            self.tree_id = data.get("tree_id", self.tree_id)
            self.config = data.get("config", self.config)
            self.nodes = {
                nid: EvolutionNode.from_dict(nd)
                for nid, nd in data.get("nodes", {}).items()
            }
            logger.info("Loaded EvolutionTree from %s (%d nodes)", path, len(self.nodes))
        except Exception as exc:
            logger.error("Failed to load tree from %s: %s", path, exc)

    @classmethod
    def create(cls, base_dir: Path | str, config: dict) -> "EvolutionTree":
        """Create a new evolution tree with a timestamped ID."""
        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        tree_id = f"evo_{ts}"
        tree_dir = Path(base_dir) / tree_id
        tree = cls(tree_dir, config)
        return tree

    @classmethod
    def resume(cls, tree_json_path: Path | str) -> "EvolutionTree":
        """Load an existing evolution tree from a tree.json path or its parent directory."""
        path = Path(tree_json_path)
        if path.is_dir():
            path = path / "tree.json"
        tree = cls(path.parent, config={})
        tree.load()
        return tree

    # ------------------------------------------------------------------
    # Node management
    # ------------------------------------------------------------------

    def add_node(
        self,
        node_id: str,
        generation: int,
        parent: Optional[str],
        schema_path: str,
        agent_prompts_path: Optional[str] = None,
        oracle_prompts_path: Optional[str] = None,
    ) -> EvolutionNode:
        """Register a new variant node (before runs are complete)."""
        node = EvolutionNode(
            node_id=node_id,
            generation=generation,
            parent=parent,
            schema_path=schema_path,
            agent_prompts_path=agent_prompts_path,
            oracle_prompts_path=oracle_prompts_path,
        )
        self.nodes[node_id] = node
        return node

    def record_run(self, node_id: str, run_id: str) -> None:
        """Append a completed run_id to a node."""
        node = self.nodes[node_id]
        node.runs.append(run_id)

    def record_ebs(self, node_id: str, mean_ebs: float, std_ebs: float) -> None:
        """Set EBS statistics for a node after all its runs are complete."""
        node = self.nodes[node_id]
        node.mean_ebs = mean_ebs
        node.std_ebs = std_ebs

    def mark_selected(self, node_ids: list[str]) -> None:
        """Mark nodes as selected (surviving to next generation)."""
        for nid, node in self.nodes.items():
            node.selected = nid in node_ids

    # ------------------------------------------------------------------
    # Selection
    # ------------------------------------------------------------------

    def select_top_k(self, generation: int, k: int) -> list[EvolutionNode]:
        """
        Select the top-K nodes from a generation by mean EBS.
        Tiebreak: lower std_ebs is preferred (more consistent).
        """
        gen_nodes = [n for n in self.nodes.values() if n.generation == generation]
        if not gen_nodes:
            return []
        sorted_nodes = sorted(
            gen_nodes,
            key=lambda n: (-n.mean_ebs, n.std_ebs),
        )
        return sorted_nodes[:k]

    def get_nodes_by_generation(self, generation: int) -> list[EvolutionNode]:
        """Return all nodes belonging to a specific generation."""
        return [n for n in self.nodes.values() if n.generation == generation]

    def is_generation_complete(self, generation: int) -> bool:
        """
        Return True if all expected nodes for this generation have their
        runs recorded (according to config.runs_per_variant).
        """
        expected_runs = self.config.get("runs_per_variant", 1)
        nodes = self.get_nodes_by_generation(generation)
        if not nodes:
            return False
        return all(len(n.runs) >= expected_runs for n in nodes)

    def max_generation(self) -> int:
        """Return the highest generation number currently in the tree."""
        if not self.nodes:
            return -1
        return max(n.generation for n in self.nodes.values())

    # ------------------------------------------------------------------
    # Schema path helpers
    # ------------------------------------------------------------------

    def schema_path_for(self, generation: int, variant_name: str) -> Path:
        """Build the canonical schema YAML path for a variant."""
        return self.tree_dir / f"gen_{generation}" / variant_name / "world_schema.yaml"

    def mutations_path_for(self, generation: int, variant_name: str) -> Path:
        """Build the canonical mutations YAML path for a variant."""
        return self.tree_dir / f"gen_{generation}" / variant_name / "mutations.yaml"

    def agent_prompts_path_for(self, generation: int, variant_name: str) -> Path:
        """Build the canonical agent prompts JSON path for a variant."""
        return self.tree_dir / f"gen_{generation}" / variant_name / "agent_prompts.json"

    def oracle_prompts_path_for(self, generation: int, variant_name: str) -> Path:
        """Build the canonical oracle prompts JSON path for a variant."""
        return self.tree_dir / f"gen_{generation}" / variant_name / "oracle_prompts.json"
