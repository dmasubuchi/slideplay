"""editor/render.js と editor/shell.py（デッキの元を描く・デッキのページ）の試験。"""
import shutil
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from editor.convert import convert  # noqa: E402
from editor.shell import deck_html  # noqa: E402
from helpers import page_session  # noqa: E402

BASIC = REPO / "tests" / "editor_decks" / "basic"

# 舞台の li のうち visibility が visible のものの、自分の文字（入れ子の ul は除く）
VISIBLE_ITEMS = """() => [...document.querySelectorAll('#stage li')]
  .filter(li => getComputedStyle(li).visibility === 'visible')
  .map(li => { const c = li.cloneNode(true); c.querySelectorAll('ul').forEach(u => u.remove()); return c.textContent; })"""


def visible_items(page):
    return page.evaluate(VISIBLE_ITEMS)


def write_page(root, md_path, editing):
    """root に render.js・player.js を写し、md_path のデッキのページ index.html を書く。"""
    (root / "editor").mkdir(exist_ok=True)
    (root / "player").mkdir(exist_ok=True)
    shutil.copy(REPO / "editor" / "render.js", root / "editor" / "render.js")
    shutil.copy(REPO / "player" / "player.js", root / "player" / "player.js")
    html = deck_html(convert(md_path, editing=editing), render_src="editor/render.js",
                     player_src="player/player.js", editing=editing)
    (root / "index.html").write_text(html, encoding="utf-8")
    return (root / "index.html").as_uri()


@pytest.fixture
def open_basic(browser, tmp_path):
    sessions = []

    def open_(hash="", editing=False):
        root = tmp_path / f"basic{len(sessions)}"
        shutil.copytree(BASIC, root)
        url = write_page(root, root / "下書き.md", editing)
        cm = page_session(browser, url + hash)
        sessions.append(cm)
        return cm.__enter__()

    yield open_
    for cm in reversed(sessions):
        cm.__exit__(None, None, None)


@pytest.fixture
def tmp_deck_page(browser, tmp_path):
    sessions = []

    def make(md_text, hash=""):
        root = tmp_path / f"tmp{len(sessions)}"
        root.mkdir()
        (root / "下書き.md").write_text(md_text, encoding="utf-8")
        cm = page_session(browser, write_page(root, root / "下書き.md", False) + hash)
        sessions.append(cm)
        return cm.__enter__()

    yield make
    for cm in reversed(sessions):
        cm.__exit__(None, None, None)


def test_star_items_follow_steps(open_basic):
    page = open_basic(hash="#s02.0")
    assert visible_items(page) == ["質問を単語に分け、同じ単語を持つ人を探す", "前回の「桶狭間」の検索も、この方式だった"]
    page.goto(page.url.split("#")[0] + "#s02.2")
    assert len(visible_items(page)) == 4


def test_inline_marks(open_basic):
    page = open_basic(hash="#s02")
    assert page.inner_html("#stage h2 b") == "珍しい語"
    assert page.inner_html("#stage li mark") == "単語に分け"


def test_text_is_escaped(tmp_deck_page):
    page = tmp_deck_page("# a\n- <script>x</script>\n")
    assert page.inner_text("#stage li") == "<script>x</script>"
    assert page.locator("#stage script").count() == 0


def test_data_src_only_when_editing(open_basic):
    assert open_basic(hash="#s02", editing=True).locator("#stage [data-src]").count() == 5
    assert open_basic(hash="#s02", editing=False).locator("#stage [data-src]").count() == 0


def test_data_src_value(open_basic):
    page = open_basic(hash="#s02", editing=True)
    assert page.get_attribute("#stage h2", "data-src") == "16:2-24"


def test_figure_and_html_page(open_basic):
    page = open_basic(hash="#s03")
    page.wait_for_function("document.querySelector('#stage img').naturalWidth > 0")
    assert page.eval_on_selector("#stage img", "e => e.naturalWidth") > 0
    page.goto(page.url.split("#")[0] + "#s04")
    assert page.inner_text("#stage .rrf") == "RRF = Σ 1/(k + rank)"


def test_missing_figure_box(tmp_deck_page):
    page = tmp_deck_page("# a\n\n![x](fig/none.svg)\n")
    assert page.inner_text("#stage .missing") == "fig/none.svg がありません"


def test_paragraph_lines_and_types(tmp_deck_page):
    page = tmp_deck_page("<!-- _class: 強調 -->\n# t\n\n一行目\n二行目\n\n---\n\n<!-- _class: 二段 -->\n# u\n\n### 左\n- a\n### 右\n- b\n")
    assert page.inner_html("#stage .big") == "一行目<br>二行目"
    page.goto(page.url.split("#")[0] + "#p2")
    assert page.locator("#stage .col").count() == 2
    assert page.inner_text("#stage .col >> nth=1 >> h3") == "右"


