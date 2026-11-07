"""切り替えの動き（ブラウザの View Transitions）の試験。動きを止めない（reduced_motion="no-preference"）で開く。

見るのは外から見える動きだけ：試験用の窓口 __sp.motion()（最後に選んだ動きの種類）と __sp.motionDone()（動きが終わるまで待つ）、
舞台・hash・直近の場所・ノートの結果、動いている途中の画面（View Transitions の animation を止めて撮る）。
同じ操作を動きなし（reduce）でも行い、動きが終わったあとの結果が同じであることを確かめる。
汎用の見本 examples/generic/proposal.html を使う（p01〜p08、p03b。p02 は段階2つ、p04 のリンク0は p07 へ、リンク1は別のページへ）。
"""
import io
import json

import pytest
from PIL import Image

from helpers import page_session

SETTINGS_KEY = "sp-settings-v1"
ARRIVE_KEY = "sp-arrive-v1"
BAND = (20, 24, 29)                                  # 舞台の外の黒い帯の色（#14181d）

# View Transitions を始めた回数と、最後の動きの値（window.__vt）を持つ。Element.animate の呼び出しも覚える（着いたときのフェードイン）
INIT = """
(() => {
  window.__vtCalls = 0;
  const original = document.startViewTransition && document.startViewTransition.bind(document);
  if (original) document.startViewTransition = cb => { window.__vtCalls++; const t = original(cb); window.__vt = t; return t; };
  window.__anim = [];
  const animate = Element.prototype.animate;
  Element.prototype.animate = function (keyframes, options) { window.__anim.push({ id: this.id, keyframes, options }); return animate.call(this, keyframes, options); };
})();
"""


def proposal(generic_dir, suffix=""):
    return (generic_dir / "proposal.html").as_uri() + suffix


@pytest.fixture
def moving(browser):
    """動かす設定（reduced_motion="no-preference"）で開く道具。with moving(url) as page。"""
    return lambda url, **kw: opened(browser, url, "no-preference", **kw)


@pytest.fixture
def still(browser):
    """動きを止める設定（reduce）で開く道具。"""
    return lambda url, **kw: opened(browser, url, "reduce", **kw)


def opened(browser, url, reduced_motion, viewport=(1440, 900), settings=None):
    """page_session のラッパー。INIT を入れてから url を開き、プレイヤーが動き出すまで待つ。settings があれば、保存された設定として先に入れる。"""
    from contextlib import contextmanager

    @contextmanager
    def run():
        with page_session(browser, "about:blank", viewport=viewport, reduced_motion=reduced_motion) as page:
            page.set_default_timeout(10000)
            page.add_init_script(INIT)
            if settings is not None:
                page.add_init_script(f"try {{ localStorage.setItem({json.dumps(SETTINGS_KEY)}, {json.dumps(settings)}); }} catch (e) {{}}")
            page.goto(url)
            page.wait_for_function("!!window.__sp")
            yield page
    return run()


def where(page):
    s = page.evaluate("__sp.state()")
    return s["id"], s["step"]


def kind(page):
    return page.evaluate("__sp.motion().kind")


def settle(page):
    """動きが終わるまで待つ。"""
    page.evaluate("__sp.motionDone()")


def calls(page):
    return page.evaluate("window.__vtCalls")


def listing(page):
    p = page.evaluate("__sp.places()")
    return [(i["ref"], i["step"]) for i in p["items"]], p["pos"]


def result(page):
    """動きが終わったあとの結果：今の場所・hash・直近の場所・位置の表示・ノート・舞台の文字。"""
    settle(page)
    return {
        "where": where(page),
        "hash": page.evaluate("location.hash"),
        "places": listing(page),
        "pos": page.evaluate("document.querySelector('.sp-pos').textContent"),
        "notes": page.evaluate("(document.querySelector('.sp-notes') || {}).textContent || ''"),
        "stage": page.evaluate("document.getElementById('stage').innerText"),
    }


