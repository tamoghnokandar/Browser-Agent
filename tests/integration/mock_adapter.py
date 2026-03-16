"""Mock ModelAdapter for integration tests. Port of tests/integration/mock-adapter.ts."""
from typing import Any, AsyncIterator, Dict, List, Optional


class MockAdapter:
    """Mock ModelAdapter that queues actions for successive steps."""

    model_id = "mock-model"
    provider = "mock"
    native_computer_use = False
    context_window_tokens = 100_000

    def __init__(self):
        self._action_queue: List[List[Dict[str, Any]]] = []
        self._step_count = 0
        self._last_stream_response: Optional[Dict[str, Any]] = None

    def queue_actions(self, actions: List[Dict[str, Any]]) -> "MockAdapter":
        """Queue actions to return on successive step() calls."""
        self._action_queue.append(actions)
        return self

    def queue_empty_response(self) -> "MockAdapter":
        """Queue an empty response (no actions)."""
        self._action_queue.append([])
        return self

    async def step(self, context: Dict[str, Any]) -> Dict[str, Any]:
        actions = self._action_queue[self._step_count] if self._step_count < len(self._action_queue) else [
            {"type": "terminate", "status": "success", "result": "done"}
        ]
        self._step_count += 1
        response = {
            "actions": actions,
            "usage": {"inputTokens": 100, "outputTokens": 50 if actions else 20},
            "rawResponse": None,
        }
        self._last_stream_response = response
        return response

    def get_last_stream_response(self) -> Optional[Dict[str, Any]]:
        return self._last_stream_response

    async def stream(self, context: Dict[str, Any]) -> AsyncIterator[Dict[str, Any]]:
        response = await self.step(context)
        for action in response.get("actions", []):
            yield action

    def estimate_tokens(self, context: Dict[str, Any]) -> int:
        return 1000

    async def summarize(
        self, wire_history: List[Dict[str, Any]], agent_state: Any
    ) -> str:
        return "Session summary."
