"""WebKit（Safari 相当）の参考の試験。iPad の Safari に向けた参考で、完成の条件には含めない。

- 既定では走らせない（pytest.ini の addopts = -m "not webkit"）。走らせるとき：python3 -m pytest -m webkit -v
- 入れ方：python3 -m playwright install webkit（入っていなければ、全部 skip になる）
- 結果は作業フォルダー（環境変数 SLIDE_PLAYER_WORK_ROOT が指すフォルダー。未設定なら一時フォルダー。tests/conftest.py の WORK_ROOT）の webkit-report.json に、試験ごと・領域ごとに書く。
  領域は試験名の2つ目の語（order・notes・overview・links・places・catalog・render・layout）
- 失敗は報告するだけで、player.js は直さない（対象は Chrome 系のブラウザー）。ただし、Chromium にも安全な直しは別に行う
- 主な操作を、Chromium の試験と同じ考え方で動かす：規定の順序、N、O、L、直近の場所（←→）、
  目次の往復、デッキをまたいだ ←→。画面の大きさの検査（layout_check.py）も同じものを使う
"""
import json
from contextlib import contextmanager

import pytest

from helpers import page_session
from layout_check import layout_problems

pytestmark = pytest.mark.webkit

PLACES_KEY = "sp-places-v1"
SETTINGS_KEY = "sp-settings-v1"
VIEWPORTS = [(1440, 900), (1000, 700), (1180, 820), (820, 1180)]


@pytest.fixture(scope="module")
def webkit_browser(playwright_instance, request):
    """WebKit を1回だけ起動する。起動できない（入っていない）ときは skip。"""
    from playwright.sync_api import Error

    try:
        b = playwright_instance.webkit.launch()
    except Error as exc:
        pytest.skip(f"WebKit が起動できない（python3 -m playwright install webkit で入れる）: {str(exc).splitlines()[0][:200]}")
    request.config._webkit_info = {"version": b.version, "note": "Playwright の WebKit（Safari 相当。実機の Safari・iPad ではない）"}
    yield b
    b.close()


# ---- 道具 ----

@contextmanager
def session(browser, url, controls="never", notes=False, viewport=(1440, 900), seed=True):
    """設定（seed=True のとき）を先に入れて url を開く。pageerror があれば抜けるときに失敗（page_session）。
    seed は読み込みのたびに入れ直すので、再読み込みで設定が残るかを見る試験は seed=False にする。"""
    with page_session(browser, "about:blank", viewport=viewport) as page:
        page.set_default_timeout(10000)
        if seed:
            value = json.dumps({"controls": controls, "notes": notes})
            page.add_init_script(f"try {{ localStorage.setItem({json.dumps(SETTINGS_KEY)}, {json.dumps(value)}); }} catch (e) {{}}")
        page.goto(url)
        page.wait_for_function("!!window.__sp")
        yield page


def where(page):
    s = page.evaluate("__sp.state()")
    return s["id"], s["step"]


def press(page, key):
    page.keyboard.press(key)
    return where(page)


def listing(page):
    p = page.evaluate("__sp.places()")
    return [(i["ref"], i["step"]) for i in p["items"]], p["pos"]


def overlay(page):
    return page.evaluate("__sp.overlay()")


def proposal(generic_dir, suffix=""):
    return (generic_dir / "proposal.html").as_uri() + suffix


def navigate(page, action):
    """action による別のページへの移動を待ち、プレイヤーが動き出すまで待つ。"""
    before = page.url.split("#")[0]
    with page.expect_navigation(url=lambda u: u.split("#")[0] != before):
        action()
    page.wait_for_function("!!window.__sp")


# ---- 規定の順序 ----