def click_button(page, text):
    page.locator(".sp-controls button", has_text=text).dispatch_event("click")


# ---- 1. 動きの判定 ----

def act_key(key):
    return lambda page: page.keyboard.press(key)


def act_button(text):
    return lambda page: click_button(page, text)


def act_link(n):
    return lambda page: page.locator(f'#stage [data-link="{n}"]').click()


def act_overview(index):
    def run(page):
        page.keyboard.press("o")
        page.locator(f'.sp-thumb[data-index="{index}"]').click()
    return run


CASES = [
    ("down", "#p01", act_key("ArrowDown"), "next", ("p02", 0)),
    ("up", "#p02", act_key("ArrowUp"), "prev", ("p01", 0)),
    ("space", "#p01", act_key("Space"), "next", ("p02", 0)),
    ("pagedown", "#p01", act_key("PageDown"), "next", ("p02", 0)),
    ("shift-down", "#p01", act_key("Shift+ArrowDown"), "next", ("p02", 0)),
    ("shift-up", "#p03", act_key("Shift+ArrowUp"), "prev", ("p02", 2)),
    ("right-without-place", "#p01", act_key("ArrowRight"), "next", ("p02", 0)),
    ("button-next", "#p01", act_button("↓ 次"), "next", ("p02", 0)),
    ("button-prev", "#p02", act_button("↑ 前"), "prev", ("p01", 0)),
    ("link-jump", "#p04", act_link(0), "jump", ("p07", 0)),
    ("home", "#p05", act_key("Home"), "jump", ("p01", 0)),
    ("end", "#p01", act_key("End"), "jump", ("p08", 0)),
    ("overview-far", "#p01", act_overview(5), "jump", ("p05", 0)),
    ("overview-next", "#p01", act_overview(1), "next", ("p02", 0)),
    ("overview-prev", "#p03", act_overview(1), "prev", ("p02", 0)),
    ("overview-jump-back", "#p08", act_overview(1), "jump", ("p02", 0)),
    ("step-only", "#p02", act_key("ArrowDown"), "none", ("p02", 1)),
]


@pytest.mark.parametrize("start,act,expected_kind,expected_where", [c[1:] for c in CASES], ids=[c[0] for c in CASES])
def test_motion_kind_is_decided_by_result(moving, generic_dir, start, act, expected_kind, expected_where):
    with moving(proposal(generic_dir, start)) as page:
        assert kind(page) == "none" and calls(page) == 0           # 初めての表示は動かさない
        act(page)
        assert where(page) == expected_where
        assert kind(page) == expected_kind
        assert calls(page) == (0 if expected_kind == "none" else 1)
        settle(page)


def test_motion_back_to_previous_place_is_jump(moving, generic_dir):
    # p04 のリンクで p07 へ飛び、← で p04 へ戻る（隣ではない）
    with moving(proposal(generic_dir, "#p04")) as page:
        act_link(0)(page)
        assert kind(page) == "jump"
        settle(page)
        page.keyboard.press("ArrowLeft")
        assert where(page) == ("p04", 0) and kind(page) == "jump"
        settle(page)


def test_motion_place_to_adjacent_slide_is_next_or_prev(moving, generic_dir):
    # リンクで p04→p05 の隣へ移った結果の ←（p05→p04）は、隣への移動：prev
    with moving(proposal(generic_dir, "#p04")) as page:
        page.keyboard.press("ArrowDown")                          # p05（隣：next）
        assert where(page) == ("p05", 0) and kind(page) == "next"
        settle(page)
        page.keyboard.press("ArrowLeft")                          # 直近の場所：p04
        assert where(page) == ("p04", 0) and kind(page) == "prev"
        settle(page)
        page.keyboard.press("ArrowRight")
        assert where(page) == ("p05", 0) and kind(page) == "next"
        settle(page)


