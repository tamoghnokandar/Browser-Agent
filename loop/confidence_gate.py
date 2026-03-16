"""
ConfidenceGate: CATTS-inspired multi-sampling.
Port of src/loop/confidence-gate.ts.
"""
from __future__ import annotations

from typing import Any, Dict, List

from model.adapter import ModelAdapter


def _bucket(n: float) -> int:
    return round(n / 64) * 64


def _action_key(action: dict[str, Any]) -> str:
    t = action.get("type", "")

    if t == "click":
        return f"click:{_bucket(action.get('x', 0))},{_bucket(action.get('y', 0))}"
    if t == "doubleClick":
        return f"dblclick:{_bucket(action.get('x', 0))},{_bucket(action.get('y', 0))}"
    if t == "type":
        return f"type:{action.get('text', '')[:50]}"
    if t == "keyPress":
        return f"key:{'+'.join(action.get('keys', []))}"
    if t == "goto":
        return f"goto:{action.get('url', '')}"
    if t == "scroll":
        return f"scroll:{action.get('direction', '')}"
    if t == "terminate":
        return f"terminate:{action.get('result', '')[:50]}"
    if t == "writeState":
        return "writeState"
    if t == "hover":
        return f"hover:{_bucket(action.get('x', 0))},{_bucket(action.get('y', 0))}"

    return str(t)


def _actions_match(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return _action_key(a) == _action_key(b)


def _get_usage_tokens(u: Dict[str, Any]) -> tuple[int, int]:
    """Extract input/output from usage dict (supports inputTokens or input_tokens)."""
    return (
        u.get("inputTokens", u.get("input_tokens", 0)),
        u.get("outputTokens", u.get("output_tokens", 0)),
    )


def _merge_usage(chosen: Dict[str, Any], all_responses: List[Dict[str, Any]]) -> Dict[str, Any]:
    total_input = 0
    total_output = 0
    for r in all_responses:
        u = r.get("usage") or {}
        ti, to = _get_usage_tokens(u)
        total_input += ti
        total_output += to

    return {
        **chosen,
        "usage": {
            "inputTokens": total_input,
            "outputTokens": total_output,
        },
    }


class ConfidenceGate:
    def __init__(self, adapter: ModelAdapter, samples: int = 3) -> None:
        self.adapter = adapter
        self.samples = samples

    def is_hard_step(self, pending_nudge: str | None, last_outcome_failed: bool) -> bool:
        return bool(pending_nudge) or last_outcome_failed

    async def decide(self, context: Dict[str, Any], is_hard: bool) -> Dict[str, Any]:
        if not is_hard:
            return await self.adapter.step(context)

        candidates: List[Dict[str, Any]] = []
        temps = [0.3, 0.7, 0.9][: self.samples]

        for temp in temps:
            ctx = {**context, "temperature": temp}
            response = await self.adapter.step(ctx)
            candidates.append(response)

        if not candidates:
            raise RuntimeError("ConfidenceGate.decide() produced no candidates")

        first_actions = [a[0] for a in (c.get("actions", []) for c in candidates) if a]
        first_actions = [a for a in first_actions if a is not None]

        # TS:
        # if (firstActions.length === 0) return candidates[0]!;
        if len(first_actions) == 0:
            return candidates[0]

        # TS:
        # const allAgree = firstActions.every((a) => actionsMatch(a, firstActions[0]!));
        all_agree = all(_actions_match(a, first_actions[0]) for a in first_actions)
        if all_agree:
            return _merge_usage(candidates[0], candidates)

        # TS majority vote over firstActions, ties go to first seen
        action_counts: dict[str, dict[str, int]] = {}
        for i, action in enumerate(first_actions):
            key = _action_key(action)
            existing = action_counts.get(key)
            if existing:
                existing["count"] += 1
            else:
                action_counts[key] = {"count": 1, "index": i}

        best_index = 0
        best_count = 0
        for entry in action_counts.values():
            if entry["count"] > best_count:
                best_count = entry["count"]
                best_index = entry["index"]

        return _merge_usage(candidates[best_index], candidates)