"""
Session: brings tab + adapter + perception loop together. Port of src/session.ts.
"""
from __future__ import annotations

import hashlib
from typing import Any, Dict, NotRequired, Optional, TypedDict

from browser.tab import BrowserTab
from logger import BrowserAgentLogger
from loop.checkpoint import CheckpointManager
from loop.confidence_gate import ConfidenceGate
from loop.history import HistoryManager
from loop.monitor import LoopMonitor
from loop.perception import LoopOptions, PerceptionLoop, PerceptionLoopOptions
from loop.policy import SessionPolicy, SessionPolicyOptions
from loop.router import RouterTiming
from loop.state import StateStore
from loop.verifier import Verifier
from memory.site_kb import SiteKB
from memory.workflow import WorkflowMemory
from model.adapter import ModelAdapter
from agent_types import PreActionHook, SerializedHistory, TaskState


class SessionOptions(TypedDict):
    tab: "BrowserTab"
    adapter: "ModelAdapter"

    log: NotRequired[Any]
    system_prompt: NotRequired[Optional[str]]
    max_steps: NotRequired[int]
    compaction_threshold: NotRequired[float]
    keep_recent_screenshots: NotRequired[int]
    cursor_overlay: NotRequired[bool]
    timing: NotRequired["RouterTiming"]
    policy: NotRequired["SessionPolicyOptions" | Dict[str, Any]]
    pre_action_hook: NotRequired["PreActionHook"]
    verifier: NotRequired["Verifier"]
    monitor: NotRequired["LoopMonitor"]
    compaction_adapter: NotRequired["ModelAdapter"]
    initial_history: NotRequired["SerializedHistory"]
    initial_state: NotRequired["TaskState"]
    cache_dir: NotRequired[Optional[str]]
    confidence_gate: NotRequired["ConfidenceGate"]
    action_verifier: NotRequired[Any]
    checkpoint_manager: NotRequired["CheckpointManager"]
    site_kb: NotRequired["SiteKB"]
    workflow_memory: NotRequired["WorkflowMemory"]


class Session:
    def __init__(self, opts: SessionOptions) -> None:
        self.tab = opts["tab"]
        self.adapter = opts["adapter"]
        self._opts = opts
        self._log = opts.get("log") or BrowserAgentLogger.noop()
        self.history = HistoryManager(
            getattr(opts["adapter"], "context_window_tokens", 128000)
        )
        self.state = StateStore()

        initial_state = opts.get("initial_state")
        if initial_state:
            self.state.load(initial_state)

        initial_history = opts.get("initial_history")
        if initial_history:
            raw = initial_history
            data: Dict[str, Any] = (
                raw
                if isinstance(raw, dict)
                else {
                    "wireHistory": getattr(raw, "wire_history", []),
                    "semanticSteps": getattr(raw, "semantic_steps", []),
                    "agentState": getattr(raw, "agent_state", None),
                }
            )
            self.history, agent_state = HistoryManager.from_json(
                data,
                getattr(opts["adapter"], "context_window_tokens", 128000),
            )
            self.state.load(agent_state)
            wire_len = len(data.get("wireHistory", []))
            self._log.loop(
                f"session resumed: wire={wire_len}msgs hasState={agent_state is not None}",
                {"wireLen": wire_len, "hasState": agent_state is not None}
            )

    async def run(self, options: Dict[str, Any]) -> Dict[str, Any]:
        max_steps = options.get("max_steps")
        if max_steps is None:
            max_steps = self._opts.get("max_steps", 30)

        instruction = options.get("instruction", "")
        instruction_slice = instruction[:80] if instruction else ""
        instruction_len = len(instruction) if instruction else 0
        self._log.loop(
            f'session.run: instruction="{instruction_slice}" maxSteps={max_steps}',
            {"maxSteps": max_steps, "instructionLen": instruction_len}
        )
        start_url = options.get("start_url")

        policy = None
        if self._opts.get("policy"):
            from loop.policy import SessionPolicyOptions

            po = self._opts["policy"]
            if isinstance(po, dict):
                po = SessionPolicyOptions(
                    allowed_domains=po.get("allowed_domains"),
                    blocked_domains=po.get("blocked_domains"),
                    allowed_actions=po.get("allowed_actions"),
                )
            policy = SessionPolicy(po)

        loop_opts = PerceptionLoopOptions(
            tab=self.tab,
            adapter=self.adapter,
            history=self.history,
            state=self.state,
            policy=policy,
            verifier=self._opts.get("verifier"),
            monitor=self._opts.get("monitor"),
            timing=self._opts.get("timing"),
            pre_action_hook=self._opts.get("pre_action_hook"),
            keep_recent_screenshots=self._opts.get("keep_recent_screenshots", 2),
            cursor_overlay=self._opts.get("cursor_overlay", True),
            compaction_adapter=self._opts.get("compaction_adapter"),
            log=self._log,
            cache_dir=self._opts.get("cache_dir"),
            confidence_gate=self._opts.get("confidence_gate"),
            action_verifier=self._opts.get("action_verifier"),
            checkpoint_manager=self._opts.get("checkpoint_manager"),
            site_kb=self._opts.get("site_kb"),
            workflow_memory=self._opts.get("workflow_memory"),
        )

        system_prompt = (
            "\n\n".join(
                filter(
                    None,
                    [
                        f"Task: {instruction}" if instruction else "",
                        self._opts.get("system_prompt", ""),
                    ],
                )
            )
            or None
        )

        instruction_hash = None
        if self._opts.get("cache_dir") and instruction:
            instruction_hash = hashlib.sha256(instruction.encode()).hexdigest()[:16]

        if start_url:
            current_url = None
            try:
                current_url = self.tab.url()
            except Exception:
                current_url = None
            if current_url != start_url:
                try:
                    await self.tab.goto(start_url)
                except Exception:
                    pass

        loop = PerceptionLoop(loop_opts)
        run_opts = LoopOptions(
            max_steps=max_steps,
            system_prompt=system_prompt,
            compaction_threshold=self._opts.get("compaction_threshold", 0.8),
            instruction_hash=instruction_hash,
        )
        loop_result = await loop.run(run_opts)
        self._log.loop(
            f"session.run done: status={loop_result.status} steps={loop_result.steps}",
            {"status": loop_result.status, "steps": loop_result.steps}
        )
        token_usage = self.history.aggregate_token_usage()
        return {
            "status": loop_result.status,
            "result": loop_result.result,
            "steps": loop_result.steps,
            "history": loop_result.history,
            "agentState": loop_result.agent_state,
            "tokenUsage": token_usage,
        }

    def serialize(self) -> Dict[str, Any]:
        return self.history.to_json(self.state.current())

    @classmethod
    def resume(cls, data: "SerializedHistory", opts: SessionOptions) -> "Session":
        next_opts: SessionOptions = dict(opts)
        next_opts["initial_history"] = data
        return cls(next_opts)

    async def close(self) -> None:
        await self.tab.close()