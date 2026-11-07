"""画面の大きさの試験（重点：820×1180 の縦）。

4つの画面（1440×900、1000×700、1180×820、820×1180）で、次の中身のそれぞれについて、ページがスクロールせず、
sp- の部品が画面の外にはみ出さないことを確かめる（検査は layout_check.py）。

- デッキ：proposal（汎用の見本）、講座の形の見本（course_dir）の第1章（25枚）
- 目次：汎用の見本の目次、講座の形の見本の目次（7枚）

デッキは次の状態を見る：
- 通常の表示（操作ボタンを「いつも出す」にして、帯が出ている状態で。全スライド・全段階を ↓ で歩き、1つ進むたびに検査する。
  最初のスライドの ↑ の知らせ、各スライドの最後の段階での L（リンクを表示）も見る）
- N を開いた状態（同じく全スライド・全段階を歩く）
- O を開いた状態、? を開いた状態（最初と最後のスライドで。ノートを開いたままの重なりも）
目次は、全ページ（Shift＋↓ で歩く）の通常の表示と、? を開いた状態。N・O を押しても何も起きない（デッキだけのキー）ことも同じ検査で確かめる。
"""
import json
from contextlib import contextmanager

import pytest

from helpers import page_session
from layout_check import layout_problems

VIEWPORTS = [(1440, 900), (1000, 700), (1180, 820), (820, 1180)]
SETTINGS_KEY = "sp-settings-v1"
DECKS = ["proposal", "course-ch-01"]
DECK_CASES = [(d, v) for d in DECKS for v in VIEWPORTS]
CATALOGS = ["generic", "course"]


def deck_url(name, generic_dir, course_dir):
    if name == "proposal":
        return (generic_dir / "proposal.html").as_uri()
    return (course_dir / f"ch-{name.removeprefix('course-ch-')}" / "slides.html").as_uri()


def catalog_url(name, generic_dir, course_dir):
    return ((generic_dir if name == "generic" else course_dir) / "index.html").as_uri()


@contextmanager
def layout_session(browser, url, viewport, controls="always", notes=False):
    """設定（操作ボタンの出し方・ノート）を先に入れて url を開く。pageerror があれば抜けるときに失敗（page_session）。"""
    with page_session(browser, "about:blank", viewport=viewport) as page:
        value = json.dumps({"controls": controls, "notes": notes})
        page.add_init_script(f"try {{ localStorage.setItem({json.dumps(SETTINGS_KEY)}, {json.dumps(value)}); }} catch (e) {{}}")
        page.goto(url)
        page.wait_for_function("!!window.__sp")
        yield page


class Collector:
    """検査の結果を集める（最初の問題で止めず、どの状態で何が出たかを全部知らせる）。"""

    def __init__(self, page, viewport):
        self.page, self.viewport, self.found = page, viewport, []

    def check(self, label):
        for problem in layout_problems(self.page):
            self.found.append(f"{self.viewport[0]}x{self.viewport[1]} {label}: {problem}")

    def assert_clean(self):
        assert not self.found, f"画面の大きさの問題が {len(self.found)} 件:\n" + "\n".join(self.found[:40])


def state(page):
    return page.evaluate("__sp.state()")


def walk_deck(page, collector, label):
    """最初のスライドから最後の段階まで ↓ で歩き、1つ進むたびに検査する。歩いた数を返す。"""
    page.keyboard.press("Home")
    info = page.evaluate("deckInfo()")
    total = sum(s["steps"] + 1 for s in info)
    collector.check(f"{label} 1/{total}")
    for n in range(1, total):
        page.keyboard.press("ArrowDown")
        collector.check(f"{label} {n + 1}/{total} {state(page)['id']}.{state(page)['step']}")
    assert (state(page)["id"], state(page)["step"]) == (info[-1]["id"], info[-1]["steps"])      # 最後まで歩いた
    return total


def walk_links(page, collector, label):
    """各スライドの最後の段階で L（リンクを表示）を開いて検査し、閉じる。リンクのないスライドでは知らせが出る。"""
    info = page.evaluate("deckInfo()")
    page.keyboard.press("Home")
    for i, s in enumerate(info):
        if i:
            page.keyboard.press("Shift+ArrowDown")
        for _ in range(s["steps"]):
            page.keyboard.press("ArrowDown")
        page.keyboard.press("l")
        if page.evaluate("__sp.overlay()") == "links":
            collector.check(f"{label} {s['id']}")
            page.keyboard.press("Escape")
        else:
            collector.check(f"{label}（リンクなし・知らせ） {s['id']}")


def overlay_checks(page, collector, label):
    """O と ? を、最初と最後のスライドで開いて検査する（開いたあとは Esc で閉じる）。"""
    for edge, key in (("先頭", "Home"), ("末尾", "End")):
        page.keyboard.press(key)
        for opener, name in (("o", "overview"), ("?", "help")):
            page.keyboard.press(opener)
            assert page.evaluate("__sp.overlay()") == name, (label, edge, name)
            collector.check(f"{label} {edge} {name}")
            if name == "overview":
                page.keyboard.press("ArrowDown")           # 選択が動いても（スクロールしても）はみ出さない
                page.keyboard.press("ArrowRight")
                collector.check(f"{label} {edge} {name}（選択を動かした）")
            page.keyboard.press("Escape")
            assert page.evaluate("__sp.overlay()") == "none"


