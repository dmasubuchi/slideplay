"""入場の動き（スライドに入ったとたんに中身が順に出る）の試験。

見るのは試験用の窓口 __sp.entry()（state・style・count・effects・plannedMs）と __sp.entryDone()、舞台の静止画。
入場は規定の順序で「次へ」進んで次のスライドに着いたときだけ再生する。止まった姿は、同じ段階を動きなしで開いた姿と1ピクセルも違わない。
見本は examples/generic/motion.html（entry: "bounce"、point: true。m02 は step:1 の points、m03 bars、m04 stat、m05 flow、m06 bullets とリンク）。
"""
import json

import pytest

import stills
from helpers import deck_with_motion, page_session
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


def entry(page):
    return page.evaluate("__sp.entry()")


def state(page):
    return entry(page)["state"]


def finish(page):
    """送りと入場が終わるまで待つ。"""
    settle(page)
    page.evaluate("__sp.entryDone()")


def stage_shot(page, path):
    return page.locator("#stage").screenshot(path=str(path))


# ---- 1. 再生する操作・しない操作 ----

def click_button(page, text):
    page.locator(".sp-controls button", has_text=text).dispatch_event("click")


PLAYS = {
    "down": ("#m01", lambda p: p.keyboard.press("ArrowDown")),
    "pagedown": ("#m01", lambda p: p.keyboard.press("PageDown")),
    "space": ("#m01", lambda p: p.keyboard.press("Space")),
    "shift-down": ("#m02", lambda p: p.keyboard.press("Shift+ArrowDown")),
    "right-no-forward": ("#m01", lambda p: p.keyboard.press("ArrowRight")),
    "button-next": ("#m01", lambda p: click_button(p, "↓ 次")),
    "button-forward-no-forward": ("#m01", lambda p: click_button(p, "→ 進む")),
}


@pytest.mark.parametrize("name", list(PLAYS))
def test_entry_plays(moving, generic_dir, name):
    start, act = PLAYS[name]
    with moving(motion_url(generic_dir, start)) as page:
        assert state(page) == "none"
        act(page)
        assert state(page) in ("pending", "playing")
        finish(page)
        e = entry(page)
        assert e["state"] == "done" and e["count"] > 0 and e["style"] == "bounce"


@pytest.mark.parametrize("direction, start", [("up", "#m01"), ("left", "#m01")])
def test_entry_plays_on_swipe(browser, generic_dir, direction, start):
    # 上へ払う＝↓、左へ払う＝→（先の場所がないので ↓ と同じ）
    with finger_page(browser, motion_url(generic_dir, start), reduced_motion="no-preference") as page:
        a, b = ((960, 800), (960, 300)) if direction == "up" else ((1400, 540), (500, 540))
        swipe(page, a, b)
        assert where(page) == ("m02", 0)
        assert state(page) in ("pending", "playing", "done")
        page.evaluate("__sp.motionDone()")
        page.evaluate("__sp.entryDone()")
        assert state(page) == "done"


def go_down_and_back(page):
    page.keyboard.press("ArrowDown")
    finish(page)
    page.keyboard.press("ArrowLeft")                     # 直近の場所を戻る（入場しない）
    settle(page)


NOT_PLAYS = {
    "up": ("#m03", lambda p: p.keyboard.press("ArrowUp")),
    "pageup": ("#m03", lambda p: p.keyboard.press("PageUp")),
    "shift-up": ("#m03", lambda p: p.keyboard.press("Shift+ArrowUp")),
    "left": ("#m01", lambda p: (p.keyboard.press("ArrowDown"), finish(p), p.keyboard.press("ArrowLeft"))),
    "right-with-forward": ("#m01", lambda p: (go_down_and_back(p), p.keyboard.press("ArrowRight"))),
    "link-to-adjacent": ("#m06", lambda p: p.locator('#stage [data-link="0"]').click()),
    "overview": ("#m01", lambda p: (p.keyboard.press("o"), p.locator('.sp-thumb[data-index="1"]').click())),
    "home": ("#m03", lambda p: p.keyboard.press("Home")),
    "end": ("#m03", lambda p: p.keyboard.press("End")),
    "hash": ("#m01", lambda p: p.evaluate("location.hash = '#m02'")),
    "reload": ("#m02", lambda p: (p.reload(), p.wait_for_function("!!window.__sp"))),
    "open": ("#m02", lambda p: None),
    "step-only": ("#m02", lambda p: p.keyboard.press("ArrowDown")),
    "down-at-last": ("#m06", lambda p: p.keyboard.press("ArrowDown")),
}


