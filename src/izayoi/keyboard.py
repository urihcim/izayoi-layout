"""Physical key model and stroke cost matrices."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .layout import KEYS, ROWS

# Keys outside the layout grid. "-", "?" and "!" are used only by the romaji
# baseline; "?" and "!" stand for the shifted keys, with the shift chord
# folded into their effort. " " is the terminator after a solo prefix key.
# key -> (row, finger)
EXTRA_KEYS_INFO = {
    " ": (3, 8),
    "-": (-1, 7),
    "?": (2, 7),
    "!": (-1, 0),
}
EXTRA_KEYS = tuple(EXTRA_KEYS_INFO)
ALL_KEYS = KEYS + EXTRA_KEYS
KEY_INDEX = {k: i for i, k in enumerate(ALL_KEYS)}
N_KEYS = len(ALL_KEYS)

# Fingers numbered 0..7 from left pinky to right pinky.
COL_FINGER = (0, 1, 2, 3, 3, 4, 4, 5, 6, 7, 7, 7)
# Finger 8 is the thumb, which is treated as belonging to neither hand.
FINGER_NAMES = ("左小", "左薬", "左中", "左人", "右人", "右中", "右薬", "右小", "親指")


@dataclass(frozen=True)
class Key:
    row: int  # -1: number row, 0: top, 1: home, 2: bottom, 3: thumb
    finger: int
    col: int | None = None  # column in the layout grid (None outside it)

    @property
    def hand(self) -> int:
        """0: left, 1: right, 2: thumb."""
        return 0 if self.finger < 4 else 1 if self.finger < 8 else 2


def _keys() -> list[Key]:
    keys = [Key(r, COL_FINGER[c], c) for r, row in enumerate(ROWS) for c in range(len(row))]
    keys += [Key(row, finger) for row, finger in EXTRA_KEYS_INFO.values()]
    return keys


KEY_INFO = _keys()


@dataclass
class CostModel:
    effort: np.ndarray  # (N_KEYS,)
    bigram: np.ndarray  # (N_KEYS, N_KEYS)


def load_cost_model(path: str | Path) -> CostModel:
    with open(path, "rb") as f:
        cfg = tomllib.load(f)
    rows = cfg["effort"]
    effort = []
    for keys, row in zip(ROWS, rows, strict=True):
        values = [float(x) for x in row.split()]
        if len(values) != len(keys):
            raise ValueError(f"effort row {keys!r}: expected {len(keys)} values, got {len(values)}")
        effort += values
    extra = cfg["effort_extra"]
    effort += [float(extra["space" if k == " " else k]) for k in EXTRA_KEYS]
    # Fixed cost of every stroke, on top of the per-key effort.
    effort = np.array(effort) + float(cfg.get("stroke", 0.0))
    w = cfg["bigram"]
    # Row stagger: horizontal offset of each row (top, home, bottom) in key widths.
    stagger = cfg.get("stagger", {})
    offset = [float(x) for x in stagger.get("offset", [0.0, 0.0, 0.0])]
    cramp = float(stagger.get("cramp", 0.0))

    bigram = np.zeros((N_KEYS, N_KEYS))
    for i, a in enumerate(KEY_INFO):
        for j, b in enumerate(KEY_INFO):
            if a.hand != b.hand:
                continue
            rows = abs(a.row - b.row)
            if i == j:
                cost = w["same_key"]
            elif a.finger == b.finger:
                cost = w["sfb"] + w["sfb_per_row"] * rows
            elif rows >= 2:
                cost = w["scissor"]
            elif rows == 0:
                inward = (b.finger > a.finger) if a.hand == 0 else (b.finger < a.finger)
                cost = w["roll_in"] if inward else w["roll_out"]
            else:
                cost = w["same_hand"]
            if a.col is not None and b.col is not None and a.finger != b.finger and rows:
                # Neighbouring fingers on different rows end up closer than one key
                # apart when the stagger shifts the second key towards the first.
                dx = abs((b.col + offset[b.row]) - (a.col + offset[a.row]))
                cost += cramp * max(0.0, 1.0 - dx)
            bigram[i, j] = cost
    return CostModel(effort, bigram)


def classify_bigrams() -> dict[str, np.ndarray]:
    """Boolean masks over key bigrams, used for reporting."""
    n = N_KEYS
    masks = {
        name: np.zeros((n, n), dtype=bool)
        for name in ("alternate", "same_key", "sfb", "scissor", "roll_in", "roll_out")
    }
    for i, a in enumerate(KEY_INFO):
        for j, b in enumerate(KEY_INFO):
            if a.hand != b.hand:
                masks["alternate"][i, j] = True
            elif i == j:
                masks["same_key"][i, j] = True
            elif a.finger == b.finger:
                masks["sfb"][i, j] = True
            elif abs(a.row - b.row) >= 2:
                masks["scissor"][i, j] = True
            elif a.row == b.row:
                inward = (b.finger > a.finger) if a.hand == 0 else (b.finger < a.finger)
                masks["roll_in" if inward else "roll_out"][i, j] = True
    return masks
