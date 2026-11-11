import pytest

from izayoi.constraints import ConstraintError, Constraints, assign, select
from izayoi.evaluate import segment
from izayoi.keyboard import load_cost_model
from izayoi.layout import KEYS
from izayoi.optimize import Annealer, load_config

LAYERS = ["base", "d", "k"]
SLOTS = [(la, k) for la in LAYERS for k in KEYS if not (la == "base" and k in "dk")]


def test_select_intersects_categories():
    assert select("base home left !pinky", SLOTS, LAYERS) == {
        ("base", "s"),
        ("base", "f"),
        ("base", "g"),
    }
    assert select("k @jl", SLOTS, LAYERS) == {("k", "j"), ("k", "l")}
    assert select("d k index top", SLOTS, LAYERS) == {(la, k) for la in "dk" for k in "rtyu"}


def test_select_same_and_cross_hand_shift():
    same = select("same", SLOTS, LAYERS)
    cross = select("cross", SLOTS, LAYERS)
    assert ("d", "f") in same and ("k", "j") in same and ("d", "d") in same
    assert ("d", "j") in cross and ("k", "f") in cross
    assert not any(layer == "base" for layer, _ in same | cross)
    assert len(same) + len(cross) == 2 * len(KEYS)


def test_exclusive_area():
    c = Constraints.from_toml({"exclusive": [{"area": ["@[]"], "units": ["「"]}]})
    allowed = c.allowed(["「", "あ"], SLOTS, LAYERS)
    assert ("base", "[") in allowed["「"]
    assert not any(k in "[]" for _, k in allowed["あ"])


def test_select_unknown_selector():
    with pytest.raises(ConstraintError, match="unknown selector"):
        select("upper", SLOTS, LAYERS)


def test_allowed_combines_rules():
    c = Constraints.from_toml(
        {
            "reserved": ["base @t"],
            "pinned": {"あ": "base @j"},
            "area": [
                {"units": ["い"], "in": ["base home", "base top"]},
                {"units": ["い"], "not_in": ["left"]},
            ],
        }
    )
    allowed = c.allowed(["あ", "い", "う"], SLOTS, LAYERS)
    assert allowed["あ"] == {("base", "j")}
    assert allowed["い"] == {("base", k) for k in "hl;'yuiop[]"}
    assert ("base", "j") not in allowed["う"]
    assert ("base", "t") not in allowed["う"]


def test_pinned_must_match_one_slot():
    c = Constraints.from_toml({"pinned": {"あ": "base home"}})
    with pytest.raises(ConstraintError, match="matches"):
        c.allowed(["あ"], SLOTS, LAYERS)


def test_assign_detects_infeasible():
    with pytest.raises(ConstraintError):
        assign([[0], [0]], 2, [0, 1])
    assert assign([[0, 1], [0]], 2, [0, 1]) == [1, 0]


def test_annealer_respects_constraints(tmp_path):
    from pathlib import Path

    root = Path(__file__).parent.parent
    cfg = load_config(root / "config" / "optimize.toml")
    cfg.iterations, cfg.restarts = 3000, 1
    cfg.constraints = Constraints.from_toml(
        {
            "pinned": {"の": "base @a"},
            "reserved": ["base @j"],
            "area": [{"units": ["ゃ", "ぃ"], "in": ["k"]}],
        }
    )
    corpus = "かがくのしんぽはめざましい。きょうはびょういんへいった、ぱんをかう\n"
    annealer = Annealer(cfg, segment(corpus, cfg.spec), load_cost_model(root / "config/cost.toml"))
    pos, _ = annealer.run(log=lambda _: None)
    layout = annealer.to_layout(pos, "t")
    assert layout.layers["base"]["a"] == "の"
    assert "j" not in layout.layers["base"]
    for u in ("ゃ", "ぃ"):
        assert u in layout.layers["k"].values()


def test_free_moves_only_listed_and_violating_units():
    from pathlib import Path

    root = Path(__file__).parent.parent
    cfg = load_config(root / "config" / "optimize.toml")
    cfg.iterations, cfg.restarts = 2000, 1
    corpus = "かがくのしんぽはめざましい。きょうはびょういんへいった、ぱんをかう\n"
    us = segment(corpus, cfg.spec)
    cost = load_cost_model(root / "config/cost.toml")
    first = Annealer(cfg, us, cost)
    init = first.to_layout(first.run(log=lambda _: None)[0], "init")
    where = {o: (la, k) for la, g in init.layers.items() for k, o in g.items()}

    # Force "の" off its current key; keep everything else except ゃ fixed.
    cfg.constraints = Constraints.from_toml(
        {"area": [{"units": ["の"], "not_in": [f"{where['の'][0]} @{where['の'][1]}"]}]}
    )
    annealer = Annealer(cfg, us, cost, init, free={"ゃ"})
    layout = annealer.to_layout(annealer.run(log=lambda _: None)[0], "t")
    after = {o: (la, k) for la, g in layout.layers.items() for k, o in g.items()}
    moved = {u for u in after if after[u] != where[u]}
    assert "の" in moved
    assert moved <= {"の", "ゃ"}


def test_aligned_slot():
    from izayoi.constraints import aligned_slot

    layers = ["base", "d", "k", "solo"]
    assert aligned_slot(("base", "f"), layers) == ("d", "f")
    assert aligned_slot(("d", "j"), layers) == ("k", "j")
    assert aligned_slot(("k", "d"), layers) == ("d", "d")
    assert aligned_slot(("solo", "d"), layers) is None


def test_annealer_keeps_aligned_units_together():
    from pathlib import Path

    from izayoi.constraints import aligned_slot

    root = Path(__file__).parent.parent
    cfg = load_config(root / "config" / "optimize.toml")
    cfg.iterations, cfg.restarts = 5000, 1
    corpus = "かがくのしんぽはめざましい。きょうはびょういんへいった、ぱんをかう\n"
    annealer = Annealer(cfg, segment(corpus, cfg.spec), load_cost_model(root / "config/cost.toml"))
    layout = annealer.to_layout(annealer.run(log=lambda _: None)[0], "t")
    where = {o: (la, k) for la, g in layout.layers.items() for k, o in g.items()}
    for follower, leader in cfg.constraints.aligned.items():
        assert where[follower] == aligned_slot(where[leader], cfg.layers), follower
    assert set(layout.layers["solo"].values()) == {"、", "。"}
    assert layout.sequences()[where["、"][1] + " "] == "、"
    assert cfg.constraints.violations(where, cfg.slots, cfg.layers) == []
