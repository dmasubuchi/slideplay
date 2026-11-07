"""書き込み（D）の入力・表示まわりの試験。

どのデッキでも使える。書けるのはマウス・Apple Pencil（pointerType "pen"）で、指では書かない。線はスライドごとに舞台の座標で覚え、
ペンを終えても残る。PDF・縮小一覧には入らない。見本は examples/generic/motion.html（m02 段階あり、m06 リンクあり）。
"""
import json

import pytest

from test_motion import opened, settle, where
from test_swipe import finger_page, swipe


@pytest.fixture
def moving(browser):
    return lambda url, **kw: opened(browser, url, "no-preference", **kw)


@pytest.fixture
def still(browser):
    return lambda url, **kw: opened(browser, url, "reduce", **kw)


def motion_url(generic_dir, suffix=""):
    return (generic_dir / "motion.html").as_uri() + suffix


def pen(page):
    return page.evaluate("__sp.writing()")


def draw(page, points):
    """マウスで points（画面の座標）をなぞる。"""
    page.mouse.move(*points[0])
    page.mouse.down()
    for p in points[1:]:
        page.mouse.move(*p, steps=4)
    page.mouse.up()


LINE = [(500, 300), (700, 320), (900, 340)]


def ink_alpha(page, x, y):
    """画面の (x, y) にあたる、線の層の画素の不透明度（0〜255）。"""
    return page.evaluate("""([x, y]) => {
      const ink = document.querySelector('.sp-ink'); if (!ink) return 0;
      const r = ink.getBoundingClientRect(), k = ink.width / r.width;
      const px = ink.getContext('2d').getImageData(Math.round((x - r.left) * k), Math.round((y - r.top) * k), 1, 1).data;
      return px[3]; }""", [x, y])


def pointer(page, kind, type_, x, y):
    page.evaluate("""([kind, type, x, y]) => {
      const ink = document.querySelector('.sp-ink');
      ink.dispatchEvent(new PointerEvent(type, { pointerType: kind, pointerId: 7, isPrimary: true, bubbles: true,
        clientX: x, clientY: y, button: type === 'pointermove' ? -1 : 0, buttons: type === 'pointerup' ? 0 : 1 })); }""", [kind, type_, x, y])


def synthetic_line(page, kind):
    pointer(page, kind, "pointerdown", 500, 300)
    pointer(page, kind, "pointermove", 600, 320)
    pointer(page, kind, "pointermove", 700, 340)
    pointer(page, kind, "pointerup", 700, 340)


def test_d_toggles_pen(still, generic_dir):
    with still(motion_url(generic_dir, "#m03")) as page:
        page.keyboard.press("d")
        assert pen(page)["active"] is True
        assert page.locator('.sp-controls button', has_text="D 書き込み").get_attribute("aria-pressed") == "true"
        assert page.locator(".sp-write-tools").is_visible()
        page.keyboard.press("d")
        assert pen(page)["active"] is False
        assert not page.locator(".sp-write-tools").is_visible()


def test_draw_with_mouse(still, generic_dir):
    with still(motion_url(generic_dir, "#m03")) as page:
        page.keyboard.press("d")
        draw(page, LINE)
        assert pen(page)["count"] == 1
        assert ink_alpha(page, 700, 300) > 0
        assert ink_alpha(page, 700, 600) == 0


def test_pen_and_finger_input(still, generic_dir):
    with still(motion_url(generic_dir, "#m03")) as page:
        page.keyboard.press("d")
        synthetic_line(page, "pen")
        assert pen(page)["count"] == 1
        synthetic_line(page, "touch")
        assert pen(page)["count"] == 1                     # 指では書かない


def test_drawing_over_link_does_not_follow(still, generic_dir):
    with still(motion_url(generic_dir, "#m06")) as page:
        page.keyboard.press("d")
        b = page.locator('#stage [data-link="0"]').bounding_box()
        x, y = b["x"] + b["width"] / 2, b["y"] + b["height"] / 2
        draw(page, [(x, y), (x + 40, y + 10)])
        page.mouse.click(x, y)
        assert where(page) == ("m06", 0) and page.evaluate("location.hash") == "#m06"
        assert page.evaluate("__sp.overlay()") == "none"
        assert pen(page)["count"] == 1                     # 動かさずに押しただけでは何も描かない（動かして引いた1本だけ）


def test_e_clears_current_slide_only(still, generic_dir):
    with still(motion_url(generic_dir, "#m03")) as page:
        page.keyboard.press("d")
        draw(page, LINE)
        page.keyboard.press("ArrowDown")
        draw(page, LINE)
        assert where(page) == ("m04", 0) and pen(page)["count"] == 1
        page.keyboard.press("e")
        assert pen(page)["count"] == 0
        page.keyboard.press("ArrowUp")
        assert where(page) == ("m03", 0) and pen(page)["count"] == 1


