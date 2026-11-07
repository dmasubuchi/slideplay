"""書き込み（D）の土台の試験。

ざっと描いた線から、□ ○ 線 手書きを決める。種類ごとの色・太さ、帯、ロック、ひとつ戻す、蛍光ペン。
見るのは外から見える結果だけ：画面の要素（.sp-write-tools・.sp-write-pop・.sp-ink）と、試験用の窓口 window.__sp.writing()、設定 sp-settings-v1。
画面の座標で点の列を作ってマウスでなぞる。揺れは乱数の種を固定する（試験のたびに同じ）。
"""
import json
import math
import random

import pytest

from test_motion import where
from test_pen import motion_url, still  # noqa: F401（fixture）

SETTINGS_KEY = "sp-settings-v1"
TOOLS = ".sp-write-tools"


def writing(page):
    return page.evaluate("__sp.writing()")


def stroke(page, points, shift=False):
    """マウスで points（画面の座標）をなぞる。"""
    if shift:
        page.keyboard.down("Shift")
    page.mouse.move(*points[0])
    page.mouse.down()
    for p in points[1:]:
        page.mouse.move(*p)
    page.mouse.up()
    if shift:
        page.keyboard.up("Shift")


def last(page):
    return writing(page)["objects"][-1]


def btn(page, selector):
    return page.locator(f"{TOOLS} {selector}")


def saved_ink(page):
    raw = page.evaluate(f"localStorage.getItem('{SETTINGS_KEY}')")
    return (json.loads(raw) if raw else {}).get("ink")


# ---- ざっと描く点の列（画面の座標。揺れは種を固定） ----

def rng(seed=3):
    r = random.Random(seed)
    return lambda amp=4: r.uniform(-amp, amp)


def rough_rect(x, y, w, h, n=30, seed=3):
    j = rng(seed)
    corners = [(x, y), (x + w, y), (x + w, y + h), (x, y + h), (x, y + 4)]
    pts = []
    for (ax, ay), (bx, by) in zip(corners, corners[1:]):
        for i in range(n):
            t = i / n
            pts.append((ax + (bx - ax) * t + j(), ay + (by - ay) * t + j()))
    return pts


def rough_ellipse(cx, cy, rx, ry, n=80, seed=3):
    j = rng(seed)
    return [(cx + rx * math.cos(2 * math.pi * i / n - 1.2) + j(), cy + ry * math.sin(2 * math.pi * i / n - 1.2) + j()) for i in range(n + 3)]


def rough_triangle(x, y, w, h, n=30, seed=3):
    j = rng(seed)
    c = [(x + w / 2, y), (x + w, y + h), (x, y + h), (x + w / 2 + 3, y + 3)]
    pts = []
    for (ax, ay), (bx, by) in zip(c, c[1:]):
        for i in range(n):
            t = i / n
            pts.append((ax + (bx - ax) * t + j(), ay + (by - ay) * t + j()))
    return pts


def rough_line(x0, y0, x1, y1, jitter=1.5, n=40, seed=3):
    j = rng(seed)
    return [(x0 + (x1 - x0) * i / n + j(jitter), y0 + (y1 - y0) * i / n + j(jitter)) for i in range(n + 1)]


def wavy(x, y):
    return [(x + i * 2, y + 12 * math.sin(i / 3) + 8 * math.cos(i / 1.7)) for i in range(60)]


def scale_of(page):
    """舞台の座標 1 が画面の何 px か。"""
    return page.evaluate("document.querySelector('.sp-ink').getBoundingClientRect().width / 1920")


# ---- 形の判定 ----

def test_rough_closed_shapes_become_selected_shape(still, generic_dir):
    with still(motion_url(generic_dir, "#m03")) as page:
        page.keyboard.press("d")
        shapes = [rough_rect(150, 250, 300, 180), rough_ellipse(300, 350, 160, 100), rough_triangle(150, 250, 250, 200)]
        for pts in shapes:
            stroke(page, pts)
            assert last(page)["t"] == "rect"
        btn(page, '[data-shape="ellipse"]').click()
        for pts in shapes:
            stroke(page, pts)
            assert last(page)["t"] == "ellipse"
        stroke(page, rough_ellipse(400, 400, 110, 110))
        o = last(page)
        assert o["t"] == "ellipse" and o["rx"] == o["ry"]                          # ほぼ円は正円
        assert writing(page)["count"] == 7


def test_straight_strokes_become_lines(still, generic_dir):
    with still(motion_url(generic_dir, "#m03")) as page:
        page.keyboard.press("d")
        stroke(page, rough_line(150, 250, 650, 500))
        assert last(page)["t"] == "line" and last(page)["arrow"] == 0
        stroke(page, rough_line(300, 600, 355, 600, jitter=2))                     # 画面で 55px の短い横線
        o = last(page)
        assert o["t"] == "line" and o["a"][1] == o["b"][1]                         # 水平にそろう


