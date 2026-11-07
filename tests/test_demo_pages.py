"""デモのページ（GitHub Pages で出す紹介のページ index.html・index.ja.html、目次 catalog.html・catalog.ja.html、demo/ の6つのデッキ）の試験。

見るのは次のこと：
- 紹介のページ（英語 index.html・日本語 index.ja.html。README から scripts/build_portal.py で作る静的な HTML）：
  console の error・warning なし、外部の資源なし、一番上に目次と3つのデッキへのリンク（と言語の切り替え）がある、
  相対リンクがすべて実在する、スマホの幅（390px）で横にはみ出さず左右に16pxの余白がある、明るい・暗いの両方で読める、
  README の `##` の節がそのまま並ぶ、README の書き方を変えて作り直し忘れると失敗する（コミットした HTML ＝ 作り直した HTML）
- 目次（英語 catalog.html・日本語 catalog.ja.html）：リンク先がすべて実在する、デッキの id と中身の id が合う、
  meta の枚数が実際の枚数と合う、もう一方の言語の目次・紹介のページへのカードがある
- デッキ（demo/en・demo/ja の intro・chic・bounce）：lang、読み込みで console・ページの例外が出ない、
  ↓ で全部の段階を歩ける、舞台からはみ出さない、動きの型（chic は subtle、bounce は bounce）、home が目次を指す
- README.md（英語）と README.ja.md（日本語）が互いにリンクし、デモの URL と試験の準備の行を持つ。英語の README は、
  地の文を英語にしつつ、実装が受け付ける日本語の指定値（Editor のページの型）を載せる
- 紹介のデッキのノートにある Editor の停止コマンドが、path つきで書かれている（`slide-edit stop` は path が必須）

page_session は pageerror を見る。ここでは console の error・warning も集める。
"""
import html
import re
import subprocess
import sys
from contextlib import contextmanager
from html.parser import HTMLParser
from pathlib import Path

import pytest

from helpers import page_session

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

import build_portal  # noqa: E402
from editor.convert import DEFAULT_TYPE, TYPES  # noqa: E402
DEMO_URL = "https://dmasubuchi.github.io/slideplay/"
REPO_URL = "https://github.com/dmasubuchi/slideplay"
LANGS = ["en", "ja"]
DECKS = ["intro", "chic", "bounce"]
DECK_CASES = [(lang, deck) for lang in LANGS for deck in DECKS]
# (ファイル名, 言語, もう一方の言語の同じページ, 紹介のページ)
CATALOGS = [("catalog.html", "en", "catalog.ja.html", "index.html"), ("catalog.ja.html", "ja", "catalog.html", "index.ja.html")]
# (ファイル名, 言語, もう一方の言語の同じページ, 元の README, その言語の目次)
PORTALS = [("index.html", "en", "index.ja.html", "README.md", "catalog.html"),
           ("index.ja.html", "ja", "index.html", "README.ja.md", "catalog.ja.html")]
CATALOG_OF = {"en": "catalog.html", "ja": "catalog.ja.html"}
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
def recorded_page(browser, url, viewport=(1920, 1080), player=True, color_scheme=None):
    """url を開く。ページの例外（page_session）に加えて、console の error・warning と、読み込みに失敗した要求を page.sp_console に集める。
    player=True は、プレイヤーが起動する（window.__sp）まで待つ。紹介のページはプレイヤーを読まないので player=False。"""
    with page_session(browser, "about:blank", viewport=viewport) as page:
        page.sp_console = []
        page.on("console", lambda m: page.sp_console.append(f"{m.type}: {m.text}") if m.type in ("error", "warning") else None)
        page.on("requestfailed", lambda r: page.sp_console.append(f"requestfailed: {r.url}"))
        if color_scheme:
            page.emulate_media(color_scheme=color_scheme)
        page.goto(url)
        if player:
            page.wait_for_function("!!window.__sp")
        else:
            page.wait_for_load_state("load")
        yield page
        assert page.sp_console == []


def read_catalog(page):
    return page.evaluate("window.slideCatalog")


def deck_path(lang, deck):
    return REPO / "demo" / lang / f"{deck}.html"


# ---- 目次 ----

