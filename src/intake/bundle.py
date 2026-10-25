"""Checklist bundle loaded from contracts/bundle.json."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# phase_order names the phases. Section letters are the bundle's own codes.
PHASE_SECTIONS: dict[str, tuple[str, ...]] = {
    "priority_access_payment": ("P", "A"),
    "objectives_profit": ("R", "O"),
    "tools_flows": ("F",),
    "data_pulls": ("D",),
    "context_supply": ("C", "ST"),
}


@dataclass(frozen=True)
class Item:
    id: str
    section: str
    role: str
    text: str
    why: str
    type: str
    data_spec: Any
    priority: bool


@dataclass(frozen=True)
class Bundle:
    items: tuple[Item, ...]

    def by_id(self, item_id: str) -> Item | None:
        for item in self.items:
            if item.id == item_id:
                return item
        return None


def load_bundle(path: Path) -> Bundle:
    data = json.loads(path.read_text(encoding="utf-8"))
    raw_items = data["items"]
    if not isinstance(raw_items, list) or len(raw_items) != 32:
        raise ValueError(f"bundle must contain 32 items, found {len(raw_items) if isinstance(raw_items, list) else 0}")
    phase_order = list(data["phase_order"])
    section_phase: dict[str, int] = {}
    for index, phase in enumerate(phase_order):
        sections = PHASE_SECTIONS.get(str(phase))
        if sections is None:
            raise ValueError(f"no section mapping for phase {phase!r}")
        for section in sections:
            if section in section_phase:
                raise ValueError(f"section {section} belongs to more than one phase")
            section_phase[section] = index

    parsed: list[tuple[int, Item]] = []
    for original, raw in enumerate(raw_items):
        for field in ("id", "section", "role", "text"):
            if field not in raw or not isinstance(raw[field], str) or not raw[field]:
                raise ValueError(f"item {original} is missing {field}")
        section = raw["section"]
        if section not in section_phase:
            raise ValueError(f"section {section!r} is not in phase_order")
        parsed.append(
            (
                original,
                Item(
                    id=raw["id"],
                    section=section,
                    role=raw["role"],
                    text=raw["text"],
                    why=str(raw.get("why") or ""),
                    type=str(raw.get("type") or ""),
                    data_spec=raw.get("data_spec"),
                    priority=bool(raw.get("priority")),
                ),
            )
        )

    ordered = tuple(
        item
        for _, item in sorted(
            parsed,
            key=lambda pair: (
                section_phase[pair[1].section],
                0 if pair[1].priority else 1,
                pair[0],
            ),
        )
    )
    ids = [item.id for item in ordered]
    if len(ids) != len(set(ids)):
        raise ValueError("bundle item ids are not unique")
    return Bundle(items=ordered)
