"""画面の部品（操作ボタン、ノート、操作の一覧、全画面、Esc、H）の試験（約束 §3.2）。

見るのは player.js の外から見える動きだけ：画面の要素（.sp-controls・.sp-notes・.sp-help）、キー操作、
localStorage、試験用の窓口 window.__sp。

試験の決め事：
- 操作ボタンの出し方は、設定を localStorage に先に入れて（seed）開く。自動で消える動きを見る試験だけ、何も入れずに開く
- 時間は page.clock（偽の時計）で進める。CSS の遷移（0.2 秒）は本物の時間で進むので、
  「見えない」は expect の待ち（to_be_hidden）で確かめる
- 全画面は本物には切り替えず、requestFullscreen・exitFullscreen を差し替えて呼ばれ方を見る
"""
import json
import re
from contextlib import contextmanager
from pathlib import Path

import pytest
from playwright.sync_api import expect

from helpers import page_session, slides_url

REPO = Path(__file__).resolve().parents[1]
PLAYER_JS = REPO / "player" / "player.js"
KEY = "sp-settings-v1"
PLACES_KEY = "sp-places-v1"

# H で開く目次（proposal の home は index.html、デッキの ID を hash に付ける）
HOME_URL = re.compile(r"/index\.html#proposal$")

# 操作ボタンの文字（左から並ぶ順）。H はデッキに home があるときだけ
BUTTONS = ["↑ 前", "↓ 次", "← 戻る", "→ 進む", "O 一覧", "T 一覧つき", "N ノート", "M メモ", "L リンク", "H 目次", "P PDF", "D 書き込み", "F 全画面", "?"]


# ---- 試験の道具 ----

def proposal_url(generic_dir, suffix=""):
    return (generic_dir / "proposal.html").as_uri() + suffix


def seed_script(controls="auto", notes=False):
    """設定を localStorage に入れる仕掛け（読み込みのたびに入れ直す）。"""
    value = json.dumps({"controls": controls, "notes": notes})
    return f"try {{ localStorage.setItem({json.dumps(KEY)}, {json.dumps(value)}); }} catch (e) {{}}"


@contextmanager
def ui_session(browser, url, controls="always", notes=False, init=None, viewport=(1440, 900), seed=True):
    """設定を入れてから url を開く（既定は操作ボタンをいつも出す）。pageerror があれば失敗（page_session）。"""
    with page_session(browser, "about:blank", viewport=viewport) as page:
        if seed:
            page.add_init_script(seed_script(controls, notes))
        if init:
            page.add_init_script(init)
        page.goto(url)
        yield page


def freeze_clock(page):
    """偽の時計を入れて止める（進めるのは run_for だけ。本物の時間が混ざらないので、秒数の境目の試験がぶれない）。"""
    page.clock.install(time=1_000)
    page.clock.pause_at(2_000)


def where(page):
    s = page.evaluate("__sp.state()")
    return s["id"], s["step"]


def press(page, key):
    page.keyboard.press(key)
    return where(page)


def toast_text(page):
    el = page.query_selector(".sp-toast")
    return el.inner_text() if el else None


def rect_of(page, selector):
    return page.evaluate(
        "(sel) => { const e = document.querySelector(sel); if (!e) return null; const r = e.getBoundingClientRect();"
        " return {x: r.x, y: r.y, w: r.width, h: r.height, right: r.right, bottom: r.bottom}; }", selector)


def stage_rect(page):
    return rect_of(page, "#stage")


def button(page, label):
    return page.locator(".sp-controls button", has_text=label).first


def notes_open(page):
    return page.query_selector(".sp-notes") is not None


def active_in(page, selector):
    return page.evaluate("s => !!document.activeElement && !!document.activeElement.closest(s)", selector)


def stored_settings(page):
    text = page.evaluate(f"localStorage.getItem({json.dumps(KEY)})")
    return None if text is None else json.loads(text)


def write_variant(tmp_path, generic_dir, name, edit):
    """proposal.html を一時フォルダーに写し、edit(html) で書き換えたものの URL を返す。"""
    html = (generic_dir / "proposal.html").read_text(encoding="utf-8")
    html = html.replace('src="render.js"', f'src="{(generic_dir / "render.js").as_uri()}"')
    html = html.replace('src="../../player/player.js"', f'src="{PLAYER_JS.as_uri()}"')
    html = edit(html)
    path = tmp_path / name
    path.write_text(html, encoding="utf-8")
    return path.as_uri()


# 全画面の差し替え。呼ばれ方を window.__fs に記録する。window.__fsEl に要素を入れると「全画面になっている」ことになる
FULLSCREEN_STUB = """
window.__fs = [];
window.__fsEl = null;
Element.prototype.requestFullscreen = function () { window.__fs.push(['request', this === document.documentElement]); return Promise.resolve(); };
document.exitFullscreen = function () { window.__fs.push(['exit', this === document]); return Promise.resolve(); };
Object.defineProperty(document, 'fullscreenElement', { configurable: true, get: () => window.__fsEl });
"""

RECORD_PREVENTED = """
  window.__prevented = [];
  window.addEventListener('keydown', e => window.__prevented.push([e.key, e.defaultPrevented]));
"""


# ---- 操作ボタンの出し方 ----

def test_controls_autohide(browser, generic_dir):
    # 何も入れずに開く：自動で消す（既定）。読み込んだ直後は出ていない
    with ui_session(browser, proposal_url(generic_dir), seed=False) as page:
        freeze_clock(page)
        controls = page.locator(".sp-controls")
        assert not controls.is_visible()                           # 待たずに確かめる（あとから隠れても通らないように）
        page.mouse.move(700, 300)
        expect(controls).to_be_visible()
        page.clock.run_for(2900)
        page.wait_for_timeout(400)                                 # 隠す遷移（0.2 秒）が始まっていれば、ここで終わる
        assert controls.is_visible()                               # 3 秒の前は出たまま
        page.clock.run_for(200)                                    # 合わせて 3.1 秒（時計は止めてあるので、ぴったり）
        expect(controls).to_be_hidden()
        page.mouse.move(720, 320)                                  # また動かすと出る
        expect(controls).to_be_visible()


def test_controls_autohide_timer_restarts_on_move(browser, generic_dir):
    with ui_session(browser, proposal_url(generic_dir), seed=False) as page:
        freeze_clock(page)
        controls = page.locator(".sp-controls")
        page.mouse.move(700, 300)
        page.clock.run_for(2000)
        page.mouse.move(710, 310)                                  # 動かすと 3 秒を数え直す
        page.clock.run_for(2900)                                   # 最初から 4.9 秒。数え直したので、まだ出ている
        page.wait_for_timeout(400)
        assert controls.is_visible()
        page.clock.run_for(200)
        expect(controls).to_be_hidden()


def center_of(page, selector):
    box = page.locator(selector).first.bounding_box()
    return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2