def test_order_keys_walk_deck(webkit_browser, generic_dir):
    # ↓ 次の段階→次のスライド、↑ 前、Shift＋↓↑、Space・PageDown・PageUp、Home・End。hash も合う
    with session(webkit_browser, proposal(generic_dir, "#p01")) as page:
        assert press(page, "ArrowDown") == ("p02", 0)
        assert press(page, "ArrowDown") == ("p02", 1)
        assert press(page, "Space") == ("p02", 2)
        assert press(page, "PageDown") == ("p03", 0)
        assert page.evaluate("location.hash") == "#p03"
        assert press(page, "ArrowUp") == ("p02", 2)                 # 前のスライドの最後の段階
        assert press(page, "PageUp") == ("p02", 1)
        assert press(page, "Shift+ArrowDown") == ("p03", 0)
        assert press(page, "Shift+ArrowUp") == ("p02", 2)
        assert press(page, "End") == ("p08", 0)
        assert press(page, "Home") == ("p01", 0)
        page.keyboard.press("ArrowUp")
        assert page.locator(".sp-toast").count() == 1               # 先頭より前：知らせ


def test_order_stage_fits_all_viewports(webkit_browser, generic_dir):
    for viewport in VIEWPORTS:
        with session(webkit_browser, proposal(generic_dir), viewport=viewport) as page:
            r = page.evaluate("(() => { const r = document.getElementById('stage').getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom, r.width / r.height]; })()")
            assert r[0] >= -0.5 and r[1] >= -0.5 and r[2] <= viewport[0] + 0.5 and r[3] <= viewport[1] + 0.5, (viewport, r)
            assert r[4] == pytest.approx(16 / 9, rel=0.01), (viewport, r)


def test_order_stage_click_does_not_advance(webkit_browser, generic_dir):
    with session(webkit_browser, proposal(generic_dir, "#p02")) as page:
        page.mouse.click(700, 300)
        assert where(page) == ("p02", 0)


# ---- N ----

def test_notes_toggle_resizes_stage_and_persists(webkit_browser, generic_dir):
    with session(webkit_browser, proposal(generic_dir, "#p02"), seed=False) as page:
        full = page.evaluate("document.getElementById('stage').getBoundingClientRect().width")
        page.keyboard.press("n")
        assert page.locator(".sp-notes").count() == 1
        assert "月末の残業" in page.inner_text(".sp-notes-body")
        narrow = page.evaluate("document.getElementById('stage').getBoundingClientRect().width")
        assert narrow < full
        assert json.loads(page.evaluate(f"localStorage.getItem('{SETTINGS_KEY}')"))["notes"] is True
        page.reload()
        assert page.locator(".sp-notes").count() == 1               # 次に開いたときも
        page.keyboard.press("n")
        assert page.locator(".sp-notes").count() == 0


# ---- O ----

def test_overview_open_select_and_jump(webkit_browser, generic_dir):
    with session(webkit_browser, proposal(generic_dir, "#p03")) as page:
        page.keyboard.press("o")
        assert overlay(page) == "overview" and page.locator(".sp-thumb").count() == 9
        assert page.locator(".sp-thumb.sp-selected").get_attribute("data-index") == "2"      # 今のスライドが選ばれている
        page.keyboard.press("ArrowRight")
        page.keyboard.press("ArrowRight")
        assert page.locator(".sp-thumb.sp-selected").get_attribute("data-index") == "4"
        page.keyboard.press("Enter")
        assert overlay(page) == "none" and where(page) == ("p04", 0)
        assert page.locator(".sp-thumb").count() == 0                # 閉じたら DOM から外れる
        page.keyboard.press("o")
        page.keyboard.press("Escape")
        assert overlay(page) == "none"


def test_overview_thumbnail_click(webkit_browser, generic_dir):
    with session(webkit_browser, proposal(generic_dir, "#p01")) as page:
        page.keyboard.press("o")
        page.locator('.sp-thumb[data-index="5"]').click()
        assert where(page) == ("p05", 0) and overlay(page) == "none"


# ---- ? ----

