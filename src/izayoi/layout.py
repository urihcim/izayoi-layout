"""Load and validate layout definition files."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

# US (ANSI) positions. 31 basic keys plus "[" and "]".
ROWS = (
    "qwertyuiop[]",
    "asdfghjkl;'",
    "zxcvbnm,./",
)
KEYS = tuple(k for row in ROWS for k in row)
EMPTY = "_"

# Keys outside the layout that may still be postfix triggers (○ then 1 → ①).
# They type themselves and are taken over only right after a matching output.
RAW_TRIGGERS = tuple("1234567890")

# A prefix key pressed on its own and followed by a key outside the layout
# (space, Enter, ...) produces the output of the "solo" layer. The
# terminator is modelled as a space.
SOLO = "solo"
TERMINATOR = " "

Slot = tuple[str, str]  # (layer, key)

# Shift omission: a unit (e.g. に) placed on a prefix layer can be typed without
# the prefix right before one of the triggers (ゃ ゅ ょ): if D+; is に and ; is ま,
# then ; ゃ types にゃ.
# For evaluation such a stroke is a separate "shadow" unit named "に*".
# With postfix omission enabled, the same applies to the preceding output of a
# postfix rule with one of the triggers: if D+; is ふ and ; is れ, ; ゃ types ふぁ.
SHADOW = "*"


def shadow(unit: str) -> str:
    return unit + SHADOW


def is_kana(s: str) -> bool:
    """Hiragana only. Postfix rules of symbols are not typed with the prefix omitted."""
    return bool(s) and all("\u3041" <= c <= "\u309f" for c in s)


def layer_names(prefix_keys: list[str], solo: bool) -> list[str]:
    return ["base", *prefix_keys] + ([SOLO] if solo else [])


def make_slots(prefix_keys: list[str], solo: bool) -> list[Slot]:
    """Every (layer, key) position a unit can be placed on."""
    slots = [("base", k) for k in KEYS if k not in prefix_keys]
    slots += [(p, k) for p in prefix_keys for k in KEYS]
    if solo:
        slots += [(SOLO, p) for p in prefix_keys]
    return slots


class LayoutError(ValueError):
    pass


@dataclass
class Layout:
    name: str
    version: str
    prefix_keys: list[str]
    # layer name ("base", a prefix key or "solo") -> {physical key: output}
    layers: dict[str, dict[str, str]]
    # trigger output -> {preceding output: replacement}
    postfix: dict[str, dict[str, str]] = field(default_factory=dict)
    # units whose prefix may be omitted right before one of the triggers
    omit_units: list[str] = field(default_factory=list)
    omit_triggers: list[str] = field(default_factory=list)
    # also omit the prefix of the preceding output of postfix rules with the triggers
    omit_postfix: bool = False
    # replacements of explicit postfix rules that give way to postfix omission
    # (e.g. ゐ: if ふ+ゃ→ふぁ can be typed as い+ゃ, い+ゃ→ゐ is dropped)
    omit_overridable: list[str] = field(default_factory=list)

    def _prefix_slot(self, out: str) -> tuple[str, str] | None:
        """(prefix, key) of an output placed on a prefix layer but not on the base layer."""
        if out in self.layers["base"].values():
            return None
        for p in self.prefix_keys:
            for k, o in self.layers[p].items():
                if o == out:
                    return p, k
        return None

    def _omissions(
        self,
    ) -> tuple[dict[str, dict[str, str]], list[str], list[tuple[str, str]], list[str]]:
        """Rules derived from shift omission, placements of omit_units that cannot use it,
        postfix rules typed with the prefix omitted ((preceding output, trigger)), and
        postfix rules whose prefix cannot be omitted.

        The omit_units come first, then the postfix rules in the order written; a base
        output that already has an explicit rule (or an earlier omission) is not reused.
        """
        rules: dict[str, dict[str, str]] = {t: {} for t in self.omit_triggers}
        problems = []
        base = self.layers["base"]
        for kana in self.omit_units:
            if (where := self._prefix_slot(kana)) is None:
                continue
            p, k = where
            before = base.get(k)
            if before is None or before in self.omit_units:
                problems.append(f"{kana}（{p}+{k}）はシフトを省略して拗音を打てない")
                continue
            for t in self.omit_triggers:
                rules[t][before] = kana + t
        omitted, skipped = [], []
        if not self.omit_postfix:
            return rules, problems, omitted, skipped
        for t in self.omit_triggers:
            for before, after in self.postfix.get(t, {}).items():
                if (
                    not is_kana(before)
                    or before in self.omit_units
                    or (where := self._prefix_slot(before)) is None
                ):
                    continue
                b = base.get(where[1])
                own = self.postfix.get(t, {}).get(b)
                if (
                    b is None
                    or b in self.omit_units
                    or (own is not None and own not in self.omit_overridable)
                    or b in rules[t]
                ):
                    skipped.append(f"{before}+{t}→{after}")
                    continue
                rules[t][b] = after
                omitted.append((before, t))
        return rules, problems, omitted, skipped

    def omission_rules(self) -> tuple[dict[str, dict[str, str]], list[str]]:
        """Postfix rules derived from shift omission, and placements that cannot use it."""
        rules, problems, _, _ = self._omissions()
        return rules, problems

    def omitted_postfix(self) -> list[tuple[str, str]]:
        """(preceding output, trigger) of the postfix rules typed with the prefix omitted."""
        return self._omissions()[2]

    def unomitted_postfix(self) -> list[str]:
        """Postfix rules on a prefix layer whose prefix cannot be omitted ("ふ+ゃ→ふぁ")."""
        return self._omissions()[3]

    def effective_postfix(self) -> tuple[dict[str, dict[str, str]], list[str]]:
        """Explicit postfix rules merged with the rules derived from shift omission.

        Derived rules win; the explicit rules they replace are returned as well.
        """
        merged = {t: dict(r) for t, r in self.postfix.items()}
        overridden = []
        derived, _ = self.omission_rules()
        for t, rules in derived.items():
            for before, after in rules.items():
                old = merged.setdefault(t, {}).get(before)
                if old is not None and old != after:
                    overridden.append(f"{before}+{t}→{old}")
                merged[t][before] = after
        return merged, overridden

    def sequences(self) -> dict[str, str]:
        """Return {key sequence: output} for every single (non-postfix) stroke."""
        seqs: dict[str, str] = {}
        for key, out in self.layers["base"].items():
            seqs[key] = out
        for prefix in self.prefix_keys:
            for key, out in self.layers[prefix].items():
                seqs[prefix + key] = out
        for key, out in self.layers.get(SOLO, {}).items():
            seqs[key + TERMINATOR] = out
        return seqs

    def postfix_sequences(self) -> dict[str, tuple[str, str]]:
        """Return {key sequence: (preceding output, replacement)} for postfix rules.

        Every way of typing the preceding output is combined with every way of
        typing the trigger.
        """
        by_output: dict[str, list[str]] = {}
        for seq, out in self.sequences().items():
            by_output.setdefault(out, []).append(seq)
        result: dict[str, tuple[str, str]] = {}
        for trigger, rules in self.effective_postfix()[0].items():
            for before, after in rules.items():
                for s1 in by_output[before]:
                    for s2 in by_output.get(trigger, [trigger] if trigger in RAW_TRIGGERS else []):
                        result[s1 + s2] = (before, after)
        return result


def _parse_grid(name: str, rows: list[str]) -> dict[str, str]:
    if len(rows) != len(ROWS):
        raise LayoutError(f"layers.{name}: expected {len(ROWS)} rows, got {len(rows)}")
    grid: dict[str, str] = {}
    for i, (keys, row) in enumerate(zip(ROWS, rows, strict=True)):
        tokens = row.split()
        if len(tokens) != len(keys):
            raise LayoutError(
                f"layers.{name} row {i + 1}: expected {len(keys)} tokens, got {len(tokens)}"
            )
        for key, token in zip(keys, tokens, strict=True):
            if token != EMPTY:
                grid[key] = token
    return grid


def parse(data: dict) -> Layout:
    meta = data.get("meta", {})
    prefix_keys = list(data.get("prefix", {}).get("keys", []))
    for key in prefix_keys:
        if key not in KEYS:
            raise LayoutError(f"prefix key {key!r} is not a supported key")

    raw_layers = data.get("layers", {})
    expected = {"base", *prefix_keys}
    if missing := expected - raw_layers.keys():
        raise LayoutError(f"missing layers: {sorted(missing)}")
    if extra := raw_layers.keys() - expected:
        raise LayoutError(f"layers without a matching prefix key: {sorted(extra)}")
    layers = {name: _parse_grid(name, raw_layers[name]["rows"]) for name in sorted(expected)}

    for key in prefix_keys:
        if key in layers["base"]:
            raise LayoutError(f"prefix key {key!r} must be {EMPTY!r} on the base layer")

    solo = dict(data.get("prefix", {}).get("solo", {}))
    for key in solo:
        if key not in prefix_keys:
            raise LayoutError(f"prefix.solo: {key!r} is not a prefix key")
    if solo:
        layers[SOLO] = solo

    layout = Layout(
        name=meta.get("name", ""),
        version=meta.get("version", ""),
        prefix_keys=prefix_keys,
        layers=layers,
        postfix=parse_postfix(data.get("postfix", [])),
        omit_units=list(data.get("shift_omission", {}).get("units", [])),
        omit_triggers=list(data.get("shift_omission", {}).get("triggers", [])),
        omit_postfix=bool(data.get("shift_omission", {}).get("postfix", False)),
        omit_overridable=list(data.get("shift_omission", {}).get("overridable", [])),
    )
    _check_postfix(layout)
    return layout


def parse_postfix(raw: list[dict]) -> dict[str, dict[str, str]]:
    """[[postfix]] tables ({trigger, rules}) -> {trigger: {preceding: replacement}}."""
    result: dict[str, dict[str, str]] = {}
    for table in raw:
        if "trigger" not in table or "rules" not in table:
            raise LayoutError(f"postfix needs trigger and rules: {table}")
        result.setdefault(table["trigger"], {}).update(table["rules"])
    return result


def _check_postfix(layout: Layout) -> None:
    outputs = set(layout.sequences().values())
    for trigger, rules in layout.postfix.items():
        if trigger not in outputs and trigger not in RAW_TRIGGERS:
            raise LayoutError(f"postfix trigger {trigger!r} is not on any layer")
        for before in rules:
            if before not in outputs:
                raise LayoutError(f"postfix.{trigger}: {before!r} is not on any layer")


def load(path: str | Path) -> Layout:
    with open(path, "rb") as f:
        return parse(tomllib.load(f))


def _toml_str(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def dump(layout: Layout, header: str = "") -> str:
    """Serialize a layout in the same format as layout/izayoi.toml."""
    out = [header] if header else []
    out += ["[meta]", f"name = {_toml_str(layout.name)}", f"version = {_toml_str(layout.version)}"]
    out += ["", "[prefix]", "keys = [" + ", ".join(map(_toml_str, layout.prefix_keys)) + "]"]
    if solo := layout.layers.get(SOLO):
        items = ", ".join(f"{_toml_str(k)} = {_toml_str(v)}" for k, v in solo.items())
        out.append(f"solo = {{ {items} }}")
    for name in ["base", *layout.prefix_keys]:
        grid = layout.layers[name]
        out += ["", f"[layers.{name}]", "rows = ["]
        for row in ROWS:
            out.append("  " + _toml_str(" ".join(grid.get(k, EMPTY) for k in row)) + ",")
        out.append("]")
    if layout.omit_units or layout.omit_triggers:
        out += ["", "[shift_omission]"]
        out.append("units = [" + ", ".join(map(_toml_str, layout.omit_units)) + "]")
        out.append("triggers = [" + ", ".join(map(_toml_str, layout.omit_triggers)) + "]")
        if layout.omit_postfix:
            out.append("postfix = true")
        if layout.omit_overridable:
            out.append("overridable = [" + ", ".join(map(_toml_str, layout.omit_overridable)) + "]")
    for trigger, rules in layout.postfix.items():
        out += ["", "[[postfix]]", f"trigger = {_toml_str(trigger)}", "[postfix.rules]"]
        out += [f"{_toml_str(b)} = {_toml_str(a)}" for b, a in rules.items()]
    return "\n".join(out) + "\n"
