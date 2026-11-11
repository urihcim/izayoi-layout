from pathlib import Path

import pytest

from izayoi.evaluate import Spec, metrics, romaji_stats, segment
from izayoi.keyboard import KEY_INDEX
from izayoi.layout import load
from izayoi.ngram import Ngrams, is_ngram_dir, load_ngrams, ngram_romaji_stats, ngram_unit_stats

FIXTURES = Path(__file__).parent / "fixtures"
HEADER = "順位\tかな\tアクション\t頻度\t割合\t累積割合\n"


def write_tables(dest: Path, unigram: dict[str, int], bigram: dict[tuple[str, str], int]) -> None:
    rows = [f"{i}\t{m}\t{m}\t{c}\t0%\t0%\n" for i, (m, c) in enumerate(unigram.items(), 1)]
    (dest / "1gram.csv").write_text(HEADER + "".join(rows), encoding="utf-8")
    rows = [
        f"{i}\t{a}{b}\t{a}|{b}\t{c}\t0%\t0%\n" for i, ((a, b), c) in enumerate(bigram.items(), 1)
    ]
    (dest / "2gram.csv").write_text(HEADER + "".join(rows), encoding="utf-8")


def test_load_ngrams(tmp_path):
    write_tables(tmp_path, {"きゃ": 3, "く": 2}, {("きゃ", "く"): 1})
    assert is_ngram_dir(tmp_path)
    assert not is_ngram_dir(tmp_path / "missing")
    ng = load_ngrams(tmp_path)
    assert ng.unigram == {"きゃ": 3, "く": 2}
    assert ng.bigram == {("きゃ", "く"): 1}


def test_ngram_unit_stats_matches_segment():
    layout = load(FIXTURES / "mini.toml")
    spec = Spec.from_layout(layout)
    # the text "がき\nかゃ\nぬ" as morae
    ng = Ngrams(
        {"が": 1, "き": 1, "か": 1, "ゃ": 1, "ぬ": 1},
        {("が", "き"): 1, ("か", "ゃ"): 1},
    )
    a, b = ngram_unit_stats(ng, spec), segment("がき\nかゃ\nぬ", spec)
    assert (a.freq == b.freq).all()
    assert (a.bigram == b.bigram).all()
    assert a.n_kana == b.n_kana
    assert a.unsupported == b.unsupported
    assert a.conflicts == b.conflicts


def test_ngram_unit_stats_splits_unplaced_mora():
    layout = load(FIXTURES / "mini.toml")
    # mini has no きゃ: the mora is typed as き + ゃ
    us = ngram_unit_stats(Ngrams({"きゃ": 2}, {}), Spec.from_layout(layout))
    idx = {u: i for i, u in enumerate(us.units)}
    assert us.freq[idx["き"]] == 2 and us.freq[idx["ゃ"]] == 2
    assert us.bigram[idx["き"], idx["ゃ"]] == 2
    assert us.n_kana == 4


@pytest.mark.parametrize("text", ["かった", "しんぶん、きんえん。"])
def test_ngram_romaji_matches_text(text):
    morae = list(text)
    ng = Ngrams({}, {})
    for m in morae:
        ng.unigram[m] = ng.unigram.get(m, 0) + 1
    for pair in zip(morae, morae[1:], strict=False):
        ng.bigram[pair] = ng.bigram.get(pair, 0) + 1
    a, b = ngram_romaji_stats(ng), romaji_stats(text)
    assert (a.freq == b.freq).all()
    assert (a.bigram == b.bigram).all()
    assert a.n_kana == b.n_kana
    assert a.freq[KEY_INDEX["t"]] == text.count("た") + text.count("っ")


def test_ngram_metrics_run():
    layout = load(FIXTURES / "mini.toml")
    from izayoi.evaluate import layout_stats
    from izayoi.keyboard import load_cost_model

    cost = load_cost_model(Path(__file__).parent.parent / "config" / "cost.toml")
    us = ngram_unit_stats(Ngrams({"き": 1, "か": 1}, {("き", "か"): 1}), Spec.from_layout(layout))
    assert metrics(layout_stats("mini", layout, us, cost), cost)["打鍵/かな"] == 1.5
