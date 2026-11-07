"""Editor で直した文字を Markdown に書き戻す。

直しは {"key", "src": [行, 始め, 終わり], "before", "after"}。位置は convert の src のまま。
BOM・改行の種類・末尾の改行の有無・ファイルの権限は変えない。
"""
import os
import re
import stat
from pathlib import Path

from .convert import ConvertError, convert

EDIT_CONFLICT = "エディターでこの文字が変わっているので、反映しませんでした"
BAD_NEWLINE = "改行は入れられません"
BAD_EMPTY = "空にはできません。消すときはエディターで消してください"
BAD_COMMENT = "<!-- と --> は入れられません"
BAD_RULE = "--- だけの行にはできません"


def _refuse(after):
    """書けない文なら、その断りの文言。書けるなら None。"""
    if "\n" in after or "\r" in after:
        return BAD_NEWLINE
    if not after.strip():
        return BAD_EMPTY
    if "<!--" in after or "-->" in after:
        return BAD_COMMENT
    if after.strip() == "---":
        return BAD_RULE
    return None


def apply_edits(text, edits, ids=()):
    """text に直しを当てる。返すのは (新しい文, 結果)。ids は (ページの最初の行, ID)。"""
    parts = re.split(r"(\r\n|\n|\r)", text)
    lines, eols = parts[0::2], parts[1::2]
    real = len(eols) + (1 if lines[-1] else 0)   # 末尾の改行の後ろの空は行に数えない
    taken = {}   # 行 -> 当てると決めた (始め, 終わり, after)
    res = {"applied": [], "conflicts": [], "ids_added": []}

    def conflict(key, message):
        res["conflicts"].append({"key": key, "message": message})

    # 重なりは edits の並びで先のものを残す（当てる順ではない）
    for e in edits:
        message = _refuse(e["after"])
        if message:
            conflict(e["key"], message)
            continue
        line, a, b = e["src"]
        if not (1 <= line <= real) or not (0 <= a <= b <= len(lines[line - 1])) \
                or lines[line - 1][a:b] != e["before"]:
            conflict(e["key"], EDIT_CONFLICT)
            continue
        if any(a < b2 and a2 < b for a2, b2, _ in taken.get(line, ())):
            conflict(e["key"], EDIT_CONFLICT)
            continue
        taken.setdefault(line, []).append((a, b, e["after"]))
        res["applied"].append(e["key"])

    for line, items in taken.items():
        s = lines[line - 1]
        for a, b, after in sorted(items, key=lambda t: t[0], reverse=True):
            s = s[:a] + after + s[b:]
        lines[line - 1] = s

    # ID の行は、直しの後に行の番号の大きい方から入れる（位置をずらさない）
    eol = eols[0] if eols else "\n"
    pairs = list(zip(lines, eols + [""]))
    for line, sid in sorted(ids, key=lambda t: t[0], reverse=True):
        pairs.insert(line - 1, (f"<!-- id: {sid} -->", eol))
        res["ids_added"].append(sid)
    res["ids_added"].reverse()
    return "".join(s + e for s, e in pairs), res


def write_back(md_path, edits):
    """ファイルに直しを書き戻す。変わったときだけ .editor/write.tmp 経由で置き換える。"""
    md_path = Path(md_path)
    raw = md_path.read_bytes()
    bom = raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig")
    try:
        slides = convert(md_path)["slides"]
        ids = [(s["src"][0], s["id"]) for s in slides if s["auto_id"]]
    except ConvertError:
        ids = []   # 変換が誤りなら ID は足さない
    new, res = apply_edits(text, edits, ids)
    if new != text:
        out = (b"\xef\xbb\xbf" if bom else b"") + new.encode("utf-8")
        tmp = md_path.parent / ".editor" / "write.tmp"
        tmp.parent.mkdir(exist_ok=True)
        tmp.write_bytes(out)
        os.chmod(tmp, stat.S_IMODE(md_path.stat().st_mode))
        os.replace(tmp, md_path)
    return res
