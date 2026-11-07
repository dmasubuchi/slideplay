"""メモの帯（M）と保存の試験。舞台の下の帯に、スライドごとのメモを書く。

見るのは外から見える結果だけ：画面の要素（.sp-memo・.sp-memo-text・.sp-side-memo・.sp-controls・.sp-toast・#stage）の位置、
localStorage のキー（sp-memo-v1 <ページの URL> <スライドの id> <shared|own>）と設定（sp-settings-v1）、試験用の窓口 window.__sp。

試験の決め事：
- 設定は localStorage に先に入れてから開く（読み込みのたびに入れ直す）。操作ボタンは「いつも出す」。
- 汎用の見本 examples/generic/proposal.html（9枚。1枚目 p01、2枚目 p02、3枚目 p03）を使う。
- 保存の待ちは 0.5 秒なので、待つ試験は 0.6 秒待つ。
"""
import json
from contextlib import contextmanager

import pytest

from helpers import page_session
from test_side import SETTINGS_KEY, proposal, rect, saved, state_index, toast_text
from test_swipe import finger_page, swipe, webkit_browser  # noqa: F401（fixture）

PREFIX = "sp-memo-v1"
WAIT_MS = 600                                            # 保存の待ち（500ms）より少し長く
MSG_FAILED = "メモを保存できませんでした（このページを閉じると消えます）"
MSG_LOW = "画面が低いのでメモを出せません"
TEXT = "導入事例"


# ---- 試験の道具 ----

def key_of(url, slide_id, field="shared"):
    return f"{PREFIX} {url.split('#')[0].split('?')[0]} {slide_id} {field}"


def seed_script(settings=None):
    value = json.dumps({"controls": "always", "notes": False, **(settings or {})})
    key = json.dumps(SETTINGS_KEY)           # 読み直しでは入れ直さない（M で変えた設定が続くことを見るため）
    return f"try {{ if (localStorage.getItem({key}) === null) localStorage.setItem({key}, {json.dumps(value)}); }} catch (e) {{}}"


@contextmanager
def session(browser, url, settings=None, viewport=(1440, 900), init=None):
    """設定（既定は操作ボタンをいつも出す）を localStorage に入れてから url を開く。init：その後に足す init script。"""
    with page_session(browser, "about:blank", viewport=viewport) as page:
        page.set_default_timeout(10000)
        page.add_init_script(seed_script(settings))
        if init:
            page.add_init_script(init)
        page.goto(url)
        if "render" not in url:
            page.wait_for_function("!!window.__sp")
        yield page


def stored(page, key):
    return page.evaluate("(k) => localStorage.getItem(k)", key)


def memo_keys(page):
    return page.evaluate(f"Object.keys(localStorage).filter(k => k.startsWith({json.dumps(PREFIX)})).sort()")


def field(page):
    return page.locator("textarea.sp-memo-text")


def write(page, text):
    """欄に焦点を当てて、打つ（input の知らせが出る）。"""
    field(page).click()
    page.keyboard.type(text)


def leave_field(page):
    """欄から Esc で抜ける。"""
    page.keyboard.press("Escape")


def settle_save(page):
    page.wait_for_timeout(WAIT_MS)


# ---- 1. 出す・戻す ----

def test_m_toggles_band_and_saves_setting(browser, generic_dir):
    """M で帯が出て設定 memo が True。もう一度 M で消えて False。読み直しても開閉が続く。"""
    url = proposal(generic_dir)
    with session(browser, url) as page:
        assert page.locator(".sp-memo").count() == 0
        assert "memo" not in saved(page)                 # 押すまで書かない
        page.keyboard.press("m")
        assert page.locator(".sp-memo").count() == 1
        assert saved(page)["memo"] is True
        assert page.evaluate("__sp.memo().band") is True
        assert page.locator(".sp-controls button[aria-pressed='true']").filter(has_text="メモ").count() == 1
        page.reload()
        page.wait_for_function("!!window.__sp")
        assert page.locator(".sp-memo").count() == 1
        page.keyboard.press("M")
        assert page.locator(".sp-memo").count() == 0
        assert saved(page)["memo"] is False
        page.reload()
        page.wait_for_function("!!window.__sp")
        assert page.locator(".sp-memo").count() == 0


