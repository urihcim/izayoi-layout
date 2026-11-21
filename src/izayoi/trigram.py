"""Three-stroke statistics from the mora 3-gram table.

Each run of three consecutive keystrokes is counted once, in the n-gram whose
first mora holds its first stroke and whose last mora holds its last stroke:
runs inside one mora come from the 1-gram table, runs that end in the next mora
from the 2-gram table, and runs that reach two morae ahead (the middle mora is
a single stroke) from the 3-gram table. A run that touches a mora the layout
cannot type is not counted.
"""

from __future__ import annotations

import csv
from collections.abc import Callable
from pathlib import Path

import numpy as np

from . import romaji
from .evaluate import SEP, Spec, tokenizer, unit_keys
from .keyboard import KEY_INDEX, KEY_INFO, N_KEYS, CostModel
from .layout import Layout
from .ngram import Ngrams

TRIGRAM_FILE = "3gram.csv"

# keys of a mora, given the mora that follows (None: unknown or end of a run)
KeysOf = Callable[[str, str | None], tuple[int, ...] | None]


def has_trigram(path: Path) -> bool:
    return (path / TRIGRAM_FILE).is_file()


def load_trigram(path: str | Path) -> dict[tuple[str, str, str], int]:
    with (Path(path) / TRIGRAM_FILE).open(encoding="utf-8", newline="") as f:
        rows = csv.DictReader(f, delimiter="\t")
        out = {}
        for row in rows:
            a, b, c = row["アクション"].split("|")
            out[a, b, c] = int(row["頻度"])
        return out


def layout_keys_of(layout: Layout, spec: Spec, cost: CostModel) -> KeysOf:
    """Strokes of each mora on the layout (same segmentation as evaluate.segment)."""
    pattern = tokenizer(spec)
    placed = set(spec.units)
    composites = {k: v for k, v in spec.composites.items() if k not in placed}
    keys = unit_keys(layout, cost)
    cache: dict[str, tuple[int, ...] | None] = {}

    def keys_of(mora: str, _next: str | None = None) -> tuple[int, ...] | None:
        if mora not in cache:
            out: list[int] = []
            for t in pattern.findall(mora):
                units = (t,) if t in placed else composites.get(t)
                if not units:
                    cache[mora] = None
                    break
                for u in units:
                    out += keys[u]
            else:
                cache[mora] = tuple(out)
        return cache[mora]

    return keys_of


def romaji_keys_of(mora: str, nxt: str | None = None) -> tuple[int, ...] | None:
    """Romaji strokes; ん and っ are spelled for the next mora when it is known."""
    full, bad = romaji.to_romaji(mora + (nxt or ""))
    if bad:
        full, bad = romaji.to_romaji(mora)
        nxt = None
        if bad:
            return None
    own = full[: len(full) - len(romaji.to_romaji(nxt)[0])] if nxt else full
    ids = tuple(KEY_INDEX[k] for k in own if k in KEY_INDEX)
    return ids or None


def count_runs(
    ng: Ngrams, trigram: dict[tuple[str, str, str], int], seq_of: KeysOf
) -> dict[tuple[int, int, int], float]:
    """Counts of runs of three consecutive items (keystrokes or units).

    `seq_of` gives the items of a mora (None if it cannot be typed)."""
    out: dict[tuple[int, int, int], float] = {}

    def add(run: tuple[int, int, int], c: float) -> None:
        out[run] = out.get(run, 0) + c

    def inside(ks: tuple[int, ...] | None, c: float) -> None:
        if ks and len(ks) >= 3:
            for run in zip(ks, ks[1:], ks[2:], strict=False):
                add(run, c)

    # Runs inside a mora: spelled for the next mora when there is one (romaji っ ん).
    followed: dict[str, int] = {}
    for (m1, m2), c in ng.bigram.items():
        inside(seq_of(m1, m2), c)
        followed[m1] = followed.get(m1, 0) + c
    for m, c in ng.unigram.items():
        inside(seq_of(m, None), max(c - followed.get(m, 0), 0))
    # Runs from m1 into m2. The strokes of m2 depend on the mora after it (romaji
    # っ ん), taken from the 3-gram table; the rest is spelled without it.
    after: dict[tuple[str, str], list[tuple[str, int]]] = {}
    for (m1, m2, m3), c in trigram.items():
        after.setdefault((m1, m2), []).append((m3, c))
    for (m1, m2), c in ng.bigram.items():
        k1 = seq_of(m1, m2)
        if not k1:
            continue
        nexts = after.get((m1, m2), [])
        rest = max(c - sum(n for _, n in nexts), 0)
        for m3, n in [*nexts, (None, rest)]:
            k2 = seq_of(m2, m3)
            if not k2 or not n:
                continue
            # first item in m1, last item in m2
            if len(k1) >= 2:
                add((k1[-2], k1[-1], k2[0]), n)
            if len(k2) >= 2:
                add((k1[-1], k2[0], k2[1]), n)
    for (m1, m2, m3), c in trigram.items():
        k2 = seq_of(m2, m3)
        if not k2 or len(k2) != 1:
            continue
        k1, k3 = seq_of(m1, m2), seq_of(m3, None)
        if k1 and k3:
            add((k1[-1], k2[0], k3[0]), c)
    return out


