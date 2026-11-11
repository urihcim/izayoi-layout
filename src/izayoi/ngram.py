"""Mora n-gram tables as an alternative corpus.

The tables are the "日本語n-gram 1000万字統計データ" published for the design of
ロゴス配列 (note, Wikipedia and Aozora Bunko, about 10 million characters).
https://sizu.me/ditto/posts/2n3nhwene9ae

Each row is a sequence of morae (the アクション column, e.g. "しゃ|し|ん"; the
common 拗音 and 外来音 count as one mora) and its count. Only the 1-gram and 2-gram tables are used:
every metric depends on single strokes and consecutive stroke pairs, and a
pair never reaches further back than the previous mora.
"""

from __future__ import annotations

import csv
import time
import urllib.request
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from . import romaji
from .evaluate import KeyStats, Spec, UnitStats, token_stats, tokenizer
from .keyboard import KEY_INDEX, N_KEYS

LOGOS_URLS = {
    "1gram.csv": "https://files.catbox.moe/t5vksz.csv",
    "2gram.csv": "https://files.catbox.moe/ilcidg.csv",
}


@dataclass
class Ngrams:
    unigram: dict[str, int]  # mora -> count
    bigram: dict[tuple[str, str], int]  # (mora, next mora) -> count


def is_ngram_dir(path: Path) -> bool:
    return path.is_dir() and all((path / name).is_file() for name in LOGOS_URLS)


def _fetch(url: str, tries: int = 4) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "izayoi-layout corpus builder"})
    for i in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=120) as res:
                return res.read()
        except OSError:
            if i == tries - 1:
                raise
            time.sleep(2**i)
    raise AssertionError("unreachable")


def fetch_logos(dest: Path) -> list[Path]:
    dest.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, url in LOGOS_URLS.items():
        (dest / name).write_bytes(_fetch(url))
        paths.append(dest / name)
    return paths


def _read(path: Path) -> list[tuple[list[str], int]]:
    with path.open(encoding="utf-8", newline="") as f:
        rows = csv.DictReader(f, delimiter="\t")
        return [(row["アクション"].split("|"), int(row["頻度"])) for row in rows]


def load_ngrams(path: str | Path) -> Ngrams:
    path = Path(path)
    unigram = {m[0]: c for m, c in _read(path / "1gram.csv")}
    bigram = {(m[0], m[1]): c for m, c in _read(path / "2gram.csv")}
    return Ngrams(unigram, bigram)


def ngram_unit_stats(ng: Ngrams, spec: Spec) -> UnitStats:
    """Like evaluate.segment(), with the tokens of each mora counted from the tables.

    A unit or composite spanning two morae (e.g. a word placed on one key) is not
    recognised; such morae are counted with the units that make them up.
    """
    pattern = tokenizer(spec)
    tokens = {m: pattern.findall(m) for m in ng.unigram}
    tok_uni: Counter = Counter()
    tok_bi: Counter = Counter()
    for m, c in ng.unigram.items():
        ts = tokens[m]
        for t in ts:
            tok_uni[t] += c
        for pair in zip(ts, ts[1:], strict=False):
            tok_bi[pair] += c
    for (a, b), c in ng.bigram.items():
        ta = tokens.get(a) or pattern.findall(a)
        tb = tokens.get(b) or pattern.findall(b)
        tok_bi[ta[-1], tb[0]] += c
    return token_stats(spec, tok_uni, tok_bi)


def ngram_romaji_stats(ng: Ngrams) -> KeyStats:
    """Romaji keystrokes; ん and っ are spelled according to the next mora.

    The first key of a mora that depends on its own next mora (っ before た is "t")
    is not known from a 2-gram, so the pair leading into it is shared out by how
    often each spelling of that mora occurs.
    """
    freq = np.zeros(N_KEYS)
    bigram = np.zeros((N_KEYS, N_KEYS))

    def keys(mora: str, nxt: str = "") -> list[int]:
        full = romaji.to_romaji(mora + nxt)[0]
        own = full[: len(full) - len(romaji.to_romaji(nxt)[0])] if nxt else full
        return [KEY_INDEX[k] for k in own if k in KEY_INDEX]

    def add(ids: list[int], c: int) -> None:
        for i in ids:
            freq[i] += c
        for a, b in zip(ids, ids[1:], strict=False):
            bigram[a, b] += c

    followed: Counter = Counter()
    first: dict[str, Counter] = {m: Counter() for m in ng.unigram}  # mora -> first key -> count
    for (a, b), c in ng.bigram.items():
        ia = keys(a, b)
        add(ia, c)
        if ia:
            first.setdefault(a, Counter())[ia[0]] += c
        followed[a] += c
    n_kana = 0
    for m, c in ng.unigram.items():
        n_kana += len(m) * c
        rest = max(c - followed[m], 0)  # the last mora of a run
        ids = keys(m)
        add(ids, rest)
        if ids and rest:
            first[m][ids[0]] += rest
    for (a, b), c in ng.bigram.items():
        ia, fb = keys(a, b), first.get(b)
        if not ia or not fb:
            continue
        total = sum(fb.values())
        for k, n in fb.items():
            bigram[ia[-1], k] += c * n / total
    return KeyStats("ローマ字(QWERTY)", freq, bigram, n_kana, 0)
