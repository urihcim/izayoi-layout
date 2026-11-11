from pathlib import Path

import pytest

from izayoi import ahk, chart
from izayoi.layout import LayoutError, dump, load, parse

FIXTURES = Path(__file__).parent / "fixtures"
ROOT = Path(__file__).parent.parent


def test_sequences():
    layout = load(FIXTURES / "mini.toml")
    assert layout.sequences() == {"j": "か", "l": "ゃ", "dj": "き", "ka": "ま"}


def test_postfix_sequences():
    layout = load(FIXTURES / "mini.toml")
    assert layout.postfix_sequences() == {"jl": ("か", "が"), "kal": ("ま", "ぱ")}


def test_project_layout_is_valid():
    load(ROOT / "layout" / "izayoi.toml")


def _grid(cells=None):
    rows = [["_"] * n for n in (12, 11, 10)]
    for (r, c), v in (cells or {}).items():
        rows[r][c] = v
    return {"rows": [" ".join(row) for row in rows]}


def test_prefix_key_must_be_empty_on_base():
    data = {
        "prefix": {"keys": ["d"]},
        "layers": {"base": _grid({(1, 2): "あ"}), "d": _grid()},
    }
    with pytest.raises(LayoutError, match="prefix key"):
        parse(data)


def test_unknown_postfix_trigger():
    data = {"layers": {"base": _grid()}, "postfix": [{"trigger": "ゃ", "rules": {"か": "が"}}]}
    with pytest.raises(LayoutError, match="trigger"):
        parse(data)


def test_wrong_token_count():
    data = {"layers": {"base": {"rows": ["_", "_", "_"]}}}
    with pytest.raises(LayoutError, match="tokens"):
        parse(data)


def test_generate_ahk():
    script = ahk.generate(load(FIXTURES / "mini.toml"))
    assert "#HotIf izayoiCondition()\n#HotString *?CX\n" in script
    # the including script may set izayoiCondition before or after the #Include
    assert "if !IsSet(izayoiCondition)\n    izayoiCondition := izayoiKanaInput\n" in script
    assert "izayoiKanaInput()\n{" in script
    assert "return (mode & 0x01) != 0" in script
    # every used key, prefix keys included, is a single-key hotstring
    assert '::j::izayoiKey("j")' in script
    assert '::d::izayoiKey("d")' in script
    assert "::q::" not in script
    assert '    "d", Map(\n            "j", "き"\n        ),' in script
    assert '    "ゃ", Map(\n            "か", "が",\n            "ま", "ぱ"\n        )' in script
    # Space and Enter keep their own meaning (start conversion, commit)
    assert "Space::" not in script


def test_solo_layer():
    data = {
        "prefix": {"keys": ["d"], "solo": {"d": "、"}},
        "layers": {"base": _grid(), "d": _grid()},
    }
    layout = parse(data)
    assert layout.sequences() == {"d ": "、"}
    script = ahk.generate(layout)
    assert '"d", "、"' in script
    assert "Space::" not in script
    data["prefix"]["solo"] = {"k": "。"}
    with pytest.raises(LayoutError, match="not a prefix key"):
        parse(data)


def test_shift_omission():
    data = {
        "prefix": {"keys": ["d"]},
        "layers": {
            "base": _grid({(1, 9): "ま", (2, 0): "ゃ", (1, 0): "し", (1, 1): "て"}),
            # D+; = に (base ; = ま), D+a = き (base a = し: cannot omit), D+s = ち
            "d": _grid({(1, 9): "に", (1, 0): "き", (1, 1): "ち"}),
        },
        "postfix": [{"trigger": "ゃ", "rules": {"て": "てぃ"}}],
        "shift_omission": {"units": ["き", "し", "ち", "に"], "triggers": ["ゃ"]},
    }
    layout = parse(data)
    rules, problems = layout.omission_rules()
    assert rules == {"ゃ": {"ま": "にゃ", "て": "ちゃ"}}
    assert problems == ["き（d+a）はシフトを省略して拗音を打てない"]
    merged, overridden = layout.effective_postfix()
    assert merged["ゃ"]["て"] == "ちゃ" and overridden == ["て+ゃ→てぃ"]
    assert layout.postfix_sequences()[";z"] == ("ま", "にゃ")


