"""
HistoryManager: wire + semantic history. Port of src/loop/history.ts.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

from model.adapter import ModelAdapter
from agent_types import Action, ActionExecution, SemanticStep, TaskState, TokenUsage, WireMessage


class HistoryManager:
    def __init__(self, context_window_tokens: int) -> None:
        self._wire: List[WireMessage] = []
        self._semantic: List[SemanticStep] = []
        self._total_input_tokens = 0
        self._last_response: Optional[Dict[str, Any]] = None
        self._folded_summaries: List[str] = []

        # Tracks (action, toolCallId) pairs awaiting tool_result
        self._pending_tool_calls: List[Dict[str, Any]] = []

        self._context_window_tokens = context_window_tokens

    # ─── Wire history ──────────────────────────────────────────────────────

    def wire_history(self) -> List[WireMessage]:
        return list(self._wire)

    def append_action_outcome(self, action: Action, outcome: ActionExecution) -> None:
        # TS uses reference equality (p.action === action), so use identity here.
        pending = next(
            (p for p in self._pending_tool_calls if p["action"] is action),
            None,
        )

        action_type = action["type"]
        tool_call_id = (
            pending["toolCallId"]
            if pending is not None
            else f"toolu_{action_type}_{int(time.time() * 1000)}"
        )

        if pending is not None:
            self._pending_tool_calls = [
                p for p in self._pending_tool_calls if p is not pending
            ]

        msg: WireMessage = {
            "role": "tool_result",
            "tool_call_id": tool_call_id,
            "action": action_type,
            "ok": outcome.ok,
        }
        if outcome.error:
            msg["error"] = outcome.error
            msg["is_error"] = True

        self._wire.append(msg)

    def append_response(self, response: Dict[str, Any]) -> None:
        self._last_response = response

        usage = response.get("usage") or {}
        input_tokens = usage.get("inputTokens", usage.get("input_tokens", 0))
        self._total_input_tokens += int(input_tokens)

        tool_call_ids = response.get("toolCallIds", response.get("tool_call_ids"))
        actions = response.get("actions", [])

        if tool_call_ids:
            for i, tool_call_id in enumerate(tool_call_ids):
                if tool_call_id and i < len(actions):
                    self._pending_tool_calls.append(
                        {"action": actions[i], "toolCallId": tool_call_id}
                    )

        self._wire.append({
            "role": "assistant",
            "actions": actions,
            "tool_call_ids": tool_call_ids,
            "thinking": response.get("thinking"),
        })

    # ─── Semantic history (never compressed) ───────────────────────────────

    def semantic_history(self) -> List[SemanticStep]:
        return list(self._semantic)

    def append_semantic_step(self, step: SemanticStep) -> None:
        self._semantic.append(step)

    # ─── Token tracking ────────────────────────────────────────────────────

    def get_total_input_tokens(self) -> int:
        return self._total_input_tokens

    def token_utilization(self) -> float:
        return min(self._total_input_tokens / self._context_window_tokens, 1.0)

    def append_screenshot(self, base64: str, step_index: int) -> None:
        self._wire.append(
            {
                "role": "screenshot",
                "base64": base64,
                "stepIndex": step_index,
                "compressed": False,
            }
        )

    # ─── Fold (agent-controlled context compression) ───────────────────────

    def add_fold(self, summary: str) -> None:
        self._folded_summaries.append(summary)
        # Aggressively compress old screenshots when folding
        self.compress_screenshots(1)

    def get_folded_context(self) -> Optional[str]:
        if not self._folded_summaries:
            return None
        return "COMPLETED SUB-GOALS:\n" + "\n".join(
            f"{i + 1}. {summary}" for i, summary in enumerate(self._folded_summaries)
        )

    # ─── Compression ───────────────────────────────────────────────────────

    def compress_screenshots(self, keep_recent: Optional[int] = 2) -> None:
        keep_recent = keep_recent if keep_recent is not None else 2
        screenshot_indices = [
            i for i, msg in enumerate(self._wire) if msg.get("role") == "screenshot"
        ]

        compress_up_to = len(screenshot_indices) - keep_recent
        for k in range(max(0, compress_up_to)):
            idx = screenshot_indices[k]
            msg = self._wire[idx]
            self._wire[idx] = {**msg, "base64": None, "compressed": True}

    async def compact_with_summary(
        self,
        adapter: ModelAdapter,
        agent_state: Optional[TaskState],
    ) -> Dict[str, int]:
        tokens_before = self._total_input_tokens

        summary = await adapter.summarize(self._wire, agent_state)

        self._wire = [
            {
                "role": "summary",
                "content": summary,
                "compactedAt": int(time.time() * 1000),
            }
        ]
        self._total_input_tokens = round(tokens_before * 0.15)

        return {
            "tokensBefore": tokens_before,
            "tokensAfter": self._total_input_tokens,
        }

    # ─── Serialization ─────────────────────────────────────────────────────

    def to_json(self, agent_state: Optional[TaskState]) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "wireHistory": self._wire,
            "semanticSteps": self._semantic,
            "agentState": agent_state,
        }
        if self._folded_summaries:
            data["foldedSummaries"] = self._folded_summaries
        return data

    @classmethod
    def from_json(
        cls,
        data: Dict[str, Any],
        context_window_tokens: int,
    ) -> Tuple["HistoryManager", Optional[TaskState]]:
        history = cls(context_window_tokens)
        history._wire = data.get("wireHistory", [])
        history._semantic = data.get("semanticSteps", [])
        if "foldedSummaries" in data and data["foldedSummaries"] is not None:
            history._folded_summaries = data["foldedSummaries"]
        return history, data.get("agentState")

    # ─── Aggregate usage ───────────────────────────────────────────────────

    def aggregate_token_usage(self) -> Dict[str, int]:
        acc = {
            "inputTokens": 0,
            "outputTokens": 0,
            "cacheReadTokens": 0,
            "cacheWriteTokens": 0,
        }

        for step in self._semantic:
            tu = step.token_usage if hasattr(step, "token_usage") else (step.get("token_usage") or step.get("tokenUsage"))
            if tu is None:
                continue

            u: Dict[str, int] = (
                tu
                if isinstance(tu, dict)
                else {
                    "inputTokens": tu.input_tokens,
                    "outputTokens": tu.output_tokens,
                    "cacheReadTokens": tu.cache_read_tokens or 0,
                    "cacheWriteTokens": tu.cache_write_tokens or 0,
                }
            )
            acc["inputTokens"] += u.get("inputTokens", u.get("input_tokens", 0))
            acc["outputTokens"] += u.get("outputTokens", u.get("output_tokens", 0))
            acc["cacheReadTokens"] += u.get("cacheReadTokens", u.get("cache_read_tokens", 0)) or 0
            acc["cacheWriteTokens"] += u.get("cacheWriteTokens", u.get("cache_write_tokens", 0)) or 0

        return acc