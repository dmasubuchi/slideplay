"""一覧つきの画面（T）の試験。左に全スライドの縮小の列、右に今のスライドを大きく置く。

見るのは外から見える結果だけ：画面の要素（.sp-side・.sp-side-item・.sp-side-section・.sp-controls・.sp-toast・.sp-notes・.sp-linkpanel）の位置、
localStorage の設定、試験用の窓口 window.__sp、切り替えの途中の画面（止めて撮る）。

試験の決め事：
- 設定は localStorage に先に入れてから開く（読み込みのたびに入れ直す）。操作ボタンは「いつも出す」
- 汎用の見本 examples/generic/proposal.html（9枚、節 3つ）と、続けて開くデッキ minimal.html（1枚）を使う
- 切り替えの途中の画像は tests/test_motion.py の止めて撮る道具（pause_animations・screenshot・settle）で撮る。
  「列が止まって見える」は、途中の画像の列の部分が、動きが終わったあとの画像の列の部分と各画素 1 以内で同じことで見る
  （動く前とは比べない：今の印が移り、End では列がスクロールするため）
"""
import json
from contextlib import contextmanager

import numpy as np
import pytest

from helpers import page_session
from pdf_check import make_pdf, missing_parts, pdf_pages, stage_image
from test_motion import opened, pause_animations, resume_animations, screenshot, settle
from test_swipe import finger_page, swipe

SETTINGS_KEY = "sp-settings-v1"
MSG_NARROW = "画面が狭いので、一覧つきの画面は使えません"
SECTION_TITLES = ["現状と課題", "ご提案の内容", "進め方と費用"]
CATALOG_MID_PX, SIDE_MIN_CENTER_PX = 760, 400


# ---- 試験の道具 ----

def proposal(generic_dir, suffix=""):
    return (generic_dir / "proposal.html").as_uri() + suffix


@contextmanager
def session(browser, url, settings=None, viewport=(1440, 900)):
    """設定（既定は操作ボタンをいつも出す）を localStorage に入れてから url を開く。pageerror があれば失敗（page_session）。"""
    value = json.dumps({"controls": "always", "notes": False, **(settings or {})})
    with page_session(browser, "about:blank", viewport=viewport) as page:
        page.set_default_timeout(10000)
        page.add_init_script(f"try {{ localStorage.setItem({json.dumps(SETTINGS_KEY)}, {json.dumps(value)}); }} catch (e) {{}}")
        page.goto(url)
        if "render" not in url:
            page.wait_for_function("!!window.__sp")
        yield page


def rect(page, selector):
    """最初の要素の矩形（なければ None）。"""
    return page.evaluate("""(s) => { const e = document.querySelector(s); if (!e) return null;
        const r = e.getBoundingClientRect(); return {left: r.left, top: r.top, right: r.right, bottom: r.bottom, width: r.width, height: r.height}; }""", selector)


def saved(page):
    return json.loads(page.evaluate(f"localStorage.getItem({json.dumps(SETTINGS_KEY)})"))


def where(page):
    s = page.evaluate("__sp.state()")
    return s["id"], s["step"]


def state_index(page):
    return page.evaluate("__sp.state().index")


def toast_text(page):
    el = page.query_selector(".sp-toast")
    return el.inner_text() if el else None


def inside(inner, outer, tol=0.5):
    return inner["left"] >= outer["left"] - tol and inner["right"] <= outer["right"] + tol \
        and inner["top"] >= outer["top"] - tol and inner["bottom"] <= outer["bottom"] + tol


# ---- 1. 出す・戻す ----

