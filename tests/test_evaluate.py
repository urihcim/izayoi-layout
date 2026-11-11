from pathlib import Path

import numpy as np

from izayoi.evaluate import Spec, layout_stats, metrics, romaji_stats, segment
from izayoi.keyboard import KEY_INDEX, load_cost_model
from izayoi.layout import load
from izayoi.optimize import Annealer, load_config
from izayoi.romaji import to_romaji

FIXTURES = Path(__file__).parent / "fixtures"
ROOT = Path(__file__).parent.parent
COST = load_cost_model(ROOT / "config" / "cost.toml")


def test_romaji():
    assert to_romaji("きゃっと、しんぶんー")[0] == "kyatto,sinbunn-"
    assert to_romaji("きんえん")[0] == "kinnenn"
    assert to_romaji("あ☆い") == ("a\ni", 1)


def test_stroke_cost_is_added_to_every_key(tmp_path):
    src = (ROOT / "config" / "cost.toml").read_text(encoding="utf-8")
    path = tmp_path / "cost.toml"
    path.write_text(src.replace("stroke = 0.5", "stroke = 0.0"), encoding="utf-8")
    flat = load_cost_model(path)
    assert np.allclose(COST.effort, flat.effort + 0.5)
    assert np.array_equal(COST.bigram, flat.bigram)


def test_segment_expands_postfix():
    layout = load(FIXTURES / "mini.toml")
    # mini: か=j, ゃ=l, き=dj, ま=ka, か+ゃ→が, ま+ゃ→ぱ
    us = segment("がき\nかゃ\nぬ", Spec.from_layout(layout))
    idx = {u: i for i, u in enumerate(us.units)}
    assert us.freq[idx["か"]] == 2
    assert us.freq[idx["ゃ"]] == 2
    assert us.bigram[idx["か"], idx["ゃ"]] == 2  # inside が, and the literal かゃ
    assert us.bigram[idx["ゃ"], idx["き"]] == 1
    assert us.n_kana == 4
    assert us.unsupported["ぬ"] == 1
    assert us.conflicts == {"か+ゃ→が": 1, "ま+ゃ→ぱ": 0}


def test_layout_stats_counts_prefix_strokes():
    layout = load(FIXTURES / "mini.toml")
    us = segment("きか", Spec.from_layout(layout))
    ks = layout_stats("mini", layout, us, COST)
    d, j = KEY_INDEX["d"], KEY_INDEX["j"]
    assert ks.freq[d] == 1 and ks.freq[j] == 2
    assert ks.bigram[d, j] == 1 and ks.bigram[j, j] == 1
    assert metrics(ks, COST)["打鍵/かな"] == 1.5


def test_romaji_stats():
    ks = romaji_stats("かき")
    assert ks.n_kana == 2
    assert ks.freq.sum() == 4
    assert ks.bigram[KEY_INDEX["a"], KEY_INDEX["k"]] == 1


def test_annealer_cost_matches_evaluation():
    cfg = load_config(ROOT / "config" / "optimize.toml")
    cfg.iterations, cfg.restarts = 2000, 1
    corpus = "かがくのしんぽはめざましい。きょうはびょういんへいった、ぱんをかう\n"
    us = segment(corpus, cfg.spec)
    annealer = Annealer(cfg, us, COST)
    pos, best = annealer.run(log=lambda _: None)
    layout = annealer.to_layout(pos, "t")
    m = metrics(layout_stats("t", layout, segment(corpus, Spec.from_layout(layout)), COST), COST)
    assert np.isclose(m["コスト/かな"], best)


def test_shift_omission_shadow_units():
    from izayoi.layout import parse

    def grid(cells):
        rows = [["_"] * n for n in (12, 11, 10)]
        for (r, c), v in cells.items():
            rows[r][c] = v
        return {"rows": [" ".join(row) for row in rows]}

    layout = parse(
        {
            "prefix": {"keys": ["d"]},
            "layers": {"base": grid({(1, 9): "ま", (2, 0): "ゃ"}), "d": grid({(1, 9): "に"})},
            "shift_omission": {"units": ["に"], "triggers": ["ゃ"]},
        }
    )
    spec = Spec.from_layout(layout)
    assert "に*" in spec.units and spec.composites["にゃ"] == ("に*", "ゃ")
    us = segment("にゃに", spec)
    ks = layout_stats("t", layout, us, COST)
    # に* is typed as ; alone, に as d ;
    assert ks.freq.sum() == 4
    assert ks.bigram[KEY_INDEX[";"], KEY_INDEX["z"]] == 1


