"""Stroke-count targets: strings that should be typable within N strokes."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from .corpus import to_hiragana
from .layout import Layout


@dataclass
class TargetGroup:
    name: str
    priority: str
    max_strokes: int
    items: list[str]


def load_targets(path: str | Path) -> list[TargetGroup]:
    with open(path, "rb") as f:
        data = tomllib.load(f)
    return [
        TargetGroup(
            name=g["name"],
            priority=g.get("priority", ""),
            max_strokes=int(g["max_strokes"]),
            items=[to_hiragana(i) for i in g["items"]],
        )
        for g in data["group"]
    ]


def stroke_table(layout: Layout) -> dict[str, int]:
    """Fewest strokes for every output, including postfix-shift results."""
    best: dict[str, int] = {}
    for seq, out in layout.sequences().items():
        best[out] = min(best.get(out, len(seq)), len(seq))
    for seq, (_, after) in layout.postfix_sequences().items():
        best[after] = min(best.get(after, len(seq)), len(seq))
    return best


def min_strokes(text: str, table: dict[str, int]) -> int | None:
    """Fewest strokes to type `text` as a sequence of outputs, or None."""
    inf = float("inf")
    cost = [inf] * (len(text) + 1)
    cost[len(text)] = 0
    for i in range(len(text) - 1, -1, -1):
        for out, n in table.items():
            if text.startswith(out, i) and cost[i + len(out)] + n < cost[i]:
                cost[i] = cost[i + len(out)] + n
    return None if cost[0] == inf else int(cost[0])


def report(layout: Layout, groups: list[TargetGroup]) -> str:
    table = stroke_table(layout)
    lines = []
    for g in groups:
        misses = []
        for item in g.items:
            n = min_strokes(item, table)
            if n is None or n > g.max_strokes:
                misses.append(f"{item}:{'×' if n is None else n}")
        ok = len(g.items) - len(misses)
        head = f"{g.name}（{g.priority}、{g.max_strokes} 打以内）: {ok}/{len(g.items)}"
        lines.append(head + ("" if not misses else "  未達 " + " ".join(misses)))
    return "\n".join(lines)