def test_help_toggle_and_controls_choice(webkit_browser, generic_dir):
    with session(webkit_browser, proposal(generic_dir)) as page:
        page.keyboard.press("?")
        assert overlay(page) == "help"
        page.locator(".sp-help button", has_text="いつも出す").click()
        assert page.locator(".sp-controls").is_visible()
        assert json.loads(page.evaluate(f"localStorage.getItem('{SETTINGS_KEY}')"))["controls"] == "always"
        page.keyboard.press("?")
        assert overlay(page) == "none"


# ---- L とリンク ----

def test_links_view_and_follow(webkit_browser, generic_dir):
    with session(webkit_browser, proposal(generic_dir, "#p04")) as page:
        assert page.evaluate("document.querySelectorAll('#stage [data-sp-kind]').length") == 5
        page.keyboard.press("l")
        assert overlay(page) == "links" and page.locator(".sp-linkframe").count() == 5
        assert len(page.locator(".sp-linktag").all_inner_texts()) == 5
        page.keyboard.press("Escape")
        page.locator('#stage [data-link="0"]').click()               # jump（同じデッキ）
        assert where(page) == ("p07", 0)
        assert press(page, "ArrowLeft") == ("p04", 0)
        page.locator('#stage [data-link="3"]').click()               # more
        assert overlay(page) == "more" and "照らし合わせて" in page.inner_text(".sp-more-text")
        page.keyboard.press("Escape")
        assert overlay(page) == "none"


# ---- 直近の場所（←→）----

def test_places_left_right_within_deck(webkit_browser, generic_dir):
    with session(webkit_browser, proposal(generic_dir, "#p04")) as page:
        press(page, "Shift+ArrowDown")
        press(page, "Shift+ArrowDown")
        assert listing(page) == ([("p04", 0), ("p05", 0), ("p06", 0)], 2)
        assert press(page, "ArrowLeft") == ("p05", 0)
        assert press(page, "ArrowLeft") == ("p04", 0)
        assert press(page, "ArrowRight") == ("p05", 0)
        assert press(page, "ArrowRight") == ("p06", 0)
        assert press(page, "ArrowRight") == ("p07", 0)               # 先の場所がない → は ↓ と同じ（知らせない）
        assert page.locator(".sp-toast").count() == 0
        assert listing(page) == ([("p04", 0), ("p05", 0), ("p06", 0), ("p07", 0)], 3)
        for _ in range(3):
            page.keyboard.press("ArrowLeft")
        assert where(page) == ("p04", 0)
        page.keyboard.press("ArrowLeft")
        assert page.locator(".sp-toast").count() == 1               # 先頭の ← は、端で知らせる


def test_places_reload_and_browser_back(webkit_browser, generic_dir):
    P = proposal(generic_dir)
    with session(webkit_browser, P + "#p01") as page:
        press(page, "Shift+ArrowDown")
        before = listing(page)
        page.reload()
        assert where(page) == ("p02", 0) and listing(page) == before          # 再読み込みで並びが続く
        page.goto(P + "#p05")                                               # アドレス欄で hash を変える
        page.wait_for_function("__sp.state().id === 'p05'")
        assert listing(page) == ([("p01", 0), ("p02", 0), ("p05", 0)], 2)
        page.go_back()
        page.wait_for_function("__sp.state().id === 'p02'")
        assert listing(page) == ([("p01", 0), ("p02", 0), ("p05", 0)], 1)     # 二重に足されない


def test_places_cross_deck_left_right(webkit_browser, generic_dir):
    # proposal の p04 から minimal へリンクで移り、← で proposal の p04 に戻り、→ で minimal に戻る
    P = proposal(generic_dir, "#p04")
    with session(webkit_browser, P) as page:
        navigate(page, lambda: page.locator('#stage [data-link="1"]').click())
        assert page.url.endswith("minimal.html#m1") and where(page) == ("m1", 0)
        assert listing(page) == ([("p04", 0), ("m1", 0)], 1)               # 並びが、ページをまたいで続いている
        navigate(page, lambda: page.keyboard.press("ArrowLeft"))
        assert page.url.endswith("proposal.html#p04") and where(page) == ("p04", 0)
        assert listing(page) == ([("p04", 0), ("m1", 0)], 0)
        navigate(page, lambda: page.keyboard.press("ArrowRight"))
        assert page.url.endswith("minimal.html#m1") and listing(page)[1] == 1