def test_controls_stay_while_pointer_is_over_them(browser, generic_dir):
    # マウスが操作ボタンの上にある間は、自動で隠さない。離れてから 3000ms で隠す
    with ui_session(browser, proposal_url(generic_dir), seed=False) as page:
        freeze_clock(page)
        controls = page.locator(".sp-controls")
        page.mouse.move(700, 300)
        expect(controls).to_be_visible()
        page.mouse.move(*center_of(page, ".sp-controls .sp-btn"))   # 操作ボタンの上へ
        page.clock.run_for(10000)                                   # 3 秒をはるかに超えても
        page.wait_for_timeout(400)                                  # 隠す遷移（0.2 秒）が始まっていれば、ここで終わる
        assert controls.is_visible()
        page.mouse.move(700, 300)                                   # 離れる：ここから数え直す
        page.clock.run_for(2900)
        page.wait_for_timeout(400)
        assert controls.is_visible()
        page.clock.run_for(200)                                     # 離れてから 3.1 秒
        expect(controls).to_be_hidden()


def test_controls_stay_while_pointer_stays_after_a_click(browser, generic_dir):
    # ボタンを押したあと（押した焦点は外れる）も、マウスがその上にある間は隠さない
    with ui_session(browser, proposal_url(generic_dir), seed=False) as page:
        freeze_clock(page)
        controls = page.locator(".sp-controls")
        page.mouse.move(700, 300)
        expect(controls).to_be_visible()
        page.mouse.move(*center_of(page, ".sp-controls .sp-btn >> nth=1"))      # 「↓ 次」
        page.mouse.down()
        page.mouse.up()
        assert where(page) == ("p02", 0)
        assert page.evaluate("document.activeElement === document.body")        # 押したあとは焦点が外れている
        page.clock.run_for(10000)
        page.wait_for_timeout(400)
        assert controls.is_visible()


def test_controls_stay_while_focus_is_inside(browser, generic_dir):
    # 操作ボタンの中に焦点がある間は、自動で隠さない。焦点が外れてから 3000ms で隠す
    with ui_session(browser, proposal_url(generic_dir), seed=False) as page:
        freeze_clock(page)
        controls = page.locator(".sp-controls")
        page.keyboard.press("Tab")
        expect(controls).to_be_visible()
        assert page.evaluate("!!document.activeElement.closest('.sp-controls')")
        page.clock.run_for(10000)
        page.wait_for_timeout(400)
        assert controls.is_visible()
        page.keyboard.press("Tab")                                  # 隣のボタンへ移っても、中にある
        page.clock.run_for(10000)
        page.wait_for_timeout(400)
        assert controls.is_visible()
        page.evaluate("document.activeElement.blur()")              # 焦点が外れる：ここから数え直す
        page.clock.run_for(2900)
        page.wait_for_timeout(400)
        assert controls.is_visible()
        page.clock.run_for(200)
        expect(controls).to_be_hidden()


def test_controls_hide_when_neither_pointer_nor_focus_is_there(browser, generic_dir):
    # 焦点が中にあっても、そのあとマウスだけが離れる、またはその逆でも、両方が離れるまでは隠さない
    with ui_session(browser, proposal_url(generic_dir), seed=False) as page:
        freeze_clock(page)
        controls = page.locator(".sp-controls")
        page.keyboard.press("Tab")                                  # 焦点が中
        page.mouse.move(*center_of(page, ".sp-controls .sp-btn >> nth=3"))     # マウスも中
        page.mouse.move(700, 300)                                   # マウスだけ離れる
        page.clock.run_for(10000)
        page.wait_for_timeout(400)
        assert controls.is_visible()                                # 焦点がまだ中
        page.evaluate("document.activeElement.blur()")
        page.clock.run_for(3100)
        expect(controls).to_be_hidden()


def test_controls_shown_by_touch_and_pointer_down(browser, generic_dir):
    with ui_session(browser, proposal_url(generic_dir), seed=False) as page:
        freeze_clock(page)
        controls = page.locator(".sp-controls")
        assert not controls.is_visible()
        page.mouse.move(300, 300)
        page.clock.run_for(3500)
        expect(controls).to_be_hidden()
        page.mouse.down()                                          # 押す（タッチも pointerdown を起こす）
        page.mouse.up()
        expect(controls).to_be_visible()


def test_controls_shown_by_touch_event(browser, generic_dir):
    context = browser.new_context(viewport={"width": 1000, "height": 700}, has_touch=True, reduced_motion="reduce")
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    try:
        page.goto(proposal_url(generic_dir))
        assert not page.locator(".sp-controls").is_visible()
        page.touchscreen.tap(300, 300)
        expect(page.locator(".sp-controls")).to_be_visible()
    finally:
        context.close()
    assert errors == []


def test_controls_keyboard_does_not_show_them(browser, generic_dir):
    # キーで進めるだけなら、操作ボタンは出ない（発表中に画面を汚さない）
    with ui_session(browser, proposal_url(generic_dir), seed=False) as page:
        controls = page.locator(".sp-controls")
        assert not controls.is_visible()
        for key in ["ArrowDown", "ArrowDown", "Space", "End", "Home"]:
            press(page, key)
            assert not controls.is_visible(), key                  # 待たずに、押すたびに確かめる（待つと、あとから隠れても通ってしまう）


def test_controls_tab_reveals_them(browser, generic_dir):
    # キーボードだけで操作する人のために、Tab で出して、最初のボタンへ移る
    with ui_session(browser, proposal_url(generic_dir), seed=False) as page:
        assert not page.locator(".sp-controls").is_visible()
        page.keyboard.press("Tab")
        expect(page.locator(".sp-controls")).to_be_visible()
        assert page.evaluate("document.activeElement.textContent") == "↑ 前"


def test_controls_always_stays(browser, generic_dir):
    with ui_session(browser, proposal_url(generic_dir), controls="always") as page:
        freeze_clock(page)
        expect(page.locator(".sp-controls")).to_be_visible()       # 動かさなくても出ている
        page.mouse.move(700, 300)
        page.clock.run_for(10000)
        expect(page.locator(".sp-controls")).to_be_visible()


def test_controls_never_stays_hidden(browser, generic_dir):
    with ui_session(browser, proposal_url(generic_dir), controls="never") as page:
        expect(page.locator(".sp-controls")).to_be_hidden()
        page.mouse.move(700, 300)
        page.mouse.down()
        page.mouse.up()
        page.keyboard.press("Tab")
        expect(page.locator(".sp-controls")).to_be_hidden()


def test_controls_setting_saved(browser, generic_dir):
    # ? で「いつも出す」を選ぶ → 保存され、再読み込み後も（マウスを動かさなくても）見えている
    with ui_session(browser, proposal_url(generic_dir), seed=False) as page:
        assert not page.locator(".sp-controls").is_visible()
        page.keyboard.press("?")
        page.locator(".sp-help button", has_text="いつも出す").click()
        assert stored_settings(page) == {"controls": "always", "notes": False}
        page.keyboard.press("Escape")
        page.reload()
        expect(page.locator(".sp-controls")).to_be_visible()
        # 「出さない」に変えて再読み込み：出ない
        page.keyboard.press("?")
        page.locator(".sp-help button", has_text="出さない").click()
        assert stored_settings(page) == {"controls": "never", "notes": False}
        expect(page.locator(".sp-controls")).to_be_hidden()        # 選んだ時点で消える
        page.reload()
        page.mouse.move(700, 300)
        assert not page.locator(".sp-controls").is_visible()
        # 「自動で消す」に戻す：読み込み直後は出ていない
        page.keyboard.press("?")
        page.locator(".sp-help button", has_text="自動で消す").click()
        assert stored_settings(page) == {"controls": "auto", "notes": False}
        page.keyboard.press("Escape")
        page.reload()
        assert not page.locator(".sp-controls").is_visible()


