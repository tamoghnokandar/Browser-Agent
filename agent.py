"""
Agent: public facade for Browser Agent. Port of src/agent.ts.
"""
from __future__ import annotations

import asyncio
import inspect
from typing import Any, AsyncIterator, Dict, Optional, cast

from logger import BrowserAgentLogger
from session import Session
from agent_types import (
    AgentOptions,
    BrowserOptions,
    RunOptions,
    RunResult,
    SemanticStep,
    SerializedAgent,
    StreamEvent,
)


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _get_dict_value(data: Dict[str, Any], key: str, default: Any = None) -> Any:
    return data[key] if key in data else default


async def _create_adapter(
    model: str,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    thinking_budget: int = 0,
) -> Any:
    """
    Lazy adapter construction. Only Google (Gemini) models are supported.
    """
    if model.startswith("google/"):
        from model.google import GoogleAdapter

        return GoogleAdapter(
            model[len("google/"):],
            api_key,
        )

    # Short names for common Gemini models
    short_models = {
        "gemini-2.0-flash": "gemini-2.0-flash",
        "gemini-2.5-pro": "gemini-2.5-pro",
        "gemini-3-flash-preview": "gemini-3-flash-preview",
    }
    if model in short_models:
        from model.google import GoogleAdapter

        return GoogleAdapter(short_models[model], api_key)

    raise ValueError(
        f"Unsupported model: {model}. Only Google (Gemini) models are supported. "
        "Use 'google/<model-id>' (e.g. 'google/gemini-2.0-flash')."
    )


async def _resolve_page_session(conn: Any, log: BrowserAgentLogger) -> Any:
    """
    Resolve a page-level CDP session from a browser-level connection.
    Mirrors the TS intent: browser-level sessions cannot drive Page.* reliably.
    """
    try:
        main = conn.main_session()
        resp = await main.send("Target.getTargets", {})
        target_infos = resp.get("targetInfos", [])
        page_target = next((t for t in target_infos if t.get("type") == "page"), None)
        if page_target is not None:
            target_id = page_target.get("targetId")
            if target_id:
                log.browser(
                    f"attaching to page target: {target_id} ({page_target.get('url', '')})"
                )
                return await conn.new_session(target_id)
    except Exception:
        pass

    return conn.main_session()


