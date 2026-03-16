from __future__ import annotations

import asyncio
import base64
import inspect
import json
from dataclasses import asdict, dataclass, is_dataclass
from time import time
from typing import Any, AsyncIterable, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from browser.tab import BrowserTab
from logger import BrowserAgentLogger
from memory.site_kb import SiteKB
from memory.workflow import WorkflowMemory
from model.adapter import ModelAdapter
from agent_types import (
    Action,
    ActionExecution,
    LoopOptions,
    LoopResult,
    PreActionHook,
    ScreenshotOptions,
    ScreenshotResult,
    SemanticStep,
    TokenUsage,
)
from .action_cache import ActionCache, screenshot_hash, viewport_mismatch
from .action_verifier import ActionVerifier
from .checkpoint import CheckpointManager
from .confidence_gate import ConfidenceGate
from .history import HistoryManager
from .monitor import ConsoleMonitor, LoopMonitor
from .policy import SessionPolicy
from .repeat_detector import RepeatDetector, nudge_message
from .router import ActionRouter
from .state import StateStore
from .verifier import Verifier


@dataclass
class ModelResponse:
    actions: List[Action]
    tool_call_ids: Optional[List[str]] = None
    thinking: Optional[str] = None
    usage: Optional[Dict[str, int]] = None
    raw_response: Any = None

    def __post_init__(self) -> None:
        if self.tool_call_ids is None:
            self.tool_call_ids = []
        if self.usage is None:
            self.usage = {"inputTokens": 0, "outputTokens": 0}


@dataclass
class StepContext:
    screenshot: ScreenshotResult
    wire_history: List[Any]
    agent_state: Dict[str, Any]
    step_index: int
    max_steps: int
    url: str
    system_prompt: Optional[str]


def _step_context_to_dict(ctx: StepContext) -> Dict[str, Any]:
    """Convert StepContext to dict for adapter.stream/step and confidence_gate.decide."""
    return {
        "screenshot": ctx.screenshot,
        "wire_history": ctx.wire_history,
        "agent_state": ctx.agent_state,
        "step_index": ctx.step_index,
        "max_steps": ctx.max_steps,
        "url": ctx.url,
        "system_prompt": ctx.system_prompt,
    }


def _to_base64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _get_last_stream_response(adapter: Any) -> Any:
    for name in ("get_last_stream_response", "getLastStreamResponse"):
        getter = getattr(adapter, name, None)
        if callable(getter):
            return getter()
    return None


def _usage_to_token_usage(usage: Any) -> TokenUsage:
    if usage is None:
        return TokenUsage(input_tokens=0, output_tokens=0)

    if isinstance(usage, TokenUsage):
        return usage

    if isinstance(usage, dict):
        return TokenUsage(
            input_tokens=usage.get("inputTokens", usage.get("input_tokens", 0)),
            output_tokens=usage.get("outputTokens", usage.get("output_tokens", 0)),
            cache_read_tokens=usage.get("cacheReadTokens", usage.get("cache_read_tokens")),
            cache_write_tokens=usage.get("cacheWriteTokens", usage.get("cache_write_tokens")),
        )

    return TokenUsage(
        input_tokens=getattr(usage, "inputTokens", getattr(usage, "input_tokens", 0)),
        output_tokens=getattr(usage, "outputTokens", getattr(usage, "output_tokens", 0)),
        cache_read_tokens=getattr(usage, "cacheReadTokens", getattr(usage, "cache_read_tokens")),
        cache_write_tokens=getattr(usage, "cacheWriteTokens", getattr(usage, "cache_write_tokens")),
    )


def _usage_to_dict(usage: Any) -> Dict[str, int]:
    tu = _usage_to_token_usage(usage)
    out: Dict[str, int] = {
        "inputTokens": tu.input_tokens,
        "outputTokens": tu.output_tokens,
    }
    if tu.cache_read_tokens is not None:
        out["cacheReadTokens"] = tu.cache_read_tokens
    if tu.cache_write_tokens is not None:
        out["cacheWriteTokens"] = tu.cache_write_tokens
    return out