def test_help_shows_current_choice(browser, generic_dir):
    with ui_session(browser, proposal_url(generic_dir), controls="never") as page:
        page.keyboard.press("?")
        pressed = page.evaluate("Array.from(document.querySelectorAll('.sp-help [aria-pressed=\"true\"]'), b => b.textContent)")
        assert pressed == ["出さない"]
        page.locator(".sp-help button", has_text="いつも出す").click()
        pressed = page.evaluate("Array.from(document.querySelectorAll('.sp-help [aria-pressed=\"true\"]'), b => b.textContent)")
        assert pressed == ["いつも出す"]


def test_controls_buttons_present(browser, generic_dir):
    with ui_session(browser, proposal_url(generic_dir)) as page:
        labels = page.evaluate("Array.from(document.querySelectorAll('.sp-controls button'), b => b.textContent)")
        assert labels == BUTTONS
        assert page.locator(".sp-controls .sp-pos").inner_text() == "1 / 9"
        tags = page.evaluate("Array.from(document.querySelectorAll('.sp-controls button'), b => b.type)")
        assert set(tags) == {"button"}


def test_no_home_no_h(browser, generic_dir):
    # minimal（home なし）：H のボタンがなく、H を押しても何も起きない（知らせも出ない）
    url = (generic_dir / "minimal.html").as_uri()
    with ui_session(browser, url) as page:
        labels = page.evaluate("Array.from(document.querySelectorAll('.sp-controls button'), b => b.textContent)")
        assert labels == [b for b in BUTTONS if not b.startswith("H ")]
        page.keyboard.press("h")
        page.keyboard.press("H")
        page.wait_for_timeout(300)
        assert page.url == url + "#m1"
        assert toast_text(page) is None
        page.keyboard.press("?")
        assert "目次" not in page.inner_text(".sp-help")           # 操作の一覧にも出さない


def test_controls_buttons_navigate(browser, generic_dir):
    with ui_session(browser, proposal_url(generic_dir)) as page:
        button(page, "↓ 次").click()
        assert where(page) == ("p02", 0)
        assert page.locator(".sp-pos").inner_text() == "2 / 9　段階 0/2"
        button(page, "↓ 次").click()
        assert where(page) == ("p02", 1)
        assert page.locator(".sp-pos").inner_text() == "2 / 9　段階 1/2"
        button(page, "↑ 前").click()
        assert where(page) == ("p02", 0)
        button(page, "← 戻る").click()                              # 直近の場所：p01
        assert where(page) == ("p01", 0)
        button(page, "→ 進む").click()
        assert where(page) == ("p02", 0)
        # 端では動かず知らせる
        page.goto(proposal_url(generic_dir, "#p01"))
        button(page, "↑ 前").click()
        assert where(page) == ("p01", 0) and toast_text(page)


def test_controls_forward_without_next_place_is_same_as_next(browser, generic_dir):
    # 先の場所がないときの「→ 進む」は「↓ 次」と同じ。開いたばかりのデッキで押し続け、最後の知らせ（のあとの1回）まで毎回一致する
    def walk(label):
        with ui_session(browser, proposal_url(generic_dir)) as page:
            trace = []
            for _ in range(40):
                button(page, label).click()
                p = page.evaluate("__sp.places()")
                trace.append((where(page), page.evaluate("location.hash"), toast_text(page),
                              [(i["ref"], i["step"]) for i in p["items"]], p["pos"]))
                if trace[-1][2]:
                    break
            button(page, label).click()                            # 最後の知らせのあとにもう1回
            trace.append((where(page), toast_text(page)))
            return trace

    by_next = walk("↓ 次")
    assert by_next[-2][2] == "最後のスライドです" and by_next[-1] == (by_next[-2][0], "最後のスライドです")
    assert len(by_next) > 12                                       # 段階を含めて最後まで進んでいる
    by_forward = walk("→ 進む")
    assert by_forward == by_next                                   # 「これより先の場所はありません」にはならない


def test_controls_buttons_other(browser, generic_dir):
    with ui_session(browser, proposal_url(generic_dir), init=FULLSCREEN_STUB) as page:
        button(page, "N ノート").click()
        assert notes_open(page)
        button(page, "N ノート").click()
        assert not notes_open(page)
        button(page, "?").click()
        assert page.query_selector(".sp-help") is not None
        page.keyboard.press("Escape")
        button(page, "F 全画面").click()
        assert page.evaluate("__fs") == [["request", True]]


def test_controls_h_button(browser, generic_dir):
    with ui_session(browser, proposal_url(generic_dir, "#p03")) as page:
        button(page, "H 目次").click()
        page.wait_for_url(HOME_URL)


def test_controls_do_not_change_stage(browser, generic_dir):
    # 操作ボタンは画面の下に重なる：出ていても消えていても、舞台の大きさと位置は同じ
    seen = {}
    for mode in ["always", "never"]:
        with ui_session(browser, proposal_url(generic_dir), controls=mode) as page:
            seen[mode] = stage_rect(page)
            if mode == "always":
                bar = rect_of(page, ".sp-controls")
                assert bar["bottom"] == pytest.approx(900, abs=0.5) and bar["x"] == 0 and bar["w"] == pytest.approx(1440, abs=0.5)
                assert bar["h"] < 130                              # 縦の幅が舞台を押しのけるほど大きくない
                scroll = page.evaluate("({sh: document.documentElement.scrollHeight, ih: innerHeight, sw: document.documentElement.scrollWidth, iw: innerWidth})")
                assert scroll["sh"] <= scroll["ih"] and scroll["sw"] <= scroll["iw"]
    assert seen["always"] == seen["never"]
    assert seen["always"]["h"] == pytest.approx(810, abs=0.5) and seen["always"]["w"] == pytest.approx(1440, abs=0.5)


def test_position_display_in_controls(browser, generic_dir):
    with ui_session(browser, proposal_url(generic_dir, "#p05.2")) as page:
        assert page.locator(".sp-controls .sp-pos").inner_text() == "6 / 9　段階 2/3"
        press(page, "End")
        assert page.locator(".sp-controls .sp-pos").inner_text() == "9 / 9"      # 段階のないスライドは段階を出さない


# ---- Space・Enter の二重の扱い（統括の判断） ----

def test_space_after_click_advances_once(browser, generic_dir):
    # 「N ノート」を押したあとの Space：ちょうど1段階進み、ノートは開閉し直さない
    with ui_session(browser, proposal_url(generic_dir)) as page:
        button(page, "N ノート").click()
        assert notes_open(page)
        assert page.evaluate("document.activeElement === document.body")        # 押したボタンに焦点を残さない
        assert press(page, "Space") == ("p02", 0)
        assert notes_open(page)
        assert press(page, "Space") == ("p02", 1)
        assert notes_open(page)
        # ほかのボタンも同じ
        button(page, "↓ 次").click()
        assert where(page) == ("p02", 2)
        assert press(page, "Space") == ("p03", 0)


