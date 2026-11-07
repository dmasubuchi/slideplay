"""指で払う操作（iPhone・iPad）の試験。指を左へ払う＝→、右へ払う＝←、上へ払う＝↓、下へ払う＝↑（矢印キーと同じ関数を呼ぶ）。

- Chromium の has_touch=True の context に、CDP の Input.dispatchTouchEvent（touchStart・touchMove 数回・touchEnd）で本物の指の入力をまねる。
  ブラウザが pointerType: 'touch' の Pointer Events を作る（test_swipe_cdp_touch_makes_touch_pointer_events で確かめる）。
- 見るのは外から見える結果だけ：場所（__sp.state）・直近の場所（__sp.places）・hash・重なり（__sp.overlay）・操作ボタンの帯の出入り。
  「キーと同じ」は、同じ前置きのあとにキーを押した別のページと結果を比べて確かめる。
- ページは reduced_motion="reduce"（tests/helpers.py の既定）で開く。動きのある設定で払いがキーと同じ動きになることは、1件だけ確かめる。
- 汎用の見本（examples/generic/proposal.html・index.html）と、扱わない所を一通り置いた tests/swipe_deck.html を使う。
- WebKit は参考：CDP が使えず、Playwright の WebKit は指の払いをまねられないので、touch の合成の PointerEvent で1件だけ確かめる。
"""
import json
import time
from contextlib import contextmanager
from pathlib import Path

import pytest

TESTS = Path(__file__).resolve().parent
SWIPE_DECK = TESTS / "swipe_deck.html"
SETTINGS_KEY = "sp-settings-v1"
VIEWPORT = (1440, 900)                                   # 横の払いの下限は 1440×6% = 86.4px、縦は 900×6% = 54px
MID = (720, 450)                                         # 画面の真ん中（端でもプレイヤーの部品の上でもない）
BLANK = (1300, 800)                                      # swipe_deck.html の s1 で、何もない所（背景）の上。端でも操作ボタンの帯の上でもない


def proposal(generic_dir, suffix=""):
    return (generic_dir / "proposal.html").as_uri() + suffix


def catalog_url(generic_dir):
    return (generic_dir / "index.html").as_uri()


def deck_url(suffix=""):
    return SWIPE_DECK.as_uri() + suffix


# ---- 道具 ----

@contextmanager
def finger_page(browser, url, viewport=VIEWPORT, reduced_motion="reduce", settings=None, is_mobile=False):
    """指で触れる画面（has_touch=True）で url を開く。page.cdp が CDP の窓口。

    is_mobile=True ならスマートフォン相当（meta viewport を見る）の画面にする。
    settings があれば、保存された設定（操作ボタンの出し方・ノート）として先に入れる。pageerror があれば抜けるときに失敗にする。
    """
    context = browser.new_context(viewport={"width": viewport[0], "height": viewport[1]}, device_scale_factor=1,
                                  reduced_motion=reduced_motion, has_touch=True, is_mobile=is_mobile)
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.set_default_timeout(10000)
    page.cdp = context.new_cdp_session(page)
    if settings is not None:
        page.add_init_script(f"try {{ localStorage.setItem({json.dumps(SETTINGS_KEY)}, {json.dumps(json.dumps(settings))}); }} catch (e) {{}}")
    try:
        page.goto(url)
        if "render" not in url:
            page.wait_for_function("!!window.__sp")
        yield page
    finally:
        context.close()
    assert not errors, "ページが例外を出した:\n" + "\n".join(errors)


def touch_event(page, kind, points):
    """CDP の touchStart・touchMove・touchEnd。points は [(id, x, y), ...]（いま触れている全部の指。touchEnd は残る指）。"""
    page.cdp.send("Input.dispatchTouchEvent", {"type": kind, "touchPoints": [{"id": i, "x": x, "y": y} for i, x, y in points]})


