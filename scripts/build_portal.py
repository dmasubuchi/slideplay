#!/usr/bin/env python3
"""Build the introduction portal of the GitHub Pages site from the READMEs.

    python3 scripts/build_portal.py            # write index.html and index.ja.html
    python3 scripts/build_portal.py --check    # exit 1 if either file is out of date (writes nothing)

index.html is built from README.md and index.ja.html from README.ja.md. Each page is a plain static HTML
page (no script, no external resource): a top block with links to the catalog and the three demo decks,
then every section of the README. Edit the READMEs (or the texts below), not the generated pages.

Python standard library only. The README is read with a small Markdown subset, which is all the READMEs
use: `#`/`##`/`###` headings, paragraphs, `-` lists (nested by two spaces), fenced code blocks, `code`
spans, [links](url) and <https://autolinks>. Anything else (a table, a quote, a numbered list, bold text,
a list item that continues on the next line) stops the build with an error instead of being dropped.
"""
import html
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO_URL = "https://github.com/dmasubuchi/slideplay"

# Anchor ids of the README sections, keyed by heading text. A new heading needs an entry here.
SECTION_IDS = {
    "What it does": "what-it-does", "何ができるか": "what-it-does",
    "Quick start": "quick-start", "すぐ試す": "quick-start",
    "The deck format": "deck-format", "デッキの形": "deck-format",
    "Keys": "keys", "キー操作": "keys",
    "Motion, drawing, memo and PDF": "motion-drawing-memo-pdf", "動き・書き込み・メモ・PDF": "motion-drawing-memo-pdf",
    "Editor (Markdown drafts)": "editor", "Editor（Markdown の下書き）": "editor",
    "`?render`": "render",
    "Tests": "tests", "試験": "tests",
    "Browser support": "browser-support", "対応ブラウザ": "browser-support",
    "Folder layout": "folder-layout", "フォルダの形": "folder-layout",
    "License": "license", "ライセンス": "license",
}

PAGES = {
    "en": {
        "lang": "en", "readme": "README.md", "out": "index.html", "catalog": "catalog.html",
        "title": "slideplay: a single-file HTML slide player",
        "description": "slideplay is a dependency-free, single-file HTML slide player. Demo decks, a slide catalog and the README.",
        "tagline": "A single-file HTML slide player. No dependencies, no build step; works from file://.",
        "cta": "Open the slide catalog",
        "repo": "GitHub repository",
        "switch": {"label": "日本語", "href": "index.ja.html", "lang": "ja"},
        "eyebrow": "Decks about slideplay, made with slideplay",
        "decks": [
            ("intro", "Intro", "Introducing slideplay", "What it is, the deck format and how to use it."),
            ("chic", "Chic", "slideplay, quietly", "The subtle motion style: a few words per slide."),
            ("bounce", "Bounce", "slideplay by the numbers", "The bounce motion style: numbers counted from this repository count up."),
        ],
        "hint": "In a deck, press Down or Space to go forward, ? for the key list and H to return to the catalog. The player's own labels are in Japanese for now.",
        "toc": "On this page",
        "readme_note": "Below is README.md, as HTML.",
    },
    "ja": {
        "lang": "ja", "readme": "README.ja.md", "out": "index.ja.html", "catalog": "catalog.ja.html",
        "title": "slideplay：1ファイルの HTML スライドプレイヤー",
        "description": "slideplay は、1ファイル・依存なしの HTML スライドプレイヤー。紹介のデッキ、スライドの目次、README。",
        "tagline": "1ファイルの HTML スライドプレイヤー。依存なし・ビルドなし・file:// で動く。",
        "cta": "スライドの目次を開く",
        "repo": "GitHub のリポジトリ",
        "switch": {"label": "English", "href": "index.html", "lang": "en"},
        "eyebrow": "slideplay で作った、slideplay の紹介のデッキ",
        "decks": [
            ("intro", "紹介", "slideplay の紹介", "何ができるか、デッキの形、使い方。"),
            ("chic", "シック", "slideplay、静かに", "控えめ型の動き。1枚に少ない言葉。"),
            ("bounce", "バウンス", "slideplay を数字で見る", "弾む型の動き。このリポジトリから数えた数字が数え上がる。"),
        ],
        "hint": "デッキの中では、↓ か Space で進み、? で操作の一覧、H で目次に戻る。",
        "toc": "このページの内容",
        "readme_note": "以下は README.ja.md の内容。",
    },
}