def test_band_shrinks_stage(browser, generic_dir):
    """帯を出すと、舞台と操作ボタンの帯が、帯の上に収まる。"""
    with session(browser, proposal(generic_dir)) as page:
        before = rect(page, "#stage")
        page.keyboard.press("m")
        band, stage, controls = rect(page, ".sp-memo"), rect(page, "#stage"), rect(page, ".sp-controls")
        assert stage["bottom"] <= band["top"] + 0.5
        assert controls["bottom"] <= band["top"] + 0.5
        assert band["bottom"] <= 900.5 and abs(band["height"] - 180) < 1       # 画面の高さ 900 の 20%
        assert stage["height"] < before["height"]
        page.keyboard.press("m")
        assert rect(page, "#stage")["height"] == pytest.approx(before["height"], abs=0.5)


def test_low_window_refuses_band(browser, generic_dir):
    """画面が低くて舞台の領域が 240px に満たないときは、帯を出さず知らせる。設定 memo は書かない。"""
    with session(browser, proposal(generic_dir), viewport=(1280, 320)) as page:
        page.keyboard.press("m")
        assert page.locator(".sp-memo").count() == 0
        assert toast_text(page) == MSG_LOW
        assert "memo" not in saved(page)


# ---- 2. 書く・保存 ----

def test_typing_saves_per_slide_and_survives_reload(browser, generic_dir):
    """打つと、待ったあとにそのスライドのキーへ保存される。空にするとキーが消える。スライドごとに別。読み直しても残る。"""
    url = proposal(generic_dir)
    k1 = key_of(url, "p01")
    with session(browser, url, settings={"memo": True}) as page:
        write(page, TEXT)
        settle_save(page)
        assert stored(page, k1) == TEXT
        field(page).fill("")
        settle_save(page)
        assert stored(page, k1) is None
        write(page, TEXT)
        settle_save(page)
        leave_field(page)
        page.keyboard.press("ArrowDown")
        assert state_index(page) == 1
        assert field(page).input_value() == ""
        page.reload()
        page.wait_for_function("!!window.__sp")
        assert field(page).input_value() == ""           # 読み直しで 2 枚目（hash）
        page.keyboard.press("Home")
        assert field(page).input_value() == TEXT
        assert page.evaluate("__sp.memo().shared") == TEXT


def test_keys_do_not_move_while_typing(browser, generic_dir):
    """欄に焦点があるあいだは、キーでスライドも T・M も動かない。Esc で抜けると矢印が効く。"""
    with session(browser, proposal(generic_dir), settings={"memo": True}) as page:
        field(page).click()
        for key in ["Space", "ArrowDown", "ArrowRight", "t", "m"]:
            page.keyboard.press(key)
        assert state_index(page) == 0
        assert page.locator(".sp-side").count() == 0 and page.locator(".sp-memo").count() == 1
        assert page.evaluate("document.activeElement.classList.contains('sp-memo-text')")
        leave_field(page)
        assert not page.evaluate("document.activeElement.classList.contains('sp-memo-text')")
        page.keyboard.press("ArrowDown")
        assert state_index(page) == 1


def test_escape_during_composition_stays(browser, generic_dir):
    """日本語の変換中の Esc では、欄から抜けない。"""
    with session(browser, proposal(generic_dir), settings={"memo": True}) as page:
        field(page).click()
        page.evaluate("""() => { const t = document.querySelector('.sp-memo-text');
            t.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', isComposing: true, bubbles: true, cancelable: true})); }""")
        assert page.evaluate("document.activeElement.classList.contains('sp-memo-text')")
        page.evaluate("document.querySelector('.sp-memo-text').dispatchEvent(new CompositionEvent('compositionstart', {bubbles: true}))")
        page.keyboard.press("Escape")                    # isComposing の印のない Esc（Safari）も、変換中は抜けない
        assert page.evaluate("document.activeElement.classList.contains('sp-memo-text')")
        page.evaluate("document.querySelector('.sp-memo-text').dispatchEvent(new CompositionEvent('compositionend', {bubbles: true}))")
        page.keyboard.press("Escape")
        assert not page.evaluate("document.activeElement.classList.contains('sp-memo-text')")


# ---- 3. 2つのタブ・移り方 ----

