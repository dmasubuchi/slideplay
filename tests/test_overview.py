"""縮小一覧（O）の試験（約束 §2.5）。

見るのは player.js の外から見える動きだけ：画面の要素（.sp-overview・.sp-recent・.sp-section-title・.sp-thumb）、
キー操作、URL、sessionStorage、試験用の窓口 window.__sp。

試験の決め事：
- 操作ボタンは「いつも出す」にして開く（ボタンから開く・焦点を戻す試験のため）
- 「移らなかった」ことの確認だけ、短い待ち（assert_stays）を使う。ほかは、待たずにその場で確かめる
- 矢印キーの動きは、画面に出ている位置（getBoundingClientRect）から試験の側で期待を計算して比べる
"""
import json
from contextlib import contextmanager

import pytest

from helpers import page_session, slides_url

SETTINGS_KEY = "sp-settings-v1"
PLACES_KEY = "sp-places-v1"

# proposal の題名（examples/generic/proposal.html）
TITLES = {
    "p01": "請求業務の効率化のご提案", "p02": "いまの請求業務の課題", "p03": "課題が続いた場合の影響",
    "p03b": "他社の事例（補足）", "p04": "ご提案する仕組み", "p05": "導入の効果", "p06": "費用と補足の資料",
    "p07": "導入後の進め方", "p08": "ご検討をお願いします",
}
SECTION_TITLES = ["現状と課題", "ご提案の内容", "進め方と費用"]


# ---- 試験の道具 ----

def url_of(generic_dir, name="proposal.html", suffix=""):
    return (generic_dir / name).as_uri() + suffix


@contextmanager
def ui_session(browser, url, controls="always", init=None, viewport=(1440, 900)):
    """操作ボタンの出し方を localStorage に入れてから url を開く。pageerror があれば失敗（page_session）。"""
    with page_session(browser, "about:blank", viewport=viewport) as page:
        value = json.dumps({"controls": controls, "notes": False})
        page.add_init_script(f"try {{ localStorage.setItem({json.dumps(SETTINGS_KEY)}, {json.dumps(value)}); }} catch (e) {{}}")
        if init:
            page.add_init_script(init)
        page.goto(url)
        yield page


def where(page):
    s = page.evaluate("__sp.state()")
    return s["id"], s["step"]


def press(page, key):
    page.keyboard.press(key)
    return where(page)


def overlay(page):
    return page.evaluate("__sp.overlay()")


def places(page):
    return page.evaluate("__sp.places()")


def vids(page):
    return [i["vid"] for i in places(page)["items"]]


def toast_text(page):
    el = page.query_selector(".sp-toast")
    return el.inner_text() if el else None


def button(page, label):
    return page.locator(".sp-controls button", has_text=label).first


def assert_stays(page, url):
    """別のページへ移らなかったことの確認（移るなら、この短い間に始まる）。"""
    page.wait_for_timeout(300)
    assert page.url == url


def selected_index(page):
    return page.evaluate("(() => { const s = document.querySelector('.sp-thumb.sp-selected'); return s ? +s.dataset.index : null; })()")


def active_in_overview(page):
    return page.evaluate("!!document.activeElement && !!document.activeElement.closest('.sp-overview')")


def recent_texts(page):
    return page.locator(".sp-recent .sp-recent-item").all_inner_texts()


def recent_item(page, text):
    return page.locator(".sp-recent .sp-recent-item", has_text=text).first


def thumb_rects(page):
    return page.evaluate("""() => Array.from(document.querySelectorAll('.sp-thumb')).map(t => {
        const r = t.getBoundingClientRect();
        return {i: +t.dataset.index, x: r.x, y: r.y, w: r.width, h: r.height};
    })""")


def all_ids(page):
    return page.evaluate("Array.from(document.querySelectorAll('[id]')).map(e => e.id)")


def sp_targets(page):
    return page.evaluate("Array.from(document.querySelectorAll('.sp-target')).map(e => e.id)")


def item_visible(page, root_selector, text):
    """root の中の li（文字が text に一致）が見えているか。"""
    return page.evaluate(
        """([sel, text]) => {
            const li = Array.from(document.querySelector(sel).querySelectorAll('li')).find(e => e.textContent === text);
            if (!li) return null;
            return getComputedStyle(li).visibility === 'visible';
        }""", [root_selector, text])


def seed_places(page, items, pos):
    page.evaluate(f"d => sessionStorage.setItem('{PLACES_KEY}', JSON.stringify(d))", {"v": 1, "items": items, "pos": pos, "restore": None})


def expected_move(rects, cur, key):
    """矢印キーを押したあとの選択（試験の側の期待）。← →：並びの順で1つ前・後。↑ ↓：となりの行の、横の中心が一番近いもの。"""
    if key == "ArrowRight":
        return min(cur + 1, len(rects) - 1)
    if key == "ArrowLeft":
        return max(cur - 1, 0)
    me = rects[cur]
    center = me["x"] + me["w"] / 2
    tops = sorted({round(r["y"]) for r in rects})
    mine = round(me["y"])
    if key == "ArrowDown":
        later = [t for t in tops if t > mine + 4]
        top = min(later) if later else None
    else:
        earlier = [t for t in tops if t < mine - 4]
        top = max(earlier) if earlier else None
    if top is None:
        return cur
    row = [r for r in rects if abs(round(r["y"]) - top) <= 2]
    return min(row, key=lambda r: (abs(r["x"] + r["w"] / 2 - center), r["x"]))["i"]


