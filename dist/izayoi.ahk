; 十六夜配列 v0.1.0
; izayoi ahk で配列定義から生成したもの。直接編集しないこと。
; IME が ON でかな入力の間だけ有効になる（izayoiCondition で差し替えられる）。

#Requires AutoHotkey v2
#SingleInstance Force
; A_PriorKey でキーの並びが途切れたかを見るため、キーボードとマウスの入力を記録する
InstallKeybdHook
InstallMouseHook

; 有効にする条件。#Include する側で関数を代入すれば差し替えられる（前でも後でもよい）
if !IsSet(izayoiCondition)
    izayoiCondition := izayoiKanaInput

#HotIf izayoiCondition()
#HotString *?CX
::q::izayoiKey("q")
::w::izayoiKey("w")
::e::izayoiKey("e")
::r::izayoiKey("r")
::t::izayoiKey("t")
::y::izayoiKey("y")
::u::izayoiKey("u")
::i::izayoiKey("i")
::o::izayoiKey("o")
::p::izayoiKey("p")
::a::izayoiKey("a")
::s::izayoiKey("s")
::d::izayoiKey("d")
::f::izayoiKey("f")
::g::izayoiKey("g")
::h::izayoiKey("h")
::j::izayoiKey("j")
::k::izayoiKey("k")
::l::izayoiKey("l")
::;::izayoiKey(";")
::'::izayoiKey("'")
::z::izayoiKey("z")
::x::izayoiKey("x")
::c::izayoiKey("c")
::v::izayoiKey("v")
::b::izayoiKey("b")
::n::izayoiKey("n")
::m::izayoiKey("m")
::,::izayoiKey(",")
::.::izayoiKey(".")
::/::izayoiKey("/")

#HotIf

; フォーカスのあるウィンドウの IME が ON で、かな入力（英数でない）か
izayoiKanaInput()
{
    cbSize := 8 + A_PtrSize * 6 + 16
    info := Buffer(cbSize, 0)
    NumPut("UInt", cbSize, info, 0)
    DllCall("GetGUIThreadInfo", "UInt", 0, "Ptr", info)
    hwnd := NumGet(info, 8 + A_PtrSize, "Ptr")
    if (!hwnd) {
        try hwnd := WinGetID("A")
        catch
            return false
    }
    ime := DllCall("imm32\ImmGetDefaultIMEWnd", "Ptr", hwnd, "Ptr")
    ; WM_IME_CONTROL, IMC_GETOPENSTATUS
    if (!DllCall("SendMessage", "Ptr", ime, "UInt", 0x0283, "Ptr", 0x05, "Ptr", 0)) {
        return false
    }
    ; WM_IME_CONTROL, IMC_GETCONVERSIONMODE。IME_CMODE_NATIVE（かな）でなければ英数
    mode := DllCall("SendMessage", "Ptr", ime, "UInt", 0x0283, "Ptr", 0x01, "Ptr", 0)
    return (mode & 0x01) != 0
}

; 直前に打ったキー（A_PriorKey）が、状態を残したキーでなければ状態を捨てる
izayoiState()
{
    static state := {pending: "", last: "", key: ""}
    if (state.key != "" and GetKeySC(A_PriorKey) != GetKeySC(state.key)) {
        state.pending := "", state.last := "", state.key := ""
    }
    return state
}

; 直前の bs 文字を消して text を出す
izayoiReplace(bs, text)
{
    if (bs > 0) {
        SendEvent "{BS " bs "}"
    }
    if (text != "") {
        SendEvent "{Text}" text
    }
}