@pytest.mark.parametrize("name", list(NOT_PLAYS))
def test_entry_does_not_play(moving, generic_dir, name):
    start, act = NOT_PLAYS[name]
    with moving(motion_url(generic_dir, start)) as page:
        act(page)
        page.wait_for_timeout(50)
        assert state(page) == "none", name
        settle(page)


def test_entry_after_swipe_right_does_not_play(browser, generic_dir):
    # 右へ払う＝←（直近の場所を戻る）
    with finger_page(browser, motion_url(generic_dir, "#m01"), reduced_motion="no-preference") as page:
        page.keyboard.press("ArrowDown")
        page.evaluate("__sp.motionDone()")
        page.evaluate("__sp.entryDone()")
        swipe(page, (500, 540), (1400, 540))
        assert where(page) == ("m01", 0) and state(page) == "none"
        page.evaluate("__sp.motionDone()")


# ---- 2. 止まった姿は、動きなしの同じ段階と同じ ----

def test_entry_end_matches_still(moving, still, generic_dir, tmp_path):
    with moving(motion_url(generic_dir, "#m01")) as page:
        for sid in ["m02", "m03", "m04", "m05", "m06"]:
            page.keyboard.press("Shift+ArrowDown")
            finish(page)
            assert where(page) == (sid, 0) and state(page) == "done"
            stage_shot(page, tmp_path / f"moving_{sid}.png")
    for sid in ["m02", "m03", "m04", "m05", "m06"]:
        with still(motion_url(generic_dir, "#" + sid)) as page:
            stage_shot(page, tmp_path / f"still_{sid}.png")
        assert stills.diff(tmp_path / f"moving_{sid}.png", tmp_path / f"still_{sid}.png") is None, sid


# ---- 3. 送りとの重なり・時間・型 ----

def test_entry_waits_for_send(moving, generic_dir):
    with moving(motion_url(generic_dir, "#m01")) as page:
        page.keyboard.press("ArrowDown")
        assert state(page) == "pending"                   # 送りの動きの間は、入る前の姿で止めておく
        settle(page)
        assert state(page) in ("playing", "done")
        page.evaluate("__sp.entryDone()")


def test_entry_without_view_transitions(browser, generic_dir):
    with page_session(browser, "about:blank", reduced_motion="no-preference") as page:
        page.add_init_script("delete Document.prototype.startViewTransition;")
        page.goto(motion_url(generic_dir, "#m01"))
        page.wait_for_function("!!window.__sp")
        page.keyboard.press("ArrowDown")
        assert state(page) == "playing"
        page.evaluate("__sp.entryDone()")
        assert state(page) == "done"


def test_entry_time_limit(moving, generic_dir, tmp_path):
    with moving(motion_url(generic_dir, "#m01")) as page:
        for _ in range(5):
            page.keyboard.press("Shift+ArrowDown")
            finish(page)
            assert entry(page)["plannedMs"] <= 1500
    many = {"id": "s2", "type": "bullets", "title": "多い", "items": [f"項目{i}" for i in range(40)]}
    deck = deck_with_motion(generic_dir / "motion.html", tmp_path, {"send": True, "entry": "bounce", "point": False}, name="many.html")
    deck.write_text(deck.read_text(encoding="utf-8").replace(
        "  slides: [\n", "  slides: [\n    { id: 's1', type: 'title', title: '始め', subtitle: '' },\n    " + json.dumps(many, ensure_ascii=False) + ",\n", 1), encoding="utf-8")
    with moving(deck.as_uri() + "#s1") as page:
        page.keyboard.press("ArrowDown")
        finish(page)
        e = entry(page)
        assert e["count"] == 41 and e["plannedMs"] <= 2000


def test_step_hidden_items_are_not_targets(moving, generic_dir):
    with moving(motion_url(generic_dir, "#m01")) as page:
        page.keyboard.press("ArrowDown")
        finish(page)
        assert where(page) == ("m02", 0)
        assert entry(page)["count"] == 3                  # 題名と、段階0で見える2枚（3枚目は step:1）


