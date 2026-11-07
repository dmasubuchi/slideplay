"""Markdown の下書きを、Editor が描くデッキの元（JSON になる dict）に変える。

行ごとに読む小さな状態機械：front-matter → ページ → ブロック。
文字の src は [行, 始め, 終わり]（行は1から、始め・終わりは改行を除いた行の中の位置）。
"""
import re
from pathlib import Path

TYPES = ("表紙", "ふつう", "二段", "図と文", "強調")
DEFAULT_TYPE = "ふつう"

ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
HEAD_RE = re.compile(r"^(#{1,2})[ \t]+(.*\S)")
H3_RE = re.compile(r"^###[ \t]+(.*\S)")
ITEM_RE = re.compile(r"^([ \t]*)([-*+])[ \t]+(.*\S)")
IMG_RE = re.compile(r"^!\[([^\]]*)\]\(([^)\s]+)[^)]*\)\s*$")
FENCE_RE = re.compile(r"^\s*(```|~~~)")
FM_RE = re.compile(r"^([^\s:#][^:]*):[ \t]*(.*)$")
# Marp の指示。これらのコメントはノートに出さない
DIRECTIVE_RE = re.compile(
    r"^_?(id|class|html|marp|paginate|theme|header|footer|style|color|"
    r"backgroundColor|backgroundImage|backgroundPosition|backgroundRepeat|backgroundSize|"
    r"size|headingDivider|lang|title|description|author|image|math)[ \t]*:[ \t]*(.*)$", re.S)


class ConvertError(Exception):
    def __init__(self, line, message):
        super().__init__(f"{line}行目：{message}")
        self.line = line
        self.message = message


def find_markdown(path):
    path = Path(path)
    if path.is_dir():
        found = sorted(p for p in path.iterdir() if p.is_file() and p.suffix == ".md")
        if not found:
            raise ValueError(f"{path} に .md がありません")
        if len(found) > 1:
            raise ValueError(f"{path} に .md が{len(found)}つあります。ファイルを指定してください")
        return found[0]
    if path.is_file() and path.suffix == ".md":
        return path
    raise ValueError(f"{path} がありません")


def _plain(text):
    """題名用に、飾り（**…**・==…==・++…++）を外す。"""
    return text.replace("**", "").replace("==", "").replace("++", "").strip()


def _new_slide(first):
    return {"id": None, "id_line": None, "type": DEFAULT_TYPE, "title": "", "steps": 0, "notes": [],
            "src": [first, first], "head": None, "blocks": [], "html": None, "auto_id": False}


def _front_matter(lines):
    """先頭の front-matter を読む。返すのは (キーと値, 本文の始まりの添字)。"""
    if not lines or lines[0].rstrip() != "---":
        return {}, 0
    meta = {}
    for i in range(1, len(lines)):
        if lines[i].rstrip() == "---":
            return meta, i + 1
        m = FM_RE.match(lines[i])
        if m:
            v = m.group(2).strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                v = v[1:-1]
            meta[m.group(1).strip()] = v
    raise ConvertError(1, "先頭の --- が閉じていません")


