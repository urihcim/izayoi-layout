"""Generate an AutoHotkey v2 script from a layout.

The output is a standalone script: it is active only while the IME is on and in
a kana (native) input mode, so the alphanumeric mode (e.g. toggled by Shift) is left alone.
It can also be #Include'd from another script, which may replace the condition
by assigning a function object to the global `izayoiCondition`.
Every layout key is a `*?CX` hotstring (hotstrings do not fire while Ctrl / Alt
is held), and kana are sent with SendEvent, replacing the preceding output with
BackSpace for postfix rules.

Prefix shift and postfix shift are not written as multi-key hotstrings: the
hotstring buffer keeps the raw keys, so a suffix match would misread the second
key of a prefix pair as a new prefix (K+D then J would match D+J). Instead each
key calls izayoiKey(), which keeps the pending prefix key and the last output,
and treats them as stale unless the previous key press (A_PriorKey) is the key
that left them.

Digit keys that are postfix triggers (○ then 1 → ①) are hotkeys under a #HotIf
that holds only right after an output with a rule for that digit, so they type
digits as usual everywhere else.
"""

from __future__ import annotations

from .layout import KEYS, RAW_TRIGGERS, SOLO, Layout

CONDITION = "izayoiCondition"
DEFAULT_CONDITION = "izayoiKanaInput"


def _str(s: str) -> str:
    return '"' + s.replace("`", "``").replace('"', '`"') + '"'


def _map(items: dict[str, str], indent: str) -> list[str]:
    """A Map literal; one pair per line (continuation by enclosure)."""
    if not items:
        return ["Map()"]
    lines = ["Map("]
    pairs = list(items.items())
    for i, (k, v) in enumerate(pairs):
        comma = "," if i < len(pairs) - 1 else ""
        lines.append(f"{indent}    {_str(k)}, {_str(v)}{comma}")
    lines.append(f"{indent})")
    return lines


def _nested_map(items: dict[str, dict[str, str]], indent: str) -> list[str]:
    lines = ["Map("]
    pairs = list(items.items())
    for i, (k, v) in enumerate(pairs):
        comma = "," if i < len(pairs) - 1 else ""
        inner = _map(v, indent + "    ")
        inner[-1] += comma
        lines.append(f"{indent}    {_str(k)}, {inner[0]}")
        lines += inner[1:]
    lines.append(f"{indent})")
    return lines


def _static(name: str, value: list[str]) -> list[str]:
    lines = [f"    static {name} := {value[0]}"]
    return lines + value[1:]


def _hotstring_key(key: str) -> str:
    # ";" right after "::" is not a comment; only "`" and ":" need escaping.
    return key.replace("`", "``").replace(":", "`:")