def test_two_tabs_do_not_clobber(browser, generic_dir):
    """同じデッキを開いた2つのタブで、別のスライドに保存の待ちを重ねて書いても、両方残る。書いていない欄はほかのタブの値に合わせる。"""
    url = proposal(generic_dir)
    context = browser.new_context(viewport={"width": 1440, "height": 900}, reduced_motion="reduce")
    context.add_init_script(seed_script({"memo": True}))
    try:
        a, b, c = context.new_page(), context.new_page(), context.new_page()
        for p, suffix in ((a, ""), (b, "#p02"), (c, "")):
            p.set_default_timeout(10000)
            p.goto(url + suffix)
            p.wait_for_function("!!window.__sp")
        assert b.evaluate("__sp.state().id") == "p02"
        a.locator(".sp-memo-text").click()
        a.keyboard.type("Aの1枚目")
        b.locator(".sp-memo-text").click()
        b.keyboard.type("Bの2枚目")
        a.keyboard.type("！")
        a.wait_for_timeout(WAIT_MS)
        assert stored(a, key_of(url, "p01")) == "Aの1枚目！"
        assert stored(a, key_of(url, "p02")) == "Bの2枚目"
        c.wait_for_function("document.querySelector('.sp-memo-text').value === 'Aの1枚目！'")   # 書いていない欄は A の値に合う
    finally:
        context.close()


def test_text_stays_on_its_slide(browser, generic_dir):
    """書きかけの文字は、どの移り方でも、書いたスライドのキーにだけ入り、移った先の欄は空。"""
    url = proposal(generic_dir)
    k1, k2, k3 = (key_of(url, i) for i in ("p01", "p02", "p03"))
    # (a) 左の列のサムネイル
    with session(browser, url, settings={"memo": True, "side": True}) as page:
        write(page, TEXT)
        page.locator('.sp-side-item[data-index="3"]').click()
        assert state_index(page) == 3
        assert field(page).input_value() == ""
        assert stored(page, k1) == TEXT
        assert memo_keys(page) == [k1]
        settle_save(page)
        assert memo_keys(page) == [k1]
    # (b) Esc → 次のスライド → ブラウザの履歴（hash を書き換えて足した項目）で動く → 戻る
    with session(browser, url, settings={"memo": True}) as page:
        write(page, TEXT)
        leave_field(page)
        page.keyboard.press("Shift+ArrowDown")           # 次のスライドの最初へ（段階を飛ばす）
        assert state_index(page) == 1
        page.evaluate("location.hash = '#p04'")          # 履歴に項目が足され、hashchange で移る
        page.wait_for_function("__sp.state().id === 'p04'")
        assert field(page).input_value() == ""
        page.go_back()
        page.wait_for_function("__sp.state().id === 'p02'")
        assert field(page).input_value() == ""
        settle_save(page)
        assert memo_keys(page) == [k1] and stored(page, k1) == TEXT
        assert stored(page, k2) is None and stored(page, k3) is None
    # (c) 指で払う
    with finger_page(browser, url, settings={"controls": "always", "notes": False, "memo": True}) as page:
        write(page, TEXT)
        swipe(page, (900, 300), (400, 300))
        page.wait_for_function("__sp.state().index === 1")
        assert field(page).input_value() == ""
        assert stored(page, k1) == TEXT
        settle_save(page)
        assert memo_keys(page) == [k1]


# ---- 4. 左の列の印・出ない所・壊れたとき ----

def test_side_marks_slides_with_memo(browser, generic_dir):
    """左の列で、メモのあるスライドの題名の横に ✎ が付き、消すと外れる。"""
    with session(browser, proposal(generic_dir), settings={"memo": True, "side": True}) as page:
        item = '.sp-side-item[data-index="0"] .sp-side-memo'
        assert page.locator(".sp-side-memo").count() == 0
        write(page, TEXT)
        assert page.locator(item).count() == 1
        assert page.locator(item).get_attribute("aria-label") == "メモあり"
        assert page.locator(".sp-side-memo").count() == 1
        field(page).fill("")
        assert page.locator(".sp-side-memo").count() == 0