def swipe(page, start, end, ms=200, steps=5, fingers=1, offset=(60, 0)):
    """start から end へ、指 fingers 本で払う（touchStart → touchMove を steps 回 → touchEnd。全体で約 ms ミリ秒）。

    2本目以降の指は、1本目から offset だけずらした所に同時に触れ、同じだけ動く。
    """
    def at(f, t):
        x = start[0] + (end[0] - start[0]) * t + offset[0] * f
        y = start[1] + (end[1] - start[1]) * t + offset[1] * f
        return (f + 1, x, y)

    touch_event(page, "touchStart", [at(f, 0) for f in range(fingers)])
    for n in range(1, steps + 1):
        time.sleep(ms / 1000 / steps)
        touch_event(page, "touchMove", [at(f, n / steps) for f in range(fingers)])
    touch_event(page, "touchEnd", [])
    page.wait_for_timeout(60)                            # pointerup を受けた listener が走り終えるのを待つ


def tap(page, point):
    touch_event(page, "touchStart", [(1, *point)])
    time.sleep(0.04)
    touch_event(page, "touchEnd", [])
    page.wait_for_timeout(100)


def where(page):
    s = page.evaluate("__sp.state()")
    return s["id"], s["step"]


def snapshot(page):
    """場所・hash・直近の場所（試験で「キーと同じ」を比べる材料）。"""
    p = page.evaluate("__sp.places()")
    return {
        "state": page.evaluate("__sp.state()"),
        "hash": page.evaluate("location.hash"),
        "places": ([(i["ref"], i["step"]) for i in p["items"]], p["pos"]),
        "toast": page.evaluate("(document.querySelector('.sp-toast') || {}).textContent || ''"),
    }


def centre(page, selector):
    """要素の真ん中の画面上の位置。"""
    b = page.evaluate("(s) => { const r = document.querySelector(s).getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; }", selector)
    return tuple(b)


def controls_on(page):
    return page.evaluate("document.querySelector('.sp-controls').classList.contains('sp-on')")


def settle(page):
    page.evaluate("__sp.motionDone()")


def wait_to_move(page, before):
    page.wait_for_function("(b) => { const s = __sp.state(); return s.id !== b[0] || s.step !== b[1]; }", arg=list(before))


def stays(page):
    """払いが何も動かさなかったことを確かめる前の、念のための待ち。"""
    page.wait_for_timeout(150)


# ---- 1. 本物の指の入力が作れるか ----

def test_swipe_cdp_touch_makes_touch_pointer_events(browser, generic_dir):
    # CDP の Input.dispatchTouchEvent が、pointerType: 'touch' の Pointer Events（pointerdown → pointerup）を作ること。
    # 作れないなら、以降の試験の前提が崩れる（その場合は合成の PointerEvent に切り替える）
    with finger_page(browser, proposal(generic_dir, "#p02")) as page:
        page.evaluate("""window.__ev = []; for (const t of ['pointerdown', 'pointerup', 'pointercancel'])
            document.addEventListener(t, e => __ev.push([t, e.pointerType, e.isPrimary]), true)""")
        swipe(page, MID, (MID[0] - 200, MID[1]))
        assert page.evaluate("__ev") == [["pointerdown", "touch", True], ["pointerup", "touch", True]]


# ---- 2. 4つの向きが、それぞれのキーと同じ結果 ----

# (名前, 開く場所, 前置きのキー, 払う向きの始点→終点, 同じ動きのキー, 払ったあとの場所)
DECK_CASES = [
    ("left-follows-place", "#p01", ["End", "ArrowLeft"], (0, -200), "ArrowRight", ("p08", 0)),
    ("left-without-place-is-down", "#p02", [], (0, -200), "ArrowRight", ("p02", 1)),
    ("right-goes-back", "#p01", ["End"], (0, 200), "ArrowLeft", ("p01", 0)),
    ("up-is-down", "#p02", [], (1, -200), "ArrowDown", ("p02", 1)),
    ("up-to-next-slide", "#p01", [], (1, -200), "ArrowDown", ("p02", 0)),
    ("down-is-up", "#p03", [], (1, 200), "ArrowUp", ("p02", 2)),
]