def test_postfix_omission():
    data = {
        "prefix": {"keys": ["d", "k"]},
        "layers": {
            # base: ; = れ, a = て, s = き, l = ふ, z = ゃ, x = ょ
            "base": _grid(
                {(1, 9): "れ", (1, 0): "て", (1, 1): "き", (1, 8): "ふ", (2, 0): "ゃ", (2, 1): "ょ"}
            ),
            # D+; = く, K+; = ぐ (both claim れ), D+a = せ (て has its own rule),
            # D+s = つ (base き is a shift-omission unit)
            "d": _grid({(1, 9): "く", (1, 0): "せ", (1, 1): "つ"}),
            "k": _grid({(1, 9): "ぐ"}),
        },
        "postfix": [
            {"trigger": "ゃ", "rules": {"く": "くぁ", "ぐ": "ぐぁ", "て": "てぃ", "せ": "すぃ"}},
            {"trigger": "ゃ", "rules": {"つ": "つぁ", "ふ": "ふぁ"}},
            {"trigger": "ょ", "rules": {"ぐ": "ぐぉ"}},
        ],
        "shift_omission": {"units": ["き"], "triggers": ["ゃ", "ょ"], "postfix": True},
    }
    layout = parse(data)
    assert layout.omitted_postfix() == [("く", "ゃ"), ("ぐ", "ょ")]
    assert layout.unomitted_postfix() == ["ぐ+ゃ→ぐぁ", "せ+ゃ→すぃ", "つ+ゃ→つぁ"]
    seqs = layout.postfix_sequences()
    assert seqs[";z"] == ("れ", "くぁ") and seqs[";x"] == ("れ", "ぐぉ")
    assert seqs["d;z"] == ("く", "くぁ") and seqs["k;z"] == ("ぐ", "ぐぁ")
    assert seqs["az"] == ("て", "てぃ")
    assert "\npostfix = true\n" in dump(layout)
    data["shift_omission"]["postfix"] = False
    assert parse(data).omitted_postfix() == []


def test_postfix_omission_overrides_overridable_rule():
    data = {
        "prefix": {"keys": ["d"]},
        "layers": {
            # D+; = ふ over base ; = い, which has its own rule い+ゃ→ゐ
            "base": _grid({(1, 9): "い", (2, 0): "ゃ"}),
            "d": _grid({(1, 9): "ふ"}),
        },
        "postfix": [{"trigger": "ゃ", "rules": {"ふ": "ふぁ", "い": "ゐ"}}],
        "shift_omission": {"units": [], "triggers": ["ゃ"], "postfix": True},
    }
    assert parse(data).unomitted_postfix() == ["ふ+ゃ→ふぁ"]
    data["shift_omission"]["overridable"] = ["ゐ"]
    layout = parse(data)
    assert layout.omitted_postfix() == [("ふ", "ゃ")]
    assert layout.postfix_sequences()[";z"] == ("い", "ふぁ")
    assert layout.effective_postfix()[1] == ["い+ゃ→ゐ"]
    assert '\noverridable = ["ゐ"]\n' in dump(layout)


def test_symbol_postfix_is_not_omitted():
    data = {
        "prefix": {"keys": ["d"]},
        "layers": {
            # D+; = ○ over base ; = そ: そ+ゃ stays そゃ
            "base": _grid({(1, 9): "そ", (2, 0): "ゃ"}),
            "d": _grid({(1, 9): "○"}),
        },
        "postfix": [{"trigger": "ゃ", "rules": {"○": "●"}}],
        "shift_omission": {"units": [], "triggers": ["ゃ"], "postfix": True},
    }
    layout = parse(data)
    assert layout.omitted_postfix() == []
    assert layout.postfix_sequences() == {"d;z": ("○", "●")}


def test_raw_trigger():
    data = {
        "prefix": {"keys": ["d"]},
        "layers": {"base": _grid(), "d": _grid({(0, 9): "○"})},
        "postfix": [
            {"trigger": "1", "rules": {"○": "①"}},
            {"trigger": "2", "rules": {"○": "②"}},
        ],
    }
    layout = parse(data)
    assert layout.postfix_sequences() == {"dp1": ("○", "①"), "dp2": ("○", "②")}
    script = ahk.generate(layout)
    # digits are taken only right after an output with a rule for them
    assert '#HotIf izayoiCondition() and izayoiRawReady("1")\n1::izayoiKey("1")\n' in script
    assert "izayoiRawReady(key)\n{" in script
    assert '"1", "1",' in script
    assert "::1::" not in script
    data["postfix"] = [{"trigger": "a", "rules": {"○": "①"}}]
    with pytest.raises(LayoutError, match="trigger"):
        parse(data)


def test_committed_ahk_is_up_to_date():
    root = FIXTURES.parent.parent
    committed = (root / "dist/izayoi.ahk").read_text(encoding="utf-8-sig")
    expected = ahk.generate(load(root / "layout/izayoi.toml"))
    assert committed.replace("\r\n", "\n") == expected, "uv run izayoi ahk layout/izayoi.toml"


def test_readme_chart_is_up_to_date():
    root = FIXTURES.parent.parent
    readme = (root / "README.md").read_text(encoding="utf-8")
    rendered = chart.render(load(root / "layout/izayoi.toml"))
    assert chart.update(readme, rendered) == readme, (
        "uv run izayoi chart layout/izayoi.toml -o README.md"
    )


def test_chart_update_replaces_between_markers():
    text = f"before\n{chart.CHART_BEGIN}\nold\n{chart.CHART_END}\nafter\n"
    assert chart.update(text, "new") == (
        f"before\n{chart.CHART_BEGIN}\n\nnew\n\n{chart.CHART_END}\nafter\n"
    )
    with pytest.raises(ValueError, match="markers"):
        chart.update("no markers", "new")