def test_other_strokes_stay_free(still, generic_dir):
    with still(motion_url(generic_dir, "#m03")) as page:
        page.keyboard.press("d")
        stroke(page, wavy(200, 300))
        o = last(page)
        assert o["t"] == "free" and o["r"] == 2
        # 字のような線（「あ」のようにくねった線）
        kana = [(300 + 60 * math.sin(i / 4) * (1 - i / 80), 450 + i * 2.2 + 25 * math.cos(i / 2.5)) for i in range(70)]
        stroke(page, kana)
        assert last(page)["t"] == "free"


def test_click_draws_nothing(still, generic_dir):
    with still(motion_url(generic_dir, "#m03")) as page:
        page.keyboard.press("d")
        page.mouse.click(500, 400)
        assert writing(page)["count"] == 0


# ---- 種類ごとの色・太さ ----

def test_styles_per_kind_and_saved(still, generic_dir):
    with still(motion_url(generic_dir, "#m03")) as page:
        page.keyboard.press("d")
        assert saved_ink(page) is None                                             # 変えるまで書かない
        stroke(page, rough_line(150, 250, 650, 300))
        before = last(page)
        assert before["color"] == "#222222" and before["width"] == 6
        btn(page, '[data-kind="line"]').click()
        pop = page.locator(".sp-write-pop")
        assert pop.is_visible()
        pop.locator('[data-c="#1f5fbf"]').click()
        pop.locator('[data-w="12"]').click()
        stroke(page, rough_line(150, 400, 650, 450))
        after = last(page)
        assert after["color"] == "#1f5fbf" and after["width"] == 12
        assert writing(page)["objects"][0]["color"] == "#222222"                   # 前に描いた線は変わらない
        assert saved_ink(page)["line"] == {"c": "#1f5fbf", "w": 12}
        page.reload()
        page.wait_for_function("!!window.__sp")
        page.keyboard.press("d")
        btn(page, '[data-kind="line"]').click()
        pop = page.locator(".sp-write-pop")
        assert pop.locator('[data-c="#1f5fbf"]').get_attribute("aria-pressed") == "true"
        assert pop.locator('[data-w="12"]').get_attribute("aria-pressed") == "true"
        # 窓の中身：手書きだけに「描き味」、文字は「大きさ」で小・中・大
        btn(page, '[data-kind="free"]').click()
        text = page.locator(".sp-write-pop").inner_text()
        assert "描き味" in text and "太さ" in text
        assert page.locator('.sp-write-pop [data-r="2"]').get_attribute("aria-pressed") == "true"
        btn(page, '[data-kind="rect"]').click()
        assert "描き味" not in page.locator(".sp-write-pop").inner_text()
        btn(page, '[data-kind="text"]').click()
        text = page.locator(".sp-write-pop").inner_text()
        assert "大きさ" in text and "太さ" not in text and "描き味" not in text
        assert [t.strip() for t in page.locator(".sp-write-pop [data-w]").all_inner_texts()] == ["小", "中", "大"]
        # 窓の外を押すと閉じる
        page.mouse.click(60, 700)
        assert not page.locator(".sp-write-pop").is_visible()


def test_broken_ink_setting_falls_back(still, generic_dir):
    ink = {"line": {"c": "red", "w": 99}, "rect": {"c": "#2a9d3f", "w": 12}}
    with still(motion_url(generic_dir, "#m03"), settings=json.dumps({"ink": ink})) as page:
        page.keyboard.press("d")
        stroke(page, rough_line(150, 250, 650, 300))
        o = last(page)
        assert o["t"] == "line" and o["color"] == "#222222" and o["width"] == 6    # 線は既定
        stroke(page, rough_rect(150, 350, 300, 180))
        o = last(page)
        assert o["t"] == "rect" and o["color"] == "#2a9d3f" and o["width"] == 12   # □ は緑・太


# ---- ロック ----

def test_lock_draws_boxes_by_drag(still, generic_dir):
    with still(motion_url(generic_dir, "#m03")) as page:
        page.keyboard.press("d")
        rect_btn = btn(page, '[data-shape="rect"]')
        ell_btn = btn(page, '[data-shape="ellipse"]')
        k = scale_of(page)
        rect_btn.dblclick()
        assert "sp-lock" in rect_btn.get_attribute("class") and writing(page)["locked"] is True
        for i in range(3):
            stroke(page, [(150, 250 + i * 10), (450, 400 + i * 10)])
        objs = writing(page)["objects"]
        assert [o["t"] for o in objs] == ["rect"] * 3
        assert abs(objs[0]["w"] - 300 / k) < 3 and abs(objs[0]["h"] - 150 / k) < 3  # 引いた大きさ
        stroke(page, [(150, 250), (450, 400)], shift=True)
        o = last(page)
        assert o["t"] == "rect" and abs(o["w"] - o["h"]) < 1e-6                    # Shift で正方形
        stroke(page, [(200, 300), (205, 600)])                                     # 8 より小さい幅は描かない
        assert writing(page)["count"] == 4
        ell_btn.dblclick()
        assert "sp-lock" in ell_btn.get_attribute("class") and "sp-lock" not in rect_btn.get_attribute("class")
        stroke(page, [(150, 250), (450, 400)])
        assert last(page)["t"] == "ellipse"
        # Esc（選んでいるものなし）→ ロックが外れる
        page.keyboard.press("Escape")
        assert writing(page)["locked"] is False and writing(page)["active"] is True
        assert "sp-lock" not in ell_btn.get_attribute("class")
        stroke(page, rough_line(150, 500, 650, 600))
        assert last(page)["t"] == "line"
        # ロックしたボタンをもう一度押す／もう一方のボタンを押す／書き込みを終える
        rect_btn.dblclick()
        assert writing(page)["locked"] is True
        rect_btn.click()
        assert writing(page)["locked"] is False
        rect_btn.dblclick()
        ell_btn.click()
        assert writing(page)["locked"] is False and writing(page)["shape"] == "ellipse"
        ell_btn.dblclick()
        assert writing(page)["locked"] is True
        btn(page, "button", ).filter(has_text="書き込みを終える").click()
        assert writing(page)["active"] is False and writing(page)["locked"] is False