def test_effects_follow_style(moving, generic_dir, tmp_path):
    with moving(motion_url(generic_dir, "#m02")) as page:
        page.keyboard.press("Shift+ArrowDown")
        finish(page)
        assert "grow" in entry(page)["effects"] and "wipe" not in entry(page)["effects"]
    deck = deck_with_motion(generic_dir / "motion.html", tmp_path, {"send": True, "entry": "subtle", "point": True})
    with moving(deck.as_uri() + "#m02") as page:
        page.keyboard.press("Shift+ArrowDown")
        finish(page)
        e = entry(page)
        assert e["style"] == "subtle" and "wipe" in e["effects"] and "grow" not in e["effects"]


def test_count_restores_text(moving, generic_dir):
    with moving(motion_url(generic_dir, "#m03")) as page:
        page.keyboard.press("ArrowDown")
        settle(page)
        page.wait_for_timeout(300)
        during = page.evaluate("document.querySelector('#stage [data-sp-role=\"count\"]').textContent")
        page.evaluate("__sp.entryDone()")
        after = page.evaluate("document.querySelector('#stage [data-sp-role=\"count\"]').textContent")
    assert during != "3,200件" and during.endswith("件")
    assert after == "3,200件"


def test_reduced_motion_has_no_entry(still, generic_dir):
    with still(motion_url(generic_dir, "#m01")) as page:
        page.keyboard.press("ArrowDown")
        assert where(page) == ("m02", 0) and state(page) == "none"


def test_saved_motion_false_has_no_entry(moving, generic_dir):
    with moving(motion_url(generic_dir, "#m01"), settings=json.dumps({"motion": False})) as page:
        page.keyboard.press("ArrowDown")
        assert where(page) == ("m02", 0) and state(page) == "none"


def test_print_render_thumbs_same_on_off(moving, still, generic_dir, tmp_path):
    # 印刷の入れ物の各ページ・O のサムネイルは、動きの設定に関係なく同じ
    def capture(opener, tag):
        with opener(motion_url(generic_dir, "#m01")) as page:
            page.evaluate("void (window.print = () => {})")
            page.keyboard.press("p")
            page.wait_for_function("!!document.querySelector('.sp-print .sp-print-page')")
            pages = page.evaluate("[...document.querySelectorAll('.sp-print .sp-print-page')].map(p => p.innerHTML)")
            page.evaluate("dispatchEvent(new Event('afterprint'))")
            page.keyboard.press("o")
            thumbs = page.evaluate("[...document.querySelectorAll('.sp-thumb .sp-target')].map(t => t.innerHTML)")
            page.keyboard.press("Escape")
        return pages, thumbs
    assert capture(moving, "moving") == capture(still, "still")


# ---- 4. 入場の途中で終える ----

STAT = '#stage [data-sp-role="count"]'
RUNNING = "document.getAnimations().filter(a => a.effect && a.effect.target && document.getElementById('stage').contains(a.effect.target)).length"


def into_entry(page, start_key="ArrowDown"):
    """次のスライドへ進み、送りの動きが終わって入場が再生中になるまで待つ。"""
    page.keyboard.press(start_key)
    settle(page)
    assert state(page) == "playing"


def assert_settled_clean(page, count_text=None):
    assert state(page) == "settled"
    assert page.evaluate(RUNNING) == 0                    # 舞台の中に動きが残っていない
    if count_text is not None:
        assert page.evaluate(f"document.querySelector('{STAT}').textContent") == count_text


@pytest.mark.parametrize("key", ["o", "?", "t", "n"])
def test_overlays_settle_entry(moving, generic_dir, key):
    with moving(motion_url(generic_dir, "#m03")) as page:
        into_entry(page)                                  # m04（数え上げのあるスライド）
        page.keyboard.press(key)
        assert_settled_clean(page, "3,200件")
        settle(page)


def test_links_view_settles_entry(moving, generic_dir):
    with moving(motion_url(generic_dir, "#m05")) as page:
        into_entry(page)                                  # m06（リンクのあるスライド）
        page.keyboard.press("l")
        assert page.evaluate("__sp.overlay()") == "links"
        assert_settled_clean(page)


def test_print_settles_entry(moving, generic_dir):
    with moving(motion_url(generic_dir, "#m03")) as page:
        page.evaluate("void (window.print = () => {})")
        into_entry(page)
        page.keyboard.press("p")
        assert_settled_clean(page, "3,200件")