@pytest.mark.parametrize("start,prelude,move,key,expected", [c[1:] for c in DECK_CASES], ids=[c[0] for c in DECK_CASES])
def test_swipe_deck_direction_same_as_key(browser, generic_dir, start, prelude, move, key, expected):
    axis, delta = move
    end = (MID[0] + delta, MID[1]) if axis == 0 else (MID[0], MID[1] + delta)
    with finger_page(browser, proposal(generic_dir, start)) as by_swipe, finger_page(browser, proposal(generic_dir, start)) as by_key:
        for page in (by_swipe, by_key):
            for k in prelude:
                page.keyboard.press(k)
        assert snapshot(by_swipe) == snapshot(by_key)
        by_key.keyboard.press(key)
        swipe(by_swipe, MID, end)
        assert where(by_key) == expected
        assert snapshot(by_swipe) == snapshot(by_key)


def test_swipe_deck_at_the_ends_toasts_like_keys(browser, generic_dir):
    # 最初で下へ払う（↑）・最後で上へ払う（↓）は、キーと同じ知らせが出て、動かない
    with finger_page(browser, proposal(generic_dir, "#p01")) as page:
        swipe(page, MID, (MID[0], MID[1] + 200))
        page.wait_for_selector(".sp-toast")
        assert where(page) == ("p01", 0) and page.inner_text(".sp-toast") == "最初のスライドです"
    with finger_page(browser, proposal(generic_dir, "#p08")) as page:
        swipe(page, MID, (MID[0], MID[1] - 200))
        page.wait_for_selector(".sp-toast")
        assert where(page) == ("p08", 0) and page.inner_text(".sp-toast") == "最後のスライドです"


# 目次：→ は先の場所がないとき ↓ と同じ（カードを選ぶ）、↑↓ はカードを選ぶ、← は直近の場所（なければ動かない）
CATALOG_CASES = [
    ("up-selects-next", [], (1, -200), "ArrowDown"),
    ("down-selects-previous", ["ArrowDown", "ArrowDown"], (1, 200), "ArrowUp"),
    ("left-without-place-is-down", [], (0, -200), "ArrowRight"),
    ("right-without-place-stays", ["ArrowDown"], (0, 200), "ArrowLeft"),
]


@pytest.mark.parametrize("prelude,move,key", [c[1:] for c in CATALOG_CASES], ids=[c[0] for c in CATALOG_CASES])
def test_swipe_catalog_direction_same_as_key(browser, generic_dir, prelude, move, key):
    axis, delta = move
    end = (MID[0] + delta, MID[1]) if axis == 0 else (MID[0], MID[1] + delta)
    with finger_page(browser, catalog_url(generic_dir)) as by_swipe, finger_page(browser, catalog_url(generic_dir)) as by_key:
        for page in (by_swipe, by_key):
            for k in prelude:
                page.keyboard.press(k)
        before = by_swipe.evaluate("__sp.state().index")
        by_key.keyboard.press(key)
        swipe(by_swipe, MID, end)
        assert snapshot(by_swipe) == snapshot(by_key)
        if key in ("ArrowDown", "ArrowRight"):
            assert by_swipe.evaluate("__sp.state().index") == before + 1


# ---- 3. 払いと見なす条件 ----

# 1440×900 の横は 86.4px 以上、縦は 54px 以上。向きは大きい方が小さい方の 1.5 倍以上
LENGTH_CASES = [
    ("horizontal-too-short", (-80, 0), False),
    ("horizontal-long-enough", (-95, 0), True),
    ("vertical-too-short", (0, -50), False),
    ("vertical-long-enough", (0, -60), True),
    ("diagonal", (-100, 70), False),                     # 100 / 70 = 1.43 倍
    ("almost-diagonal-but-clear", (-100, 60), True),     # 100 / 60 = 1.67 倍
]


@pytest.mark.parametrize("delta,moves", [c[1:] for c in LENGTH_CASES], ids=[c[0] for c in LENGTH_CASES])
def test_swipe_length_and_clearness(browser, generic_dir, delta, moves):
    with finger_page(browser, proposal(generic_dir, "#p02")) as page:
        swipe(page, MID, (MID[0] + delta[0], MID[1] + delta[1]))
        if moves:
            wait_to_move(page, ("p02", 0))
        else:
            stays(page)
            assert where(page) == ("p02", 0)


