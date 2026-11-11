"""Render the layout as Markdown tables for the README.

The tables are written between the CHART_BEGIN and CHART_END markers so that
they can be regenerated from the layout definition (`izayoi chart`).
"""

from __future__ import annotations

from .layout import ROWS, SOLO, Layout, is_kana

CHART_BEGIN = "<!-- chart:begin (uv run izayoi chart layout/izayoi.toml -o README.md) -->"
CHART_END = "<!-- chart:end -->"

# "[" and "]" are left to the IME.
_ROWS = tuple(row.rstrip("[]") for row in ROWS)
_ROW_NAMES = ("上段", "中段", "下段")
_WIDTH = max(len(row) for row in _ROWS)


def _key_label(key: str) -> str:
    return key.upper()


def _layer_table(layout: Layout, layer: str) -> list[str]:
    grid = layout.layers[layer]
    lines = [
        "| |" + " |" * _WIDTH,
        "| --- |" + " :---: |" * _WIDTH,
    ]
    for name, keys in zip(_ROW_NAMES, _ROWS, strict=True):
        cells = []
        for key in keys:
            if layer == "base" and key in layout.prefix_keys:
                text = "前置"
            else:
                text = grid.get(key, "")
            cells.append(f"{text}<br><sub>{_key_label(key)}</sub>")
        cells += [""] * (_WIDTH - len(keys))
        lines.append(f"| {name} | " + " | ".join(cells) + " |")
    return lines


def _postfix_table(layout: Layout, preceding: list[str]) -> list[str]:
    triggers = list(layout.postfix)
    lines = [
        "| 直前の文字 | " + " | ".join(f"＋{t}" for t in triggers) + " |",
        "| :---: |" + " :---: |" * len(triggers),
    ]
    for before in preceding:
        cells = [layout.postfix[t].get(before, "") for t in triggers]
        lines.append(f"| {before} | " + " | ".join(cells) + " |")
    return lines


def render(layout: Layout) -> str:
    """Markdown for the three layers and the postfix rules."""
    out: list[str] = []
    titles = {"base": "通常面"} | {k: f"{_key_label(k)} 面" for k in layout.prefix_keys}
    for layer in ["base", *layout.prefix_keys]:
        out += [f"#### {titles[layer]}", "", *_layer_table(layout, layer), ""]

    solo = layout.layers.get(SOLO, {})
    if solo:
        items = " ／ ".join(
            f"`{_key_label(k)}` → {solo[k]}" for k in layout.prefix_keys if k in solo
        )
        out += [f"単独打鍵（前置シフトのキー＋スペース・Enter など）: {items}", ""]

    preceding: list[str] = []
    for rules in layout.postfix.values():
        preceding += [b for b in rules if b not in preceding]
    kana = [b for b in preceding if all(is_kana(r.get(b, "あ")) for r in layout.postfix.values())]
    symbols = [b for b in preceding if b not in kana]
    out += ["#### 後置シフト（外来音・古語）", "", *_postfix_table(layout, kana), ""]
    out += ["#### 後置シフト（記号）", "", *_postfix_table(layout, symbols)]
    return "\n".join(out)


def update(text: str, chart: str) -> str:
    """Replace the part of `text` between the markers with `chart`."""
    try:
        head, rest = text.split(CHART_BEGIN, 1)
        _, tail = rest.split(CHART_END, 1)
    except ValueError:
        raise ValueError(f"markers not found: {CHART_BEGIN!r} ... {CHART_END!r}") from None
    return f"{head}{CHART_BEGIN}\n\n{chart}\n\n{CHART_END}{tail}"
