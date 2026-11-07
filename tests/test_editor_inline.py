"""editor/edit.js（舞台の文字をその場で直す入力欄）の試験。実物のサーバーで開く。
段階で隠れない #s02.2 の文は、全体の文で探す（item(page, "珍しい語ほど、点数を高く付ける")）。"""
import shutil
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from editor.server import EditorServer  # noqa: E402
from helpers import page_session  # noqa: E402
from test_editor_server import BASIC  # noqa: E402

ITEM1 = "珍しい語ほど、点数を高く付ける"
S02 = "#s02.2"            # 段階の項目まで見えているページ

MARKS_MD = """---
marp: true
title: 印
---

<!-- id: m01 -->
# 印

- a **b** ==c== d
"""


@pytest.fixture
def server(tmp_path):
    deck = tmp_path / "deck"
    shutil.copytree(BASIC, deck)
    s = EditorServer(deck / "下書き.md")
    s.start()
    try:
        yield s
    finally:
        s.stop()


def _start(md_path):
    s = EditorServer(md_path)
    s.start()
    return s


@pytest.fixture
def server_with_marks(tmp_path):
    md = tmp_path / "印.md"
    md.write_text(MARKS_MD, encoding="utf-8")
    s = _start(md)
    try:
        yield s
    finally:
        s.stop()


@pytest.fixture
def server_with_error(tmp_path):
    md = tmp_path / "誤り.md"
    md.write_text("<!-- 閉じていない\n# x\n", encoding="utf-8")
    s = _start(md)
    try:
        yield s
    finally:
        s.stop()


def item(page, text):
    """#stage の中の、text を含む文の [data-src]。"""
    return page.locator("#stage [data-src]").filter(has_text=text).first


def click_text(page, text):
    """札（前の文）を除いた、文字の真ん中を押す（Playwright の click は、描いた札まで含めた箱の真ん中を狙ってしまう）。"""
    x, y = page.evaluate("""(t) => { const el = [...document.querySelectorAll('#stage [data-src]')].find(e => e.textContent.includes(t));
      const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
      for (let n; (n = w.nextNode());) { if (n.parentElement.closest('.sp-ed-before')) continue;
        const r = document.createRange(); r.selectNodeContents(n); const b = r.getBoundingClientRect(); return [b.x + b.width / 2, b.y + b.height / 2]; } }""", text)
    page.mouse.click(x, y)


def select_all(page):
    """開いた要素の中身を全部選ぶ（キー操作の ⌘A は OS で違うので Range で）。"""
    page.evaluate("getSelection().selectAllChildren(document.activeElement)")


def open_and_replace(page, text, new):
    item(page, text).click()
    select_all(page)
    page.keyboard.type(new)


def select_text(page, text):
    """開いた要素の中の text を Range で選ぶ。"""
    assert page.evaluate("""(t) => {
      const root = document.querySelector('#stage .sp-ed-open');
      const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
      for (let n; (n = w.nextNode());) {
        if (n.parentElement.closest('.sp-ed-before')) continue;
        const i = n.data.indexOf(t);
        if (i < 0) continue;
        const r = document.createRange(); r.setStart(n, i); r.setEnd(n, i + t.length);
        const s = getSelection(); s.removeAllRanges(); s.addRange(r);
        return true;
      }
      return false; }""", text)


def test_click_opens_immediately(server, browser):
    with page_session(browser, server.url + S02) as page:
        item(page, ITEM1).click()
        assert page.evaluate("document.activeElement.matches('#stage [data-src].sp-ed-open[contenteditable=true]')")
        page.keyboard.type("X")                                   # 待たずに打てる
        assert "X" in item(page, "X").inner_text()
        assert page.inner_text("#stage .sp-ed-before") == ITEM1
        assert page.locator(".sp-ed-tools").inner_text().split() == ["B", "太く", "A＋", "大きく"]


def test_enter_confirms_and_pends(server, browser):
    with page_session(browser, server.url + S02) as page:
        open_and_replace(page, ITEM1, "珍しい語ほど、点数を高くする")
        page.keyboard.press("Enter")
        assert not page.locator("#stage .sp-ed-open").count() and not page.locator(".sp-ed-tools").count()
        assert page.evaluate("EditorPending.list().map(e => e.after)") == ["珍しい語ほど、点数を高くする"]
        assert page.evaluate("EditorPending.list()[0].before") == ITEM1
        assert ITEM1 in server.md.read_text(encoding="utf-8")   # まだ書き戻さない