def test_swipe_minimum_is_30px_on_a_small_screen(browser, generic_dir):
    # 小さい画面（幅 400）の 6% は 24px。30px 未満は払いではない
    with finger_page(browser, proposal(generic_dir, "#p02"), viewport=(400, 700)) as page:
        swipe(page, (200, 350), (175, 350))               # 25px
        stays(page)
        assert where(page) == ("p02", 0)
        swipe(page, (200, 350), (165, 350))               # 35px
        wait_to_move(page, ("p02", 0))


def test_swipe_too_slow_is_not_a_swipe(browser, generic_dir):
    with finger_page(browser, proposal(generic_dir, "#p02")) as page:
        swipe(page, MID, (MID[0], MID[1] - 200), ms=900)
        stays(page)
        assert where(page) == ("p02", 0)
        swipe(page, MID, (MID[0], MID[1] - 200), ms=300)
        wait_to_move(page, ("p02", 0))


def test_swipe_is_decided_when_the_finger_lifts(browser, generic_dir):
    # 離すまで動かさない（pointermove の途中では動かない）
    with finger_page(browser, proposal(generic_dir, "#p02")) as page:
        touch_event(page, "touchStart", [(1, *MID)])
        touch_event(page, "touchMove", [(1, MID[0], MID[1] - 100)])
        touch_event(page, "touchMove", [(1, MID[0], MID[1] - 200)])
        page.wait_for_timeout(100)
        assert where(page) == ("p02", 0)
        touch_event(page, "touchEnd", [])
        wait_to_move(page, ("p02", 0))


def test_swipe_a_second_finger_cancels_it(browser, generic_dir):
    with finger_page(browser, proposal(generic_dir, "#p02")) as page:
        swipe(page, MID, (MID[0], MID[1] - 200), fingers=2)                       # 2本で同時に払う（2本指の拡大・回転の形）
        stays(page)
        assert where(page) == ("p02", 0)
        touch_event(page, "touchStart", [(1, *MID)])                              # 払いの途中で2本目が触れる
        touch_event(page, "touchMove", [(1, MID[0], MID[1] - 100)])
        touch_event(page, "touchStart", [(1, MID[0], MID[1] - 100), (2, MID[0] + 100, MID[1])])
        touch_event(page, "touchMove", [(1, MID[0], MID[1] - 200), (2, MID[0] + 100, MID[1] - 100)])
        touch_event(page, "touchEnd", [])
        stays(page)
        assert where(page) == ("p02", 0)
        swipe(page, MID, (MID[0], MID[1] - 200))                                  # 次の1本指の払いは、また効く
        wait_to_move(page, ("p02", 0))


def test_swipe_pointercancel_gives_up(browser, generic_dir):
    # ブラウザが指の入力を取った（pointercancel）ときは、そのあとに pointerup が来ても払いにしない
    with finger_page(browser, proposal(generic_dir, "#p02")) as page:
        page.evaluate("""() => {
            const fire = (type, y) => document.elementFromPoint(720, 450).dispatchEvent(new PointerEvent(type,
                { pointerType: 'touch', pointerId: 9, isPrimary: true, clientX: 720, clientY: y, bubbles: true, composed: true }));
            fire('pointerdown', 450); fire('pointercancel', 250); fire('pointerup', 250);
        }""")
        stays(page)
        assert where(page) == ("p02", 0)


# ---- 4. 扱わない払い（始めた所・そのときの状態で決める） ----

@pytest.mark.parametrize("start,inside", [
    ((10, 450), (30, 450)),                              # 左の端
    ((1430, 450), (1410, 450)),                          # 右の端
    ((720, 10), (720, 30)),                              # 上の端
    ((720, 890), (720, 820)),                            # 下の端（操作ボタンの帯が出ても重ならない高さ）
], ids=["left-edge", "right-edge", "top-edge", "bottom-edge"])
def test_swipe_started_near_the_screen_edge_is_ignored(browser, generic_dir, start, inside):
    # どの端からも、上へ払う（↓：段階が進む）。端から 20px 以内で始めると動かず、30px の所からなら動く
    with finger_page(browser, proposal(generic_dir, "#p02")) as page:
        swipe(page, start, (start[0], start[1] - 150 if start[1] > 100 else start[1] + 150))
        stays(page)
        assert where(page) == ("p02", 0)
        swipe(page, inside, (inside[0], inside[1] - 150 if inside[1] > 100 else inside[1] + 150))
        wait_to_move(page, ("p02", 0))