def test_lock_buttons_keep_width(still, generic_dir):
    with still(motion_url(generic_dir, "#m03")) as page:
        page.keyboard.press("d")
        before = btn(page, '[data-shape="ellipse"]').bounding_box()["x"]
        btn(page, '[data-shape="rect"]').dblclick()
        assert btn(page, '[data-shape="ellipse"]').bounding_box()["x"] == before
        btn(page, '[data-shape="rect"]').click()
        assert btn(page, '[data-shape="ellipse"]').bounding_box()["x"] == before


# ---- 蛍光ペン ----

def test_highlighter_toggle(still, generic_dir):
    with still(motion_url(generic_dir, "#m03")) as page:
        page.keyboard.press("d")
        hl = btn(page, "[data-hl]")
        assert hl.inner_text().strip() == "蛍光ペン"
        hl.click()
        assert writing(page)["highlighter"] is True and hl.get_attribute("aria-pressed") == "true"
        stroke(page, rough_rect(150, 250, 300, 180))                               # 閉じた形も形にしない
        o = last(page)
        assert o["t"] == "free" and o["hl"] and o["color"] == "#ffd60a" and o["width"] == 28
        stroke(page, rough_line(150, 500, 650, 500))
        assert last(page)["t"] == "free"
        hl.click()
        assert writing(page)["highlighter"] is False
        stroke(page, rough_line(150, 600, 650, 600))
        assert last(page)["t"] == "line"
        hl.click()
        btn(page, '[data-shape="rect"]').click()                                   # □ のボタンで蛍光ペンが切れる
        assert writing(page)["highlighter"] is False
        hl.click()
        btn(page, '[data-shape="ellipse"]').dblclick()
        assert writing(page)["highlighter"] is False and writing(page)["locked"] is True


# ---- ひとつ戻す・全部消す ----

def test_undo_steps_back(still, generic_dir):
    mod = "ControlOrMeta+z"
    with still(motion_url(generic_dir, "#m03")) as page:
        page.keyboard.press("d")
        stroke(page, wavy(200, 300))
        stroke(page, rough_rect(150, 400, 300, 180))
        assert [o["t"] for o in writing(page)["objects"]] == ["free", "rect"]
        page.keyboard.press(mod)
        assert [o["t"] for o in writing(page)["objects"]] == ["free", "free"]      # 形に直したものは、まず手書きに戻る
        page.keyboard.press(mod)
        assert [o["t"] for o in writing(page)["objects"]] == ["free"]
        page.keyboard.press(mod)
        assert writing(page)["count"] == 0
        page.keyboard.press(mod)                                                   # 戻すものがなくても何も起きない
        assert writing(page)["count"] == 0
        # 帯の「ひとつ戻す」も同じ
        stroke(page, wavy(200, 300))
        stroke(page, rough_rect(150, 400, 300, 180))
        btn(page, "button").filter(has_text="ひとつ戻す").click()
        assert [o["t"] for o in writing(page)["objects"]] == ["free", "free"]
        btn(page, "button").filter(has_text="ひとつ戻す").click()
        btn(page, "button").filter(has_text="ひとつ戻す").click()
        assert writing(page)["count"] == 0
        # 全部消す・E は「ひとつ戻す」で全部戻る
        stroke(page, rough_line(150, 250, 650, 300))
        stroke(page, wavy(200, 450))
        stroke(page, rough_rect(150, 500, 300, 150))
        btn(page, "button").filter(has_text="全部消す").click()
        assert writing(page)["count"] == 0
        page.keyboard.press(mod)
        assert writing(page)["count"] == 3
        page.keyboard.press("e")
        assert writing(page)["count"] == 0
        btn(page, "button").filter(has_text="ひとつ戻す").click()
        assert [o["t"] for o in writing(page)["objects"]] == ["line", "free", "rect"]


def test_undo_is_per_page(still, generic_dir):
    with still(motion_url(generic_dir, "#m03")) as page:
        page.keyboard.press("d")
        stroke(page, rough_line(150, 250, 650, 300))
        page.keyboard.press("ArrowDown")
        assert where(page) == ("m04", 0)
        stroke(page, rough_line(150, 250, 650, 300))
        for _ in range(3):
            page.keyboard.press("ControlOrMeta+z")
        assert writing(page)["count"] == 0
        page.keyboard.press("ArrowUp")
        assert writing(page)["count"] == 1
        assert writing(page)["page"] == "s:m03"