def generate(layout: Layout) -> str:
    layers = {name: layout.layers[name] for name in ["base", *layout.prefix_keys]}
    solo = layout.layers.get(SOLO, {})
    postfix, _ = layout.effective_postfix()
    outputs = set(layout.sequences().values())
    raw = {t: r for t, r in postfix.items() if t in RAW_TRIGGERS and t not in outputs}
    # a raw trigger types itself
    layers["base"] = {**layers["base"], **{t: t for t in raw}}
    used = [k for k in KEYS if k in layout.prefix_keys or any(k in g for g in layers.values())]

    out = [
        f"; {layout.name} v{layout.version}",
        "; izayoi ahk で配列定義から生成したもの。直接編集しないこと。",
        "; IME が ON でかな入力の間だけ有効になる（izayoiCondition で差し替えられる）。",
        "",
        "#Requires AutoHotkey v2",
        "#SingleInstance Force",
        "; A_PriorKey でキーの並びが途切れたかを見るため、キーボードとマウスの入力を記録する",
        "InstallKeybdHook",
        "InstallMouseHook",
        "",
    ]
    out += [
        "; 有効にする条件。#Include する側で関数を代入すれば差し替えられる（前でも後でもよい）",
        f"if !IsSet({CONDITION})",
        f"    {CONDITION} := {DEFAULT_CONDITION}",
        "",
        f"#HotIf {CONDITION}()",
        "#HotString *?CX",
    ]
    out += [f"::{_hotstring_key(k)}::izayoiKey({_str(k)})" for k in used]
    if raw:
        out += ["", "; 数字キーは、後置シフトの規則がある文字の直後だけ取る"]
        for t in raw:
            out += [f"#HotIf {CONDITION}() and izayoiRawReady({_str(t)})"]
            out += [f"{t}::izayoiKey({_str(t)})"]
    out += ["", "#HotIf", ""]

    prefix = {k: solo.get(k, "") for k in layout.prefix_keys}
    out += [
        "; フォーカスのあるウィンドウの IME が ON で、かな入力（英数でない）か",
        "izayoiKanaInput()",
        "{",
        "    cbSize := 8 + A_PtrSize * 6 + 16",
        "    info := Buffer(cbSize, 0)",
        '    NumPut("UInt", cbSize, info, 0)',
        '    DllCall("GetGUIThreadInfo", "UInt", 0, "Ptr", info)',
        '    hwnd := NumGet(info, 8 + A_PtrSize, "Ptr")',
        "    if (!hwnd) {",
        '        try hwnd := WinGetID("A")',
        "        catch",
        "            return false",
        "    }",
        '    ime := DllCall("imm32\\ImmGetDefaultIMEWnd", "Ptr", hwnd, "Ptr")',
        "    ; WM_IME_CONTROL, IMC_GETOPENSTATUS",
        '    if (!DllCall("SendMessage", "Ptr", ime, "UInt", 0x0283, "Ptr", 0x05, "Ptr", 0)) {',
        "        return false",
        "    }",
        "    ; WM_IME_CONTROL, IMC_GETCONVERSIONMODE。IME_CMODE_NATIVE（かな）でなければ英数",
        '    mode := DllCall("SendMessage", "Ptr", ime, "UInt", 0x0283, "Ptr", 0x01, "Ptr", 0)',
        "    return (mode & 0x01) != 0",
        "}",
        "",
        "; 直前に打ったキー（A_PriorKey）が、状態を残したキーでなければ状態を捨てる",
        "izayoiState()",
        "{",
        '    static state := {pending: "", last: "", key: ""}',
        '    if (state.key != "" and GetKeySC(A_PriorKey) != GetKeySC(state.key)) {',
        '        state.pending := "", state.last := "", state.key := ""',
        "    }",
        "    return state",
        "}",
        "",
        *(
            [
                "; key（数字）に、直前の文字を置き換える後置シフトの規則があるか",
                "izayoiRawReady(key)",
                "{",
                *_static("rules", _nested_map(raw, "    ")),
                "    state := izayoiState()",
                '    return state.pending == "" and rules[key].Has(state.last)',
                "}",
                "",
            ]
            if raw
            else []
        ),
        "; 直前の bs 文字を消して text を出す",
        "izayoiReplace(bs, text)",
        "{",
        "    if (bs > 0) {",
        '        SendEvent "{BS " bs "}"',
        "    }",
        '    if (text != "") {',
        '        SendEvent "{Text}" text',
        "    }",
        "}",
        "",
        "izayoiKey(key)",
        "{",
        "    ; 前置シフトのキー → 単独打鍵の句読点",
        *_static("prefix", _map(prefix, "    ")),
        *_static("layers", _nested_map(layers, "    ")),
        "    ; 後置シフト: トリガーの文字 → {直前の文字: 置き換え後}",
        *_static("postfix", _nested_map(postfix, "    ")),
        "    state := izayoiState()",
        "    state.key := key",
        '    if (state.pending != "") {',
        "        ; 前置シフトのキーで出しておいた句読点を消して、シフト面の文字にする",
        "        layer := state.pending",
        "        shown := prefix[layer]",
        '        state.pending := ""',
        "    } else if (prefix.Has(key)) {",
        "        ; 単独打鍵の句読点を先に出しておく。直前の文字は後置シフトのために覚えたまま",
        "        state.pending := key",
        "        izayoiReplace(0, prefix[key])",
        "        return",
        "    } else {",
        '        layer := "base"',
        '        shown := ""',
        "    }",
        '    text := layers[layer].Get(key, "")',
        "    before := state.last",
        '    if (text == "") {',
        '        izayoiReplace(StrLen(shown), "")',
        '        state.last := ""',
        "    } else if (postfix.Has(text) and postfix[text].Has(before)) {",
        "        ; 置き換えた文字にはさらに後置シフトをかけない",
        "        izayoiReplace(StrLen(shown) + StrLen(before), postfix[text][before])",
        '        state.last := ""',
        "    } else {",
        "        izayoiReplace(StrLen(shown), text)",
        "        state.last := text",
        "    }",
        "}",
        "",
    ]
    return "\n".join(out)
