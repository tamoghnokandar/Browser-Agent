# Browser Agent

A vision-first browser agent with self-healing deterministic replay.

## Features

- **Vision-only loop** — screenshot → model → action(s) → screenshot. No DOM scraping, no selectors.
- **Google Gemini** — Native support for Gemini computer-use models.
- **History compression** — tier-1 screenshot compression + tier-2 LLM summarization at 80% context utilization.
- **Unified coordinates** — `ActionDecoder` normalizes all provider formats to viewport pixels at decode time.
- **Persistent memory** — `writeState` persists structured JSON that survives history compaction.
- **Streaming** — `agent.stream()` yields typed `StreamEvent` objects for real-time UI.
- **Session resumption** — serialize to JSON, restore later with `Agent.resume()`.
- **Safety** — `SessionPolicy` (domain allowlist/blocklist), `PreActionHook` (imperative deny), `Verifier` (completion gate).
- **Repeat detection** — three-layer stuck detection with escalating nudges.
- **Action caching** — on-disk cache for replaying known-good actions.
- **Child delegation** — the model can hand off sub-tasks to a fresh loop via `delegate`.

## Install

```bash
# Clone the repository and install dependencies
git clone <repository-url>
cd Browser-Agent
uv sync
```

Requires Python ≥3.11 and Chrome/Chromium for local browser mode.

### Local browser (Playwright)