def test_t_shows_list_and_fits_stage(browser, generic_dir):
    with session(browser, proposal(generic_dir)) as page:
        width = page.evaluate("innerWidth")
        plain = rect(page, "#stage")
        assert page.locator(".sp-side").count() == 0
        page.keyboard.press("t")
        assert page.locator(".sp-side").count() == 1
        assert page.locator(".sp-side .sp-side-item").count() == 9
        assert page.locator(".sp-side .sp-side-section").all_inner_texts() == SECTION_TITLES
        assert page.locator(".sp-controls button", has_text="T 一覧つき").get_attribute("aria-pressed") == "true"
        assert saved(page)["side"] is True
        side, stage, bar = rect(page, ".sp-side"), rect(page, "#stage"), rect(page, ".sp-controls")
        assert side["left"] == 0 and 180 <= side["width"] <= 300 and side["width"] == pytest.approx(max(180, min(300, width * 0.18)), abs=0.5)
        assert stage["left"] >= side["right"] - 0.5 and stage["right"] <= width + 0.5
        assert stage["width"] / stage["height"] == pytest.approx(16 / 9, rel=0.01)
        assert bar["left"] == pytest.approx(side["right"], abs=0.5)
        page.keyboard.press("t")
        assert page.locator(".sp-side").count() == 0
        assert rect(page, "#stage") == plain
        assert page.locator(".sp-controls button", has_text="T 一覧つき").get_attribute("aria-pressed") == "false"
        assert saved(page)["side"] is False


def test_button_toggles_like_key(browser, generic_dir):
    with session(browser, proposal(generic_dir)) as page:
        page.locator(".sp-controls button", has_text="T 一覧つき").click()
        assert page.locator(".sp-side").count() == 1
        page.locator(".sp-controls button", has_text="T 一覧つき").click()
        assert page.locator(".sp-side").count() == 0


def test_t_works_while_an_overlay_is_open(browser, generic_dir):
    # N と同じく、重なり（縮小一覧）が開いていても効く
    with session(browser, proposal(generic_dir)) as page:
        page.keyboard.press("o")
        assert page.evaluate("__sp.overlay()") == "overview"
        page.keyboard.press("t")
        assert page.locator(".sp-side").count() == 1
        assert page.evaluate("__sp.overlay()") == "overview"


def test_help_lists_t(browser, generic_dir):
    with session(browser, proposal(generic_dir)) as page:
        page.keyboard.press("?")
        texts = page.locator(".sp-help-row").all_inner_texts()
        assert any(t.replace("\n", " ").split(" ")[0] == "T" and "一覧つきの画面にする・戻す" in t for t in texts)


# ---- 2. 今の印 ----

def test_current_marker_follows_moves_without_focus(browser, generic_dir):
    with session(browser, proposal(generic_dir)) as page:
        page.keyboard.press("t")
        for _ in range(7):
            page.keyboard.press("Shift+ArrowDown")
        assert page.locator(".sp-side-item.sp-current").evaluate_all("els => els.map(e => e.dataset.index)") == ["7"]
        item, side = rect(page, '.sp-side-item[data-index="7"]'), rect(page, ".sp-side")
        assert inside(item, side)
        assert page.evaluate("!!document.activeElement && !document.activeElement.closest('.sp-side')")
        assert page.evaluate("Array.from(document.querySelectorAll('.sp-side-item')).every(e => e.tabIndex < 0)")
        page.keyboard.press("Home")                                         # 戻ると、列の上へ動く
        assert page.locator(".sp-side-item.sp-current").evaluate_all("els => els.map(e => e.dataset.index)") == ["0"]
        assert inside(rect(page, '.sp-side-item[data-index="0"]'), rect(page, ".sp-side"))


def test_click_item_jumps_and_records(browser, generic_dir):
    with session(browser, proposal(generic_dir, "#p02")) as page:
        page.keyboard.press("t")
        page.locator('.sp-side-item[data-index="4"]').click()
        assert page.evaluate("__sp.state()") == {"kind": "deck", "index": 4, "step": 0, "id": "p04", "add": None, "label": "5 / 9"}
        assert page.evaluate("document.activeElement === document.body || !document.activeElement.closest('.sp-side')")
        after_click = page.evaluate("__sp.places()")
    with session(browser, proposal(generic_dir, "#p02")) as page:           # 縮小一覧（O）で選んだときと、直近の場所が同じ
        page.keyboard.press("o")
        page.locator('.sp-thumb[data-index="4"]').click()
        after_overview = page.evaluate("__sp.places()")

    def refs(p):
        return [(i["ref"], i["step"]) for i in p["items"]], p["pos"]
    assert refs(after_click) == refs(after_overview) == ([("p02", 0), ("p04", 0)], 1)