# ---- 開く・サムネイル ----

def test_open_and_thumbs(browser, generic_dir):
    with ui_session(browser, url_of(generic_dir, suffix="#p03")) as page:
        assert page.query_selector(".sp-overview") is None
        page.keyboard.press("o")
        assert overlay(page) == "overview"
        assert page.locator(".sp-overview .sp-thumb").count() == 9
        assert page.evaluate("Array.from(document.querySelectorAll('.sp-thumb')).map(t => +t.dataset.index)") == list(range(9))
        # 節の見出しは、その節の最初のスライドの前に1つずつ。節のない表紙（p01）の前には出ない
        order = page.evaluate("""Array.from(document.querySelectorAll('.sp-overview .sp-section-title, .sp-overview .sp-thumb'))
            .map(e => e.classList.contains('sp-thumb') ? +e.dataset.index : e.textContent)""")
        assert order == [0, SECTION_TITLES[0], 1, 2, 3, SECTION_TITLES[1], 4, 5, SECTION_TITLES[2], 6, 7, 8]
        # 今のスライド（p03 = 2）に枠。最初の選択もそこで、焦点もそこにある
        assert page.locator(".sp-current").count() == 1
        assert page.locator(".sp-current").get_attribute("data-index") == "2"
        assert selected_index(page) == 2
        assert page.evaluate("document.activeElement.dataset.index") == "2"
        # 各サムネイルに、番号と題名の見出しが付く（読み上げ用の名前にも同じものが入る）
        for i, title in enumerate(TITLES.values()):
            thumb = page.locator(f'.sp-thumb[data-index="{i}"]')
            assert title in thumb.locator(".sp-thumb-caption").inner_text()
            assert title in thumb.get_attribute("aria-label") and f"{i + 1}" in thumb.get_attribute("aria-label")


def test_thumb_geometry(browser, generic_dir):
    # 描画先は 1920×1080 のまま transform で縮め、サムネイルの枠の中に収まる
    with ui_session(browser, url_of(generic_dir)) as page:
        page.keyboard.press("o")
        info = page.evaluate("""() => Array.from(document.querySelectorAll('.sp-thumb')).map(t => {
            const tg = t.querySelector('.sp-target');
            const r = tg.getBoundingClientRect(), box = t.getBoundingClientRect();
            return {w: tg.offsetWidth, h: tg.offsetHeight, transform: getComputedStyle(tg).transform,
                    rw: r.width, rh: r.height, inside: r.left >= box.left - 0.5 && r.top >= box.top - 0.5 && r.right <= box.right + 0.5 && r.bottom <= box.bottom + 0.5,
                    n: t.querySelectorAll('.sp-target').length, ownId: tg.id};
        })""")
        assert len(info) == 9
        for t in info:
            assert (t["w"], t["h"]) == (1920, 1080) and t["n"] == 1 and t["ownId"] == ""
            assert t["transform"].startswith("matrix(")
            assert 100 < t["rw"] < 400 and t["rw"] / t["rh"] == pytest.approx(1920 / 1080, abs=0.01)
            assert t["inside"]
        assert len(sp_targets(page)) == 10                         # #stage と、サムネイルの9つ


def test_thumbs_last_step(browser, generic_dir):
    # p05 は段階3で初めて見える項目がある。サムネイルには最後の段階で出る（メインの舞台は段階0のまま）
    last = "浮いた時間で、支払の分析に取り組めます"
    with ui_session(browser, url_of(generic_dir, suffix="#p05")) as page:
        assert item_visible(page, "#stage", last) is False
        page.keyboard.press("o")
        assert item_visible(page, '.sp-thumb[data-index="5"]', last) is True
        assert item_visible(page, '.sp-thumb[data-index="1"]', "入力の誤りの確認に、毎月2日かかっている") is True   # p02 の段階2
        assert item_visible(page, "#stage", last) is False        # メインの舞台は変わらない
        assert where(page) == ("p05", 0)


def test_render_calls(browser, generic_dir):
    # 描くのは slideDeck.render(i, 最後の段階, サムネイルの描画先) だけ。メインの舞台には描かない
    with ui_session(browser, url_of(generic_dir, suffix="#p05")) as page:
        page.evaluate("""() => {
            window.__calls = [];
            const orig = slideDeck.render;
            slideDeck.render = function (ref, step, target) {
                window.__calls.push({ref, step, main: target === document.getElementById('stage'), isTarget: target.classList.contains('sp-target')});
                return orig.call(this, ref, step, target);
            };
        }""")
        stage_html = page.evaluate("document.getElementById('stage').innerHTML")
        page.keyboard.press("o")
        calls = page.evaluate("__calls")
        steps = page.evaluate("slideDeck.info.slides.map(s => s.steps)")
        assert [c["ref"] for c in calls] == list(range(9))
        assert [c["step"] for c in calls] == steps and max(steps) == 3
        assert not any(c["main"] for c in calls) and all(c["isTarget"] for c in calls)
        page.keyboard.press("Escape")
        assert len(page.evaluate("__calls")) == 9                  # 閉じても描かない
        assert page.evaluate("document.getElementById('stage').innerHTML") == stage_html


