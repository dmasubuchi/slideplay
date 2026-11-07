"""指す層の試験：ホバーの強調、関係するものの一緒の強調、マウスの光、操作ボタンの帯、押せる印。

指す層を選んだデッキ（examples/generic/motion.html、point: true）のメインの舞台だけに効く。
動きを止めても強調は残る（浮き上がりと揺れだけ止まる）。光は動きのスイッチと OS の設定では止めない。
"""
import json
import re

import pytest

from test_motion import opened
from test_swipe import finger_page, tap

LIGHT = ".sp-light"


@pytest.fixture
def moving(browser):
    return lambda url, **kw: opened(browser, url, "no-preference", **kw)


@pytest.fixture
def still(browser):
    return lambda url, **kw: opened(browser, url, "reduce", **kw)


def motion_url(generic_dir, suffix=""):
    return (generic_dir / "motion.html").as_uri() + suffix


def center(page, selector):
    b = page.locator(selector).first.bounding_box()
    return b["x"] + b["width"] / 2, b["y"] + b["height"] / 2


def scale_of(page, selector):
    t = page.evaluate(f"getComputedStyle(document.querySelector({json.dumps(selector)})).transform")
    m = re.match(r"matrix\(([^,]+),", t)
    return float(m.group(1)) if m else 1.0


def opacity_of(page, selector):
    return page.evaluate(f"getComputedStyle(document.querySelector({json.dumps(selector)})).opacity")


def light_visible(page):
    return page.evaluate(f"(() => {{ const l = document.querySelector('{LIGHT}'); return !!l && getComputedStyle(l).display !== 'none' && getComputedStyle(l).opacity !== '0'; }})()")


def light_center(page):
    b = page.locator(LIGHT).bounding_box()
    return b["x"] + b["width"] / 2, b["y"] + b["height"] / 2


CARDS = '#stage [data-sp-role="card"]'


def test_hover_lifts_and_dims(moving, generic_dir):
    with moving(motion_url(generic_dir, "#m02")) as page:
        page.mouse.move(*center(page, CARDS))
        page.wait_for_timeout(400)
        assert scale_of(page, CARDS) == pytest.approx(1.04, abs=0.005)
        assert opacity_of(page, f"{CARDS}:nth-child(2)") == "0.35"


def test_hover_still_mode(still, generic_dir):
    with still(motion_url(generic_dir, "#m02")) as page:
        page.mouse.move(*center(page, CARDS))
        assert scale_of(page, CARDS) == 1.0                         # 浮き上がりはしない
        assert opacity_of(page, f"{CARDS}:nth-child(2)") == "0.35"  # 強調はすぐ


def test_key_pair_lights_together(moving, generic_dir):
    with moving(motion_url(generic_dir, "#m03")) as page:
        page.mouse.move(*center(page, '#stage .bar-l[data-sp-key="b0"]'))
        assert page.evaluate("[...document.querySelectorAll('#stage .sp-key-on')].map(e => e.getAttribute('data-sp-key'))") == ["b0", "b0"]
        page.mouse.move(5, 5)
        assert page.locator("#stage .sp-key-on").count() == 0


def test_light_follows_mouse(moving, generic_dir):
    with moving(motion_url(generic_dir, "#m03")) as page:
        page.mouse.move(700, 400)
        assert light_visible(page)
        x, y = light_center(page)
        assert abs(x - 700) <= 2 and abs(y - 400) <= 2
        page.mouse.move(720, 10)                                    # 舞台の外（上の黒い帯）
        assert not light_visible(page)


def test_light_setting_off(moving, generic_dir):
    with moving(motion_url(generic_dir, "#m02"), settings=json.dumps({"light": False})) as page:
        page.mouse.move(*center(page, CARDS))
        assert not light_visible(page)
        assert opacity_of(page, f"{CARDS}:nth-child(2)") in ("0.35", "1")      # ホバーは効く（途中の値でもよい）
        page.wait_for_timeout(400)
        assert opacity_of(page, f"{CARDS}:nth-child(2)") == "0.35"


def test_light_hidden_under_overlay(moving, generic_dir):
    with moving(motion_url(generic_dir, "#m03")) as page:
        page.mouse.move(700, 400)
        assert light_visible(page)
        page.keyboard.press("?")
        page.mouse.move(710, 410)
        assert not light_visible(page)
        page.keyboard.press("Escape")
        page.mouse.move(700, 400)
        assert light_visible(page)


def test_light_ignores_motion_switch(still, generic_dir):
    with still(motion_url(generic_dir, "#m03")) as page:
        page.mouse.move(700, 400)
        assert light_visible(page)


def test_no_point_for_unchosen_deck(moving, generic_dir):
    with moving((generic_dir / "proposal.html").as_uri() + "#p02") as page:
        page.mouse.move(700, 400)
        assert page.locator("#stage.sp-point").count() == 0
        assert not light_visible(page)


def test_controls_only_near_bottom_with_light(moving, generic_dir):
    with moving(motion_url(generic_dir, "#m03")) as page:
        page.mouse.move(700, 400)
        assert page.locator(".sp-controls.sp-on").count() == 0
        page.mouse.move(700, 900 - 50)
        assert page.locator(".sp-controls.sp-on").count() == 1
    with moving((generic_dir / "proposal.html").as_uri() + "#p02") as page:
        page.mouse.move(700, 400)
        assert page.locator(".sp-controls.sp-on").count() == 1            # 指す層のないデッキは今のまま


def test_touch_device_has_no_point(browser, generic_dir):
    with finger_page(browser, motion_url(generic_dir, "#m02"), is_mobile=True) as page:
        tap(page, (500, 300))
        assert page.locator("#stage.sp-point").count() == 0
        assert not light_visible(page)


def test_thumbnails_and_print_have_no_point(moving, generic_dir):
    with moving(motion_url(generic_dir, "#m03")) as page:
        page.mouse.move(*center(page, '#stage .bar-l[data-sp-key="b0"]'))
        page.keyboard.press("o")
        assert page.locator(".sp-thumb .sp-target").count() > 0
        assert page.locator(".sp-thumb .sp-point, .sp-thumb .sp-target.sp-point, .sp-thumb .sp-key-on").count() == 0
        page.keyboard.press("Escape")
        page.evaluate("void (window.print = () => {})")
        page.keyboard.press("p")
        page.wait_for_function("!!document.querySelector('.sp-print .sp-print-page')")
        assert page.locator(".sp-print .sp-target.sp-point, .sp-print .sp-key-on").count() == 0


@pytest.mark.parametrize("mode, expect", [("moving", True), ("still", False)])
def test_link_wiggle(moving, still, generic_dir, mode, expect):
    opener = moving if mode == "moving" else still
    with opener(motion_url(generic_dir, "#m06")) as page:
        page.mouse.move(*center(page, '#stage [data-link="0"]'))
        n = page.evaluate("document.querySelector('.sp-linkmark[data-index=\"0\"]').getAnimations().length")
        assert (n > 0) is expect
        assert page.evaluate("getComputedStyle(document.querySelector('#stage [data-link=\"0\"]')).cursor") == "pointer"