CSS = """\
:root {
  color-scheme: light dark;
  --bg: #ffffff; --fg: #1d2733; --muted: #4f5d6b; --line: #d9dee4; --card: #f4f6f8; --code: #eef1f4;
  --link: #0a5eb5; --btn-bg: #0b6bcb; --btn-fg: #ffffff;
  --intro: #0e7c66; --chic: #3a4a63; --bounce: #b83c0a;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #10151b; --fg: #e7ebef; --muted: #a4b0bc; --line: #2a3340; --card: #171e26; --code: #1c242d;
    --link: #7bb8ff; --btn-bg: #7bb8ff; --btn-fg: #0b1520;
    --intro: #3fc7a5; --chic: #9bb0d3; --bounce: #ff9a62;
  }
}
* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; text-size-adjust: 100%; }
body {
  margin: 0; background: var(--bg); color: var(--fg);
  font: 16px/1.65 system-ui, -apple-system, "Segoe UI", "Hiragino Sans", "Yu Gothic", "Noto Sans CJK JP", sans-serif;
}
.wrap { max-width: 50rem; margin: 0 auto; padding: 0 16px 56px; }
a { color: var(--link); }
:focus-visible { outline: 3px solid var(--link); outline-offset: 2px; }
.hero { padding: 28px 0 4px; }
.titlebar { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
h1 { margin: 0; font-size: clamp(2.2rem, 9vw, 3.2rem); line-height: 1.1; letter-spacing: -0.02em; }
.lang a { display: inline-block; padding: 6px 14px; border: 1px solid var(--line); border-radius: 999px;
  color: var(--fg); text-decoration: none; font-size: 0.95rem; }
.tagline { margin: 10px 0 20px; font-size: 1.15rem; color: var(--muted); }
.cta { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; margin: 0; }
.button { display: inline-block; padding: 13px 22px; border-radius: 10px; background: var(--btn-bg); color: var(--btn-fg);
  font-weight: 600; font-size: 1.05rem; text-decoration: none; }
.ghost { display: inline-block; padding: 12px 18px; border: 1px solid var(--line); border-radius: 10px;
  color: var(--fg); text-decoration: none; }
.eyebrow { margin: 30px 0 10px; color: var(--muted); font-size: 0.85rem; letter-spacing: 0.03em; }
.decks { list-style: none; margin: 0; padding: 0; display: grid; gap: 12px;
  grid-template-columns: repeat(auto-fit, minmax(14rem, 1fr)); }
.decks li { margin: 0; }
.decks a { display: block; height: 100%; padding: 14px 16px; border: 1px solid var(--line); border-top: 4px solid var(--deck);
  border-radius: 10px; background: var(--card); color: var(--fg); text-decoration: none; }
.decks a:hover { border-color: var(--deck); }
.deck-intro { --deck: var(--intro); } .deck-chic { --deck: var(--chic); } .deck-bounce { --deck: var(--bounce); }
.decks .kind { display: block; font-size: 0.8rem; font-weight: 700; color: var(--deck); }
.decks strong { display: block; margin: 2px 0 4px; font-size: 1.05rem; line-height: 1.35; }
.decks .line { display: block; color: var(--muted); font-size: 0.95rem; line-height: 1.5; }
.hint { margin: 14px 0 0; color: var(--muted); font-size: 0.9rem; }
.toc { margin: 28px 0 0; padding: 14px 0; border-top: 1px solid var(--line); }
.toc p:first-child { margin: 0; font-weight: 600; font-size: 0.9rem; }
.toc ul { list-style: none; display: flex; flex-wrap: wrap; gap: 4px 16px; margin: 6px 0 0; padding: 0; }
.toc li { margin: 0; }
.readme-note { margin: 12px 0 0; color: var(--muted); font-size: 0.9rem; }
main { margin-top: 8px; }
main section { scroll-margin-top: 12px; }
main h2 { margin: 2.4rem 0 0.6rem; padding-top: 1.1rem; border-top: 1px solid var(--line); font-size: 1.5rem; line-height: 1.3; }
main p { margin: 0.8rem 0; }
main ul { margin: 0.6rem 0; padding-left: 1.4rem; }
main li { margin: 0.3rem 0; }
main li ul { margin: 0.3rem 0; }
code { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace; font-size: 0.88em;
  background: var(--code); padding: 0.1em 0.35em; border-radius: 5px; overflow-wrap: anywhere; }
pre { margin: 1rem 0; padding: 14px 16px; background: var(--code); border: 1px solid var(--line); border-radius: 10px;
  overflow-x: auto; font-size: 0.85rem; line-height: 1.5; tab-size: 2; }
pre code { padding: 0; background: none; font-size: inherit; overflow-wrap: normal; white-space: pre; }
"""

