"""目次（window.slideCatalog）の試験（約束 §4）。

見るのは player.js の外から見える動きだけ：画面の要素（.sp-catalog・.sp-card・.sp-pager）、キー操作、URL、
sessionStorage、試験用の窓口 window.__sp。

試験台：
- 汎用の目次 examples/generic/index.html（proposal・minimal と、kind "page" の handout.html の3枚）
- 講座の形の見本の目次（course_dir。conftest.py が作る。ch-01〜ch-07 の7枚。各章は ch-NN/slides.html）

試験の決め事：
- 1ページのカードの数は、幅 1200px 以上で3、760px 以上で2、それより狭いと1（820 幅は2枚）
- カードは全部 DOM にあり、今のページにないカードは hidden。「見えているカード」は :not([hidden])
- 「移らなかった」ことの確認だけ、短い待ち（stays）を使う。ほかは、移動の完了を待つ
"""
import json
import re
from pathlib import Path

import pytest

from helpers import page_session, slides_url

PLACES_KEY = "sp-places-v1"
PLAYER_JS = Path(__file__).resolve().parents[1] / "player" / "player.js"
COURSE_IDS = [f"ch-{n:02d}" for n in range(1, 8)]
GENERIC_IDS = ["proposal", "minimal", "handout"]

# hashchange が起きた回数（同じ文書の中の移動の完了を待つため。プレイヤーより先に登録される）
COUNT_HASHCHANGE = "window.__hc = 0; addEventListener('hashchange', () => { window.__hc++; });"
# history.replaceState の呼ばれた回数（hash を書き換えた回数）を数える
COUNT_REPLACE = """
window.__rs = [];
(() => { const orig = history.replaceState; history.replaceState = function (...a) { window.__rs.push(String(a[2])); return orig.apply(this, a); }; })();
"""


# ---- 試験の道具 ----

def url_of(directory, name="index.html", suffix=""):
    return (Path(directory) / name).as_uri() + suffix


def write_catalog(tmp_path, catalog, name="index.html", style=""):
    """一時フォルダーに目次のページを作る（player.js は元の場所の絶対パスで読む）。style：ページ自身の CSS（<style> の中身）。"""
    payload = json.dumps(catalog, ensure_ascii=False).replace("<", "\\u003c")
    html = (f'<!doctype html><html lang="ja"><head><meta charset="utf-8"><title>t</title>'
            + (f'<style>{style}</style>' if style else '') + '</head><body>'
            f'<script>window.slideCatalog = {payload};</script>'
            f'<script src="{PLAYER_JS.as_uri()}"></script></body></html>')
    path = tmp_path / name
    path.write_text(html, encoding="utf-8")
    return path.as_uri()


def state(page):
    return page.evaluate("__sp.state()")


def selected(page):
    return page.evaluate("(() => { const s = document.querySelectorAll('.sp-card.sp-selected'); "
                         "return s.length === 1 ? s[0].dataset.id : s.length; })()")


def visible_ids(page):
    return page.evaluate("Array.from(document.querySelectorAll('.sp-card:not([hidden])'), c => c.dataset.id)")


def all_ids(page):
    return page.evaluate("Array.from(document.querySelectorAll('.sp-card'), c => c.dataset.id)")


def pager_labels(page):
    return page.evaluate("Array.from(document.querySelectorAll('.sp-pager .sp-pager-btn'), b => b.textContent)")


def current_pager(page):
    return page.evaluate("Array.from(document.querySelectorAll('.sp-pager .sp-pager-btn[aria-current=\"page\"]'), b => b.textContent)")


def places(page):
    return page.evaluate("__sp.places()")


def toast_text(page):
    el = page.query_selector(".sp-toast")
    return el.inner_text() if el else None


def hash_of(page):
    return page.evaluate("location.hash")


def stays(page, url):
    """別のページへ移らなかったことの確認（移るなら、この短い間に始まる）。"""
    page.wait_for_timeout(300)
    assert page.url == url


def navigate(page, action, player=True):
    """action による別のページへの移動を待ち、移った先でプレイヤーが動き出すまで待つ（player=False：プレイヤーのないページ）。

    待つのは hash を除いた URL が変わる移動だけ（目次の選択の hash の書き換え（replaceState）は、Playwright には移動に見える）。"""
    before = page.url.split("#")[0]
    with page.expect_navigation(url=lambda u: u.split("#")[0] != before):
        action()
    if player:
        page.wait_for_function("!!window.__sp")


def clear_toast(page):
    """出ている知らせを消す（次の知らせだけを見るため）。"""
    page.evaluate("(() => { const t = document.querySelector('.sp-toast'); if (t) t.remove(); })()")


def wait_per_page(page, n):
    """幅の変更（resize）が反映されて、見えているカードが n 枚になるまで待つ。"""
    page.wait_for_function(f"document.querySelectorAll('.sp-card:not([hidden])').length === {n}")


def press_n(page, key, n):
    for _ in range(n):
        page.keyboard.press(key)


# ---- 汎用の目次：カードと、キー・マウス ----

def test_generic_catalog_cards(browser, generic_dir):
    with page_session(browser, url_of(generic_dir)) as page:
        assert page.locator(".sp-catalog").count() == 1
        assert page.locator(".sp-catalog-title").inner_text() == "汎用の見本"
        assert page.locator(".sp-catalog-lead").inner_text() == "商談の提案書など、講座でない中身の見本"
        assert all_ids(page) == GENERIC_IDS and visible_ids(page) == GENERIC_IDS
        assert page.evaluate("Array.from(document.querySelectorAll('.sp-card'), c => c.dataset.kind)") == ["deck", "deck", "page"]
        # デッキ：label・title・items・meta。page：title だけ
        deck = page.locator('.sp-card[data-id="proposal"]')
        assert deck.locator(".sp-card-label").inner_text() == "提案書"
        assert deck.locator(".sp-card-title").inner_text() == "請求業務の効率化のご提案"
        assert deck.locator(".sp-card-items li").all_inner_texts() == ["現状と課題", "ご提案の内容", "進め方と費用"]
        assert deck.locator(".sp-card-meta").inner_text() == "9枚・約16分"
        minimal = page.locator('.sp-card[data-id="minimal"]')
        assert minimal.locator(".sp-card-title").inner_text() == "最小の見本" and minimal.locator(".sp-card-label").count() == 0
        assert minimal.locator(".sp-card-items").count() == 0 and minimal.locator(".sp-card-meta").inner_text() == "1枚"
        handout = page.locator('.sp-card[data-id="handout"]')
        assert handout.inner_text().strip() == "配布用の資料" and handout.locator(".sp-card-title").inner_text() == "配布用の資料"
        # 3枚で1ページ：切り替えのボタンはいらない
        assert page.locator(".sp-pager .sp-pager-btn").count() == 0
        # 最初のカードを選んでいる。試験用の窓口
        assert selected(page) == "proposal" and hash_of(page) == "#proposal"
        assert state(page) == {"kind": "catalog", "index": 0, "step": 0, "id": "proposal"}
        assert page.evaluate("__sp.overlay()") == "none"
        # header・main・footer を使わず、クラス名は sp- で始まる
        assert page.locator(".sp-catalog header, .sp-catalog main, .sp-catalog footer").count() == 0
        assert page.evaluate("Array.from(document.querySelectorAll('.sp-catalog, .sp-catalog *')).every(e => "
                             "Array.from(e.classList).every(c => c.startsWith('sp-')))")