def test_undo_empty_calls_hook_result_ignored_in_task1(still, generic_dir):
    # 追加ページはまだない。戻すものがないときは何も起きず、例外も出ない
    with still(motion_url(generic_dir, "#m03")) as page:
        page.keyboard.press("d")
        btn(page, "button").filter(has_text="ひとつ戻す").click()
        assert writing(page)["count"] == 0 and writing(page)["active"] is True


def test_cmd_z_ignored_without_writing_and_in_fields(still, generic_dir):
    with still(motion_url(generic_dir, "#m03"), settings=json.dumps({"controls": "always"})) as page:
        page.keyboard.press("ControlOrMeta+z")                                     # 書き込みでない：何も起きない
        assert writing(page)["active"] is False
        page.keyboard.press("d")
        stroke(page, rough_line(150, 250, 650, 300))
        page.keyboard.press("d")
        page.keyboard.press("ControlOrMeta+z")                                     # 終えたあとも、書き込みの間でないので戻さない
        assert writing(page)["count"] == 1
        page.keyboard.press("d")
        page.keyboard.press("m")                                                   # メモの帯
        field = page.locator(".sp-memo-text")
        field.click()
        field.fill("abc")
        page.keyboard.press("ControlOrMeta+z")
        assert writing(page)["count"] == 1                                         # 欄の中の取り消しはブラウザーに任せる


def test_no_dom_until_d(still, generic_dir):
    with still(motion_url(generic_dir, "#m03")) as page:
        assert page.locator(".sp-ink").count() == 0 and page.locator(TOOLS).count() == 0
        result = page.evaluate("""() => {
          const out = {};
          const fire = (target, ev) => { target.dispatchEvent(ev); return ev.defaultPrevented; };
          const stage = document.getElementById('stage');
          out.context = fire(stage, new MouseEvent('contextmenu', { bubbles: true, cancelable: true }));
          out.dbl = fire(stage, new MouseEvent('dblclick', { bubbles: true, cancelable: true }));
          out.undo = fire(document.body, new KeyboardEvent('keydown', { key: 'z', ctrlKey: true, bubbles: true, cancelable: true }));
          out.undoMeta = fire(document.body, new KeyboardEvent('keydown', { key: 'z', metaKey: true, bubbles: true, cancelable: true }));
          return out; }""")
        assert result == {"context": False, "dbl": False, "undo": False, "undoMeta": False}
        assert page.locator(".sp-ink").count() == 0 and page.locator(TOOLS).count() == 0


def test_d_button_and_help_labels(still, generic_dir):
    with still(motion_url(generic_dir, "#m03")) as page:
        page.locator(".sp-controls button", has_text="D 書き込み").dispatch_event("click")
        assert writing(page)["active"] is True
        assert page.locator(".sp-controls button", has_text="D 書き込み").get_attribute("aria-pressed") == "true"
        assert page.locator(".sp-controls button", has_text="D ペン").count() == 0
        btn(page, "button").filter(has_text="書き込みを終える（D）").click()
        assert writing(page)["active"] is False and not page.locator(TOOLS).is_visible()
        page.keyboard.press("?")
        rows = page.evaluate("Array.from(document.querySelectorAll('.sp-help-row'), r => [Array.from(r.querySelectorAll('.sp-key'), k => k.textContent), r.querySelector('.sp-help-text').textContent])")
        d_rows = [r for r in rows if r[0] == ["D"]]
        assert len(d_rows) == 1 and "書き込みを始める・終える" in d_rows[0][1]


# ---- 文字と、選んでから変える ----

TEXT = "textarea.sp-write-text"
MINI = ".sp-write-mini"


def screen(page, p):
    """舞台の座標 p を画面の座標にする。"""
    return page.evaluate("""p => { const r = document.querySelector('.sp-ink').getBoundingClientRect();
      return [r.left + p[0] * r.width / 1920, r.top + p[1] * r.height / 1080]; }""", list(p))


def right_click(page, x, y):
    page.mouse.click(x, y, button="right")


def dbl(page, x, y):
    page.mouse.dblclick(x, y)


def selected(page):
    return writing(page)["selected"]


def mini_buttons(page):
    return page.locator(f"{MINI} button")