def _semantic_step_to_workflow_dict(step: SemanticStep) -> Dict[str, Any]:
    """
    WorkflowMemory.extract currently expects history entries that behave like dicts:
      step.get("actions", []), step.get("url", "")
    and action entries like {"action": ...}.
    Convert SemanticStep dataclasses into that shape.
    """
    if isinstance(step, dict):
        return step

    if is_dataclass(step):
        return {
            "step_index": step.step_index,
            "url": step.url,
            "screenshot_base64": step.screenshot_base64,
            "thinking": step.thinking,
            "actions": step.actions,
            "agent_state": step.agent_state,
            "token_usage": asdict(step.token_usage) if is_dataclass(step.token_usage) else step.token_usage,
            "duration_ms": step.duration_ms,
        }

    return {
        "url": getattr(step, "url", ""),
        "actions": getattr(step, "actions", []),
    }


def is_productive_action(action: Action) -> bool:
    return action["type"] in {
        "click",
        "doubleClick",
        "goto",
        "writeState",
        "terminate",
        "type",
        "delegate",
        "fold",
    }


def is_url_escape_action(action: Action) -> bool:
    return action["type"] in {"writeState", "terminate"}


def normalize_url_for_stall(url: str) -> str:
    try:
        u = urlparse(url)
        return f"{u.scheme}://{u.netloc}{u.path}"
    except Exception:
        return url


@dataclass
class PerceptionLoopOptions:
    tab: BrowserTab
    adapter: ModelAdapter
    history: HistoryManager
    state: StateStore
    policy: Optional[SessionPolicy] = None
    verifier: Optional[Verifier] = None
    monitor: Optional[LoopMonitor] = None
    timing: Optional[Any] = None
    pre_action_hook: Optional[PreActionHook] = None
    keep_recent_screenshots: int = 2
    cursor_overlay: bool = True
    compaction_adapter: Optional[ModelAdapter] = None
    log: Optional[BrowserAgentLogger] = None
    cache_dir: Optional[str] = None
    confidence_gate: Optional[ConfidenceGate] = None
    action_verifier: Optional[ActionVerifier] = None
    checkpoint_manager: Optional[CheckpointManager] = None
    site_kb: Optional[SiteKB] = None
    workflow_memory: Optional[WorkflowMemory] = None