def test_thumb_render_error_is_contained(browser, generic_dir):
    # 1枚の描画が例外を出しても、一覧は開き、ほかのサムネイルは描かれる
    with ui_session(browser, url_of(generic_dir)) as page:
        page.evaluate("""() => {
            const orig = slideDeck.render;
            slideDeck.render = function (ref, step, target) {
                if (ref === 3 && target.id !== 'stage') throw new Error('壊れたスライド');
                return orig.call(this, ref, step, target);
            };
        }""")
        page.keyboard.press("o")
        assert overlay(page) == "overview"
        assert page.locator(".sp-thumb").count() == 9
        assert page.locator('.sp-thumb[data-index="4"] li').count() > 0


def test_no_sections_no_headings(browser, generic_dir):
    with ui_session(browser, url_of(generic_dir, "minimal.html")) as page:
        page.keyboard.press("o")
        assert page.locator(".sp-thumb").count() == 1
        assert page.locator(".sp-section-title").count() == 0
        assert page.locator(".sp-current").get_attribute("data-index") == "0"
        page.keyboard.press("Enter")
        assert overlay(page) == "none" and where(page) == ("m1", 0)


def test_not_in_render_mode(browser, generic_dir):
    with page_session(browser, url_of(generic_dir) + "?render") as page:
        page.keyboard.press("o")
        assert page.query_selector(".sp-overview") is None


# ---- 開く・閉じる ----

def test_open_close_ways(browser, generic_dir):
    with ui_session(browser, url_of(generic_dir, suffix="#p02")) as page:
        assert overlay(page) == "none"
        page.keyboard.press("o")                                   # O で開き、O で閉じる
        assert overlay(page) == "overview"
        page.keyboard.press("o")
        assert overlay(page) == "none" and page.query_selector(".sp-overview") is None
        page.keyboard.press("O")                                   # 大文字（CapsLock）でも
        assert overlay(page) == "overview"
        page.keyboard.press("Shift+O")
        assert overlay(page) == "none"
        button(page, "O 一覧").click()                             # ボタンで開く
        assert overlay(page) == "overview"
        page.locator(".sp-overview button", has_text="閉じる").click()
        assert overlay(page) == "none"
        page.keyboard.press("o")                                   # Esc で閉じる
        page.keyboard.press("Escape")
        assert overlay(page) == "none"
        assert where(page) == ("p02", 0) and len(places(page)["items"]) == 1


def test_background_click_closes(browser, generic_dir):
    with ui_session(browser, url_of(generic_dir)) as page:
        page.keyboard.press("o")
        page.locator(".sp-overview-panel").click(position={"x": 5, "y": 5})   # 中の余白では閉じない
        assert overlay(page) == "overview"
        page.mouse.click(5, 5)                                     # 背景では閉じる
        assert overlay(page) == "none"


@pytest.mark.parametrize("closer", ["Escape", "o", "close-button", "backdrop", "enter-on-thumb"])
def test_removed_on_close(browser, generic_dir, closer):
    with ui_session(browser, url_of(generic_dir, suffix="#p03")) as page:
        page.keyboard.press("o")
        assert len(sp_targets(page)) == 10
        if closer == "close-button":
            page.locator(".sp-overview button", has_text="閉じる").click()
        elif closer == "backdrop":
            page.mouse.click(5, 5)
        else:
            page.keyboard.press({"enter-on-thumb": "Enter"}.get(closer, closer))
        assert page.query_selector(".sp-overview") is None
        assert page.query_selector(".sp-thumb") is None
        assert sp_targets(page) == ["stage"]                       # 描画先は #stage の1つだけ
        ids = all_ids(page)
        assert len(ids) == len(set(ids))
        assert overlay(page) == "none"


def test_closes_when_location_changes_under_it(browser, generic_dir):
    # 開いている間にブラウザの戻る・進む・hash の変更で場所が変わったら、一覧は閉じて、その場所を出す
    with ui_session(browser, url_of(generic_dir, suffix="#p02")) as page:
        page.keyboard.press("o")
        page.evaluate("location.hash = '#p05'")
        page.wait_for_function("__sp.overlay() === 'none'")
        assert where(page) == ("p05", 0)
        assert sp_targets(page) == ["stage"]


# ---- 選ぶ ----

def test_select_by_keys(browser, generic_dir):
    with ui_session(browser, url_of(generic_dir, suffix="#p01")) as page:
        page.keyboard.press("o")
        assert selected_index(page) == 0
        page.keyboard.press("ArrowRight")
        page.keyboard.press("ArrowRight")
        assert selected_index(page) == 2
        assert where(page) == ("p01", 0) and len(places(page)["items"]) == 1   # 選んだだけでは移らない
        page.keyboard.press("Enter")
        assert where(page) == ("p03", 0)                           # 2枚先のスライドの段階0
        assert overlay(page) == "none" and page.query_selector(".sp-overview") is None
        assert page.url.endswith("#p03")
        assert len(places(page)["items"]) == 2 and places(page)["pos"] == 1   # 新しい場所として足される