# ---- Markdown subset ----

INLINE = re.compile(
    r"(?P<tick>`+)(?P<code>.+?)(?P=tick)"
    r"|<(?P<auto>https?://[^>\s]+)>"
    r"|\[(?P<text>[^\]]+)\]\((?P<url>[^)\s]+)\)"
)
LIST_ITEM = re.compile(r"^( *)- (.*)$")
HEADING = re.compile(r"^(#{1,3}) (.+)$")


def esc(text):
    return html.escape(text, quote=False)


def link_target(url):
    """A page of this site stays relative; a file that is not a page (CONTRACT.md, LICENSE, a README) opens on GitHub."""
    if re.match(r"[a-z][a-z0-9+.-]*:", url):
        return url
    if url.split("#")[0].endswith(".html") and (ROOT / url.split("#")[0]).is_file():
        return url
    return f"{REPO_URL}/blob/main/{url}"


def inline(text):
    out, pos = [], 0
    for m in INLINE.finditer(text):
        out.append(esc(text[pos:m.start()]))
        if m.group("code") is not None:
            out.append(f"<code>{esc(m.group('code'))}</code>")
        elif m.group("auto") is not None:
            url = m.group("auto")
            out.append(f'<a href="{html.escape(url)}">{esc(url)}</a>')
        else:
            out.append(f'<a href="{html.escape(link_target(m.group("url")))}">{inline(m.group("text"))}</a>')
        pos = m.end()
    out.append(esc(text[pos:]))
    rest = "".join(out)
    for stray in ("**", "__", "~~"):
        if stray in re.sub(r"<code>.*?</code>", "", rest):
            raise ValueError(f"unsupported emphasis {stray!r} in: {text}")
    return rest


def starts_block(line):
    return bool(line.startswith("```") or HEADING.match(line) or LIST_ITEM.match(line))


def parse(md):
    """Markdown text -> blocks: ("h", level, text) | ("p", text) | ("ul", items) | ("code", lang, text).
    A list item is {"text": str, "children": [items]}."""
    lines = md.split("\n")
    blocks, i = [], 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
        elif line.startswith("```"):
            lang, body, i = line[3:].strip(), [], i + 1
            while i < len(lines) and not lines[i].startswith("```"):
                body.append(lines[i])
                i += 1
            if i >= len(lines):
                raise ValueError("a code fence is not closed")
            blocks.append(("code", lang, "\n".join(body)))
            i += 1
        elif HEADING.match(line):
            m = HEADING.match(line)
            blocks.append(("h", len(m.group(1)), m.group(2).strip()))
            i += 1
        elif LIST_ITEM.match(line):
            items, stack = [], []          # stack: (level, children list)
            while i < len(lines) and LIST_ITEM.match(lines[i]):
                m = LIST_ITEM.match(lines[i])
                indent = len(m.group(1))
                if indent % 2:
                    raise ValueError(f"list indent must be a multiple of 2: {lines[i]!r}")
                level = indent // 2
                if level > len(stack):
                    raise ValueError(f"list item nested too deep: {lines[i]!r}")
                del stack[level:]
                item = {"text": m.group(2), "children": []}
                (stack[-1][1]["children"] if stack else items).append(item)
                stack.append((level, item))
                i += 1
            if i < len(lines) and lines[i].strip():
                raise ValueError(f"a list item that continues on the next line is not supported: {lines[i]!r}")
            blocks.append(("ul", items))
        else:
            para = [line]
            i += 1
            while i < len(lines) and lines[i].strip() and not starts_block(lines[i]):
                para.append(lines[i])
                i += 1
            text = " ".join(s.strip() for s in para)
            if re.match(r"^(>|\||\d+[.)] |\* |\+ )", text) or text.startswith("<!--"):
                raise ValueError(f"unsupported Markdown block: {text[:60]!r}")
            blocks.append(("p", text))
    return blocks


def render_list(items):
    rows = []
    for item in items:
        if item["children"]:
            rows.append(f"<li>{inline(item['text'])}\n{render_list(item['children'])}</li>")
        else:
            rows.append(f"<li>{inline(item['text'])}</li>")
    return "<ul>\n" + "\n".join(rows) + "\n</ul>"


def render_block(block):
    kind = block[0]
    if kind == "p":
        return f"<p>{inline(block[1])}</p>"
    if kind == "ul":
        return render_list(block[1])
    if kind == "code":
        cls = f' class="language-{html.escape(block[1])}"' if block[1] else ""
        return f'<pre tabindex="0"><code{cls}>{esc(block[2])}</code></pre>'
    raise ValueError(f"cannot render {kind!r} here")