# ---- 3. ノート・知らせ・リンクを表示は中央の領域 ----

def test_with_notes_and_links_stay_in_center(browser, generic_dir):
    with session(browser, proposal(generic_dir)) as page:
        page.keyboard.press("t")
        page.keyboard.press("n")
        side, notes, stage, bar = rect(page, ".sp-side"), rect(page, ".sp-notes"), rect(page, "#stage"), rect(page, ".sp-controls")
        assert side["right"] <= stage["left"] + 0.5 and stage["right"] <= notes["left"] + 0.5
        assert bar["left"] == pytest.approx(side["right"], abs=0.5) and bar["right"] == pytest.approx(notes["left"], abs=0.5)
        page.keyboard.press("ArrowUp")                                      # 先頭より前：知らせ
        toast = rect(page, ".sp-toast")
        assert toast is not None
        assert (toast["left"] + toast["right"]) / 2 == pytest.approx((side["right"] + notes["left"]) / 2, abs=1)
        assert inside(toast, {"left": side["right"], "right": notes["left"], "top": 0, "bottom": 900})
        page.evaluate("location.hash = '#p04'")
        page.wait_for_function("__sp.state().id === 'p04'")
        page.keyboard.press("l")
        assert page.evaluate("__sp.overlay()") == "links"
        panel = rect(page, ".sp-linkpanel")
        assert inside(panel, {"left": side["right"], "right": notes["left"], "top": 0, "bottom": 900})
        page.keyboard.press("Escape")
        page.keyboard.press("n")                                            # ノートを閉じると、舞台が広がる
        assert page.locator(".sp-notes").count() == 0
        wide = rect(page, "#stage")
        assert wide["right"] > stage["right"] + 20 and wide["left"] >= side["right"] - 0.5
        assert rect(page, ".sp-controls")["right"] == pytest.approx(1440, abs=0.5)


def test_toast_centers_on_screen_without_side(browser, generic_dir):
    # 列もノートもないときは、今までどおり画面の中央
    with session(browser, proposal(generic_dir)) as page:
        page.keyboard.press("ArrowUp")
        toast = rect(page, ".sp-toast")
        assert (toast["left"] + toast["right"]) / 2 == pytest.approx(720, abs=1)


@pytest.mark.parametrize("viewport,has_side", [((760, 900), False), ((1000, 700), True)])
def test_small_screen_with_notes_and_links_usable(browser, generic_dir, viewport, has_side):
    with session(browser, proposal(generic_dir, "#p04"), {"side": True, "notes": True}, viewport=viewport) as page:
        width, height = viewport
        side_w = max(180, min(300, width * 0.18))
        notes = rect(page, ".sp-notes")
        assert (page.locator(".sp-side").count() == 1) == has_side
        assert has_side == (width - side_w - notes["width"] >= SIDE_MIN_CENTER_PX)
        stage = rect(page, "#stage")
        assert stage["right"] <= notes["left"] + 0.5 and stage["left"] >= -0.5
        if has_side:
            assert rect(page, ".sp-side")["right"] <= stage["left"] + 0.5
        for b in page.locator(".sp-controls button").all():                  # 帯のボタンはどれも画面の中
            r = b.bounding_box()
            assert r["x"] >= -0.5 and r["x"] + r["width"] <= width + 0.5 and r["y"] >= -0.5 and r["y"] + r["height"] <= height + 0.5
        page.locator(".sp-controls button", has_text="O 一覧").click()
        assert page.evaluate("__sp.overlay()") == "overview"
        page.keyboard.press("Escape")
        page.keyboard.press("l")
        panel = rect(page, ".sp-linkpanel")
        left = rect(page, ".sp-side")["right"] if has_side else 0
        assert inside(panel, {"left": left, "right": notes["left"], "top": 0, "bottom": height})
        page.locator('.sp-linkframe[data-index="0"]').click()                # 枠が押せる（p04 の 0 番は p07 へ）
        assert where(page) == ("p07", 0)


