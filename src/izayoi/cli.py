"""Command line interface."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import ahk, chart
from .constraints import ConstraintError
from .layout import SOLO, LayoutError, load

DEFAULT_CORPUS = Path("corpus/kana.txt")
DEFAULT_COST = Path("config/cost.toml")


def _cmd_check(args) -> None:
    layout = load(args.layout)
    print(f"ok: {len(layout.sequences())} strokes, {len(layout.postfix_sequences())} postfix")


def _cmd_ahk(args) -> None:
    layout = load(args.layout)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # AutoHotkey v2 reads UTF-8 with BOM reliably; CRLF for Windows editors.
    args.output.write_text(ahk.generate(layout), encoding="utf-8-sig", newline="\r\n")
    print(f"wrote {args.output}")


def _cmd_chart(args) -> None:
    rendered = chart.render(load(args.layout))
    if args.output is None:
        print(rendered)
        return
    text = args.output.read_text(encoding="utf-8")
    args.output.write_text(chart.update(text, rendered), encoding="utf-8")
    print(f"updated {args.output}")


def _cmd_corpus_fetch(args) -> None:
    from .corpus import fetch_aozora

    paths = fetch_aozora(args.dest, args.count, args.seed, args.delay)
    print(f"{len(paths)} works in {args.dest}")


def _cmd_corpus_fetch_ngram(args) -> None:
    from .ngram import fetch_logos

    paths = fetch_logos(args.dest)
    print(f"wrote {', '.join(str(p) for p in paths)}")


def _load_source(path: Path):
    """A kana corpus file, or a directory of n-gram tables."""
    from .evaluate import load_corpus
    from .ngram import is_ngram_dir, load_ngrams

    if is_ngram_dir(path):
        return load_ngrams(path)
    if path.is_dir():
        raise ValueError(
            f"{path} に 1gram.csv と 2gram.csv がない（corpus-fetch-ngram で取得する）"
        )
    return load_corpus(path)


def _unit_stats(source, spec):
    from .evaluate import segment
    from .ngram import Ngrams, ngram_unit_stats

    return ngram_unit_stats(source, spec) if isinstance(source, Ngrams) else segment(source, spec)


def _romaji_stats(source):
    from .evaluate import romaji_stats
    from .ngram import Ngrams, ngram_romaji_stats

    return ngram_romaji_stats(source) if isinstance(source, Ngrams) else romaji_stats(source)


def _cmd_corpus_build(args) -> None:
    from .corpus import build

    raw_dirs = [d for d in sorted(args.raw.iterdir()) if d.is_dir()]
    out = build(raw_dirs, args.output)
    n_chars = len(out.read_text(encoding="utf-8").replace("\n", ""))
    print(f"wrote {out}: {n_chars:,} chars from {[d.name for d in raw_dirs]}")


def _cmd_eval(args) -> None:
    from .evaluate import Spec, format_table, layout_stats, metrics
    from .keyboard import load_cost_model

    source = _load_source(args.corpus)
    cost = load_cost_model(args.cost)
    # Keystroke triples: for the three-stroke metrics and the [trigram] cost.
    need_tri = args.trigram or cost.trigram is not None
    rows, tris = [], []
    if args.romaji:
        tri = _romaji_trigrams(source, args.corpus) if need_tri else None
        rows.append(("ローマ字", metrics(_romaji_stats(source), cost, tri)))
        tris.append(("ローマ字", tri))
    details = []
    for path in args.layouts:
        layout = load(path)
        us = _unit_stats(source, Spec.from_layout(layout))
        tri = _key_trigrams(source, args.corpus, layout, cost) if need_tri else None
        rows.append((path.stem, metrics(layout_stats(path.stem, layout, us, cost), cost, tri)))
        tris.append((path.stem, tri))
        details.append((path.stem, us))
    print(format_table(rows))
    if args.trigram:
        _print_trigrams(args, tris)
    if args.config:
        from .optimize import load_config

        cfg = load_config(args.config)
        for path in args.layouts:
            problems = _violations(load(path), cfg)
            print(
                f"\n[{path.stem}] 制約違反: " + ("なし" if not problems else " / ".join(problems))
            )
    if args.targets:
        from .targets import load_targets, report

        groups = load_targets(args.targets)
        for path in args.layouts:
            print(f"\n[{path.stem}] 打鍵数の目標\n" + report(load(path), groups))
    if args.detail:
        for name, us in details:
            print(
                f"\n[{name}] 未対応文字（上位）: "
                + " ".join(f"{t!r}:{c}" for t, c in us.unsupported.most_common(10))
            )
            layout = load(next(p for p in args.layouts if p.stem == name))
            overridden = layout.effective_postfix()[1]
            if unomitted := layout.unomitted_postfix():
                print(f"[{name}] シフトを省略できない後置シフト: " + " ".join(unomitted))
            if overridden:
                print(
                    f"[{name}] 拗音の規則と重なって無効になった後置シフト: " + " ".join(overridden)
                )
            conflicts = sorted(us.conflicts.items(), key=lambda kv: -kv[1])
            print(
                f"[{name}] 後置シフトの衝突（その並びを直接打てなくなる回数）: "
                + " ".join(f"{r}:{c}" for r, c in conflicts if c)
            )


def _trigram_dir(path: Path) -> Path:
    from .trigram import has_trigram

    if not has_trigram(path):
        raise ValueError(
            f"{path} に 3gram.csv がない（corpus-fetch-ngram で取得する）。"
            "3 打鍵の評価と cost.toml の [trigram] に必要"
        )
    return path


def _key_trigrams(source, corpus: Path, layout, cost):
    """Keystroke triples of the layout, from the n-gram tables or the kana corpus."""
    from .evaluate import Spec
    from .ngram import Ngrams
    from .trigram import key_trigrams, layout_keys_of, load_trigram, text_key_trigrams

    spec = Spec.from_layout(layout)
    if isinstance(source, Ngrams):
        trigram = _TRIGRAM_CACHE.get(corpus)
        if trigram is None:
            trigram = _TRIGRAM_CACHE[corpus] = load_trigram(_trigram_dir(corpus))
        return key_trigrams(source, trigram, layout_keys_of(layout, spec, cost))
    return text_key_trigrams(source, layout, spec, cost)


_TRIGRAM_CACHE: dict = {}


def _romaji_trigrams(source, corpus: Path):
    from .ngram import Ngrams
    from .trigram import key_trigrams, load_trigram, romaji_keys_of, romaji_text_trigrams

    if isinstance(source, Ngrams):
        trigram = _TRIGRAM_CACHE.get(corpus)
        if trigram is None:
            trigram = _TRIGRAM_CACHE[corpus] = load_trigram(_trigram_dir(corpus))
        return key_trigrams(source, trigram, romaji_keys_of)
    return romaji_text_trigrams(source)


def _print_trigrams(args, tris) -> None:
    from .evaluate import format_table
    from .trigram import class_masks, skip_masks, trigram_metrics, trigram_report

    rows = [(name, trigram_metrics(tri)) for name, tri in tris]
    print("\n3 打鍵の連なり\n" + format_table(rows))
    if args.detail:
        masks = class_masks()
        sfs, _ = skip_masks()
        for name, tri in tris:
            if name == "ローマ字":
                continue
            for c in ("悪い方向転換", "同指を含む"):
                print(f"[{name}] " + trigram_report(tri, c, masks[c]))
            print(f"[{name}] " + trigram_report(tri, "1打飛ばし同指", sfs))


def _violations(layout, cfg) -> list[str]:
    if layout.prefix_keys != cfg.prefix_keys:
        return [f"前置シフトキーが設定と違う: {layout.prefix_keys}"]
    # An output on several keys (。 on D alone and on D+C) is checked where the
    # D/K alone layer has it, then in the order of the layers.
    placement = {}
    layers = sorted(layout.layers.items(), key=lambda item: item[0] != SOLO)
    for layer, grid in layers:
        for k, out in grid.items():
            placement.setdefault(out, (layer, k))
    problems = [f"{u} が置かれていない" for u in cfg.units if u not in placement]
    placed = {u: s for u, s in placement.items() if u in cfg.units}
    problems += layout.omission_rules()[1]
    return problems + cfg.constraints.violations(placed, cfg.slots, cfg.layers)


def _cmd_optimize(args) -> None:
    from .keyboard import load_cost_model
    from .layout import dump
    from .optimize import Annealer, load_config

    cfg = load_config(args.config)
    if args.iterations:
        cfg.iterations = args.iterations
    if args.restarts:
        cfg.restarts = args.restarts
    if args.seed is not None:
        cfg.seed = args.seed
    from .ngram import Ngrams

    source = _load_source(args.corpus)
    us = _unit_stats(source, cfg.spec)
    init = load(args.init) if args.init else None
    free = set(args.free) if args.free is not None else None
    if free is not None and init is None:
        raise ValueError("--free は --init と一緒に指定してください")
    cost = load_cost_model(args.cost)
    trigrams = None
    if cost.trigram is not None:
        from .trigram import load_trigram, text_unit_trigrams, unit_trigrams

        if isinstance(source, Ngrams):
            trigrams = unit_trigrams(source, load_trigram(_trigram_dir(args.corpus)), cfg.spec)
        else:
            trigrams = text_unit_trigrams(source, cfg.spec)
    annealer = Annealer(cfg, us, cost, init, free, trigrams)
    pos, best = annealer.run()
    layout = annealer.to_layout(pos, args.output.stem)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    origin = f", init={args.init}" if args.init else ""
    if isinstance(source, Ngrams):
        origin += f", n-gram 表 {args.corpus.name}" + (" 3-gram 込み" if trigrams else "")
    header = f"# {args.config} から生成（seed={cfg.seed}{origin}, cost/kana={best:.4f}）\n"
    args.output.write_text(dump(layout, header), encoding="utf-8")
    print(f"wrote {args.output}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="izayoi", description="十六夜配列ジェネレーター")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("check", help="配列定義を検証する")
    p.add_argument("layout", type=Path)
    p.set_defaults(func=_cmd_check)

    p = sub.add_parser("ahk", help="AutoHotkey スクリプトを生成する")
    p.add_argument("layout", type=Path)
    p.add_argument("-o", "--output", type=Path, default=Path("dist/izayoi.ahk"))
    p.set_defaults(func=_cmd_ahk)

    p = sub.add_parser("chart", help="配列表を Markdown で出力する")
    p.add_argument("layout", type=Path)
    p.add_argument("-o", "--output", type=Path, help="この Markdown ファイルの配列表を書き換える")
    p.set_defaults(func=_cmd_chart)

    p = sub.add_parser("corpus-fetch", help="青空文庫から作品を取得する")
    p.add_argument("--dest", type=Path, default=Path("corpus/raw/aozora"))
    p.add_argument("--count", type=int, default=150)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--delay", type=float, default=1.0, help="作品ごとの待ち時間（秒）")
    p.set_defaults(func=_cmd_corpus_fetch)

    p = sub.add_parser("corpus-fetch-ngram", help="ロゴス配列用のモーラ n-gram 表を取得する")
    p.add_argument("--dest", type=Path, default=Path("corpus/ngram/logos"))
    p.set_defaults(func=_cmd_corpus_fetch_ngram)

    p = sub.add_parser("corpus-build", help="corpus/raw/*/ の文章をかなコーパスに変換する")
    p.add_argument("--raw", type=Path, default=Path("corpus/raw"))
    p.add_argument("-o", "--output", type=Path, default=DEFAULT_CORPUS)
    p.set_defaults(func=_cmd_corpus_build)

    p = sub.add_parser("eval", help="配列を評価する")
    p.add_argument("layouts", type=Path, nargs="*")
    p.add_argument("--romaji", action="store_true", help="ローマ字入力も並べて比較する")
    p.add_argument("--detail", action="store_true", help="未対応文字と後置シフトの衝突を表示")
    p.add_argument("--config", type=Path, help="この設定の制約を守っているか確認する")
    p.add_argument("--targets", type=Path, help="打鍵数の目標（config/targets.toml）を確認する")
    p.add_argument(
        "--trigram",
        action="store_true",
        help="3 打鍵の連なりを評価する（n-gram 表では 3gram.csv が必要）",
    )
    p.add_argument(
        "--corpus",
        type=Path,
        default=DEFAULT_CORPUS,
        help="かなコーパスのファイル、または n-gram 表のディレクトリ（corpus-fetch-ngram）",
    )
    p.add_argument("--cost", type=Path, default=DEFAULT_COST)
    p.set_defaults(func=_cmd_eval)

    p = sub.add_parser("optimize", help="焼きなまし法で配列を生成する")
    p.add_argument("config", type=Path, nargs="?", default=Path("config/optimize.toml"))
    p.add_argument("-o", "--output", type=Path, required=True)
    p.add_argument("--iterations", type=int)
    p.add_argument("--restarts", type=int)
    p.add_argument("--seed", type=int)
    p.add_argument("--init", type=Path, help="この配列を初期配置にして探索する")
    p.add_argument(
        "--free",
        help="--init の配置のうち、動かしてよい文字（例: --free 'ゃゅょ'）。"
        "ほかは固定する。制約に違反している文字は指定しなくても動かす",
    )
    p.add_argument(
        "--corpus",
        type=Path,
        default=DEFAULT_CORPUS,
        help="かなコーパスのファイル、または n-gram 表のディレクトリ（corpus-fetch-ngram）",
    )
    p.add_argument("--cost", type=Path, default=DEFAULT_COST)
    p.set_defaults(func=_cmd_optimize)

    args = parser.parse_args(argv)
    if args.command == "eval" and not args.layouts and not args.romaji:
        parser.error("eval: 配列ファイルか --romaji を指定してください")
    try:
        args.func(args)
    except (LayoutError, ConstraintError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