def test_enter_on_focused_button_activates_only_button(browser, generic_dir):
    # Tab などで焦点が乗ったボタンの Space・Enter は、そのボタンを押す動作だけ（スライドは動かない）
    with ui_session(browser, proposal_url(generic_dir, "#p02")) as page:
        button(page, "N ノート").focus()
        page.keyboard.press("Space")
        assert notes_open(page) and where(page) == ("p02", 0)
        page.keyboard.press("Enter")
        assert not notes_open(page) and where(page) == ("p02", 0)
        page.keyboard.press("Enter")
        assert notes_open(page) and where(page) == ("p02", 0)
        # ボタンに焦点があっても、矢印キーは今までどおりスライドを動かす
        assert press(page, "ArrowDown") == ("p02", 1)
        assert notes_open(page)


def test_prevented_keys_are_skipped(browser, generic_dir):
    # すでにほかの処理が止めたキー（defaultPrevented）は、プレイヤーが扱わない
    block = "window.addEventListener('keydown', e => { if (window.__block) e.preventDefault(); }, true);"
    with ui_session(browser, proposal_url(generic_dir, "#p02"), init=block) as page:
        page.evaluate("window.__block = true")
        for key in ["ArrowDown", "Space", "End", "n", "?", "f", "h"]:
            page.keyboard.press(key)
        assert where(page) == ("p02", 0)
        assert not notes_open(page) and page.query_selector(".sp-help") is None
        assert page.url.endswith("proposal.html#p02")
        page.evaluate("window.__block = false")
        assert press(page, "ArrowDown") == ("p02", 1)              # 空振りでない確認
        page.keyboard.press("n")
        assert notes_open(page)


# ---- 移動のキー：キーボードで押した操作ボタンから焦点を外す ----

MOVE_KEYS_FROM_P03 = [
    ("ArrowDown", ("p03b", 0)), ("ArrowUp", ("p02", 2)), ("PageDown", ("p03b", 0)), ("PageUp", ("p02", 2)),
    ("Space", ("p03b", 0)), ("Home", ("p01", 0)), ("End", ("p08", 0)),
    ("Shift+ArrowDown", ("p03b", 0)), ("Shift+ArrowUp", ("p02", 2)), ("ArrowLeft", ("p03", 0)), ("ArrowRight", ("p03b", 0)),
]


@pytest.mark.parametrize("key, expected", MOVE_KEYS_FROM_P03, ids=[k for k, _ in MOVE_KEYS_FROM_P03])
def test_move_key_after_keyboard_press_releases_the_controls(browser, generic_dir, key, expected):
    # 操作ボタンをキーボードで押したあと、焦点が帯に残ったまま移動のキーを押したら、焦点を外してから通常の移動にする
    # （帯が隠れなくなる・Space がそのボタンを押し直す、のを防ぐ）
    with ui_session(browser, proposal_url(generic_dir, "#p03")) as page:
        button(page, "N ノート").focus()
        page.keyboard.press("Enter")
        assert notes_open(page) and active_in(page, ".sp-controls")      # 押した。焦点は帯に残る
        assert press(page, key) == expected
        assert page.evaluate("document.activeElement === document.body")  # 焦点を外した
        assert notes_open(page)                                           # ボタンは押し直されていない


def test_space_after_keyboard_press_moves_instead_of_pressing_again(browser, generic_dir):
    with ui_session(browser, proposal_url(generic_dir, "#p02")) as page:
        button(page, "N ノート").focus()
        page.keyboard.press("Space")                                      # 最初の Space は、そのボタンを押す
        assert notes_open(page) and where(page) == ("p02", 0) and active_in(page, ".sp-controls")
        assert press(page, "Space") == ("p02", 1)                         # 2回目からは移動（ノートは開いたまま）
        assert notes_open(page) and page.evaluate("document.activeElement === document.body")
        assert press(page, "Space") == ("p02", 2)


def test_space_on_another_button_after_focus_moved_still_presses_it(browser, generic_dir):
    # Tab で別のボタンへ移れば、そのボタンの最初の Space はそのボタンを押す（移動に取られない）
    with ui_session(browser, proposal_url(generic_dir, "#p02")) as page:
        button(page, "N ノート").focus()
        page.keyboard.press("Enter")
        assert notes_open(page)
        page.keyboard.press("Shift+Tab")                                  # 「T 一覧つき」を越えて「O 一覧」へ
        page.keyboard.press("Shift+Tab")
        assert page.evaluate("document.activeElement.textContent") == "O 一覧"
        page.keyboard.press("Space")
        assert page.evaluate("__sp.overlay()") == "overview" and where(page) == ("p02", 0)


def test_controls_hide_after_a_move_key_releases_focus(browser, generic_dir):
    # 焦点が帯に残らないので、自動で消す設定の帯は、動かして 3 秒後に隠れる
    with ui_session(browser, proposal_url(generic_dir, "#p02"), seed=False) as page:
        freeze_clock(page)
        controls = page.locator(".sp-controls")
        page.keyboard.press("Tab")                                 # Tab で帯が出て、最初のボタン（↑ 前）に焦点が乗る
        expect(controls).to_be_visible()
        assert page.evaluate("document.activeElement.textContent") == "↑ 前"
        page.keyboard.press("Enter")                               # キーボードで押す：p01 へ。焦点は帯に残る
        assert where(page) == ("p01", 0) and active_in(page, ".sp-controls")
        page.clock.run_for(10000)
        assert controls.is_visible()                               # 焦点が帯にある間は隠れない
        assert press(page, "ArrowDown") == ("p02", 0)              # 移動のキー：焦点を外して動く
        assert not active_in(page, ".sp-controls")
        page.clock.run_for(2900)
        assert controls.is_visible()                               # 外れたところから 3 秒数える
        page.clock.run_for(200)
        expect(controls).to_be_hidden()


# ---- 知らせ（toast）は操作ボタンの帯の上に出す ----

@pytest.mark.parametrize("viewport", [(1000, 700), (820, 1180)], ids=["1000x700", "820x1180"])
def test_toast_sits_above_the_controls(browser, generic_dir, viewport):
    # ノートを開いて帯が狭くなり、帯が何段にもなっても、知らせは帯に重ならない
    with ui_session(browser, proposal_url(generic_dir), controls="always", notes=True, viewport=viewport) as page:
        assert press(page, "ArrowUp") == ("p01", 0)
        toast, bar = rect_of(page, ".sp-toast"), rect_of(page, ".sp-controls")
        assert toast is not None and bar["h"] > 0
        assert toast["bottom"] <= bar["y"], (toast, bar)                  # 知らせの下端が帯の上端より上