Local browser mode uses [Playwright for Python](https://github.com/microsoft/playwright-python). After `uv sync`:

```bash
playwright install chromium
# On Linux/WSL, also install system dependencies (fixes libasound errors):
playwright install-deps   # or: sudo playwright install-deps
```

## Usage

### One-shot

```python
import asyncio
from index import Agent

async def main():
    result = await Agent.run_once({
        "model": "google/gemini-3-flash-preview",
        "browser": {"type": "local", "headless": True},
        "instruction": "Find the price of the top result for 'mechanical keyboard' on Amazon.",
        "max_steps": 15,
    })
    print(result["result"])

asyncio.run(main())
```

### Multi-run session

```python
agent = Agent({
    "model": "google/gemini-3-flash-preview",
    "browser": {"type": "local"},
})

await agent.run({"instruction": "Navigate to github.com"})
await agent.run({"instruction": "Search for the 'react' repository."})
await agent.close()
```

### Pre-navigate with start_url

Save 1–2 model steps by going to the target page before the first screenshot:

```python
result = await Agent.run_once({
    "model": "google/gemini-3-flash-preview",
    "browser": {"type": "local"},
    "instruction": "Find the cheapest flight from JFK to LAX next Friday.",
    "start_url": "https://www.google.com/travel/flights",
})
```

### Demo example

Create a `.env` file in the project root with:

```
GEMINI_API_KEY=your-api-key-here
BROWSER_AGENT_MODEL=google/gemini-3-flash-preview
BROWSER_AGENT_HEADED=true
```

Then run the demo (Linux/macOS):

```bash
# From repo root
uv run python app.py
```

The demo loads variables from `.env` automatically.

With `BROWSER_AGENT_HEADED=true`, a Chrome window opens so you can watch the agent browse. Without it, the agent runs headless.

## Models

Pass `"google/model-id"` for Gemini models:

```python
model: "google/gemini-2.5-pro"
model: "google/gemini-3-flash-preview"   # default in examples
```

## API Keys

Create a `.env` file in the project root with:

```
GEMINI_API_KEY=your-api-key-here
BROWSER_AGENT_MODEL=google/gemini-3-flash-preview
BROWSER_AGENT_HEADED=true
```

You can also pass `api_key` in options or set these as environment variables.

## Browser Options

```python
# Local Chrome (default)
browser: {"type": "local", "headless": True, "port": 9222}

# Existing CDP endpoint
browser: {"type": "cdp", "url": "ws://localhost:9222/devtools/browser/..."}

# Browserbase (cloud — no local Chrome needed)
browser: {
    "type": "browserbase",
    "apiKey": "…",
    "projectId": "…",
}
```

## Safety

### SessionPolicy

```python
policy: {
    "allowed_domains": ["*.mycompany.com"],
    "blocked_domains": ["facebook.com"],
    "allowed_actions": ["click", "type", "scroll", "goto", "terminate"],
}
```

### PreActionHook

```python
async def pre_action_hook(action):
    if action.get("type") == "goto" and "checkout" in action.get("url", ""):
        return {"decision": "deny", "reason": "checkout not permitted"}
    return {"decision": "allow"}

agent = Agent({"model": "...", "browser": {...}, "pre_action_hook": pre_action_hook})
```

### Verifier

```python
import re
from index import Agent, UrlMatchesGate, ModelVerifier, GoogleAdapter

# URL pattern match
verifier = UrlMatchesGate(r"/confirmation\?order=\d+")

# Model-based verification
verifier = ModelVerifier(
    GoogleAdapter("gemini-3-flash-preview"),
    "Complete the checkout flow",
)

agent = Agent({"model": "google/gemini-3-flash-preview", "browser": {...}, "verifier": verifier})
```

## Session Resumption

```python
# Save
snapshot = await agent.serialize()
with open("session.json", "w") as f:
    json.dump(snapshot, f)

# Restore
with open("session.json") as f:
    data = json.load(f)
agent2 = Agent.resume(data, {"model": "...", "browser": {"type": "local"}})
```

## Options

| Option                    | Type                 | Default | Description                                      |
| ------------------------- | -------------------- | ------- | ------------------------------------------------ |
| `model`                   | str                  | —       | Model ID (e.g. `google/gemini-2.0-flash`)        |
| `browser`                 | dict                 | —       | Browser config (`type`, `headless`, `url`, etc.) |
| `api_key`                 | str                  | env     | Override API key                                 |
| `base_url`                | str                  | —       | Unused (Google only)                             |
| `max_steps`               | int                  | 30      | Max perception loop steps                        |
| `system_prompt`           | str                  | —       | Extra system instructions                        |
| `planner_model`           | str                  | —       | Cheap model for pre-loop planning                |
| `thinking_budget`         | int                  | 0       | Unused (kept for API compatibility)              |
| `compaction_threshold`    | float                | 0.8     | Trigger LLM compaction at this utilization       |
| `compaction_model`        | str                  | —       | Model for summarization                          |
| `keep_recent_screenshots` | int                  | 2       | Screenshots to keep before compression           |
| `auto_align_viewport`     | bool                 | True    | Align viewport to model patch size               |
| `cursor_overlay`          | bool                 | True    | Draw cursor dot on screenshots                   |
| `verbose`                 | 0\|1\|2              | 1       | Log verbosity                                    |
| `logger`                  | callable             | —       | Custom log handler                               |
| `monitor`                 | LoopMonitor          | —       | Step/action event callbacks                      |
| `policy`                  | SessionPolicyOptions | —       | Domain allowlist/blocklist                       |
| `pre_action_hook`         | PreActionHook        | —       | Imperative action deny                           |
| `verifier`                | Verifier             | —       | Completion gate                                  |
| `cache_dir`               | str                  | —       | Action cache directory                           |
| `initial_history`         | SerializedHistory    | —       | Resume from snapshot                             |
| `initial_state`           | TaskState            | —       | Initial `writeState` data                        |

## Project Structure

```
├── agent.py           # Agent facade, run_once, stream, resume
├── session.py         # Session, PerceptionLoop orchestration
├── index.py           # Public API exports
├── agent_types.py     # Action, RunResult, AgentOptions, etc.
├── logger.py          # BrowserAgentLogger
├── errors.py          # BrowserAgentError, BrowserAgentErrorCode
│
├── browser/           # CDP, tab, viewport, launch
│   ├── cdp.py         # CdpConnection (WebSocket)
│   ├── cdptab.py      # CDPTab (Page.*, Input.*)
│   ├── tab.py         # BrowserTab protocol
│   ├── viewport.py    # ViewportManager
│   └── launch/
│       ├── local.py   # launch_chrome
│       └── browserbase.py
│
├── model/             # Adapters, decoder, normalization
│   ├── adapter.py     # ModelAdapter, StepContext, withRetry
│   ├── decoder.py     # ActionDecoder (provider → viewport pixels)
│   └── google.py      # GoogleAdapter (Gemini)
│
├── loop/              # Perception loop, history, routing
│   ├── perception.py  # PerceptionLoop (core)
│   ├── history.py     # HistoryManager (wire + semantic)
│   ├── router.py      # ActionRouter (dispatch to CDP)
│   ├── state.py       # StateStore (writeState)
│   ├── repeat_detector.py
│   ├── action_verifier.py
│   ├── action_cache.py
│   ├── checkpoint.py  # CheckpointManager, backtrack
│   ├── child.py       # ChildLoop (delegate)
│   ├── planner.py     # run_planner
│   ├── policy.py      # SessionPolicy
│   ├── verifier.py    # UrlMatchesGate, ModelVerifier
│   ├── confidence_gate.py
│   ├── monitor.py     # LoopMonitor, ConsoleMonitor
│   └── streaming_monitor.py
│
├── memory/            # SiteKB, WorkflowMemory
│   ├── site_kb.py
│   └── workflow.py
│
├── app.py             # TodoMVC demo
│
└── tests/
    ├── unit/
    └── integration/
```

## Architecture

Browser Agent uses a **perception loop** — screenshot → think → act → repeat — driven by Google Gemini over Chrome DevTools Protocol (CDP):

```
                    ┌──────────────────────────────────────┐
                    │     Browser Agent — PerceptionLoop   │
                    │                                      │
 ┌────────┐   ┌────┴─────┐   ┌───────────┐   ┌─────────┐ │
 │ Chrome ├──▶│Screenshot├──▶│  History   ├──▶│  Build  │ │
 │ (CDP)  │   └──────────┘   │  Manager   │   │ Context │ │
 │        │                  │            │   │         │ │
 │        │                  │ tier-1:    │   │ + state │ │
 │        │                  │  compress  │   │ + KB    │ │
 │        │                  │ tier-2:    │   │ + nudge │ │
 │        │                  │  summarize │   └────┬────┘ │
 │        │                  └────────────┘        │      │
 │        │                                        ▼      │
 │        │   ┌──────────┐   ┌────────────────────────┐   │
 │        │   │  Action   │   │  GoogleAdapter (Gemini) │   │
 │        │◀──┤  Router   │◀──┤  stream actions         │   │
 │        │   │          │   │                        │   │
 │        │   │ click    │   │  google/gemini-*       │   │
 │        │   │ type     │   │                        │   │
 │        │   │ scroll   │   └────────────────────────┘   │
 │        │   │ goto     │                                │
 │        │   └────┬─────┘                                │
 │        │        │                                      │
 │        │        ▼                                      │
 │        │   ┌──────────────────┐                        │
 │        │   │  Post-Action     │                        │
 │        │   │                  │                        │
 │        │   │ ActionVerifier   │◀─ heuristic checks     │
 │        │   │ RepeatDetector   │◀─ 3-layer stuck detect │
 │        │   │ Checkpoint       │◀─ save for backtrack   │
 │        │   └────────┬─────────┘                        │
 │        │            │                                  │
 │        │            ▼                                  │
 │        │   ┌──────────────────┐                        │
 │        │   │  task_complete?  │                        │
 │        │   │                  │     ┌──────────┐       │
 │        │   │  yes ──────────────▶│ Verifier │       │
 │        │   │                  │     │  (gate)  │       │
 │        │   │                  │     └────┬─────┘       │
 │        │   └──────────────────┘          │             │
 └────────┘                          pass ──▶ done        │
                                     fail ──▶ continue    │
                    └──────────────────────────────────────┘
```

**Step by step:**

1. **Screenshot** — capture the browser viewport via CDP
2. **History** — append to wire history; if context exceeds threshold, compress (tier-1: drop old screenshots, tier-2: LLM summarization)
3. **Context** — assemble system prompt with persistent state, site-specific tips (SiteKB), stuck nudges, and workflow hints
4. **Model** — Google Gemini streams actions (GoogleAdapter)
5. **Execute** — ActionRouter dispatches each action to Chrome via CDP (click, type, scroll, goto, etc.)
6. **Verify action** — ActionVerifier runs heuristic post-checks
7. **Detect loops** — RepeatDetector checks 3 layers: exact action repeats, category dominance, URL stall
8. **Checkpoint** — periodically save browser state; backtrack on deep stalls
9. **Termination gate** — when the model calls `task_complete`, the Verifier checks the screenshot. Rejected? Loop continues. Passed? Return result.

## Testing

```bash
uv sync --all-extras
uv run pytest
```

## Troubleshooting

**Chrome fails to launch** — Verify Chrome is installed. On Linux (including WSL), if you see `libasound.so.2: cannot open shared object file`, run `playwright install-deps` (or `sudo playwright install-deps` on Ubuntu/Debian) to install required system libraries. On Linux CI, launch Chrome with `--no-sandbox` yourself and use `browser: {"type": "cdp", "url": "ws://..."}`.

**API key not found** — Set `GOOGLE_API_KEY` or `GEMINI_API_KEY`.

**Loop hits max_steps** — Increase `max_steps`, add a focused `system_prompt`, or use `verbose: 2` to debug.

**BROWSER_DISCONNECTED** — The CDP socket closed unexpectedly. This is the only error that throws; all action errors are fed back to the model.

**ModuleNotFoundError** — Run from the repo root so the `pythonpath` in `pyproject.toml` is applied (e.g. `uv run python app.py`).

## License

MIT