def test_motion_off_settles_entry(moving, generic_dir):
    with moving(motion_url(generic_dir, "#m03")) as page:
        into_entry(page)
        page.evaluate("document.querySelector('.sp-controls button[aria-label=\"操作の一覧\"]').click()")
        assert_settled_clean(page, "3,200件")             # ? を開いた時点で確定する
        page.locator('.sp-help [data-sp-motion="off"]').click()
        page.keyboard.press("Escape")
        page.keyboard.press("ArrowDown")                  # 動きを止めたので、次は入場しない
        assert state(page) == "none"


def test_moving_settles_entry(moving, generic_dir):
    with moving(motion_url(generic_dir, "#m03")) as page:
        into_entry(page)
        page.keyboard.press("ArrowDown")                  # 入場の途中で m05 へ
        assert where(page) == ("m05", 0) and state(page) in ("pending", "playing")
        finish(page)
        assert state(page) == "done"


def test_held_key_leaves_no_stale_text(moving, still, generic_dir, tmp_path):
    with moving(motion_url(generic_dir, "#m01")) as page:
        for _ in range(4):
            page.keyboard.down("ArrowDown")               # 押しっぱなし（repeat）で m02 → m02.1 → m03 → m04
        page.keyboard.up("ArrowDown")
        assert where(page) == ("m04", 0)
        finish(page)
        assert page.evaluate(f"document.querySelector('{STAT}').textContent") == "3,200件"
        stage_shot(page, tmp_path / "moving.png")
    with still(motion_url(generic_dir, "#m04")) as page:
        stage_shot(page, tmp_path / "still.png")
    assert stills.diff(tmp_path / "moving.png", tmp_path / "still.png") is None


def test_os_reduce_settles_entry(moving, generic_dir):
    with moving(motion_url(generic_dir, "#m03")) as page:
        into_entry(page)
        page.emulate_media(reduced_motion="reduce")
        page.wait_for_function("__sp.entry().state === 'settled'")
        assert_settled_clean(page, "3,200件")


def test_click_during_entry_is_swallowed(moving, generic_dir):
    with moving(motion_url(generic_dir, "#m05")) as page:
        into_entry(page)                                  # m06
        page.locator('#stage [data-link="0"]').dispatch_event("click")       # m05 への移動のリンク
        assert where(page) == ("m06", 0) and page.evaluate("location.hash") == "#m06"
        assert_settled_clean(page)


def test_enter_during_entry_is_swallowed(moving, generic_dir):
    with moving(motion_url(generic_dir, "#m05")) as page:
        into_entry(page)
        page.evaluate("document.querySelector('#stage [data-link=\"0\"]').focus()")
        page.keyboard.press("Enter")
        assert where(page) == ("m06", 0) and page.evaluate("location.hash") == "#m06"
        assert_settled_clean(page)


def failing_page(browser, generic_dir, init, start="#m03"):
    from contextlib import contextmanager

    @contextmanager
    def run():
        with page_session(browser, "about:blank", reduced_motion="no-preference") as page:
            page.add_init_script(init)
            page.goto(motion_url(generic_dir, start))
            page.wait_for_function("!!window.__sp")
            yield page
    return run()


def matches_still(page, still, generic_dir, sid, tmp_path):
    stage_shot(page, tmp_path / "a.png")
    with still(motion_url(generic_dir, "#" + sid)) as other:
        stage_shot(other, tmp_path / "b.png")
    return stills.diff(tmp_path / "a.png", tmp_path / "b.png") is None


def test_animate_error_falls_back(browser, still, generic_dir, tmp_path):
    init = """(() => { let n = 0; const orig = Element.prototype.animate;
      Element.prototype.animate = function (...a) {
        if (this.closest && this.closest('#stage') && ++n === 3) throw new Error('animate のこわれ');
        return orig.apply(this, a); }; })();"""
    with failing_page(browser, generic_dir, init) as page:
        page.keyboard.press("ArrowDown")
        settle(page)
        assert_settled_clean(page, "3,200件")
        assert matches_still(page, still, generic_dir, "m04", tmp_path)
        page.keyboard.press("ArrowDown")
        assert where(page) == ("m05", 0)
        settle(page)


def test_play_error_falls_back(browser, still, generic_dir, tmp_path):
    init = "Animation.prototype.play = function () { throw new Error('play のこわれ'); };"
    with failing_page(browser, generic_dir, init) as page:
        page.keyboard.press("ArrowDown")
        settle(page)
        page.wait_for_timeout(50)
        assert_settled_clean(page, "3,200件")
        assert matches_still(page, still, generic_dir, "m04", tmp_path)