def test_storage_failure_keeps_working(browser, generic_dir):
    """localStorage に書けなくても、書けて・移れて、知らせが1回だけ出る。ページの中では覚えている。"""
    init = "Storage.prototype.setItem = function () { throw new Error('quota'); };"
    with session(browser, proposal(generic_dir), settings={"memo": True}, init=init) as page:
        write(page, TEXT)
        settle_save(page)
        assert toast_text(page) == MSG_FAILED
        page.evaluate("document.querySelector('.sp-toast').remove()")
        leave_field(page)
        page.keyboard.press("ArrowDown")
        assert state_index(page) == 1
        write(page, "二枚目")
        settle_save(page)
        assert toast_text(page) is None                  # 2回目は出さない
        leave_field(page)
        page.keyboard.press("Home")
        assert field(page).input_value() == TEXT


def test_broken_store_value_is_ignored(browser, generic_dir):
    """4001 文字の値は捨てて欄は空。ほかのスライドのキーは残る。"""
    url = proposal(generic_dir)
    k1, k2 = key_of(url, "p01"), key_of(url, "p02")
    init = f"try {{ if (!localStorage.getItem({json.dumps(k1)})) {{ localStorage.setItem({json.dumps(k1)}, 'あ'.repeat(4001)); localStorage.setItem({json.dumps(k2)}, '残る'); }} }} catch (e) {{}}"
    with session(browser, url, settings={"memo": True, "side": True}, init=init) as page:
        assert field(page).input_value() == ""
        assert page.locator('.sp-side-item[data-index="0"] .sp-side-memo').count() == 0
        assert page.locator('.sp-side-item[data-index="1"] .sp-side-memo').count() == 1
        leave_field(page)
        page.keyboard.press("ArrowDown")
        assert field(page).input_value() == "残る"
        assert stored(page, k2) == "残る"


def test_memo_not_in_render_or_print_or_overview(browser, generic_dir):
    """?render には帯がなく、PDF の印刷用の箱と縮小一覧に書いた文字が出ない。"""
    url = proposal(generic_dir)
    with session(browser, url + "?render", settings={"memo": True}) as page:
        assert page.locator(".sp-memo").count() == 0
    with session(browser, url, settings={"memo": True}) as page:
        write(page, "ひみつのメモ")
        leave_field(page)
        page.evaluate("window.dispatchEvent(new Event('beforeprint'))")
        assert page.locator(".sp-print").count() == 1
        assert "ひみつのメモ" not in page.locator(".sp-print").inner_text()
        page.evaluate("window.dispatchEvent(new Event('afterprint'))")
        page.keyboard.press("o")
        page.wait_for_selector(".sp-overview")
        assert "ひみつのメモ" not in page.locator(".sp-overview").inner_text()


# ---- 5. 置き方 ----

@pytest.mark.parametrize("viewport", [(1280, 720), (1024, 768)])
def test_all_open_do_not_overlap(browser, generic_dir, viewport):
    """T・N・M を全部開いた狭い画面で、舞台・帯・操作ボタンの帯・知らせが重ならない。"""
    with session(browser, proposal(generic_dir), settings={"memo": True, "side": True, "notes": True}, viewport=viewport) as page:
        assert page.locator(".sp-side").count() == 1 and page.locator(".sp-notes").count() == 1
        band, stage, controls = rect(page, ".sp-memo"), rect(page, "#stage"), rect(page, ".sp-controls")
        side, notes = rect(page, ".sp-side"), rect(page, ".sp-notes")
        assert stage["bottom"] <= band["top"] + 0.5 and controls["bottom"] <= band["top"] + 0.5
        assert band["left"] >= side["right"] - 0.5 and band["right"] <= notes["left"] + 0.5
        assert controls["left"] >= side["right"] - 0.5 and controls["right"] <= notes["left"] + 0.5
        page.keyboard.press("ArrowUp")                   # 最初のスライドで ↑ → 「最初のスライドです」の知らせ
        page.wait_for_selector(".sp-toast")
        toast = rect(page, ".sp-toast")
        assert toast["bottom"] <= controls["top"] + 0.5 and toast["bottom"] <= band["top"] + 0.5
        assert toast["left"] >= side["right"] - 0.5 and toast["right"] <= notes["left"] + 0.5


# ---- 6. 焦点のある欄はほかのタブに上書きされない ----