def convert(md_path, *, editing=False):
    md_path = Path(md_path)
    base = md_path.parent.resolve()
    text_all = md_path.read_bytes().decode("utf-8-sig")
    lines = re.split(r"\r\n|\n|\r", text_all)
    if lines and lines[-1] == "":
        lines.pop()
    meta, start = _front_matter(lines)

    warnings = []

    def warn(line, message):
        warnings.append({"line": line, "message": message})

    def inside(rel):
        """デッキのフォルダーの中に解決できれば、そのパス。外なら None。"""
        target = (base / rel).resolve()
        return target if target.is_relative_to(base) else None

    slides = []
    cur = None
    para = []          # 段落になる途中の行 [(行, 始め, 文字)]
    open_list = None   # 続いている箇条書きのブロック
    step = 0

    def flush_para():
        nonlocal para
        if para:
            line, a, _ = para[0]
            text = "\n".join(t for _, _, t in para)
            # lines は1行ごとの文字と位置（書き戻しはこちらを使う）
            per_line = [{"text": t, "src": [ln, st, st + len(t)]} for ln, st, t in para]
            cur["blocks"].append({"kind": "p", "text": text, "src": [line, a, a + len(para[0][2])],
                                  "lines": per_line})
            para = []

    def begin(n):
        nonlocal cur, para, open_list, step
        cur = _new_slide(n)
        para, open_list, step = [], None, 0

    def finish(last):
        nonlocal cur
        flush_para()
        if cur is not None and any(ln.strip() for ln in lines[cur["src"][0] - 1:last]):
            cur["src"][1] = last
            slides.append(cur)
        cur = None

    begin(start + 1)
    i = start
    n = len(lines)
    while i < n:
        no = i + 1
        line = lines[i]
        if FENCE_RE.match(line):
            flush_para()
            open_list = None
            fence = FENCE_RE.match(line).group(1)
            j = i + 1
            while j < n and not lines[j].lstrip().startswith(fence):
                j += 1
            last = min(j, n - 1)
            cur["blocks"].append({"kind": "pre", "text": "\n".join(lines[i + 1:j]), "src": [no, last + 1]})
            i = last + 1
            continue
        if line.rstrip() == "---":
            finish(no - 1)
            begin(no + 1)
            i += 1
            continue
        if line.lstrip().startswith("<!--"):
            flush_para()
            j = i
            while "-->" not in lines[j]:
                j += 1
                if j >= n:
                    raise ConvertError(no, "<!-- が閉じていません")
            body = "\n".join(lines[i:j + 1])
            inner = body[body.index("<!--") + 4:body.index("-->")].strip()
            d = DIRECTIVE_RE.match(inner)
            if not d:
                if inner:
                    cur["notes"].append(inner)
            else:
                key = inner.split(":", 1)[0].strip().lstrip("_")
                value = d.group(2).strip()
                if key == "id":
                    cur["id"], cur["id_line"] = value, no
                elif key == "class":
                    if value in TYPES:
                        cur["type"] = value
                    else:
                        cur["type"] = DEFAULT_TYPE
                        warn(no, f"型「{value}」はありません。{DEFAULT_TYPE}で描きます")
                elif key == "html":
                    target = inside(value)
                    if target is None:
                        warn(no, f"{value} はデッキのフォルダーの外なので使えません")
                    elif not target.is_file():
                        warn(no, f"{value} がありません")
                    else:
                        cur["html"] = target.read_text(encoding="utf-8")
            i = j + 1
            continue
        if not line.strip():
            flush_para()
            i += 1
            continue

        m = HEAD_RE.match(line)
        if m and cur["head"] is None:
            flush_para()
            open_list = None
            a = m.start(2)
            cur["head"] = {"text": m.group(2), "src": [no, a, a + len(m.group(2))]}
            cur["title"] = _plain(m.group(2))
            i += 1
            continue
        m = H3_RE.match(line)
        if m:
            flush_para()
            open_list = None
            a = m.start(1)
            cur["blocks"].append({"kind": "h3", "text": m.group(1), "src": [no, a, a + len(m.group(1))]})
            i += 1
            continue
        m = IMG_RE.match(line)
        if m:
            flush_para()
            open_list = None
            alt, path = m.group(1), m.group(2)
            block = {"kind": "img", "path": path, "alt": alt, "src": [no], "missing": False}
            target = inside(path)
            if target is None:
                block["missing"] = True
                warn(no, f"{path} はデッキのフォルダーの外なので使えません")
            elif not target.is_file():
                block["missing"] = True
                warn(no, f"{path} がありません")
            elif editing:
                block["v"] = target.stat().st_mtime_ns
            cur["blocks"].append(block)
            i += 1
            continue
        m = ITEM_RE.match(line)
        if m:
            flush_para()
            a = m.start(3)
            text = m.group(3)
            entry = {"text": text, "src": [no, a, a + len(text)]}
            if open_list is None:
                open_list = {"kind": "list", "items": []}
                cur["blocks"].append(open_list)
            if m.group(1) and open_list["items"]:
                open_list["items"][-1]["sub"].append(entry)
            else:
                if m.group(2) == "*":
                    step += 1
                    cur["steps"] = step
                open_list["items"].append({**entry, "step": step if m.group(2) == "*" else 0, "sub": []})
            i += 1
            continue
        open_list = None
        a = len(line) - len(line.lstrip())
        para.append((no, a, line.strip()))
        i += 1
    finish(n)

    if not slides:
        raise ConvertError(1, "ページがありません")

    seen = {}
    for s in slides:
        sid, id_line = s["id"], s.pop("id_line")
        if sid is None:
            continue
        if not ID_RE.match(sid):
            raise ConvertError(id_line, f"ID {sid} は使えません。英字で始め、英数字・-・_ だけにしてください")
        if sid in seen:
            raise ConvertError(id_line, f"ID {sid} が2つあります（{seen[sid]}行目と{id_line}行目）")
        seen[sid] = id_line
    # 仮の ID：明示された ID が先。使われていれば p2b、p2c … にずらす
    for k, s in enumerate(slides, 1):
        if s["id"] is None:
            s["auto_id"] = True   # ID を書いていないページ（書き戻しで ID を足す）
            sid = f"p{k}"
            for suffix in "bcdefghijklmnopqrstuvwxyz":
                if sid not in seen:
                    break
                sid = f"p{k}{suffix}"
            else:
                n = 2
                while f"p{k}b{n}" in seen:
                    n += 1
                sid = f"p{k}b{n}"
            s["id"] = sid
            seen[sid] = None
        if not s["title"]:
            s["title"] = s["id"]
        s["notes"] = "\n".join(s["notes"])

    first_title = slides[0]['title'] if slides[0]['head'] else ''
    info = {"id": meta["id"] if ID_RE.match(meta.get("id", "")) else "deck",
            "title": _plain(meta.get("title", "")) or first_title or md_path.stem}
    if meta.get("color"):
        info["color"] = meta["color"]
    return {"info": info, "slides": slides, "warnings": warnings}