def test_esc_cancels(server, browser):
    with page_session(browser, server.url + S02) as page:
        open_and_replace(page, ITEM1, "ちがう")
        page.keyboard.press("Escape")
        assert page.evaluate("EditorPending.count()") == 0 and ITEM1 in page.inner_text("#stage")
        assert not page.locator("#stage .sp-ed-open").count() and not page.locator("#stage .sp-ed-before").count()
        assert not page.locator(".sp-ed-tools").count()


def test_tab_moves_to_next(server, browser):
    with page_session(browser, server.url + S02) as page:
        open_and_replace(page, ITEM1, "一")
        page.keyboard.press("Tab")
        assert page.evaluate("document.activeElement.classList.contains('sp-ed-open')")
        assert page.evaluate("document.activeElement.textContent.includes('どの人にも出る語は')")
        assert page.evaluate("EditorPending.count()") == 1
        page.keyboard.press("Shift+Tab")                           # 前へ（直した文へ戻る）
        assert page.evaluate("document.activeElement.classList.contains('sp-ed-open') && document.activeElement.textContent.includes('一')")


def test_tab_on_last_confirms_only(server, browser):
    with page_session(browser, server.url + S02) as page:
        open_and_replace(page, "どの人にも出る語は、手がかりにならない", "最後")
        page.keyboard.press("Tab")
        assert not page.locator("#stage .sp-ed-open").count() and page.evaluate("EditorPending.count()") == 1


def test_ime_enter_does_not_confirm(server, browser):
    with page_session(browser, server.url + S02) as page:
        item(page, ITEM1).click()
        for init in ("{key: 'Enter', isComposing: true, bubbles: true, cancelable: true}", "{key: 'Enter', keyCode: 229, bubbles: true, cancelable: true}",
                     "{key: 'Escape', isComposing: true, bubbles: true, cancelable: true}"):
            page.evaluate(f"document.activeElement.dispatchEvent(new KeyboardEvent('keydown', {init}))")
            assert page.locator("#stage .sp-ed-open").count() == 1


def test_cmd_b_bolds_selection(server, browser):
    with page_session(browser, server.url + S02) as page:
        item(page, ITEM1).click()
        select_text(page, "高く")                                  # 開いた要素の中の文字を Range で選ぶ
        page.keyboard.press("Meta+B")
        page.keyboard.press("Enter")
        assert page.evaluate("EditorPending.list()[0].after") == "珍しい語ほど、点数を**高く**付ける"


def test_cmd_b_toggles_off(server, browser):
    with page_session(browser, server.url + "#s02") as page:
        item(page, "珍しい語").click()                             # 見出し「…**珍しい語**ほど重く見る」
        select_text(page, "珍しい語")
        page.keyboard.press("Control+B")
        page.keyboard.press("Enter")
        assert page.evaluate("EditorPending.list()[0].after") == "キーワード検索は珍しい語ほど重く見る"


def test_bigger_button(server, browser):
    with page_session(browser, server.url + S02) as page:
        item(page, ITEM1).click()
        select_text(page, "高く")
        page.click(".sp-ed-tools >> text=A＋ 大きく")
        assert page.evaluate("document.activeElement.classList.contains('sp-ed-open')")   # 焦点は移らない
        page.keyboard.press("Enter")
        assert page.evaluate("EditorPending.list()[0].after") == "珍しい語ほど、点数を++高く++付ける"


def test_bold_button_and_bigger_toggle(server, browser):
    with page_session(browser, server.url + S02) as page:
        item(page, ITEM1).click()
        select_text(page, "高く")
        page.click(".sp-ed-tools >> text=A＋ 大きく")
        select_text(page, "高く")
        page.click(".sp-ed-tools >> text=A＋ 大きく")              # すべて大きいので外す
        page.click(".sp-ed-tools >> text=B 太く")
        page.keyboard.press("Enter")
        assert page.evaluate("EditorPending.list()[0].after") == "珍しい語ほど、点数を**高く**付ける"


def test_marks_visible_while_editing(server_with_marks, browser):   # 「a **b** ==c== d」の項目
    with page_session(browser, server_with_marks.url) as page:
        item(page, "a b c d").click()
        assert page.locator("#stage .sp-ed-open b").inner_text() == "b" and page.locator("#stage .sp-ed-open mark").inner_text() == "c"
        assert "**" not in page.inner_text("#stage .sp-ed-open") and "==" not in page.inner_text("#stage .sp-ed-open")