def test_catalog_text_is_not_html(browser, tmp_path):
    cat = {"contract": 1, "title": "<img src=x onerror=\"window.__x=1\">題", "lead": "<b>lead</b>",
           "decks": [{"id": "a", "href": "a.html", "label": "<i>L</i>", "title": "<img src=x onerror=\"window.__x=2\">",
                      "items": ["<b>x</b>"], "meta": "<u>m</u>"}]}
    with page_session(browser, write_catalog(tmp_path, cat)) as page:
        assert page.locator(".sp-catalog-title").text_content() == cat["title"]
        assert page.locator(".sp-catalog-lead").text_content() == "<b>lead</b>"
        assert page.locator(".sp-card-title").text_content() == cat["decks"][0]["title"]
        assert page.locator(".sp-card-items li").text_content() == "<b>x</b>"
        assert page.locator(".sp-card-label").text_content() == "<i>L</i>" and page.locator(".sp-card-meta").text_content() == "<u>m</u>"
        assert page.locator(".sp-catalog img, .sp-catalog b, .sp-catalog i, .sp-catalog u").count() == 0
        assert page.evaluate("window.__x") is None


def test_malformed_catalog_entries(browser, tmp_path):
    # null・同じ ID・ID のないもの・ID の形が違うものがあっても、描ける。場所に使う ID はいつも一意で、形が正しい。色は読めるものだけ使う
    cat = {"contract": 1, "title": "t", "decks": [
        None, "x", {"id": "a", "href": "a.html", "title": "A"}, {"id": "a", "href": "b.html", "title": "重複"},
        {"href": "c.html", "title": "ID なし"}, {"id": "1bad", "href": "d.html", "title": "形が違う", "color": "red;background:url(x)"},
        {"id": "ok", "href": "e.html", "title": "色あり", "color": "#0b6bcb"}]}
    with page_session(browser, write_catalog(tmp_path, cat)) as page:
        ids = all_ids(page)
        assert len(ids) == 5 and len(set(ids)) == 5 and ids[0] == "a" and ids[-1] == "ok"
        assert all(re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", i) for i in ids)
        assert page.locator(".sp-card-title").all_inner_texts() == ["A", "重複", "ID なし", "形が違う", "色あり"]
        assert page.evaluate("document.querySelectorAll('.sp-card')[3].style.getPropertyValue('--c')") == ""
        assert page.evaluate("document.querySelectorAll('.sp-card')[4].style.getPropertyValue('--c')") == "#0b6bcb"
        assert page.evaluate("document.querySelector('.sp-catalog').innerHTML.includes('url(x)')") is False
        # 選んだ場所は、保存できる形の ID で残り、再読み込みでも同じカードを選ぶ（ID のないカードも）
        for n, key in enumerate(["ArrowDown", "ArrowDown", "ArrowDown", "ArrowDown"], start=1):
            page.keyboard.press(key)
            chosen = selected(page)
            assert chosen == ids[n] and places(page)["items"][0]["ref"] == chosen and hash_of(page) == "#" + chosen
            page.reload()
            page.wait_for_function("!!window.__sp")
            assert selected(page) == chosen and len(places(page)["items"]) == 1


def test_catalog_without_cards_does_nothing(browser, tmp_path):
    with page_session(browser, write_catalog(tmp_path, {"contract": 1, "title": "空", "decks": []})) as page:
        assert page.locator(".sp-card").count() == 0
        page.keyboard.press("ArrowDown")
        page.keyboard.press("1")
        assert page.evaluate("document.querySelectorAll('.sp-toast').length") == 0


def test_keys_select_and_open(browser, generic_dir):
    url = url_of(generic_dir)
    with page_session(browser, url) as page:
        assert selected(page) == "proposal"
        page.keyboard.press("ArrowDown")                           # minimal を選ぶ
        assert selected(page) == "minimal" and state(page)["index"] == 1 and state(page)["id"] == "minimal"
        assert hash_of(page) == "#minimal"
        assert page.url == url + "#minimal"
        navigate(page, lambda: page.keyboard.press("Enter"))
        assert page.url == url_of(generic_dir, "minimal.html", "#m1")     # 開いたデッキは、先頭のスライドに着く
        assert state(page)["kind"] == "deck" and state(page)["id"] == "m1"


def test_arrows_walk_all_cards_and_stop_at_ends(browser, generic_dir):
    with page_session(browser, url_of(generic_dir)) as page:
        page.keyboard.press("ArrowUp")                             # 先頭より前はない：動かず、知らせる
        assert selected(page) == "proposal" and toast_text(page) and "最初" in toast_text(page)
        clear_toast(page)
        page.keyboard.press("ArrowDown")
        assert selected(page) == "minimal"
        page.keyboard.press("ArrowDown")
        assert selected(page) == "handout" and toast_text(page) is None
        page.keyboard.press("ArrowDown")                           # 末尾より先はない
        assert selected(page) == "handout" and "最後" in toast_text(page)
        assert state(page)["index"] == 2
        page.keyboard.press("ArrowUp")
        assert selected(page) == "minimal"


def test_selection_changes_current_place_only(browser, generic_dir):
    # 目次の場所は kind "catalog"・ref は選んでいるカードの ID・step 0。選択だけの変化は今の場所の書き換え（場所は増えない）
    url = url_of(generic_dir)
    with page_session(browser, "about:blank") as page:
        page.add_init_script(COUNT_REPLACE)
        page.goto(url)
        first = places(page)
        assert len(first["items"]) == 1 and first["pos"] == 0
        item = first["items"][0]
        assert (item["kind"], item["ref"], item["step"], item["page"]) == ("catalog", "proposal", 0, url)
        base = len(page.evaluate("__rs"))
        length = page.evaluate("history.length")
        page.keyboard.press("ArrowDown")
        page.keyboard.press("ArrowDown")
        now = places(page)
        assert len(now["items"]) == 1 and now["pos"] == 0
        assert now["items"][0]["vid"] == item["vid"] and now["items"][0]["ref"] == "handout" and now["items"][0]["step"] == 0
        assert page.evaluate("history.length") == length
        assert page.evaluate("__rs.slice(%d)" % base) == [url + "#minimal", url + "#handout"]    # 変わるたびに1回ずつ
        assert page.evaluate("history.state.spVid") == item["vid"]
        page.keyboard.press("ArrowDown")                           # 端：動かない。hash も書き換えない
        assert len(page.evaluate("__rs")) == base + 2
        # 保存した並びの中でも同じ
        stored = json.loads(page.evaluate(f"sessionStorage.getItem('{PLACES_KEY}')"))
        assert [(i["kind"], i["ref"], i["step"]) for i in stored["items"]] == [("catalog", "handout", 0)]


def test_hover_selects_and_click_opens(browser, generic_dir):
    url = url_of(generic_dir)
    with page_session(browser, url) as page:
        page.locator('.sp-card[data-id="minimal"]').hover()
        assert selected(page) == "minimal" and hash_of(page) == "#minimal"
        assert state(page)["id"] == "minimal"
        assert len(places(page)["items"]) == 1 and places(page)["items"][0]["ref"] == "minimal"
        page.locator('.sp-card[data-id="handout"]').hover()
        assert selected(page) == "handout"
        navigate(page, lambda: page.locator('.sp-card[data-id="minimal"]').click())
        assert page.url == url_of(generic_dir, "minimal.html", "#m1")


def test_hover_does_not_follow_a_still_pointer(browser, generic_dir):
    # ↓ でカードが入れ替わっても、止まっているマウスの下のカードには移らない（マウスを動かしたときだけ選ぶ）。
    # 実際のブラウザは、レイアウトが変わると止まったマウスの下で mouseenter を起こすことがある（この試験の Chromium では起きない）。
    # プレイヤーは座標が変わった mousemove だけで選ぶ。ここで確かめるのは、動かしたら（同じカードの中でも）選ぶこと
    with page_session(browser, url_of(generic_dir), viewport=(900, 800)) as page:       # 2枚で1ページ
        assert visible_ids(page) == ["proposal", "minimal"]
        box = page.locator('.sp-card[data-id="proposal"]').bounding_box()
        page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        assert selected(page) == "proposal"
        press_n(page, "ArrowDown", 2)                              # handout：次のページ（1枚だけ。同じ列の位置にある）
        assert selected(page) == "handout" and visible_ids(page) == ["handout"]
        page.keyboard.press("ArrowUp")                             # minimal：前のページ。マウスの下は proposal になる
        assert selected(page) == "minimal" and visible_ids(page) == ["proposal", "minimal"]
        page.wait_for_timeout(100)
        assert selected(page) == "minimal"                         # 止まったままのマウスでは、proposal に戻らない
        page.mouse.move(box["x"] + box["width"] / 2 + 3, box["y"] + box["height"] / 2)
        assert selected(page) == "proposal"                        # 動かしたら選ぶ


def test_digit_keys(browser, generic_dir):
    url = url_of(generic_dir)
    with page_session(browser, url) as page:
        navigate(page, lambda: page.keyboard.press("1"))           # 1：proposal
        assert page.url == url_of(generic_dir, "proposal.html", "#p01")
    with page_session(browser, url) as page:
        page.keyboard.press("5")                                   # 3つしかない：何もしない（知らせも出ない）
        page.keyboard.press("9")
        page.keyboard.press("0")
        stays(page, url + "#proposal")
        assert toast_text(page) is None and selected(page) == "proposal" and len(places(page)["items"]) == 1
    with page_session(browser, url) as page:
        navigate(page, lambda: page.keyboard.press("3"), player=False)     # 3：kind "page" のカードも、同じに開く（hash を足さない）
        assert page.url == url_of(generic_dir, "handout.html")


def test_digit_key_selects_before_leaving(browser, generic_dir):
    # 数字で開くと、そのカードを選んでから開く：← で戻ったとき、開いたカードが選ばれている
    url = url_of(generic_dir)
    with page_session(browser, url) as page:
        navigate(page, lambda: page.keyboard.press("2"))
        assert page.url == url_of(generic_dir, "minimal.html", "#m1")
        navigate(page, lambda: page.keyboard.press("ArrowLeft"))
        assert page.url == url + "#minimal" and selected(page) == "minimal"


def test_open_clears_restore(browser, generic_dir):
    # 開く前に、残っている復元先を消す。消さないと、開いた先のページが復元先の場所を使ってしまう
    url = url_of(generic_dir)
    with page_session(browser, url) as page:
        kept = "keptvid00001"
        page.evaluate(f"""(() => {{
          const d = JSON.parse(sessionStorage.getItem('{PLACES_KEY}'));
          d.items.push({{vid: '{kept}', page: {json.dumps(url_of(generic_dir, "proposal.html"))}, kind: 'deck', ref: 'p05', step: 2}});
          d.restore = {{vid: '{kept}', t: Date.now()}};
          sessionStorage.setItem('{PLACES_KEY}', JSON.stringify(d));
        }})()""")
        navigate(page, lambda: page.keyboard.press("Enter"))      # proposal を開く（選択は変えない）
        assert page.url == url_of(generic_dir, "proposal.html", "#p01")
        items = places(page)["items"]
        assert [i["ref"] for i in items] == ["proposal", "p01"] and items[1]["vid"] != kept     # 復元先の p05 ではなく、先頭に着いた
        assert json.loads(page.evaluate(f"sessionStorage.getItem('{PLACES_KEY}')"))["restore"] is None


def test_open_with_unsafe_href_does_nothing(browser, tmp_path):
    cat = {"contract": 1, "title": "t", "decks": [
        {"id": "bad", "href": "javascript:window.__x=1", "title": "危ない"},
        {"id": "data", "href": "data:text/html,x", "title": "data"},
        {"id": "none", "title": "href なし"}]}
    url = write_catalog(tmp_path, cat)
    with page_session(browser, url) as page:
        for i, card in enumerate(["bad", "data", "none"]):
            page.locator(f'.sp-card[data-id="{card}"]').click()    # クリックで開こうとする
            assert selected(page) == card and "開けません" in toast_text(page)
            page.evaluate("document.querySelector('.sp-toast').remove()")
            page.keyboard.press("Enter")                           # Enter でも同じ
            assert "開けません" in toast_text(page)
            page.evaluate("document.querySelector('.sp-toast').remove()")
        page.keyboard.press("1")
        assert "開けません" in toast_text(page)
        stays(page, url + "#bad")
        assert page.evaluate("window.__x") is None


def test_left_right_walk_places(browser, generic_dir):
    # ←→ は直近の場所（デッキの中と同じ動き）。← は先頭で動かず知らせる。先の場所がないときの → は ↓ と同じ（次のカードを選ぶ）
    url = url_of(generic_dir)
    with page_session(browser, url) as page:
        page.keyboard.press("ArrowLeft")
        assert toast_text(page) == "これより前の場所はありません"
        assert selected(page) == "proposal"
        page.evaluate("document.querySelector('.sp-toast').remove()")
        page.keyboard.press("ArrowRight")
        assert selected(page) == "minimal" and hash_of(page) == "#minimal"
        assert toast_text(page) is None                            # 「これより先の場所はありません」は出ない
        page.keyboard.press("Shift+ArrowLeft")                     # Shift は使わない
        page.keyboard.press("Shift+ArrowRight")
        assert selected(page) == "minimal" and toast_text(page) is None


def test_right_without_next_place_is_same_as_down(browser, generic_dir):
    # 開いたばかりの目次で → を押し続ける＝別に開いた同じ目次で ↓ を押し続ける。選び・hash・知らせ・直近の場所の並びが毎回一致する
    def walk(key):
        with page_session(browser, url_of(generic_dir)) as page:
            trace = []
            for _ in range(5):                                     # 3枚のカードを順に選び、最後のカードで2回押す
                page.keyboard.press(key)
                p = places(page)
                trace.append((selected(page), hash_of(page), toast_text(page), [(i["ref"], i["step"]) for i in p["items"]], p["pos"]))
            return trace

    by_down = walk("ArrowDown")
    assert [t[0] for t in by_down] == ["minimal", "handout", "handout", "handout", "handout"]
    assert [t[2] for t in by_down] == [None, None] + ["最後のカードです"] * 3
    assert by_down[-1][3:] == ([("handout", 0)], 0)               # カードを選ぶだけなので場所は1つのまま、選びに合わせて書き換わる
    assert walk("ArrowRight") == by_down                           # 最後のカードでも、→ は ↓ と同じ動き・知らせ（「これより先の場所はありません」ではない）


def test_modifier_keys_and_typing_are_ignored(browser, generic_dir):
    url = url_of(generic_dir)
    with page_session(browser, url) as page:
        page.keyboard.press("Control+ArrowDown")
        page.keyboard.press("Meta+1")
        page.keyboard.press("Alt+ArrowDown")
        assert selected(page) == "proposal"
        page.evaluate("document.body.appendChild(Object.assign(document.createElement('input'), {id: 'box'}))")
        page.focus("#box")
        page.keyboard.press("ArrowDown")
        page.keyboard.press("2")
        assert selected(page) == "proposal" and page.input_value("#box") == "2"
        stays(page, url + "#proposal")


# ---- 操作の一覧（?）----

HELP_ROWS = "Array.from(document.querySelectorAll('.sp-help-row'), r => [Array.from(r.querySelectorAll('.sp-key'), k => k.textContent), r.querySelector('.sp-help-text').textContent])"


def test_catalog_help_opens_and_closes(browser, generic_dir):
    # 目次にも「?」の操作の一覧がある（デッキと同じ共通の重なり）。? で開閉、Esc で閉じる、焦点が選んでいたカードへ戻る
    with page_session(browser, url_of(generic_dir)) as page:
        assert page.evaluate("__sp.overlay()") == "none"
        page.keyboard.press("?")
        assert page.evaluate("__sp.overlay()") == "help" and page.locator(".sp-help").count() == 1
        assert page.locator(".sp-help").get_attribute("role") == "dialog"
        assert page.locator(".sp-help-title").inner_text() == "操作の一覧"
        page.keyboard.press("?")                                   # もう一度で閉じる
        assert page.evaluate("__sp.overlay()") == "none" and page.locator(".sp-help").count() == 0
        page.keyboard.press("ArrowDown")
        page.keyboard.press("?")
        assert page.evaluate("document.activeElement.closest('.sp-help') !== null")
        page.keyboard.press("Escape")
        assert page.evaluate("__sp.overlay()") == "none"
        assert page.evaluate("document.activeElement.dataset.id") == "minimal"       # 開く前に焦点があったカード
        page.keyboard.press("Escape")                              # 何も開いていない Esc は何もしない
        assert selected(page) == "minimal" and toast_text(page) is None


def test_catalog_help_lists_catalog_keys_only(browser, generic_dir):
    with page_session(browser, url_of(generic_dir)) as page:
        page.keyboard.press("?")
        rows = page.evaluate(HELP_ROWS)
        keys = [k for ks, _ in rows for k in ks]
        for expected in ["↑", "↓", "Shift＋↑", "Shift＋↓", "Enter", "1〜9", "←", "→", "?", "Esc"]:
            assert expected in keys, expected
        for absent in ["N", "O", "L", "H", "F", "Home", "End", "PageDown", "Space"]:      # デッキだけのキー
            assert absent not in keys, absent
        assert page.locator(".sp-help button", has_text="いつも出す").count() == 0      # 操作ボタンはない
        assert all(text for _, text in rows)
        assert "?" in page.locator(".sp-catalog-hint").inner_text()                   # 下の案内にも「?」が出ている


def test_catalog_help_is_modal(browser, generic_dir):
    url = url_of(generic_dir)
    with page_session(browser, url) as page:
        page.keyboard.press("ArrowDown")
        page.keyboard.press("?")
        before = (selected(page), hash_of(page), places(page))
        for key in ["ArrowDown", "ArrowUp", "Shift+ArrowDown", "ArrowLeft", "ArrowRight", "Enter", "1", "2", "9"]:
            page.keyboard.press(key)
            assert page.evaluate("__sp.overlay()") == "help", key
            assert (selected(page), hash_of(page), places(page)) == before, key
        stays(page, url + "#minimal")
        # Tab は一覧の中だけを巡る
        seen = set()
        for _ in range(4):
            page.keyboard.press("Tab")
            seen.add(page.evaluate("!!document.activeElement.closest('.sp-help')"))
        assert seen == {True}
        page.keyboard.press("Escape")
        page.keyboard.press("ArrowDown")                           # 閉じれば、また動く
        assert selected(page) == "handout"


def test_catalog_help_close_button_and_backdrop(browser, generic_dir):
    with page_session(browser, url_of(generic_dir)) as page:
        page.keyboard.press("?")
        page.locator(".sp-help button", has_text="閉じる").click()
        assert page.evaluate("__sp.overlay()") == "none"
        page.keyboard.press("?")
        page.mouse.click(5, 5)                                     # 背景を押すと閉じる
        assert page.evaluate("__sp.overlay()") == "none"


@pytest.mark.parametrize("viewport", [(1440, 900), (820, 1180), (640, 300)])
def test_catalog_help_fits_screen(browser, generic_dir, viewport):
    with page_session(browser, url_of(generic_dir), viewport=viewport) as page:
        page.keyboard.press("?")
        r = page.evaluate("""() => { const p = document.querySelector('.sp-help-panel').getBoundingClientRect();
            return {l: p.left, t: p.top, r: p.right, b: p.bottom, iw: innerWidth, ih: innerHeight,
                    scroll: [document.documentElement.scrollWidth - innerWidth, document.documentElement.scrollHeight - innerHeight]}; }""")
        assert r["l"] >= 0 and r["t"] >= 0 and r["r"] <= r["iw"] and r["b"] <= r["ih"] and r["scroll"] == [0, 0]


def test_catalog_help_is_ignored_with_modifiers_and_typing(browser, generic_dir):
    with page_session(browser, url_of(generic_dir)) as page:
        page.keyboard.press("Control+?")
        page.keyboard.press("Meta+?")
        assert page.evaluate("__sp.overlay()") == "none"
        page.evaluate("document.body.appendChild(Object.assign(document.createElement('input'), {id: 'box'}))")
        page.focus("#box")
        page.keyboard.press("?")
        assert page.evaluate("__sp.overlay()") == "none" and page.input_value("#box") == "?"


# ---- page のカード：items・meta があれば出す ----

def card_text(page, card_id):
    return page.evaluate("""id => { const c = document.querySelector(`.sp-card[data-id="${id}"]`);
        return {items: Array.from(c.querySelectorAll('.sp-card-items li'), li => li.textContent),
                meta: Array.from(c.querySelectorAll('.sp-card-meta'), m => m.textContent),
                label: c.querySelectorAll('.sp-card-label').length, title: c.querySelector('.sp-card-title').textContent}; }""", card_id)


def test_page_card_items_and_meta_are_optional(browser, tmp_path):
    cat = {"contract": 1, "title": "t", "decks": [
        {"id": "p-both", "kind": "page", "href": "a.pdf", "title": "両方", "items": ["一", "二"], "meta": "A4 1枚"},
        {"id": "p-items", "kind": "page", "href": "b.pdf", "title": "項目だけ", "items": ["一"]},
        {"id": "p-meta", "kind": "page", "href": "c.pdf", "title": "補足だけ", "meta": "PDF"},
        {"id": "p-bare", "kind": "page", "href": "d.pdf", "title": "題だけ", "label": "出さない", "items": [], "meta": ""},
    ]}
    with page_session(browser, write_catalog(tmp_path, cat), viewport=(1920, 1080)) as page:
        page.keyboard.press("Shift+ArrowDown")                     # 4 枚は 2 ページ（3 + 1）
        assert card_text(page, "p-both") == {"items": ["一", "二"], "meta": ["A4 1枚"], "label": 0, "title": "両方"}
        assert card_text(page, "p-items") == {"items": ["一"], "meta": [], "label": 0, "title": "項目だけ"}
        assert card_text(page, "p-meta") == {"items": [], "meta": ["PDF"], "label": 0, "title": "補足だけ"}
        assert card_text(page, "p-bare") == {"items": [], "meta": [], "label": 0, "title": "題だけ"}      # label は出さない
        assert page.evaluate("Array.from(document.querySelectorAll('.sp-card[data-kind=\"page\"]'), c => c.dataset.id)") == \
            ["p-both", "p-items", "p-meta", "p-bare"]


def test_page_card_without_details_stays_centered(browser, tmp_path):
    # items・meta のない page は、これまでどおり題を縦の中央に出す。あるものは上から並べる
    cat = {"contract": 1, "title": "t", "decks": [
        {"id": "p-bare", "kind": "page", "href": "d.pdf", "title": "題だけ"},
        {"id": "p-meta", "kind": "page", "href": "c.pdf", "title": "補足だけ", "meta": "PDF"}]}
    with page_session(browser, write_catalog(tmp_path, cat)) as page:
        r = page.evaluate("""() => Array.from(document.querySelectorAll('.sp-card'), c => {
            const card = c.getBoundingClientRect(), t = c.querySelector('.sp-card-title').getBoundingClientRect();
            return {top: t.top - card.top, bottom: card.bottom - t.bottom}; })""")
        assert abs(r[0]["top"] - r[0]["bottom"]) < 12                # 中央
        assert r[1]["top"] < 60 and r[1]["bottom"] > 80             # 上寄せ（補足は下）


# ---- ページの切り替え ----

def test_paging_by_width(browser, course_dir):
    url = url_of(course_dir)
    with page_session(browser, url, viewport=(1440, 900)) as page:
        assert all_ids(page) == COURSE_IDS
        assert visible_ids(page) == COURSE_IDS[:3]
        assert pager_labels(page) == ["1〜3", "4〜6", "7"] and current_pager(page) == ["1〜3"]
        page.keyboard.press("Shift+ArrowDown")                     # 次のページの最初のカード
        assert visible_ids(page) == COURSE_IDS[3:6] and selected(page) == "ch-04"
        assert current_pager(page) == ["4〜6"] and hash_of(page) == "#ch-04"
        page.keyboard.press("Shift+ArrowDown")
        assert visible_ids(page) == COURSE_IDS[6:] and selected(page) == "ch-07" and current_pager(page) == ["7"]
        page.keyboard.press("Shift+ArrowDown")                     # 最後のページ：動かず、知らせる
        assert selected(page) == "ch-07" and "最後" in toast_text(page)
        page.keyboard.press("Shift+ArrowUp")
        assert selected(page) == "ch-04" and visible_ids(page) == COURSE_IDS[3:6]
        page.keyboard.press("Shift+ArrowUp")
        assert selected(page) == "ch-01"
        page.keyboard.press("Shift+ArrowUp")
        assert selected(page) == "ch-01" and "最初" in toast_text(page)
    with page_session(browser, url, viewport=(1000, 700)) as page:
        assert visible_ids(page) == COURSE_IDS[:2] and len(pager_labels(page)) == 4
        assert pager_labels(page) == ["1〜2", "3〜4", "5〜6", "7"]
        page.keyboard.press("Shift+ArrowDown")
        assert visible_ids(page) == COURSE_IDS[2:4] and selected(page) == "ch-03"
    with page_session(browser, url, viewport=(820, 1180)) as page:     # 820 は 760 以上：2枚
        assert visible_ids(page) == COURSE_IDS[:2] and len(pager_labels(page)) == 4
    with page_session(browser, url, viewport=(700, 900)) as page:
        assert visible_ids(page) == COURSE_IDS[:1] and len(pager_labels(page)) == 7
        assert pager_labels(page) == ["1", "2", "3", "4", "5", "6", "7"]
        page.keyboard.press("Shift+ArrowDown")
        assert visible_ids(page) == ["ch-02"] and selected(page) == "ch-02"


@pytest.mark.parametrize("width,per_page", [(1200, 3), (1199, 2), (760, 2), (759, 1), (320, 1), (1920, 3)])
def test_cards_per_page_thresholds(browser, course_dir, width, per_page):
    with page_session(browser, url_of(course_dir), viewport=(width, 900)) as page:
        assert len(visible_ids(page)) == per_page


def test_arrows_cross_pages(browser, course_dir):
    # ↑↓ は順に選ぶ。選んだカードのあるページへ切り替わる
    with page_session(browser, url_of(course_dir)) as page:
        press_n(page, "ArrowDown", 2)
        assert selected(page) == "ch-03" and visible_ids(page) == COURSE_IDS[:3]
        page.keyboard.press("ArrowDown")                           # 4枚目：次のページ
        assert selected(page) == "ch-04" and visible_ids(page) == COURSE_IDS[3:6] and current_pager(page) == ["4〜6"]
        page.keyboard.press("ArrowUp")                             # 戻る：前のページ
        assert selected(page) == "ch-03" and visible_ids(page) == COURSE_IDS[:3] and current_pager(page) == ["1〜3"]
        assert len(places(page)["items"]) == 1                     # 選択だけの変化：場所は増えない


def test_pager_buttons(browser, course_dir):
    with page_session(browser, url_of(course_dir)) as page:
        page.locator(".sp-pager-btn", has_text="4〜6").click()     # そのページの最初のカードを選ぶ
        assert visible_ids(page) == COURSE_IDS[3:6] and selected(page) == "ch-04" and hash_of(page) == "#ch-04"
        assert places(page)["items"][0]["ref"] == "ch-04" and len(places(page)["items"]) == 1
        assert current_pager(page) == ["4〜6"]
        page.locator(".sp-pager-btn", has_text="7").click()
        assert selected(page) == "ch-07" and visible_ids(page) == ["ch-07"]


def test_pager_button_enter_does_not_open_card(browser, course_dir):
    # キーボードで押したボタンの Enter は、そのボタンを押す（選んでいるカードを開かない）
    url = url_of(course_dir)
    with page_session(browser, url) as page:
        page.locator(".sp-pager-btn", has_text="4〜6").focus()
        page.keyboard.press("Enter")
        assert selected(page) == "ch-04" and visible_ids(page) == COURSE_IDS[3:6]
        stays(page, url + "#ch-04")


def test_resize_keeps_selection_visible(browser, course_dir):
    with page_session(browser, url_of(course_dir), viewport=(1440, 900)) as page:
        press_n(page, "ArrowDown", 4)
        assert selected(page) == "ch-05" and visible_ids(page) == COURSE_IDS[3:6]
        page.set_viewport_size({"width": 1000, "height": 700})     # 2枚：ch-05 は3ページ目の最初
        wait_per_page(page, 2)
        assert visible_ids(page) == COURSE_IDS[4:6] and selected(page) == "ch-05" and len(pager_labels(page)) == 4
        assert current_pager(page) == ["5〜6"]
        page.set_viewport_size({"width": 700, "height": 900})      # 1枚
        wait_per_page(page, 1)
        assert visible_ids(page) == ["ch-05"] and len(pager_labels(page)) == 7
        page.set_viewport_size({"width": 1440, "height": 900})
        wait_per_page(page, 3)
        assert visible_ids(page) == COURSE_IDS[3:6] and selected(page) == "ch-05" and len(pager_labels(page)) == 3
        assert len(places(page)["items"]) == 1 and places(page)["items"][0]["ref"] == "ch-05"


# ---- hash ----

@pytest.mark.parametrize("bad", ["#nope", "#proposal.2", "#3", "#%E0%A4%A", "#proposal%20", "#__"])
def test_bad_hash(browser, generic_dir, bad):
    # 読めない・ない ID：最初のカードを選び、知らせる。hash は選んだカードの ID に直る
    url = url_of(generic_dir)
    with page_session(browser, url + bad) as page:
        assert selected(page) == "proposal" and state(page)["index"] == 0
        assert toast_text(page) and "最初のカード" in toast_text(page)
        assert hash_of(page) == "#proposal"
        assert len(places(page)["items"]) == 1 and places(page)["items"][0]["ref"] == "proposal"


def test_good_hash_selects_card(browser, course_dir):
    url = url_of(course_dir)
    with page_session(browser, url + "#ch-05") as page:
        assert selected(page) == "ch-05" and visible_ids(page) == COURSE_IDS[3:6]
        assert toast_text(page) is None and hash_of(page) == "#ch-05"
        assert places(page)["items"][0]["ref"] == "ch-05"
        page.reload()                                              # 再読み込みでも同じ
        page.wait_for_function("!!window.__sp")
        assert selected(page) == "ch-05" and len(places(page)["items"]) == 1
    with page_session(browser, url + "#ch-07") as page:
        assert selected(page) == "ch-07" and visible_ids(page) == ["ch-07"]


def test_hash_changes_follow(browser, generic_dir):
    # アドレス欄で hash だけを変える・ブラウザの戻る：その hash のカードを選ぶ（保存した選択より hash が先）
    url = url_of(generic_dir)
    with page_session(browser, "about:blank") as page:
        page.add_init_script(COUNT_HASHCHANGE)
        page.goto(url)
        assert selected(page) == "proposal"
        page.goto(url + "#minimal")                                # 同じ文書の中の移動
        page.wait_for_function("__hc > 0")
        assert selected(page) == "minimal" and state(page)["id"] == "minimal" and hash_of(page) == "#minimal"
        page.evaluate("location.hash = '#handout'")
        page.wait_for_function("__hc > 1")
        assert selected(page) == "handout" and [i["ref"] for i in places(page)["items"]] == ["proposal", "minimal", "handout"]
        page.go_back()
        page.wait_for_function("__hc > 2")
        assert selected(page) == "minimal" and hash_of(page) == "#minimal"
        assert [i["ref"] for i in places(page)["items"]] == ["proposal", "minimal", "handout"] and places(page)["pos"] == 1   # 場所は増えない


def test_catalog_works_without_storage(browser, generic_dir):
    # 保存領域が使えなくても、目次は表示・選択・開くことができる。別のページへの ←→ は端と同じ知らせ
    url = url_of(generic_dir)
    broken = "Storage.prototype.getItem = Storage.prototype.setItem = function () { throw new DOMException('拒否', 'SecurityError'); };"
    with page_session(browser, "about:blank") as page:
        page.add_init_script(broken)
        page.goto(url)
        assert selected(page) == "proposal" and visible_ids(page) == GENERIC_IDS
        page.keyboard.press("ArrowDown")
        assert selected(page) == "minimal" and hash_of(page) == "#minimal"
        page.keyboard.press("ArrowLeft")
        assert toast_text(page) == "これより前の場所はありません"
        navigate(page, lambda: page.keyboard.press("Enter"))
        assert page.url == url_of(generic_dir, "minimal.html", "#m1")


# ---- デッキとの往復（講座の形の見本） ----

def test_h_round_trip(browser, course_dir):
    # 目次で第2章を選んで開く → 5枚目まで進む → H → 目次で第2章が選ばれている
    with page_session(browser, url_of(course_dir)) as page:
        page.keyboard.press("ArrowDown")
        assert selected(page) == "ch-02"
        navigate(page, lambda: page.keyboard.press("Enter"))
        assert page.url.startswith(slides_url(course_dir, 2, render=False)) and state(page)["kind"] == "deck"
        assert state(page)["index"] == 0
        press_n(page, "Shift+ArrowDown", 4)
        assert state(page)["index"] == 4
        navigate(page, lambda: page.keyboard.press("h"))
        assert page.url == url_of(course_dir, "index.html", "#ch-02")
        assert state(page)["kind"] == "catalog" and selected(page) == "ch-02" and state(page)["id"] == "ch-02"
        assert visible_ids(page) == COURSE_IDS[:3]
        assert toast_text(page) is None


def test_h_round_trip_to_another_page_of_cards(browser, course_dir):
    # 第5章（2ページ目）を開いて H：2ページ目に切り替わって、第5章が選ばれている
    with page_session(browser, slides_url(course_dir, 5, render=False)) as page:
        navigate(page, lambda: page.keyboard.press("h"))
        assert page.url == url_of(course_dir, "index.html", "#ch-05")
        assert selected(page) == "ch-05" and visible_ids(page) == COURSE_IDS[3:6] and current_pager(page) == ["4〜6"]


def test_back_to_catalog_with_left(browser, course_dir):
    # 目次で第2章を開き、数枚進んで ← を何度か押す → 目次（第2章を選んだ状態）に戻る
    index = url_of(course_dir)
    with page_session(browser, index) as page:
        page.keyboard.press("ArrowDown")
        navigate(page, lambda: page.keyboard.press("Enter"))
        press_n(page, "Shift+ArrowDown", 3)
        assert state(page)["index"] == 3
        assert [i["kind"] for i in places(page)["items"]] == ["catalog", "deck", "deck", "deck", "deck"]
        press_n(page, "ArrowLeft", 3)                              # デッキの中を先頭まで
        assert state(page)["index"] == 0 and places(page)["pos"] == 1
        navigate(page, lambda: page.keyboard.press("ArrowLeft"))   # もう一度：目次へ
        assert page.url == index + "#ch-02"
        assert state(page)["kind"] == "catalog" and selected(page) == "ch-02"
        assert places(page)["pos"] == 0 and len(places(page)["items"]) == 5      # 並びは変わらない（目次の場所は1つのまま）
        assert places(page)["items"][0]["ref"] == "ch-02"
        navigate(page, lambda: page.keyboard.press("ArrowRight"))  # → でデッキの先頭へ戻れる
        assert page.url == slides_url(course_dir, 2, render=False) + "#" + places(page)["items"][1]["ref"]
        assert state(page)["kind"] == "deck" and state(page)["index"] == 0


def test_selection_before_leaving_is_what_left_returns_to(browser, course_dir):
    # 選び直してから別のカードを開く：← で戻るのは、開いたカード
    index = url_of(course_dir)
    with page_session(browser, index) as page:
        press_n(page, "ArrowDown", 3)                              # ch-04
        page.keyboard.press("ArrowUp")                             # ch-03
        navigate(page, lambda: page.keyboard.press("Enter"))
        navigate(page, lambda: page.keyboard.press("ArrowLeft"))
        assert selected(page) == "ch-03" and visible_ids(page) == COURSE_IDS[:3]


def test_left_to_catalog_in_new_card_page(browser, course_dir):
    index = url_of(course_dir)
    with page_session(browser, index) as page:
        press_n(page, "ArrowDown", 4)                              # ch-05（2ページ目）
        navigate(page, lambda: page.keyboard.press("Enter"))
        navigate(page, lambda: page.keyboard.press("ArrowLeft"))
        assert page.url == index + "#ch-05"
        assert selected(page) == "ch-05" and visible_ids(page) == COURSE_IDS[3:6]


# ---- スクロールしない ----

VIEWPORTS = [(1440, 900), (1000, 700), (820, 1180)]

CHECK_LAYOUT = """() => {
  const iw = innerWidth, ih = innerHeight, de = document.documentElement, root = document.querySelector('.sp-catalog');
  const rect = e => { const r = e.getBoundingClientRect(); return {l: r.left, t: r.top, r: r.right, b: r.bottom}; };
  const cards = Array.from(document.querySelectorAll('.sp-card:not([hidden])'));
  const pager = Array.from(document.querySelectorAll('.sp-pager-btn'));
  const out = (r) => r.l < -0.5 || r.t < -0.5 || r.r > iw + 0.5 || r.b > ih + 0.5;
  const parts = Array.from(root.querySelectorAll('.sp-catalog-head, .sp-cards, .sp-pager, .sp-catalog-hint'));
  const kids = Array.from(document.querySelectorAll('.sp-card:not([hidden]) *'));
  const clippedKids = kids.filter(k => { const c = k.closest('.sp-card').getBoundingClientRect(), r = k.getBoundingClientRect();
    return k.getClientRects().length > 0 && (r.bottom > c.bottom + 0.5 || r.right > c.right + 0.5); });
  window.scrollTo(0, 500); root.scrollTop = 500;
  return {
    docScroll: [de.scrollWidth - iw, de.scrollHeight - ih, document.body.scrollHeight - ih],
    scrollY: window.scrollY, rootScroll: [root.scrollWidth - root.clientWidth, root.scrollHeight - root.clientHeight, root.scrollTop],
    cards: cards.length,
    clipped: cards.filter(c => c.scrollHeight > c.clientHeight + 1 || c.scrollWidth > c.clientWidth + 1).map(c => c.dataset.id),
    clippedKids: clippedKids.length,
    cardsOutside: cards.filter(c => out(rect(c))).map(c => c.dataset.id),
    pagerOutside: pager.filter(b => out(rect(b))).length,
    partsOutside: parts.filter(p => out(rect(p))).length,
    partsOverlap: parts.filter(p => p.getClientRects().length > 0).sort((a, b) => rect(a).t - rect(b).t)
      .some((p, i, list) => i > 0 && rect(list[i - 1]).b > rect(p).t + 0.5),
  };
}"""


def assert_fits(page, where):
    r = page.evaluate(CHECK_LAYOUT)
    assert r["cards"] >= 1, where
    assert all(v <= 0 for v in r["docScroll"]) and r["scrollY"] == 0, (where, r)
    assert r["rootScroll"][0] <= 0 and r["rootScroll"][1] <= 0 and r["rootScroll"][2] == 0, (where, r)
    assert r["clipped"] == [] and r["clippedKids"] == 0, (where, r)
    assert r["cardsOutside"] == [] and r["pagerOutside"] == 0 and r["partsOutside"] == 0 and not r["partsOverlap"], (where, r)


@pytest.mark.parametrize("viewport", VIEWPORTS)
@pytest.mark.parametrize("bed", ["generic", "course"])
def test_no_scroll(browser, generic_dir, course_dir, bed, viewport):
    # どの幅でも、全ページのカードがはみ出さず、切り詰められず、ページも縦横にスクロールしない
    directory = {"generic": generic_dir, "course": course_dir}[bed]
    with page_session(browser, url_of(directory), viewport=viewport) as page:
        pages_seen = 0
        while True:
            assert_fits(page, f"{bed} {viewport} ページ{pages_seen + 1}")
            pages_seen += 1
            before = selected(page)
            page.keyboard.press("Shift+ArrowDown")
            if selected(page) == before:
                break
        assert pages_seen == max(1, len(pager_labels(page)))      # 全ページを見た
        page.mouse.wheel(0, 800)                                   # ホイールでも動かない（動かないことの確認：次の評価までの間に動けば見える）
        assert page.evaluate("[scrollY, document.querySelector('.sp-catalog').scrollTop]") == [0, 0]
        assert page.evaluate("getComputedStyle(document.documentElement).overflow") == "hidden"


def test_catalog_with_many_items_does_not_scroll(browser, tmp_path):
    # 項目が極端に多くても、ページはスクロールしない（カードの中で切る。カードは画面からはみ出さない）
    cat = {"contract": 1, "title": "多い" * 30, "lead": "とても長い説明文　" * 12,
           "decks": [{"id": f"d{n}", "href": f"d{n}.html", "label": "第一回", "title": "とても長い題名　" * 6,
                      "items": [f"項目 {k} " + "長い" * 12 for k in range(40)], "meta": "長いメタ　" * 10} for n in range(4)]}
    for viewport in VIEWPORTS:
        with page_session(browser, write_catalog(tmp_path, cat), viewport=viewport) as page:
            r = page.evaluate(CHECK_LAYOUT)
            assert all(v <= 0 for v in r["docScroll"]) and r["scrollY"] == 0 and r["rootScroll"][2] == 0, (viewport, r)
            assert r["cardsOutside"] == [] and r["pagerOutside"] == 0 and r["partsOutside"] == 0 and not r["partsOverlap"], (viewport, r)


def test_many_items_are_clipped_before_the_meta(browser, tmp_path):
    # 項目が極端に多いカード（40項目）：項目の入れ物（.sp-card-items）の中で切り、下の meta に重ならない
    cat = {"contract": 1, "title": "t", "decks": [
        {"id": f"d{n}", "href": f"d{n}.html", "label": "第一回", "title": "題名", "meta": "28枚・約30分",
         "items": [f"項目 {k}" for k in range(40)]} for n in range(3)]}
    for viewport in [(1440, 900), (1000, 700), (820, 1180)]:
        with page_session(browser, write_catalog(tmp_path, cat), viewport=viewport) as page:
            r = page.evaluate("""() => Array.from(document.querySelectorAll('.sp-card:not([hidden])'), c => {
                const ul = c.querySelector('.sp-card-items'), meta = c.querySelector('.sp-card-meta'), u = ul.getBoundingClientRect(), m = meta.getBoundingClientRect();
                const lis = Array.from(ul.querySelectorAll('li'));
                // 入れ物の中で見える項目（入れ物の外へはみ出して切られている分は数えない）が、meta の上端を越えない
                const visible = lis.filter(li => li.getBoundingClientRect().top < u.bottom);
                const lastVisibleBottom = Math.min(Math.max(...visible.map(li => li.getBoundingClientRect().bottom)), u.bottom);
                const probe = document.elementFromPoint((m.left + m.right) / 2, (m.top + m.bottom) / 2);
                return {overflow: getComputedStyle(ul).overflow, ulBottom: u.bottom, metaTop: m.top, lastVisibleBottom,
                        clipped: ul.scrollHeight > ul.clientHeight + 1, visibleCount: visible.length, total: lis.length,
                        probeIsMeta: !!probe && meta.contains(probe)}; })""")
            assert len(r) >= 1
            for c in r:
                assert c["overflow"] == "hidden", (viewport, c)
                assert c["clipped"] and c["visibleCount"] < c["total"], (viewport, c)      # 本当に切れている（空振りでない）
                assert c["ulBottom"] <= c["metaTop"] + 0.5 and c["lastVisibleBottom"] <= c["metaTop"] + 0.5, (viewport, c)
                assert c["probeIsMeta"], (viewport, c)                                      # meta の場所に見えているのは meta


HOSTILE_LIST_CSS = """
ul { display: flex; flex-wrap: wrap; position: relative; left: 90px; top: 7px; float: right; width: 55%; margin: 33px; padding: 21px;
     list-style: none; border: 5px solid red; background: #fcc; columns: 3; text-indent: 40px; }
li { display: inline-block; float: left; width: 240px; height: 60px; margin: 17px; padding: 9px; border: 3px solid blue;
     list-style: square; position: absolute; text-transform: uppercase; background: #ccf; }
ul li { visibility: visible; line-height: 3; }
"""

LIST_PROBE = """() => {
  const ul = document.querySelector('.sp-card:not([hidden]) .sp-card-items'), li = ul.querySelector('li');
  const cs = e => getComputedStyle(e), box = e => { const r = e.getBoundingClientRect(); return [r.left, r.top, r.width, r.height]; };
  const pick = (e, names) => Object.fromEntries(names.map(n => [n, cs(e)[n]]));
  return {
    ul: pick(ul, ['display', 'position', 'float', 'marginTop', 'marginLeft', 'paddingTop', 'paddingLeft', 'borderTopWidth', 'borderLeftWidth',
                  'listStyleType', 'listStylePosition', 'backgroundColor', 'textIndent', 'columnCount', 'flexWrap', 'overflow']),
    li: pick(li, ['display', 'position', 'float', 'width', 'height', 'marginTop', 'marginLeft', 'paddingTop', 'paddingLeft', 'borderTopWidth',
                  'listStyleType', 'backgroundColor', 'textTransform', 'lineHeight']),
    ulBox: box(ul), liBox: box(li),
  };
}"""


def test_card_list_ignores_page_css_for_ul_and_li(browser, tmp_path):
    # ページ自身の CSS の ul・li の指定（display・float・position・margin・border・list-style など）が、目次のカードの項目へ漏れない。
    # 同じ目次を、ページの CSS なしと、荒れた CSS ありで開いて、項目の入れ物と項目の見た目と位置が同じ
    cat = {"contract": 1, "title": "t", "decks": [
        {"id": "d1", "href": "d1.html", "label": "第一回", "title": "題名", "items": ["一つ目", "二つ目", "三つ目"], "meta": "メタ"}]}
    with page_session(browser, write_catalog(tmp_path, cat, "clean.html")) as page:
        clean = page.evaluate(LIST_PROBE)
    with page_session(browser, write_catalog(tmp_path, cat, "hostile.html", style=HOSTILE_LIST_CSS)) as page:
        hostile = page.evaluate(LIST_PROBE)
    assert clean["ul"]["display"] == "block" and clean["li"]["display"] == "list-item"
    assert clean["ul"]["listStyleType"] == "disc"
    assert hostile == clean


# ---- ページ自身の CSS（body の flex・余白・背景と、ページ側に残っていそうな .ch・.track・.view・nav の規則）に左右されない ----

PAGE_CSS = """
html { overflow: auto; }
body { display: flex; flex-direction: column; margin: 12px; padding: 4vh 4vw 3vh; background: #fff8e1; color: #222; overflow: auto; }
nav { display: flex; gap: 8px; padding: 10px; }
.ch { display: block; width: 300px; padding: 20px; border: 2px solid #c00; }
.track { display: flex; overflow-x: auto; }
.view { width: 100vw; height: 100vh; }
"""


def page_css_catalog():
    """7枚（デッキ6＋ページ1）。項目の数がまちまちなので、高さがそろうのは目次の側の決まり。"""
    decks = [{"id": f"d{n}", "href": f"d{n}/slides.html", "label": f"第{n}回", "title": f"第{n}回の題名", "meta": f"{n}0分",
              "items": [f"項目 {n}-{k}" for k in range(1, n % 4 + 2)]} for n in range(1, 7)]
    decks.append({"id": "sheet", "kind": "page", "href": "sheet/index.html", "title": "早見表", "items": ["一枚の表"], "meta": "A4 1枚"})
    return {"contract": 1, "title": "講座の見本", "lead": "ページ自身の CSS が残っている目次", "decks": decks}


def test_catalog_ignores_page_css(browser, tmp_path):
    # ページの <style>（body の flex と余白・背景、ul・nav・.ch・.track・.view の規則）が残っていても、目次は画面いっぱいに出る
    with page_session(browser, write_catalog(tmp_path, page_css_catalog(), style=PAGE_CSS)) as page:
        assert page.evaluate("document.head.innerHTML.includes('padding: 4vh 4vw 3vh')")     # ページ自身の <style> が残っている
        info = page.evaluate("""() => {
          const cs = getComputedStyle(document.body), r = document.querySelector('.sp-catalog').getBoundingClientRect();
          return {margin: cs.margin, padding: cs.padding, overflow: [cs.overflow, getComputedStyle(document.documentElement).overflow],
                  pos: getComputedStyle(document.querySelector('.sp-catalog')).position, rect: [r.left, r.top, r.width, r.height],
                  old: document.querySelectorAll('.ch, .track, .view, nav').length};
        }""")
        assert info["margin"] == "0px" and info["padding"] == "0px" and info["overflow"] == ["hidden", "hidden"]
        assert info["pos"] == "fixed" and info["rect"] == [0, 0, 1440, 900] and info["old"] == 0
        # 最初の描画の全カードが、同じ高さ・同じ列で並ぶ
        rects = page.evaluate("Array.from(document.querySelectorAll('.sp-card:not([hidden])'), c => { const r = c.getBoundingClientRect(); return [r.top, r.height, r.width]; })")
        assert len(rects) == 3 and len({tuple(r[:2]) for r in rects}) == 1 and max(r[2] for r in rects) - min(r[2] for r in rects) < 1


def test_catalog_help_ignores_page_css(browser, tmp_path):
    # ページ自身の CSS が残っていても、目次の「?」の操作の一覧は開き、画面に収まり、Esc で閉じる
    with page_session(browser, write_catalog(tmp_path, page_css_catalog(), style=PAGE_CSS)) as page:
        page.keyboard.press("?")
        assert page.evaluate("__sp.overlay()") == "help"
        assert [ks for ks, _ in page.evaluate(HELP_ROWS)][0] == ["↑", "↓"]
        r = page.evaluate("""() => { const p = document.querySelector('.sp-help-panel').getBoundingClientRect();
            return {l: p.left, t: p.top, r: p.right, b: p.bottom, iw: innerWidth, ih: innerHeight}; }""")
        assert r["l"] >= 0 and r["t"] >= 0 and r["r"] <= r["iw"] and r["b"] <= r["ih"]
        page.keyboard.press("Escape")
        assert page.evaluate("__sp.overlay()") == "none"


# ---- ?render ----

def test_render_mode_on_catalog_does_nothing(browser, generic_dir):
    with page_session(browser, url_of(generic_dir) + "?render") as page:
        assert page.locator(".sp-catalog, .sp-card, .sp-style").count() == 0
        assert page.evaluate("typeof window.__sp") == "undefined"
        page.keyboard.press("ArrowDown")
        page.keyboard.press("1")
        stays(page, url_of(generic_dir) + "?render")
