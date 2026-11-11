"""Romaji input on QWERTY, used as a baseline for comparison.

Uses the shortest common spellings accepted by Japanese IMEs
(si, ti, tu, hu, zi, sya, ...).
"""

from __future__ import annotations

import re

_BASE = """
あ a い i う u え e お o
か ka き ki く ku け ke こ ko  が ga ぎ gi ぐ gu げ ge ご go
さ sa し si す su せ se そ so  ざ za じ zi ず zu ぜ ze ぞ zo
た ta ち ti つ tu て te と to  だ da ぢ di づ du で de ど do
な na に ni ぬ nu ね ne の no
は ha ひ hi ふ hu へ he ほ ho  ば ba び bi ぶ bu べ be ぼ bo  ぱ pa ぴ pi ぷ pu ぺ pe ぽ po
ま ma み mi む mu め me も mo
や ya ゆ yu よ yo
ら ra り ri る ru れ re ろ ro
わ wa を wo ゔ vu
ぁ la ぃ li ぅ lu ぇ le ぉ lo ゃ lya ゅ lyu ょ lyo っ ltu ゎ lwa
ゐ wi ゑ we
きゃ kya きゅ kyu きょ kyo  ぎゃ gya ぎゅ gyu ぎょ gyo
しゃ sya しゅ syu しょ syo  じゃ zya じゅ zyu じょ zyo  しぇ sye じぇ zye
ちゃ tya ちゅ tyu ちょ tyo  ぢゃ dya ぢゅ dyu ぢょ dyo  ちぇ tye
にゃ nya にゅ nyu にょ nyo
ひゃ hya ひゅ hyu ひょ hyo  びゃ bya びゅ byu びょ byo  ぴゃ pya ぴゅ pyu ぴょ pyo
みゃ mya みゅ myu みょ myo
りゃ rya りゅ ryu りょ ryo
ふぁ fa ふぃ fi ふぇ fe ふぉ fo  ゔぁ va ゔぃ vi ゔぇ ve ゔぉ vo
てぃ thi でぃ dhi とぅ twu どぅ dwu  うぃ wi うぇ we うぉ who
てゅ thu でゅ dhu ふゅ fyu
"""

TABLE: dict[str, str] = {}
for _k, _v in re.findall(r"(\S+) (\S+)", _BASE):
    TABLE[_k] = _v
TABLE["ー"] = "-"
TABLE["、"] = ","
TABLE["。"] = "."
TABLE["「"] = "["
TABLE["」"] = "]"
TABLE["？"] = "?"
TABLE["！"] = "!"

_UNIT_RE = re.compile("|".join(sorted(map(re.escape, TABLE), key=len, reverse=True)) + "|.")


def to_romaji(text: str) -> tuple[str, int]:
    """Convert a kana line to keystrokes. Returns (keys, unsupported char count).

    Unsupported characters become a newline (no bigram across it).
    """
    units = _UNIT_RE.findall(text)
    out = []
    unsupported = 0
    for i, u in enumerate(units):
        nxt = TABLE.get(units[i + 1], "") if i + 1 < len(units) else ""
        if u == "ん":
            # A single "n" is enough only before a consonant other than n/y.
            single = nxt[:1].isalpha() and nxt[0] not in "aiueony"
            out.append("n" if single else "nn")
        elif u == "っ":
            out.append(nxt[0] if nxt[:1].isalpha() and nxt[0] not in "aiueonl" else "ltu")
        elif u in TABLE:
            out.append(TABLE[u])
        else:
            unsupported += len(u)
            out.append("\n")
    return "".join(out), unsupported
