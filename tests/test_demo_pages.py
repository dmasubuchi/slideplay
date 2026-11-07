"""デモのページ（GitHub Pages で出す index.html・index.ja.html・demo/ の6つのデッキ）の試験。

見るのは次のこと：
- 目次（英語 index.html・日本語 index.ja.html）：リンク先がすべて実在する、デッキの id と中身の id が合う、
  meta の枚数が実際の枚数と合う、もう一方の言語の目次へのカードがある
- デッキ（demo/en・demo/ja の intro・chic・bounce）：lang、読み込みで console・ページの例外が出ない、
  ↓ で全部の段階を歩ける、舞台からはみ出さない、動きの型（chic は subtle、bounce は bounce）、home が実在する
- README.md（英語）と README.ja.md（日本語）が互いにリンクし、デモの URL と試験の準備の行を持つ。英語の README は、
  地の文を英語にしつつ、実装が受け付ける日本語の指定値（Editor のページの型）を載せる
- 紹介のデッキのノートにある Editor の停止コマンドが、path つきで書かれている（`slide-edit stop` は path が必須）

page_session は pageerror を見る。ここでは console の error・warning も集める。
"""
import re
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest

from helpers import page_session

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from editor.convert import DEFAULT_TYPE, TYPES  # noqa: E402
DEMO_URL = "https://dmasubuchi.github.io/slideplay/"
LANGS = ["en", "ja"]
DECKS = ["intro", "chic", "bounce"]
DECK_CASES = [(lang, deck) for lang in LANGS for deck in DECKS]
CATALOGS = [("index.html", "en", "index.ja.html"), ("index.ja.html", "ja", "index.html")]
EXPECTED_MOTION_ENTRY = {"intro": "bounce", "chic": "subtle", "bounce": "bounce"}

# 舞台（#stage）の中の要素が、舞台の外にはみ出していないか・自分の箱から溢れていないか
OVERFLOW_JS = """() => {
  const stage = document.getElementById('stage');
  const sr = stage.getBoundingClientRect();
  const bad = [];
  const name = e => e.tagName.toLowerCase() + Array.from(e.classList).map(c => '.' + c).join('');
  for (const e of stage.querySelectorAll('*')) {
    const r = e.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) continue;
    if (r.left < sr.left - 1 || r.top < sr.top - 1 || r.right > sr.right + 1 || r.bottom > sr.bottom + 1)
      bad.push('舞台の外: ' + name(e) + ' ' + [r.left, r.top, r.right, r.bottom].map(Math.round));
    if (getComputedStyle(e).display === 'inline') continue;
    if (e.scrollWidth > e.clientWidth + 1) bad.push('横に溢れる: ' + name(e) + ' ' + e.scrollWidth + '>' + e.clientWidth);
    // .kicker は render.js の見出し上の行（高さ 40px 固定）。日本語フォントの行が 48px になるだけで、見た目は切れない
    if (!e.classList.contains('kicker') && e.scrollHeight > e.clientHeight + 1) bad.push('縦に溢れる: ' + name(e) + ' ' + e.scrollHeight + '>' + e.clientHeight);
  }
  const h = stage.querySelector('h1, h2');
  if (h) {
    const lines = Math.round(h.getBoundingClientRect().height / parseFloat(getComputedStyle(h).lineHeight));
    if (lines > 1) bad.push('題名が' + lines + '行に折り返す: ' + h.textContent);
  }
  return bad;
}"""


@contextmanager
def recorded_page(browser, url, viewport=(1920, 1080)):
    """url を開く。ページの例外（page_session）に加えて、console の error・warning と、読み込みに失敗した要求を page.sp_console に集める。"""
    with page_session(browser, "about:blank", viewport=viewport) as page:
        page.sp_console = []
        page.on("console", lambda m: page.sp_console.append(f"{m.type}: {m.text}") if m.type in ("error", "warning") else None)
        page.on("requestfailed", lambda r: page.sp_console.append(f"requestfailed: {r.url}"))
        page.goto(url)
        page.wait_for_function("!!window.__sp")
        yield page
        assert page.sp_console == []


def read_catalog(page):
    return page.evaluate("window.slideCatalog")


def deck_path(lang, deck):
    return REPO / "demo" / lang / f"{deck}.html"


# ---- 目次 ----

@pytest.mark.parametrize("name,lang,other", CATALOGS)
def test_catalog_links_exist_and_ids_match(browser, name, lang, other):
    with recorded_page(browser, (REPO / name).as_uri()) as page:
        assert page.evaluate("document.documentElement.lang") == lang
        catalog = read_catalog(page)
        ids = [d["id"] for d in catalog["decks"]]
        assert len(ids) == len(set(ids)), "目次の id が重なっている"
        assert page.evaluate("document.querySelectorAll('.sp-card').length") == len(ids)
        for d in catalog["decks"]:
            target = (REPO / d["href"]).resolve()
            assert target.is_file(), f"{name}: {d['id']} のリンク先がない: {d['href']}"
            assert REPO in target.parents
        # 3つの紹介のデッキが、その言語の demo/ を指す
        by_id = {d["id"]: d for d in catalog["decks"]}
        for deck in DECKS:
            assert by_id[deck]["href"] == f"demo/{lang}/{deck}.html" and by_id[deck].get("kind", "deck") == "deck"
        # もう一方の言語の目次へのカード
        link = [d for d in catalog["decks"] if d.get("kind") == "page" and d["href"] == other]
        assert len(link) == 1