def test_no_heading_when_head_missing(tmp_deck_page):
    page = tmp_deck_page("- a\n")
    assert page.locator("#stage h1, #stage h2").count() == 0


def test_each_type_draws_and_no_id_attrs(open_basic):
    page = open_basic()
    for i in range(5):
        page.evaluate("i => window.renderSlide(i, 0)", i)
        assert page.locator("#stage [id]").count() == 0
    assert page.evaluate("deckInfo()") == [{"id": "s01", "steps": 0}, {"id": "s02", "steps": 2},
                                           {"id": "s03", "steps": 0}, {"id": "s04", "steps": 0}, {"id": "p5", "steps": 0}]


def test_deck_html_escapes_script_close():
    data = {"info": {"id": "d", "title": "t"}, "slides": [{"id": "a", "title": "</script>", "steps": 0, "notes": "",
                                                          "head": None, "blocks": [], "type": "ふつう", "html": None}]}
    out = deck_html(data, render_src="r.js", player_src="p.js", live_src="/editor/live.js")
    assert "</script>x" not in out and "<\\/script>" in out
    assert out.index("r.js") < out.index("EditorSlides.createDeck") < out.index("live.js") < out.index("p.js")


def test_emphasis_sentence_is_big_and_centred(tmp_deck_page):
    page = tmp_deck_page("<!-- _class: 強調 -->\n# t\n\n大きな一文\n")
    assert page.evaluate("parseFloat(getComputedStyle(document.querySelector('#stage .big')).fontSize)") >= 80
    box = page.evaluate("""() => { const s = document.querySelector('#stage').getBoundingClientRect();
      const r = document.querySelector('#stage .big').getBoundingClientRect();
      return [r.left + r.width / 2 - s.left, r.top + r.height / 2 - s.top, s.width]; }""")
    scale = box[2] / 1920
    assert abs(box[0] / scale - 960) <= 120 and abs(box[1] / scale - 540) <= 120, box


# 題名「題名」（1行目 2-4）と項目「点数」（3行目 2-4）の1枚のデッキ（render.js だけを読んだページ）
UNIT_DATA = {"info": {"id": "t", "title": "t"}, "slides": [
    {"id": "s01", "title": "題名", "steps": 0, "type": "標準", "head": {"text": "題名", "src": [1, 2, 4]},
     "blocks": [{"kind": "list", "items": [{"text": "点数", "step": 0, "src": [3, 2, 4]}]}]}]}


@pytest.fixture
def page(browser, tmp_path):
    import json
    (tmp_path / "editor").mkdir()
    shutil.copy(REPO / "editor" / "render.js", tmp_path / "editor" / "render.js")
    (tmp_path / "index.html").write_text(
        '<!doctype html><meta charset="utf-8"><script src="editor/render.js"></script>'
        f"<script>window.DATA = {json.dumps(UNIT_DATA)};</script>", encoding="utf-8")
    with page_session(browser, (tmp_path / "index.html").as_uri()) as p:
        yield p


def test_inline_nesting_and_bigger(page):
    html = page.evaluate("""() => { const d = document.createElement('div');
      EditorSlides.inline(d, 'x **a ==b== c** ++大++ <i>'); return d.innerHTML; }""")
    assert html == 'x <b>a <mark>b</mark> c</b> <span class="bigger">大</span> &lt;i&gt;'


def test_deck_editor_lookup(page):
    r = page.evaluate("""() => { const deck = EditorSlides.createDeck(DATA, {editing: true});
      return [deck.editor.textAt('1:2-4'), deck.editor.slideAt('3:2-4'), deck.editor.keys(), deck.editor.textAt('9:0-1')]; }""")
    assert r == ["題名", "s01", ["1:2-4", "3:2-4"], None]


def test_no_editor_when_not_editing(page):
    assert page.evaluate("() => EditorSlides.createDeck(DATA, {editing: false}).editor === undefined")


def test_render_calls_decorate_only_when_editing(page):
    calls = page.evaluate("""() => { const seen = []; window.EditorPending = { decorate: (t, id) => seen.push(id) };
      const t = document.createElement('div'); t.className = 'sp-target';
      EditorSlides.createDeck(DATA, {editing: true}).render(0, 0, t);
      EditorSlides.createDeck(DATA, {editing: false}).render(0, 0, t);
      return seen; }""")
    assert calls == ["s01"]


def test_decorate_error_does_not_break_render(page):
    assert page.evaluate("""() => { window.EditorPending = { decorate() { throw new Error('x'); } };
      const t = document.createElement('div'); EditorSlides.createDeck(DATA, {editing: true}).render(0, 0, t);
      return t.textContent.includes('題名'); }""")
