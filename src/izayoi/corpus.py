"""Corpus acquisition and conversion to kana.

The kana corpus is plain text of hiragana, the long vowel mark and
Japanese punctuation (、。「」？！). A newline separates runs that cannot be typed as
continuous kana (alphanumerics, brackets, line breaks, ...), so that no
stroke bigram is counted across it.
"""

from __future__ import annotations

import csv
import io
import random
import re
import time
import urllib.request
import zipfile
from collections.abc import Iterable, Iterator
from pathlib import Path

AOZORA_INDEX = "https://www.aozora.gr.jp/index_pages/list_person_all_extended_utf8.zip"
SEP = "\n"

PUNCT = {
    "、": "、", "，": "、", "。": "。", "．": "。", "ー": "ー", "―": SEP,
    "「": "「", "」": "」", "？": "？", "?": "？", "！": "！", "!": "！",
}  # fmt: skip
_KATA_TO_HIRA = {c: c - 0x60 for c in range(ord("ァ"), ord("ヶ") + 1)}
_KANA_RE = re.compile(r"^[ぁ-ゖァ-ヺー]+$")


def to_hiragana(text: str) -> str:
    return text.translate(_KATA_TO_HIRA)


# --- Aozora Bunko ---------------------------------------------------------


def _fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "izayoi-layout corpus builder"})
    with urllib.request.urlopen(req, timeout=60) as res:
        return res.read()


def fetch_aozora(dest: Path, count: int, seed: int, delay: float = 1.0) -> list[Path]:
    """Download a random sample of public-domain works in modern kana usage."""
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(_fetch(AOZORA_INDEX))) as z:
        name = next(n for n in z.namelist() if n.endswith(".csv"))
        rows = list(csv.reader(io.TextIOWrapper(z.open(name), encoding="utf-8-sig")))
    header, rows = rows[0], rows[1:]
    col = {h: i for i, h in enumerate(header)}

    works: dict[str, str] = {}
    for r in rows:
        if (
            r[col["文字遣い種別"]] == "新字新仮名"
            and r[col["作品著作権フラグ"]] == "なし"
            and r[col["役割フラグ"]] == "著者"
            and r[col["テキストファイルURL"]].endswith(".zip")
        ):
            works.setdefault(r[col["作品ID"]], r[col["テキストファイルURL"]])

    ids = sorted(works)
    random.Random(seed).shuffle(ids)
    paths = []
    for work_id in ids[:count]:
        path = dest / f"{work_id}.txt"
        if not path.exists():
            data = _fetch(works[work_id])
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                txt = next(n for n in z.namelist() if n.endswith(".txt"))
                path.write_text(z.read(txt).decode("cp932", errors="replace"), encoding="utf-8")
            time.sleep(delay)
        paths.append(path)
    return paths


def clean_aozora(text: str) -> str:
    """Strip Aozora Bunko headers, footers, ruby and annotations."""
    lines = text.splitlines()
    # Header: title lines, then an optional legend enclosed by dashed lines.
    dashes = [i for i, line in enumerate(lines[:60]) if line.startswith("-----")]
    start = dashes[1] + 1 if len(dashes) >= 2 else 2
    body = []
    for line in lines[start:]:
        if line.startswith("底本："):
            break
        body.append(line)
    text = "\n".join(body)
    text = re.sub(r"《[^》]*》", "", text)
    text = re.sub(r"［＃[^］]*］", "", text)
    return text.replace("｜", "").replace("※", "")


# --- conversion to kana ---------------------------------------------------


def to_kana(lines: Iterable[str]) -> Iterator[str]:
    import fugashi

    tagger = fugashi.Tagger()
    for line in lines:
        out = []
        for word in tagger(line):
            surface = word.surface
            if surface in PUNCT:
                out.append(PUNCT[surface])
                continue
            kana = getattr(word.feature, "kana", None)
            if kana and kana != "*" and _KANA_RE.match(kana):
                out.append(to_hiragana(kana))
            elif _KANA_RE.match(surface):
                out.append(to_hiragana(surface))
            else:
                out.append(SEP)
        text = re.sub(r"\n+", SEP, "".join(out)).strip(SEP)
        if text:
            yield text


def build(raw_dirs: Iterable[Path], dest: Path) -> Path:
    """Convert every *.txt under raw_dirs into a single kana corpus file."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", encoding="utf-8") as out:
        for raw_dir in raw_dirs:
            for path in sorted(raw_dir.glob("*.txt")):
                text = path.read_text(encoding="utf-8")
                if raw_dir.name == "aozora":
                    text = clean_aozora(text)
                for line in to_kana(text.splitlines()):
                    out.write(line + SEP)
    return dest
