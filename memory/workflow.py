"""
WorkflowMemory: reusable workflow storage. Port of src/memory/workflow.ts.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, TypedDict
from urllib.parse import urlparse


class Workflow(TypedDict):
    """A workflow entry: name, trigger, steps, domain, successCount."""
    name: str
    trigger: str
    steps: List[str]
    domain: str
    successCount: int

STOP_WORDS = {
    "the", "this", "that", "what", "which", "where", "when", "how",
    "from", "with", "into", "about", "than", "then", "them", "their",
    "have", "been", "will", "would", "could", "should", "does",
    "find", "show", "tell", "give", "make", "take", "look",
}


def mode(arr: List[str]) -> Optional[str]:
    counts: Dict[str, int] = {}
    for item in arr:
        counts[item] = counts.get(item, 0) + 1

    best: Optional[str] = None
    best_count = 0
    for item, count in counts.items():
        if count > best_count:
            best_count = count
            best = item
    return best


def describe_action(action: Dict[str, Any], url: str) -> Optional[str]:
    action_type = action.get("type")

    if action_type == "click":
        return f'Click at ({action.get("x")}, {action.get("y")})'

    if action_type == "type":
        text = str(action.get("text", ""))
        return f'Type "{text[:30]}"'

    if action_type == "keyPress":
        keys = action.get("keys", [])
        return f'Press {"+".join(keys)}'

    if action_type == "goto":
        target_url = str(action.get("url", ""))
        domain = target_url
        try:
            parsed = urlparse(target_url)
            if parsed.hostname:
                domain = parsed.hostname
        except Exception:
            pass
        return f"Navigate to {domain}"

    if action_type == "scroll":
        return f'Scroll {action.get("direction")}'

    if action_type == "writeState":
        return "Save progress"

    if action_type in {"terminate", "wait", "screenshot"}:
        return None

    return action_type


class WorkflowMemory:
    def __init__(self, workflows: Optional[List[Workflow]] = None) -> None:
        self._workflows: List[Workflow] = workflows if workflows is not None else []

    @classmethod
    def from_file(cls, path: str) -> "WorkflowMemory":
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            return cls(data)
        except Exception:
            return cls()

    def match(self, instruction: str, url: Optional[str] = None) -> Optional[Workflow]:
        lower = instruction.lower()
        best_match: Optional[Workflow] = None
        best_score = 0

        for wf in self._workflows:
            triggers = [t.strip().lower() for t in str(wf.get("trigger", "")).split("|")]
            score = 0

            for trigger in triggers:
                if trigger and trigger in lower:
                    score += len(trigger)

            if url and score > 0:
                try:
                    hostname = urlparse(url).hostname or ""
                    if str(wf.get("domain", "")) in hostname:
                        score += 10
                except Exception:
                    pass

            score += min(int(wf.get("successCount", 0)), 5)

            if score > best_score:
                best_score = score
                best_match = wf

        return best_match

    def to_prompt_hint(self, workflow: Workflow) -> str:
        steps = workflow.get("steps", [])
        steps_text = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(steps))
        return (
            f'SUGGESTED WORKFLOW (from past success on "{workflow.get("name", "")}"):\n'
            f"{steps_text}\n"
            "This is a suggestion — adapt as needed for the current task."
        )

    @staticmethod
    def extract(
        instruction: str,
        history: List[Dict[str, Any]],
        domain: Optional[str] = None,
    ) -> Optional[Workflow]:
        if len(history) < 3:
            return None

        steps: List[str] = []
        last_action_type = ""

        for step in history:
            for action_entry in step.get("actions", []):
                action = action_entry.get("action", {})
                desc = describe_action(action, step.get("url", ""))

                action_type = action.get("type", "")
                if action_type == last_action_type and action_type in {"scroll", "wait"}:
                    continue

                if desc:
                    steps.append(desc)
                    last_action_type = action_type

        if len(steps) < 2:
            return None

        trigger_words = [
            w for w in re.sub(r"[^a-z0-9\s]", "", instruction.lower()).split()
            if len(w) > 3 and w not in STOP_WORDS
        ][:4]

        trigger = " ".join(trigger_words)
        if not trigger:
            return None

        primary_domain = domain or ""
        if not primary_domain:
            domains: List[str] = []
            for step in history:
                try:
                    hostname = urlparse(step.get("url", "")).hostname or ""
                    if hostname:
                        domains.append(hostname)
                except Exception:
                    pass
            primary_domain = mode(domains) or ""

        return {
            "name": instruction[:60],
            "trigger": trigger,
            "steps": steps[:15],
            "domain": primary_domain,
            "successCount": 1,
        }

    def add(self, workflow: Workflow) -> None:
        existing = next(
            (
                w for w in self._workflows
                if w.get("domain") == workflow.get("domain")
                and w.get("trigger") == workflow.get("trigger")
            ),
            None,
        )

        if existing is not None:
            existing["successCount"] = int(existing.get("successCount", 0)) + 1

            existing_steps = existing.get("steps", [])
            new_steps = workflow.get("steps", [])
            if len(new_steps) < len(existing_steps):
                existing["steps"] = new_steps
        else:
            self._workflows.append(workflow)

    def save(self, path: str) -> None:
        Path(path).write_text(json.dumps(self._workflows, indent=2), encoding="utf-8")

    def to_json(self) -> List[Workflow]:
        return self._workflows