# ---- 目次 ----

def test_catalog_keys_and_open(webkit_browser, generic_dir):
    index = (generic_dir / "index.html").as_uri()
    with session(webkit_browser, index) as page:
        assert page.locator(".sp-card").count() == 3 and page.locator(".sp-card.sp-selected").get_attribute("data-id") == "proposal"
        page.keyboard.press("ArrowDown")
        assert page.evaluate("__sp.state().id") == "minimal" and page.evaluate("location.hash") == "#minimal"
        navigate(page, lambda: page.keyboard.press("Enter"))
        assert page.url.endswith("minimal.html#m1")
    with session(webkit_browser, index) as page:
        navigate(page, lambda: page.keyboard.press("1"))              # 数字キーで最初のカードを開く
        assert page.url.endswith("proposal.html#p01")


def test_catalog_round_trip_with_h_and_left(webkit_browser, generic_dir):
    index = (generic_dir / "index.html").as_uri()
    with session(webkit_browser, index) as page:                       # 目次→デッキ→ H（目次へ。見ていたデッキが選ばれている）
        navigate(page, lambda: page.keyboard.press("Enter"))           # proposal を開く
        assert page.url.endswith("proposal.html#p01")
        navigate(page, lambda: page.keyboard.press("h"))
        assert page.url.endswith("index.html#proposal") and page.evaluate("__sp.state()")["id"] == "proposal"
    with session(webkit_browser, index) as page:                       # 目次→デッキ→ ←（目次へ戻る）→ →（デッキへ）
        page.keyboard.press("ArrowDown")
        navigate(page, lambda: page.keyboard.press("Enter"))           # minimal を開く（home のないデッキ）
        navigate(page, lambda: page.keyboard.press("ArrowLeft"))
        assert page.url.endswith("index.html#minimal") and page.evaluate("__sp.state()")["kind"] == "catalog"
        navigate(page, lambda: page.keyboard.press("ArrowRight"))
        assert page.url.endswith("minimal.html#m1")


def test_catalog_help(webkit_browser, generic_dir):
    with session(webkit_browser, (generic_dir / "index.html").as_uri()) as page:
        page.keyboard.press("?")
        assert overlay(page) == "help" and page.locator(".sp-help-row").count() >= 6
        page.keyboard.press("ArrowDown")
        assert page.evaluate("__sp.state().id") == "proposal"         # 開いている間は動かない
        page.keyboard.press("Escape")
        assert overlay(page) == "none"


def test_catalog_course_cards_and_paging(webkit_browser, course_dir):
    with session(webkit_browser, (course_dir / "index.html").as_uri()) as page:
        assert page.locator(".sp-card").count() == 7 and page.locator(".sp-card:not([hidden])").count() == 3
        page.keyboard.press("Shift+ArrowDown")
        page.keyboard.press("Shift+ArrowDown")
        assert page.evaluate("__sp.state().id") == "ch-07"
        assert "第7章" in page.inner_text('.sp-card[data-id="ch-07"]')


# ---- ?render は変わらない ----

def test_render_mode_untouched(webkit_browser, generic_dir):
    with page_session(webkit_browser, proposal(generic_dir, "?render"), viewport=(1920, 1080)) as page:
        assert page.evaluate("document.querySelectorAll('[class*=\"sp-\"]:not(#stage)').length") == 0
        assert page.evaluate("document.body.classList.contains('render')")
        assert len(page.evaluate("deckInfo()")) == 9
        page.evaluate("renderSlide(1, 2)")
        assert "入力の誤り" in page.inner_text("#stage")
        page.keyboard.press("ArrowDown")
        assert page.url.endswith("proposal.html?render")