@pytest.mark.parametrize("name,lang,other,about", CATALOGS)
def test_catalog_links_exist_and_ids_match(browser, name, lang, other, about):
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
        # もう一方の言語の目次へのカードと、紹介のページへのカード（目次から行き止まりにならない）
        for target in (other, about):
            link = [d for d in catalog["decks"] if d.get("kind") == "page" and d["href"] == target]
            assert len(link) == 1, f"{name}: {target} へのカードがない"


@pytest.mark.parametrize("name,lang,other,about", CATALOGS)
def test_catalog_meta_counts_and_deck_ids(browser, name, lang, other, about):
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
        assert home == (REPO / CATALOG_OF[lang]).resolve(), "H はその言語の目次（catalog）へ戻る（紹介のページではない）"
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
        # H：その言語の目次（catalog）を、このデッキを選んだ状態で開く
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
        # 紹介のページ（トップ）と目次の URL。目次は catalog
        assert DEMO_URL + "catalog.html" in text and DEMO_URL + "catalog.ja.html" in text
        # フォルダの形に、紹介のページ・目次・作る道具が載っている
        for name in ("index.html", "index.ja.html", "catalog.html", "catalog.ja.html", "scripts/build_portal.py"):
            assert re.search(rf"^{re.escape(name)}\s", text, re.M), f"フォルダの形に {name} がない"
    assert "Demo and introduction: <" + DEMO_URL + ">" in en
    assert "デモと紹介：<" + DEMO_URL + ">" in ja
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


# ---- 紹介のページ（index.html・index.ja.html。README から scripts/build_portal.py で作る） ----

class Refs(HTMLParser):
    """HTML の中の href・src・id・見出し・script/style の有無を集める。"""

    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.refs, self.ids, self.tags, self.h2, self.links = [], [], [], [], []
        self._h2 = None
        self._a = None
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self.tags.append((tag, a))
        if a.get("id"):
            self.ids.append(a["id"])
        for key in ("href", "src"):
            if key in a:
                self.refs.append((tag, key, a[key], a))
        if tag == "h2":
            self._h2 = []
        if tag == "a":
            self._a = [a.get("href"), []]

    def handle_endtag(self, tag):
        if tag == "h2" and self._h2 is not None:
            self.h2.append("".join(self._h2))
            self._h2 = None
        if tag == "a" and self._a is not None:
            self.links.append((self._a[0], "".join(self._a[1])))
            self._a = None

    def handle_data(self, data):
        if self._h2 is not None:
            self._h2.append(data)
        if self._a is not None:
            self._a[1].append(data)


def read(name):
    return (REPO / name).read_text(encoding="utf-8")


def readme_parts(name):
    """README の（## の題の一覧, コードブロックの本文の一覧, コードブロックを除いた本文）。題の `…` は外す。"""
    text = read(name)
    blocks = re.findall(r"^```[^\n]*\n(.*?)\n```$", text, re.M | re.S)
    prose = re.sub(r"^```[^\n]*\n.*?\n```$", "", text, flags=re.M | re.S)
    titles = [t.replace("`", "") for t in re.findall(r"^## (.+)$", prose, re.M)]
    return titles, blocks, prose


@pytest.mark.parametrize("name,lang,other,readme,catalog", PORTALS)
def test_portal_loads_cleanly_without_external_resources(browser, name, lang, other, readme, catalog):
    """読み込みで console・ページの例外・失敗した要求が出ない。script も外部の資源もない静的なページ（file:// で開ける）。"""
    text = read(name)
    refs = Refs(text)
    tags = {t for t, _ in refs.tags}
    assert not tags & {"script", "iframe", "img", "video", "audio", "source", "object", "embed"}, tags
    for tag, key, value, attrs in refs.refs:
        if tag == "a":
            continue                                   # 移動のリンク（資源ではない）
        # <link>：アイコン（data:）と、もう一方の言語の同じページ（rel="alternate"）だけ
        assert tag == "link" and (value.startswith("data:") or (attrs.get("rel") == "alternate" and value == other)), (tag, key, value)
    assert not re.search(r"@import|url\(|<link[^>]+stylesheet", text), "CSS は <style> に書き、外部の資源は読まない"
    with recorded_page(browser, (REPO / name).as_uri(), viewport=(1280, 800), player=False) as page:
        assert page.evaluate("document.documentElement.lang") == lang
        assert page.evaluate("document.scripts.length") == 0
        assert page.evaluate("performance.getEntriesByType('resource').length") == 0
        assert page.evaluate("document.querySelectorAll('h1').length") == 1
        assert page.inner_text("h1") == "slideplay"
        assert page.evaluate("!!document.querySelector('meta[name=viewport]')")
        assert page.evaluate("getComputedStyle(document.body).fontFamily").count("system-ui") == 1, "外部のフォントを読まず、システムの書体を使う"


