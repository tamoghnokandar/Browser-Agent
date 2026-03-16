"""
ActionDecoder: translates provider tool/function calls into internal Action dicts.
Port of src/model/decoder.ts.
"""
from __future__ import annotations

from typing import Any, Dict
from urllib.parse import quote_plus

from agent_types import Action, ViewportSize
from model.adapter import denormalize


class ActionDecoder:
    """Decode provider-specific tool calls into internal Action shapes."""

    def from_google(
        self,
        call: Dict[str, Any],
        viewport: ViewportSize,
    ) -> Action:
        """
        Google function_call -> Action.
        Coordinates are 0-1000 -> denormalize to pixels.
        """
        name = call.get("name")
        args = call.get("args", {})

        # Legacy computer_use tool (older Google models)
        if name == "computer_use":
            action = args.get("action")

            if action == "screenshot":
                return {"type": "screenshot"}

            if action == "click":
                return {
                    "type": "click",
                    "x": denormalize(args["x"], viewport.width),
                    "y": denormalize(args["y"], viewport.height),
                    "button": args.get("button", "left"),
                }

            if action == "double_click":
                return {
                    "type": "doubleClick",
                    "x": denormalize(args["x"], viewport.width),
                    "y": denormalize(args["y"], viewport.height),
                }

            if action in ("hover", "move"):
                return {
                    "type": "hover",
                    "x": denormalize(args["x"], viewport.width),
                    "y": denormalize(args["y"], viewport.height),
                }

            if action == "drag":
                return {
                    "type": "drag",
                    "startX": denormalize(args["startX"], viewport.width),
                    "startY": denormalize(args["startY"], viewport.height),
                    "endX": denormalize(args["endX"], viewport.width),
                    "endY": denormalize(args["endY"], viewport.height),
                }

            if action == "scroll":
                return {
                    "type": "scroll",
                    "x": denormalize(args["x"], viewport.width),
                    "y": denormalize(args["y"], viewport.height),
                    "direction": args.get("direction", "down"),
                    "amount": args.get("amount", 3),
                }

            if action == "type":
                return {"type": "type", "text": args.get("text", "")}

            if action == "key":
                return {"type": "keyPress", "keys": [args["key"]]}

            if action == "navigate":
                return {"type": "goto", "url": args["url"]}

            if action == "terminate":
                return {
                    "type": "terminate",
                    "status": args.get("status", "success"),
                    "result": args.get("result", ""),
                }

        # Native Gemini computer-use function names
        if name == "click_at":
            return {
                "type": "click",
                    "x": denormalize(args["x"], viewport.width),
                    "y": denormalize(args["y"], viewport.height),
                "button": args.get("button", "left"),
            }

        if name == "type_text_at":
            return {"type": "type", "text": args.get("text", "")}

        if name in ("navigate", "go_to_url"):
            return {"type": "goto", "url": args["url"]}

        if name == "search":
            query = args.get("query") or args.get("text") or ""
            url = (
                f"https://www.google.com/search?q={quote_plus(query)}"
                if query else
                "https://www.google.com"
            )
            return {"type": "goto", "url": url}

        if name in ("scroll_at", "scroll"):
            return {
                "type": "scroll",
                "x": denormalize(args.get("x", 500), viewport.width),
                "y": denormalize(args.get("y", 500), viewport.height),
                "direction": args.get("direction", "down"),
                "amount": args.get("amount", 3),
            }

        if name in ("key_press", "press_key"):
            key = args.get("key") or args.get("keys") or "Return"
            return {"type": "keyPress", "keys": [key]}

        if name in ("wait", "wait_5_seconds", "wait_for_page_load"):
            ms = (
                5000 if name == "wait_5_seconds"
                else args.get("ms")
                or ((args["seconds"] * 1000) if "seconds" in args else 2000)
            )
            return {"type": "wait", "ms": ms}

        if name in ("back", "go_back"):
            return {"type": "keyPress", "keys": ["Alt+ArrowLeft"]}

        if name in ("forward", "go_forward"):
            return {"type": "keyPress", "keys": ["Alt+ArrowRight"]}

        if name in ("terminate", "done", "finish"):
            return {
                "type": "terminate",
                "status": args.get("status", "success"),
                "result": args.get("result") or args.get("answer") or "",
            }

        if name == "open_web_browser":
            return {"type": "screenshot"}

        return {"type": "screenshot"}