def key_trigrams(
    ng: Ngrams, trigram: dict[tuple[str, str, str], int], keys_of: KeysOf
) -> np.ndarray:
    """(N_KEYS, N_KEYS, N_KEYS) counts of consecutive keystroke triples."""
    out = np.zeros((N_KEYS, N_KEYS, N_KEYS))
    for (a, b, c), n in count_runs(ng, trigram, keys_of).items():
        out[a, b, c] += n
    return out


def unit_trigrams(
    ng: Ngrams, trigram: dict[tuple[str, str, str], int], spec: Spec
) -> tuple[np.ndarray, np.ndarray]:
    """Runs of three consecutive units (indices into spec.units) and their counts.

    Uses the same segmentation as ngram.ngram_unit_stats(), for the optimizer."""
    pattern = tokenizer(spec)
    placed = set(spec.units)
    composites = {k: v for k, v in spec.composites.items() if k not in placed}
    index = {u: i for i, u in enumerate(spec.units)}
    cache: dict[str, tuple[int, ...] | None] = {}

    def units_of(mora: str, _next: str | None = None) -> tuple[int, ...] | None:
        if mora not in cache:
            out: list[int] = []
            for t in pattern.findall(mora):
                units = (t,) if t in placed else composites.get(t)
                if not units:
                    cache[mora] = None
                    break
                out += [index[u] for u in units]
            else:
                cache[mora] = tuple(out)
        return cache[mora]

    runs = count_runs(ng, trigram, units_of)
    idx = np.array(list(runs), dtype=int).reshape(-1, 3)
    return idx, np.array(list(runs.values()), dtype=float)


def text_runs(corpus: str, spec: Spec, seq_of_unit) -> dict[tuple[int, int, int], float]:
    """Runs of three items in a kana corpus; seq_of_unit maps a unit to its items.

    Lines and characters that cannot be typed break the runs."""
    pattern = tokenizer(spec)
    placed = set(spec.units)
    composites = {k: v for k, v in spec.composites.items() if k not in placed}
    out: dict[tuple[int, int, int], float] = {}
    for line in corpus.split(SEP):
        seq: list[int] = []
        for t in [*pattern.findall(line), None]:
            units = None if t is None else (t,) if t in placed else composites.get(t)
            if units:
                for u in units:
                    seq += seq_of_unit(u)
                continue
            for run in zip(seq, seq[1:], seq[2:], strict=False):
                out[run] = out.get(run, 0) + 1
            seq = []
    return out


def text_key_trigrams(corpus: str, layout: Layout, spec: Spec, cost: CostModel) -> np.ndarray:
    keys = unit_keys(layout, cost)
    out = np.zeros((N_KEYS,) * 3)
    for (a, b, c), n in text_runs(corpus, spec, lambda u: keys[u]).items():
        out[a, b, c] += n
    return out


def text_unit_trigrams(corpus: str, spec: Spec) -> tuple[np.ndarray, np.ndarray]:
    index = {u: i for i, u in enumerate(spec.units)}
    runs = text_runs(corpus, spec, lambda u: (index[u],))
    idx = np.array(list(runs), dtype=int).reshape(-1, 3)
    return idx, np.array(list(runs.values()), dtype=float)


def romaji_text_trigrams(corpus: str) -> np.ndarray:
    out = np.zeros((N_KEYS,) * 3)
    for line in corpus.split(SEP):
        keys, _ = romaji.to_romaji(line)
        ids = [KEY_INDEX.get(k, -1) for k in keys]
        for a, b, c in zip(ids, ids[1:], ids[2:], strict=False):
            if min(a, b, c) >= 0:
                out[a, b, c] += 1
    return out


# --- classification ---------------------------------------------------------

TRIGRAM_CLASSES = (
    "交互",  # L R L / R L R
    "内ロール",  # two strokes on one hand (different fingers, inward), one on the other
    "外ロール",
    "片手内ロール",  # three fingers of one hand in one direction
    "片手外ロール",
    "方向転換",  # three fingers of one hand, direction changes, with the index finger
    "悪い方向転換",  # the same without the index finger
    "同指を含む",  # consecutive strokes on the same finger (including the same key)
    "親指を含む",
)