def test_swipe_started_on_the_controls_is_ignored(browser, generic_dir):
    with finger_page(browser, proposal(generic_dir, "#p02"), settings={"controls": "always", "notes": False}) as page:
        box = page.evaluate("(() => { const r = document.querySelector('.sp-controls').getBoundingClientRect(); return [r.left, r.top, r.width, r.height]; })()")
        start = (60, box[1] + box[3] / 2)                # 帯の左のボタンのない所
        assert page.evaluate("([x, y]) => document.elementFromPoint(x, y).classList.contains('sp-controls')", list(start))
        swipe(page, start, (start[0], start[1] - 200))
        stays(page)
        assert where(page) == ("p02", 0)


def test_swipe_started_on_the_notes_is_ignored(browser):
    with finger_page(browser, deck_url("#s2"), settings={"controls": "never", "notes": True}) as page:
        for selector in (".sp-notes-head", ".sp-notes-body"):             # 見出し（スクロールしない所）と本文（スクロールする所）
            start = centre(page, selector)
            swipe(page, start, (start[0], start[1] - 150))
            stays(page)
            assert where(page) == ("s2", 0)


def show_toast(page):
    page.keyboard.press("ArrowUp")                       # 最初のスライドで ↑：知らせが出る
    page.wait_for_selector(".sp-toast")


def test_swipe_started_on_the_toast_is_ignored(browser, generic_dir):
    # 実際の知らせは pointer-events: none：イベントの相手は下のスライドになるので、見た目の矩形で除外される必要がある
    with finger_page(browser, proposal(generic_dir, "#p01")) as page:
        show_toast(page)
        before = snapshot(page)
        start = centre(page, ".sp-toast")
        swipe(page, start, (start[0], start[1] - 150))
        stays(page)
        assert where(page) == ("p01", 0)
        after = snapshot(page)
        assert (after["hash"], after["places"]) == (before["hash"], before["places"])


def test_swipe_started_on_the_toast_is_ignored_on_a_phone(browser, generic_dir):
    with finger_page(browser, proposal(generic_dir, "#p01"), viewport=(390, 844), is_mobile=True) as page:
        show_toast(page)
        before = snapshot(page)
        start = centre(page, ".sp-toast")
        swipe(page, start, (start[0], start[1] - 150))
        stays(page)
        assert where(page) == ("p01", 0)
        after = snapshot(page)
        assert (after["hash"], after["places"]) == (before["hash"], before["places"])


def test_swipe_works_again_where_the_toast_was(browser, generic_dir):
    with finger_page(browser, proposal(generic_dir, "#p01")) as page:
        show_toast(page)
        start = centre(page, ".sp-toast")
        page.wait_for_selector(".sp-toast", state="detached", timeout=6000)    # TOAST_MS（2500ms）を超えて待つ
        swipe(page, start, (start[0], start[1] - 150))
        wait_to_move(page, ("p01", 0))


def test_swipe_started_on_an_input_is_ignored(browser):
    with finger_page(browser, deck_url("#s1")) as page:
        start = centre(page, "#field")
        swipe(page, start, (start[0], start[1] + 200))
        swipe(page, start, (start[0] - 200, start[1]))
        stays(page)
        assert where(page) == ("s1", 0)
        swipe(page, BLANK, (BLANK[0], BLANK[1] - 200))   # 入力欄の外（何もない所）なら払える
        wait_to_move(page, ("s1", 0))


def test_swipe_started_on_contenteditable_is_ignored(browser):
    with finger_page(browser, deck_url("#s1")) as page:
        page.evaluate("document.getElementById('text').setAttribute('contenteditable', 'true')")
        start = centre(page, "#text")
        swipe(page, start, (start[0], start[1] - 200))
        stays(page)
        assert where(page) == ("s1", 0)