async def _connect_browser(opts: BrowserOptions | Dict[str, Any], log: BrowserAgentLogger) -> Dict[str, Any]:
    """
    Connect local / cdp / browserbase browsers in the same spirit as src/agent.ts.
    Returns {tab, cleanup, conn?}.
    """
    from browser.cdp import CdpConnection
    from browser.cdptab import CDPTab

    browser_opts = cast(Dict[str, Any], opts)
    browser_type = browser_opts.get("type", "local")

    if browser_type == "local":
        from browser.launch.local import launch_chrome

        headless = browser_opts.get("headless", True)
        log.browser(
            f"launching local Chrome{' (headless)' if headless is not False else ' (headed)'}"
        )

        launch_result = await launch_chrome(
            {
                "port": browser_opts.get("port"),
                "headless": browser_opts.get("headless"),
                "userDataDir": browser_opts.get("userDataDir") or browser_opts.get("user_data_dir"),
            }
        )

        # Playwright path: launch_chrome returns { tab, cleanup, conn: None }
        if "tab" in launch_result:
            tab = launch_result["tab"]
            cleanup = launch_result["cleanup"]
            conn = launch_result.get("conn")
            log.browser("Chrome launched via Playwright")
            return {"tab": tab, "cleanup": cleanup, "conn": conn}

        # Legacy path: launch_chrome returns { wsUrl, kill }
        ws_url = launch_result.get("wsUrl") or launch_result.get("ws_url")
        kill = launch_result.get("kill")
        if not ws_url:
            raise RuntimeError("launch_chrome() did not return wsUrl or tab")

        log.browser(f"Chrome launched, connecting CDP: {ws_url}")
        conn = await CdpConnection.connect(ws_url, log)
        session = await _resolve_page_session(conn, log)
        tab = CDPTab(session, log)

        async def cleanup() -> None:
            try:
                conn.close()
            finally:
                if kill:
                    result = kill()
                    if inspect.isawaitable(result):
                        await result

        return {"tab": tab, "cleanup": cleanup, "conn": conn}

    if browser_type == "cdp":
        url = browser_opts.get("url")
        if not url:
            raise ValueError("CDP browser requires 'url'")

        log.browser(f"connecting to CDP endpoint: {url}")
        conn = await CdpConnection.connect(url, log)
        session = await _resolve_page_session(conn, log)
        tab = CDPTab(session, log)

        async def cleanup() -> None:
            conn.close()

        return {"tab": tab, "cleanup": cleanup, "conn": conn}

    if browser_type == "browserbase":
        from browser.launch.browserbase import connect_browserbase

        project_id = browser_opts.get("projectId") or browser_opts.get("project_id")
        session_id = browser_opts.get("sessionId") or browser_opts.get("session_id")
        log.browser(
            f"connecting to Browserbase (project={project_id}"
            f"{f' session={session_id}' if session_id else ''})"
        )
        bb_result = await connect_browserbase(browser_opts)
        ws_url = bb_result.get("wsUrl") or bb_result.get("ws_url")
        session_id = bb_result.get("sessionId") or bb_result.get("session_id")

        if not ws_url:
            raise RuntimeError("connect_browserbase() did not return wsUrl")

        log.browser(f"Browserbase session ready (id={session_id}), connecting CDP")
        conn = await CdpConnection.connect(ws_url, log)
        session = await _resolve_page_session(conn, log)
        tab = CDPTab(session, log)

        async def cleanup() -> None:
            conn.close()

        return {"tab": tab, "cleanup": cleanup, "conn": conn}

    raise ValueError(f"Unknown browser type: {browser_type}")


async def _build_monitor(opts: AgentOptions | Dict[str, Any]) -> Any:
    """
    Build a monitor compatible with src/agent.ts:
    - custom monitor wins
    - verbose=0 -> NoopMonitor
    - else ConsoleMonitor
    - if logger callback exists, wrap monitor to emit structured log lines too
    """
    options = cast(Dict[str, Any], opts)
    custom_monitor = options.get("monitor")
    if custom_monitor is not None:
        return custom_monitor

    from loop.monitor import ConsoleMonitor, NoopMonitor

    verbose = options.get("verbose", 1)
    if verbose == 0:
        return NoopMonitor()

    base = ConsoleMonitor()
    callback = options.get("logger")

    if callback is None:
        return base

    def emit(level: str, message: str) -> None:
        import time

        callback(
            {
                "level": level,
                "message": message,
                "timestamp": time.time() * 1000,
            }
        )

    class WrappedMonitor:
        def step_started(self, step: int, context: Any) -> None:
            if verbose >= 1 and hasattr(base, "step_started"):
                base.step_started(step, context)
            max_steps = context.get("max_steps", "") if isinstance(context, dict) else getattr(context, "max_steps", "")
            url = context.get("url", "") if isinstance(context, dict) else getattr(context, "url", "")
            emit("info", f"step_start step={step + 1}/{max_steps} url={url}")

        def step_completed(self, step: int, response: Any) -> None:
            if verbose >= 1 and hasattr(base, "step_completed"):
                base.step_completed(step, response)
            if isinstance(response, dict):
                actions = response.get("actions", []) or []
                usage = response.get("usage", {}) or {}
            else:
                actions = getattr(response, "actions", []) or []
                usage = getattr(response, "usage", {}) or {}
            input_tokens = usage.get("inputTokens", usage.get("input_tokens", 0)) if isinstance(usage, dict) else getattr(usage, "input_tokens", 0)
            emit(
                "info",
                f"step_complete step={step + 1} actions={len(actions)} input_tokens={input_tokens}",
            )

        def action_executed(self, step: int, action: Any, outcome: Any) -> None:
            if verbose >= 2 and hasattr(base, "action_executed"):
                base.action_executed(step, action, outcome)
            ok = outcome.get("ok", False) if isinstance(outcome, dict) else getattr(outcome, "ok", False)
            if not ok:
                action_type = action.get("type", "unknown") if isinstance(action, dict) else getattr(action, "type", "unknown")
                error = outcome.get("error", "") if isinstance(outcome, dict) else getattr(outcome, "error", "")
                emit(
                    "warn",
                    f"action_error step={step + 1} type={action_type} error={error}",
                )

        def action_blocked(self, step: int, action: Any, reason: str) -> None:
            if hasattr(base, "action_blocked"):
                base.action_blocked(step, action, reason)
            action_type = action.get("type", "unknown") if isinstance(action, dict) else getattr(action, "type", "unknown")
            emit(
                "warn",
                f"action_blocked step={step + 1} type={action_type} reason={reason}",
            )

        def termination_rejected(self, step: int, reason: str) -> None:
            if hasattr(base, "termination_rejected"):
                base.termination_rejected(step, reason)
            emit("warn", f"termination_rejected step={step + 1} reason={reason}")

        def compaction_triggered(
            self, step: int, tokens_before: int, tokens_after: int
        ) -> None:
            if hasattr(base, "compaction_triggered"):
                base.compaction_triggered(step, tokens_before, tokens_after)
            emit(
                "info",
                f"compaction step={step + 1} tokens_before={tokens_before} tokens_after={tokens_after}",
            )

        def terminated(self, result: Any) -> None:
            if hasattr(base, "terminated"):
                base.terminated(result)
            status = result.get("status", "") if isinstance(result, dict) else getattr(result, "status", "")
            steps = result.get("steps", 0) if isinstance(result, dict) else getattr(result, "steps", 0)
            emit("info", f"terminated status={status} steps={steps}")

        def error(self, err: Exception) -> None:
            if hasattr(base, "error"):
                base.error(err)
            emit("error", f"error {err}")

    return WrappedMonitor()