@pytest.mark.parametrize("name,lang,other,readme,catalog", PORTALS)
def test_portal_top_links(browser, name, lang, other, readme, catalog):
    """一番上のブロック：言語の切り替え・目次・GitHub・3つのデッキへのリンクが、この順で最初に並ぶ。どれも開ける。"""
    expected = [other, catalog, REPO_URL, *[f"demo/{lang}/{d}.html" for d in DECKS]]
    with recorded_page(browser, (REPO / name).as_uri(), viewport=(1280, 800), player=False) as page:
        first = page.eval_on_selector_all("a", "els => els.slice(0, 6).map(e => e.getAttribute('href'))")
        assert first == expected
        assert page.eval_on_selector_all("header.hero a", "els => els.map(e => e.getAttribute('href'))") == expected
        # 目次のボタンは「目次を開く」、言語の切り替えは相手の言語の名前
        assert page.inner_text("a.button") == {"en": "Open the slide catalog", "ja": "スライドの目次を開く"}[lang]
        assert page.inner_text(".lang a") == {"en": "日本語", "ja": "English"}[lang]
        assert page.get_attribute(".lang a", "lang") == other_lang(lang)
        cards = page.eval_on_selector_all(".decks a", "els => els.map(e => [e.querySelector('.kind').textContent, e.querySelector('strong').textContent, e.querySelector('.line').textContent])")
    assert len(cards) == len(DECKS) and all(c[2].strip() for c in cards), "デッキのカードが3つあり、どれにも1行の説明がある"
    # カードの種類（label）と題名が、デッキ自身の info と同じ
    for deck, (kind, title, _) in zip(DECKS, cards):
        with recorded_page(browser, (REPO / f"demo/{lang}/{deck}.html").as_uri()) as deck_page:
            info = deck_page.evaluate("window.slideDeck.info")
        assert (kind, title) == (info["label"], info["title"])
    # リンク先は実在し、開ける。目次は目次、デッキはそのデッキ、言語の切り替えは相手の紹介のページ
    for href in expected:
        if href.startswith("https://"):
            continue
        assert (REPO / href).is_file(), href
    with recorded_page(browser, (REPO / catalog).as_uri()) as page:
        assert page.evaluate("__sp.state()")["kind"] == "catalog"
    with recorded_page(browser, (REPO / other).as_uri(), player=False) as page:
        assert page.inner_text("h1") == "slideplay" and page.evaluate("document.documentElement.lang") == other_lang(lang)


def other_lang(lang):
    return "ja" if lang == "en" else "en"


@pytest.mark.parametrize("name,lang,other,readme,catalog", PORTALS)
def test_portal_click_through(browser, name, lang, other, readme, catalog):
    """実際にクリックして移れる：目次ボタン → 目次、カード → デッキ、言語の切り替え → もう一方の紹介のページ。目次の「紹介」カードで戻れる。"""
    url = (REPO / name).as_uri()
    with recorded_page(browser, url, viewport=(1280, 800), player=False) as page:
        with page.expect_navigation():
            page.click("a.button")
        page.wait_for_function("!!window.__sp")
        assert page.url.split("#")[0] == (REPO / catalog).as_uri() and page.evaluate("__sp.state()")["kind"] == "catalog"
        # 目次の「紹介」カードを開くと、この紹介のページに戻る（カードは目次の中にあり、番号キーでも開ける）
        index = page.evaluate("slideCatalog.decks.findIndex(d => d.href === %r)" % name)
        assert index >= 0
        page.keyboard.press(str(index + 1))
        page.wait_for_url(url)                          # 選んだ時の hash の更新で終わらず、紹介のページが開くまで待つ
        assert page.evaluate("document.querySelectorAll('h1').length") == 1 and page.inner_text("h1") == "slideplay"
    for deck in DECKS:
        with recorded_page(browser, url, viewport=(1280, 800), player=False) as page:
            with page.expect_navigation():
                page.click(f"a.deck-{deck}")
            page.wait_for_function("!!window.__sp")
            assert page.url.split("#")[0] == (REPO / f"demo/{lang}/{deck}.html").as_uri()
            assert page.evaluate("slideDeck.info.id") == deck
    with recorded_page(browser, url, viewport=(1280, 800), player=False) as page:
        with page.expect_navigation():
            page.click(".lang a")
        assert page.url.split("#")[0] == (REPO / other).as_uri()


