"""Stage agents: one agent per SDLC stage, each run with a context built only from files.

An agent never receives another agent's memory. Its context is loaded fresh from the
artifacts its stage declares in `reads`, it does its one job through the same gates
people use (so every action is logged with the agent's name), and it exits. With
process isolation (the default in autopilot) each run is a separate Python process.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from sdlc import engine
from sdlc.store import Workspace, now_iso

ARTIFACTS = ("brd", "work_items", "bundle", "dependencies", "specs", "tickets", "status", "releases", "outbox", "draft", "answers")


@dataclass(frozen=True)
class AgentContext:
    """Everything an agent run is allowed to know."""

    agent: str
    subject: str
    inputs: dict[str, Any]
    now: str = field(default_factory=now_iso)
    pid: int = field(default_factory=os.getpid)


@dataclass
class Outcome:
    action: str
    detail: str
    ok: bool = True

    def as_dict(self) -> dict:
        return {"action": self.action, "detail": self.detail, "ok": self.ok}


class StageAgent:
    """Base class. Subclasses set key, name, stage, reads and implement find_work/run."""

    key = "agent"
    name = "Agent"
    stage = "spec"
    reads: tuple[str, ...] = ()
    system_prompt = ""

    @classmethod
    def find_work(cls, state: dict) -> list[str]:
        """Subjects (spec ids, ticket ids or 'client') ready for this agent."""
        return []

    def run(self, ctx: AgentContext, ws: Workspace) -> Outcome:
        raise NotImplementedError

    @classmethod
    def context(cls, ws: Workspace, subject: str) -> AgentContext:
        """Load only the declared artifacts, fresh from disk."""
        state = ws.load()
        loaders = {
            "brd": ws.brd,
            "work_items": ws.work_items,
            "bundle": ws.bundle,
            "dependencies": ws.dependencies,
            "specs": lambda: state["specs"],
            "tickets": lambda: state["tickets"],
            "status": lambda: state.get("status"),
            "releases": lambda: state["releases"],
            "outbox": lambda: state["outbox"],
            "draft": lambda: ws.read_draft(subject) if subject.startswith("SPEC-") and "-T" in subject else None,
            "answers": lambda: engine.answers_by_item(ws.work_items()),
        }
        unknown = set(cls.reads) - set(loaders)
        if unknown:
            raise ValueError(f"{cls.key} declares unknown artifacts: {sorted(unknown)}")
        inputs = {name: loaders[name]() for name in cls.reads}
        return AgentContext(agent=cls.name, subject=subject, inputs=inputs)


def spec_of(ctx: AgentContext, spec_id: str) -> dict | None:
    return next((s for s in ctx.inputs.get("specs", []) if s["id"] == spec_id), None)


def ticket_of(ctx: AgentContext, ticket_id: str) -> dict | None:
    return next((t for t in ctx.inputs.get("tickets", []) if t["id"] == ticket_id), None)