def test_motion_browser_back_forward_follow_result(moving, generic_dir):
    # アドレス欄の hash の変更・ブラウザの戻る・進むも、移った結果で決まる（プレイヤー自身の書き換えは履歴を足さないので、hash を直接変える）
    with moving(proposal(generic_dir, "#p01")) as page:
        page.keyboard.press("ArrowDown")
        settle(page)
        page.evaluate("location.hash = '#p03'")                    # p02 → p03：隣
        page.wait_for_function("__sp.state().id === 'p03'")
        assert kind(page) == "next"
        settle(page)
        page.evaluate("location.hash = '#p08'")                    # p03 → p08：隣ではない
        page.wait_for_function("__sp.state().id === 'p08'")
        assert kind(page) == "jump"
        settle(page)
        page.evaluate("history.back()")
        page.wait_for_function("__sp.state().id === 'p03'")
        assert kind(page) == "jump"
        settle(page)
        page.evaluate("history.back()")
        page.wait_for_function("__sp.state().id === 'p02'")
        assert kind(page) == "prev"
        settle(page)
        page.evaluate("history.forward()")
        page.wait_for_function("__sp.state().id === 'p03'")
        assert kind(page) == "next"
        settle(page)


# ---- 2. 終わったあとの結果は、動きなしと同じ ----

SEQUENCE = ["n", "ArrowDown", "ArrowDown", "ArrowDown", "ArrowDown", "ArrowUp", "Shift+ArrowDown", "End", "ArrowLeft", "Home",
            "ArrowRight", "ArrowRight", "ArrowLeft", "o", "Escape", "ArrowDown"]


def test_motion_result_equals_still(moving, still, generic_dir):
    with still(proposal(generic_dir, "#p01")) as a, moving(proposal(generic_dir, "#p01")) as b:
        for key in SEQUENCE:
            a.keyboard.press(key)
            b.keyboard.press(key)
            assert result(a) == result(b), f"{key} のあとで違う"
        assert calls(a) == 0 and calls(b) > 0


def test_motion_result_equals_still_after_jump_by_link(moving, still, generic_dir):
    with still(proposal(generic_dir, "#p04")) as a, moving(proposal(generic_dir, "#p04")) as b:
        for page in (a, b):
            page.keyboard.press("n")
            act_link(0)(page)
        assert result(a) == result(b)
        for page in (a, b):
            page.keyboard.press("ArrowLeft")
        assert result(a) == result(b) and result(b)["where"] == ("p04", 0)


# ---- 3. 速く押す ----

@pytest.mark.parametrize("presses", [4, 7])
def test_motion_rapid_presses_advance_every_time(moving, still, generic_dir, presses):
    with still(proposal(generic_dir, "#p05")) as a, moving(proposal(generic_dir, "#p05")) as b:
        for _ in range(presses):
            a.keyboard.press("ArrowDown")
        for _ in range(presses):
            b.keyboard.press("ArrowDown")                         # 動きの途中（300ms の間）に次を押す
        expected = result(a)
        assert result(b) == expected and expected["where"][0] != "p05"
        assert b.evaluate("document.documentElement.className").find("sp-vt") < 0       # 動きの印は残らない
        assert b.locator(".sp-jumpmsg").count() == 0


def test_motion_rapid_mixed_presses_end_in_the_right_place(moving, still, generic_dir):
    keys = ["ArrowDown", "End", "ArrowUp", "ArrowUp", "Home", "ArrowDown", "Shift+ArrowDown"]
    with still(proposal(generic_dir, "#p02")) as a, moving(proposal(generic_dir, "#p02")) as b:
        for key in keys:
            a.keyboard.press(key)
        for key in keys:
            b.keyboard.press(key)
        assert result(b) == result(a)


# ---- 4. 設定「なし」と reduce では始めない ----

def test_motion_reduce_does_not_start(still, generic_dir):
    with still(proposal(generic_dir, "#p01")) as page:
        page.keyboard.press("ArrowDown")
        page.keyboard.press("End")
        assert kind(page) == "none" and calls(page) == 0
        assert where(page) == ("p08", 0)