@pytest.mark.parametrize("deck, viewport", DECK_CASES, ids=[f"{d}-{v[0]}x{v[1]}" for d, v in DECK_CASES])
def test_deck_fits(browser, generic_dir, course_dir, deck, viewport):
    url = deck_url(deck, generic_dir, course_dir)
    with layout_session(browser, url, viewport) as page:
        c = Collector(page, viewport)
        # 通常の表示（操作ボタンの帯が出ている）
        assert page.locator(".sp-controls").is_visible()
        walk_deck(page, c, "通常")
        page.keyboard.press("Home")
        page.keyboard.press("ArrowUp")                     # 先頭より前：知らせ（.sp-toast）が出る
        assert page.locator(".sp-toast").count() == 1
        c.check("通常 先頭の知らせ")
        walk_links(page, c, "通常 L")
        overlay_checks(page, c, "通常")
        # N を開いた状態
        page.keyboard.press("n")
        assert page.locator(".sp-notes").count() == 1
        walk_deck(page, c, "N")
        walk_links(page, c, "N L")
        overlay_checks(page, c, "N")
        page.keyboard.press("n")
        assert page.locator(".sp-notes").count() == 0
        c.assert_clean()


@pytest.mark.parametrize("viewport", VIEWPORTS, ids=lambda v: f"{v[0]}x{v[1]}")
@pytest.mark.parametrize("catalog", CATALOGS)
def test_catalog_fits(browser, generic_dir, course_dir, catalog, viewport):
    url = catalog_url(catalog, generic_dir, course_dir)
    with layout_session(browser, url, viewport) as page:
        c = Collector(page, viewport)
        seen = 0
        while True:
            seen += 1
            c.check(f"通常 ページ{seen} {state(page)['id']}")
            before = state(page)["id"]
            page.keyboard.press("Shift+ArrowDown")
            if state(page)["id"] == before:
                break
        assert seen == max(1, page.locator(".sp-pager .sp-pager-btn").count())       # 全ページを見た
        page.keyboard.press("n")                           # デッキだけのキー：何も起きない
        page.keyboard.press("o")
        assert page.evaluate("__sp.overlay()") == "none" and page.locator(".sp-notes, .sp-overview").count() == 0
        c.check("N・O を押したあと")
        page.keyboard.press("Home")
        page.keyboard.press("?")
        assert page.evaluate("__sp.overlay()") == "help"
        c.check("? を開いた")
        page.keyboard.press("Escape")
        assert page.evaluate("__sp.overlay()") == "none"
        c.check("? を閉じたあと")
        c.assert_clean()


# ---- 検査そのものの確かめ（見つけるべきものを見つけ、見つけなくてよいものを見つけない） ----

def checker_problems(browser, body, viewport=(800, 600)):
    with page_session(browser, "about:blank", viewport=viewport) as page:
        page.set_content(f'<!doctype html><html><head><style>html, body {{ margin: 0; }}</style></head><body>{body}</body></html>')
        return layout_problems(page)


def test_checker_finds_scroll_and_overflow(browser):
    out = checker_problems(browser, '<div class="sp-x" style="position:fixed;left:700px;top:10px;width:300px;height:50px"></div>'
                                     '<div style="height:2000px;width:900px"></div>')
    text = "\n".join(out)
    assert "縦にスクロールできる" in text and "横にスクロールできる" in text
    assert "画面の外にはみ出す: div.sp-x" in text
    out = checker_problems(browser, '<div id="stage" style="position:absolute;left:0;top:-5px;width:100px;height:100px"></div>')
    assert any("div#stage" in p for p in out)                       # 舞台も数える
    out = checker_problems(browser, '<div class="sp-y" style="overflow:hidden;width:100px;height:50px"><div style="height:200px"></div></div>')
    assert any("中身が切れている: div.sp-y" in p for p in out)


def test_checker_ignores_what_it_should(browser):
    body = (
        # スクロールできる入れ物の中の長い中身、その中の画面の外
        '<div class="sp-scroll" style="overflow:auto;width:200px;height:100px"><div class="sp-inner" style="height:900px;width:100px"></div></div>'
        # 隠している部品・消している部品
        '<div class="sp-hidden" style="visibility:hidden;position:fixed;left:-500px;top:0;width:10px;height:10px"></div>'
        '<div class="sp-none" style="display:none;position:fixed;left:-500px"></div>'
        # サムネイルの枠と省略記号で切る文字（切れているのが仕様）
        '<div class="sp-thumb-frame" style="overflow:hidden;width:100px;height:50px"><div style="width:400px;height:300px"></div></div>'
        '<div class="sp-caption" style="overflow:hidden;white-space:nowrap;text-overflow:ellipsis;width:50px">とても長い題名の文字がここに入る</div>'
        # 大きさのない層
        '<div class="sp-layer" style="position:fixed;left:0;top:0;width:0;height:0"></div>')
    assert checker_problems(browser, body) == []