def test_annealer_avoids_omission_violations():
    cfg = load_config(ROOT / "config" / "optimize.toml")
    cfg.iterations, cfg.restarts = 20000, 1
    corpus = "きゃくのしんぽはめざましい。きょうはびょういんへいった、ぱんをかう\n"
    us = segment(corpus, cfg.spec)
    annealer = Annealer(cfg, us, COST)
    pos, best = annealer.run(log=lambda _: None)
    assert annealer.omission_violations(pos) == 0
    layout = annealer.to_layout(pos, "t")
    assert layout.omission_rules()[1] == []
    assert layout.effective_postfix()[1] == []  # no postfix rule overridden by an omission
    m = metrics(layout_stats("t", layout, segment(corpus, Spec.from_layout(layout)), COST), COST)
    assert np.isclose(m["コスト/かな"], best)


def test_postfix_omission_shadow_units():
    from izayoi.layout import parse

    def grid(cells):
        rows = [["_"] * n for n in (12, 11, 10)]
        for (r, c), v in cells.items():
            rows[r][c] = v
        return {"rows": [" ".join(row) for row in rows]}

    layout = parse(
        {
            "prefix": {"keys": ["d"]},
            "layers": {"base": grid({(1, 9): "れ", (2, 0): "ゃ"}), "d": grid({(1, 9): "ふ"})},
            "postfix": [{"trigger": "ゃ", "rules": {"ふ": "ふぁ"}}],
            "shift_omission": {"units": [], "triggers": ["ゃ"], "postfix": True},
        }
    )
    spec = Spec.from_layout(layout)
    assert "ふ*" in spec.units and spec.composites["ふぁ"] == ("ふ*", "ゃ")
    ks = layout_stats("t", layout, segment("ふぁふ", spec), COST)
    # ふぁ is typed as ; z, ふ as d ;
    assert ks.freq.sum() == 4
    assert ks.bigram[KEY_INDEX[";"], KEY_INDEX["z"]] == 1


def test_annealer_postfix_omission_matches_layout():
    import random

    cfg = load_config(ROOT / "config" / "optimize.toml")
    assert cfg.omit_postfix
    corpus = "ふぁいる、てぃー。うぉーく、くぉーく、ぐぁむ、ふぉーく\n"
    annealer = Annealer(cfg, segment(corpus, cfg.spec), COST)
    pairs = [u.split("*") for u in cfg.spec.units if "*" in u and not u.endswith("*")]
    rng = random.Random(0)
    seen = 0
    for _ in range(30):
        pos = annealer._initial(rng)
        ok = annealer.pair_omitted(pos, annealer._occupant(pos))
        layout = annealer.to_layout(pos, "t")
        on_prefix = {b for b, _ in pairs if layout._prefix_slot(b) is not None}
        expected = set(layout.omitted_postfix())
        assert {
            (b, t) for (b, t), o in zip(pairs, ok, strict=True) if o and b in on_prefix
        } == expected
        seen += len(expected)
    assert seen > 0


def test_annealer_counts_preferred_postfix_without_omission():
    import dataclasses
    import random

    cfg = load_config(ROOT / "config" / "optimize.toml")
    assert "ふぁ" in cfg.omit_preferred
    us = segment("ふぁいる、ふぃーるど\n", cfg.spec)
    plain = Annealer(dataclasses.replace(cfg, omit_preferred=[]), us, COST)
    annealer = Annealer(cfg, us, COST)
    rng = random.Random(1)
    seen = 0
    for _ in range(30):
        pos = plain._initial(rng)
        layout = annealer.to_layout(pos, "t")
        missed = sum(after in cfg.omit_preferred for after in _unomitted_results(layout))
        assert annealer.omission_violations(pos) - plain.omission_violations(pos) == missed
        seen += missed
    assert seen > 0


def _unomitted_results(layout):
    return [rule.split("→")[1] for rule in layout.unomitted_postfix()]


def test_stagger_cramp_penalizes_neighbouring_fingers(tmp_path):
    src = (ROOT / "config" / "cost.toml").read_text(encoding="utf-8")
    path = tmp_path / "cost.toml"
    path.write_text(src.replace("cramp = 2.0", "cramp = 0.0"), encoding="utf-8")
    flat = load_cost_model(path)
    i = KEY_INDEX

    def extra(a, b):
        return COST.bigram[i[a], i[b]] - flat.bigram[i[a], i[b]]

    assert np.isclose(extra("d", "x"), 1.0)  # X sits half a key towards D
    assert np.isclose(extra("d", "r"), 0.5)  # R sits a quarter key towards D
    assert np.isclose(extra("d", "w"), 0.0)  # W moves away from D
    assert np.isclose(extra("f", "f"), 0.0)
    assert np.isclose(extra("d", "j"), 0.0)
