"""
Subgoal completion/failure evaluator.

After each oracle resolution, checks whether the agent's active planning
subgoal has been satisfied or should be considered failed.  The evaluator
uses keyword pattern matching against the LLM-generated completion_signal
and failure_signal strings, combined with the agent's current state.
"""
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from simulation.agent import Agent
    from simulation.planning_state import PlanningSubgoal

# Action → keywords that appear in completion_signals for that action type
_ACTION_COMPLETION_HINTS: dict[str, tuple[str, ...]] = {
    "eat":       ("hunger", "food", "eat", "fed", "nourish", "sustain", "satiat", "meal"),
    "rest":      ("energy", "rest", "sleep", "recover", "regen", "heal", "restore"),
    "pickup":    ("gather", "collect", "pick", "inventory", "item", "resource", "obtain", "has"),
    "move":      ("reach", "arriv", "find", "locate", "travel", "explore", "scout", "move"),
    "innovate":  ("innovat", "create", "invent", "discover", "craft", "new action"),
    "communicate": ("communicat", "social", "talk", "message", "contact", "speak"),
    "give_item": ("give", "trade", "cooperat", "share", "transfer", "assist"),
    "teach":     ("teach", "knowledge", "skill", "pass", "share"),
    "reproduce": ("reproduc", "child", "offspring", "family"),
    "drop_item": ("drop", "place", "deposit"),
}

# Keywords in failure_signal that map to failed action types
_ACTION_FAILURE_HINTS: dict[str, tuple[str, ...]] = {
    "eat":       ("no food", "nothing to eat", "cannot eat", "starvation", "hungry"),
    "rest":      ("cannot rest", "no energy", "interrupted"),
    "pickup":    ("nothing here", "empty tile", "cannot pick", "no items"),
    "move":      ("blocked", "wall", "cannot move", "stuck", "bounds"),
    "innovate":  ("rejected", "cannot innovat", "failed innovat"),
}


def check_completion(subgoal: "PlanningSubgoal", agent: "Agent", oracle_result: dict,
                     action_str: str) -> bool:
    """
    Return True if the subgoal's completion_signal is satisfied.

    Checks in strict priority order — each stage is tried independently:
    1. Numeric state conditions (hunger < N, energy > N, life > N).
       These are evaluated against current agent state; oracle success not required.
    2. Inventory conditions (has X, inventory has X).
       Evaluated against current inventory; oracle success not required.
    3. Action-signal keyword match (oracle succeeded + keyword hint present).
       Only runs when the signal contains no numeric or inventory patterns,
       to avoid false positives from stat-name keywords in numeric signals.
    4. Kind-based fallback: subgoal.kind matches action_str verb (oracle succeeded).
    """
    signal = (subgoal.completion_signal or "").lower()
    if not signal:
        return False

    # --- 1. Numeric state checks (independent of oracle success) ---
    numeric_conditions = _extract_numeric_conditions(signal)
    for stat, (op, threshold) in numeric_conditions:
        actual = getattr(agent, stat, None)
        if actual is not None:
            if op == "<" and actual < threshold:
                return True
            if op == ">" and actual > threshold:
                return True
            if op == "<=" and actual <= threshold:
                return True
            if op == ">=" and actual >= threshold:
                return True

    # --- 2. Inventory conditions ---
    inv_match = re.search(
        r'(?:inventory has|has)\s+(\d+)?\s*([a-z][a-z_]*)',
        signal,
    )
    if inv_match:
        qty_str, item = inv_match.group(1), inv_match.group(2)
        qty = int(qty_str) if qty_str else 1
        if agent.inventory.has(item, qty):
            return True
        # Signal is inventory-based but condition not met — don't fall through
        # to keyword check, since keywords like "has" would match the signal text.
        if _is_inventory_signal(signal):
            return False

    # --- 3. Action-signal keyword match (only for non-state signals) ---
    # Skip if the signal encodes a numeric or inventory condition, to prevent
    # keywords like "hunger" or "has" from matching condition strings.
    if not numeric_conditions and not _is_inventory_signal(signal):
        if oracle_result.get("success"):
            hints = _ACTION_COMPLETION_HINTS.get(action_str, ())
            if any(kw in signal for kw in hints):
                return True

    # --- 4. Kind-based fallback ---
    kind = (subgoal.kind or "").lower().replace("_", " ")
    if kind and oracle_result.get("success"):
        action_words = set(action_str.replace("_", " ").split())
        kind_words = set(kind.split())
        if action_words & kind_words:
            return True

    return False


def check_failure(subgoal: "PlanningSubgoal", agent: "Agent", oracle_result: dict,
                  action_str: str, consecutive_failures: int) -> bool:
    """
    Return True if the subgoal should be marked as failed.

    A subgoal is considered failed when:
    - The oracle failed AND the failure_signal keywords match the action, OR
    - The agent has failed the same kind of action 3+ consecutive times.
    """
    if oracle_result.get("success"):
        return False

    failure_signal = (subgoal.failure_signal or "").lower()
    hints = _ACTION_FAILURE_HINTS.get(action_str, ())
    if failure_signal and any(kw in failure_signal for kw in hints):
        return True

    return consecutive_failures >= 3


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_numeric_conditions(signal: str) -> list[tuple[str, tuple[str, int]]]:
    """
    Extract patterns like 'hunger < 30', 'energy > 70', 'life >= 50'.
    Returns list of (stat_name, (operator, threshold)).
    """
    results = []
    pattern = re.compile(
        r'\b(hunger|energy|life)\s*(<=|>=|<|>)\s*(\d+)'
    )
    for m in pattern.finditer(signal):
        stat, op, val = m.group(1), m.group(2), int(m.group(3))
        results.append((stat, (op, val)))
    return results


def _is_inventory_signal(signal: str) -> bool:
    """Return True if the signal primarily describes an inventory condition."""
    return bool(re.search(r'\b(?:inventory has|has \w+ in inventory|has \w+ item)\b', signal))