def test_toast_stays_low_when_the_controls_are_not_shown(browser, generic_dir):
    # 帯が出ていない（出さない設定）ときは、今までの高さ（画面の下から 72px）
    with ui_session(browser, proposal_url(generic_dir), controls="never", viewport=(820, 1180)) as page:
        assert press(page, "ArrowUp") == ("p01", 0)
        assert rect_of(page, ".sp-toast")["bottom"] == pytest.approx(1180 - 72, abs=0.5)


def test_toast_moves_above_the_controls_when_they_appear(browser, generic_dir):
    with ui_session(browser, proposal_url(generic_dir), controls="auto", viewport=(820, 1180)) as page:
        freeze_clock(page)                                                # 知らせも帯も、時計を進めない限り消えない
        assert press(page, "ArrowUp") == ("p01", 0)
        assert rect_of(page, ".sp-toast")["bottom"] == pytest.approx(1180 - 72, abs=0.5)      # 帯はまだ出ていない
        page.mouse.move(400, 300)                                         # 帯が出る
        toast, bar = rect_of(page, ".sp-toast"), rect_of(page, ".sp-controls")
        assert toast["bottom"] <= bar["y"], (toast, bar)


# ---- ノート ----

def test_notes_toggle_and_fit(browser, generic_dir):
    with ui_session(browser, proposal_url(generic_dir)) as page:
        before = stage_rect(page)
        assert before["x"] == 0 and before["w"] == pytest.approx(1440, abs=0.5)
        page.keyboard.press("n")
        notes = page.locator(".sp-notes")
        expect(notes).to_be_visible()
        assert "冒頭のあいさつ" in notes.inner_text()               # p01 のノート
        panel, stage = rect_of(page, ".sp-notes"), stage_rect(page)
        assert panel["w"] == pytest.approx(min(520, max(320, 1440 * 0.28)), abs=0.5)   # 403.2
        assert panel["x"] + panel["w"] == pytest.approx(1440, abs=0.5) and panel["y"] == 0 and panel["h"] == pytest.approx(900, abs=0.5)
        assert stage["right"] <= panel["x"] + 0.01                  # 舞台の右端がノートの左端を越えない
        assert stage["w"] / stage["h"] == pytest.approx(16 / 9, abs=0.01)
        assert stage["w"] < before["w"] and stage["x"] >= 0
        # 閉じる：舞台が元の大きさに戻る
        page.keyboard.press("n")
        assert not notes_open(page)
        assert stage_rect(page) == before


@pytest.mark.parametrize("viewport", [(1440, 900), (1000, 700), (1920, 1080), (820, 1180), (1180, 820), (640, 300)])
def test_notes_stage_beside_notes(browser, generic_dir, viewport):
    w, h = viewport
    with ui_session(browser, proposal_url(generic_dir), notes=True, viewport=viewport) as page:
        assert notes_open(page)                                    # 保存した状態で開く
        panel, stage = rect_of(page, ".sp-notes"), stage_rect(page)
        assert panel["w"] == pytest.approx(min(520, max(320, w * 0.28)), abs=0.5)
        assert stage["right"] <= panel["x"] + 0.01
        assert stage["w"] / stage["h"] == pytest.approx(16 / 9, abs=0.01)
        assert 0 <= stage["x"] and 0 <= stage["y"] and stage["bottom"] <= h + 0.01
        avail = panel["x"]
        k = min(avail / 1920, h / 1080)
        assert stage["w"] == pytest.approx(1920 * k, abs=0.5)      # 残りの領域に最大
        scroll = page.evaluate("({sw: document.documentElement.scrollWidth, sh: document.documentElement.scrollHeight, iw: innerWidth, ih: innerHeight})")
        assert scroll["sw"] <= scroll["iw"] and scroll["sh"] <= scroll["ih"]


def test_notes_stage_follows_resize(browser, generic_dir):
    with ui_session(browser, proposal_url(generic_dir), notes=True) as page:
        for w, h in [(1000, 700), (1920, 1080), (820, 1180), (1440, 900)]:
            page.set_viewport_size({"width": w, "height": h})
            panel_w = min(520, max(320, w * 0.28))
            expected = 1920 * min((w - panel_w) / 1920, h / 1080)
            page.wait_for_function(
                "(want) => Math.abs(document.getElementById('stage').getBoundingClientRect().width - want) < 0.5", arg=expected)
            panel, stage = rect_of(page, ".sp-notes"), stage_rect(page)
            assert stage["right"] <= panel["x"] + 0.01, (w, h)
            assert stage["w"] / stage["h"] == pytest.approx(16 / 9, abs=0.01), (w, h)


def test_notes_on_course_deck(browser, course_dir):
    with ui_session(browser, slides_url(course_dir, 1, render=False)) as page:
        page.keyboard.press("n")
        expect(page.locator(".sp-notes")).to_be_visible()
        panel, stage = rect_of(page, ".sp-notes"), stage_rect(page)
        assert stage["right"] <= panel["x"] + 0.01
        first_id = page.evaluate("deckInfo()[0].id")
        assert first_id in page.inner_text(".sp-notes")             # 「ID　題名」の ID
        press(page, "ArrowDown")
        page.keyboard.press("n")
        assert not notes_open(page)


def test_notes_empty(browser, generic_dir):
    with ui_session(browser, proposal_url(generic_dir, "#p06")) as page:
        page.keyboard.press("n")
        notes = page.locator(".sp-notes")
        expect(notes).to_be_visible()
        assert "ノートはありません" in notes.inner_text()
        assert "p06" in notes.inner_text() and "費用と補足の資料" in notes.inner_text()


def test_notes_head_shows_id_title_and_minutes(browser, generic_dir):
    with ui_session(browser, proposal_url(generic_dir, "#p02")) as page:
        page.keyboard.press("n")
        assert page.locator(".sp-notes-title").inner_text() == "p02　いまの請求業務の課題"
        assert page.locator(".sp-notes-time").inner_text() == "目安 2 分"
        assert "月末の残業" in page.locator(".sp-notes").inner_text()
    # 目安のないスライド（minimal）：「目安」を出さない
    with ui_session(browser, (generic_dir / "minimal.html").as_uri()) as page:
        page.keyboard.press("n")
        text = page.inner_text(".sp-notes")
        assert "m1　最小の見本" in text and "目安" not in text and "ノートはありません" in text


def test_notes_follow_slide_and_step(browser, generic_dir):
    with ui_session(browser, proposal_url(generic_dir), notes=True) as page:
        assert "冒頭のあいさつ" in page.inner_text(".sp-notes")
        press(page, "ArrowDown")                                   # p02
        text = page.inner_text(".sp-notes")
        assert "p02" in text and "目安 2 分" in text and "冒頭のあいさつ" not in text
        press(page, "ArrowDown")                                   # p02 の段階1：同じノートのまま
        assert page.locator(".sp-notes-title").inner_text().startswith("p02")
        press(page, "End")                                         # p08：ノートなし
        assert "ノートはありません" in page.inner_text(".sp-notes")
        press(page, "Home")
        assert "冒頭のあいさつ" in page.inner_text(".sp-notes")


