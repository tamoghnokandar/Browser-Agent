"""
Planner: produces numbered step-by-step plan. Port of src/loop/planner.ts.
"""
from __future__ import annotations


async def run_planner(
    instruction: str,
    screenshot: object,
    adapter: object,
) -> str:
    context = {
        "screenshot": screenshot,
        "wire_history": [],
        "agent_state": None,
        "step_index": 0,
        "max_steps": 1,
        "url": "",
        "system_prompt": "\n".join([
            "You are a task planner. Given the current screenshot and instruction, produce a numbered step-by-step plan.",
            "Be concise. Output ONLY the numbered plan, no other text.",
            f"Instruction: {instruction}",
        ]),
    }
    response = await adapter.step(context)

    thinking = response.get("thinking")
    if thinking:
        return thinking

    return f"Plan for: {instruction}\n1. Analyze the current screen\n2. Execute the required steps\n3. Verify completion and terminate"