def test_untouched_marks_round_trip(server_with_marks, browser):
    with page_session(browser, server_with_marks.url) as page:
        item(page, "a b c d").click()
        page.keyboard.press("End")
        page.keyboard.press("Backspace")
        page.keyboard.type("e")
        page.keyboard.press("Enter")
        assert page.evaluate("EditorPending.list()[0].after") == "a **b** ==c== e"


def test_serialize(server_with_marks, browser):
    with page_session(browser, server_with_marks.url) as page:
        page.wait_for_selector("#stage [data-src]")
        got = page.evaluate("""() => { const d = document.createElement('div');
          d.innerHTML = 'a\\u00a0<b>x</b><strong>y</strong><mark>z</mark><span class="bigger">w</span><b></b><br><i>i</i><span class="sp-ed-before">前</span>';
          return EditorInline.serialize(d); }""")
        assert got == "a **x****y**==z==++w++i"


def test_paste_is_plain_text(server, browser):
    # クリップボードの実物は使えない環境なので、同じ中身（HTML と文字）を持つ paste イベントを送る
    with page_session(browser, server.url + S02) as page:
        item(page, ITEM1).click()
        select_all(page)
        page.evaluate("""() => { const dt = new DataTransfer();
          dt.setData('text/html', '<b>x</b>\\ny'); dt.setData('text/plain', 'x\\ny');
          document.activeElement.dispatchEvent(new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true })); }""")
        assert page.locator("#stage .sp-ed-open b").count() == 0
        page.keyboard.press("Enter")
        assert page.evaluate("EditorPending.list()[0].after") == "x y"


def test_player_keys_ignored_while_editing(server, browser):
    with page_session(browser, server.url + "#s02") as page:
        item(page, "珍しい語").click()
        page.keyboard.press("ArrowDown")
        page.keyboard.type("t")
        assert page.evaluate("location.hash") == "#s02" and not page.locator(".sp-side").count()   # 一覧つきの画面（T）は開かない


def test_blur_confirms(server, browser):
    with page_session(browser, server.url + S02) as page:
        open_and_replace(page, ITEM1, "外で確定")
        page.mouse.click(5, 450)                                    # 舞台の外
        assert page.evaluate("EditorPending.list()[0].after") == "外で確定"
        assert not page.locator("#stage .sp-ed-open").count()


def test_click_other_item_confirms_and_opens(server, browser):
    with page_session(browser, server.url + S02) as page:
        open_and_replace(page, ITEM1, "一つ目")
        item(page, "どの人にも出る語は").click()
        assert page.evaluate("EditorPending.count()") == 1
        assert page.locator("#stage .sp-ed-open").count() == 1
        assert page.evaluate("document.activeElement.textContent.includes('どの人にも出る語は')")


def test_reopen_pending_keeps_original_before(server, browser):
    with page_session(browser, server.url + S02) as page:
        open_and_replace(page, ITEM1, "一回目")
        page.keyboard.press("Enter")
        click_text(page, "一回目")
        assert page.locator("#stage .sp-ed-before").count() == 1 and page.inner_text("#stage .sp-ed-before") == ITEM1
        select_all(page)
        page.keyboard.type("二回目")
        page.keyboard.press("Enter")
        e = page.evaluate("EditorPending.list()")
        assert len(e) == 1 and e[0]["before"] == ITEM1 and e[0]["after"] == "二回目"
        click_text(page, "二回目")                                 # 元の文に戻すと、直しは消える
        select_all(page)
        page.keyboard.type(ITEM1)
        page.keyboard.press("Enter")
        assert page.evaluate("EditorPending.count()") == 0 and not page.locator("#stage .sp-ed-pending").count()


def test_esc_on_pending_keeps_pending(server, browser):
    with page_session(browser, server.url + S02) as page:
        open_and_replace(page, ITEM1, "一回目")
        page.keyboard.press("Enter")
        click_text(page, "一回目")
        select_all(page)
        page.keyboard.type("捨てる")
        page.keyboard.press("Escape")
        assert page.evaluate("EditorPending.list()[0].after") == "一回目"
        assert page.inner_text("#stage .sp-ed-before") == ITEM1 and "捨てる" not in page.inner_text("#stage")