def test_focused_field_not_overwritten_by_other_tab(browser, generic_dir):
    """書いている欄（焦点あり）は、ほかのタブが同じキーに書いても変わらない。焦点が外れたあとは、ほかのタブに合う。"""
    url = proposal(generic_dir)
    k1 = key_of(url, "p01")
    context = browser.new_context(viewport={"width": 1440, "height": 900}, reduced_motion="reduce")
    context.add_init_script(seed_script({"memo": True}))
    try:
        a, b = context.new_page(), context.new_page()
        for p in (a, b):
            p.set_default_timeout(10000)
            p.goto(url)
            p.wait_for_function("!!window.__sp")
        a.locator(".sp-memo-text").click()
        a.keyboard.type("Aの文字")
        a.wait_for_timeout(WAIT_MS)
        assert stored(a, k1) == "Aの文字"
        b.locator(".sp-memo-text").click()
        b.keyboard.type("Bの文字")                       # B の続き（A の値に足される）
        b.wait_for_timeout(WAIT_MS)
        b_value = stored(b, k1)
        assert b_value and b_value != "Aの文字"
        a.wait_for_timeout(300)
        assert a.locator(".sp-memo-text").input_value() == "Aの文字"            # 焦点のある A の欄は変わらない
        a.keyboard.press("Escape")                       # A が焦点を外す
        b.keyboard.type("！")
        b.wait_for_timeout(WAIT_MS)
        a.wait_for_function("(v) => document.querySelector('.sp-memo-text').value === v", arg=stored(b, k1))
    finally:
        context.close()


# ---- 7. 自分用のメモ（N の中） ----

OWN_OPEN = "自分用のメモを開く"
OWN_CLOSE = "自分用のメモを閉じる"
OWN_HEAD = "自分用のメモ（画面に出すと相手にも見えます）"


def own_field(page):
    return page.locator("textarea.sp-notes-memo")


def open_own(page):
    page.locator(".sp-notes button", has_text=OWN_OPEN).click()


def test_own_memo_in_notes_only(browser, generic_dir):
    """N の中、ノートの下に「自分用のメモを開く」だけがある。押すと見出しと欄が出る。own のキーに入り、帯には出ない。"""
    url = proposal(generic_dir)
    with session(browser, url, settings={"memo": True, "notes": True}) as page:
        assert page.locator(".sp-notes").count() == 1
        assert page.locator(".sp-notes button").inner_text() == OWN_OPEN
        assert own_field(page).count() == 0 and OWN_HEAD not in page.locator(".sp-notes").inner_text()
        assert page.evaluate("__sp.memo().ownOpen") is False
        open_own(page)
        assert OWN_HEAD in page.locator(".sp-notes").inner_text()
        assert own_field(page).get_attribute("maxlength") == "4000"
        assert page.locator(".sp-notes button").inner_text() == OWN_CLOSE
        assert page.evaluate("__sp.memo().ownOpen") is True
        body, area = rect(page, ".sp-notes-body"), rect(page, "textarea.sp-notes-memo")
        assert body["bottom"] <= area["top"] + 0.5                 # 中身のノートの下
        own_field(page).click()
        page.keyboard.type("自分だけ")
        settle_save(page)
        assert stored(page, key_of(url, "p01", "own")) == "自分だけ"
        assert stored(page, key_of(url, "p01")) is None
        assert field(page).input_value() == ""                     # 帯には出ない
        write(page, "帯だけ")
        assert own_field(page).input_value() == "自分だけ"         # ノートの欄に帯の文字は出ない
        assert page.evaluate("__sp.memo().own") == "自分だけ"
        page.locator(".sp-notes button", has_text=OWN_CLOSE).click()
        assert own_field(page).count() == 0 and page.evaluate("__sp.memo().ownOpen") is False


def test_own_memo_closed_on_load(browser, generic_dir):
    """N が開いていても、自分用のメモは閉じた状態で始まり、中身は画面のどこにもない。"""
    url = proposal(generic_dir)
    init = f"try {{ localStorage.setItem({json.dumps(key_of(url, 'p01', 'own'))}, '見えてはいけない'); }} catch (e) {{}}"
    with session(browser, url, settings={"notes": True}, init=init) as page:
        assert page.locator(".sp-notes").count() == 1
        assert "見えてはいけない" not in page.evaluate("document.body.innerText")
        assert own_field(page).count() == 0
        open_own(page)
        assert own_field(page).input_value() == "見えてはいけない"
        page.reload()
        page.wait_for_function("!!window.__sp")
        assert own_field(page).count() == 0 and "見えてはいけない" not in page.evaluate("document.body.innerText")
        page.keyboard.press("n")                          # N を閉じて開き直しても閉じた状態
        page.keyboard.press("n")
        assert own_field(page).count() == 0