@pytest.mark.parametrize("name,lang,other", CATALOGS)
def test_catalog_meta_counts_and_deck_ids(browser, name, lang, other):
    """meta の最初の数（枚数）が、デッキの実際の枚数と合う。目次の id がデッキの info.id と合う。"""
    with recorded_page(browser, (REPO / name).as_uri()) as page:
        catalog = read_catalog(page)
    checked = 0
    for d in catalog["decks"]:
        if d.get("kind") == "page":
            continue
        with recorded_page(browser, (REPO / d["href"]).as_uri()) as deck_page:
            info = deck_page.evaluate("window.slideDeck.info")
        assert info["id"] == d["id"], f"{d['href']}: 目次の id {d['id']} と info.id {info['id']} が違う"
        count = int(re.match(r"\d+", d["meta"]).group())
        assert count == len(info["slides"]), f"{d['id']}: meta {d['meta']!r} と実際の枚数 {len(info['slides'])}"
        checked += 1
    assert checked == 6


# ---- デッキ ----

@pytest.mark.parametrize("lang,deck", DECK_CASES)
def test_deck_loads_and_walks(browser, lang, deck):
    """読み込みで console・ページの例外が出ない。↓ と Space で全部の位置を順に歩ける。舞台からはみ出さない。H で目次へ戻る。"""
    with recorded_page(browser, deck_path(lang, deck).as_uri()) as page:
        assert page.evaluate("document.documentElement.lang") == lang
        info = page.evaluate("window.slideDeck.info")
        assert info["id"] == deck
        assert info["motion"]["entry"] == EXPECTED_MOTION_ENTRY[deck]
        home = (deck_path(lang, deck).parent / info["home"]).resolve()
        assert home == (REPO / ("index.html" if lang == "en" else "index.ja.html")).resolve()
        assert 6 <= len(info["slides"]) <= 12
        for s in info["slides"]:
            assert s["notes"], f"{s['id']}: ノートがない"
        expected = [(s["id"], t) for s in info["slides"] for t in range(s["steps"] + 1)]
        seen = []
        for k in range(len(expected)):
            state = page.evaluate("__sp.state()")
            seen.append((state["id"], state["step"]))
            problems = page.evaluate(OVERFLOW_JS)
            assert not problems, f"{lang}/{deck} {state['id']}.{state['step']}: {problems}"
            if k < len(expected) - 1:
                page.keyboard.press("ArrowDown" if k % 2 == 0 else "Space")
                page.wait_for_function(f"(() => {{ const s = __sp.state(); return s.id !== {state['id']!r} || s.step !== {state['step']} }})()")
        assert seen == expected
        # H：その言語の目次を、このデッキを選んだ状態で開く
        with page.expect_navigation():
            page.keyboard.press("h")
        assert page.url.split("#")[0] == home.as_uri()
        assert page.url.endswith("#" + deck)


@pytest.mark.parametrize("lang,deck", DECK_CASES)
def test_deck_links_are_valid(browser, lang, deck):
    """スライドの links：jump の行き先がデッキにある。external は https。copy は text を持つ。"""
    with recorded_page(browser, deck_path(lang, deck).as_uri()) as page:
        info = page.evaluate("window.slideDeck.info")
    ids = {s["id"] for s in info["slides"]}
    for s in info["slides"]:
        for link in s["links"]:
            if link["kind"] == "jump":
                assert link["target"] in ids
            elif link["kind"] == "external":
                assert link["target"].startswith("https://")
            elif link["kind"] == "copy":
                assert link["text"]


# ---- README ----

def test_readmes_link_each_other_and_keep_key_lines():
    en = (REPO / "README.md").read_text(encoding="utf-8")
    ja = (REPO / "README.ja.md").read_text(encoding="utf-8")
    head_en, head_ja = en[:400], ja[:400]
    assert "(README.ja.md)" in head_en and "(README.md)" in head_ja
    for text in (en, ja):
        assert DEMO_URL in text
        assert "python3 -m playwright install chromium" in text
        assert "index.ja.html" in text and "demo/" in text
    assert "Japanese" in en and "CONTRACT.md" in en


def test_readme_keeps_english_prose_and_exact_editor_literals():
    """英語の README の地の文は英語。日本語が出てよいのは、実装が受け付ける指定値・ファイル名・日本語版への案内だけ。"""
    en = (REPO / "README.md").read_text(encoding="utf-8")
    # Editor のページの型：実装が受け付ける文字を、そのまま載せる（英語の名前では受け付けない）
    for name in TYPES:
        assert f"`{name}`" in en, f"README.md に型 {name} がない"
    assert "<!-- _class: 表紙 -->" in en
    assert f"`{DEFAULT_TYPE}`" in en and "default" in en
    # 許す日本語：型の名前、見本・書き出しのファイル名、日本語版への案内
    allowed = [*TYPES, "下書き.md", "-メモ.md", "日本語"]
    stripped = en
    for literal in allowed:
        stripped = stripped.replace(literal, "")
    leftover = re.findall(r"[^\n]*[\u3040-\u30ff\u4e00-\u9fff][^\n]*", stripped)
    assert leftover == [], f"英語の README に、許していない日本語がある: {leftover}"


@pytest.mark.parametrize("lang", LANGS)
def test_intro_editor_commands_have_a_path(lang):
    """slide-edit の open・stop は、どちらも path が必須。ノートの案内がそのまま実行できる。"""
    text = deck_path(lang, "intro").read_text(encoding="utf-8")
    assert "scripts/slide-edit open examples/editor" in text
    assert "scripts/slide-edit stop examples/editor" in text
    assert re.search(r"slide-edit (open|stop)(?! examples/editor)", text) is None
