"""Segment the kana corpus into typed units and compute stroke statistics."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import romaji
from .keyboard import FINGER_NAMES, KEY_INDEX, KEY_INFO, N_KEYS, CostModel, classify_bigrams
from .layout import Layout, shadow

SEP = "\n"


@dataclass
class Spec:
    """What a layout can type, independent of where things are placed."""

    units: list[str]  # outputs placed directly on some key
    composites: dict[str, tuple[str, str]]  # postfix result -> (preceding unit, trigger unit)

    @classmethod
    def from_layout(cls, layout: Layout) -> Spec:
        placed = set(layout.sequences().values())
        kana = [k for k in layout.omit_units if k in placed]
        # Triggers outside the layout (digits) have no key cost; leave those results out.
        composites = {
            a: (b, t)
            for a, (b, t) in composites_from_postfix(layout.effective_postfix()[0]).items()
            if t in placed
        }
        composites.update(omission_composites(kana, layout.omit_triggers))
        befores = []
        for before, t in layout.omitted_postfix():
            composites[layout.postfix[t][before]] = (shadow(before), t)
            if before not in befores:
                befores.append(before)
        return cls(sorted(placed) + [shadow(k) for k in kana + befores], composites)


def omission_composites(kana: list[str], triggers: list[str]) -> dict[str, tuple[str, str]]:
    """きゃ etc. typed as the unit without its prefix, then the trigger."""
    return {k + t: (shadow(k), t) for k in kana for t in triggers}


def composites_from_postfix(postfix: dict[str, dict[str, str]]) -> dict[str, tuple[str, str]]:
    return {
        after: (before, trigger)
        for trigger, rules in postfix.items()
        for before, after in rules.items()
    }


@dataclass
class UnitStats:
    units: list[str]
    freq: np.ndarray  # (U,) occurrences of each unit as a stroke group
    bigram: np.ndarray  # (U, U) consecutive unit pairs
    n_kana: int  # kana characters that could be typed
    unsupported: Counter = field(default_factory=Counter)
    conflicts: dict[str, int] = field(default_factory=dict)  # "き+ゃ→ぎ" -> literal count


def tokenizer(spec: Spec) -> re.Pattern:
    """Longest match over the units and composites; any other character is a token by itself."""
    placed = set(spec.units)
    targets = sorted(placed | spec.composites.keys(), key=len, reverse=True)
    return (
        re.compile("|".join(map(re.escape, targets)) + r"|\n|.") if targets else re.compile(r"\n|.")
    )


def segment(corpus: str, spec: Spec) -> UnitStats:
    pattern = tokenizer(spec)
    tok_uni: Counter = Counter()
    tok_bi: Counter = Counter()
    for line in corpus.split(SEP):
        tokens = pattern.findall(line)
        tok_uni.update(tokens)
        tok_bi.update(zip(tokens, tokens[1:], strict=False))
    return token_stats(spec, tok_uni, tok_bi)


def token_stats(spec: Spec, tok_uni: Counter, tok_bi: Counter) -> UnitStats:
    """Unit statistics from token counts (tokens as produced by tokenizer())."""
    placed = set(spec.units)
    composites = {k: v for k, v in spec.composites.items() if k not in placed}

    def expand(t: str) -> tuple[str, ...]:
        if t in placed:
            return (t,)
        if t in composites:
            return composites[t]
        return ()

    index = {u: i for i, u in enumerate(spec.units)}
    n = len(spec.units)
    freq = np.zeros(n)
    bigram = np.zeros((n, n))
    unsupported: Counter = Counter()
    n_kana = 0
    for t, c in tok_uni.items():
        e = expand(t)
        if not e:
            unsupported[t] += c
            continue
        n_kana += len(t) * c
        for u in e:
            freq[index[u]] += c
        for a, b in zip(e, e[1:], strict=False):
            bigram[index[a], index[b]] += c
    for (a, b), c in tok_bi.items():
        ea, eb = expand(a), expand(b)
        if ea and eb:
            bigram[index[ea[-1]], index[eb[0]]] += c

    conflicts = {f"{b}+{t}→{a}": tok_bi.get((b, t), 0) for a, (b, t) in composites.items()}
    return UnitStats(spec.units, freq, bigram, n_kana, unsupported, conflicts)


@dataclass
class KeyStats:
    name: str
    freq: np.ndarray  # (N_KEYS,)
    bigram: np.ndarray  # (N_KEYS, N_KEYS)
    n_kana: int
    unsupported: int
    conflicts: dict[str, int] = field(default_factory=dict)
    prefix_strokes: float = 0.0


def unit_keys(layout: Layout, cost: CostModel) -> dict[str, tuple[int, ...]]:
    """Cheapest key sequence for every unit of the layout."""
    best: dict[str, tuple[int, ...]] = {}
    for seq, out in layout.sequences().items():
        keys = tuple(KEY_INDEX[k] for k in seq)
        if out not in best or cost.effort[list(keys)].sum() < cost.effort[list(best[out])].sum():
            best[out] = keys
    for kana in layout.omit_units + [b for b, _ in layout.omitted_postfix()]:
        if kana in best:
            best[shadow(kana)] = best[kana][-1:]
    return best


def layout_stats(name: str, layout: Layout, us: UnitStats, cost: CostModel) -> KeyStats:
    keys = unit_keys(layout, cost)
    freq = np.zeros(N_KEYS)
    bigram = np.zeros((N_KEYS, N_KEYS))
    prefix = 0.0
    for i, u in enumerate(us.units):
        ks = keys[u]
        for k in ks:
            freq[k] += us.freq[i]
        for a, b in zip(ks, ks[1:], strict=False):
            bigram[a, b] += us.freq[i]
        if len(ks) > 1:
            prefix += us.freq[i] * (len(ks) - 1)
    first = np.array([keys[u][0] for u in us.units], dtype=int)
    last = np.array([keys[u][-1] for u in us.units], dtype=int)
    np.add.at(bigram, (last[:, None], first[None, :]), us.bigram)
    return KeyStats(
        name, freq, bigram, us.n_kana, sum(us.unsupported.values()), us.conflicts, prefix
    )


def romaji_stats(corpus: str) -> KeyStats:
    lut = np.full(128, -1, dtype=int)
    for k, i in KEY_INDEX.items():
        lut[ord(k)] = i
    freq = np.zeros(N_KEYS)
    bigram = np.zeros((N_KEYS, N_KEYS))
    n_kana = unsupported = 0
    for line in corpus.split(SEP):
        keys, bad = romaji.to_romaji(line)
        n_kana += len(line) - bad
        unsupported += bad
        ids = lut[np.frombuffer(keys.encode("ascii"), dtype=np.uint8)]
        ok = ids >= 0
        np.add.at(freq, ids[ok], 1)
        pair = ok[:-1] & ok[1:]
        np.add.at(bigram, (ids[:-1][pair], ids[1:][pair]), 1)
    return KeyStats("ローマ字(QWERTY)", freq, bigram, n_kana, unsupported)


# --- metrics --------------------------------------------------------------


def metrics(ks: KeyStats, cost: CostModel) -> dict[str, float]:
    strokes = ks.freq.sum()
    pairs = ks.bigram.sum()
    masks = classify_bigrams()
    rows = np.array([k.row for k in KEY_INFO])
    hands = np.array([k.hand for k in KEY_INFO])
    total_cost = ks.freq @ cost.effort + (ks.bigram * cost.bigram).sum()
    m = {
        "打鍵/かな": strokes / ks.n_kana,
        "コスト/かな": total_cost / ks.n_kana,
        "前置シフト率%": 100 * ks.prefix_strokes / ks.n_kana,
        "ホーム段%": 100 * ks.freq[rows == 1].sum() / strokes,
        "上段%": 100 * ks.freq[rows == 0].sum() / strokes,
        "下段%": 100 * ks.freq[rows == 2].sum() / strokes,
        "左手%": 100 * ks.freq[hands == 0].sum() / strokes,
        "左右交互%": 100 * ks.bigram[masks["alternate"]].sum() / pairs,
        "同指連続%": 100 * ks.bigram[masks["sfb"]].sum() / pairs,
        "同キー連打%": 100 * ks.bigram[masks["same_key"]].sum() / pairs,
        "段越え%": 100 * ks.bigram[masks["scissor"]].sum() / pairs,
        "内ロール%": 100 * ks.bigram[masks["roll_in"]].sum() / pairs,
        "外ロール%": 100 * ks.bigram[masks["roll_out"]].sum() / pairs,
        "未対応文字%": 100 * ks.unsupported / max(ks.n_kana + ks.unsupported, 1),
        "後置衝突%": 100 * sum(ks.conflicts.values()) / ks.n_kana,
    }
    fingers = np.array([k.finger for k in KEY_INFO])
    for f, name in enumerate(FINGER_NAMES):
        m[f"{name}%"] = 100 * ks.freq[fingers == f].sum() / strokes
    return m


def _width(s: str) -> int:
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)


def _rjust(s: str, width: int) -> str:
    return " " * max(width - _width(s), 0) + s


def format_table(rows: list[tuple[str, dict[str, float]]]) -> str:
    label = 16
    width = max(12, *(_width(n) + 2 for n, _ in rows))
    out = [" " * label + "".join(_rjust(n, width) for n, _ in rows)]
    for k in rows[0][1]:
        cells = "".join(_rjust(f"{m[k]:.2f}", width) for _, m in rows)
        out.append(k + " " * (label - _width(k)) + cells)
    return "\n".join(out)


def load_corpus(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8")