@pytest.mark.parametrize("bed", ["proposal", "course"])
def test_arrow_keys_follow_rendered_position(browser, generic_dir, course_dir, bed):
    url = url_of(generic_dir) if bed == "proposal" else slides_url(course_dir, 1, render=False)
    keys = (["ArrowDown"] * 7 + ["ArrowUp"] * 9 + ["ArrowRight"] * 4 + ["ArrowDown", "ArrowDown", "ArrowLeft", "ArrowUp", "ArrowRight", "ArrowDown",
            "ArrowDown", "ArrowDown", "ArrowRight", "ArrowUp", "ArrowUp", "ArrowLeft", "ArrowLeft", "ArrowLeft", "ArrowDown"] * 3)
    with ui_session(browser, url) as page:
        page.keyboard.press("o")
        cur = selected_index(page)
        visited = {cur}
        for key in keys:
            rects = thumb_rects(page)
            want = expected_move(rects, cur, key)
            page.keyboard.press(key)
            cur = selected_index(page)
            assert cur == want, (key, want, cur)
            assert page.evaluate("document.activeElement.dataset.index") == str(cur)   # 焦点も選択についていく
            visited.add(cur)
        assert len(visited) >= 5                                   # 動きが本当に起きている
        assert where(page) == (page.evaluate("slideDeck.info.slides[0].id"), 0)
        assert len(places(page)["items"]) == 1                     # 矢印では場所が増えない


def test_arrows_wrap_rows_in_reading_order(browser, course_dir):
    # 1つの節が何行かになるとき、→ で行の終わりから次の行の先頭へ、← で逆に
    with ui_session(browser, slides_url(course_dir, 1, render=False), viewport=(900, 700)) as page:
        page.keyboard.press("o")
        rects = thumb_rects(page)
        tops = {}
        for r in rects:
            tops.setdefault(round(r["y"]), []).append(r["i"])
        wide = next(row for row in tops.values() if len(row) >= 2 and row[-1] + 1 < len(rects) and (row[-1] + 1) not in row)
        end = wide[-1]
        for _ in range(end):
            page.keyboard.press("ArrowRight")
        assert selected_index(page) == end
        page.keyboard.press("ArrowRight")
        assert selected_index(page) == end + 1
        page.keyboard.press("ArrowLeft")
        assert selected_index(page) == end


def test_click_thumb(browser, generic_dir):
    with ui_session(browser, url_of(generic_dir, suffix="#p01")) as page:
        page.keyboard.press("o")
        page.locator('.sp-thumb[data-index="6"]').click()
        assert where(page) == ("p06", 0)
        assert overlay(page) == "none" and sp_targets(page) == ["stage"]
        assert page.url.endswith("#p06")
        assert [i["ref"] for i in places(page)["items"]] == ["p01", "p06"]


def test_open_thumb_goes_to_step_zero(browser, generic_dir):
    # 同じスライドの段階の途中から選ぶと、段階0へ。場所は足さず、今の場所を書き換える
    with ui_session(browser, url_of(generic_dir, suffix="#p05.2")) as page:
        assert where(page) == ("p05", 2)
        page.keyboard.press("o")
        assert selected_index(page) == 5
        page.keyboard.press("Enter")
        assert where(page) == ("p05", 0)
        items = places(page)["items"]
        assert [(i["ref"], i["step"]) for i in items] == [("p05", 0)]
        assert page.url.endswith("#p05")


def test_enter_goes_to_step_zero_of_other_slide_from_middle_step(browser, generic_dir):
    with ui_session(browser, url_of(generic_dir, suffix="#p02")) as page:
        press(page, "ArrowDown")
        press(page, "ArrowDown")
        assert where(page) == ("p02", 2)
        page.keyboard.press("o")
        page.keyboard.press("ArrowRight")                          # p03 へ（p02 の段階2のままの選択ではない）
        page.keyboard.press("Enter")
        assert where(page) == ("p03", 0)
        assert [(i["ref"], i["step"]) for i in places(page)["items"]] == [("p02", 2), ("p03", 0)]


# ---- 直近の場所の列 ----

def test_recent_row(browser, generic_dir):
    # 3か所を移ったあと：新しい順に3件。2番目を選ぶと、そこへ移り、件数は変わらない
    with ui_session(browser, url_of(generic_dir, suffix="#p01")) as page:
        press(page, "Shift+ArrowDown")
        press(page, "Shift+ArrowDown")
        assert where(page) == ("p03", 0)
        before = vids(page)
        assert len(before) == 3
        page.keyboard.press("o")
        assert recent_texts(page) == [TITLES["p03"], TITLES["p02"], TITLES["p01"]]
        assert page.locator(".sp-recent .sp-recent-item").evaluate_all("els => els.map(e => e.dataset.vid)") == before[::-1]
        recent_item(page, TITLES["p02"]).click()
        assert where(page) == ("p02", 0)
        assert overlay(page) == "none" and sp_targets(page) == ["stage"]
        assert page.url.endswith("#p02")
        after = places(page)
        assert [i["vid"] for i in after["items"]] == before        # 並びは変わらない
        assert after["pos"] == 1
        assert page.evaluate("history.state.spVid") == before[1]
        # ←→ はこの並びのとおりに動く
        assert press(page, "ArrowRight") == ("p03", 0)
        assert press(page, "ArrowLeft") == ("p02", 0)
        assert press(page, "ArrowLeft") == ("p01", 0)


