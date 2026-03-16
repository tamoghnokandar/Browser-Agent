"""
Single-Page App stress test — TodoMVC (React SPA).
Python port of examples/todomvc-test.ts.

Tests CUA agent on a TodoMVC app: create todos, complete one, verify count.

Usage:
  # From repo root:
  uv run python app.py

  # With visible browser:
  BROWSER_AGENT_HEADED=true uv run python app.py

Requires: GOOGLE_API_KEY or GEMINI_API_KEY (for Gemini), Playwright (playwright install chromium)
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

# Add repo root to path so package can be imported
_repo_root = Path(__file__).resolve().parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

# Load .env from project root (optional; falls back to shell env vars)
try:
    from dotenv import load_dotenv
    load_dotenv(_repo_root / ".env")
except ImportError:
    pass

model = os.environ.get("BROWSER_AGENT_MODEL", "google/gemini-3-flash-preview")
headed = os.environ.get("BROWSER_AGENT_HEADED", "").lower() == "true"

# TASK = {
#     "instruction": "\n".join([
#         "You are a productivity assistant testing a TodoMVC application.",
#         "This is a single-page app — the URL will not change.",
#         "",
#         "STEP 1 — CREATE TODOS:",
#         "Create these 3 todo items by typing in the input field at the top (it says 'What needs to be done?') and pressing Enter after each:",
#         "  1. Buy groceries",
#         "  2. Walk the dog",
#         "  3. Read a book",
#         "",
#         "STEP 2 — COMPLETE ONE:",
#         "Mark 'Buy groceries' as completed by clicking the circle/checkbox next to it.",
#         "",
#         "STEP 3 — VERIFY:",
#         "Look at the bottom of the list. It should show '2 items left'.",
#         "Report what you see: all 3 todos and their completion status, and the items-left count.",
#     ]),
#     "start_url": "https://todomvc.com/examples/react/dist/",
#     "max_steps": 25,
# }

TASK = {
  "instruction": "\n".join([
    
    "Go to Hacker News (https://news.ycombinator.com).",
    "Find the top 5 stories on the front page.",
    "For each story, record: the title, the number of points, and the number of comments.",
    "Then go to the second page (More link at the bottom) and find the top 3 stories there.",
    "Return ALL 8 stories in a numbered list with title, points, and comments.",
  
  ]),
  "start_url": "https://news.ycombinator.com",
  "max_steps": 30,
};

async def main() -> None:
    from index import Agent

    print("\n=== Browser Agent SPA Test — TodoMVC (Python) ===\n")
    print(f"Model:    {model}")
    print(f"Headed:   {headed}")
    print(f"MaxSteps: {TASK['max_steps']}\n")

    start_time = time.perf_counter()

    result = await Agent.run_once({
        "model": model,
        "browser": {"type": "local", "headless": not headed},
        "max_steps": TASK["max_steps"],
        "verbose": 2,
        "instruction": TASK["instruction"],
        "start_url": TASK["start_url"],
        "max_steps": TASK["max_steps"],
    })

    elapsed = time.perf_counter() - start_time

    # Result can be dict (from session) or RunResult dataclass
    status = result.get("status", getattr(result, "status", "unknown"))
    steps = result.get("steps", getattr(result, "steps", 0))
    task_result = result.get("result", getattr(result, "result", ""))
    token_usage = result.get("tokenUsage", getattr(result, "token_usage", {}))
    history = result.get("history", getattr(result, "history", []))

    input_tokens = token_usage.get("inputTokens", token_usage.get("input_tokens", 0))
    output_tokens = token_usage.get("outputTokens", token_usage.get("output_tokens", 0))

    print("=" * 60)
    print(f"Status:   {status}")
    print(f"Steps:    {steps}")
    print(f"Time:     {elapsed:.1f}s")
    print(f"Tokens:   {input_tokens:,} in / {output_tokens:,} out")
    print("=" * 60)
    print("\n--- Agent Output ---\n")
    print(task_result)
    print("\n--- Execution Trace ---")
    for step in history:
        step_idx = step.get("step_index", 0) if isinstance(step, dict) else getattr(step, "step_index", 0)
        actions_list = step.get("actions", []) if isinstance(step, dict) else getattr(step, "actions", [])
        duration_ms = step.get("duration_ms", 0) if isinstance(step, dict) else getattr(step, "duration_ms", 0)
        action_labels = []
        for ar in actions_list:
            action = ar.get("action", getattr(ar, "action", {}))
            outcome = ar.get("outcome", getattr(ar, "outcome", {}))
            label = action.get("type", getattr(action, "type", "unknown"))
            if label == "goto":
                url = action.get("url", getattr(action, "url", ""))
                label += f" → {url[:50]}"
            elif label == "type":
                text = action.get("text", getattr(action, "text", ""))
                label += f' "{text[:30]}"'
            elif label == "writeState":
                label += " 📝"
            ok = outcome.get("ok", getattr(outcome, "ok", True))
            if not ok:
                label += " ✗"
            action_labels.append(label)
        actions_str = ", ".join(action_labels)
        print(f"  [{step_idx + 1:2}] {actions_str} ({duration_ms / 1000:.1f}s)")


if __name__ == "__main__":
    asyncio.run(main())