class PerceptionLoop:
    def __init__(self, opts: PerceptionLoopOptions) -> None:
        self.tab = opts.tab
        self.adapter = opts.adapter
        self.history = opts.history
        self.state = opts.state
        self.policy = opts.policy
        self.verifier = opts.verifier
        self.monitor = opts.monitor or ConsoleMonitor()
        self.pre_action_hook = opts.pre_action_hook
        self.keep_recent_screenshots = opts.keep_recent_screenshots
        self.cursor_overlay = opts.cursor_overlay
        self.compaction_adapter = opts.compaction_adapter or opts.adapter
        self.log = opts.log or BrowserAgentLogger.noop()
        self.router = ActionRouter(opts.timing, self.log)
        self.action_cache = ActionCache(opts.cache_dir) if opts.cache_dir else None
        self.confidence_gate = opts.confidence_gate
        self.action_verifier = opts.action_verifier
        self.checkpoint_manager = opts.checkpoint_manager
        self.site_kb = opts.site_kb
        self.workflow_memory = opts.workflow_memory
        self.repeat_detector = RepeatDetector()

    async def _try_cache(
        self,
        step: int,
        url: str,
        instruction_hash: str,
        screenshot: ScreenshotResult,
        tab: BrowserTab,
    ) -> Optional[Tuple[Action, ActionExecution]]:
        if not self.action_cache:
            return None

        try:
            key = self.action_cache.step_key(url, instruction_hash)
            cached = await self.action_cache.get(key)
            if not cached:
                return None

            self.log.loop(
                f"step {step + 1}: cache HIT — replaying {cached.get('type')} action"
            )

            viewport = {"width": screenshot.width, "height": screenshot.height}
            if viewport_mismatch(cached, viewport):
                cv = cached.get("viewport") or {}
                self.log.loop(
                    f"step {step + 1}: viewport mismatch — cached {cv.get('width')}x{cv.get('height')}, "
                    f"current {viewport['width']}x{viewport['height']}",
                )

            action = cached.get("args")
            if not isinstance(action, dict):
                action = {"type": str(cached.get("type", "screenshot"))}

            outcome = await self.router.execute(action, tab, self.state)

            if not outcome.ok:
                self.log.loop(
                    f"step {step + 1}: cached action FAILED ({outcome.error}) — self-healing via model",
                )
                return None

            tool_call_id = f"toolu_cache_{int(time() * 1000)}"
            synthetic = {
                "actions": [action],
                "tool_call_ids": [tool_call_id],
                "thinking": None,
                "usage": {"inputTokens": 0, "outputTokens": 0},
            }
            self.history.append_response(synthetic)
            self.history.append_action_outcome(action, outcome)

            return action, outcome
        except Exception as err:
            self.log.loop(f"step {step + 1}: cache error — {err}")
            return None

    def _spawn_cache_write(
        self,
        key: str,
        action: Action,
        url: str,
        instruction_hash: str,
        screenshot_digest: str,
        viewport: Dict[str, int],
    ) -> None:
        if not self.action_cache:
            return

        async def _write() -> None:
            try:
                await self.action_cache.set(
                    key,
                    action,
                    url,
                    instruction_hash,
                    screenshot_digest,
                    viewport,
                )
            except Exception:
                pass

        asyncio.create_task(_write())

    async def run(self, options: LoopOptions) -> LoopResult:
        threshold = (
            options.compaction_threshold
            if options.compaction_threshold is not None
            else 0.8
        )

        pending_nudge: Optional[str] = None
        nudge_source: Optional[str] = None
        last_normalized_url = ""
        last_outcome_failed = False
        has_backtracked = False

        for step in range(options.max_steps):
            if self.log.loop_enabled:
                util = self.history.token_utilization()
                total_tokens = self.history.get_total_input_tokens()
                ctx_tokens = self.adapter.context_window_tokens
                wire_len = len(self.history.wire_history())
                self.log.loop(
                    f"step {step + 1}/{options.max_steps} start | url={self.tab.url()} "
                    f"wire={wire_len}msgs util={util * 100:.1f}% ({total_tokens}/{ctx_tokens})",
                    {
                        "step": step + 1,
                        "url": self.tab.url(),
                        "wireLen": wire_len,
                        "util": util,
                        "totalTokens": total_tokens,
                        "ctxTokens": ctx_tokens,
                    },
                )

            if self.history.token_utilization() > threshold:
                util = self.history.token_utilization()
                self.log.history(
                    f"step {step + 1}: tier-2 compaction triggered "
                    f"(util={util * 100:.1f}% > threshold={threshold * 100:.0f}%)",
                )

                comp = await self.history.compact_with_summary(
                    self.compaction_adapter,
                    self.state.current(),
                )
                tokens_before = comp.get("tokensBefore", 0)
                tokens_after = comp.get("tokensAfter", 0)

                self.monitor.compaction_triggered(step, tokens_before, tokens_after)

                reduction_pct = 0.0
                if tokens_before > 0:
                    reduction_pct = 100.0 - (tokens_after / tokens_before) * 100.0

                self.log.history(
                    f"step {step + 1}: tier-2 done | {tokens_before} → {tokens_after} tokens "
                    f"(~{reduction_pct:.0f}% reduction)",
                    {"tokensBefore": tokens_before, "tokensAfter": tokens_after},
                )

                self.history.compress_screenshots(self.keep_recent_screenshots)
                self.log.history(
                    f"step {step + 1}: tier-1 compress (post-compaction) | "
                    f"keepRecent={self.keep_recent_screenshots}",
                )

            current_normalized = normalize_url_for_stall(self.tab.url())
            if nudge_source == "url" and current_normalized != last_normalized_url:
                pending_nudge = None
                nudge_source = None
                has_backtracked = False
            last_normalized_url = current_normalized

            url_stall = self.repeat_detector.record_url(self.tab.url())
            if url_stall is not None:
                self.log.loop(
                    f"step {step + 1}: URL stall detected at level {url_stall} (url={self.tab.url()})",
                )

                if (
                    url_stall >= 8
                    and self.checkpoint_manager is not None
                    and not has_backtracked
                ):
                    checkpoint = await self.checkpoint_manager.restore(self.tab)
                    if checkpoint:
                        has_backtracked = True
                        if getattr(checkpoint, "agent_state", None):
                            self.state.write(checkpoint.agent_state)

                        pending_nudge = (
                            f"BACKTRACKED to step {checkpoint.step}. "
                            "Your previous approach was stuck. Try a COMPLETELY different strategy — "
                            "different elements, different navigation path, or URL parameters."
                        )
                        nudge_source = "url"

                        self.log.loop(
                            f"step {step + 1}: backtracked to checkpoint at step {checkpoint.step}",
                        )
                    else:
                        pending_nudge = nudge_message(url_stall, "url")
                        nudge_source = "url"
                else:
                    pending_nudge = nudge_message(url_stall, "url")
                    nudge_source = "url"

            if self.checkpoint_manager and step % self.checkpoint_manager.interval == 0:
                await self.checkpoint_manager.save(
                    step,
                    self.tab.url(),
                    self.state.current(),
                    self.tab,
                )

            screenshot: ScreenshotResult = await self.tab.screenshot(
                ScreenshotOptions(cursor_overlay=self.cursor_overlay)
            )
            current_screenshot_hash = (
                screenshot_hash(screenshot.data) if self.action_cache else None
            )
            screenshot_b64 = _to_base64(screenshot.data)

            self.history.append_screenshot(screenshot_b64, step)

            prompt_parts: List[str] = []

            folded = self.history.get_folded_context()
            if folded:
                prompt_parts.append(folded)

            if self.site_kb:
                site_tips = self.site_kb.format_for_prompt(self.tab.url())
                if site_tips:
                    prompt_parts.append(site_tips)

            if step == 0 and self.workflow_memory and options.system_prompt:
                wf = self.workflow_memory.match(options.system_prompt, self.tab.url())
                if wf:
                    prompt_parts.append(self.workflow_memory.to_prompt_hint(wf))

            if pending_nudge:
                prompt_parts.append(pending_nudge)

            if options.system_prompt:
                prompt_parts.append(options.system_prompt)

            step_system_prompt = "\n\n".join(prompt_parts) if prompt_parts else None

            ctx = StepContext(
                screenshot=screenshot,
                wire_history=self.history.wire_history(),
                agent_state=self.state.current(),
                step_index=step,
                max_steps=options.max_steps,
                url=self.tab.url(),
                system_prompt=step_system_prompt,
            )
            self.monitor.step_started(step, ctx)

            if options.instruction_hash:
                cache_hit = await self._try_cache(
                    step,
                    self.tab.url(),
                    options.instruction_hash,
                    screenshot,
                    self.tab,
                )
                if cache_hit:
                    action, outcome = cache_hit

                    repeat_level = self.repeat_detector.record(action)
                    if repeat_level is not None:
                        pending_nudge = nudge_message(repeat_level)
                        nudge_source = "action"

                    if outcome.terminated:
                        result = LoopResult(
                            status=outcome.status or "success",
                            result=outcome.result or "",
                            steps=step + 1,
                            history=[],
                            agent_state=self.state.current(),
                        )

                        self.history.append_semantic_step(
                            SemanticStep(
                                step_index=step,
                                url=self.tab.url(),
                                screenshot_base64=screenshot_b64,
                                thinking=None,
                                actions=[
                                    {
                                        "action": action,
                                        "outcome": {
                                            "ok": outcome.ok,
                                            "error": outcome.error,
                                        },
                                    }
                                ],
                                agent_state=self.state.current(),
                                token_usage=TokenUsage(
                                    input_tokens=0,
                                    output_tokens=0,
                                ),
                                duration_ms=0,
                            )
                        )

                        result.history = self.history.semantic_history()
                        self.monitor.step_completed(
                            step,
                            ModelResponse(
                                actions=[action],
                                usage={"inputTokens": 0, "outputTokens": 0},
                                raw_response=None,
                            ),
                        )
                        self.monitor.terminated(result)
                        return result

                    self.history.append_semantic_step(
                        SemanticStep(
                            step_index=step,
                            url=self.tab.url(),
                            screenshot_base64=screenshot_b64,
                            thinking=None,
                            actions=[
                                {
                                    "action": action,
                                    "outcome": {
                                        "ok": outcome.ok,
                                        "error": outcome.error,
                                    },
                                }
                            ],
                            agent_state=self.state.current(),
                            token_usage=TokenUsage(
                                input_tokens=0,
                                output_tokens=0,
                            ),
                            duration_ms=0,
                        )
                    )

                    self.monitor.action_executed(step, action, outcome)
                    self.monitor.step_completed(
                        step,
                        ModelResponse(
                            actions=[action],
                            usage={"inputTokens": 0, "outputTokens": 0},
                            raw_response=None,
                        ),
                    )

                    self.history.compress_screenshots(self.keep_recent_screenshots)
                    continue

            step_start = time()
            step_actions: List[Dict[str, Any]] = []
            step_usage = TokenUsage(input_tokens=0, output_tokens=0)
            thinking: Optional[str] = None

            buffered_outcomes: List[Dict[str, Any]] = []
            terminated = False
            termination_result: Optional[LoopResult] = None

            self.log.adapter(
                f"step {step + 1}: stream start | model={self.adapter.model_id} "
                f"histMsgs={len(ctx.wire_history)}",
                {
                    "step": step + 1,
                    "model": self.adapter.model_id,
                    "histMsgs": len(ctx.wire_history),
                },
            )
            model_t0 = time()

            use_conf_gate = (
                self.confidence_gate is not None
                and self.confidence_gate.is_hard_step(pending_nudge, last_outcome_failed)
            )
            ctx_dict = _step_context_to_dict(ctx)

            if use_conf_gate and self.confidence_gate:
                stream_response: Dict[str, Any] = await self.confidence_gate.decide(ctx_dict, True)

                async def _gate_gen() -> AsyncIterable[Action]:
                    for a in stream_response.get("actions", []):
                        yield a

                action_source: AsyncIterable[Action] = _gate_gen()
            else:
                action_source = self.adapter.stream(ctx_dict)
                stream_response = None

            pre_action_url = self.tab.url()

            async for action in action_source:
                if terminated:
                    continue

                if self.pre_action_hook:
                    hook_result = self.pre_action_hook(action)
                    hook_decision: Dict[str, Any] = await _maybe_await(hook_result)
                    if hook_decision.get("decision", "") == "deny":
                        reason = hook_decision.get("reason", "")
                        self.log.loop(
                            f'step {step + 1}: action "{action["type"]}" '
                            f"denied by preActionHook: {reason}",
                        )
                        wire_outcome = {"ok": False, "error": reason}
                        buffered_outcomes.append(
                            {"action": action, "wireOutcome": wire_outcome}
                        )
                        self.monitor.action_blocked(step, action, reason)
                        step_actions.append({"action": action, "outcome": wire_outcome})
                        continue

                if self.policy:
                    policy_result = self.policy.check(action)
                    if not policy_result.allowed:
                        reason = policy_result.reason or ""
                        self.log.loop(
                            f'step {step + 1}: action "{action["type"]}" '
                            f"blocked by policy: {reason}",
                        )
                        wire_outcome = {"ok": False, "error": reason}
                        buffered_outcomes.append(
                            {"action": action, "wireOutcome": wire_outcome}
                        )
                        self.monitor.action_blocked(step, action, reason)
                        step_actions.append({"action": action, "outcome": wire_outcome})
                        continue

                outcome = await self.router.execute(action, self.tab, self.state)

                if action["type"] == "fold":
                    summary = action.get("summary", "")
                    self.history.add_fold(summary)
                    self.log.loop(f'step {step + 1}: fold — "{summary[:60]}"')
                    buffered_outcomes.append(
                        {"action": action, "wireOutcome": {"ok": True}}
                    )
                    step_actions.append({"action": action, "outcome": {"ok": True}})
                    continue

                if (
                    self.action_verifier
                    and not outcome.terminated
                    and not outcome.is_delegate_request
                ):
                    verification = await self.action_verifier.verify(
                        action, outcome, self.tab, pre_action_url
                    )
                    if not verification.success and verification.hint:
                        hint = verification.hint
                        if pending_nudge:
                            pending_nudge = f"{pending_nudge}\n\n{hint}"
                        else:
                            pending_nudge = hint
                            nudge_source = "action"
                        last_outcome_failed = True

                if outcome.terminated:
                    if self.verifier:
                        current_screenshot = await self.tab.screenshot()
                        verify_result = await self.verifier.verify(
                            current_screenshot,
                            self.tab.url(),
                        )
                        if not verify_result.passed:
                            reason = verify_result.reason or "completion condition not met"
                            self.log.loop(
                                f"step {step + 1}: termination rejected by verifier: {reason}",
                            )
                            wire_outcome = {
                                "ok": False,
                                "error": f"terminate rejected: {reason}",
                            }
                            buffered_outcomes.append(
                                {"action": action, "wireOutcome": wire_outcome}
                            )
                            self.monitor.termination_rejected(step, reason)
                            step_actions.append({"action": action, "outcome": wire_outcome})
                            continue

                    terminated = True
                    buffered_outcomes.append(
                        {"action": action, "wireOutcome": {"ok": True}}
                    )
                    termination_result = LoopResult(
                        status=outcome.status or "success",
                        result=outcome.result or "",
                        steps=step + 1,
                        history=[],
                        agent_state=self.state.current(),
                    )
                    self.log.loop(
                        f'step {step + 1}: termination accepted | status={outcome.status} '
                        f'result="{(outcome.result or "")[:80]}"',
                    )
                    continue

                if outcome.is_delegate_request:
                    self.log.loop(
                        f'step {step + 1}: spawning child loop — '
                        f'"{(outcome.delegate_instruction or "")[:60]}" '
                        f"max_steps={outcome.delegate_max_steps or 20}"
                    )

                    from .child import ChildLoop

                    child_result = await ChildLoop.run(
                        outcome.delegate_instruction or "",
                        {
                            "tab": self.tab,
                            "adapter": self.adapter,
                        },
                        {
                            "max_steps": outcome.delegate_max_steps or 20,
                        },
                    )

                    self.log.loop(
                        f"step {step + 1}: child loop done | status={child_result.get('status')} "
                        f"steps={child_result.get('steps')}",
                    )

                    wire_outcome = {
                        "ok": child_result.get("status") == "success",
                        "error": (
                            child_result.get("result")
                            if child_result.get("status") != "success"
                            else None
                        ),
                    }
                    buffered_outcomes.append(
                        {"action": action, "wireOutcome": wire_outcome}
                    )
                    self.monitor.action_executed(step, action, outcome)
                    step_actions.append(
                        {
                            "action": action,
                            "outcome": {"ok": child_result.get("status") == "success"},
                        }
                    )
                    continue

                self.monitor.action_executed(step, action, outcome)
                step_actions.append(
                    {
                        "action": action,
                        "outcome": {"ok": outcome.ok, "error": outcome.error},
                    }
                )
                buffered_outcomes.append(
                    {
                        "action": action,
                        "wireOutcome": {"ok": outcome.ok, "error": outcome.error},
                    }
                )
                last_outcome_failed = not outcome.ok

                if pending_nudge and nudge_source == "action" and is_productive_action(action):
                    pending_nudge = None
                    nudge_source = None
                elif pending_nudge and nudge_source == "url" and is_url_escape_action(action):
                    pending_nudge = None
                    nudge_source = None

                repeat_level = self.repeat_detector.record(action)
                if repeat_level is not None:
                    self.log.loop(
                        f"step {step + 1}: repeat detected at level {repeat_level}"
                    )
                    pending_nudge = nudge_message(repeat_level)
                    nudge_source = "action"

                if (
                    self.action_cache
                    and outcome.ok
                    and options.instruction_hash is not None
                    and current_screenshot_hash is not None
                ):
                    key = self.action_cache.step_key(self.tab.url(), options.instruction_hash)
                    viewport = {"width": screenshot.width, "height": screenshot.height}
                    self._spawn_cache_write(
                        key,
                        action,
                        self.tab.url(),
                        options.instruction_hash,
                        current_screenshot_hash,
                        viewport,
                    )

            had_form_action = any(
                a_o["action"]["type"] in {"click", "doubleClick", "type"}
                for a_o in buffered_outcomes
            )
            if had_form_action and not terminated:
                try:
                    form_state = await self.tab.evaluate(
                        """
                        (() => {
                          const fields = [];
                          const empties = [];
                          const inputs = document.querySelectorAll('input:not([type="hidden"]), select, textarea');
                          for (const el of inputs) {
                            if (!el.offsetParent && el.tagName !== 'INPUT') continue;
                            const label = el.getAttribute('aria-label') ||
                                          el.getAttribute('placeholder') ||
                                          el.getAttribute('name') ||
                                          el.id || '';
                            if (!label) continue;
                            const val = el.tagName === 'SELECT'
                              ? el.options[el.selectedIndex]?.text
                              : el.value;
                            if (val) {
                              fields.push(label.slice(0, 30) + ': ' + val.slice(0, 50));
                            } else {
                              empties.push(label.slice(0, 30));
                            }
                          }
                          let result = '';
                          if (fields.length > 0) result += 'FILLED: ' + fields.slice(0, 8).join(' | ');
                          if (empties.length > 0) result += (result ? '\\n' : '') + 'EMPTY: ' + empties.slice(0, 6).join(', ');
                          return result;
                        })()
                        """
                    )
                    if isinstance(form_state, str) and len(form_state) > 5:
                        form_nudge = (
                            f"FORM STATE: {form_state}\n"
                            "Verify these values match your intent. If a field is EMPTY or wrong, "
                            "your previous action may not have worked — try clicking the field first, then typing."
                        )
                        if pending_nudge:
                            pending_nudge = f"{pending_nudge}\n\n{form_nudge}"
                        else:
                            pending_nudge = form_nudge
                            nudge_source = "action"
                except Exception:
                    pass

            if stream_response is None:
                stream_response = _get_last_stream_response(self.adapter)

            if stream_response:
                resp: Dict[str, Any] = (
                    stream_response
                    if isinstance(stream_response, dict)
                    else {
                        "usage": getattr(stream_response, "usage", None),
                        "actions": getattr(stream_response, "actions", []),
                        "tool_call_ids": getattr(stream_response, "tool_call_ids", None),
                        "thinking": getattr(stream_response, "thinking", None),
                    }
                )
                usage = resp.get("usage")
                resp["usage"] = _usage_to_dict(usage)

                actions = resp.get("actions")
                if actions is None:
                    actions = []
                    resp["actions"] = actions
                model_ms = int((time() - model_t0) * 1000)
                usage_dict = resp.get("usage") or {}
                self.log.adapter(
                    f"step {step + 1}: stream done | actions={len(actions)} "
                    f"in={usage_dict.get('inputTokens', 0)} "
                    f"out={usage_dict.get('outputTokens', 0)} ({model_ms}ms)",
                    {
                        "step": step + 1,
                        "actions": len(actions),
                        "inputTokens": usage_dict.get("inputTokens", 0),
                        "outputTokens": usage_dict.get("outputTokens", 0),
                        "cacheReadTokens": usage_dict.get("cacheReadTokens"),
                        "durationMs": model_ms,
                    },
                )

                if len(actions) == 0:
                    self.log.loop(
                        f"step {step + 1}: model returned no actions — injecting noop screenshot"
                    )
                    noop_action: Action = {"type": "screenshot"}
                    noop_id = f"toolu_noop_{int(time() * 1000)}"
                    actions.append(noop_action)
                    tool_call_ids = resp.get("tool_call_ids")
                    if tool_call_ids is None:
                        tool_call_ids = resp.get("toolCallIds")
                    if tool_call_ids is None:
                        tool_call_ids = []
                    resp["tool_call_ids"] = tool_call_ids
                    tool_call_ids.append(noop_id)

                    buffered_outcomes.append(
                        {"action": noop_action, "wireOutcome": {"ok": True}}
                    )

                    noop_repeat = self.repeat_detector.record(noop_action)
                    if noop_repeat is not None:
                        self.log.loop(
                            f"step {step + 1}: noop repeat detected at level {noop_repeat}",
                        )
                        pending_nudge = nudge_message(noop_repeat)
                        nudge_source = "action"

                self.history.append_response(resp)
                step_usage = _usage_to_token_usage(resp.get("usage"))
                thinking = resp.get("thinking")
                self.monitor.step_completed(step, resp)

            for item in buffered_outcomes:
                self.history.append_action_outcome(
                    item["action"],
                    ActionExecution.from_dict(item["wireOutcome"]),
                )

            self.history.append_semantic_step(
                SemanticStep(
                    step_index=step,
                    url=self.tab.url(),
                    screenshot_base64=screenshot_b64,
                    thinking=thinking,
                    actions=step_actions,
                    agent_state=self.state.current(),
                    token_usage=step_usage,
                    duration_ms=int((time() - step_start) * 1000),
                )
            )

            if termination_result:
                termination_result.history = self.history.semantic_history()

                if (
                    termination_result.status == "success"
                    and self.workflow_memory
                    and options.system_prompt
                ):
                    try:
                        workflow_history = [
                            _semantic_step_to_workflow_dict(s)
                            for s in termination_result.history
                        ]
                        workflow = WorkflowMemory.extract(
                            options.system_prompt,
                            workflow_history,
                        )
                        if workflow:
                            self.workflow_memory.add(workflow)
                    except Exception:
                        pass

                self.monitor.terminated(termination_result)
                return termination_result

            self.history.compress_screenshots(self.keep_recent_screenshots)
            if self.log.history_enabled:
                wire_len = len(self.history.wire_history())
                self.log.history(
                    f"step {step + 1}: tier-1 compress | keepRecent={self.keep_recent_screenshots} "
                    f"wire={wire_len}msgs total",
                    {
                        "step": step + 1,
                        "wireLen": wire_len,
                        "keepRecentScreenshots": self.keep_recent_screenshots,
                    },
                )

        max_steps_result = "Maximum steps reached without completion"
        final_state = self.state.current()
        if final_state and len(final_state) > 0:
            max_steps_result = "; ".join(
                f"{k}: {v}" if isinstance(v, str) else f"{k}: {json.dumps(v, ensure_ascii=False)}"
                for k, v in final_state.items()
            )

        result = LoopResult(
            status="max_steps",
            result=max_steps_result,
            steps=options.max_steps,
            history=self.history.semantic_history(),
            agent_state=final_state,
        )
        self.monitor.terminated(result)
        return result