@pytest.mark.parametrize("name,lang,other,readme,catalog", PORTALS)
@pytest.mark.parametrize("viewport", [(1280, 800), (390, 844), (320, 568)], ids=["desktop", "phone-390", "phone-320"])
def test_portal_layout(browser, name, lang, other, readme, catalog, viewport):
    """横スクロールがない。文の左右に16pxの余白がある。コードの横長は、ページでなくコードの枠の中でスクロールする。
    目次のボタンは、最初の画面に入る大きさ（高さ44px以上）。"""
    with recorded_page(browser, (REPO / name).as_uri(), viewport=viewport, player=False) as page:
        width, height = viewport
        assert page.evaluate("document.documentElement.scrollWidth") <= width, "ページが横にはみ出す"
        assert page.evaluate("document.body.scrollWidth") <= width
        boxes = page.evaluate("""() => {
          const out = [];
          for (const e of document.querySelectorAll('h1, .tagline, .cta > *, .decks a, .hint, .toc, main h2, main p, main li, pre')) {
            const r = e.getBoundingClientRect();
            out.push([e.tagName.toLowerCase() + '.' + e.className, r.left, r.right]);
          }
          return out;
        }""")
        assert len(boxes) > 40
        gutter = 16
        for label, left, right in boxes:
            assert left >= gutter - 0.5, f"{label}: 左の余白 {left}"
            assert right <= width - gutter + 0.5, f"{label}: 右の余白 {width - right}"
        # コード：枠の中でスクロール（スマホでは、横長のコードが実際にはみ出して枠の中でスクロールする）
        pres = page.evaluate("Array.from(document.querySelectorAll('pre')).map(p => [getComputedStyle(p).overflowX, p.scrollWidth, p.clientWidth])")
        assert pres and all(o == "auto" for o, _, _ in pres)
        if width <= 390:
            assert any(sw > cw for _, sw, cw in pres)
        # 最初の画面に、タイトル・目次のボタンが入る
        cta = page.evaluate("(() => { const r = document.querySelector('a.button').getBoundingClientRect(); return [r.top, r.bottom, r.height]; })()")
        assert cta[1] <= height and cta[2] >= 44


CONTRAST_JS = """(selectors) => {
  const rgb = c => { const m = c.match(/rgba?\\(([^)]+)\\)/); const p = m[1].split(/[ ,\\/]+/).filter(Boolean).map(Number); return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1]; };
  const lum = ([r, g, b]) => { const f = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }; return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b); };
  const bgOf = e => { for (let n = e; n; n = n.parentElement) { const c = rgb(getComputedStyle(n).backgroundColor); if (c[3] > 0) return c; } return [255, 255, 255, 1]; };
  const out = {};
  for (const sel of selectors) {
    const e = document.querySelector(sel);
    if (!e) { out[sel] = null; continue; }
    const fg = rgb(getComputedStyle(e).color), bg = bgOf(e);
    const [hi, lo] = [lum(fg), lum(bg)].sort((a, b) => b - a);
    out[sel] = Math.round((hi + 0.05) / (lo + 0.05) * 100) / 100;
  }
  out['body-bg-luminance'] = lum(rgb(getComputedStyle(document.body).backgroundColor));
  return out;
}"""
CONTRAST_SELECTORS = ["h1", ".tagline", ".button", ".ghost", ".lang a", ".eyebrow", ".deck-intro .kind", ".deck-chic .kind", ".deck-bounce .kind",
                      ".decks strong", ".decks .line", ".hint", ".toc a", ".toc p", ".readme-note", "main p", "main h2", "main a",
                      "main li code", "pre code"]


