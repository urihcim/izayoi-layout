# 十六夜配列

月配列系の前置シフトと、拗音キーによる後置シフトを組み合わせたかな配列。
青空文庫などのコーパスに対する運指コストを評価し、焼きなまし法で配置を決めている。

Windows では AutoHotkey v2 のスクリプトで使える。配列はまだ調整中で、今後も配置が変わることがある。

## 特徴

- **逐次打鍵だけ**: 同時打鍵は使わない
- **前置シフト**: `D` / `K` を先に押してから、次のキーでシフト面の文字を出す
  - 異手シフト（`D`＋右手、`K`＋左手）: シフト面の文字
  - 同手シフト（`D`＋左手、`K`＋右手）: 濁音・半濁音。清音と同じキーで出す（ぱ行は ま行、ゔ は う と同じキー）
  - 単独打鍵（`D` / `K` ＋スペース・Enter など）: 句読点
- **拗音**: い段の文字＋小書きの ゃ ゅ ょ で打つ（き＋ゃ＝きゃ）。ゃ ゅ ょ は通常面にあり、シフト面にある い段の文字も、ゃ ゅ ょ の直前ではシフトを省略して 2 打で打てる
- **後置シフト**: 文字の直後に ゃ ゅ ょ を打つと、直前の文字と合わせて外来音・古語・記号に置き換わる（て＋ゃ＝てぃ、っ＋ゃ＝「）
- **キー**: US 配列の 31 キー（英字部分の 30 キー＋`'`）。`[` `]` と数字キーは IME にそのまま渡す（`[` `]` で 「 」 を打てる）

## 配列

各キーの上がかな、下がキー（US 配列の位置）。空欄は割り当てなし。

<!-- chart:begin (uv run izayoi chart layout/izayoi.toml -o README.md) -->

#### 通常面

| | | | | | | | | | | | |
| --- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| 上段 | も<br><sub>Q</sub> | こ<br><sub>W</sub> | の<br><sub>E</sub> | あ<br><sub>R</sub> | ま<br><sub>T</sub> | つ<br><sub>Y</sub> | た<br><sub>U</sub> | な<br><sub>I</sub> | っ<br><sub>O</sub> | ー<br><sub>P</sub> |  |
| 中段 | を<br><sub>A</sub> | い<br><sub>S</sub> | 前置<br><sub>D</sub> | か<br><sub>F</sub> | と<br><sub>G</sub> | ん<br><sub>H</sub> | て<br><sub>J</sub> | 前置<br><sub>K</sub> | し<br><sub>L</sub> | く<br><sub>;</sub> | お<br><sub>'</sub> |
| 下段 | ゃ<br><sub>Z</sub> | ょ<br><sub>X</sub> | に<br><sub>C</sub> | は<br><sub>V</sub> | ゅ<br><sub>B</sub> | る<br><sub>N</sub> | う<br><sub>M</sub> | そ<br><sub>,</sub> | き<br><sub>.</sub> | す<br><sub>/</sub> |  |

#### D 面

| | | | | | | | | | | | |
| --- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| 上段 | ぽ<br><sub>Q</sub> | ご<br><sub>W</sub> | ぴ<br><sub>E</sub> | ぼ<br><sub>R</sub> | ぱ<br><sub>T</sub> | ゎ<br><sub>Y</sub> | り<br><sub>U</sub> | ち<br><sub>I</sub> | め<br><sub>O</sub> | ぃ<br><sub>P</sub> |  |
| 中段 | ぶ<br><sub>A</sub> | ざ<br><sub>S</sub> | ぜ<br><sub>D</sub> | が<br><sub>F</sub> | ど<br><sub>G</sub> | ひ<br><sub>H</sub> | ら<br><sub>J</sub> | け<br><sub>K</sub> | れ<br><sub>L</sub> | え<br><sub>;</sub> | <br><sub>'</sub> |
| 下段 | ゜<br><sub>Z</sub> | ゛<br><sub>X</sub> | 。<br><sub>C</sub> | ば<br><sub>V</sub> | ぷ<br><sub>B</sub> | へ<br><sub>N</sub> | ゆ<br><sub>M</sub> | ！<br><sub>,</sub> | ぁ<br><sub>.</sub> | ぇ<br><sub>/</sub> |  |

#### K 面

| | | | | | | | | | | | |
| --- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| 上段 | ぉ<br><sub>Q</sub> | や<br><sub>W</sub> | み<br><sub>E</sub> | ほ<br><sub>R</sub> | ね<br><sub>T</sub> | づ<br><sub>Y</sub> | だ<br><sub>U</sub> | ぢ<br><sub>I</sub> | ぺ<br><sub>O</sub> | <br><sub>P</sub> |  |
| 中段 | ふ<br><sub>A</sub> | さ<br><sub>S</sub> | せ<br><sub>D</sub> | ろ<br><sub>F</sub> | わ<br><sub>G</sub> | び<br><sub>H</sub> | で<br><sub>J</sub> | げ<br><sub>K</sub> | じ<br><sub>L</sub> | ぐ<br><sub>;</sub> | 、<br><sub>'</sub> |
| 下段 | ぅ<br><sub>Z</sub> | ぬ<br><sub>X</sub> | ？<br><sub>C</sub> | よ<br><sub>V</sub> | む<br><sub>B</sub> | べ<br><sub>N</sub> | ゔ<br><sub>M</sub> | ぞ<br><sub>,</sub> | ぎ<br><sub>.</sub> | ず<br><sub>/</sub> |  |