def test_swipe_started_on_a_link_works_and_does_not_open_it(browser):
    # 大きなリンクの箱の上から始めた払いは払いになる。リンクは開かない（s3 へ飛ばない）
    with finger_page(browser, deck_url("#s1")) as page:
        start = centre(page, "#biglink")
        swipe(page, start, (start[0], start[1] - 200))
        wait_to_move(page, ("s1", 0))
        assert where(page) == ("s1", 1)
        swipe(page, start, (start[0] - 200, start[1]))   # → と同じ（先の場所がないので ↓ と同じ）
        wait_to_move(page, ("s1", 1))
        assert where(page) == ("s1", 2)


def test_swipe_over_a_horizontally_scrollable_box(browser):
    with finger_page(browser, deck_url("#s1")) as page:
        start = centre(page, "#wide")
        swipe(page, start, (start[0] - 200, start[1]))   # 横の払いは、枠をスクロールする（スライドは動かさない）
        stays(page)
        assert where(page) == ("s1", 0)
        assert page.evaluate("document.getElementById('wide').scrollLeft") > 0


def test_swipe_over_a_vertically_scrollable_box(browser):
    with finger_page(browser, deck_url("#s1")) as page:
        start = centre(page, "#tall")
        swipe(page, start, (start[0], start[1] - 200))   # 縦の払いは、枠をスクロールする
        stays(page)
        assert where(page) == ("s1", 0)
        assert page.evaluate("document.getElementById('tall').scrollTop") > 0


def test_swipe_over_the_notes_scrolls_the_notes(browser):
    # 1本指のスクロールを止める指定（touch-action）が、ノートの中のスクロールまで止めていない
    with finger_page(browser, deck_url("#s2"), settings={"controls": "never", "notes": True}) as page:
        start = centre(page, ".sp-notes-body")
        swipe(page, start, (start[0], start[1] - 200))
        stays(page)
        assert page.evaluate("document.querySelector('.sp-notes-body').scrollTop") > 0
        assert where(page) == ("s2", 0)


def test_swipe_is_ignored_while_an_overlay_is_open(browser, generic_dir):
    with finger_page(browser, proposal(generic_dir, "#p04")) as page:
        for key, name in (("?", "help"), ("o", "overview"), ("l", "links")):
            page.keyboard.press(key)
            assert page.evaluate("__sp.overlay()") == name
            swipe(page, MID, (MID[0], MID[1] - 200))
            swipe(page, MID, (MID[0] - 200, MID[1]))
            stays(page)
            assert page.evaluate("__sp.overlay()") == name and where(page) == ("p04", 0)
            page.keyboard.press("Escape")
            assert page.evaluate("__sp.overlay()") == "none"


def test_swipe_is_ignored_while_the_catalog_help_is_open(browser, generic_dir):
    with finger_page(browser, catalog_url(generic_dir)) as page:
        page.keyboard.press("?")
        swipe(page, MID, (MID[0], MID[1] - 200))
        stays(page)
        assert page.evaluate("__sp.state().index") == 0


def test_swipe_is_ignored_while_text_is_selected(browser):
    with finger_page(browser, deck_url("#s1")) as page:
        page.evaluate("getSelection().selectAllChildren(document.getElementById('text'))")
        swipe(page, BLANK, (BLANK[0], BLANK[1] - 200))
        stays(page)
        assert where(page) == ("s1", 0)
        page.evaluate("getSelection().removeAllRanges()")
        swipe(page, BLANK, (BLANK[0], BLANK[1] - 200))
        wait_to_move(page, ("s1", 0))


def test_swipe_is_ignored_while_pinch_zoomed(browser, generic_dir):
    with finger_page(browser, proposal(generic_dir, "#p02")) as page:
        page.cdp.send("Emulation.setPageScaleFactor", {"pageScaleFactor": 2})
        page.wait_for_function("visualViewport.scale > 1.5")
        page.wait_for_function("document.documentElement.classList.contains('sp-zoomed')")
        assert page.evaluate("getComputedStyle(document.documentElement).touchAction") == "auto"       # 拡大した画面を指で動かせる
        swipe(page, MID, (MID[0], MID[1] - 150))
        stays(page)
        assert where(page) == ("p02", 0)
        page.cdp.send("Emulation.setPageScaleFactor", {"pageScaleFactor": 1})
        page.wait_for_function("!document.documentElement.classList.contains('sp-zoomed')")
        assert page.evaluate("getComputedStyle(document.documentElement).touchAction") == "pinch-zoom"
        swipe(page, MID, (MID[0], MID[1] - 200))
        wait_to_move(page, ("p02", 0))