def test_right_click_places_text(still, generic_dir):
    with still(motion_url(generic_dir, "#m03")) as page:
        page.keyboard.press("d")
        right_click(page, 400, 300)
        assert page.locator(TEXT).count() == 1 and page.evaluate("document.activeElement.matches('textarea.sp-write-text')")
        assert writing(page)["editing"] is True
        box = page.locator(TEXT).bounding_box()
        assert abs(box["x"] - 400) < 6 and abs(box["y"] - 300) < 6
        page.keyboard.type("議事メモ")
        page.keyboard.press("Enter")
        assert page.locator(TEXT).count() == 0 and writing(page)["editing"] is False
        o = last(page)
        assert o["t"] == "text" and o["lines"] == ["議事メモ"] and o["color"] == "#222222" and o["size"] == 32
        # Shift+Enter で2行
        right_click(page, 400, 500)
        page.keyboard.type("一行目")
        page.keyboard.press("Shift+Enter")
        page.keyboard.type("二行目")
        page.keyboard.press("Enter")
        assert last(page)["lines"] == ["一行目", "二行目"]
        # Esc で何も置かない
        right_click(page, 700, 300)
        page.keyboard.type("やめる")
        page.keyboard.press("Escape")
        assert page.locator(TEXT).count() == 0 and writing(page)["count"] == 2
        # 欄の外を押すと決まる
        right_click(page, 700, 300)
        page.keyboard.type("外を押す")
        page.mouse.click(900, 700)
        assert page.locator(TEXT).count() == 0 and last(page)["lines"] == ["外を押す"]


def test_enter_during_composition_does_not_commit(still, generic_dir):
    with still(motion_url(generic_dir, "#m03")) as page:
        page.keyboard.press("d")
        right_click(page, 400, 300)
        page.keyboard.type("あ")
        page.evaluate("""() => { const t = document.querySelector('textarea.sp-write-text');
          t.dispatchEvent(new CompositionEvent('compositionstart', { bubbles: true }));
          for (const key of ['Enter', 'Escape']) t.dispatchEvent(new KeyboardEvent('keydown', { key, isComposing: true, keyCode: 229, bubbles: true, cancelable: true }));
          for (const key of ['Enter', 'Escape']) t.dispatchEvent(new KeyboardEvent('keydown', { key, keyCode: 229, bubbles: true, cancelable: true })); }""")
        assert page.locator(TEXT).count() == 1 and writing(page)["count"] == 0


def test_right_click_without_writing_is_browser_menu(still, generic_dir):
    with still(motion_url(generic_dir, "#m03")) as page:
        assert page.evaluate("""() => { const ev = new MouseEvent('contextmenu', { bubbles: true, cancelable: true });
          document.getElementById('stage').dispatchEvent(ev); return ev.defaultPrevented; }""") is False
        page.keyboard.press("d")
        page.keyboard.press("d")
        assert page.evaluate("""() => { const ev = new MouseEvent('contextmenu', { bubbles: true, cancelable: true });
          document.getElementById('stage').dispatchEvent(ev); return ev.defaultPrevented; }""") is False


def test_double_click_selects_and_mini_bar(still, generic_dir):
    with still(motion_url(generic_dir, "#m03")) as page:
        page.keyboard.press("d")
        stroke(page, rough_line(150, 250, 650, 500))
        dbl(page, 400, 375)
        assert selected(page) == 0 and page.locator(MINI).is_visible()
        assert page.locator(f"{MINI} [data-arrow]").count() == 3
        assert page.locator(f"{MINI} [data-c]").count() == 9
        assert mini_buttons(page).filter(has_text="消す").count() == 1
        page.keyboard.press("Escape")
        stroke(page, rough_rect(800, 250, 300, 180))
        dbl(page, 800, 340)
        assert writing(page)["objects"][selected(page)]["t"] == "rect"
        assert page.locator(f"{MINI} [data-arrow]").count() == 0 and page.locator(f"{MINI} [data-c]").count() == 9
        page.keyboard.press("Escape")
        btn(page, "[data-hl]").click()
        stroke(page, rough_line(150, 700, 650, 700, jitter=1))
        o = last(page)
        assert o.get("hl")
        dbl(page, 400, 700)
        assert writing(page)["objects"][selected(page)].get("hl")
        assert page.locator(f"{MINI} [data-c]").count() == 0 and page.locator(f"{MINI} [data-arrow]").count() == 0
        assert mini_buttons(page).filter(has_text="消す").count() == 1


def test_arrow_direction_takes_arrow_style(still, generic_dir):
    mod = "ControlOrMeta+z"
    with still(motion_url(generic_dir, "#m03")) as page:
        page.keyboard.press("d")
        stroke(page, rough_line(150, 250, 650, 500))
        assert last(page)["color"] == "#222222" and last(page)["width"] == 6
        dbl(page, 400, 375)
        page.locator(f'{MINI} [data-arrow="1"]').click()
        o = last(page)
        assert o["arrow"] == 1 and o["color"] == "#d62828" and o["width"] == 6
        page.locator(f'{MINI} [data-c="#2a9d3f"]').click()
        assert last(page)["color"] == "#2a9d3f"
        page.keyboard.press(mod)
        page.keyboard.press(mod)
        o = last(page)
        assert o["arrow"] == 0 and o["color"] == "#222222" and o["width"] == 6