def test_detached_while_open_confirms(server, browser):
    with page_session(browser, server.url + S02) as page:
        open_and_replace(page, ITEM1, "消えても残る")
        page.evaluate("document.querySelector('#stage').replaceChildren()")
        page.wait_for_function("EditorPending.count() === 1 && !EditorInline.isOpen()")
        assert page.evaluate("EditorPending.list()[0].after") == "消えても残る" and not page.locator(".sp-ed-tools").count()


def test_not_editable_outside_stage_or_hidden(server, browser):
    with page_session(browser, server.url + "#s02") as page:
        page.wait_for_selector("#stage [data-src]")
        # 段階で隠れた項目（#s02 では * の項目は隠れている）
        page.evaluate("""() => { const el = [...document.querySelectorAll('#stage [data-src]')].find(e => e.textContent.includes('どの人にも出る語は'));
          el.dispatchEvent(new MouseEvent('click', { bubbles: true })); }""")
        assert not page.locator(".sp-ed-open").count() and not page.evaluate("EditorInline.isOpen()")
        page.keyboard.press("t")                                     # 左の縮小（T）
        page.wait_for_selector(".sp-side [data-src]", state="attached")
        page.evaluate("document.querySelector('.sp-side [data-src]').dispatchEvent(new MouseEvent('click', { bubbles: true }))")
        assert not page.locator(".sp-ed-open").count() and not page.evaluate("EditorInline.isOpen()")
    with page_session(browser, server.url + "#s04") as page:        # 作り込んだページ（html:）
        page.wait_for_selector("#stage .html")
        page.mouse.click(720, 450)
        assert not page.locator(".sp-ed-open").count()


def test_error_placeholder_not_editable(server_with_error, browser):
    with page_session(browser, server_with_error.url) as page:
        page.wait_for_selector("#stage .frame")
        page.mouse.click(720, 450)
        page.locator("#stage p").click()
        assert not page.locator(".sp-ed-open").count()


def test_click_to_apply_end_to_end(server, browser):
    with page_session(browser, server.url + S02) as page:
        open_and_replace(page, ITEM1, "珍しい語ほど、点数を高くする")
        page.keyboard.press("Enter")
        page.click(".sp-edit-apply")
        page.wait_for_function("EditorPending.count() === 0 && document.querySelector('#stage').textContent.includes('点数を高くする')", timeout=2000)
        assert "* 珍しい語ほど、点数を高くする" in server.md.read_text(encoding="utf-8")


def test_live_reload_waits_while_editing(server, browser):
    from test_editor_server import replace_text
    with page_session(browser, server.url + S02) as page:
        item(page, "どの人にも出る語は").click()
        replace_text(server.md, ITEM1, "珍しい語ほど、別の文")
        page.wait_for_timeout(800)
        assert "別の文" not in page.inner_text("#stage") and page.locator("#stage .sp-ed-open").count() == 1
        page.keyboard.press("Escape")
        page.wait_for_function("document.querySelector('#stage').textContent.includes('別の文')", timeout=2000)


def test_select_all_backspace_then_type(server, browser):
    with page_session(browser, server.url + S02) as page:
        item(page, ITEM1).click()
        select_all(page)
        page.keyboard.press("Backspace")
        page.keyboard.type("打ち直し")
        page.keyboard.press("Enter")
        assert page.evaluate("EditorPending.list().map(e => e.after)") == ["打ち直し"]


def test_select_all_then_leading_space(server, browser):
    with page_session(browser, server.url + S02) as page:
        item(page, ITEM1).click()
        select_all(page)
        page.keyboard.type(" x")
        page.keyboard.press("Enter")
        assert page.evaluate("EditorPending.list().map(e => e.after.trim())") == ["x"]


def test_empty_confirm_is_refused(server, browser):
    with page_session(browser, server.url + S02) as page:
        item(page, ITEM1).click()
        select_all(page)
        page.keyboard.press("Backspace")
        page.keyboard.press("Enter")
        assert page.evaluate("EditorPending.count()") == 0 and not page.locator("#stage .sp-ed-open").count()
        assert ITEM1 in page.inner_text("#stage") and not page.locator("#stage .sp-ed-before").count()
        assert page.inner_text(".sp-edit-toast") == "空にはできません。消すときはエディターで消してください"


def test_partial_unbold_keeps_rest(server, browser):
    with page_session(browser, server.url + "#s02") as page:
        item(page, "珍しい語").click()                             # 見出し「…**珍しい語**ほど重く見る」
        select_text(page, "しい")
        page.keyboard.press("Meta+B")
        page.keyboard.press("Enter")
        assert page.evaluate("EditorPending.list()[0].after") == "キーワード検索は**珍**しい**語**ほど重く見る"


