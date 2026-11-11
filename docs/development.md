# 開発

配列の定義、配列を生成・評価するツール、各環境向けの実装（AutoHotkey スクリプト）の生成について。
要件は [requirements.md](requirements.md)、実装方式や評価・生成の設計は [design.md](design.md) にまとめている。

## 準備

[uv](https://docs.astral.sh/uv/) と Python 3.14 を使う。

```sh
uv sync                                  # 依存関係のインストール
uv run pytest                            # テスト
uv run ruff check . && uv run ruff format .
```

## 配列の定義と実装の生成

採用した配列の定義は `layout/izayoi.toml` だけに書き、実装や README の配列表はそこから生成する。生成物は手で編集しない。

```sh
uv run izayoi check layout/izayoi.toml               # 配列定義の検証
uv run izayoi ahk layout/izayoi.toml                 # dist/izayoi.ahk を生成
uv run izayoi chart layout/izayoi.toml -o README.md  # README の配列表を更新
```

`dist/izayoi.ahk` と README の配列表は git で管理している。配列定義やジェネレーターを変えたら生成し直してコミットする（食い違いはテストで検出する）。

WSL で開発している場合は、生成したスクリプトを Windows 側に出力して実行する。

```sh
uv run izayoi ahk layout/izayoi.toml -o /mnt/c/Users/<ユーザー名>/izayoi/izayoi.ahk
```

## 配列の生成と評価

配列は、コーパス（文章を読みのかなに変換したもの）に対する運指コストで評価し、
焼きなまし法でコストの低い配置を探す。

```sh
uv run izayoi corpus-fetch                     # 青空文庫から 150 作品を取得（corpus/raw/aozora/）
uv run izayoi corpus-build                     # corpus/raw/*/ をかなに変換（corpus/kana.txt）
uv run izayoi optimize -o candidates/foo.toml   # 配列を生成
uv run izayoi eval candidates/foo.toml --romaji --detail   # 評価・比較
```

- 自分の文章も評価に使いたいときは、`corpus/raw/<任意の名前>/*.txt`（UTF-8）に置いて `corpus-build` し直す。
- モーラ単位の n-gram 表（ロゴス配列用）でも評価できる。`uv run izayoi corpus-fetch-ngram` のあと、`eval` / `optimize` に `--corpus corpus/ngram/logos` を付ける。
- `config/optimize.toml`: キーに置く文字、後置シフトの規則、配置の制約（固定・置ける場所の制限・空けておくキー）、探索回数。
- 気に入った案の一部だけを動かすには `optimize --init <配列> --free '<動かす文字>'`。それ以外の文字は固定する（制約に違反している文字だけは動かす）。
- 手で編集した配列は `eval <配列> --config config/optimize.toml` で、制約を守っているかも確認できる。`--targets config/targets.toml` を付けると、打鍵数の目標を満たすかも表示する。
- `config/cost.toml`: 運指コストの重み。
- `eval` には複数の配列ファイルを渡せる。`--detail` を付けると、未対応の文字と後置シフトの衝突（規則のせいで、その並びをそのまま打てなくなる回数）も表示する。

### 評価指標

| 指標 | 意味 |
| --- | --- |
| 打鍵/かな | かな 1 文字あたりの打鍵数 |
| コスト/かな | キーの負担と 2 打鍵の組み合わせの負担の合計を、かな 1 文字あたりにしたもの（最適化の目的関数） |
| 前置シフト率% | かな 1 文字あたりの前置シフトキーの打鍵数 |
| 同指連続% | 同じ指で別のキーを続けて打つ割合 |
| 段越え% | 同じ手で上段と下段を続けて打つ割合 |
| 内ロール% / 外ロール% | 同じ手・同じ段で、隣の指へ内向き / 外向きに続けて打つ割合 |
| 後置衝突% | 後置シフトの規則と衝突する並びの出現率 |

## Claude Code のクラウドセッション

Claude Code のクラウドセッションで作業するための設定は、[設計仕様](design.md) の「5. クラウドでの作業」にまとめている。
コーパスは git に入れず、クラウド環境のセットアップスクリプトで `scripts/cloud-corpus.sh` を実行して作る。
`.claude/settings.json` の SessionStart フック（`scripts/cloud-session-start.sh`）は、クラウドセッションでだけ依存関係のインストールとコーパスのリンクを行い、手元では何もしない。

## ディレクトリ構成

| パス | 内容 |
| --- | --- |
| `layout/izayoi.toml` | 採用した配列の定義（実装の生成元） |
| `config/` | 生成・評価の設定 |
| `candidates/` | 生成・検討中の配列案 |
| `corpus/` | コーパス（git 管理外） |
| `src/izayoi/` | 定義の読み込み・検証、評価、生成、AHK と配列表の出力 |
| `tests/` | テスト |
| `dist/izayoi.ahk` | 生成した AutoHotkey スクリプト（git で管理） |
| `scripts/` | クラウドセッション用のスクリプト |
| `docs/` | 要件・設計仕様・開発の文書 |