def test_notes_text_not_html(browser, generic_dir):
    # p03 のノートの「<b>太字にならない</b>」は、文字のまま出る（HTML として解釈しない）
    with ui_session(browser, proposal_url(generic_dir, "#p03")) as page:
        page.keyboard.press("n")
        assert "<b>太字にならない</b>" in page.inner_text(".sp-notes")
        assert page.evaluate("document.querySelectorAll('.sp-notes b').length") == 0


def test_notes_keep_line_breaks_and_escape_title(browser, generic_dir, tmp_path):
    # 改行は残る。題名・ノートの HTML は解釈しない
    def edit(html):
        html = html.replace("notes: '冒頭のあいさつ。", "notes: '1行目\\n2行目\\n\\n<img src=x onerror=alert(1)>冒頭のあいさつ。")
        return html.replace("title: '請求業務の効率化のご提案', subtitle", "title: '<i>題名</i>', subtitle", 1)
    url = write_variant(tmp_path, generic_dir, "html-in-notes.html", edit)
    with ui_session(browser, url) as page:
        page.keyboard.press("n")
        assert page.evaluate("document.querySelectorAll('.sp-notes img, .sp-notes i').length") == 0
        text = page.inner_text(".sp-notes-body")
        assert text.startswith("1行目\n2行目") and "<img src=x onerror=alert(1)>" in text
        assert "<i>題名</i>" in page.inner_text(".sp-notes-title")


def test_notes_state_saved(browser, generic_dir):
    with ui_session(browser, proposal_url(generic_dir), seed=False) as page:
        assert not notes_open(page)                                # 既定は閉じている
        page.keyboard.press("n")
        assert stored_settings(page) == {"controls": "auto", "notes": True}
        page.reload()
        assert notes_open(page)                                    # 次に開いたときも同じ
        page.goto(proposal_url(generic_dir, "#p05"))               # 同じページの別の場所でも
        page.reload()
        assert notes_open(page)
        page.keyboard.press("n")
        assert stored_settings(page) == {"controls": "auto", "notes": False}
        page.reload()
        assert not notes_open(page)


def test_notes_and_controls_settings_are_independent(browser, generic_dir):
    with ui_session(browser, proposal_url(generic_dir), seed=False) as page:
        page.keyboard.press("n")
        page.keyboard.press("?")
        page.locator(".sp-help button", has_text="いつも出す").click()
        assert stored_settings(page) == {"controls": "always", "notes": True}
        page.keyboard.press("Escape")                              # 重なりの Esc。ノートはそのまま
        assert notes_open(page)
        assert stored_settings(page) == {"controls": "always", "notes": True}


def test_controls_sit_beside_notes(browser, generic_dir):
    # ノートを開いていても、操作ボタンの帯はノートに重ならない（舞台の側の下に出る）
    with ui_session(browser, proposal_url(generic_dir), notes=True) as page:
        bar, panel = rect_of(page, ".sp-controls"), rect_of(page, ".sp-notes")
        assert bar["right"] <= panel["x"] + 0.5 and bar["bottom"] == pytest.approx(900, abs=0.5)
        page.keyboard.press("n")
        bar = rect_of(page, ".sp-controls")
        assert bar["right"] == pytest.approx(1440, abs=0.5)        # 閉じれば全幅に戻る


# ---- 操作の一覧（?）と Esc ----

def test_help_and_esc(browser, generic_dir):
    with ui_session(browser, proposal_url(generic_dir)) as page:
        assert page.query_selector(".sp-help") is None
        page.keyboard.press("?")
        help_el = page.locator(".sp-help")
        expect(help_el).to_be_visible()
        text = help_el.inner_text()
        for word in ["PageDown", "Space", "Shift", "Home", "End", "Esc", "ノート", "全画面", "目次", "いつも出す", "自動で消す", "出さない"]:
            assert word in text, word
        page.keyboard.press("Escape")
        assert page.query_selector(".sp-help") is None


def test_help_toggles_with_question_mark(browser, generic_dir):
    with ui_session(browser, proposal_url(generic_dir)) as page:
        page.keyboard.press("?")
        assert page.query_selector(".sp-help") is not None
        page.keyboard.press("?")
        assert page.query_selector(".sp-help") is None
        button(page, "?").click()
        assert page.query_selector(".sp-help") is not None
        page.locator(".sp-help button", has_text="閉じる").click()
        assert page.query_selector(".sp-help") is None
        # 背景を押しても閉じる。中身の余白を押しても閉じない
        page.keyboard.press("?")
        page.locator(".sp-help-panel").click(position={"x": 5, "y": 5})
        assert page.query_selector(".sp-help") is not None
        page.mouse.click(5, 5)
        assert page.query_selector(".sp-help") is None


def test_help_fits_small_screen(browser, generic_dir):
    with ui_session(browser, proposal_url(generic_dir), viewport=(820, 600)) as page:
        page.keyboard.press("?")
        panel = rect_of(page, ".sp-help-panel")
        assert panel["x"] >= 0 and panel["right"] <= 820 and panel["y"] >= 0 and panel["bottom"] <= 600
        scroll = page.evaluate("({sw: document.documentElement.scrollWidth, sh: document.documentElement.scrollHeight})")
        assert scroll["sw"] <= 820 and scroll["sh"] <= 600


def test_help_is_modal(browser, generic_dir):
    # 操作の一覧が開いている間、? Esc N F 以外のキーではスライドが動かない
    with ui_session(browser, proposal_url(generic_dir, "#p02"), init=FULLSCREEN_STUB) as page:
        page.keyboard.press("?")
        for key in ["ArrowDown", "ArrowUp", "Space", "PageDown", "PageUp", "End", "Home", "Shift+ArrowDown", "Shift+ArrowUp",
                    "ArrowLeft", "ArrowRight", "h", "o", "l", "a", "Enter"]:
            page.keyboard.press(key)
            assert where(page) == ("p02", 0), key
            assert page.query_selector(".sp-help") is not None, key
        assert page.url.endswith("proposal.html#p02")
        assert page.evaluate("__sp.places().items.length") == 1    # 場所も増えていない
        # N と F は効く
        page.keyboard.press("n")
        assert notes_open(page) and page.query_selector(".sp-help") is not None
        page.keyboard.press("f")
        assert page.evaluate("__fs") == [["request", True]]
        # ? で閉じると、また動く
        page.keyboard.press("?")
        assert page.query_selector(".sp-help") is None
        assert press(page, "ArrowDown") == ("p02", 1)


def test_help_modal_keys_do_not_prevent_page_default(browser, generic_dir):
    # 一覧が開いているとき、スライドの移動は何もしないので、ブラウザの動き（一覧の中のスクロールなど）を止めない
    with ui_session(browser, proposal_url(generic_dir, "#p02")) as page:
        page.keyboard.press("?")
        page.evaluate(RECORD_PREVENTED)
        for key in ["ArrowDown", "Space", "PageDown"]:
            page.keyboard.press(key)
        assert not any(prevented for _, prevented in page.evaluate("__prevented"))