@pytest.mark.parametrize("name,lang,other,readme,catalog", PORTALS)
@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_portal_readable_in_light_and_dark(browser, name, lang, other, readme, catalog, scheme):
    """OS の明るい・暗いに合わせて配色が変わり、どちらでも文字と背景のコントラスト比が 4.5 以上（WCAG AA）。"""
    with recorded_page(browser, (REPO / name).as_uri(), viewport=(1280, 800), player=False, color_scheme=scheme) as page:
        result = page.evaluate(CONTRAST_JS, CONTRAST_SELECTORS)
    luminance = result.pop("body-bg-luminance")
    assert luminance > 0.8 if scheme == "light" else luminance < 0.05, f"{scheme}: 背景の明るさ {luminance}"
    missing = [k for k, v in result.items() if v is None]
    assert not missing, f"要素がない: {missing}"
    low = {k: v for k, v in result.items() if v < 4.5}
    assert not low, f"{scheme}: コントラスト比が 4.5 未満: {low}"


@pytest.mark.parametrize("name,lang,other,readme,catalog", PORTALS)
def test_portal_relative_links_exist(name, lang, other, readme, catalog):
    """紹介のページの相対リンク・ページ内のリンク・GitHub の blob リンクがすべて実在する。"""
    refs = Refs(read(name))
    ids = set(refs.ids)
    assert len(ids) == len(refs.ids), "id が重なっている"
    checked = 0
    for tag, key, value, attrs in refs.refs:
        if value.startswith("data:"):
            continue
        if value.startswith("#"):
            assert value[1:] in ids, f"{name}: ページ内のリンク先 {value} がない"
        elif value.startswith(f"{REPO_URL}/blob/main/"):
            target = value[len(f"{REPO_URL}/blob/main/"):].split("#")[0]
            assert (REPO / target).is_file(), f"{name}: GitHub のリンク先 {target} がリポジトリにない"
        elif value.startswith("https://") or value.startswith("http://"):
            assert value in (REPO_URL, DEMO_URL) or value.startswith(DEMO_URL), f"{name}: 想定外の外部リンク {value}"
        else:
            assert (REPO / value.split("#")[0]).is_file(), f"{name}: 相対リンク先 {value} がない"
        checked += 1
    assert checked > 20


@pytest.mark.parametrize("name", ["catalog.html", "catalog.ja.html"])
def test_catalog_relative_links_exist(name):
    """目次の href と、読み込む player.js が実在する（ブラウザなしで確かめる）。"""
    text = read(name)
    hrefs = re.findall(r"href:\s*'([^']+)'", text)
    assert len(hrefs) >= 9
    srcs = [v for _, k, v, _ in Refs(text).refs if k == "src"]
    assert srcs == ["player/player.js"]
    for value in hrefs + srcs:
        assert (REPO / value.split("#")[0]).is_file(), f"{name}: {value} がない"