# ---- 5. 指以外 ----

def test_swipe_ignores_mouse_drag(browser, generic_dir):
    with finger_page(browser, proposal(generic_dir, "#p02")) as page:
        page.mouse.move(*MID)
        page.mouse.down()
        page.mouse.move(MID[0], MID[1] - 100, steps=4)
        page.mouse.move(MID[0], MID[1] - 200, steps=4)
        page.mouse.up()
        stays(page)
        assert where(page) == ("p02", 0)


def test_swipe_ignores_pen(browser, generic_dir):
    # ペン（Apple Pencil）は書き込みに使う。合成の pointerType: 'pen' の払い（touch なら同じ入力で動く）
    with finger_page(browser, proposal(generic_dir, "#p02")) as page:
        script = """([kind, x1, y1, x2, y2]) => {
            const fire = (type, x, y) => document.elementFromPoint(x, y).dispatchEvent(new PointerEvent(type,
                { pointerType: kind, pointerId: 7, isPrimary: true, clientX: x, clientY: y, bubbles: true, composed: true }));
            fire('pointerdown', x1, y1); fire('pointerup', x2, y2);
        }"""
        page.evaluate(script, ["pen", MID[0], MID[1], MID[0], MID[1] - 200])
        stays(page)
        assert where(page) == ("p02", 0)
        page.evaluate(script, ["touch", MID[0], MID[1], MID[0], MID[1] - 200])                          # 同じ入力でも touch なら動く
        wait_to_move(page, ("p02", 0))


# ---- 6. タップ・操作ボタンの帯 ----

def test_tap_still_shows_the_controls_and_opens_links(browser, generic_dir):
    with finger_page(browser, deck_url("#s1")) as page:
        assert not controls_on(page)
        tap(page, BLANK)                                    # 何もない所（背景）
        assert controls_on(page) and where(page) == ("s1", 0)
        tap(page, centre(page, "#biglink"))                     # リンクは今までどおり開く（s3 へ飛ぶ）
        page.wait_for_function("__sp.state().id === 's3'")


def test_swipe_keeps_a_hidden_controls_bar_hidden(browser, generic_dir):
    with finger_page(browser, proposal(generic_dir, "#p02")) as page:
        assert not controls_on(page)
        swipe(page, MID, (MID[0], MID[1] - 200))
        wait_to_move(page, ("p02", 0))
        assert not controls_on(page)
        swipe(page, MID, (MID[0] - 200, MID[1]))
        page.wait_for_timeout(100)
        assert not controls_on(page)                             # 払うたびに帯が出ない


def test_swipe_leaves_a_shown_controls_bar_shown(browser, generic_dir):
    with finger_page(browser, proposal(generic_dir, "#p02")) as page:
        tap(page, MID)
        assert controls_on(page)
        swipe(page, MID, (MID[0], MID[1] - 200))
        wait_to_move(page, ("p02", 0))
        assert controls_on(page)                                 # 出ていたなら、そのまま（3 秒で消える決まりは変わらない）


def test_swipe_leaves_always_shown_controls_shown(browser, generic_dir):
    with finger_page(browser, proposal(generic_dir, "#p02"), settings={"controls": "always", "notes": False}) as page:
        assert controls_on(page)
        swipe(page, MID, (MID[0], MID[1] - 200))
        wait_to_move(page, ("p02", 0))
        assert controls_on(page)


# ---- 7. touch-action と listener、?render ----

def listener_types(page):
    """document に付いている listener の種類と、capture・passive（CDP の DOMDebugger）。"""
    obj = page.cdp.send("Runtime.evaluate", {"expression": "document"})["result"]["objectId"]
    found = page.cdp.send("DOMDebugger.getEventListeners", {"objectId": obj})["listeners"]
    return {(f["type"], f["useCapture"], f["passive"]) for f in found}