def test_notes_are_not_modal(browser, generic_dir):
    with ui_session(browser, proposal_url(generic_dir), notes=True) as page:
        assert press(page, "ArrowDown") == ("p02", 0)
        assert press(page, "ArrowDown") == ("p02", 1)
        assert press(page, "Shift+ArrowDown") == ("p03", 0)
        assert press(page, "ArrowLeft") == ("p02", 1)
        assert press(page, "End") == ("p08", 0)
        assert notes_open(page)


def test_overlay_names(browser, generic_dir):
    with ui_session(browser, proposal_url(generic_dir)) as page:
        assert page.evaluate("__sp.overlay()") == "none"
        page.keyboard.press("n")
        assert page.evaluate("__sp.overlay()") == "none"           # ノートは数えない
        page.keyboard.press("?")
        assert page.evaluate("__sp.overlay()") == "help"
        page.keyboard.press("n")                                   # 一覧が開いたままノートを閉じても
        assert page.evaluate("__sp.overlay()") == "help"
        page.keyboard.press("Escape")
        assert page.evaluate("__sp.overlay()") == "none"


def test_esc_closes_topmost_only(browser, generic_dir):
    with ui_session(browser, proposal_url(generic_dir), notes=True) as page:
        page.keyboard.press("?")
        page.keyboard.press("Escape")                              # 一覧だけが閉じる
        assert page.query_selector(".sp-help") is None and notes_open(page)
        page.keyboard.press("Escape")                              # 次は、ほかに何もなければノートを閉じる
        assert not notes_open(page)
        assert stored_settings(page)["notes"] is False             # 閉じた状態を保存する
        page.keyboard.press("Escape")                              # 何も開いていない：何も起きない
        assert where(page) == ("p01", 0) and toast_text(page) is None


def test_esc_with_help_opened_after_notes_order(browser, generic_dir):
    # 一覧を先に開いて、あとからノートを開いても、Esc は重なり（一覧）を先に閉じる
    with ui_session(browser, proposal_url(generic_dir)) as page:
        page.keyboard.press("?")
        page.keyboard.press("n")
        assert notes_open(page)
        page.keyboard.press("Escape")
        assert page.query_selector(".sp-help") is None and notes_open(page)


def test_esc_with_nothing_open_does_nothing(browser, generic_dir):
    with ui_session(browser, proposal_url(generic_dir, "#p03")) as page:
        page.evaluate(RECORD_PREVENTED)
        before = page.evaluate("[location.href, __sp.places(), document.body.children.length]")
        page.keyboard.press("Escape")
        assert page.evaluate("[location.href, __sp.places(), document.body.children.length]") == before
        assert toast_text(page) is None and page.query_selector(".sp-help") is None
        assert page.evaluate("__prevented") == [["Escape", False]]  # ブラウザの動き（全画面を抜けるなど）を止めない


def test_focus_returns_to_page_after_help(browser, generic_dir):
    with ui_session(browser, proposal_url(generic_dir, "#p02")) as page:
        page.keyboard.press("?")
        page.keyboard.press("Escape")
        assert press(page, "ArrowDown") == ("p02", 1)


def test_help_tab_stays_inside(browser, generic_dir):
    with ui_session(browser, proposal_url(generic_dir)) as page:
        page.keyboard.press("?")
        for _ in range(12):
            page.keyboard.press("Tab")
            assert page.evaluate("!!document.activeElement.closest('.sp-help')")
        for _ in range(12):
            page.keyboard.press("Shift+Tab")
            assert page.evaluate("!!document.activeElement.closest('.sp-help')")


# ---- H（目次へ） ----

def test_h_goes_home(browser, generic_dir):
    with ui_session(browser, proposal_url(generic_dir, "#p03")) as page:
        page.keyboard.press("h")
        page.wait_for_url(HOME_URL)
        assert page.evaluate("__sp.state().kind") == "catalog"
    with ui_session(browser, proposal_url(generic_dir, "#p05.2")) as page:
        page.keyboard.press("H")                                   # 大文字（CapsLock）でも
        page.wait_for_url(HOME_URL)


def test_h_goes_home_on_course_deck(browser, course_dir):
    # 講座の形の見本の章：home は ../index.html、デッキの ID（ch-01）を hash に付ける
    with ui_session(browser, slides_url(course_dir, 1, render=False)) as page:
        page.keyboard.press("h")
        page.wait_for_url(re.compile(r"/index\.html#ch-01$"))
        assert page.evaluate("__sp.state().kind") == "catalog"


def test_h_clears_restore_target(browser, generic_dir):
    # H で移る前に、残っている復元先を消す
    with ui_session(browser, proposal_url(generic_dir, "#p03")) as page:
        press(page, "ArrowDown")
        page.evaluate(f"""(() => {{
          const d = JSON.parse(sessionStorage.getItem({json.dumps(PLACES_KEY)}));
          d.restore = {{vid: d.items[0].vid, t: Date.now()}};
          sessionStorage.setItem({json.dumps(PLACES_KEY)}, JSON.stringify(d));
        }})()""")
        page.keyboard.press("h")
        page.wait_for_url(HOME_URL)
        assert json.loads(page.evaluate(f"sessionStorage.getItem({json.dumps(PLACES_KEY)})"))["restore"] is None


def test_h_ignores_unsafe_home(browser, generic_dir, tmp_path):
    url = write_variant(tmp_path, generic_dir, "bad-home.html",
                        lambda html: html.replace("home: 'index.html'", "home: 'javascript:alert(1)'"))
    with ui_session(browser, url) as page:
        labels = page.evaluate("Array.from(document.querySelectorAll('.sp-controls button'), b => b.textContent)")
        assert "H 目次" not in labels
        page.keyboard.press("h")
        page.wait_for_timeout(300)
        assert page.url.endswith("bad-home.html#p01")


# ---- F（全画面） ----

def test_f_requests_and_exits_fullscreen(browser, generic_dir):
    with ui_session(browser, proposal_url(generic_dir), init=FULLSCREEN_STUB) as page:
        page.keyboard.press("f")
        assert page.evaluate("__fs") == [["request", True]]        # document.documentElement に対して
        page.evaluate("window.__fsEl = document.documentElement")
        page.keyboard.press("F")                                   # もう全画面なら抜ける
        assert page.evaluate("__fs") == [["request", True], ["exit", True]]
        assert toast_text(page) is None


def test_f_unavailable_is_announced(browser, generic_dir):
    unavailable = "Element.prototype.requestFullscreen = undefined; Element.prototype.webkitRequestFullscreen = undefined;"
    with ui_session(browser, proposal_url(generic_dir), init=unavailable) as page:
        page.keyboard.press("f")
        assert toast_text(page)
        assert where(page) == ("p01", 0)


def test_f_rejected_is_announced(browser, generic_dir):
    rejected = "Element.prototype.requestFullscreen = () => Promise.reject(new TypeError('許可されていない'));"
    with ui_session(browser, proposal_url(generic_dir), init=rejected) as page:
        page.keyboard.press("f")
        page.wait_for_selector(".sp-toast")
        assert toast_text(page)
    throws = "Element.prototype.requestFullscreen = () => { throw new TypeError('使えない'); };"
    with ui_session(browser, proposal_url(generic_dir), init=throws) as page:
        page.keyboard.press("f")
        assert toast_text(page)