def test_own_memo_follows_slide(browser, generic_dir):
    """スライドごとに別々。移ると入れ替わり、読み直しても残る。移る前の文字は書いたスライドに入る。"""
    url = proposal(generic_dir)
    with session(browser, url, settings={"notes": True}) as page:
        open_own(page)
        own_field(page).click()
        page.keyboard.type("一枚目")
        page.keyboard.press("Escape")
        page.keyboard.press("ArrowDown")
        assert state_index(page) == 1
        assert own_field(page).input_value() == ""
        own_field(page).click()
        page.keyboard.type("二枚目")
        page.keyboard.press("Escape")
        page.keyboard.press("Home")
        assert own_field(page).input_value() == "一枚目"
        assert stored(page, key_of(url, "p02", "own")) == "二枚目"
        page.reload()
        page.wait_for_function("!!window.__sp")
        open_own(page)
        assert own_field(page).input_value() == "二枚目" or own_field(page).input_value() == "一枚目"
        page.keyboard.press("Home")
        assert own_field(page).input_value() == "一枚目"
        page.keyboard.press("ArrowDown")
        assert own_field(page).input_value() == "二枚目"
        assert memo_keys(page) == sorted([key_of(url, "p01", "own"), key_of(url, "p02", "own")])


def test_own_memo_keys_stay_in_field(browser, generic_dir):
    """自分用の欄でも、キーでスライドは動かず、Esc で抜けられる。"""
    with session(browser, proposal(generic_dir), settings={"notes": True}) as page:
        open_own(page)
        own_field(page).click()
        for key in ["Space", "ArrowDown", "t"]:
            page.keyboard.press(key)
        assert state_index(page) == 0
        page.keyboard.press("Escape")
        assert not page.evaluate("document.activeElement.classList.contains('sp-notes-memo')")
        page.keyboard.press("ArrowDown")
        assert state_index(page) == 1


# ---- 8. 書き出し ----

EXPORT = "書き出す"


def export_md(page):
    with page.expect_download() as info:
        page.locator(".sp-memo button", has_text=EXPORT).click()
    d = info.value
    with open(d.path(), encoding="utf-8") as f:
        return d.suggested_filename, f.read()


def test_export_shared_only(browser, generic_dir):
    """帯のメモだけを、デッキの順に Markdown にして書き出す。own は入らない。メモがなければボタンは押せない。"""
    url = proposal(generic_dir)
    init = (f"try {{ if (!localStorage.getItem({json.dumps(key_of(url, 'p01'))})) {{"
            f"localStorage.setItem({json.dumps(key_of(url, 'p03'))}, 'C本文');"
            f"localStorage.setItem({json.dumps(key_of(url, 'p01', 'own'))}, 'B本文');"
            f"localStorage.setItem({json.dumps(key_of(url, 'p01'))}, 'A本文');"
            f"localStorage.setItem({json.dumps(key_of(url, 'gone'))}, 'D消えたスライド'); }} }} catch (e) {{}}")
    with session(browser, url, settings={"memo": True}, init=init) as page:
        name, text = export_md(page)
        assert name == "請求業務の効率化のご提案-メモ.md"
        assert "A本文" in text and "C本文" in text
        assert "B本文" not in text and "D消えたスライド" not in text
        assert text.index("A本文") < text.index("C本文")
        assert "## 1　" in text and "## 3　" in text
        assert text.index("## 1　") < text.index("A本文") < text.index("## 3　") < text.index("C本文")
    empty = proposal(generic_dir)
    with session(browser, empty, settings={"memo": True}) as page:
        page.evaluate("localStorage.clear()")
        page.reload()
        page.wait_for_function("!!window.__sp")
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    try:
        p = ctx.new_page()
        p.add_init_script(seed_script({"memo": True}))
        p.goto(empty)
        p.wait_for_function("!!window.__sp")
        assert p.locator(".sp-memo button", has_text=EXPORT).is_disabled()
        p.locator(".sp-memo-text").click()
        p.keyboard.type("あ")                            # 打つと、待たずに押せるようになる
        p.wait_for_function("!document.querySelector('.sp-memo button').disabled")
        p.locator(".sp-memo-text").fill("")
        p.wait_for_function("document.querySelector('.sp-memo button').disabled")
    finally:
        ctx.close()


