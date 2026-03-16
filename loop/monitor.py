"""
LoopMonitor: observability hooks. Port of src/loop/monitor.ts.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from model.adapter import ModelResponse, StepContext
from agent_types import Action, ActionExecution, LoopResult


class LoopMonitor(ABC):
    @abstractmethod
    def step_started(self, step: int, context: StepContext) -> None:
        pass

    @abstractmethod
    def step_completed(self, step: int, response: ModelResponse) -> None:
        pass

    @abstractmethod
    def action_executed(self, step: int, action: Action, outcome: ActionExecution) -> None:
        pass

    @abstractmethod
    def action_blocked(self, step: int, action: Action, reason: str) -> None:
        pass

    @abstractmethod
    def termination_rejected(self, step: int, reason: str) -> None:
        pass

    @abstractmethod
    def compaction_triggered(self, step: int, tokens_before: int, tokens_after: int) -> None:
        pass

    @abstractmethod
    def terminated(self, result: LoopResult) -> None:
        pass

    def error(self, err: Exception) -> None:
        pass


class ConsoleMonitor(LoopMonitor):
    def step_started(self, step: int, context: StepContext) -> None:
        max_steps = context.max_steps
        url = context.url
        print(f"[browser-agent] step {step + 1}/{max_steps} — {url}")

    def step_completed(self, step: int, response: ModelResponse) -> None:
        actions = response.actions if hasattr(response, "actions") else response.get("actions", [])
        actions_len = len(actions)
        usage = response.usage if hasattr(response, "usage") else response.get("usage")
        input_tokens = (
            usage.get("inputTokens", usage.get("input_tokens", 0))
            if isinstance(usage, dict)
            else getattr(usage, "input_tokens", 0)
        )
        print(f"[browser-agent] step {step + 1} complete — {actions_len} action(s), {input_tokens} input tokens")

    def action_executed(self, step: int, action: Action, outcome: ActionExecution) -> None:
        if not outcome.ok:
            action_type = action["type"]
            print(f'[browser-agent] step {step + 1} action "{action_type}" failed: {outcome.error}')

    def action_blocked(self, step: int, action: Action, reason: str) -> None:
        action_type = action["type"]
        print(f'[browser-agent] step {step + 1} action "{action_type}" blocked: {reason}')

    def termination_rejected(self, step: int, reason: str) -> None:
        print(f"[browser-agent] step {step + 1} termination rejected: {reason}")

    def compaction_triggered(self, step: int, tokens_before: int, tokens_after: int) -> None:
        print(f"[browser-agent] step {step + 1} compaction — {tokens_before} → {tokens_after} tokens")

    def terminated(self, result: LoopResult) -> None:
        print(f"[browser-agent] done — status: {result.status}, steps: {result.steps}")
        print(f"[browser-agent] result: {result.result}")

    def error(self, err: Exception) -> None:
        print(f"[browser-agent] error: {err}")


class NoopMonitor(LoopMonitor):
    def step_started(self, step: int, context: StepContext) -> None:
        pass

    def step_completed(self, step: int, response: ModelResponse) -> None:
        pass

    def action_executed(self, step: int, action: Action, outcome: ActionExecution) -> None:
        pass

    def action_blocked(self, step: int, action: Action, reason: str) -> None:
        pass

    def termination_rejected(self, step: int, reason: str) -> None:
        pass

    def compaction_triggered(self, step: int, tokens_before: int, tokens_after: int) -> None:
        pass

    def terminated(self, result: LoopResult) -> None:
        pass
