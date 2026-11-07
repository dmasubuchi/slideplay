"""書き込みと追加ページの PDF・離れるときの確認の試験。

P と ⌘P の入口（beforeprint）が同じ順・同じ中身になること、書き込みも追加ページもないときは今の印刷用の表示のままであること、
beforeunload の確認と留まったときの知らせ、サムネイルには書き込みを入れないこと。
汎用の見本 examples/generic/proposal.html（9枚）を使う。
"""
import pytest

from test_added_pages import ADD_BTN, tool
from test_side import proposal, session
from test_swipe import webkit_browser  # noqa: F401（fixture）
from test_writing import rough_rect, stroke, writing

LINE = [(500, 300), (700, 320), (900, 340)]
STUB_PRINT = "void (window.print = () => {})"
PAGES = ".sp-print .sp-print-page"
STAY = "書き込みは P で PDF に残せます"


def pages_info(page):
    """印刷用の各ページ：白い追加ページか、書き込みの層の有無。"""
    return page.evaluate("""() => Array.from(document.querySelectorAll('.sp-print .sp-print-page')).map(p => ({
      blank: p.classList.contains('sp-print-blank'), target: !!p.querySelector('.sp-target'),
      ink: p.querySelectorAll('canvas.sp-print-ink').length })) """)


def ink_alpha(page, index, x, y):
    """印刷用の index ページの書き込みの層の、舞台の座標 (x, y) の画素の不透明度（なければ -1）。"""
    return page.evaluate("""([i, x, y]) => {
      const c = document.querySelectorAll('.sp-print .sp-print-page')[i].querySelector('canvas.sp-print-ink');
      if (!c) return -1;
      return c.getContext('2d').getImageData(Math.round(x), Math.round(y), 1, 1).data[3]; }""", [index, x, y])


def prepare(page):
    """3枚目に線、その直後の追加ページに □ を描いて、書き込みを終える。返すのは (線の中点, □ の左辺の中点)（舞台の座標）。"""
    page.keyboard.press("d")
    stroke(page, LINE)
    line = writing(page)["objects"][-1]
    assert line["t"] == "line"
    (ax, ay), (bx, by) = line["a"], line["b"]
    tool(page, ADD_BTN).click()
    stroke(page, rough_rect(300, 250, 400, 250))
    box = writing(page)["objects"][-1]
    assert box["t"] == "rect"
    page.keyboard.press("d")
    return ((ax + bx) / 2, (ay + by) / 2), (box["x"], box["y"] + box["h"] / 2)


def open_print(page, how):
    page.evaluate(STUB_PRINT)
    if how == "p":
        page.keyboard.press("p")
        page.wait_for_function("!!document.querySelector('.sp-print .sp-print-page')")
    else:
        page.evaluate("dispatchEvent(new Event('beforeprint'))")


@pytest.mark.parametrize("how", ["p", "beforeprint"])
def test_print_includes_writing_and_added_pages(browser, generic_dir, how):
    with session(browser, proposal(generic_dir, "#p03")) as page:
        mid, edge = prepare(page)
        open_print(page, how)
        info = pages_info(page)
        assert len(info) == 10
        assert [i for i, p in enumerate(info) if p["blank"]] == [3]
        assert info[3]["target"] is False and info[2]["target"] is True
        assert [i for i, p in enumerate(info) if p["ink"]] == [2, 3]
        assert ink_alpha(page, 2, *mid) == 255
        assert ink_alpha(page, 3, *edge) == 255
        assert ink_alpha(page, 2, 100, 900) == 0 and ink_alpha(page, 3, 1800, 1000) == 0   # 離れた所は透明
        assert ink_alpha(page, 0, *mid) == -1                                               # 書き込みのないページに層はない
        css = page.evaluate("(() => { const c = document.querySelector('.sp-print-ink'); const s = getComputedStyle(c);"
                            " return [c.width, c.height, s.position, s.left, s.top, s.width, s.height]; })()")
        assert css == [1920, 1080, "absolute", "0px", "0px", "1920px", "1080px"]
        page.evaluate("dispatchEvent(new Event('afterprint'))")
        assert page.locator(".sp-print").count() == 0


def test_cmd_p_matches_p(browser, generic_dir):
    with session(browser, proposal(generic_dir, "#p03")) as page:
        prepare(page)
        open_print(page, "p")
        by_p = pages_info(page)
        page.evaluate("dispatchEvent(new Event('afterprint'))")
        open_print(page, "beforeprint")
        assert pages_info(page) == by_p and len(by_p) == 10
        page.evaluate("dispatchEvent(new Event('afterprint'))")


def test_print_unchanged_without_writing(browser, generic_dir):
    with session(browser, proposal(generic_dir, "#p03")) as page:
        open_print(page, "p")
        info = pages_info(page)
        assert len(info) == 9
        assert all(not p["blank"] and p["target"] and p["ink"] == 0 for p in info)
        assert page.locator(".sp-print canvas").count() == 0
        page.evaluate("dispatchEvent(new Event('afterprint'))")


def fire_unload(page):
    return page.evaluate("(() => { const e = new Event('beforeunload', { cancelable: true }); dispatchEvent(e); return e.defaultPrevented; })()")


def test_beforeunload_only_when_something(browser, generic_dir):
    with session(browser, proposal(generic_dir, "#p03")) as page:
        assert fire_unload(page) is False
        page.keyboard.press("d")
        stroke(page, LINE)
        assert fire_unload(page) is True
        page.keyboard.press("e")
        assert writing(page)["count"] == 0
        assert fire_unload(page) is False
        tool(page, ADD_BTN).click()                       # 追加ページだけ（書き込みなし）
        assert fire_unload(page) is True