# ---- 保存領域が使えない・壊れているとき ----

LOCAL_STORAGE_THROWS = """
Object.defineProperty(window, 'localStorage', { configurable: true, get() { throw new DOMException('拒否', 'SecurityError'); } });
"""
SET_ITEM_THROWS = """
(() => {
  const orig = Storage.prototype.setItem;
  Storage.prototype.setItem = function (k, v) {
    if (k === 'sp-settings-v1') throw new DOMException('いっぱい', 'QuotaExceededError');
    return orig.call(this, k, v);
  };
})();
"""


@pytest.mark.parametrize("stub", [LOCAL_STORAGE_THROWS, SET_ITEM_THROWS], ids=["localStorage-itself", "setItem-only"])
def test_storage_throws(browser, generic_dir, stub):
    with ui_session(browser, proposal_url(generic_dir), seed=False, init=stub) as page:
        # N が動く（保存できなくても、このページの中では開閉する）
        page.keyboard.press("n")
        assert notes_open(page)
        assert page.evaluate("__sp.overlay()") == "none"
        page.keyboard.press("n")
        assert not notes_open(page)
        # 操作ボタン：「いつも出す」を選べて、このページの中では効く。ボタンも動く
        page.keyboard.press("?")
        page.locator(".sp-help button", has_text="いつも出す").click()
        page.keyboard.press("Escape")
        expect(page.locator(".sp-controls")).to_be_visible()
        button(page, "↓ 次").click()
        assert where(page) == ("p02", 0)
        button(page, "N ノート").click()
        assert notes_open(page)
        assert press(page, "Space") == ("p02", 1)                  # 移動も続く


@pytest.mark.parametrize("stub", [LOCAL_STORAGE_THROWS, SET_ITEM_THROWS], ids=["localStorage-itself", "setItem-only"])
def test_storage_throws_in_minimal_deck(browser, generic_dir, stub):
    with ui_session(browser, (generic_dir / "minimal.html").as_uri(), seed=False, init=stub) as page:
        page.mouse.move(500, 300)
        expect(page.locator(".sp-controls")).to_be_visible()
        button(page, "N ノート").click()
        assert notes_open(page)


DEFAULTS = ("auto", False)


SETTINGS_CASES = [
    # 全体が読めない：どちらも既定（自動で消す・ノートは閉じる）
    ("{broken", DEFAULTS), ("", DEFAULTS), ("null", DEFAULTS), ("[]", DEFAULTS), ("42", DEFAULTS), ('"auto"', DEFAULTS), ("{}", DEFAULTS),
    ('{"controls":null,"notes":null}', DEFAULTS),
    # 項目ごとに確かめる：壊れた項目だけ既定に戻し、正しい項目は生かす
    ('{"controls":"bogus","notes":true}', ("auto", True)),
    ('{"controls":"always","notes":"yes"}', ("always", False)),
    ('{"controls":"always"}', ("always", False)),
    ('{"notes":true}', ("auto", True)),
    ('{"controls":"never","notes":1}', ("never", False)),
    ('{"controls":["always"],"notes":true}', ("auto", True)),
    ('{"controls":"ALWAYS","notes":true}', ("auto", True)),
]


@pytest.mark.parametrize("bad, expected", SETTINGS_CASES, ids=[bad or "empty" for bad, _ in SETTINGS_CASES])
def test_corrupt_settings_fall_back_per_field(browser, generic_dir, bad, expected):
    # 壊れた・形の違う項目は捨てて既定にする（ほかの正しい項目は生かす）。次に保存するときに直る
    controls, notes = expected
    with page_session(browser, "about:blank") as page:
        page.add_init_script(f"try {{ localStorage.setItem({json.dumps(KEY)}, {json.dumps(bad)}); }} catch (e) {{}}")
        page.goto(proposal_url(generic_dir))
        assert notes_open(page) == notes
        assert page.locator(".sp-controls").is_visible() == (controls == "always")       # always だけ、動かさなくても出ている
        page.keyboard.press("n")
        assert notes_open(page) == (not notes)
        assert stored_settings(page) == {"controls": controls, "notes": not notes}


def test_valid_settings_with_extra_keys(browser, generic_dir):
    # 知らない項目があっても、controls と notes が正しければ使う
    with page_session(browser, "about:blank") as page:
        page.add_init_script(
            f"try {{ localStorage.setItem({json.dumps(KEY)}, JSON.stringify({{controls: 'always', notes: true, future: 1}})); }} catch (e) {{}}")
        page.goto(proposal_url(generic_dir))
        assert notes_open(page)
        expect(page.locator(".sp-controls")).to_be_visible()


# ---- 作りの決まり（約束 §2.5） ----

def test_class_names_and_elements(browser, generic_dir):
    # プレイヤーの要素のクラスは sp- で始まり、header・main・footer を使わない。文字は textContent（要素の子は決めた形だけ）
    with ui_session(browser, proposal_url(generic_dir), notes=True) as page:
        page.keyboard.press("?")
        got = page.evaluate("""(() => {
          const roots = Array.from(document.querySelectorAll('.sp-controls, .sp-notes, .sp-help'));
          const all = roots.flatMap(r => [r, ...r.querySelectorAll('*')]);
          return {
            roots: roots.map(r => r.className),
            badClasses: all.flatMap(e => Array.from(e.classList)).filter(c => !c.startsWith('sp-')),
            tags: Array.from(new Set(all.map(e => e.tagName.toLowerCase()))),
            outside: Array.from(document.body.children).filter(e => !e.matches('#stage, script, [class*="sp-"]')).map(e => e.tagName),
          };
        })()""")
        assert [r.split()[0] for r in got["roots"]] == ["sp-controls", "sp-notes", "sp-help"]
        assert got["badClasses"] == [] and got["outside"] == []
        assert not {"header", "main", "footer"} & set(got["tags"])


def test_render_mode_has_no_ui(browser, generic_dir):
    # ?render：画面の部品も保存の読み書きもしない
    with page_session(browser, "about:blank") as page:
        page.add_init_script("window.__ls = []; const g = Storage.prototype.getItem, s = Storage.prototype.setItem;"
                             "Storage.prototype.getItem = function (k) { window.__ls.push(['get', k]); return g.call(this, k); };"
                             "Storage.prototype.setItem = function (k, v) { window.__ls.push(['set', k]); return s.call(this, k, v); };")
        page.goto(proposal_url(generic_dir, "?render"))
        for key in ["n", "?", "f", "h", "Escape", "ArrowDown"]:
            page.keyboard.press(key)
        assert page.evaluate("document.querySelectorAll('.sp-controls, .sp-notes, .sp-help, .sp-pos').length") == 0
        assert page.evaluate("__ls") == []
        assert page.url.endswith("proposal.html?render")


def test_mouse_wheel_in_notes_does_not_change_slide(browser, generic_dir):
    with ui_session(browser, proposal_url(generic_dir, "#p02"), notes=True) as page:
        page.mouse.move(1300, 400)
        page.mouse.wheel(0, 300)
        assert where(page) == ("p02", 0)