def test_partial_unbigger_keeps_rest(server, browser):
    with page_session(browser, server.url + S02) as page:
        item(page, ITEM1).click()
        select_text(page, "高く")
        page.click(".sp-ed-tools >> text=A＋ 大きく")
        select_text(page, "高")
        page.click(".sp-ed-tools >> text=A＋ 大きく")
        page.keyboard.press("Enter")
        assert page.evaluate("EditorPending.list()[0].after") == "珍しい語ほど、点数を高++く++付ける"


def test_bold_over_partly_bold_does_not_nest(server, browser):
    with page_session(browser, server.url + "#s02") as page:
        item(page, "珍しい語").click()
        # 「…検索は」の「は」から、太い語の「珍し」までを選ぶ
        page.evaluate("""() => { const el = document.querySelector('#stage .sp-ed-open'); const b = el.querySelector('b');
          const r = document.createRange(); r.setStart(el.firstChild, el.firstChild.length - 1); r.setEnd(b.firstChild, 2);
          const s = getSelection(); s.removeAllRanges(); s.addRange(r); }""")
        page.keyboard.press("Meta+B")
        page.keyboard.press("Enter")
        assert page.evaluate("EditorPending.list()[0].after") == "キーワード検索**は珍しい語**ほど重く見る"   # 太い所と隣り合う分は1つにまとまる


TWO_MD = """---
marp: true
title: 二段
---

<!-- id: t01 -->
<!-- _class: 二段 -->
# 二段の題名

### 左の見出し

左の文です

### 右の見出し

右の文です
"""


def _rects(page):
    """開いている入力欄・前の文の札・道具の、大きさと位置。"""
    return page.evaluate("""() => {
      const el = document.querySelector('#stage .sp-ed-open');
      const lab = document.querySelector('#stage .sp-ed-before');
      const tools = document.querySelector('.sp-ed-tools');
      const r = e => { const b = e.getBoundingClientRect(); return { top: b.top, bottom: b.bottom, left: b.left, right: b.right }; };
      return { el: r(el), lab: r(lab), tools: r(tools),
               elFont: parseFloat(getComputedStyle(el).fontSize), labFont: parseFloat(getComputedStyle(lab).fontSize),
               labBg: getComputedStyle(lab).backgroundColor, toolsBg: getComputedStyle(tools).backgroundColor }; }""")


def _check_label(page, text, name):
    item(page, text).click()
    page.wait_for_selector("#stage .sp-ed-open")
    g = _rects(page)
    assert g["labFont"] >= g["elFont"] * 0.5, (name, g)
    above = g["lab"]["bottom"] <= g["el"]["top"] + 1
    below = g["lab"]["top"] >= g["el"]["bottom"] - 1
    assert above or below, (name, g)
    t, lab = g["tools"], g["lab"]
    assert t["right"] <= lab["left"] or t["left"] >= lab["right"] or t["bottom"] <= lab["top"] or t["top"] >= lab["bottom"], (name, "道具と札が重なる", g)
    assert g["labBg"] != "rgba(0, 0, 0, 0)" and g["toolsBg"].count(",") == 2, (name, g["labBg"], g["toolsBg"])   # 不透明
    page.keyboard.press("Escape")


@pytest.mark.parametrize("text,name", [
    ("検索のしくみ", "表紙のh1"),
    ("質問から答えが出るまでを", "段落の行"),
    ("キーワード検索は", "h2"),
    (ITEM1, "項目"),
])
def test_before_label_is_readable_basic(server, browser, text, name):
    with page_session(browser, server.url + S02) as page:
        if name in ("表紙のh1", "段落の行"):
            page.evaluate("location.hash = '#s01'")
            page.wait_for_selector("#stage h1")
        _check_label(page, text, name)


def test_before_label_is_readable_two_column_h3(tmp_path, browser):
    md = tmp_path / "二段.md"
    md.write_text(TWO_MD, encoding="utf-8")
    s = _start(md)
    try:
        with page_session(browser, s.url + "#t01") as page:
            page.wait_for_selector("#stage h3")
            _check_label(page, "左の見出し", "二段のh3")
            _check_label(page, "左の文です", "二段の段落")
    finally:
        s.stop()