def test_move_resize_endpoints_delete(still, generic_dir):
    mod = "ControlOrMeta+z"
    with still(motion_url(generic_dir, "#m03")) as page:
        page.keyboard.press("d")
        stroke(page, rough_rect(300, 300, 300, 200))
        r0 = last(page)
        k = scale_of(page)
        dbl(page, 450, 400)
        assert selected(page) == 0
        stroke(page, [(450, 400), (500, 440), (550, 460)])
        r1 = last(page)
        assert abs((r1["x"] - r0["x"]) - 100 / k) < 3 and abs((r1["y"] - r0["y"]) - 60 / k) < 3
        assert r1["w"] == r0["w"] and selected(page) == 0
        # 右下のつまみ
        hx, hy = screen(page, (r1["x"] + r1["w"], r1["y"] + r1["h"]))
        stroke(page, [(hx, hy), (hx + 40, hy + 30)])
        r2 = last(page)
        assert r2["x"] == r1["x"] and r2["y"] == r1["y"] and r2["w"] > r1["w"] + 40 and r2["h"] > r1["h"] + 20
        hx, hy = screen(page, (r2["x"] + r2["w"], r2["y"] + r2["h"]))
        tx, ty = screen(page, (r2["x"] + 5, r2["y"] + 5))                          # 左上の角のすぐ近くまで縮める
        stroke(page, [(hx, hy), (tx, ty)])
        r3 = last(page)
        assert r3["w"] == 24 and r3["h"] == 24 and r3["x"] == r1["x"] and r3["y"] == r1["y"]
        # 線の端
        page.keyboard.press("Escape")
        stroke(page, rough_line(150, 700, 650, 700, jitter=1))
        ln = last(page)
        dbl(page, 400, 700)
        ex, ey = screen(page, ln["b"])
        stroke(page, [(ex, ey), (ex + 60, ey - 80)])
        l2 = last(page)
        assert l2["a"] == ln["a"] and abs(l2["b"][0] - ln["b"][0] - 60 / k) < 3 and abs(l2["b"][1] - ln["b"][1] + 80 / k) < 3
        # Delete で消え、⌘Z で元の位置に戻る
        n = writing(page)["count"]
        page.keyboard.press("Delete")
        assert writing(page)["count"] == n - 1 and selected(page) == -1 and not page.locator(MINI).is_visible()
        page.keyboard.press(mod)
        assert writing(page)["count"] == n and last(page)["b"] == l2["b"]
        # 小さな帯の「消す」も同じ
        dbl(page, 400, 700 - 40)
        assert selected(page) == n - 1
        mini_buttons(page).filter(has_text="消す").click()
        assert writing(page)["count"] == n - 1
        page.keyboard.press(mod)
        assert writing(page)["count"] == n
        # Backspace
        dbl(page, 400, 700 - 40)
        page.keyboard.press("Backspace")
        assert writing(page)["count"] == n - 1


def test_double_click_on_overlap_selects_topmost(still, generic_dir):
    with still(motion_url(generic_dir, "#m03")) as page:
        page.keyboard.press("d")
        stroke(page, rough_rect(300, 300, 300, 200))
        r = writing(page)["objects"][0]
        x0, y0 = screen(page, (r["x"] + r["w"], r["y"] + r["h"] / 2))
        stroke(page, rough_line(x0 - 100, y0 - 100, x0 + 100, y0 + 100, jitter=1))
        assert last(page)["t"] == "line"
        dbl(page, x0, y0)
        assert writing(page)["objects"][selected(page)]["t"] == "line"
        page.keyboard.press("Escape")
        cx, cy = screen(page, (r["x"] + r["w"] / 2, r["y"] + r["h"] / 2))
        dbl(page, cx, cy)
        assert writing(page)["objects"][selected(page)]["t"] == "rect"


def test_selection_ends(still, generic_dir):
    with still(motion_url(generic_dir, "#m03")) as page:
        page.keyboard.press("d")
        stroke(page, rough_line(150, 250, 650, 500))

        def pick():
            dbl(page, 400, 375)
            assert selected(page) == 0 and page.locator(MINI).is_visible()

        def ended():
            assert selected(page) == -1 and not page.locator(MINI).is_visible()
        pick()
        page.mouse.click(1000, 800)                                                # ほかの所を押す
        ended()
        pick()
        page.keyboard.press("Escape")
        ended()
        assert writing(page)["active"] is True
        pick()
        page.keyboard.press("ArrowDown")                                           # ↓ で移る
        ended()
        page.keyboard.press("ArrowUp")
        pick()
        page.keyboard.press("d")                                                   # 書き込みを終える
        assert writing(page)["active"] is False and selected(page) == -1
        assert not page.locator(MINI).is_visible()


def test_escape_order_inside_writing(still, generic_dir):
    with still(motion_url(generic_dir, "#m03")) as page:
        page.keyboard.press("d")
        stroke(page, rough_line(150, 250, 650, 500))
        right_click(page, 900, 300)
        page.keyboard.type("x")
        page.keyboard.press("Escape")
        assert page.locator(TEXT).count() == 0 and writing(page)["active"] is True
        dbl(page, 400, 375)
        page.keyboard.press("Escape")
        assert selected(page) == -1 and writing(page)["active"] is True
        btn(page, '[data-shape="rect"]').dblclick()
        assert writing(page)["locked"] is True
        page.keyboard.press("Escape")
        assert writing(page)["locked"] is False and writing(page)["active"] is True
        page.keyboard.press("o")
        assert page.locator(".sp-overview").count() == 1
        page.keyboard.press("Escape")
        assert page.locator(".sp-overview").count() == 0 and writing(page)["active"] is True
        page.keyboard.press("Escape")
        assert writing(page)["active"] is False