class Agent:
    def __init__(self, options: AgentOptions | Dict[str, Any]) -> None:
        self._options = cast(Dict[str, Any], options)
        self._tab: Optional[Any] = None
        self._adapter: Optional[Any] = None
        self._cleanup: Optional[Any] = None
        self._conn: Optional[Any] = None
        self._session: Optional[Session] = None
        self._pending_history: Optional[SerializedAgent] = None
        self._log: Optional[BrowserAgentLogger] = None

    @property
    def tab(self) -> Any:
        if self._tab is None:
            raise RuntimeError("Agent not connected. Call run() first.")
        return self._tab

    async def _connect(self) -> None:
        if self._tab is not None:
            return

        verbose = self._options.get("verbose", 1)
        logger_cb = cast(Optional[Any], self._options.get("logger"))
        log = BrowserAgentLogger(verbose, logger_cb)
        self._log = log

        browser_opts = cast(Dict[str, Any], self._options.get("browser", {}) or {})
        browser_type = browser_opts.get("type", "local")

        log.info(
            f"[browser-agent] connecting — model={self._options.get('model')} browser={browser_type}"
        )

        adapter, browser_result, monitor = await asyncio.gather(
            _create_adapter(
                self._options["model"],
                self._options.get("api_key"),
                self._options.get("base_url"),
                self._options.get("thinking_budget", 0) or 0,
            ),
            _connect_browser(browser_opts, log),
            _build_monitor(self._options),
        )

        compaction_model = self._options.get("compaction_model")
        compaction_adapter = None
        if compaction_model:
            compaction_adapter = await _create_adapter(
                compaction_model,
                self._options.get("api_key"),
                self._options.get("base_url"),
            )

        tab = browser_result["tab"]
        cleanup = browser_result["cleanup"]
        conn = browser_result.get("conn")

        log.adapter(
            "adapter ready | "
            f"provider={getattr(adapter, 'provider', '')} "
            f"model={getattr(adapter, 'model_id', getattr(adapter, 'modelId', ''))} "
            f"contextWindow={getattr(adapter, 'context_window_tokens', getattr(adapter, 'contextWindowTokens', ''))}",
            {
                "provider": getattr(adapter, "provider", None),
                "modelId": getattr(adapter, "model_id", getattr(adapter, "modelId", None)),
                "contextWindow": getattr(
                    adapter, "context_window_tokens", getattr(adapter, "contextWindowTokens", None)
                ),
            },
        )

        self._adapter = adapter
        self._tab = tab
        self._cleanup = cleanup
        self._conn = conn

        if self._options.get("auto_align_viewport", True) is not False:
            try:
                from browser.viewport import ViewportManager

                vm = ViewportManager(tab)
                aligned = await vm.align_to_model(
                    getattr(adapter, "patch_size", getattr(adapter, "patchSize", None)),
                    getattr(adapter, "max_image_dimension", getattr(adapter, "maxImageDimension", None)),
                )
                log.browser(
                    f"viewport aligned: {aligned.get('width')}x{aligned.get('height')} "
                    f"(patchSize={getattr(adapter, 'patch_size', getattr(adapter, 'patchSize', 'n/a'))})",
                    {
                        "width": aligned.get("width"),
                        "height": aligned.get("height"),
                        "patchSize": getattr(adapter, "patch_size", getattr(adapter, "patchSize", None)),
                    },
                )
            except Exception as e:
                log.warn(f"[browser-agent] viewport alignment skipped (CDP not supported): {e}")

        initial_history = (
            self._pending_history
            if self._pending_history is not None
            else cast(Optional[SerializedAgent], self._options.get("initial_history"))
        )

        confidence_gate = None
        if self._options.get("confidence_gate"):
            from loop.confidence_gate import ConfidenceGate

            confidence_gate = ConfidenceGate({"adapter": adapter})

        action_verifier = None
        if self._options.get("action_verifier"):
            from loop.action_verifier import ActionVerifier

            action_verifier = ActionVerifier()

        checkpoint_manager = None
        checkpoint_interval = self._options.get("checkpoint_interval")
        if checkpoint_interval is not None:
            from loop.checkpoint import CheckpointManager

            checkpoint_manager = CheckpointManager({"interval": checkpoint_interval})

        site_kb = None
        site_kb_opt = self._options.get("site_kb")
        if site_kb_opt:
            from memory.site_kb import SiteKB

            if isinstance(site_kb_opt, str):
                site_kb = SiteKB.from_file(site_kb_opt)
            else:
                site_kb = SiteKB(site_kb_opt)

        workflow_memory = None
        workflow_memory_opt = self._options.get("workflow_memory")
        if workflow_memory_opt:
            from memory.workflow import WorkflowMemory

            workflow_memory = WorkflowMemory.from_file(workflow_memory_opt)

        self._session = Session(
            {
                "tab": tab,
                "adapter": adapter,
                "system_prompt": self._options.get("system_prompt"),
                "max_steps": self._options.get("max_steps"),
                "compaction_threshold": self._options.get("compaction_threshold"),
                "keep_recent_screenshots": self._options.get("keep_recent_screenshots"),
                "cursor_overlay": self._options.get("cursor_overlay"),
                "timing": self._options.get("timing"),
                "policy": self._options.get("policy"),
                "pre_action_hook": self._options.get("pre_action_hook"),
                "verifier": self._options.get("verifier"),
                "monitor": monitor,
                "compaction_adapter": compaction_adapter,
                "initial_history": initial_history,
                "initial_state": self._options.get("initial_state"),
                "log": log,
                "confidence_gate": confidence_gate,
                "action_verifier": action_verifier,
                "checkpoint_manager": checkpoint_manager,
                "site_kb": site_kb,
                "workflow_memory": workflow_memory,
            }
        )
        self._pending_history = None

        log.info("[browser-agent] connected and ready")

    async def run(
        self,
        options: RunOptions | Dict[str, Any] | str,
        **kwargs: Any,
    ) -> RunResult | Dict[str, Any]:
        """
          await agent.run("do something", max_steps=20, start_url="...")
        """
        await self._connect()
        assert self._session is not None
        assert self._tab is not None
        assert self._log is not None

        if isinstance(options, str):
            run_options: Dict[str, Any] = {"instruction": options, **kwargs}
        else:
            run_options = dict(cast(Dict[str, Any], options))
            run_options.update(kwargs)

        instruction = cast(str, run_options.get("instruction", ""))
        max_steps = run_options.get("max_steps")
        start_url = run_options.get("start_url")

        self._log.info(
            f'[browser-agent] run: "{instruction[:80]}{"..." if len(instruction) > 80 else ""}"',
            {
                "instructionLen": len(instruction),
                "max_steps": max_steps,
            },
        )

        planner_model = self._options.get("planner_model")
        if planner_model:
            screenshot = await self._tab.screenshot()
            from loop.planner import run_planner

            planner_adapter = await _create_adapter(
                planner_model,
                self._options.get("api_key"),
                self._options.get("base_url"),
            )
            plan = await run_planner(instruction, screenshot, planner_adapter)
            planner_system_prompt = (
                f"{plan}\n\n{self._options.get('system_prompt') or ''}"
            ).strip()

            monitor = await _build_monitor(self._options)
            compaction_adapter = None
            compaction_model = self._options.get("compaction_model")
            if compaction_model:
                compaction_adapter = await _create_adapter(
                    compaction_model,
                    self._options.get("api_key"),
                    self._options.get("base_url"),
                )

            session_with_plan = Session(
                {
                    "tab": self._tab,
                    "adapter": self._adapter,
                    "system_prompt": planner_system_prompt,
                    "max_steps": self._options.get("max_steps"),
                    "compaction_threshold": self._options.get("compaction_threshold"),
                    "keep_recent_screenshots": self._options.get("keep_recent_screenshots"),
                    "cursor_overlay": self._options.get("cursor_overlay"),
                    "timing": self._options.get("timing"),
                    "policy": self._options.get("policy"),
                    "pre_action_hook": self._options.get("pre_action_hook"),
                    "verifier": self._options.get("verifier"),
                    "monitor": monitor,
                    "compaction_adapter": compaction_adapter,
                    "initial_history": self._pending_history or self._options.get("initial_history"),
                    "initial_state": self._options.get("initial_state"),
                    "log": self._log,
                }
            )
            return await session_with_plan.run(
                {
                    "instruction": instruction,
                    "max_steps": max_steps,
                    "start_url": start_url,
                }
            )

        if start_url:
            self._log.browser(f"pre-navigating to start_url: {start_url}")
            try:
                await self._tab.goto(start_url)
            except Exception as e:
                self._log.warn(
                    f"[browser-agent] start_url pre-navigation failed ({start_url}): {e}. "
                    "Attempting CDP reconnect."
                )
                if self._conn is not None:
                    try:
                        await asyncio.sleep(0.150)
                        new_page_session = await _resolve_page_session(
                            self._conn, self._log
                        )
                        from browser.cdptab import CDPTab

                        if isinstance(self._tab, CDPTab) and hasattr(
                            self._tab, "reconnect"
                        ):
                            await self._tab.reconnect(new_page_session)
                            try:
                                current_url = self._tab.url()
                            except Exception:
                                current_url = "unknown"
                            self._log.browser(
                                f"[browser-agent] CDPTab reconnected to new page target (url={current_url})"
                            )
                            try:
                                await self._tab.goto(start_url)
                            except Exception:
                                self._log.warn(
                                    "[browser-agent] retry navigation after reconnect failed. "
                                    "Model will navigate."
                                )
                    except Exception as reconnect_err:
                        self._log.warn(
                            f"[browser-agent] CDP reconnect failed: {reconnect_err}. "
                            "Model will navigate."
                        )

        return await self._session.run(
            {
                "instruction": instruction,
                "max_steps": max_steps,
                "start_url": start_url,
            }
        )

    async def stream(
        self,
        options: RunOptions | Dict[str, Any] | str,
        **kwargs: Any,
    ) -> AsyncIterator[StreamEvent | Dict[str, Any]]:
        from loop.streaming_monitor import StreamingMonitor

        await self._connect()
        assert self._tab is not None
        assert self._adapter is not None
        assert self._log is not None

        if isinstance(options, str):
            run_options: Dict[str, Any] = {"instruction": options, **kwargs}
        else:
            run_options = dict(cast(Dict[str, Any], options))
            run_options.update(kwargs)

        streaming_monitor = StreamingMonitor()

        compaction_adapter = None
        compaction_model = self._options.get("compaction_model")
        if compaction_model:
            compaction_adapter = await _create_adapter(
                compaction_model,
                self._options.get("api_key"),
                self._options.get("base_url"),
            )

        session = Session(
            {
                "tab": self._tab,
                "adapter": self._adapter,
                "system_prompt": self._options.get("system_prompt"),
                "max_steps": self._options.get("max_steps"),
                "compaction_threshold": self._options.get("compaction_threshold"),
                "keep_recent_screenshots": self._options.get("keep_recent_screenshots"),
                "cursor_overlay": self._options.get("cursor_overlay"),
                "timing": self._options.get("timing"),
                "policy": self._options.get("policy"),
                "pre_action_hook": self._options.get("pre_action_hook"),
                "verifier": self._options.get("verifier"),
                "monitor": streaming_monitor,
                "compaction_adapter": compaction_adapter,
                "log": self._log,
            }
        )

        start_url = run_options.get("start_url")
        if start_url:
            self._log.browser(f"pre-navigating to start_url: {start_url}")
            try:
                await self._tab.goto(start_url)
            except Exception as e:
                self._log.warn(
                    f"[browser-agent] start_url pre-navigation failed ({start_url}): {e}. "
                    "Model will navigate."
                )

        async def _run_and_complete() -> Any:
            try:
                result = await session.run(
                    {
                        "instruction": run_options.get("instruction", ""),
                        "max_steps": run_options.get("max_steps"),
                        "start_url": start_url,
                    }
                )
                streaming_monitor.complete(result)
                return result
            except Exception as err:
                streaming_monitor.complete(
                    {
                        "status": "failure",
                        "result": str(err),
                        "steps": 0,
                        "history": [],
                        "agentState": None,
                        "tokenUsage": {"inputTokens": 0, "outputTokens": 0},
                    }
                )
                raise

        run_task = asyncio.create_task(_run_and_complete())

        async for event in streaming_monitor.events():
            yield event

        await run_task

    def history(self) -> list[SemanticStep] | list[Any]:
        if self._session is None:
            return []
        serialized = self._session.serialize()
        if isinstance(serialized, dict):
            return cast(list[SemanticStep], serialized.get("semanticSteps", serialized.get("semantic_steps", [])))
        return cast(list[SemanticStep], getattr(serialized, "semantic_steps", []))

    async def serialize(self) -> SerializedAgent | Dict[str, Any]:
        if self._session is None:
            raise RuntimeError("No session to serialize.")
        data = self._session.serialize()
        out = dict(data)
        out["modelId"] = self._options["model"]
        return out

    @classmethod
    def resume(cls, data: SerializedAgent | Dict[str, Any], options: AgentOptions | Dict[str, Any]) -> "Agent":
        agent = cls(options)
        agent._pending_history = cast(SerializedAgent, data)
        return agent

    async def close(self) -> None:
        if self._cleanup:
            cleanup = self._cleanup
            self._cleanup = None
            await _maybe_await(cleanup())
            self._tab = None
            self._adapter = None
            self._session = None

    async def __aenter__(self) -> "Agent":
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        await self.close()

    @classmethod
    async def run_once(cls, options: AgentOptions | Dict[str, Any]) -> RunResult | Dict[str, Any]:
        agent = cls(options)
        try:
            options_dict = cast(Dict[str, Any], options)
            return await agent.run(
                {
                    "instruction": options_dict["instruction"],
                    "max_steps": _get_dict_value(options_dict, "max_steps"),
                    "start_url": _get_dict_value(options_dict, "start_url"),
                }
            )
        finally:
            await agent.close()