def test_motion_setting_off_does_not_start(moving, generic_dir):
    with moving(proposal(generic_dir, "#p01"), settings=json.dumps({"motion": False})) as page:
        page.keyboard.press("ArrowDown")
        page.keyboard.press("End")
        assert kind(page) == "none" and calls(page) == 0
        assert where(page) == ("p08", 0)


def test_motion_broken_setting_returns_to_default(moving, generic_dir):
    with moving(proposal(generic_dir, "#p01"), settings=json.dumps({"motion": "yes", "controls": "never"})) as page:
        page.keyboard.press("ArrowDown")
        assert kind(page) == "next" and calls(page) == 1
        settle(page)


def test_motion_help_choice_is_saved_and_applied(moving, generic_dir):
    with moving(proposal(generic_dir, "#p01")) as page:
        page.keyboard.press("?")
        on, off = page.locator('.sp-help [data-sp-motion="on"]'), page.locator('.sp-help [data-sp-motion="off"]')
        assert (on.get_attribute("aria-checked"), off.get_attribute("aria-checked")) == ("true", "false")      # 既定は「あり」
        off.click()
        assert (on.get_attribute("aria-checked"), off.get_attribute("aria-checked")) == ("false", "true")
        assert json.loads(page.evaluate(f"localStorage.getItem({json.dumps(SETTINGS_KEY)})"))["motion"] is False
        page.keyboard.press("Escape")
        page.keyboard.press("ArrowDown")
        assert where(page) == ("p02", 0) and kind(page) == "none" and calls(page) == 0
        page.keyboard.press("?")
        page.locator('.sp-help [data-sp-motion="on"]').click()
        assert json.loads(page.evaluate(f"localStorage.getItem({json.dumps(SETTINGS_KEY)})"))["motion"] is True
        page.keyboard.press("Escape")
        page.keyboard.press("ArrowUp")
        assert where(page) == ("p01", 0) and kind(page) == "prev" and calls(page) == 1
        settle(page)


def test_motion_does_not_start_while_overlay_is_open(moving, generic_dir):
    # 操作の一覧が開いている間は、動きの層が重なりを隠すので動かさない（ブラウザの戻る・進むで場所が変わっても）
    with moving(proposal(generic_dir, "#p01")) as page:
        page.keyboard.press("End")
        settle(page)
        page.keyboard.press("?")
        page.evaluate("location.hash = '#p05'")
        page.wait_for_function("__sp.state().id === 'p05'")
        assert kind(page) == "none" and calls(page) == 1


# ---- 5. ジャンプの途中の文字 ----

def pause_animations(page, t):
    """動きの animation を止めて、t ミリ秒の所に合わせる（決まった瞬間の画面を撮るため）。"""
    page.evaluate("window.__vt.ready")
    page.evaluate("t => { for (const a of document.getAnimations()) { a.pause(); a.currentTime = t; } }", t)
    page.wait_for_timeout(100)


def resume_animations(page):
    page.evaluate("for (const a of document.getAnimations()) a.play()")


def screenshot(page):
    return Image.open(io.BytesIO(page.screenshot())).convert("RGB")


def brightest(img, box):
    return max(max(p) for p in img.crop(box).getdata())


def test_motion_jump_shows_faint_message_then_removes_it(moving, generic_dir):
    with moving(proposal(generic_dir, "#p01"), viewport=(1440, 900)) as page:
        assert page.locator(".sp-jumpmsg").count() == 0
        page.keyboard.press("End")
        assert kind(page) == "jump"
        page.wait_for_selector(".sp-jumpmsg", state="attached")
        assert page.locator(".sp-jumpmsg").inner_text() == "URLジャンプします"
        pause_animations(page, 250)                                # 真ん中：前のスライドは消え、次のスライドはまだ現れていない
        img = screenshot(page)
        center = (620, 420, 820, 480)
        assert brightest(img, center) > 100                        # 薄い文字（背景は #14181d = 29）
        faint = img.crop(center).getdata()
        assert max(max(p) for p in faint) < 200                    # 白くはない（不透明度 0.5 前後）
        resume_animations(page)
        settle(page)
        assert page.locator(".sp-jumpmsg").count() == 0
        assert where(page) == ("p08", 0)