def test_no_animate_api(browser, still, generic_dir, tmp_path):
    with failing_page(browser, generic_dir, "delete Element.prototype.animate;") as page:
        page.keyboard.press("ArrowDown")
        settle(page)
        assert state(page) == "none"
        assert matches_still(page, still, generic_dir, "m04", tmp_path)


def test_render_error_skips_entry(moving, generic_dir, tmp_path):
    deck = deck_with_motion(generic_dir / "motion.html", tmp_path, {"send": True, "entry": "bounce", "point": False}, name="broken.html")
    deck.write_text(deck.read_text(encoding="utf-8").replace(
        "  slides: [\n", "  slides: [\n    { id: 's1', type: 'title', title: '始め', subtitle: '' },\n    { id: 's2', type: 'nope', title: 'こわれ' },\n", 1),
        encoding="utf-8")
    with moving(deck.as_uri() + "#s1") as page:
        page.keyboard.press("ArrowDown")
        settle(page)
        assert where(page) == ("s2", 0)
        assert page.locator("#stage .sp-render-error").count() == 1
        assert state(page) == "none"


# ---- 入場の途中の確定・Tab・取り消し ----

def keys_at_once(page, *keys):
    """keydown を同じ JavaScript の実行の中で続けて送る（↓ のあと、描画される前に次のキーが届く順を固定する）。"""
    page.evaluate("""(keys) => { for (const k of keys) document.dispatchEvent(new KeyboardEvent('keydown', { key: k, bubbles: true, cancelable: true })); }""", list(keys))


@pytest.mark.parametrize("key", ["d", "n", "t"])
def test_settle_before_paint_cancels_entry(moving, generic_dir, key):
    # 描く前に D・N・T で確定した入場は、送りの動きが終わっても始まらない
    with moving(motion_url(generic_dir, "#m03")) as page:
        keys_at_once(page, "ArrowDown", key)
        settle(page)
        page.wait_for_timeout(150)
        assert where(page) == ("m04", 0)
        assert state(page) == "settled" and page.evaluate(RUNNING) == 0
        assert page.evaluate(f"document.querySelector('{STAT}').textContent") == "3,200件"


@pytest.mark.parametrize("key", ["d", "n", "t"])
def test_settle_during_send_cancels_entry(moving, generic_dir, key):
    # 描いたあと、送りの動きの途中（pending）で確定した入場も、送りのあとに始まらない
    with moving(motion_url(generic_dir, "#m03")) as page:
        page.keyboard.press("ArrowDown")
        page.wait_for_function("__sp.entry().state === 'pending' && __sp.entry().count > 0")
        page.keyboard.press(key)
        settle(page)
        page.wait_for_timeout(150)
        assert state(page) == "settled" and page.evaluate(RUNNING) == 0


def test_tab_during_entry_settles_first(browser, generic_dir):
    # 入場の途中の Tab は、先に入場を確定する（まだ見えない要素に焦点が入らない）
    with page_session(browser, "about:blank", reduced_motion="no-preference") as page:
        page.add_init_script("delete Document.prototype.startViewTransition;")
        page.goto(motion_url(generic_dir, "#m05"))
        page.wait_for_function("!!window.__sp")
        page.keyboard.press("ArrowDown")
        assert state(page) == "playing"
        page.keyboard.press("Tab")
        assert state(page) == "settled" and page.evaluate(RUNNING) == 0


def test_cancelled_animation_falls_back(moving, still, generic_dir, tmp_path):
    # 再生の途中で動きが外から取り消されても、止まった姿に戻り、待っているものが解ける
    with moving(motion_url(generic_dir, "#m03")) as page:
        page.keyboard.press("ArrowDown")
        settle(page)
        assert state(page) == "playing"
        page.wait_for_timeout(150)
        page.evaluate(f"document.querySelector('{STAT}').getAnimations()[0].cancel()")
        page.wait_for_function("__sp.entry().state === 'settled'", timeout=3000)
        page.evaluate("__sp.entryDone()")
        assert page.evaluate(f"document.querySelector('{STAT}').textContent") == "3,200件"
        assert page.evaluate(RUNNING) == 0
        assert matches_still(page, still, generic_dir, "m04", tmp_path)
        page.keyboard.press("ArrowDown")                  # 古い失敗が次のスライドを止めない
        finish(page)
        assert where(page) == ("m05", 0) and state(page) == "done"
