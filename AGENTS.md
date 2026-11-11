# AGENTS.md

十六夜配列（かな配列）の定義と、配列の生成・評価ツール、各環境向けの実装のジェネレーター。

## 構成

- `layout/izayoi.toml` が採用した配列の唯一の定義元。生成・検討中の案は `candidates/` に置く。各環境向けの実装（AHK スクリプトなど）は必ずここから生成し、生成物を手で編集しない。
- `src/izayoi/layout.py`: 定義の読み込みと検証。
- `src/izayoi/corpus.py`: 青空文庫の取得と、fugashi + unidic-lite による読み（表記どおりのかな）への変換。
- `src/izayoi/ngram.py`: モーラ単位の n-gram 表（ロゴス配列用）の取得と、それを使った評価。
- `src/izayoi/evaluate.py`: コーパスを打鍵単位に分割し、キーごと・2 打鍵ごとの統計と評価指標を出す。
- `src/izayoi/constraints.py`: 配置の制約（場所のセレクター、固定、置ける場所の制限、空けておくキー）。
- `src/izayoi/optimize.py`: 焼きなまし法。後置シフトの規則は固定し、文字の配置だけを探す。
- `src/izayoi/romaji.py`: 比較の基準にするローマ字入力。
- `src/izayoi/targets.py`: 打鍵数の目標（`config/targets.toml`）を満たすかの確認。
- `src/izayoi/chart.py`: README の配列表（Markdown）を生成する。`<!-- chart:begin ... -->` と `<!-- chart:end -->` の間を書き換える。
- `src/izayoi/ahk.py`: AHK v2 のホットストリングを生成する。単独で実行でき、IME が ON でかな入力の間だけ有効になる。`#Include` する側は `izayoiCondition` で有効にする条件を差し替えられる。

## 配列の仕様

README は配列を使う人向けに書き、開発の手順（ツールの使い方、評価指標、ディレクトリ構成など）は `docs/development.md` に書く。

要件（何を満たすか）は `docs/requirements.md`、設計仕様（各 OS 向けの実装方式、評価・生成ツールの設計）は `docs/design.md` に、決定・仮・未定の状態つきでまとめている。実装方式などの設計判断を要件側に書かない。仕様や設定を変えたら、該当する文書も更新する。

- キー: US 配列の 31 キー（30 キー＋`'`）。`[` `]` と数字キーは使わず、IME にそのまま渡す（数字キーを後置シフトのトリガーにする仕組み `RAW_TRIGGERS` は残してある）。
- 前置シフト: `D` / `K`（月配列系）。異手シフトは通常のシフト面の文字、同手シフトは原則として濁音・半濁音で、対応する清音と同じキーにそろえる（ぱ行は ま行）。
- 単独打鍵: `D` / `K` ＋確定系のキーで句読点（配列定義では `[prefix] solo`）。
- 拗音: い段＋小書き（き＋ゃ）で打つ。シフト面の い段は、拗音キーの直前ではシフトを省略できる（`[shift_omission]`。同じキーの通常面の文字＋拗音キー → い段＋拗音）。拗音キーの後置シフトの規則でも、直前の文字がシフト面にあれば同じようにシフトを省略できる（`postfix = true`。例: ふ＋ゃ → ふぁ）。
- 後置シフト: 拗音キー（例外的にほかのキー）を直後に打つと直前の文字を置き換える（外来音、記号、古語）。打った並びはなるべくそのまま残す。記号は ゃ＝前、ょ＝次、ゅ＝代替 にそろえる。
- 「濁音・半濁音は同手シフト」と「拗音はい段＋小書き」は例外なく守る。外来音・古語は規則から外れてよい。
- 要件の「原則」はコードに固定せず、`config/optimize.toml` の制約として書く。
- TOML のテーブル名は ASCII 文字だけにする（かなはキーや値に書く。例: `[[postfix]]` の `trigger = "ょ"`）。
- 同時打鍵には対応しない。IME ON の間だけ有効にする。
- 対象 OS は Windows。Linux も候補（実装方式は未定）。OS 固有の処理は実装のジェネレーターに閉じ込め、配列定義や評価には持ち込まない。

## コミットメッセージ

Conventional Commits 形式で、type と scope は英語、件名と本文は日本語で書く。

```
feat(optimize): 拗音を通常面に置く

「きゃ」などを 2 打で打てることを優先する。
```

## コマンド

- テスト: `uv run pytest`
- lint / format: `uv run ruff check .` / `uv run ruff format .`
- AHK 生成: `uv run izayoi ahk layout/izayoi.toml`（生成した `dist/izayoi.ahk` もコミットする）
- README の配列表: `uv run izayoi chart layout/izayoi.toml -o README.md`（配列定義を変えたら更新してコミットする）
- 配列生成: `uv run izayoi optimize -o candidates/<名前>.toml`
- 評価: `uv run izayoi eval <配列>... --romaji --detail --config config/optimize.toml --targets config/targets.toml`（`corpus/kana.txt` が必要。なければ `corpus-fetch` → `corpus-build`）
- n-gram 表で評価: `uv run izayoi corpus-fetch-ngram` のあと、`eval` / `optimize` に `--corpus corpus/ngram/logos`