def test_swipe_player_screens_set_touch_action_and_listeners(browser, generic_dir):
    for url in (proposal(generic_dir, "#p02"), catalog_url(generic_dir)):
        with finger_page(browser, url) as page:
            style = page.evaluate("(() => { const h = getComputedStyle(document.documentElement), b = getComputedStyle(document.body); return [h.touchAction, b.touchAction, h.overscrollBehaviorX, h.overscrollBehaviorY, b.overscrollBehaviorY]; })()")
            assert style == ["pinch-zoom", "pinch-zoom", "none", "none", "none"]
            assert {("pointerdown", True, True), ("pointerup", True, True), ("pointercancel", True, True)} <= listener_types(page)


def test_swipe_render_mode_adds_nothing(browser, generic_dir):
    with finger_page(browser, proposal(generic_dir, "?render")) as page:
        assert page.evaluate("(() => { const h = getComputedStyle(document.documentElement); return [h.touchAction, h.overscrollBehaviorY, !!document.querySelector('style.sp-style'), typeof window.__sp]; })()") \
            == ["auto", "auto", False, "undefined"]
        assert not {t for t, _, _ in listener_types(page)} & {"pointerdown", "pointerup", "pointercancel"}
        assert not page.evaluate("document.documentElement.classList.contains('sp-zoomed')")


# ---- 8. 切り替えの動き（動きのある設定）----

def test_swipe_motion_same_as_key(browser, generic_dir):
    # 動きのある設定（no-preference）でも、払いはキーと同じ動き・同じ結果になる
    results = []
    for use_swipe in (True, False):
        with finger_page(browser, proposal(generic_dir, "#p01"), reduced_motion="no-preference") as page:
            if use_swipe:
                swipe(page, MID, (MID[0], MID[1] - 200))
            else:
                page.keyboard.press("ArrowDown")
            page.wait_for_function("__sp.state().id === 'p02'")
            kind = page.evaluate("__sp.motion().kind")
            settle(page)
            results.append((kind, snapshot(page)))
    assert results[0] == results[1] and results[0][0] == "next"


# ---- 9. WebKit（参考）----

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


@pytest.mark.webkit
def test_swipe_webkit_synthetic_touch_pointers_move_the_slide(webkit_browser, generic_dir):
    # WebKit では CDP が使えず、Playwright は指の払いをまねられない（touchscreen.tap だけ）。
    # touch の合成の PointerEvent を送って、払いの見分けと、押したキーと同じ動きが WebKit でも動くことだけを確かめる。
    # touch-action が実機の指のスクロールを止めるかは、実機（iPad・iPhone）で確かめる
    context = webkit_browser.new_context(viewport={"width": VIEWPORT[0], "height": VIEWPORT[1]}, has_touch=True, reduced_motion="reduce")
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    try:
        page.goto(proposal(generic_dir, "#p02"))
        page.wait_for_function("!!window.__sp")
        script = """([x1, y1, x2, y2]) => {
            const fire = (type, x, y) => document.elementFromPoint(x, y).dispatchEvent(new PointerEvent(type,
                { pointerType: 'touch', pointerId: 3, isPrimary: true, clientX: x, clientY: y, bubbles: true, composed: true }));
            fire('pointerdown', x1, y1); fire('pointerup', x2, y2);
        }"""
        page.evaluate(script, [MID[0], MID[1], MID[0], MID[1] - 200])        # 上へ払う＝↓：段階 1
        page.wait_for_function("__sp.state().step === 1")
        page.evaluate(script, [MID[0], MID[1], MID[0], MID[1] - 10])         # 短い払いは動かない
        page.wait_for_timeout(100)
        assert where(page) == ("p02", 1)
        page.evaluate(script, [MID[0], MID[1], MID[0], MID[1] + 200])        # 下へ払う＝↑：段階 0
        page.wait_for_function("__sp.state().step === 0")
        assert page.evaluate("getComputedStyle(document.documentElement).touchAction") == "pinch-zoom"
    finally:
        context.close()
    assert not errors, errors