def split_readme(md):
    """-> (title, lead blocks, [(heading text, blocks)]). The language switch line and the Demo line at the top
    are not part of the portal (the top block of the page replaces them); anything else before the first ## is the lead."""
    blocks = parse(md)
    if not blocks or blocks[0][:2] != ("h", 1):
        raise ValueError("the README must start with a # title")
    title, lead, sections, skipped = blocks[0][2], [], [], 0
    for block in blocks[1:]:
        if block[0] == "h":
            if block[1] != 2:
                raise ValueError(f"only ## headings are supported as section titles: {block[2]!r}")
            sections.append((block[2], []))
        elif sections:
            sections[-1][1].append(block)
        elif block[0] == "p" and re.match(r"^(English \||\[English\]|Demo|デモ|\[日本語\])", block[1]):
            skipped += 1
        else:
            lead.append(block)
    if skipped != 2:
        raise ValueError(f"expected the language line and the Demo line before the first ##, skipped {skipped}")
    return title, lead, sections


# ---- Page ----

def build(lang):
    """The text of the portal page for lang ("en" or "ja")."""
    cfg = PAGES[lang]
    title, lead, sections = split_readme((ROOT / cfg["readme"]).read_text(encoding="utf-8"))
    ids = []
    for heading, _ in sections:
        if heading not in SECTION_IDS:
            raise ValueError(f"add an anchor id for the heading {heading!r} to SECTION_IDS in scripts/build_portal.py")
        ids.append(SECTION_IDS[heading])
    if len(set(ids)) != len(ids):
        raise ValueError("two sections have the same anchor id")
    other = PAGES["ja" if lang == "en" else "en"]
    sw = cfg["switch"]

    cards = "\n".join(
        f'<li><a class="deck-{deck}" href="demo/{lang}/{deck}.html"><span class="kind">{esc(kind)}</span>'
        f'<strong>{esc(name)}</strong><span class="line">{esc(line)}</span></a></li>'
        for deck, kind, name, line in cfg["decks"]
    )
    toc = "\n".join(f'<li><a href="#{i}">{inline(h)}</a></li>' for (h, _), i in zip(sections, ids))
    body_lead = "\n".join(render_block(b) for b in lead)
    body = "\n".join(
        f'<section id="{i}">\n<h2>{inline(h)}</h2>\n' + "\n".join(render_block(b) for b in blocks) + "\n</section>"
        for (h, blocks), i in zip(sections, ids)
    )
    return f"""<!doctype html>
<html lang="{cfg['lang']}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<meta name="description" content="{html.escape(cfg['description'])}">
<title>{esc(cfg['title'])}</title>
<link rel="icon" href="data:,">
<link rel="alternate" hreflang="{other['lang']}" href="{other['out']}">
<!-- Generated by scripts/build_portal.py from {cfg['readme']}. Do not edit by hand; edit the README and run the script. -->
<style>
{CSS}</style>
</head>
<body>
<div class="wrap">
<header class="hero">
<div class="titlebar">
<h1>{esc(title)}</h1>
<p class="lang"><a href="{sw['href']}" hreflang="{sw['lang']}" lang="{sw['lang']}">{esc(sw['label'])}</a></p>
</div>
<p class="tagline">{esc(cfg['tagline'])}</p>
<p class="cta"><a class="button" href="{cfg['catalog']}">{esc(cfg['cta'])}</a> <a class="ghost" href="{REPO_URL}">{esc(cfg['repo'])}</a></p>
<p class="eyebrow">{esc(cfg['eyebrow'])}</p>
<ul class="decks">
{cards}
</ul>
<p class="hint">{esc(cfg['hint'])}</p>
</header>
<nav class="toc" aria-label="{html.escape(cfg['toc'])}">
<p>{esc(cfg['toc'])}</p>
<ul>
{toc}
</ul>
<p class="readme-note">{esc(cfg['readme_note'])}</p>
</nav>
<main id="readme">
{body_lead}
{body}
</main>
</div>
</body>
</html>
"""


def main(argv):
    check = "--check" in argv
    stale = []
    for lang, cfg in PAGES.items():
        text, path = build(lang), ROOT / cfg["out"]
        if check:
            if not path.is_file() or path.read_text(encoding="utf-8") != text:
                stale.append(cfg["out"])
        else:
            path.write_text(text, encoding="utf-8")
            print(f"wrote {cfg['out']} from {cfg['readme']}")
    if stale:
        print("out of date (run python3 scripts/build_portal.py): " + ", ".join(stale), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