def test_motion_next_has_no_message(moving, generic_dir):
    with moving(proposal(generic_dir, "#p01")) as page:
        page.keyboard.press("ArrowDown")
        page.wait_for_timeout(100)
        assert page.locator(".sp-jumpmsg").count() == 0
        settle(page)


# ---- 6. 隣への動きの途中の画面は、スライドの枠の外へはみ出さない ----

@pytest.mark.parametrize("key,start", [("ArrowDown", "#p01"), ("ArrowUp", "#p02")])
def test_motion_slide_stays_inside_stage_frame(moving, generic_dir, key, start):
    with moving(proposal(generic_dir, start), viewport=(1800, 700)) as page:
        r = page.evaluate("(() => { const r = document.getElementById('stage').getBoundingClientRect(); return [r.left, r.right]; })()")
        left, right = round(r[0]), round(r[1])
        assert left > 100                                           # 横に黒い帯が出る大きさ
        page.keyboard.press(key)
        pause_animations(page, 150)
        img = screenshot(page)
        w, h = img.size
        for box in [(0, 0, left - 1, h), (right + 1, 0, w, h)]:
            band = list(img.crop(box).getdata())
            assert all(p == BAND for p in band), "帯にスライドがはみ出している"
        inside = list(img.crop((left + 5, 5, right - 5, h - 5)).getdata())
        assert any(p != BAND for p in inside)                       # 枠の中では動いている（描かれている）
        resume_animations(page)
        settle(page)