def long_copy_text(page, text):
    page.evaluate("(t) => { slideDeck.info.slides.find(s => s.id === 'p04').links[4].text = t; }", text)


def test_toast_stays_on_screen_with_notes_on_narrow_screen(browser, generic_dir):
    # 390px＋ノート：中央の領域は 70px しかない。知らせは中央に寄せず、画面の中で全文が読める
    with session(browser, proposal(generic_dir), {"notes": True, "controls": "never"}, viewport=(390, 844)) as page:
        page.keyboard.press("ArrowUp")
        toast = rect(page, ".sp-toast")
        assert toast["left"] >= 0 and toast["right"] <= 390
        assert page.evaluate("(() => { const e = document.querySelector('.sp-toast'); return e.scrollWidth <= e.clientWidth; })()")


def test_long_toast_stays_in_center_with_side_and_notes(browser, generic_dir):
    with session(browser, proposal(generic_dir), {"side": True, "notes": True}, viewport=(900, 900)) as page:
        side, notes = rect(page, ".sp-side"), rect(page, ".sp-notes")
        page.evaluate("location.hash = '#not-found'")
        page.wait_for_selector(".sp-toast")
        toast = rect(page, ".sp-toast")
        assert inside(toast, {"left": side["right"], "right": notes["left"], "top": 0, "bottom": 900})


@pytest.mark.parametrize("side", [False, True])
@pytest.mark.parametrize("text", ["長いコピー文字列の表示を確認します", "とても長いコピー文字列の表示を確認します。" * 6])
def test_link_tags_stay_in_center(browser, generic_dir, side, text):
    with session(browser, proposal(generic_dir, "#p04"), {"side": side, "notes": True, "controls": "never"}, viewport=(900, 900)) as page:
        long_copy_text(page, text)
        page.keyboard.press("l")
        area = {"left": rect(page, ".sp-side")["right"] if side else 0, "right": rect(page, ".sp-notes")["left"], "top": 0, "bottom": 900}
        tags = page.locator(".sp-linktag")
        assert tags.count() > 0
        for i in range(tags.count()):
            box = tags.nth(i).bounding_box()
            r = {"left": box["x"], "right": box["x"] + box["width"], "top": box["y"], "bottom": box["y"] + box["height"]}
            assert inside(r, area), (i, r, area)


@pytest.mark.webkit
@pytest.mark.parametrize("side", [False, True])
def test_webkit_link_tags_and_toast_stay_in_center(webkit_browser, generic_dir, side):
    with session(webkit_browser, proposal(generic_dir, "#p04"), {"side": side, "notes": True, "controls": "never"}, viewport=(900, 900)) as page:
        long_copy_text(page, "長いコピー文字列の表示を確認します")
        page.keyboard.press("l")
        left, right = (rect(page, ".sp-side")["right"] if side else 0), rect(page, ".sp-notes")["left"]
        for box in page.locator(".sp-linktag").evaluate_all("els => els.map(e => { const r = e.getBoundingClientRect(); return [r.left, r.right]; })"):
            assert box[0] >= left - 0.5 and box[1] <= right + 0.5