izayoiKey(key)
{
    ; 前置シフトのキー → 単独打鍵の句読点
    static prefix := Map(
        "d", "。",
        "k", "、"
    )
    static layers := Map(
        "base", Map(
            "q", "も",
            "w", "こ",
            "e", "の",
            "r", "あ",
            "t", "ま",
            "y", "つ",
            "u", "た",
            "i", "な",
            "o", "っ",
            "p", "ー",
            "a", "を",
            "s", "い",
            "f", "か",
            "g", "と",
            "h", "ん",
            "j", "て",
            "l", "し",
            ";", "く",
            "'", "お",
            "z", "ゃ",
            "x", "ょ",
            "c", "に",
            "v", "は",
            "b", "ゅ",
            "n", "る",
            "m", "う",
            ",", "そ",
            ".", "き",
            "/", "す"
        ),
        "d", Map(
            "q", "ぽ",
            "w", "ご",
            "e", "ぴ",
            "r", "ぼ",
            "t", "ぱ",
            "y", "ゎ",
            "u", "り",
            "i", "ち",
            "o", "め",
            "p", "ぃ",
            "a", "ぶ",
            "s", "ざ",
            "d", "ぜ",
            "f", "が",
            "g", "ど",
            "h", "ひ",
            "j", "ら",
            "k", "け",
            "l", "れ",
            ";", "え",
            "z", "゜",
            "x", "゛",
            "c", "。",
            "v", "ば",
            "b", "ぷ",
            "n", "へ",
            "m", "ゆ",
            ",", "！",
            ".", "ぁ",
            "/", "ぇ"
        ),
        "k", Map(
            "q", "ぉ",
            "w", "や",
            "e", "み",
            "r", "ほ",
            "t", "ね",
            "y", "づ",
            "u", "だ",
            "i", "ぢ",
            "o", "ぺ",
            "a", "ふ",
            "s", "さ",
            "d", "せ",
            "f", "ろ",
            "g", "わ",
            "h", "び",
            "j", "で",
            "k", "げ",
            "l", "じ",
            ";", "ぐ",
            "'", "、",
            "z", "ぅ",
            "x", "ぬ",
            "c", "？",
            "v", "よ",
            "b", "む",
            "n", "べ",
            "m", "ゔ",
            ",", "ぞ",
            ".", "ぎ",
            "/", "ず"
        )
    )
    ; 後置シフト: トリガーの文字 → {直前の文字: 置き換え後}
    static postfix := Map(
        "ゃ", Map(
            "て", "てぃ",
            "で", "でぃ",
            "こ", "くぃ",
            "ご", "ぐぃ",
            "と", "つぃ",
            "ど", "づぃ",
            "お", "うぃ",
            "へ", "ふぃ",
            "べ", "ゔぃ",
            "う", "いぇ",
            "す", "すぃ",
            "ず", "ずぃ",
            "ふ", "ふぁ",
            "は", "ふぁ",
            "つ", "つぁ",
            "く", "くぁ",
            "ぐ", "ぐぁ",
            "ゔ", "ゔぁ",
            "げ", "ゃ",
            "も", "□",
            "ぽ", "◇",
            "あ", "○",
            "ま", "△",
            "ぱ", "▽",
            "い", "☆",
            "か", "←",
            "が", "↑",
            "ゎ", "；",
            "っ", "「",
            "め", "【",
            "ぺ", "『",
            "ー", "－",
            "そ", "‥‥",
            "な", "ちゃ",
            "ん", "ひゃ",
            "の", "みゃ",
            "た", "りゃ",
            "る", "ふぃ",
            "を", "ふぁ"
        ),
        "ょ", Map(
            "て", "ちぇ",
            "で", "ぢぇ",
            "こ", "くぇ",
            "ご", "ぐぇ",
            "と", "つぇ",
            "ど", "づぇ",
            "お", "うぇ",
            "へ", "ふぇ",
            "べ", "ゔぇ",
            "う", "うぉ",
            "す", "しぇ",
            "ず", "じぇ",
            "ふ", "ふぉ",
            "は", "ふぉ",
            "つ", "つぉ",
            "く", "くぉ",
            "ぐ", "ぐぉ",
            "ゔ", "ゔぉ",
            "げ", "ょ",
            "も", "■",
            "ぽ", "◆",
            "あ", "●",
            "ま", "▲",
            "ぱ", "▼",
            "い", "★",
            "か", "→",
            "が", "↓",
            "ゎ", "’",
            "っ", "」",
            "め", "】",
            "ぺ", "』",
            "ー", "―",
            "そ", "……",
            "な", "ちょ",
            "ん", "ひょ",
            "の", "みょ",
            "た", "りょ",
            "る", "ふぇ",
            "を", "ふぉ"
        ),
        "ゅ", Map(
            "と", "とぅ",
            "ど", "どぅ",
            "ふ", "ふゅ",
            "う", "ゐ",
            "お", "ゑ",
            "く", "くゎ",
            "ぐ", "ぐゎ",
            "げ", "ゅ",
            "あ", "◎",
            "い", "×",
            "か", "⇒",
            "が", "⇔",
            "。", "．",
            "、", "，",
            "っ", "・",
            "め", "／",
            "ぺ", "※",
            "ー", "～",
            "な", "ちゅ",
            "ん", "ひゅ",
            "の", "みゅ",
            "た", "りゅ",
            "を", "ふゅ"
        )
    )
    state := izayoiState()
    state.key := key
    if (state.pending != "") {
        ; 前置シフトのキーで出しておいた句読点を消して、シフト面の文字にする
        layer := state.pending
        shown := prefix[layer]
        state.pending := ""
    } else if (prefix.Has(key)) {
        ; 単独打鍵の句読点を先に出しておく。直前の文字は後置シフトのために覚えたまま
        state.pending := key
        izayoiReplace(0, prefix[key])
        return
    } else {
        layer := "base"
        shown := ""
    }
    text := layers[layer].Get(key, "")
    before := state.last
    if (text == "") {
        izayoiReplace(StrLen(shown), "")
        state.last := ""
    } else if (postfix.Has(text) and postfix[text].Has(before)) {
        ; 置き換えた文字にはさらに後置シフトをかけない
        izayoiReplace(StrLen(shown) + StrLen(before), postfix[text][before])
        state.last := ""
    } else {
        izayoiReplace(StrLen(shown), text)
        state.last := text
    }
}
