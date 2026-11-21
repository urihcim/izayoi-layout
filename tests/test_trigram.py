from collections import Counter
from pathlib import Path

import numpy as np
import pytest

from izayoi.evaluate import Spec
from izayoi.keyboard import KEY_INDEX, load_cost_model
from izayoi.layout import load
from izayoi.ngram import Ngrams
from izayoi.trigram import (
    classify,
    key_trigrams,
    layout_keys_of,
    load_trigram,
    romaji_keys_of,
    trigram_metrics,
)

FIXTURES = Path(__file__).parent / "fixtures"
COST = Path(__file__).parent.parent / "config" / "cost.toml"
HEADER = "順位\tかな\tアクション\t頻度\t割合\t累積割合\n"


def tables(lines: list[list[str]]) -> tuple[Ngrams, dict]:
    uni: Counter = Counter()
    bi: Counter = Counter()
    tri: Counter = Counter()
    for morae in lines:
        uni.update(morae)
        bi.update(zip(morae, morae[1:], strict=False))
        tri.update(zip(morae, morae[1:], morae[2:], strict=False))
    return Ngrams(dict(uni), dict(bi)), dict(tri)


def direct(lines: list[list[str]], keys_of) -> np.ndarray:
    n = len(KEY_INDEX)
    out = np.zeros((n, n, n))
    for morae in lines:
        ks: list[int] = []
        for m, nxt in zip(morae, morae[1:] + [None], strict=True):
            ks += keys_of(m, nxt)
        for a, b, c in zip(ks, ks[1:], ks[2:], strict=False):
            out[a, b, c] += 1
    return out


def test_load_trigram(tmp_path):
    (tmp_path / "3gram.csv").write_text(HEADER + "1\tている\tて|い|る\t5\t0%\t0%\n", "utf-8")
    assert load_trigram(tmp_path) == {("て", "い", "る"): 5}


def test_layout_trigrams_match_text():
    layout = load(FIXTURES / "mini.toml")
    keys_of = layout_keys_of(layout, Spec.from_layout(layout), load_cost_model(COST))
    # き is D+J (2 strokes), が is か+ゃ (postfix), ぱ is K+A then ゃ
    lines = [["か", "き", "が", "ぱ", "か"], ["き", "き", "か"], ["ぱ"]]
    ng, tri = tables(lines)
    assert (key_trigrams(ng, tri, keys_of) == direct(lines, keys_of)).all()


def test_unsupported_mora_breaks_runs():
    layout = load(FIXTURES / "mini.toml")
    keys_of = layout_keys_of(layout, Spec.from_layout(layout), load_cost_model(COST))
    assert keys_of("ぬ") is None
    ng, tri = tables([["か", "ぬ", "か", "か", "か"]])
    assert key_trigrams(ng, tri, keys_of).sum() == 1


@pytest.mark.parametrize(
    "morae", [list("かった"), list("しんぶん、きんえん。"), ["きゃ", "っ", "と", "ん"]]
)
def test_romaji_trigrams_match_text(morae):
    ng, tri = tables([morae])
    assert (key_trigrams(ng, tri, romaji_keys_of) == direct([morae], romaji_keys_of)).all()


def test_classify():
    k = KEY_INDEX
    assert classify(k["f"], k["j"], k["d"]) == "交互"
    assert classify(k["s"], k["f"], k["j"]) == "内ロール"
    assert classify(k["j"], k["f"], k["s"]) == "外ロール"
    assert classify(k["a"], k["s"], k["d"]) == "片手内ロール"
    assert classify(k["d"], k["s"], k["a"]) == "片手外ロール"
    assert classify(k["s"], k["f"], k["d"]) == "方向転換"
    assert classify(k["a"], k["d"], k["s"]) == "悪い方向転換"
    assert classify(k["f"], k["g"], k["j"]) == "同指を含む"
    assert classify(k["d"], k["d"], k["j"]) == "同指を含む"


def test_trigram_metrics_sum_to_100():
    tri = np.random.default_rng(0).random((len(KEY_INDEX),) * 3)
    m = trigram_metrics(tri)
    classes = [v for name, v in m.items() if "1打飛ばし" not in name]
    assert sum(classes) == pytest.approx(100)