OVERLAP_SETUP = """() => {
  const links = slideDeck.info.slides.find(s => s.id === 'p04').links;
  links.splice(0, links.length,
    {label: 'A', kind: 'more', title: 'コピー：長いコピー文字列の表示を確認します', text: '補足Aの本文'},
    {label: 'B', kind: 'more', title: '補足B', text: '補足Bの本文'});
  const stage = document.getElementById('stage');
  const r = stage.getBoundingClientRect(), k = r.width / 1920;
  stage.replaceChildren();
  for (const [i, x, y, w, h, label] of [[0, 380, 400, 40, 20, 'A'], [1, 285, 445, 45, 20, 'B']]) {
    const e = document.createElement('span'); e.dataset.link = i; e.textContent = label;
    Object.assign(e.style, {position: 'absolute', left: (x - r.left) / k + 'px', top: (y - r.top) / k + 'px',
      width: w / k + 'px', height: h / k + 'px', fontSize: 16 / k + 'px', lineHeight: h / k + 'px'});
    stage.append(e);
  }
}"""


def check_shifted_tag_clear(browser, generic_dir):
    # 札A を横にずらして中央の領域に収めたあと、Bの枠・Bの札・隅の一覧に重ならない（重なると、押した所でBが開く）
    with session(browser, proposal(generic_dir, "#p04"), {"side": True, "notes": True, "controls": "never"}, viewport=(900, 900)) as page:
        page.evaluate(OVERLAP_SETUP)
        page.keyboard.press("l")
        area = {"left": rect(page, ".sp-side")["right"], "right": rect(page, ".sp-notes")["left"], "top": 0, "bottom": 900}
        a = rect(page, '.sp-linkframe[data-index="0"] .sp-linktag')
        assert inside(a, area), (a, area)
        for sel in ['.sp-linkframe[data-index="1"]', '.sp-linkframe[data-index="1"] .sp-linktag', ".sp-linkpanel"]:
            o = rect(page, sel)
            assert not (a["left"] < o["right"] and o["left"] < a["right"] and a["top"] < o["bottom"] and o["top"] < a["bottom"]), (sel, a, o)


def test_shifted_link_tag_does_not_cover_other_frame(browser, generic_dir):
    check_shifted_tag_clear(browser, generic_dir)


@pytest.mark.webkit
def test_webkit_shifted_link_tag_does_not_cover_other_frame(webkit_browser, generic_dir):
    check_shifted_tag_clear(webkit_browser, generic_dir)


# ---- 4. 設定と広さ ----

def test_setting_persists_to_next_deck(browser, generic_dir):
    with page_session(browser, proposal(generic_dir), viewport=(1440, 900)) as page:    # 設定を入れ直さずに、続けて開く
        page.wait_for_function("!!window.__sp")
        page.keyboard.press("t")
        assert page.locator(".sp-side").count() == 1
        page.goto((generic_dir / "minimal.html").as_uri())
        page.wait_for_function("!!window.__sp")
        assert page.locator(".sp-side").count() == 1
        assert page.locator(".sp-side .sp-side-item").count() == 1


def test_narrow_screen_hides_without_changing_setting(browser, generic_dir):
    with session(browser, proposal(generic_dir), {"side": True}, viewport=(700, 900)) as page:
        assert page.locator(".sp-side").count() == 0
        assert saved(page)["side"] is True
        page.keyboard.press("t")
        assert toast_text(page) == MSG_NARROW
        assert page.locator(".sp-side").count() == 0
        assert saved(page)["side"] is True
        page.set_viewport_size({"width": 1200, "height": 900})
        page.wait_for_selector(".sp-side")
        assert saved(page)["side"] is True
        page.set_viewport_size({"width": 700, "height": 900})               # 狭くなっても設定は変えない
        page.wait_for_selector(".sp-side", state="detached")
        assert saved(page)["side"] is True


def test_narrow_screen_with_setting_off_t_does_not_turn_on(browser, generic_dir):
    with session(browser, proposal(generic_dir), {"side": False}, viewport=(700, 900)) as page:
        page.keyboard.press("t")
        assert toast_text(page) == MSG_NARROW
        assert saved(page)["side"] is False