def test_recent_marks_current(browser, generic_dir):
    with ui_session(browser, url_of(generic_dir, suffix="#p01")) as page:
        press(page, "Shift+ArrowDown")
        press(page, "Shift+ArrowDown")
        press(page, "ArrowLeft")                                   # 今の位置は2番目（p02）
        page.keyboard.press("o")
        marks = page.locator(".sp-recent .sp-recent-item").evaluate_all("els => els.map(e => e.classList.contains('sp-recent-now'))")
        assert marks == [False, True, False]
        current = page.locator(".sp-recent .sp-recent-now")
        assert current.count() == 1 and current.get_attribute("aria-current") == "true"
        assert page.locator(".sp-current").count() == 1            # .sp-current はサムネイルの枠だけ
        assert page.locator(".sp-thumb.sp-current").get_attribute("data-index") == "1"
        # 先に進んだ場所も残っている：1番目（p03）を選べる
        recent_item(page, TITLES["p03"]).click()
        assert where(page) == ("p03", 0) and places(page)["pos"] == 2


def test_recent_max_ten(browser, generic_dir):
    with ui_session(browser, url_of(generic_dir, suffix="#p01")) as page:
        for _ in range(7):
            press(page, "Shift+ArrowDown")                         # 8か所
        for _ in range(4):
            press(page, "Shift+ArrowUp")                           # 12か所になるところを、10か所で止める
        assert len(places(page)["items"]) == 10
        page.keyboard.press("o")
        assert page.locator(".sp-recent .sp-recent-item").count() == 10


def test_recent_labels(browser, generic_dir):
    # 同じデッキ：スライドの題名。別のページ：「ページ名：ID」。目次：「目次：デッキの ID」
    P, M, C = url_of(generic_dir), url_of(generic_dir, "minimal.html"), url_of(generic_dir, "index.html")
    with ui_session(browser, M + "#m1") as page:
        page.goto(P + "#p02")                                      # 別のページの場所 m1 ができる
        stored = page.evaluate(f"JSON.parse(sessionStorage.getItem('{PLACES_KEY}'))")
        catalog = {"vid": "catalogvid001", "page": C, "kind": "catalog", "ref": "proposal", "step": 0}
        seed_places(page, [catalog] + stored["items"], stored["pos"] + 1)
        page.reload()                                              # 保存した並びを読み直す（今の場所は state の識別子で合う）
        assert [i["ref"] for i in places(page)["items"]] == ["proposal", "m1", "p02"] and places(page)["pos"] == 2
        page.keyboard.press("o")
        assert recent_texts(page) == [TITLES["p02"], "minimal：m1", "目次：proposal"]


def test_recent_labels_use_folder_for_slides_and_index(browser, course_dir):
    # 別のページの場所のラベル：ファイル名（拡張子なし）。ただしファイル名が slides・index のときは、1つ上のフォルダー名
    root = course_dir.resolve().as_uri()
    here = slides_url(course_dir, 2, render=False)
    with ui_session(browser, here + "#s05") as page:
        stored = page.evaluate(f"JSON.parse(sessionStorage.getItem('{PLACES_KEY}'))")
        other = lambda n, page_url, ref: {"vid": f"labelvid{n:04d}", "page": page_url, "kind": "deck", "ref": ref, "step": 0}
        seeded = [
            other(1, f"{root}/ch-03/slides.html", "s12"),          # slides → フォルダー名
            other(2, f"{root}/ch-04/index.html", "s03"),           # index → フォルダー名
            other(3, f"{root}/ch-05/talk.html", "s01"),            # ほかのファイル名はそのまま
            other(4, f"{root}/%E7%AC%AC%202%E7%AB%A0/slides.html", "a1"),     # パーセント表記は戻す
            other(5, "file:///slides.html", "s01"),                # 上のフォルダーがなければ、ファイル名のまま
            {"vid": "labelvid0006", "page": f"{root}/index.html", "kind": "catalog", "ref": "ch-02", "step": 0},      # 目次は「目次：ID」
        ]
        seed_places(page, seeded + stored["items"], stored["pos"] + len(seeded))
        page.reload()
        page.keyboard.press("o")
        assert recent_texts(page)[1:] == ["目次：ch-02", "slides：s01", "第 2章：a1", "talk：s01", "ch-04：s03", "ch-03：s12"]


def test_recent_labels_never_show_the_full_path_when_decoding_fails(browser, course_dir):
    # 復号できない % を含む名前でも、元の URL（手元のフルパス）は出さない。末尾のファイル名・フォルダー名だけを、生の文字列のまま出す
    root = course_dir.resolve().as_uri()
    here = slides_url(course_dir, 2, render=False)
    with ui_session(browser, here + "#s05") as page:
        stored = page.evaluate(f"JSON.parse(sessionStorage.getItem('{PLACES_KEY}'))")
        other = lambda n, page_url, ref: {"vid": f"pctvid{n:05d}", "page": page_url, "kind": "deck", "ref": ref, "step": 0}
        seeded = [
            other(1, f"{root}/100%/slides.html", "s01"),            # フォルダーが復号できない
            other(2, f"{root}/ch-03/50%.html", "s02"),              # ファイル名が復号できない
            other(3, f"{root}/%E0%A4%A/index.html", "s03"),         # 壊れたパーセント表記のフォルダー
        ]
        seed_places(page, seeded + stored["items"], stored["pos"] + len(seeded))
        page.reload()
        page.keyboard.press("o")
        texts = recent_texts(page)
        assert texts[1:] == ["%E0%A4%A：s03", "50%：s02", "100%：s01"], texts
        assert not any("file:" in t or "/" in t for t in texts[1:])


