"""
Connect to Browserbase. Port of src/browser/launch/browserbase.ts.
"""
from __future__ import annotations

from typing import NotRequired, TypedDict

import aiohttp


class BrowserbaseOptions(TypedDict):
    """Options for connecting to Browserbase."""
    apiKey: str
    projectId: str
    sessionId: NotRequired[str]


async def connect_browserbase(opts: BrowserbaseOptions) -> dict[str, str]:
    api_key = opts["apiKey"]
    project_id = opts["projectId"]
    session_id = opts.get("sessionId")

    headers = {
        "X-BB-API-Key": api_key,
    }

    async with aiohttp.ClientSession() as session:
        if not session_id:
            headers["Content-Type"] = "application/json"
            payload = {"projectId": project_id}

            async with session.post(
                "https://api.browserbase.com/v1/sessions",
                headers=headers,
                json=payload,
            ) as res:
                if not res.ok:
                    text = await res.text()
                    raise RuntimeError(
                        f"Browserbase session creation failed ({res.status}): {text}"
                    )

                data = await res.json()
                return {
                    "wsUrl": data["connectUrl"],
                    "sessionId": data["id"],
                }

        async with session.get(
            f"https://api.browserbase.com/v1/sessions/{session_id}/debug",
            headers=headers,
        ) as res:
            if not res.ok:
                raise RuntimeError(
                    f"Browserbase session lookup failed ({res.status})"
                )

            data = await res.json()
            return {
                "wsUrl": data["wsUrl"],
                "sessionId": session_id,
            }