def test_export_name_without_title(browser, generic_dir):
    """題名がなければ メモ.md。題名の / \\ : * ? " < > | は _ にする（書き出しの時点の題名）。"""
    url = proposal(generic_dir)
    init = f"try {{ localStorage.setItem({json.dumps(key_of(url, 'p01'))}, 'x'); }} catch (e) {{}}"
    for title, want in (("", "メモ.md"), ('a/b\\c:d*e?f"g<h>i|j', "a_b_c_d_e_f_g_h_i_j-メモ.md")):
        with session(browser, url, settings={"memo": True}, init=init) as page:
            page.evaluate("(t) => { window.slideDeck.info.title = t; }", title)
            assert export_md(page)[0] == want


# ---- 9. WebKit ----

@pytest.mark.webkit
def test_band_and_notes_memo_webkit(webkit_browser, generic_dir):
    """Safari でも、帯が出て書け、読み直しで残る。自分用のメモも開いて書ける。"""
    url = proposal(generic_dir)
    with session(webkit_browser, url, settings={"memo": True, "notes": True}) as page:
        assert page.locator(".sp-memo").count() == 1
        write(page, TEXT)
        settle_save(page)
        assert stored(page, key_of(url, "p01")) == TEXT
        open_own(page)
        own_field(page).click()
        page.keyboard.type("自分用")
        settle_save(page)
        assert stored(page, key_of(url, "p01", "own")) == "自分用"
        page.reload()
        page.wait_for_function("!!window.__sp")
        assert field(page).input_value() == TEXT
        assert own_field(page).count() == 0


# ---- 8. 古い欄のまま移っても、ほかのタブの新しい保存を戻さない ----

def _stale_tab_session(browser, url, settings):
    context = browser.new_context(viewport={"width": 1440, "height": 900}, reduced_motion="reduce")
    context.add_init_script(seed_script({"side": True, **settings}))
    a, b = context.new_page(), context.new_page()
    for p in (a, b):
        p.set_default_timeout(10000)
        p.goto(url)
        p.wait_for_function("!!window.__sp")
    return context, a, b


@pytest.mark.parametrize("which", ["shared", "own"])
@pytest.mark.parametrize("typed_after", [False, True])
def test_stale_focused_field_does_not_clobber_on_navigate(browser, generic_dir, which, typed_after):
    """A が打って保存 → B が同じ欄に後から書いて保存 → A は焦点を保ったままサムネイルで移る。
    A があとに打っていなければ B の値のまま。B の保存のあとに A がさらに打ったなら A の値（あとに書いた方）。"""
    url = proposal(generic_dir)
    key = key_of(url, "p01", which)
    settings = {"memo": True} if which == "shared" else {"memo": False, "notes": True}
    context, a, b = _stale_tab_session(browser, url, settings)
    try:
        if which == "own":
            for p in (a, b):
                open_own(p)
        pick = field if which == "shared" else own_field
        pick(a).click()
        a.keyboard.type("Aの保存済み値")
        a.wait_for_timeout(WAIT_MS)
        assert stored(a, key) == "Aの保存済み値"
        pick(b).click()
        b.keyboard.type("とBの後書き")
        b.wait_for_timeout(WAIT_MS)
        b_value = stored(b, key)
        assert b_value == "Aの保存済み値とBの後書き"
        assert pick(a).input_value() == "Aの保存済み値"           # 焦点のある A の欄は古いまま
        if typed_after:
            a.keyboard.type("！")                                  # B の保存のあとに A が打つ（あとに書いた方が残る）
        a.locator('.sp-side-item[data-index="1"]').click()
        assert state_index(a) == 1
        expected = "Aの保存済み値！" if typed_after else b_value
        assert stored(a, key) == expected
    finally:
        context.close()