def test_recent_label_for_unknown_slide_uses_id(browser, generic_dir):
    # このページの場所だが、デッキにその ID がもうない：ID をそのまま出す
    P = url_of(generic_dir)
    with ui_session(browser, P + "#p02") as page:
        stored = page.evaluate(f"JSON.parse(sessionStorage.getItem('{PLACES_KEY}'))")
        ghost = {"vid": "ghostvid0001", "page": P, "kind": "deck", "ref": "p77", "step": 0}
        seed_places(page, [ghost] + stored["items"], stored["pos"] + 1)
        page.reload()
        page.keyboard.press("o")
        assert recent_texts(page) == [TITLES["p02"], "p77"]


def test_cross_page_recent_choice(browser, generic_dir):
    # 別のページの場所を選ぶ：←→ と同じに、復元先を保存してからそのページへ移る。並びは変わらない
    P, M = url_of(generic_dir), url_of(generic_dir, "minimal.html")
    with ui_session(browser, P + "#p05.2") as page:
        page.goto(M + "#m1")
        ids = vids(page)
        assert [i["ref"] for i in places(page)["items"]] == ["p05", "m1"]
        page.keyboard.press("o")
        assert recent_texts(page) == ["最小の見本", "proposal：p05"]
        with page.expect_navigation():
            recent_item(page, "proposal：p05").click()
        page.wait_for_function("!!window.__sp")
        assert page.url == P + "#p05.2"                            # 離れたときの段階
        assert where(page) == ("p05", 2)
        assert vids(page) == ids and places(page)["pos"] == 0
        assert page.evaluate("history.state.spVid") == ids[0]
        assert page.evaluate(f"JSON.parse(sessionStorage.getItem('{PLACES_KEY}')).restore") is None   # 使った復元先は消える


@pytest.mark.parametrize("how", ["write-fails", "read-fails"])
def test_cross_page_recent_refused_without_storage(browser, generic_dir, how):
    # 保存領域が使えないとき、別のページの場所は選べない（知らせて、そのまま）。同じページの場所は選べる
    P, M = url_of(generic_dir), url_of(generic_dir, "minimal.html")
    with ui_session(browser, M + "#m1") as page:
        page.goto(P + "#p02")
        if how == "write-fails":
            page.evaluate("() => { Storage.prototype.setItem = function () { throw new DOMException('満杯', 'QuotaExceededError'); }; }")
        else:
            page.evaluate("() => { Storage.prototype.getItem = function () { throw new DOMException('拒否', 'SecurityError'); }; }")
        page.goto(P + "#p03")                                      # hash だけ違う：同じ文書の中の移動（着いたときの処理が走る）
        assert [i["ref"] for i in places(page)["items"]] == ["m1", "p02", "p03"]
        page.keyboard.press("o")
        assert recent_texts(page) == [TITLES["p03"], TITLES["p02"], "minimal：m1"]
        length = page.evaluate("history.length")
        recent_item(page, "minimal：m1").click()
        text = toast_text(page)
        assert text and "別のページ" in text
        assert overlay(page) == "overview"                         # 一覧は開いたまま：ほかの場所を選べる
        assert_stays(page, P + "#p03")
        assert page.evaluate("history.length") == length
        assert places(page)["pos"] == 2 and where(page) == ("p03", 0)
        recent_item(page, TITLES["p02"]).click()                   # 同じページの場所は選べる
        assert where(page) == ("p02", 0) and overlay(page) == "none"
        assert places(page)["pos"] == 1 and len(places(page)["items"]) == 3


# ---- 一覧が開いている間のキー ----

def test_left_right_do_not_move_places_while_open(browser, generic_dir):
    with ui_session(browser, url_of(generic_dir, suffix="#p02")) as page:
        press(page, "Shift+ArrowDown")
        press(page, "Shift+ArrowDown")
        assert where(page) == ("p03b", 0)
        page.keyboard.press("o")
        before = (where(page), places(page), page.url)
        assert selected_index(page) == 3
        page.keyboard.press("ArrowLeft")                           # 一覧の中の選択が動くだけ
        assert selected_index(page) == 2
        page.keyboard.press("ArrowRight")
        page.keyboard.press("ArrowRight")
        assert selected_index(page) == 4
        assert (where(page), places(page), page.url) == before
        assert toast_text(page) is None
        page.keyboard.press("Escape")
        assert press(page, "ArrowLeft") == ("p03", 0)              # 閉じれば ←→ は直近の場所へ


def test_other_keys_do_not_move_slide_while_open(browser, generic_dir):
    with ui_session(browser, url_of(generic_dir, suffix="#p02")) as page:
        page.keyboard.press("o")
        before = (where(page), places(page), page.url)
        for key in ["Space", "PageDown", "PageUp", "End", "Home", "h", "l", "a", "Shift+ArrowDown", "Shift+ArrowUp"]:
            page.keyboard.press(key)
            assert overlay(page) == "overview", key
            assert (where(page), places(page), page.url) == before, key
        assert toast_text(page) is None


def test_help_over_overview(browser, generic_dir):
    # 一覧の上に操作の一覧を開ける。閉じると一覧に戻り、焦点も一覧の中に戻る
    with ui_session(browser, url_of(generic_dir, suffix="#p03")) as page:
        page.keyboard.press("o")
        page.keyboard.press("?")
        assert overlay(page) == "help"
        assert page.query_selector(".sp-overview") is not None
        page.keyboard.press("Escape")
        assert overlay(page) == "overview"
        assert active_in_overview(page)
        assert page.evaluate("document.activeElement.dataset.index") == "2"
        page.keyboard.press("Escape")
        assert overlay(page) == "none"


