"""
Type definitions for Browser Agent. Port of src/types.ts.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import (
    Any,
    Awaitable,
    Callable,
    Dict,
    List,
    Literal,
    NotRequired,
    Optional,
    Required,
    TypedDict,
    Union,
)

# ─── Coordinates ──────────────────────────────────────────────────────────────


@dataclass
class Point:
    x: float
    y: float


@dataclass
class ViewportSize:
    width: int
    height: int


# ─── Screenshot ────────────────────────────────────────────────────────────────


@dataclass
class ScreenshotResult:
    data: bytes
    width: int
    height: int
    mime_type: Literal["image/png", "image/jpeg"]


@dataclass
class ScreenshotOptions:
    format: Optional[Literal["png", "jpeg"]] = None
    quality: Optional[int] = None
    # Composite a cursor dot at last click position. Default: true
    cursor_overlay: bool = True
    full_page: bool = False


# ─── Task State ───────────────────────────────────────────────────────────────


TaskState = Dict[str, Any]


# ─── Actions ──────────────────────────────────────────────────────────────────
# Dict-based representation to mirror the JS/TS runtime shape.


class ClickAction(TypedDict):
    type: Literal["click"]
    x: float
    y: float
    button: NotRequired[Literal["left", "right", "middle"]]


class DoubleClickAction(TypedDict):
    type: Literal["doubleClick"]
    x: float
    y: float


class DragAction(TypedDict):
    type: Literal["drag"]
    startX: float
    startY: float
    endX: float
    endY: float


class ScrollAction(TypedDict):
    type: Literal["scroll"]
    x: float
    y: float
    direction: Literal["up", "down", "left", "right"]
    amount: float


class TypeAction(TypedDict):
    type: Literal["type"]
    text: str


class KeyPressAction(TypedDict):
    type: Literal["keyPress"]
    keys: List[str]


class WaitAction(TypedDict):
    type: Literal["wait"]
    ms: int


class GotoAction(TypedDict):
    type: Literal["goto"]
    url: str


class WriteStateAction(TypedDict):
    type: Literal["writeState"]
    data: TaskState


class ScreenshotAction(TypedDict):
    type: Literal["screenshot"]


class TerminateAction(TypedDict):
    type: Literal["terminate"]
    status: Literal["success", "failure"]
    result: str


class HoverAction(TypedDict):
    type: Literal["hover"]
    x: float
    y: float


class DelegateAction(TypedDict):
    type: Literal["delegate"]
    instruction: str
    max_steps: NotRequired[int]


class FoldAction(TypedDict):
    type: Literal["fold"]
    summary: str


Action = Union[
    ClickAction,
    DoubleClickAction,
    DragAction,
    ScrollAction,
    TypeAction,
    KeyPressAction,
    WaitAction,
    GotoAction,
    WriteStateAction,
    ScreenshotAction,
    TerminateAction,
    HoverAction,
    DelegateAction,
    FoldAction,
]


# ─── Action Outcome ────────────────────────────────────────────────────────────


@dataclass
class ActionOutcome:
    ok: bool
    error: Optional[str] = None
    # Description of what element received focus after a click
    click_target: Optional[str] = None


@dataclass
class ActionExecution:
    """Outcome of executing an action. Supports attribute access for .ok, .terminated, etc."""
    ok: bool
    error: Optional[str] = None
    click_target: Optional[str] = None
    terminated: Optional[bool] = None
    status: Optional[Literal["success", "failure"]] = None
    result: Optional[str] = None
    is_screenshot_request: Optional[bool] = None
    is_delegate_request: Optional[bool] = None
    delegate_instruction: Optional[str] = None
    delegate_max_steps: Optional[int] = None

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ActionExecution":
        """Create from dict (e.g. wireOutcome from buffered outcomes)."""
        return cls(
            ok=d.get("ok", True),
            error=d.get("error"),
            click_target=d.get("click_target"),
            terminated=d.get("terminated"),
            status=d.get("status"),
            result=d.get("result"),
            is_screenshot_request=d.get("is_screenshot_request"),
            is_delegate_request=d.get("is_delegate_request"),
            delegate_instruction=d.get("delegate_instruction"),
            delegate_max_steps=d.get("delegate_max_steps"),
        )


# ─── Token Usage ───────────────────────────────────────────────────────────────


@dataclass
class TokenUsage:
    input_tokens: int
    output_tokens: int
    cache_read_tokens: Optional[int] = None
    cache_write_tokens: Optional[int] = None


# ─── History ───────────────────────────────────────────────────────────────────


class SemanticActionRecord(TypedDict):
    action: Action
    outcome: Dict[str, Any]  # { ok: bool, error?: str }


@dataclass
class SemanticStep:
    step_index: int
    url: str
    screenshot_base64: str
    actions: List[SemanticActionRecord]
    agent_state: Optional[TaskState]
    token_usage: TokenUsage
    duration_ms: int
    thinking: Optional[str] = None


WireMessage = Dict[str, Any]


class _SerializedHistoryRequired(TypedDict):
    wireHistory: List[WireMessage]
    semanticSteps: List[SemanticStep]
    agentState: Optional[TaskState]


class SerializedHistory(_SerializedHistoryRequired, total=False):
    foldedSummaries: List[str]


# ─── Loop ──────────────────────────────────────────────────────────────────────


@dataclass
class LoopOptions:
    max_steps: int
    system_prompt: Optional[str] = None
    # 0.0–1.0. Trigger LLM compaction at this utilization level. Default: 0.8
    compaction_threshold: float = 0.8
    # Hash of the original task instruction, used as part of the action cache key.
    instruction_hash: Optional[str] = None


@dataclass
class LoopResult:
    status: Literal["success", "failure", "max_steps"]
    result: str
    steps: int
    history: List[SemanticStep]
    agent_state: Optional[TaskState]


# ─── Session ───────────────────────────────────────────────────────────────────


@dataclass
class RunResult:
    status: Literal["success", "failure", "max_steps"]
    result: str
    steps: int
    history: List[SemanticStep]
    agent_state: Optional[TaskState]
    token_usage: TokenUsage

@dataclass
class RunOptions:
    instruction: str
    max_steps: Optional[int] = None
    start_url: Optional[str] = None

# Logging
@dataclass
class LogLine:
    level: Literal["debug", "info", "warn", "error"]
    message: str
    timestamp: float
    data: Optional[Dict[str, Any]] = None

# ─── Streaming Events ──────────────────────────────────────────────────────────


class StepStartEvent(TypedDict):
    type: Literal["step_start"]
    step: int
    max_steps: int
    url: str


class ScreenshotEvent(TypedDict):
    type: Literal["screenshot"]
    step: int
    imageBase64: str


class ThinkingEvent(TypedDict):
    type: Literal["thinking"]
    step: int
    text: str


class ActionEvent(TypedDict):
    type: Literal["action"]
    step: int
    action: Action


class ActionResultEvent(TypedDict):
    type: Required[Literal["action_result"]]
    step: Required[int]
    action: Required[Action]
    ok: Required[bool]
    error: NotRequired[str]


class ActionBlockedEvent(TypedDict):
    type: Literal["action_blocked"]
    step: int
    action: Action
    reason: str


class StateWrittenEvent(TypedDict):
    type: Literal["state_written"]
    step: int
    data: TaskState


class CompactionEvent(TypedDict):
    type: Literal["compaction"]
    step: int
    tokensBefore: int
    tokensAfter: int


class TerminationRejectedEvent(TypedDict):
    type: Literal["termination_rejected"]
    step: int
    reason: str


class DoneEvent(TypedDict):
    type: Literal["done"]
    result: RunResult


StreamEvent = Union[
    StepStartEvent,
    ScreenshotEvent,
    ThinkingEvent,
    ActionEvent,
    ActionResultEvent,
    ActionBlockedEvent,
    StateWrittenEvent,
    CompactionEvent,
    TerminationRejectedEvent,
    DoneEvent,
]


# ─── Pre-Action Hook ───────────────────────────────────────────────────────────


class AllowDecision(TypedDict):
    decision: Literal["allow"]


class DenyDecision(TypedDict):
    decision: Literal["deny"]
    reason: str


PreActionDecision = Union[AllowDecision, DenyDecision]

PreActionHook = Callable[
    [Action],
    Union[PreActionDecision, Awaitable[PreActionDecision]],
]

class SerializedAgent(SerializedHistory):
    modelId: str


class LocalBrowserOptions(TypedDict):
    type: Required[Literal["local"]]
    port: NotRequired[int]
    headless: NotRequired[bool]
    userDataDir: NotRequired[str]


class CdpBrowserOptions(TypedDict):
    type: Literal["cdp"]
    url: str


class BrowserbaseBrowserOptions(TypedDict):
    type: Literal["browserbase"]
    apiKey: str
    projectId: str
    sessionId: NotRequired[str]


BrowserOptions = Union[
    LocalBrowserOptions,
    CdpBrowserOptions,
    BrowserbaseBrowserOptions,
]

class SiteRule(TypedDict):
    domain: str
    rules: List[str]

@dataclass
class AgentOptions:
    # e.g. "google/gemini-2.0-flash", "google/gemini-3-flash-preview", etc.
    model: str
    browser: BrowserOptions

    api_key: Optional[str] = None
    base_url: Optional[str] = None
    planner_model: Optional[str] = None
    auto_align_viewport: Optional[bool] = None
    system_prompt: Optional[str] = None
    max_steps: Optional[int] = None
    confidence_gate: Optional[bool] = None
    action_verifier: Optional[bool] = None
    checkpoint_interval: Optional[int] = None
    site_kb: Optional[Union[str, List[SiteRule]]] = None
    workflow_memory: Optional[str] = None
    thinking_budget: Optional[int] = None  # Unused; kept for API compatibility
    compaction_threshold: Optional[float] = None
    compaction_model: Optional[str] = None
    keep_recent_screenshots: Optional[int] = None
    cursor_overlay: Optional[bool] = None
    verbose: Optional[Literal[0, 1, 2]] = None
    logger: Optional[Callable[[LogLine], None]] = None
    timing: Optional[Any] = None
    policy: Optional[Any] = None
    pre_action_hook: Optional[PreActionHook] = None
    verifier: Optional[Any] = None
    monitor: Optional[Any] = None
    initial_history: Optional[SerializedHistory] = None
    initial_state: Optional[TaskState] = None
