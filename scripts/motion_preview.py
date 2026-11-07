"""動きの確認の見本づくり。

デッキの HTML を写し、player.js を読む直前に window.slideDeck.info.motion の上書きを入れる。
元のデッキのファイルは書き換えない。
"""
import json
from html.parser import HTMLParser

# script の type に書ける JavaScript の MIME（HTML の仕様の一覧）
JS_MIME_TYPES = {
    "application/ecmascript", "application/javascript", "application/x-ecmascript", "application/x-javascript",
    "text/ecmascript", "text/javascript", "text/javascript1.0", "text/javascript1.1", "text/javascript1.2", "text/javascript1.3",
    "text/javascript1.4", "text/javascript1.5", "text/jscript", "text/livescript", "text/x-ecmascript", "text/x-javascript",
}


def _runs_js(type_attr) -> bool:
    """script の type が JavaScript として実行されるものか（ない・空・JavaScript の MIME・module）。"""
    t = (type_attr or "").strip().lower()
    return t in ("", "module") or t in JS_MIME_TYPES


class _Places(HTMLParser):
    """本物の要素だけを見て、<head> の開きタグの終わりと、player.js を読む最初の <script> の始まりを、文字の位置で覚える。

    HTML のコメントと、script の中の文字（'<script src=…>' という文字列など）はタグとして扱われないので、選ばれない。
    type が JavaScript でない script（text/plain など。実行されない）も選ばない。
    """

    def __init__(self, html: str):
        super().__init__(convert_charrefs=True)
        self.line_starts = [0]
        for i, ch in enumerate(html):
            if ch == "\n":
                self.line_starts.append(i + 1)
        self.head_end = None
        self.player_at = None
        self.feed(html)
        self.close()

    def _here(self) -> int:
        line, col = self.getpos()
        return self.line_starts[line - 1] + col

    def handle_starttag(self, tag, attrs):
        if tag == "head" and self.head_end is None:
            self.head_end = self._here() + len(self.get_starttag_text())
        if tag == "script" and self.player_at is None:
            a = dict(attrs)
            src = a.get("src") or ""
            if _runs_js(a.get("type")) and src.split("?")[0].split("#")[0].rsplit("/", 1)[-1] == "player.js":
                self.player_at = self._here()


def inject_motion(html: str, base_href: str | None, motion: dict | None) -> str:
    """html に、<base href>（base_href があれば <head> の先頭）と、player.js の直前の motion の上書きを入れて返す。

    motion が None なら上書きは入れない。player.js を読む本物の script がなければ ValueError。
    """
    places = _Places(html)
    if places.player_at is None:
        raise ValueError("player.js を読む <script> が見つかりません")
    if base_href and places.head_end is None:
        raise ValueError("<head> が見つかりません")
    # 後ろの位置から入れる（前に入れると、後ろの位置がずれる）
    inserts = []
    if motion is not None:
        # JSON は < を含まないように書く（</script> で script が途切れないように）
        data = json.dumps(motion, ensure_ascii=False).replace("<", "\\u003c")
        inserts.append((places.player_at, f"<script>window.slideDeck.info.motion = {data};</script>\n"))
    if base_href:
        inserts.append((places.head_end, f'\n<base href="{base_href}">'))
    for at, text in sorted(inserts, reverse=True):
        html = html[:at] + text + html[at:]
    return html


ENTRY_LABELS = {"subtle": "控えめ型", "bounce": "弾む型"}


def parse_choice(text: str) -> dict:
    """「none」か、send・entry=subtle|bounce・point を , でつないだもの → info.motion。書いていない層は選ばない。読めなければ ValueError。"""
    if text.strip() == "none":
        return {"send": False, "entry": None, "point": False}
    motion = {"send": False, "entry": None, "point": False}
    for part in (p.strip() for p in text.split(",")):
        if part == "send":
            motion["send"] = True
        elif part == "point":
            motion["point"] = True
        elif part.startswith("entry=") and part[len("entry="):] in ENTRY_LABELS:
            motion["entry"] = part[len("entry="):]
        else:
            raise ValueError(f"組み合わせの「{part}」が読めません（none、または send・entry=subtle|bounce・point を , でつなぐ）")
    return motion


def describe(motion: dict) -> str:
    """見出しに出す組み合わせの名前（例：送り・入場（弾む型）・指す）。"""
    names = (["送り"] if motion["send"] else []) + ([f"入場（{ENTRY_LABELS[motion['entry']]}）"] if motion["entry"] else []) \
        + (["指す"] if motion["point"] else [])
    return "・".join(names) or "なし"


COMPARE = """<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>動きの見本：{title}</title>
<style>
body {{ margin: 0; padding: 16px; background: #14181d; color: #e8ecf1; font: 15px/1.5 "Hiragino Sans", "Yu Gothic UI", sans-serif; }}
.cols {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
h2 {{ margin: 0 0 6px; font-size: 16px; }}
iframe {{ width: 100%; aspect-ratio: 16 / 9; border: 0; border-radius: 6px; background: #000; }}
p {{ margin: 10px 0 0; color: #aab4c0; }}
</style>
</head>
<body>
<div class="cols">
  <div><h2>動きなし</h2><iframe src="none.html" title="動きなし"></iframe></div>
  <div><h2>勧める組み合わせ：{choice}</h2><iframe src="choice.html" title="勧める組み合わせ"></iframe></div>
</div>
<p>見本の中を押してから、↓ で次へ進めてください。2つは別々に動きます。</p>
</body>
</html>
"""


def main(argv=None) -> int:
    import argparse
    import html as html_lib
    import sys
    from pathlib import Path

    ap = argparse.ArgumentParser(description="動きの確認の見本（動きなし／勧める組み合わせ）を作る")
    ap.add_argument("deck", type=Path, help="デッキの HTML（player.js を読むもの）")
    ap.add_argument("--choice", required=True, help="none、または send・entry=subtle|bounce・point を , でつないだもの")
    ap.add_argument("--out", required=True, type=Path, help="見本を書くフォルダー（元のデッキのフォルダーは不可）")
    args = ap.parse_args(argv)
    try:
        motion = parse_choice(args.choice)
        deck = args.deck.resolve()
        out = args.out.resolve()
        if out == deck.parent or deck.parent in out.parents:
            raise ValueError("見本は、元のデッキのフォルダーの外に書いてください")
        source = deck.read_text(encoding="utf-8")
        base = deck.parent.as_uri() + "/"
        pages = {"none.html": inject_motion(source, base, parse_choice("none")), "choice.html": inject_motion(source, base, motion)}
    except (ValueError, OSError) as e:
        print(f"motion_preview: {e}", file=sys.stderr)
        return 2
    out.mkdir(parents=True, exist_ok=True)
    for name, text in pages.items():
        (out / name).write_text(text, encoding="utf-8")
    (out / "compare.html").write_text(COMPARE.format(title=html_lib.escape(deck.stem), choice=html_lib.escape(describe(motion))), encoding="utf-8")
    print(out / "compare.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