def test_notes_toggle_while_open(browser, generic_dir):
    with ui_session(browser, url_of(generic_dir)) as page:
        page.keyboard.press("o")
        page.keyboard.press("n")
        assert page.query_selector(".sp-notes") is not None and overlay(page) == "overview"
        page.keyboard.press("Escape")                              # 一覧だけが閉じる
        assert overlay(page) == "none" and page.query_selector(".sp-notes") is not None


# ---- 焦点（Tab の閉じ込め、閉じたときの戻し）と、ボタン ----

def test_tab_stays_inside(browser, generic_dir):
    with ui_session(browser, url_of(generic_dir)) as page:
        page.keyboard.press("o")
        seen = set()
        for key in ["Tab"] * 15 + ["Shift+Tab"] * 15:
            page.keyboard.press(key)
            assert active_in_overview(page), key
            seen.add(page.evaluate("document.activeElement.outerHTML.slice(0, 80)"))
        assert len(seen) >= 3                                      # 巡っている（閉じる、直近の場所、選択中のサムネイル）
        assert page.evaluate("document.activeElement.closest('.sp-controls')") is None


def test_tab_visits_recent_items_and_selected_thumb_only(browser, generic_dir):
    with ui_session(browser, url_of(generic_dir, suffix="#p03")) as page:
        press(page, "Shift+ArrowDown")
        page.keyboard.press("o")
        kinds = []
        for _ in range(8):
            page.keyboard.press("Tab")
            kinds.append(page.evaluate("""(() => { const a = document.activeElement;
                return a.closest('.sp-recent-item') ? 'recent' : a.closest('.sp-thumb') ? 'thumb:' + a.dataset.index : a.textContent; })()"""))
        thumbs = [k for k in kinds if k.startswith("thumb")]
        assert set(thumbs) == {"thumb:3"}                          # 全部のサムネイルを巡らない（選択中の1つだけ）
        assert "recent" in kinds and "閉じる" in kinds


def test_focus_returns_after_close(browser, generic_dir):
    with ui_session(browser, url_of(generic_dir, suffix="#p02")) as page:
        # 焦点がボタンにあるときに開くと、閉じたとき、そのボタンに戻る
        button(page, "O 一覧").focus()
        page.keyboard.press("o")
        assert active_in_overview(page)
        page.keyboard.press("Escape")
        assert page.evaluate("document.activeElement.textContent") == "O 一覧"
        # キーボードでボタンを押して開いた場合も同じ
        page.keyboard.press("Enter")
        assert overlay(page) == "overview" and active_in_overview(page)
        page.keyboard.press("o")
        assert page.evaluate("document.activeElement.textContent") == "O 一覧"
        # 操作の一覧（?）も同じ
        button(page, "?").focus()
        page.keyboard.press("?")
        assert overlay(page) == "help"
        page.keyboard.press("Escape")
        assert page.evaluate("document.activeElement.getAttribute('aria-label')") == "操作の一覧"
        # 何にも焦点がないときに開けば、閉じても何にも当たらない
        page.evaluate("document.activeElement.blur()")
        page.keyboard.press("o")
        page.keyboard.press("Escape")
        assert page.evaluate("document.activeElement === document.body")
        assert press(page, "ArrowDown") == ("p02", 1)              # 閉じたあとのキー操作も効く


def test_focus_returns_after_choosing(browser, generic_dir):
    # 選んで移ったあとも、開く前の焦点に戻す（消えた要素に焦点が残らない）
    with ui_session(browser, url_of(generic_dir, suffix="#p02")) as page:
        button(page, "O 一覧").focus()
        page.keyboard.press("Enter")
        page.keyboard.press("ArrowRight")
        page.keyboard.press("Enter")
        assert where(page) == ("p03", 0)
        assert page.evaluate("document.activeElement.textContent") == "O 一覧"


def test_enter_and_space_on_player_buttons_in_overview(browser, generic_dir):
    # 一覧の中のプレイヤーのボタン（直近の場所の項目・閉じる）は、焦点が乗っていれば Enter・Space でそのボタン自身が押される。
    # 選択中のサムネイルを開くことはしない（isOwnButton は sp-btn の class で見る）
    with ui_session(browser, url_of(generic_dir, suffix="#p01")) as page:
        press(page, "Shift+ArrowDown")
        press(page, "Shift+ArrowDown")
        page.keyboard.press("o")
        assert selected_index(page) == 2
        recent_item(page, TITLES["p02"]).focus()
        page.keyboard.press("Enter")
        assert where(page) == ("p02", 0) and overlay(page) == "none"
        page.keyboard.press("o")
        recent_item(page, TITLES["p01"]).focus()
        page.keyboard.press("Space")
        assert where(page) == ("p01", 0) and overlay(page) == "none"
        assert len(places(page)["items"]) == 3                     # 選び直しで場所は増えない
        # 閉じるボタン
        page.keyboard.press("o")
        page.keyboard.press("ArrowRight")
        page.keyboard.press("ArrowRight")
        assert selected_index(page) == 2
        page.locator(".sp-overview button", has_text="閉じる").focus()
        page.keyboard.press("Enter")
        assert overlay(page) == "none" and where(page) == ("p01", 0)


# ---- 描画先が変わっても同じ見た目（約束 §2.5） ----