def test_notes_toggle_reevaluates_room(browser, generic_dir):
    with session(browser, proposal(generic_dir), viewport=(880, 700)) as page:
        page.keyboard.press("t")
        assert page.locator(".sp-side").count() == 1                         # 中央は 880 − 180 = 700
        page.keyboard.press("n")                                             # 880 − 180 − 320 = 380 < 400
        assert page.locator(".sp-notes").count() == 1
        assert page.locator(".sp-side").count() == 0
        assert saved(page)["side"] is True
        stage, notes = rect(page, "#stage"), rect(page, ".sp-notes")
        assert stage["left"] >= -0.5 and stage["right"] <= notes["left"] + 0.5
        page.keyboard.press("n")
        assert page.locator(".sp-side").count() == 1
        assert saved(page)["side"] is True


# ---- 5. 指で払う操作は列の上では扱わない ----

def test_swipe_on_list_does_not_move(browser, generic_dir):
    with finger_page(browser, proposal(generic_dir, "#p03"), viewport=(1180, 820), settings={"controls": "always", "notes": False}) as page:
        page.keyboard.press("t")
        assert page.locator(".sp-side").count() == 1
        before = where(page)
        side = rect(page, ".sp-side")
        assert side["width"] > 60
        swipe(page, (100, 500), (100, 300))                                  # 列の上で上へ（ふつうなら ↓）
        page.wait_for_timeout(150)
        assert where(page) == before
        swipe(page, (side["right"] - 25, 450), (30, 450))                    # 列の上で左へ（ふつうなら →）。横にはスクロールしない列
        page.wait_for_timeout(150)
        assert where(page) == before
        swipe(page, (700, 450), (500, 450))                                  # 舞台の上では、今までどおり動く
        page.wait_for_function("(b) => __sp.state().id !== b", arg=before[0])


# ---- 6. 切り替えの途中でも、列は止まって見える ----

def column_box(page):
    r = rect(page, ".sp-side")
    return (0, 0, int(round(r["right"])), int(round(r["bottom"])))


def mode_colour(img):
    """画像でいちばん多い色。"""
    arr = np.asarray(img.convert("RGB")).reshape(-1, 3)
    colours, counts = np.unique(arr, axis=0, return_counts=True)
    return tuple(int(v) for v in colours[counts.argmax()])


def share_of(img, colour, tol):
    arr = np.asarray(img.convert("RGB")).astype(int)
    return float((np.abs(arr - np.array(colour)).max(axis=2) <= tol).mean())


SLIDE_BG = {"p01": "rgb(250, 110, 110)", "p02": "rgb(110, 200, 110)", "p08": "rgb(110, 110, 250)"}   # 互いに各成分で 60 以上離す
TOL = 14


def paint_slides(page):
    """試験の中だけで、p01・p02・p08 の舞台の背景をはっきり違う色にする（プレイヤーと見本は変えない）。移る先が写ったかを、許容差でも元の色と混ざらずに見分けるため。"""
    page.evaluate("""(bg) => {
        const stage = document.getElementById('stage');
        const paint = () => { const c = bg[__sp.state().id]; if (c) stage.style.background = c; };
        new MutationObserver(paint).observe(stage, { childList: true, subtree: true, attributes: true });
        paint();
    }""", SLIDE_BG)


def check_list_stays_still(page, key, expected):
    """T のあと key を押し、途中で止めて撮る。列の部分が動いたあとと各画素 1 以内で同じ、舞台の部分に移る先の色が写っている。"""
    paint_slides(page)
    page.keyboard.press("t")
    page.evaluate("__sp.motionDone()")
    box = column_box(page)
    stage_box = page.evaluate("(() => { const r = document.getElementById('stage').getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom].map(Math.round); })()")
    source = mode_colour(screenshot(page).crop(tuple(stage_box)))
    page.keyboard.press(key)
    jump = page.evaluate("__sp.motion().kind") == "jump"
    pause_animations(page, 350 if jump else 150)                             # ジャンプは、前のスライドが消えきり、次が薄く現れ始めたあたり
    mid = screenshot(page)
    if jump:
        pause_animations(page, 490)                                          # 次のスライドが現れきる直前（移る先の色を見る）
    late = screenshot(page)
    resume_animations(page)
    settle(page)
    assert where(page)[0] == expected
    end = screenshot(page)
    dest = mode_colour(end.crop(tuple(stage_box)))
    assert max(abs(d - o) for d, o in zip(dest, source)) > TOL * 2, "移る先と元の背景の色が近いと、写ったかを見分けられない"
    a = np.asarray(mid.crop(box)).astype(int)
    b = np.asarray(end.crop(box)).astype(int)
    assert np.abs(a - b).max() <= 1, "動いている間に列が動いて見える"
    assert share_of(late.crop(tuple(stage_box)), dest, TOL) > 0.03, "舞台の部分に移る先のスライドが写っていない"