# ---- 画面の大きさ ----

@pytest.mark.parametrize("viewport", VIEWPORTS, ids=lambda v: f"{v[0]}x{v[1]}")
def test_layout_deck_states(webkit_browser, generic_dir, viewport):
    # 通常・N・O・? のそれぞれで、ページがスクロールせず、sp- の部品が画面の外にはみ出さない
    found = []
    with session(webkit_browser, proposal(generic_dir, "#p04"), controls="always", viewport=viewport) as page:
        found += [f"通常: {p}" for p in layout_problems(page)]
        page.keyboard.press("n")
        found += [f"N: {p}" for p in layout_problems(page)]
        page.keyboard.press("n")
        for key, name in (("o", "overview"), ("?", "help")):
            page.keyboard.press(key)
            assert overlay(page) == name
            found += [f"{name}: {p}" for p in layout_problems(page)]
            page.keyboard.press("Escape")
    assert not found, f"{viewport}:\n" + "\n".join(found)


@pytest.mark.parametrize("viewport", VIEWPORTS, ids=lambda v: f"{v[0]}x{v[1]}")
def test_layout_course_catalog(webkit_browser, course_dir, viewport):
    found = []
    with session(webkit_browser, (course_dir / "index.html").as_uri(), viewport=viewport) as page:
        for _ in range(3):
            found += layout_problems(page)
            page.keyboard.press("Shift+ArrowDown")
        page.keyboard.press("?")
        found += layout_problems(page)
    assert not found, f"{viewport}:\n" + "\n".join(found)


@pytest.mark.parametrize("viewport", [(1440, 900), (820, 1180)], ids=lambda v: f"{v[0]}x{v[1]}")
@pytest.mark.parametrize("notes", [False, True], ids=["plain", "notes"])
def test_layout_course_deck_walk(webkit_browser, course_dir, viewport, notes):
    # 講座の形の見本の第2章を全スライド・全段階歩く。例外なく最後まで届き、1つ進むたびにはみ出さない（ノートを開いた状態も）
    found = []
    with session(webkit_browser, (course_dir / "ch-02" / "slides.html").as_uri(), controls="always", notes=notes, viewport=viewport) as page:
        info = page.evaluate("deckInfo()")
        found += layout_problems(page)
        for _ in range(sum(s["steps"] + 1 for s in info) - 1):
            page.keyboard.press("ArrowDown")
            found += [f"{where(page)}: {p}" for p in layout_problems(page)]
        assert where(page) == (info[-1]["id"], info[-1]["steps"])
    assert not found, f"{viewport}:\n" + "\n".join(found[:20])


# ---- 切り替えの動き（View Transitions） ----

def test_motion_next_and_jump_finish_in_webkit(webkit_browser, generic_dir):
    # 隣への移動とジャンプが例外なく終わり、最後の表示・hash・直近の場所が動きなしと同じになる（WebKit ではページ全体を動かす）
    with page_session(webkit_browser, "about:blank", reduced_motion="no-preference") as page:
        page.set_default_timeout(10000)
        page.goto(proposal(generic_dir, "#p01"))
        page.wait_for_function("!!window.__sp")
        page.keyboard.press("ArrowDown")
        assert page.evaluate("__sp.motion().kind") == "next"
        page.evaluate("__sp.motionDone()")
        page.keyboard.press("End")
        assert page.evaluate("__sp.motion().kind") == "jump"
        page.evaluate("__sp.motionDone()")
        assert where(page) == ("p08", 0)
        assert page.evaluate("location.hash") == "#p08"
        assert listing(page) == ([("p01", 0), ("p02", 0), ("p08", 0)], 2)
        assert page.locator(".sp-jumpmsg").count() == 0
        assert page.evaluate("document.documentElement.className").find("sp-vt") < 0
        assert "ご検討をお願いします" in page.evaluate("document.getElementById('stage').innerText")