def _inward(hand: int, f1: int, f2: int) -> bool:
    return f2 > f1 if hand == 0 else f2 < f1


def classify(a: int, b: int, c: int) -> str:
    ka, kb, kc = KEY_INFO[a], KEY_INFO[b], KEY_INFO[c]
    ha, hb, hc = ka.hand, kb.hand, kc.hand
    if 2 in (ha, hb, hc):
        return "親指を含む"
    if (ha == hb and ka.finger == kb.finger) or (hb == hc and kb.finger == kc.finger):
        return "同指を含む"
    if ha != hb and hb != hc:
        return "交互"
    if ha == hb != hc:
        return "内ロール" if _inward(ha, ka.finger, kb.finger) else "外ロール"
    if ha != hb == hc:
        return "内ロール" if _inward(hb, kb.finger, kc.finger) else "外ロール"
    first = _inward(ha, ka.finger, kb.finger)
    second = _inward(ha, kb.finger, kc.finger)
    if first == second:
        return "片手内ロール" if first else "片手外ロール"
    index = 3 if ha == 0 else 4
    return "方向転換" if index in (ka.finger, kb.finger, kc.finger) else "悪い方向転換"


def class_masks() -> dict[str, np.ndarray]:
    masks = {name: np.zeros((N_KEYS,) * 3, dtype=bool) for name in TRIGRAM_CLASSES}
    for a in range(N_KEYS):
        for b in range(N_KEYS):
            for c in range(N_KEYS):
                masks[classify(a, b, c)][a, b, c] = True
    return masks


def skip_masks() -> tuple[np.ndarray, np.ndarray]:
    """1st and 3rd strokes on the same finger (different keys / same key), 2nd elsewhere."""
    n = N_KEYS
    sfs = np.zeros((n,) * 3, dtype=bool)
    same = np.zeros((n,) * 3, dtype=bool)
    for a, ka in enumerate(KEY_INFO):
        for c, kc in enumerate(KEY_INFO):
            if ka.hand == 2 or ka.finger != kc.finger:
                continue
            for b, kb in enumerate(KEY_INFO):
                if kb.finger == ka.finger:
                    continue
                (same if a == c else sfs)[a, b, c] = True
    return sfs, same


def trigram_metrics(tri: np.ndarray) -> dict[str, float]:
    total = tri.sum()
    masks = class_masks()
    m = {f"3:{name}%": 100 * tri[mask].sum() / total for name, mask in masks.items()}
    sfs, same = skip_masks()
    m["3:1打飛ばし同指%"] = 100 * tri[sfs].sum() / total
    m["3:1打飛ばし同キー%"] = 100 * tri[same].sum() / total
    return m


def trigram_report(tri: np.ndarray, label: str, mask: np.ndarray, top: int = 10) -> str:
    """The most frequent key triples in a class, as QWERTY keys."""
    names = [k if k != " " else "␣" for k in KEY_INDEX]
    counts = np.where(mask, tri, 0)
    order = np.argsort(counts, axis=None)[::-1][:top]
    total = tri.sum()
    items = []
    for flat in order:
        a, b, c = np.unravel_index(flat, counts.shape)
        if counts[a, b, c] == 0:
            break
        items.append(f"{names[a]}{names[b]}{names[c]}:{100 * counts[a, b, c] / total:.2f}")
    return f"{label}: " + " ".join(items)


# cost.toml [trigram] key -> class
TRIGRAM_WEIGHTS = {
    "redirect": "方向転換",
    "bad_redirect": "悪い方向転換",
    "alternate": "交互",
    "roll_in": "内ロール",
    "roll_out": "外ロール",
    "onehand_in": "片手内ロール",
    "onehand_out": "片手外ロール",
}


def trigram_cost(weights: dict[str, float]) -> np.ndarray | None:
    """(N_KEYS,)*3 cost of each keystroke triple, or None if every weight is 0."""
    unknown = set(weights) - set(TRIGRAM_WEIGHTS) - {"skip_same_finger"}
    if unknown:
        raise ValueError(f"[trigram] に知らない項目がある: {sorted(unknown)}")
    if not any(weights.values()):
        return None
    out = np.zeros((N_KEYS,) * 3)
    masks = class_masks()
    for key, cls in TRIGRAM_WEIGHTS.items():
        out[masks[cls]] += float(weights.get(key, 0.0))
    sfs, _ = skip_masks()
    out[sfs] += float(weights.get("skip_same_finger", 0.0))
    return out