KEYS = [("ArrowDown", "p02", "#p01"), ("ArrowUp", "p01", "#p02"), ("End", "p08", "#p02")]


def check_switches_at_once(page, key, expected):
    """WebKit の経路（root）で列を出している間は、動かさずにすぐ切り替わる（列が止まって見える・移る先が写る、は動きがないことで満たされる）。

    本物の WebKit は、名前を付けた列の新しい写しを描かず、動きの途中で列が消える（test_webkit_motion_with_list_would_hide_it）。
    列を出していなければ、WebKit でも今までどおり動く。
    """
    page.keyboard.press("t")
    page.evaluate("__sp.motionDone()")
    before = page.evaluate("window.__vtCalls")
    page.keyboard.press(key)
    assert where(page)[0] == expected                                        # 押してすぐ、移る先が舞台に描かれている
    assert page.evaluate("__sp.motion().kind") == "none"
    assert page.evaluate("window.__vtCalls") == before
    assert page.evaluate("document.documentElement.className").find("sp-vt") < 0
    assert page.locator(".sp-side").count() == 1 and page.locator(".sp-side-item.sp-current").evaluate_all("els => els.map(e => e.dataset.index)") == [str(page.evaluate("__sp.state().index"))]
    assert "sp-side" not in page.evaluate("getComputedStyle(document.querySelector('.sp-side')).viewTransitionName")
    page.keyboard.press("t")                                                 # 列を戻すと、WebKit でも動く（動かさないのは列を出している間だけ）
    page.keyboard.press("Home" if expected == "p08" else "End")
    assert page.evaluate("__sp.motion().kind") == "jump"
    settle(page)


@pytest.mark.parametrize("key,expected,start", KEYS)
@pytest.mark.parametrize("path", ["stage", "root"])
def test_list_stays_still_during_motion_stage_and_root(browser, generic_dir, key, expected, start, path):
    with opened(browser, proposal(generic_dir, start), "no-preference", viewport=(1440, 900), settings=json.dumps({"controls": "never", "notes": False})) as page:
        if path == "stage":
            check_list_stays_still(page, key, expected)
        else:                                                                # root：navigator.vendor を WebKit に見せかける（Chromium の上で WebKit の経路を通す）
            page.evaluate("Object.defineProperty(navigator, 'vendor', { get: () => 'Apple Computer, Inc.' })")
            check_switches_at_once(page, key, expected)


@pytest.mark.parametrize("key,expected,start", KEYS)
def test_missing_incoming_slide_is_detected(browser, generic_dir, key, expected, start):
    """負例：移る先の写しだけを隠すと、check_list_stays_still は失敗する（元と先を見分けられない色の見本では通ってしまった）。"""
    with opened(browser, proposal(generic_dir, start), "no-preference", viewport=(1440, 900), settings=json.dumps({"controls": "never", "notes": False})) as page:
        page.add_style_tag(content="html.sp-vt-stage::view-transition-new(sp-stage) { visibility: hidden !important; }")
        with pytest.raises(AssertionError, match="舞台の部分に移る先のスライドが写っていない"):
            check_list_stays_still(page, key, expected)