単独打鍵（前置シフトのキー＋スペース・Enter など）: `D` → 。 ／ `K` → 、

#### 後置シフト（外来音・古語）

| 直前の文字 | ＋ゃ | ＋ょ | ＋ゅ |
| :---: | :---: | :---: | :---: |
| て | てぃ | ちぇ |  |
| で | でぃ | ぢぇ |  |
| こ | くぃ | くぇ |  |
| ご | ぐぃ | ぐぇ |  |
| と | つぃ | つぇ | とぅ |
| ど | づぃ | づぇ | どぅ |
| お | うぃ | うぇ | ゑ |
| へ | ふぃ | ふぇ |  |
| べ | ゔぃ | ゔぇ |  |
| う | いぇ | うぉ | ゐ |
| す | すぃ | しぇ |  |
| ず | ずぃ | じぇ |  |
| ふ | ふぁ | ふぉ | ふゅ |
| は | ふぁ | ふぉ |  |
| つ | つぁ | つぉ |  |
| く | くぁ | くぉ | くゎ |
| ぐ | ぐぁ | ぐぉ | ぐゎ |
| ゔ | ゔぁ | ゔぉ |  |
| げ | ゃ | ょ | ゅ |

#### 後置シフト（記号）

| 直前の文字 | ＋ゃ | ＋ょ | ＋ゅ |
| :---: | :---: | :---: | :---: |
| も | □ | ■ |  |
| ぽ | ◇ | ◆ |  |
| あ | ○ | ● | ◎ |
| ま | △ | ▲ |  |
| ぱ | ▽ | ▼ |  |
| い | ☆ | ★ | × |
| か | ← | → | ⇒ |
| が | ↑ | ↓ | ⇔ |
| ゎ | ； | ’ |  |
| っ | 「 | 」 | ・ |
| め | 【 | 】 | ／ |
| ぺ | 『 | 』 | ※ |
| ー | － | ― | ～ |
| そ | ‥‥ | …… |  |
| 。 |  |  | ． |
| 、 |  |  | ， |

<!-- chart:end -->

- シフト面にある文字は、後置シフトの直前でもシフトを省略できる。たとえば ふ（`K`→`A`）＋ゃ の ふぁ は、`A`→`Z` の 2 打で打てる（同じキーの通常面の文字にその規則がないとき）。
- げ＋ゃ／ょ／ゅ は小書きの ゃ ょ ゅ だけを出す。規則のある文字の直後に小書きをそのまま打ちたいときに使う（て の後に ゃ を打つと てぃ になるので、「てゃ」は て・げ・ゃ と打つ）。
- （ ） ① などほかの記号は、IME の変換や数字キーで打つ。

## 使い方（Windows）

1. [AutoHotkey v2](https://www.autohotkey.com/) をインストールする。
2. [`dist/izayoi.ahk`](dist/izayoi.ahk) をダウンロードする（ファイルのページの「Download raw file」）。
3. `izayoi.ahk` をダブルクリックして起動する。IME が ON でかな入力のときだけ有効になり、英数入力（Shift 単独などで切り替えたとき）や IME OFF のときはキーをそのまま通す。

ログオン時に起動するには、`izayoi.ahk` のショートカットをスタートアップフォルダー（エクスプローラーのアドレス欄に `shell:startup` と入力すると開く）に置く。

### Microsoft IME の設定

Microsoft IME では、設定の「Microsoft IME → 全般 → 以前のバージョンの Microsoft IME を使う」をオンにする。
新しい Microsoft IME では、確定後に Ctrl+A → BackSpace で中身を全部消すなどすると、以後のかなが変換中にならず確定状態で入るようになり、別のウィンドウに切り替えるまで戻らない（スクリプトがかなを Unicode の文字として送るため）。

### 打ち方の注意

- `D` / `K` を押した時点で 。 / 、 が表示され、続けてかなのキーを押すと前置シフトの文字に置き換わる。スペースや Enter を続けたときは句読点のまま、そのキーは IME に渡す（変換が始まる）。
- 前置シフトや後置シフトの途中で BackSpace・カーソル移動・マウスのクリックなどを挟むと、シフトは取り消される。

### ほかのスクリプトから使う

ほかの AutoHotkey スクリプトに `#Include` して使うこともできる。有効にする条件は、`izayoiCondition` に関数を代入して差し替えられる。

```ahk
izayoiCondition := () => imeOn() and myKanaMode()
#Include izayoi.ahk
```

### ほかの OS

今は Windows（AutoHotkey）だけに対応している。Linux への対応は検討中（[設計仕様](docs/design.md) の「2.3 Linux（候補）」）。

## ドキュメント

- [要件](docs/requirements.md): 配列が満たすべきこと
- [設計仕様](docs/design.md): 実装方式、配列の評価・生成の方法、候補の比較
- [開発](docs/development.md): 配列の生成・評価ツールと、AutoHotkey スクリプトの生成

## ライセンス

[MIT License](LICENSE)。配列の定義、ツール、AutoHotkey スクリプトのすべてに適用する。