def toast_text(page):
    el = page.query_selector(".sp-toast")
    return el.inner_text() if el else None


def test_stay_notice(browser, generic_dir):
    with session(browser, proposal(generic_dir, "#p03")) as page:
        fire_unload(page)
        page.wait_for_timeout(450)
        assert toast_text(page) != STAY                    # 何もないときは出さない
        page.keyboard.press("d")
        stroke(page, LINE)
        fire_unload(page)
        page.wait_for_timeout(450)
        assert toast_text(page) == STAY
    with session(browser, proposal(generic_dir, "#p03")) as page:
        page.keyboard.press("d")
        stroke(page, LINE)
        page.evaluate("Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => 'hidden' })")
        fire_unload(page)
        page.wait_for_timeout(450)
        assert toast_text(page) != STAY


def test_thumbnails_still_without_writing(browser, generic_dir):
    with session(browser, proposal(generic_dir, "#p03")) as page:
        prepare(page)
        page.keyboard.press("o")
        page.wait_for_selector(".sp-thumb")
        assert page.locator(".sp-thumb canvas, .sp-thumb .sp-ink").count() == 0
        page.keyboard.press("Escape")
        page.keyboard.press("t")
        assert page.locator(".sp-side canvas, .sp-side-item canvas, .sp-side .sp-ink").count() == 0


TEXT_FIELD = "textarea.sp-write-text"


def open_field(page, text):
    """右クリックで文字の欄を開き、Enter を押さずに text を打つ。"""
    page.keyboard.press("d")
    page.mouse.click(400, 300, button="right")
    page.wait_for_selector(TEXT_FIELD)
    if text:
        page.keyboard.type(text)
    return page.evaluate("""() => { const r = document.querySelector('.sp-ink').getBoundingClientRect();
      return [(400 - r.left) * 1920 / r.width, (300 - r.top) * 1080 / r.height]; }""")


def text_opaque_somewhere(page, index, origin):
    """印刷用の index ページの書き込みの層の、文字の置き場所のまわりに不透明な画素があるか。"""
    return page.evaluate("""([i, ox, oy]) => {
      const c = document.querySelectorAll('.sp-print .sp-print-page')[i].querySelector('canvas.sp-print-ink');
      if (!c) return false;
      const d = c.getContext('2d').getImageData(Math.round(ox), Math.round(oy), 120, 60).data;
      for (let k = 3; k < d.length; k += 4) if (d[k] > 0) return true;
      return false; }""", [index, origin[0], origin[1]])


@pytest.mark.parametrize("how", ["button", "beforeprint"])
def test_open_text_field_is_printed(browser, generic_dir, how):
    with session(browser, proposal(generic_dir, "#p03")) as page:
        origin = open_field(page, "未確定の文字")
        page.evaluate(STUB_PRINT)
        if how == "button":
            page.locator(".sp-controls button", has_text="P PDF").click()
            page.wait_for_function("!!document.querySelector('.sp-print .sp-print-page')")
        else:
            page.evaluate("dispatchEvent(new Event('beforeprint'))")
        assert page.locator(".sp-print canvas.sp-print-ink").count() == 1
        assert text_opaque_somewhere(page, 2, origin)
        assert page.locator(TEXT_FIELD).count() == 0           # 確定して欄は閉じる
        page.evaluate("dispatchEvent(new Event('afterprint'))")


def test_beforeunload_counts_open_text_field(browser, generic_dir):
    with session(browser, proposal(generic_dir, "#p03")) as page:
        open_field(page, "")
        assert fire_unload(page) is False                      # 空の欄は何も残さない
    with session(browser, proposal(generic_dir, "#p03")) as page:
        open_field(page, "未確定")
        assert fire_unload(page) is True


def test_help_lists_writing_keys(browser, generic_dir):
    with session(browser, proposal(generic_dir, "#p03")) as page:
        page.keyboard.press("?")
        text = page.inner_text(".sp-help")
        for word in ("書き込みを始める・終える", "Ctrl＋Z", "右クリック", "ダブルクリック", "Delete・Backspace"):
            assert word in text, word


@pytest.mark.webkit
def test_writing_webkit(webkit_browser, generic_dir):
    """Safari でも、□・文字・選んで動かす・白紙を足すが動き、PDF の箱に書き込みの層が入る。"""
    with session(webkit_browser, proposal(generic_dir, "#p03")) as page:
        page.keyboard.press("d")
        stroke(page, rough_rect(300, 250, 400, 250))
        assert writing(page)["objects"][-1]["t"] == "rect"
        page.mouse.click(1000, 400, button="right")
        page.keyboard.type("メモ")
        page.keyboard.press("Enter")
        assert writing(page)["objects"][-1]["t"] == "text"
        page.mouse.dblclick(300, 375)                      # □ の左辺
        assert writing(page)["selected"] >= 0
        page.mouse.move(300, 375)
        page.mouse.down()
        page.mouse.move(340, 395, steps=4)
        page.mouse.up()
        tool(page, ADD_BTN).click()
        assert page.evaluate("__sp.state().add") is not None
        page.keyboard.press("d")
        page.evaluate(STUB_PRINT)
        page.keyboard.press("p")
        page.wait_for_function("!!document.querySelector('.sp-print .sp-print-page')")
        info = pages_info(page)
        assert len(info) == 10 and info[3]["blank"] and info[2]["ink"] == 1