def test_motion_next_moves_slide_to_the_left(moving, generic_dir):
    # 次へ：途中で、前のスライドが左へ出ていき、次のスライドが右から入ってくる（左右で白さが違う）
    with moving(proposal(generic_dir, "#p01"), viewport=(1800, 700)) as page:
        page.keyboard.press("ArrowDown")
        pause_animations(page, 150)
        img = screenshot(page)
        resume_animations(page)
        settle(page)
        w, h = img.size
        # p01 は白、p02 は薄い青灰（#f5f7fb 付近）。右の半分に p02 の色、左の半分に白が出ている
        left_pixel, right_pixel = img.getpixel((w // 2 - 150, 100)), img.getpixel((w // 2 + 150, 100))
        assert left_pixel == (255, 255, 255) and right_pixel != (255, 255, 255)


# ---- 6b. 別のページへ移るときのフェードイン（root の経路も、WebKit の見分けを上書きして確かめる） ----

def test_motion_webkit_path_runs_and_ends_clean(moving, generic_dir):
    with moving(proposal(generic_dir, "#p01")) as page:
        page.evaluate("Object.defineProperty(navigator, 'vendor', { get: () => 'Apple Computer, Inc.' })")
        page.keyboard.press("ArrowDown")
        assert page.evaluate("document.documentElement.classList.contains('sp-vt-root')")
        page.keyboard.press("End")
        settle(page)
        assert where(page) == ("p08", 0)
        assert page.evaluate("document.documentElement.className").find("sp-vt") < 0


# ---- 7. 別のページへのリンクで移ったときのフェードイン ----

def navigate(page, action):
    before = page.url.split("#")[0]
    with page.expect_navigation(url=lambda u: u.split("#")[0] != before):
        action()
    page.wait_for_function("!!window.__sp")


def test_motion_arrival_fades_in_after_link_to_other_page(moving, generic_dir):
    with moving(proposal(generic_dir, "#p04")) as page:
        assert page.evaluate(f"sessionStorage.getItem({json.dumps(ARRIVE_KEY)})") is None
        navigate(page, lambda: page.locator('#stage [data-link="1"]').click())
        assert page.url.endswith("minimal.html#m1")
        assert page.evaluate("__sp.motion().arrival") is True
        settle(page)
        anims = page.evaluate("window.__anim")
        assert any([k["opacity"] for k in a["keyframes"]] == [0, 1] and a["options"]["duration"] == 250 for a in anims)
        assert page.evaluate(f"sessionStorage.getItem({json.dumps(ARRIVE_KEY)})") is None      # 使って消す
        page.reload()
        page.wait_for_function("!!window.__sp")
        assert page.evaluate("__sp.motion().arrival") is False                                 # 再読み込みでは動かさない


def test_motion_arrival_fades_in_after_back_to_other_page(moving, generic_dir):
    # p04 のリンクで別のページへ移り、← で戻る（goToPlace の別のページ）：どちらの着いた側もフェードインする
    with moving(proposal(generic_dir, "#p04")) as page:
        navigate(page, lambda: page.locator('#stage [data-link="1"]').click())
        settle(page)
        navigate(page, lambda: page.keyboard.press("ArrowLeft"))
        assert page.url.endswith("proposal.html#p04")
        assert page.evaluate("__sp.motion().arrival") is True
        settle(page)


def test_motion_arrival_fades_in_catalog_cards(moving, generic_dir):
    # H で目次へ（openPage）：着いた目次は、カードの並び全体をフェードインする。アドレス欄から開いたときは動かさない
    with moving(proposal(generic_dir, "#p01")) as page:
        navigate(page, lambda: page.keyboard.press("h"))
        assert page.evaluate("__sp.state().kind") == "catalog"
        assert page.evaluate("__sp.motion().arrival") is True
        settle(page)
        assert page.evaluate("window.__anim.some(a => a.keyframes.length === 2 && a.options.duration === 250)")
    with moving((generic_dir / "index.html").as_uri()) as page:
        assert page.evaluate("__sp.motion().arrival") is False


def test_motion_arrival_not_played_when_opened_from_address_bar(moving, generic_dir):
    with moving(proposal(generic_dir, "#p04")) as page:
        assert page.evaluate("__sp.motion().arrival") is False
        page.goto((generic_dir / "minimal.html").as_uri())
        page.wait_for_function("!!window.__sp")
        assert page.evaluate("__sp.motion().arrival") is False
        assert page.evaluate("window.__anim.length") == 0


def test_motion_arrival_is_not_played_with_reduce(still, generic_dir):
    with still(proposal(generic_dir, "#p04")) as page:
        navigate(page, lambda: page.locator('#stage [data-link="1"]').click())
        assert page.evaluate("__sp.motion().arrival") is False
        assert page.evaluate(f"sessionStorage.getItem({json.dumps(ARRIVE_KEY)})") is None


def test_motion_arrival_stale_mark_is_ignored(moving, generic_dir):
    # 10秒より前の印は使わない（使えなくても消す）
    with moving(proposal(generic_dir, "#p01")) as page:
        page.evaluate(f"sessionStorage.setItem({json.dumps(ARRIVE_KEY)}, String(Date.now() - 20000))")
        page.reload()
        page.wait_for_function("!!window.__sp")
        assert page.evaluate("__sp.motion().arrival") is False
        assert page.evaluate(f"sessionStorage.getItem({json.dumps(ARRIVE_KEY)})") is None


# ---- 6. 動きの途中の操作 ----
# 描画前の順序は、同じイベントループの中で送って作る（View Transitions の更新は、その後に走る）。
# p04（リンクが5つ）で ↓ を押すと p05・段階0 に着く。この段階では見えるリンクがない（リンク0 は段階2から）


def test_motion_link_view_right_after_move_does_not_use_stale_stage(moving, still, generic_dir):
    # M1・L：描画待ちの間に L を送っても、古い舞台の要素と p05 の links を組み合わせない（動きなしと同じ結果）
    outcomes = []
    for open_page in (moving, still):
        with open_page(proposal(generic_dir, "#p04")) as page:
            page.evaluate("""async () => {
              for (const key of ['ArrowDown', 'l']) document.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true }));
              await __sp.motionDone();
            }""")
            outcomes.append((where(page), page.locator(".sp-linkframe").count(), page.locator(".sp-linkview").count()))
    assert outcomes[0] == outcomes[1] == (("p05", 0), 0, 0)


def test_motion_click_on_stale_link_right_after_move_does_nothing(moving, generic_dir):
    # M1・クリック：移る前の舞台の要素を、↓の直後に押しても、p05 のリンク0 として p02 へ飛ばない
    with moving(proposal(generic_dir, "#p04")) as page:
        page.evaluate("""async () => {
          const old = document.querySelector('#stage [data-link="0"]');
          document.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }));
          old.click();
          await __sp.motionDone();
        }""")
        assert where(page) == ("p05", 0)
        assert page.locator(".sp-more, .sp-linkview").count() == 0


def test_motion_enter_on_stale_link_right_after_move_does_nothing(moving, generic_dir):
    # M1・Enter：古い要素に焦点があるまま ↓ の直後に Enter を送っても、p02 へ飛ばない
    with moving(proposal(generic_dir, "#p04")) as page:
        page.evaluate("""async () => {
          const old = document.querySelector('#stage [data-link="0"]');
          old.focus();
          document.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }));
          old.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
          await __sp.motionDone();
        }""")
        assert where(page) == ("p05", 0)


# 別のツールが作ったデッキの再現：p04 のリンク0 を、同じ属性・中身で href のある a に置き換える
REPLACE_WITH_ANCHOR = """
  const old = document.querySelector('#stage [data-link="0"]');
  const a = document.createElement('a');
  for (const attr of old.attributes) a.setAttribute(attr.name, attr.value);
  a.innerHTML = old.innerHTML;
  a.href = '#p03';
  old.replaceWith(a);
"""


def test_motion_click_on_stale_anchor_right_after_move_is_fully_ignored(moving, generic_dir):
    # F1・クリック：href のある古い a を ↓ の直後に押しても、ブラウザの既定の動きで #p03 へ移らない
    with moving(proposal(generic_dir, "#p04")) as page:
        prevented = page.evaluate("""async () => {
          %s
          document.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }));
          const ok = a.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, button: 0 }));
          await __sp.motionDone();
          return !ok;
        }""" % REPLACE_WITH_ANCHOR)
        assert prevented
        assert where(page) == ("p05", 0)
        assert page.evaluate("location.hash") == "#p05"
        assert "p03" not in json.dumps(page.evaluate("__sp.places()"))


def test_motion_enter_on_stale_anchor_right_after_move_is_fully_ignored(moving, generic_dir):
    # F1・Enter：href のある古い a で、↓ の直後の Enter は defaultPrevented（ブラウザの既定のクリックが起きない）
    with moving(proposal(generic_dir, "#p04")) as page:
        prevented = page.evaluate("""async () => {
          %s
          a.focus();
          document.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }));
          const ok = a.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }));
          await __sp.motionDone();
          return !ok;
        }""" % REPLACE_WITH_ANCHOR)
        assert prevented
        assert where(page) == ("p05", 0)
        assert page.evaluate("location.hash") == "#p05"


def test_motion_click_on_reused_element_is_not_read_as_link_of_new_slide(moving, generic_dir):
    # F1・要素の使い回し：描画関数が古いリンクの要素（同じオブジェクト）を移動先でも使うとき、描画待ちの間のクリックは移動先のリンク0にならない
    # （p05・段階2 のリンク0 は p02 へ、p04 のリンク0 は p07 へ。Shift+↑ で p04 へ動く）
    with moving(proposal(generic_dir, "#p05.2")) as page:
        page.evaluate("""async () => {
          const old = document.querySelector('#stage [data-link="0"]');
          const render = window.slideDeck.render;
          window.slideDeck.render = function (index, step, target) {
            const result = render.call(this, index, step, target);
            const fresh = target.querySelector('[data-link="0"]');
            if (fresh && fresh !== old) fresh.replaceWith(old);
            return result;
          };
          document.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowUp', shiftKey: true, bubbles: true }));
          old.click();
          await __sp.motionDone();
          window.slideDeck.render = render;
        }""")
        assert where(page)[0] == "p04"
        assert "p07" not in json.dumps(page.evaluate("__sp.places()"))


def test_motion_click_on_current_link_while_only_animating_keeps_motion(moving, generic_dir):
    # 描画済みでアニメーションだけが続いているときは、舞台のクリックで動きを止めない（今の要素は最新）
    with moving(proposal(generic_dir, "#p03b.1")) as page:         # p03b は段階1が最後
        page.keyboard.press("ArrowDown")                           # p04
        page.evaluate("window.__vt.updateCallbackDone")
        assert page.evaluate("__sp.motion().kind") == "next"
        page.evaluate("document.querySelector('#stage').click()")
        assert page.evaluate("document.documentElement.className.includes('sp-vt-')")
        settle(page)


def marks_visibility(page):
    return page.evaluate("getComputedStyle(document.querySelector('.sp-linkmarks')).visibility")


def test_motion_link_marks_hidden_in_middle_of_jump(moving, generic_dir):
    # M2：舞台だけを動かす間は、印の層を隠す（移動先の印だけが見えないように）。終わると印が見える
    with moving(proposal(generic_dir, "#p01")) as page:
        page.evaluate("location.hash = '#p04'")
        page.wait_for_function("__sp.state().id === 'p04'")
        assert kind(page) == "jump"
        pause_animations(page, 250)
        assert marks_visibility(page) == "hidden"
        resume_animations(page)
        settle(page)
        assert marks_visibility(page) == "visible"
        assert page.locator(".sp-linkmarks .sp-linkmark").count() >= 1


def test_motion_link_marks_hidden_in_middle_of_adjacent_move(moving, generic_dir):
    with moving(proposal(generic_dir, "#p03b.1")) as page:
        page.keyboard.press("ArrowDown")                           # p04（リンクがある）
        assert kind(page) == "next"
        pause_animations(page, 250)
        assert where(page) == ("p04", 0)
        assert marks_visibility(page) == "hidden"
        resume_animations(page)
        settle(page)
        assert marks_visibility(page) == "visible"
        assert page.locator(".sp-linkmarks .sp-linkmark").count() >= 1


@pytest.mark.parametrize("key,selector", [("?", ".sp-help"), ("o", ".sp-overview"), ("l", ".sp-linkview")])
def test_motion_opening_overlay_in_middle_ends_the_motion(moving, generic_dir, key, selector):
    # M3：動きの途中で重なりを開くと、動きを終え、舞台は移動先を描き、動きの層が重なりにかぶらない
    # （L は見えるリンクのあるスライドへ着いたときだけ開く。p01 から p04 へ飛ぶ）
    target = "#p04" if key == "l" else None
    with moving(proposal(generic_dir, "#p01")) as page:
        if target:
            page.evaluate(f"location.hash = '{target}'")
            page.wait_for_function("__sp.state().id === 'p04'")
            expected = ("p04", 0)
        else:
            page.keyboard.press("End")
            expected = ("p08", 0)
        assert kind(page) == "jump"
        pause_animations(page, 250)
        page.keyboard.press(key)
        page.wait_for_selector(selector, state="attached")
        assert page.evaluate("document.documentElement.className.includes('sp-vt-') || document.documentElement.className.includes('sp-mv-')") is False
        assert page.locator(".sp-jumpmsg").count() == 0
        assert where(page) == expected
        assert page.evaluate("document.getElementById('stage').innerText") != ""
        settle(page)