def test_no_drawing_over_overlay(still, generic_dir):
    with still(motion_url(generic_dir, "#m03")) as page:
        page.keyboard.press("d")
        page.keyboard.press("o")
        assert page.locator(".sp-overview").count() == 1
        n = writing(page)["count"]
        stroke(page, rough_line(300, 300, 900, 600))
        stroke(page, [(700, 400), (720, 420), (740, 400)])
        assert writing(page)["count"] == n == 0


def test_resize_while_editing(still, generic_dir):
    with still(motion_url(generic_dir, "#m03")) as page:
        page.keyboard.press("d")
        right_click(page, 400, 300)
        page.keyboard.type("窓を変える")
        page.set_viewport_size({"width": 1280, "height": 720})
        page.wait_for_timeout(200)
        assert page.locator(TEXT).count() == 0 and last(page)["lines"] == ["窓を変える"]
        stroke(page, rough_rect(300, 250, 300, 180))
        r = last(page)
        dbl(page, 300, 340)
        assert selected(page) >= 0
        page.keyboard.press("t")
        page.wait_for_timeout(300)
        assert selected(page) >= 0
        sx, sy = screen(page, (r["x"], r["y"]))
        ex, ey = screen(page, (r["x"] + r["w"], r["y"] + r["h"]))
        mb = page.locator(MINI).bounding_box()
        assert mb["x"] <= ex and mb["x"] + mb["width"] >= sx - 20
        assert mb["y"] + mb["height"] <= sy + 2 or mb["y"] >= ey - 2


def test_double_click_jitter_leaves_no_dot(still, generic_dir):
    with still(motion_url(generic_dir, "#m03")) as page:
        page.keyboard.press("d")
        stroke(page, rough_rect(300, 300, 300, 200))
        r = last(page)
        x, y = screen(page, (r["x"] + r["w"] / 2, r["y"]))                         # □ の上の縁
        page.mouse.click(x, y)
        page.mouse.down(click_count=2)
        page.mouse.move(x + 5, y + 2, steps=4)                                     # 2回目の押している間に画面で約5px動く
        page.mouse.up(click_count=2)
        assert writing(page)["count"] == 1 and writing(page)["selected"] == 0
        page.keyboard.press("Escape")
        # ちゃんと引いた短い線（舞台で約 20px）は描く
        sx, sy = screen(page, (1000, 800))
        k = scale_of(page)
        stroke(page, [(sx, sy), (sx + 10 * k, sy + 5 * k), (sx + 20 * k, sy + 10 * k)])
        assert writing(page)["count"] == 2


# ---- ドラッグの途中でページが変わる・書き込みが終わる ----

def _drag_then(page, key_press):
    """□ を描いて選び、押したまま動かし、押している間に key_press を呼ぶ。離したあと、元のページへ戻って □ を返す。"""
    page.keyboard.press("d") if not writing(page)["active"] else None
    stroke(page, rough_rect(300, 300, 300, 200))
    r0 = last(page)
    dbl(page, 450, 400)
    assert selected(page) == 0
    page.mouse.move(450, 400)
    page.mouse.down()
    page.mouse.move(520, 450, steps=5)
    key_press()
    page.mouse.up()
    return r0


def test_drag_committed_when_page_changes(still, generic_dir):
    mod = "ControlOrMeta+z"
    with still(motion_url(generic_dir, "#m03")) as page:
        page.keyboard.press("d")
        r0 = _drag_then(page, lambda: page.keyboard.press("ArrowDown"))
        page.keyboard.press("ArrowUp")
        r1 = last(page)
        assert writing(page)["count"] == 1 and r1["x"] > r0["x"] + 40 and r1["y"] > r0["y"] + 30
        page.keyboard.press(mod)
        assert writing(page)["count"] == 1 and last(page) == r0                    # 1回で元の位置にそのまま戻る


def test_drag_committed_when_writing_ends(still, generic_dir):
    mod = "ControlOrMeta+z"
    with still(motion_url(generic_dir, "#m03")) as page:
        page.keyboard.press("d")
        r0 = _drag_then(page, lambda: page.keyboard.press("d"))
        assert writing(page)["active"] is False
        page.keyboard.press("d")
        r1 = last(page)
        assert r1["x"] > r0["x"] + 40
        page.keyboard.press(mod)
        assert writing(page)["count"] == 1 and last(page) == r0


def test_delete_in_memo_field_keeps_selection(still, generic_dir):
    mod = "ControlOrMeta+z"
    with still(motion_url(generic_dir, "#m03")) as page:
        page.keyboard.press("d")
        stroke(page, rough_line(150, 250, 650, 500))
        dbl(page, 400, 375)
        assert selected(page) == 0
        page.keyboard.press("m")
        field = page.locator(".sp-memo-text")
        field.click()
        page.keyboard.type("abcd")
        page.keyboard.press("Backspace")
        page.keyboard.press("Home")
        page.keyboard.press("Delete")
        assert field.input_value() == "bc"
        assert writing(page)["count"] == 1
        page.keyboard.press(mod)                                                   # 欄の中の取り消しは書き込みを戻さない
        assert writing(page)["count"] == 1