def test_e_without_pen_does_nothing(still, generic_dir):
    with still(motion_url(generic_dir, "#m03")) as page:
        page.keyboard.press("d")
        draw(page, LINE)
        page.keyboard.press("d")
        page.keyboard.press("e")
        assert pen(page)["count"] == 1


def test_escape_order(still, generic_dir):
    with still(motion_url(generic_dir, "#m03")) as page:
        page.keyboard.press("n")
        page.keyboard.press("d")
        page.keyboard.press("?")
        assert page.evaluate("__sp.overlay()") == "help"
        page.keyboard.press("Escape")
        assert page.evaluate("__sp.overlay()") == "none" and pen(page)["active"] is True
        page.keyboard.press("Escape")
        assert pen(page)["active"] is False and page.locator(".sp-notes").count() == 1
        page.keyboard.press("Escape")
        assert page.locator(".sp-notes").count() == 0


def test_lines_stay_after_pen_off(still, generic_dir):
    with still(motion_url(generic_dir, "#m03")) as page:
        page.keyboard.press("d")
        draw(page, LINE)
        page.keyboard.press("d")
        assert ink_alpha(page, 700, 300) > 0
        page.keyboard.press("ArrowDown")
        assert ink_alpha(page, 700, 300) == 0              # 別のスライドには出ない
        page.keyboard.press("ArrowUp")
        assert pen(page)["count"] == 1 and ink_alpha(page, 700, 300) > 0


def test_stroke_cut_on_move(still, generic_dir):
    with still(motion_url(generic_dir, "#m03")) as page:
        page.keyboard.press("d")
        page.mouse.move(500, 300)
        page.mouse.down()
        page.mouse.move(700, 320, steps=4)
        page.keyboard.press("ArrowDown")                   # 押したまま次のスライドへ
        page.mouse.move(900, 600, steps=4)
        page.mouse.up()
        assert where(page) == ("m04", 0) and pen(page)["count"] == 0
        page.keyboard.press("ArrowUp")
        assert pen(page)["count"] == 1
        assert ink_alpha(page, 600, 310) > 0 and ink_alpha(page, 900, 600) == 0


def test_ink_follows_stage(still, generic_dir):
    def same_rect(page):
        a = page.locator(".sp-ink").bounding_box()
        b = page.locator("#stage").bounding_box()
        return all(abs(a[k] - b[k]) <= 1 for k in ("x", "y", "width", "height"))
    with still(motion_url(generic_dir, "#m03")) as page:
        page.keyboard.press("d")
        draw(page, LINE)
        assert same_rect(page)
        page.keyboard.press("n")
        assert same_rect(page)
        page.keyboard.press("t")
        assert same_rect(page)
        page.set_viewport_size({"width": 1200, "height": 800})
        page.wait_for_timeout(100)
        assert same_rect(page)
        assert pen(page)["count"] == 1


def test_no_ink_in_thumbnails(still, generic_dir):
    with still(motion_url(generic_dir, "#m03")) as page:
        page.keyboard.press("d")
        draw(page, LINE)
        page.keyboard.press("o")
        assert page.locator(".sp-thumb canvas, .sp-thumb .sp-ink").count() == 0
        page.keyboard.press("Escape")
        assert pen(page)["active"] is True and pen(page)["count"] == 1


def test_ink_in_print(still, generic_dir):
    """PDF には書き込みが入る。書き終えても残り、印刷を終えても書き込みはそのまま。"""
    with still(motion_url(generic_dir, "#m03")) as page:
        page.keyboard.press("d")
        draw(page, LINE)
        page.evaluate("void (window.print = () => {})")
        page.keyboard.press("p")
        page.wait_for_function("!!document.querySelector('.sp-print .sp-print-page')")
        assert page.locator(".sp-print canvas.sp-print-ink").count() == 1
        page.evaluate("dispatchEvent(new Event('afterprint'))")
        assert pen(page)["active"] is True and pen(page)["count"] == 1


def test_swipe_disabled_while_pen(browser, generic_dir):
    with finger_page(browser, motion_url(generic_dir, "#m03")) as page:
        page.keyboard.press("d")
        swipe(page, (960, 800), (960, 300))
        assert where(page) == ("m03", 0)


def test_keys_move_while_pen(still, generic_dir):
    with still(motion_url(generic_dir, "#m03")) as page:
        page.keyboard.press("d")
        page.keyboard.press("ArrowDown")
        assert where(page) == ("m04", 0) and pen(page)["active"] is True


