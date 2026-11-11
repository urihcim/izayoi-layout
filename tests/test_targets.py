from pathlib import Path

from izayoi.layout import load
from izayoi.targets import load_targets, min_strokes, report, stroke_table

ROOT = Path(__file__).parent.parent
FIXTURES = Path(__file__).parent / "fixtures"


def test_min_strokes_uses_postfix_shortcuts():
    # mini: か=j, ゃ=l, き=dj, ま=ka, か+ゃ→が, ま+ゃ→ぱ
    table = stroke_table(load(FIXTURES / "mini.toml"))
    assert table == {"か": 1, "ゃ": 1, "き": 2, "ま": 2, "が": 2, "ぱ": 3}
    assert min_strokes("きゃ", table) == 3
    assert min_strokes("がか", table) == 3
    assert min_strokes("ぬ", table) is None


def test_report_lists_misses():
    layout = load(FIXTURES / "mini.toml")
    groups = load_targets(ROOT / "config" / "targets.toml")
    text = report(layout, groups)
    assert "拗音（清音）（必須、2 打以内）: 0/21" in text
    assert "きゃ:3" in text


def test_targets_accept_katakana():
    groups = load_targets(ROOT / "config" / "targets.toml")
    foreign = next(g for g in groups if g.name == "外来音（清音・優先）")
    assert "ふぁ" in foreign.items and "ゔ" not in foreign.items