@pytest.mark.webkit
@pytest.mark.parametrize("viewport", [(820, 1180), (1180, 820)])
@pytest.mark.parametrize("key,expected,start", KEYS)
def test_webkit_list_stays_still_during_motion(webkit_browser, generic_dir, viewport, key, expected, start):
    with opened(webkit_browser, proposal(generic_dir, start), "no-preference", viewport=viewport, settings=json.dumps({"controls": "never", "notes": False})) as page:
        check_switches_at_once(page, key, expected)


@pytest.mark.webkit
@pytest.mark.parametrize("viewport", [(820, 1180), (1180, 820)])
def test_webkit_motion_with_list_would_hide_it(webkit_browser, generic_dir, viewport):
    """D3 の根拠：列に名前を付けて動かすと、本物の WebKit では列が消える（新しい写しが描かれない）。これが直ったら、動かさない決まりを外せる。"""
    with opened(webkit_browser, proposal(generic_dir, "#p01"), "no-preference", viewport=viewport, settings=json.dumps({"controls": "never", "notes": False})) as page:
        page.keyboard.press("t")
        page.evaluate("__sp.motionDone()")
        box = column_box(page)
        page.add_style_tag(content=(
            "html.sp-vt-root .sp-side { view-transition-name: sp-side; }"
            "html.sp-vt-root::view-transition-group(sp-side) { animation: none; }"
            "html.sp-vt-root::view-transition-old(sp-side) { display: none; }"
            "html.sp-vt-root::view-transition-new(sp-side) { animation: none; mix-blend-mode: normal; }"))
        page.evaluate("document.documentElement.classList.add('sp-vt-root')")      # 動かさない決まりを通さずに、同じ経路を直接動かす
        page.evaluate("document.documentElement.classList.add('sp-mv-jump'); window.__vt = document.startViewTransition(() => { location.hash = '#p08'; })")
        pause_animations(page, 350)
        mid = np.asarray(screenshot(page).crop(box))                       # 単色（背景だけ）：列が写っていない
        assert np.ptp(mid.reshape(-1, 3), axis=0).max() == 0, "列が写っている（WebKit が直ったので、motionKind の例外と試験を見直す）"
        resume_animations(page)
        page.evaluate("window.__vt.finished")


@pytest.fixture(scope="module")
def webkit_browser(playwright_instance, request):
    from playwright.sync_api import Error

    try:
        b = playwright_instance.webkit.launch()
    except Error as exc:
        pytest.skip(f"WebKit が起動できない（python3 -m playwright install webkit で入れる）: {str(exc).splitlines()[0][:200]}")
    request.config._webkit_info = {"version": b.version, "note": "Playwright の WebKit（Safari 相当。実機の Safari・iPad ではない）"}
    yield b
    b.close()


# ---- 7. 描画モード・印刷 ----

def test_render_mode_has_no_list(browser, generic_dir):
    with session(browser, proposal(generic_dir, "?render"), {"side": True}) as page:
        page.wait_for_function("document.body.classList.contains('render')")
        assert page.locator(".sp-side").count() == 0
        assert page.locator(".sp-controls").count() == 0


def test_print_hides_list(browser, generic_dir, tmp_path):
    with session(browser, proposal(generic_dir), viewport=(1920, 1080)) as page:
        page.keyboard.press("t")
        assert page.locator(".sp-side").count() == 1
        with_side = make_pdf(page, tmp_path / "with-side.pdf")
        assert page.locator(".sp-side").count() == 1                         # 印刷のあとも列はそのまま
        page.keyboard.press("t")
        without = make_pdf(page, tmp_path / "without.pdf")

        import fitz

        def texts(path):
            with fitz.open(str(path)) as doc:
                return [p.get_text() for p in doc]
        a, b = texts(with_side), texts(without)
        assert len(a) == 9 and a == b
        images = pdf_pages(with_side)
        for i, img in enumerate(images):                                     # 列を閉じた舞台（1920×1080 の等倍）と比べる
            assert missing_parts(img, stage_image(page, i)) == [], f"{i + 1}ページ目に欠けの疑い"