def test_controls_not_shown_by_mouse_while_pen(still, generic_dir):
    with still(motion_url(generic_dir, "#m03")) as page:
        assert page.locator(".sp-controls.sp-on").count() == 0
        page.keyboard.press("d")
        draw(page, [(500, 840), (800, 845)])               # 舞台の下の端の近く
        assert page.locator(".sp-controls.sp-on").count() == 0
        assert page.locator(".sp-write-tools").is_visible()
        page.locator(".sp-write-tools button", has_text="書き込みを終える").click()
        assert pen(page)["active"] is False
        page.mouse.move(700, 850)
        assert page.locator(".sp-controls.sp-on").count() == 1


def test_controls_always_mode_kept_while_pen(still, generic_dir):
    with still(motion_url(generic_dir, "#m03"), settings=json.dumps({"controls": "always"})) as page:
        page.keyboard.press("d")
        assert pen(page)["active"] is True
        draw(page, LINE)
        assert page.locator(".sp-controls.sp-on").count() == 1
        assert json.loads(page.evaluate("localStorage.getItem('sp-settings-v1')"))["controls"] == "always"


def test_motion_off_keeps_ink(moving, generic_dir):
    with moving(motion_url(generic_dir, "#m03")) as page:
        page.keyboard.press("d")
        draw(page, LINE)
        page.keyboard.press("d")
        page.keyboard.press("?")
        page.locator('.sp-help [data-sp-motion="off"]').click()
        page.keyboard.press("Escape")
        assert pen(page)["count"] == 1 and ink_alpha(page, 700, 300) > 0


def test_pen_settles_entry(moving, generic_dir):
    with moving(motion_url(generic_dir, "#m03")) as page:
        page.keyboard.press("ArrowDown")
        settle(page)
        assert page.evaluate("__sp.entry().state") == "playing"
        page.keyboard.press("d")
        assert page.evaluate("__sp.entry().state") == "settled"


def test_toolbar_works_without_keyboard(still, generic_dir):
    with still(motion_url(generic_dir, "#m03")) as page:
        page.locator(".sp-controls button", has_text="D 書き込み").dispatch_event("click")
        assert pen(page)["active"] is True
        draw(page, LINE)
        assert pen(page)["count"] == 1
        page.locator(".sp-write-tools button", has_text="全部消す").click()
        assert pen(page)["count"] == 0
        page.locator(".sp-write-tools button", has_text="書き込みを終える").click()
        assert pen(page)["active"] is False


def test_pen_works_on_unchosen_deck(still, generic_dir):
    with still((generic_dir / "proposal.html").as_uri() + "#p03") as page:
        page.keyboard.press("d")
        draw(page, LINE)
        assert pen(page)["count"] == 1


def test_help_lists_d(still, generic_dir):
    with still((generic_dir / "proposal.html").as_uri()) as page:
        page.keyboard.press("?")
        rows = page.evaluate("Array.from(document.querySelectorAll('.sp-help-row'), r => [Array.from(r.querySelectorAll('.sp-key'), k => k.textContent), r.querySelector('.sp-help-text').textContent])")
    assert [["D"], "書き込みを始める・終える（書き込みの間は E で今のページの書き込みを全部消す）"] in rows


# ---- ペンの間は、キーボードでも舞台のリンクを開かない ----

def focus_link(page):
    page.evaluate("document.querySelector('#stage [data-link=\"0\"]').focus()")
    assert page.evaluate("document.activeElement.getAttribute('data-link')") == "0"


def test_enter_on_focused_link_with_pen(still, generic_dir):
    with still(motion_url(generic_dir, "#m06")) as page:
        focus_link(page)                                   # 焦点を置いてから D
        page.keyboard.press("d")
        page.keyboard.press("Enter")
        assert where(page) == ("m06", 0) and pen(page)["active"] is True


def test_tab_into_link_after_pen(still, generic_dir):
    with still(motion_url(generic_dir, "#m06")) as page:
        page.keyboard.press("d")                           # D のあとで Tab で舞台のリンクへ
        for _ in range(20):
            page.keyboard.press("Tab")
            if page.evaluate("document.activeElement.getAttribute('data-link')") == "0":
                break
        page.keyboard.press("Enter")
        assert where(page) == ("m06", 0) and pen(page)["active"] is True
        assert page.evaluate("__sp.overlay()") == "none"


def test_more_link_space_with_pen(still, generic_dir):
    # 補足のリンク（role=button）も、Space・Enter で開かない
    with still(motion_url(generic_dir, "#m06")) as page:
        page.keyboard.press("d")
        page.evaluate("document.querySelector('#stage [data-link=\"1\"]').focus()")
        page.keyboard.press("Enter")
        assert page.evaluate("__sp.overlay()") == "none"
