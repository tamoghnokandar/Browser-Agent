"""
Public API — primary entry point. Port of src/index.ts.
"""
from __future__ import annotations

# Public API — primary entry point
from agent import Agent
from browser.cdp import CdpConnection
from browser.cdptab import CDPTab
from browser.launch.browserbase import BrowserbaseOptions, connect_browserbase
from browser.launch.local import launch_chrome

# Browser
from browser.tab import BrowserTab, ClickOptions, DragOptions, TypeOptions
from browser.viewport import ViewportManager

# Errors
from errors import BrowserAgentError, BrowserAgentErrorCode

# Logger
from logger import BrowserAgentLogger
from loop.action_cache import ActionCache, viewport_mismatch
from loop.action_verifier import ActionVerification, ActionVerifier
from loop.checkpoint import BrowserCheckpoint, CheckpointManager
from loop.child import ChildLoop, ChildLoopOptions, ChildLoopResult

# Optional features
from loop.confidence_gate import ConfidenceGate
from loop.history import HistoryManager

# Monitors
from loop.monitor import ConsoleMonitor, LoopMonitor, NoopMonitor
from loop.perception import PerceptionLoop, PerceptionLoopOptions
from loop.planner import run_planner

# Policy
from loop.policy import SessionPolicy, SessionPolicyOptions, SessionPolicyResult
from loop.repeat_detector import RepeatDetector
from loop.router import ActionRouter, RouterTiming

# Loop primitives (for custom integrations)
from loop.state import StateStore
from loop.streaming_monitor import StreamingMonitor

# Verifiers (completion gates)
from loop.verifier import (
    CustomGate,
    ModelVerifier,
    UrlMatchesGate,
    Verifier,
    VerifyResult,
)
from memory.site_kb import SiteKB, SiteRule
from memory.workflow import Workflow, WorkflowMemory

# Model adapters
from model.adapter import (
    ModelAdapter,
    ModelResponse,
    StepContext,
    denormalize,
    denormalize_point,
    normalize,
)
from model.decoder import ActionDecoder
from model.google import GoogleAdapter

# Session API
from session import Session, SessionOptions

# Types
from agent_types import (
    Action,
    ActionExecution,
    ActionOutcome,
    AgentOptions,
    BrowserOptions,
    LogLine,
    LoopOptions,
    LoopResult,
    Point,
    PreActionDecision,
    PreActionHook,
    RunOptions,
    RunResult,
    ScreenshotOptions,
    ScreenshotResult,
    SemanticStep,
    SerializedAgent,
    SerializedHistory,
    StreamEvent,
    TaskState,
    TokenUsage,
    ViewportSize,
)

# TypeScript-style aliases for public parity.
runPlanner = run_planner
denormalizePoint = denormalize_point

__all__ = [
    # Public API
    "Agent",
    "AgentOptions",
    "SerializedAgent",
    "BrowserOptions",
    # Logger
    "BrowserAgentLogger",
    # Session API
    "Session",
    "SessionOptions",
    # Types
    "Action",
    "StreamEvent",
    "RunResult",
    "RunOptions",
    "LoopOptions",
    "LoopResult",
    "TaskState",
    "SemanticStep",
    "SerializedHistory",
    "ScreenshotResult",
    "ScreenshotOptions",
    "ActionOutcome",
    "ActionExecution",
    "TokenUsage",
    "LogLine",
    "ViewportSize",
    "Point",
    "PreActionHook",
    "PreActionDecision",
    # Errors
    "BrowserAgentError",
    "BrowserAgentErrorCode",
    # Browser
    "BrowserTab",
    "ClickOptions",
    "TypeOptions",
    "DragOptions",
    "CDPTab",
    "CdpConnection",
    "ViewportManager",
    "launch_chrome",
    "BrowserbaseOptions",
    # Model adapters
    "ModelAdapter",
    "StepContext",
    "ModelResponse",
    "denormalize",
    "normalize",
    "denormalize_point",
    "denormalizePoint",
    "ActionDecoder",
    "GoogleAdapter",
    # Loop primitives
    "StateStore",
    "HistoryManager",
    "ActionRouter",
    "RouterTiming",
    "PerceptionLoop",
    "PerceptionLoopOptions",
    "ChildLoop",
    "ChildLoopOptions",
    "ChildLoopResult",
    "run_planner",
    "RepeatDetector",
    "ActionCache",
    "viewport_mismatch",
    # Policy
    "SessionPolicy",
    "SessionPolicyOptions",
    "SessionPolicyResult",
    # Verifiers
    "UrlMatchesGate",
    "CustomGate",
    "ModelVerifier",
    "Verifier",
    "VerifyResult",
    # Monitors
    "ConsoleMonitor",
    "NoopMonitor",
    "LoopMonitor",
    "StreamingMonitor",
    # Optional features
    "ConfidenceGate",
    "ActionVerifier",
    "ActionVerification",
    "CheckpointManager",
    "BrowserCheckpoint",
    "SiteKB",
    "SiteRule",
    "WorkflowMemory",
    "Workflow",
    "connect_browserbase"
]