def test_portal_sections_follow_the_readmes():
    """README の `##` の題と、紹介のページの節（h2・目次・section の id）が、同じ順で一致する。コードブロックと `コード` も落ちない。
    節は英語と日本語で同じ数・同じ並び（同じ id）。"""
    section_ids = {}
    for name, lang, other, readme, catalog in PORTALS:
        titles, blocks, prose = readme_parts(readme)
        text = read(name)
        refs = Refs(text)
        assert titles, "README に ## の節がない"
        assert refs.h2 == titles, "紹介のページの節が README の ## と違う"
        toc = [label for href, label in refs.links if href and href.startswith("#")]
        assert toc == titles, "目次の項目が README の ## と違う"
        ids = re.findall(r'<section id="([^"]+)">', text)
        assert len(ids) == len(titles) and [h for h in re.findall(r'<a href="#([^"]+)">', text)] == ids
        section_ids[lang] = ids
        shown = html.unescape(text)
        # コードブロック：全部、同じ順で、本文がそのまま載っている
        pre = [html.unescape(m) for m in re.findall(r"<pre[^>]*><code[^>]*>(.*?)</code></pre>", text, re.S)]
        assert pre == blocks, "コードブロックが README と違う"
        # コードの範囲（`…`）は、README の最初の2段落（言語の切り替えと Demo の行）を除いて、すべて紹介のページに載っている
        head, rest = prose.split("\n## ", 1)
        lead = "\n\n".join(para for para in head.split("\n\n")[1:] if not re.match(r"(English \||\[English\]|Demo|デモ)", para)) + "\n## " + rest
        for span in re.findall(r"`([^`\n]+)`", lead):
            assert span in shown, f"{name}: README の `{span}` が紹介のページにない"
        # リンク：README の [文字](先) の文字が、紹介のページのリンクの文字にある
        for label, target in re.findall(r"\[([^\]]+)\]\(([^)\s]+)\)", lead):
            assert any(label == l for _, l in refs.links), f"{name}: README のリンク {label} がない"
    assert section_ids["en"] == section_ids["ja"]


def test_portal_is_a_fresh_build_of_the_readmes():
    """コミットした index.html・index.ja.html が、README から作り直した結果と一字一句同じ（README を直して作り直し忘れると失敗する）。"""
    for name, lang, other, readme, catalog in PORTALS:
        assert build_portal.build(lang) == read(name), f"{name} が古い。python3 scripts/build_portal.py で作り直す"
    r = subprocess.run([sys.executable, str(REPO / "scripts" / "build_portal.py"), "--check"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_english_portal_prose_is_english():
    """英語の紹介のページの日本語は、型の名前・見本と書き出しのファイル名・言語の切り替えだけ。"""
    text = read("index.html")
    text = re.sub(r"<style>.*?</style>", "", text, flags=re.S)
    for literal in [*TYPES, "下書き.md", "-メモ.md", "日本語"]:
        text = text.replace(literal, "")
    assert re.findall(r"[^\n]*[぀-ヿ一-鿿][^\n]*", text) == []


# ---- scripts/build_portal.py の Markdown の読み方 ----

def test_build_portal_inline_escapes_and_links():
    inline = build_portal.inline
    assert inline("a `<b> && c` d") == "a <code>&lt;b&gt; &amp;&amp; c</code> d"
    assert inline("x < y & z") == "x &lt; y &amp; z"
    assert inline("<https://example.com/a?b=1&c=2>") == '<a href="https://example.com/a?b=1&amp;c=2">https://example.com/a?b=1&amp;c=2</a>'
    assert inline("[CONTRACT.md](CONTRACT.md)") == f'<a href="{REPO_URL}/blob/main/CONTRACT.md">CONTRACT.md</a>'
    assert inline("[the catalog](catalog.html)") == '<a href="catalog.html">the catalog</a>'    # 実在するページは相対のまま
    assert inline("[`code` in a link](https://example.com/)") == '<a href="https://example.com/"><code>code</code> in a link</a>'
    assert inline("`**...**` and `__pycache__`") == "<code>**...**</code> and <code>__pycache__</code>"


@pytest.mark.parametrize("markdown", [
    "| a | b |\n|---|---|",                  # 表
    "> a quote",
    "1. numbered",
    "text with **bold**",
    "- an item\ncontinued here",              # 次の行へ続く箇条書き
    "- item\n   - odd indent",
    "- item\n    - nested too deep",
    "```\nnever closed",
    "<!-- a comment -->",
])
def test_build_portal_refuses_unsupported_markdown(markdown):
    with pytest.raises(ValueError):
        for block in build_portal.parse(markdown):
            build_portal.render_block(block)


def test_build_portal_renders_lists_and_code():
    blocks = build_portal.parse("- a\n  - b `c`\n- d\n\n```html\n<p>&</p>\n```\n")
    assert [build_portal.render_block(b) for b in blocks] == [
        "<ul>\n<li>a\n<ul>\n<li>b <code>c</code></li>\n</ul></li>\n<li>d</li>\n</ul>",
        '<pre tabindex="0"><code class="language-html">&lt;p&gt;&amp;&lt;/p&gt;</code></pre>',
    ]