def test_arrow_head_is_selectable(still, generic_dir):
    with still(motion_url(generic_dir, "#m03")) as page:
        page.keyboard.press("d")
        k = scale_of(page)
        ends = []
        for i, (direction, y) in enumerate([(1, 250), (2, 600)]):
            stroke(page, rough_line(150, y, 650, y, jitter=0.5))
            ln = last(page)
            mx, my = screen(page, ((ln["a"][0] + ln["b"][0]) / 2, ln["a"][1]))
            dbl(page, mx, my)
            page.locator(f'{MINI} [data-arrow="{direction}"]').click()
            page.keyboard.press("Escape")
            ends.append((i, direction))
        for i, direction in ends:
            ln = writing(page)["objects"][i]
            tip = ln["b"] if direction == 1 else ln["a"]
            sign = -1 if direction == 1 else 1                                     # 頭は先端から線の内側へ
            w = ln["width"]
            L = 14 + w * 2.2
            for back, off in [(6, 0), (L - 4, 11.8 * (L - 4) / L)]:                # 先端の少し内側・羽の角の近く
                p = (tip[0] + sign * back, tip[1] + off)
                x, y = screen(page, p)
                dbl(page, x, y)
                assert selected(page) == i, (i, back)
                page.keyboard.press("Escape")


# ---- 設定 ink：値ごとに確かめる（種類ごと。壊れた値だけ既定に戻り、正しい値は残る） ----

@pytest.mark.parametrize("ink, want", [
    ({"arrow": {"c": "#2a9d3f", "w": 99}}, {"arrow": {"c": "#2a9d3f", "w": 6}}),
    ({"arrow": {"c": "green", "w": 12}}, {"arrow": {"c": "#d62828", "w": 12}}),
    ({"ellipse": {"c": "#7b3fbf", "w": "12"}}, {"ellipse": {"c": "#7b3fbf", "w": 6}}),
    ({"ellipse": {"c": 5, "w": 12}}, {"ellipse": {"c": "#d62828", "w": 12}}),
    ({"text": {"c": "#1f5fbf", "w": 33}}, {"text": {"c": "#1f5fbf", "w": 32}}),
    ({"text": {"c": "#123456", "w": 40}}, {"text": {"c": "#222222", "w": 40}}),
    ({"free": {"c": "#f77f00", "w": 12, "r": 5}}, {"free": {"c": "#f77f00", "w": 12, "r": 2}}),
    ({"free": {"c": "#f77f00", "w": 7, "r": 7}}, {"free": {"c": "#f77f00", "w": 6, "r": 7}}),
    ({"free": {"c": None, "w": 12, "r": 0}}, {"free": {"c": "#222222", "w": 12, "r": 0}}),
])
def test_broken_ink_values_fall_back_one_by_one(still, generic_dir, ink, want):
    with still(motion_url(generic_dir, "#m03"), settings=json.dumps({"ink": ink})) as page:
        styles = writing(page)["styles"]
        for kind, expected in want.items():
            got = {k: v for k, v in styles[kind].items() if k in expected}
            assert got == expected, (kind, styles[kind])


def test_short_arrow_selectable_from_wing_corners(still, generic_dir):
    """矢印を縮めて 10 舞台px ほどにしても、頭の羽の角から選べる（長さの下限は設けない）。"""
    for direction in (1, 2):
        with still(motion_url(generic_dir, "#m03")) as page:
            page.keyboard.press("d")
            stroke(page, rough_line(150, 300, 650, 300, jitter=0.5))
            dbl(page, 400, 300)
            page.locator(f'{MINI} [data-arrow="{direction}"]').click()
            ln = last(page)
            near, far = (ln["a"], ln["b"]) if direction == 1 else (ln["b"], ln["a"])
            # far（頭と反対の端）を、頭の側の端のすぐ近くまで引く
            fx, fy = screen(page, far)
            tx, ty = screen(page, (near[0] - 10, near[1]))
            stroke(page, [(fx, fy), (tx, ty)])
            ln = last(page)
            assert math.dist(ln["a"], ln["b"]) < 16 and ln["arrow"] == direction
            page.keyboard.press("Escape")
            assert selected(page) == -1
            tip = ln["b"] if direction == 1 else ln["a"]
            other = ln["a"] if direction == 1 else ln["b"]
            ang = math.atan2(tip[1] - other[1], tip[0] - other[0])
            L = 14 + ln["width"] * 2.2
            for da in (-0.45, 0.45):
                corner = (tip[0] - L * math.cos(ang + da), tip[1] - L * math.sin(ang + da))
                x, y = screen(page, corner)
                dbl(page, x, y)
                assert selected(page) == 0, (direction, da)
                page.keyboard.press("Escape")
                assert selected(page) == -1
