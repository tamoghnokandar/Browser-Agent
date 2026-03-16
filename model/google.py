"""
GoogleAdapter: Gemini Computer Use adapter using google-genai.
Integrated version that imports the real shared adapter/decoder/types modules.
"""
from __future__ import annotations

import json
import os
from typing import Any, AsyncIterable, Optional

from google import genai
from google.genai import types

from agent_types import Action, TokenUsage, ViewportSize, WireMessage
from .adapter import ModelAdapter, ModelResponse, with_retry
from .decoder import ActionDecoder

decoder = ActionDecoder()


def _ctx(ctx: Any, key: str, default: Any = None) -> Any:
    """Get context field; supports both StepContext (object) and dict from perception."""
    if isinstance(ctx, dict):
        return ctx.get(key, default)
    return getattr(ctx, key, default)


def build_system_instruction(context: Any) -> str:
    parts: list[str] = []

    system_prompt = _ctx(context, "system_prompt")
    if system_prompt:
        parts.append(system_prompt)

    url = _ctx(context, "url") or "(unknown)"
    step_index = _ctx(context, "step_index", 0)
    max_steps = _ctx(context, "max_steps", 1)

    parts.append(
        "You are a computer use agent browsing the web."
        f"\nCurrent URL: {url}"
        f"\nStep {step_index + 1} of {max_steps}"
        "\n\n#1 RULE — TERMINATE IMMEDIATELY: If the answer to the task is visible anywhere in the current screenshot "
        "(in any text, header, infobox, table, or element), call terminate(status='success', result='your answer') "
        "RIGHT NOW. Do NOT scroll, click, navigate, or take any other action first."
        "\n\nOTHER RULES:"
        "\n- Screenshots are provided automatically; never request one."
        "\n- Use navigate(url='...') to go to a URL."
        "\n- Take only ONE action per step; a new screenshot follows each action."
        "\n- If the page has a cookie/consent banner, dismiss it, then proceed with the task."
        "\n- LIST VIEWS: When a page shows items in a list or grid with visible values (prices, counts, ratings), read those values directly from the list. Do NOT click into individual items to verify data already visible in the list view."
        "\n- EFFICIENT SCROLLING: To move through a long page, press the Page_Down key (keyPress action) instead of small mouse scrolls — each Page_Down advances a full screen and covers content faster."
        "\n- TRUST YOUR MEMORY: If you have already memorized data from a page, do NOT navigate back to that page to re-verify. Trust what you recorded and use it directly to answer."
        "\n- MULTI-PAGE COLLECTION: Collect data page by page, memorize as you go, then terminate once you have data from all pages. Never revisit a page you already processed."
        "\n- BE DECISIVE: Once you have sufficient information to answer the task, call terminate immediately. Do not keep scrolling or browsing to double-check."
        "\n- THINK FIRST: Before acting, briefly consider: What key information is visible? What have I accomplished? What is my next step?"
        "\n- CHECKPOINT PROGRESS: Save your findings every 3-5 steps so they persist even if history is compacted. Include ALL data collected so far."
        "\n- VERIFY ACTIONS: After any form interaction (date picker, dropdown, filter, checkbox), CHECK the next screenshot to confirm your selection was applied correctly. If the field shows a wrong value or the filter shows wrong results, try again with a different approach."
        "\n- DATE PICKERS: 1) First try typing the date directly into the input field (common formats: MM/DD/YYYY, YYYY-MM-DD). 2) If using a calendar widget, navigate to the correct MONTH first using arrow buttons, then click the specific date. 3) After selecting, READ the date field value in the next screenshot to verify it matches your intent."
        "\n- FORMS: Fill one field at a time. For dropdowns, click to open then click the exact option text. If an element doesn't respond to clicks, try Tab key to move between fields, or type directly into focused inputs."
        "\n- URL FALLBACK: If form filling (especially date pickers or complex filters) fails after 2-3 attempts, construct the search URL with query parameters and navigate directly. Most sites encode search parameters in the URL."
        "\n- COMPLETE ALL SUB-TASKS: If the task asks for multiple pieces of information, track each one. Do NOT call terminate until ALL requested items are found."
        "\n- NEVER HALLUCINATE: Only report information you can see on screen. If a specific piece of data is not visible, say so rather than guessing."
    )

    agent_state = _ctx(context, "agent_state")
    if agent_state:
        parts.append(f"Current state: {json.dumps(agent_state)}")

    steps_remaining = max_steps - step_index - 1
    if steps_remaining <= max(3, max_steps // 10):
        parts.append(
            f"⚠️ URGENT: Only {steps_remaining} step(s) remaining! "
            "You MUST call terminate with your best answer on your NEXT action. "
            "Do NOT continue browsing."
        )

    return "\n\n".join(parts)


class GoogleAdapter(ModelAdapter):
    provider = "google"
    native_computer_use = True
    patch_size = 56
    max_image_dimension = 1568
    supports_thinking = True
    MAX_HISTORY_TURNS = 4

    def __init__(self, model_id: str, api_key: Optional[str] = None) -> None:
        self.model_id = model_id
        self.client = genai.Client(
            api_key=api_key
            or os.getenv("GOOGLE_API_KEY")
            or os.getenv("GEMINI_API_KEY")
            or ""
        )

        self.conversation_history: list[types.Content] = []
        self.pending_function_calls: list[types.FunctionCall] = []
        self.pending_has_safety_decision: list[bool] = []
        self._last_stream_response: Optional[ModelResponse] = None

    @property
    def context_window_tokens(self) -> int:
        return 1_000_000

    def prune_history(self) -> None:
        if len(self.conversation_history) <= 1 + self.MAX_HISTORY_TURNS * 2:
            return
        initial = self.conversation_history[0]
        recent = self.conversation_history[-(self.MAX_HISTORY_TURNS * 2):]
        self.conversation_history = [initial, *recent]

    def _make_config(self) -> types.GenerateContentConfig:
        return types.GenerateContentConfig(
            tools=[
                types.Tool(
                    computer_use=types.ComputerUse(
                        environment=types.Environment.ENVIRONMENT_BROWSER
                    )
                )
            ],
            thinking_config=types.ThinkingConfig(include_thoughts=True),
        )

    def _first_user_turn(self, context: Any) -> types.Content:
        parts: list[types.Part] = []

        # Put system instruction in user message; system_instruction in config can cause 400 with computer use
        parts.append(types.Part(text=build_system_instruction(context)))

        screenshot = _ctx(context, "screenshot")
        parts.append(
            types.Part.from_bytes(
                data=screenshot.data,
                mime_type=screenshot.mime_type,
            )
        )

        return types.Content(role="user", parts=parts)

    def _function_response_turn(self, context: Any) -> types.Content:
        response_parts: list[types.Part] = []
        screenshot = _ctx(context, "screenshot")
        url = _ctx(context, "url") or ""

        for i, fc in enumerate(self.pending_function_calls):
            response_payload: dict[str, Any] = {
                "url": url,
            }

            if i < len(self.pending_has_safety_decision) and self.pending_has_safety_decision[i]:
                response_payload["safety_acknowledgement"] = "true"

            fr = types.FunctionResponse(
                name=fc.name,
                response=response_payload,
                parts=[
                    types.FunctionResponsePart(
                        inline_data=types.FunctionResponseBlob(
                            mime_type=screenshot.mime_type,
                            data=screenshot.data,
                        )
                    )
                ],
            )
            response_parts.append(types.Part(function_response=fr))

        return types.Content(role="user", parts=response_parts)

    async def step(self, context: Any) -> ModelResponse:
        async def _impl() -> ModelResponse:
            if self.pending_function_calls:
                self.conversation_history.append(self._function_response_turn(context))
                self.pending_function_calls = []
                self.pending_has_safety_decision = []
                self.prune_history()
            else:
                self.conversation_history.append(self._first_user_turn(context))

            last_response: Any = None
            total_input_tokens = 0
            total_output_tokens = 0

            for _turn in range(5):
                response = self.client.models.generate_content(
                    model=self.model_id,
                    contents=self.conversation_history,
                    config=self._make_config(),
                )
                last_response = response

                usage = getattr(response, "usage_metadata", None)
                total_input_tokens += getattr(usage, "prompt_token_count", 0) or 0
                total_output_tokens += getattr(usage, "candidates_token_count", 0) or 0

                candidates = getattr(response, "candidates", None) or []
                candidate = candidates[0] if candidates else None
                content = getattr(candidate, "content", None)
                parts = list(getattr(content, "parts", None) or [])

                thinking_parts = [
                    getattr(part, "text", "") or ""
                    for part in parts
                    if getattr(part, "thought", False)
                ]
                thinking = " ".join(thinking_parts).strip() or None

                function_calls: list[types.FunctionCall] = [
                    part.function_call
                    for part in parts
                    if getattr(part, "function_call", None) is not None
                ]

                if not function_calls:
                    text_chunks = [
                        part.text
                        for part in parts
                        if getattr(part, "text", None)
                    ]
                    text = " ".join(text_chunks).strip()

                    if text:
                        self.conversation_history.append(
                            types.Content(role="model", parts=parts)
                        )
                        return ModelResponse(
                            actions=[{
                                "type": "terminate",
                                "status": "success",
                                "result": text,
                            }],
                            usage=TokenUsage(
                                input_tokens=total_input_tokens,
                                output_tokens=total_output_tokens,
                            ),
                            raw_response=last_response,
                            thinking=thinking,
                        )
                    break

                self.conversation_history.append(types.Content(role="model", parts=parts))

                open_browser_calls = [fc for fc in function_calls if fc.name == "open_web_browser"]
                action_calls = [fc for fc in function_calls if fc.name != "open_web_browser"]

                if open_browser_calls and not action_calls:
                    response_parts: list[types.Part] = []
                    _url = _ctx(context, "url") or ""
                    _scr = _ctx(context, "screenshot")
                    for fc in open_browser_calls:
                        fr = types.FunctionResponse(
                            name=fc.name,
                            response={
                                "url": _url,
                                "status": (
                                    "Browser is open. Examine the screenshot carefully. "
                                    "If the answer to the task is visible, call "
                                    "terminate(status='success', result='answer') immediately."
                                ),
                            },
                            parts=[
                                types.FunctionResponsePart(
                                    inline_data=types.FunctionResponseBlob(
                                        mime_type=_scr.mime_type,
                                        data=_scr.data,
                                    )
                                )
                            ],
                        )
                        response_parts.append(types.Part(function_response=fr))

                    self.conversation_history.append(
                        types.Content(role="user", parts=response_parts)
                    )
                    continue

                actions: list[Action] = []
                screenshot = _ctx(context, "screenshot")
                google_viewport = ViewportSize(
                    width=screenshot.width,
                    height=screenshot.height,
                )

                for fc in action_calls:
                    args = dict(fc.args) if fc.args else {}
                    actions.append(
                        decoder.from_google(
                            {"name": fc.name, "args": args},
                            google_viewport,
                        )
                    )
                    if fc.name == "type_text_at" and args.get("press_enter"):
                        actions.append({"type": "keyPress", "keys": ["Enter"]})

                has_terminate = any(action.get("type") == "terminate" for action in actions)
                if not has_terminate:
                    self.pending_function_calls = action_calls
                    self.pending_has_safety_decision = [
                        bool(getattr(fc, "args", None) and dict(fc.args).get("safety_decision"))
                        for fc in action_calls
                    ]

                return ModelResponse(
                    actions=actions,
                    usage=TokenUsage(
                        input_tokens=total_input_tokens,
                        output_tokens=total_output_tokens,
                    ),
                    raw_response=last_response,
                    thinking=thinking,
                )

            return ModelResponse(
                actions=[],
                usage=TokenUsage(
                    input_tokens=total_input_tokens,
                    output_tokens=total_output_tokens,
                ),
                raw_response=last_response,
                thinking=thinking,
            )

        return await with_retry(_impl)

    def get_last_stream_response(self) -> Optional[ModelResponse]:
        return self._last_stream_response

    async def stream(self, context: Any) -> AsyncIterable[Action]:
        response = await self.step(context)
        self._last_stream_response = response
        for action in response.actions:
            yield action

    def estimate_tokens(self, context: Any) -> int:
        wire_history = _ctx(context, "wire_history") or []
        return len(wire_history) * 200 + 1500

    async def summarize(
        self,
        wire_history: list[WireMessage],
        agent_state: Optional[dict[str, Any]],
    ) -> str:
        response = self.client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part(
                            text="\n\n".join(
                                part
                                for part in [
                                    "Summarize this computer use session history concisely.",
                                    f"Current state: {json.dumps(agent_state)}" if agent_state else "",
                                    f"History ({len(wire_history)} messages): {json.dumps(wire_history[-10:])}",
                                ]
                                if part
                            )
                        )
                    ],
                )
            ],
        )

        candidates = getattr(response, "candidates", None) or []
        if not candidates:
            return "Session history summarized."

        content = getattr(candidates[0], "content", None)
        parts = list(getattr(content, "parts", None) or [])
        text_parts = [part.text for part in parts if getattr(part, "text", None)]
        return " ".join(text_parts).strip() or "Session history summarized."