# 描画先の中の、文字を直接持つ要素の文字の見た目（色・字体・大きさ・行の高さ）を、文書の順に集める
TEXT_STYLES = """(root) => {
    const out = [];
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT);
    for (let e = walker.currentNode; e; e = walker.nextNode()) {
        if (/^(SCRIPT|STYLE)$/.test(e.tagName)) continue;
        const own = Array.from(e.childNodes).filter(n => n.nodeType === 3).map(n => n.textContent.trim()).join('');
        if (!own) continue;
        const cs = getComputedStyle(e);
        out.push([e.tagName, own.slice(0, 24), cs.color, cs.fontFamily, cs.fontSize, cs.lineHeight]);
    }
    return out;
}"""


def bed_url(request, bed):
    if bed == "course":
        return slides_url(request.getfixturevalue("course_dir"), 3, render=False)
    return url_of(request.getfixturevalue("generic_dir"))


@pytest.mark.parametrize("bed", ["course", "proposal"])
def test_thumbs_look_like_the_main_stage(browser, request, bed):
    # 一覧の外側（.sp-overview・パネル・枠）の文字の色・字体を、中身の中へ継がせない：
    # 同じスライドの最後の段階を、サムネイルと #stage で比べて、文字の見た目が同じ
    with ui_session(browser, bed_url(request, bed)) as page:
        slides = page.evaluate("slideDeck.info.slides.map(s => [s.id, s.steps])")
        main = []
        for slide_id, steps in slides:
            page.evaluate("h => { location.hash = h; }", f"#{slide_id}.{steps}")
            page.wait_for_function("([id, step]) => __sp.state().id === id && __sp.state().step === step", arg=[slide_id, steps])
            main.append(page.evaluate(TEXT_STYLES, page.query_selector("#stage")))
        page.keyboard.press("o")
        assert page.locator(".sp-thumb").count() == len(slides)
        total = 0
        for i, (slide_id, _) in enumerate(slides):
            thumb = page.evaluate(TEXT_STYLES, page.query_selector(f'.sp-thumb[data-index="{i}"] .sp-target'))
            assert thumb == main[i], slide_id
            total += len(thumb)
        assert total >= len(slides)                                # 比べた要素がある（空の比較で通らない）
        # 文字の色が、一覧の文字の色（パネルの明るい色）になっていない
        panel_color = page.evaluate("getComputedStyle(document.querySelector('.sp-overview-panel')).color")
        thumb_colors = {t[2] for i in range(len(slides)) for t in main[i]}
        assert thumb_colors != {panel_color}


# ---- ページのスクロール ----

@pytest.mark.parametrize("viewport", [(1440, 900), (820, 600)])
def test_no_page_scroll(browser, course_dir, viewport):
    with ui_session(browser, slides_url(course_dir, 1, render=False), viewport=viewport) as page:
        page.keyboard.press("o")
        count = page.locator(".sp-thumb").count()
        assert count >= 20
        scroll = "({h: document.scrollingElement.scrollHeight, w: document.scrollingElement.scrollWidth, top: document.scrollingElement.scrollTop})"
        s = page.evaluate(scroll)
        assert s["h"] <= viewport[1] and s["w"] <= viewport[0] and s["top"] == 0
        # 一覧の中だけがスクロールする
        panel = page.evaluate("""(() => { const p = document.querySelector('.sp-overview-panel'); const r = p.getBoundingClientRect();
            return {sh: p.scrollHeight, ch: p.clientHeight, x: r.x, y: r.y, right: r.right, bottom: r.bottom}; })()""")
        assert panel["sh"] > panel["ch"]
        assert panel["x"] >= 0 and panel["y"] >= 0 and panel["right"] <= viewport[0] and panel["bottom"] <= viewport[1]
        page.evaluate("document.querySelector('.sp-overview-panel').scrollTop = 400")
        assert page.evaluate("document.querySelector('.sp-overview-panel').scrollTop") > 0
        # 選択を動かして一覧が追いかけても、ページはスクロールしない
        for _ in range(count - 1):
            page.keyboard.press("ArrowRight")
        assert page.locator(".sp-thumb.sp-selected").get_attribute("data-index") == str(count - 1)
        s = page.evaluate(scroll)
        assert s["h"] <= viewport[1] and s["top"] == 0
        # 選択中のサムネイルが一覧の見える範囲に入っている
        inside = page.evaluate("""(() => { const p = document.querySelector('.sp-overview-panel').getBoundingClientRect();
            const t = document.querySelector('.sp-thumb.sp-selected').getBoundingClientRect(); return t.top >= p.top - 1 && t.bottom <= p.bottom + 1; })()""")
        assert inside


@pytest.mark.parametrize("viewport", [(1440, 900), (820, 1180), (640, 300)])
def test_fits_viewport(browser, generic_dir, viewport):
    with ui_session(browser, url_of(generic_dir), viewport=viewport) as page:
        press(page, "Shift+ArrowDown")
        press(page, "Shift+ArrowDown")
        page.keyboard.press("o")
        r = page.evaluate("(() => { const r = document.querySelector('.sp-overview-panel').getBoundingClientRect(); return [r.x, r.y, r.right, r.bottom]; })()")
        assert r[0] >= 0 and r[1] >= 0 and r[2] <= viewport[0] and r[3] <= viewport[1]
        s = page.evaluate("({w: document.scrollingElement.scrollWidth, h: document.scrollingElement.scrollHeight})")
        assert s["w"] <= viewport[0] and s["h"] <= viewport[1]
