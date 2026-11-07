"""editor/pending.js（ためた直し・上の札・一覧・反映）と、editor/live.js の札・つながらない帯の試験。
直しは page.evaluate で EditorPending.add を呼んで作る（入力欄を開かずに作る）。"""
import re
import shutil
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from editor.server import EditorServer  # noqa: E402
from helpers import page_session  # noqa: E402
from test_editor_server import BASIC, replace_text  # noqa: E402
from test_pen import LINE, draw, ink_alpha  # noqa: E402

# basic の s02 の文（* の項目は段階 2 まで隠れているので、#s02.2 で開く）
ITEM1 = "珍しい語ほど、点数を高く付ける"
ITEM2 = "どの人にも出る語は、手がかりにならない"
SUB = "前回の「桶狭間」の検索も、この方式だった"
EDITS_ON_TWO_PAGES = [          # 2ページで3か所
    (ITEM1, "珍しい語ほど、点数を高くする"),
    (ITEM2, "どの人にも出る語は、手がかりにならない（例外あり）"),
]
LAST_ITEM = "仮の ID が付く"


@pytest.fixture
def server(tmp_path):
    deck = tmp_path / "deck"
    shutil.copytree(BASIC, deck)
    s = EditorServer(deck / "下書き.md")
    s.start()
    try:
        yield s
    finally:
        s.stop()


def src_of(page, text):
    """描いたデッキの keys から、text の文の key を探す。"""
    return page.evaluate("""(t) => { const e = slideDeck.editor;
      const k = e.keys().find(k => e.textAt(k) === t); return k ? [k, e.slideAt(k)] : null; }""", text)


def add(page, before, after):
    found = src_of(page, before)
    assert found, before
    page.evaluate("([key, slide, before, after]) => EditorPending.add({ key, slide, before, after })",
                  [found[0], found[1], before, after])


def test_bar_texts(server, browser):
    with page_session(browser, server.url) as page:
        page.wait_for_selector(".sp-edit-bar")
        assert re.fullmatch(r"下書き\.md · \d\d:\d\d:\d\d に描き直し", page.inner_text(".sp-edit-pill"))
        assert page.inner_text(".sp-edit-hint") == "文字をクリックすると直せます"
        assert "編集中" not in page.inner_text(".sp-edit-bar")
        assert not page.is_visible(".sp-edit-count") and page.is_disabled(".sp-edit-apply")


def test_add_decorates_stage_and_counts(server, browser):
    with page_session(browser, server.url + "#s02.2") as page:
        add(page, ITEM1, "珍しい語ほど、点数を**高く**する")
        el = page.locator("#stage .sp-ed-pending")
        assert el.inner_text().endswith("珍しい語ほど、点数を高くする") and el.locator("b").inner_text() == "高く"
        assert page.inner_text("#stage .sp-ed-before") == ITEM1
        assert page.inner_text(".sp-edit-count") == "直し 1" and not page.is_disabled(".sp-edit-apply")


def test_apply_writes_all_at_once(server, browser):
    three = EDITS_ON_TWO_PAGES + [(SUB, "前回の「桶狭間」の検索も、この方式でした")]
    with page_session(browser, server.url + "#s02.2") as page:
        for before, after in three:
            add(page, before, after)
        # 2ページ目の直し：最後のページ
        add(page, LAST_ITEM, "仮の ID が付きます")
        t = time.monotonic()
        page.click(".sp-edit-apply")
        page.wait_for_function("EditorPending.count() === 0 && !document.querySelector('#stage .sp-ed-pending')", timeout=3000)
        assert time.monotonic() - t < 1.5
        md = server.md.read_text(encoding="utf-8")
        assert all(after in md for _, after in three) and "仮の ID が付きます" in md
        assert page.inner_text(".sp-edit-toast") == "4か所を反映しました" and page.evaluate("location.hash") == "#s02.2"


def test_apply_keeps_ink(server, browser):
    with page_session(browser, server.url + "#s02.2") as page:
        page.keyboard.press("d")
        draw(page, LINE)
        page.keyboard.press("d")
        assert ink_alpha(page, 700, 300) > 0
        add(page, ITEM1, "珍しい語ほど、点数を高くする")
        page.click(".sp-edit-apply")
        page.wait_for_function("EditorPending.count() === 0 && !document.querySelector('#stage .sp-ed-pending')", timeout=3000)
        assert ink_alpha(page, 700, 300) > 0


def test_cancel_one_from_list(server, browser):
    with page_session(browser, server.url + "#s02.2") as page:
        add(page, ITEM1, "x")
        page.click(".sp-edit-count")
        page.click(".sp-edit-list >> text=取り消す")
        assert page.evaluate("EditorPending.count()") == 0 and ITEM1 in page.inner_text("#stage")
        assert not page.locator("#stage .sp-ed-before").count()


def test_list_row_jumps_to_page(server, browser):
    with page_session(browser, server.url + "#s02.2") as page:
        add(page, ITEM1, "x")
        page.evaluate("location.hash = '#s01'")
        page.click(".sp-edit-count")
        assert ITEM1 in page.inner_text(".sp-edit-list")
        page.click(".sp-edit-row-text")
        assert page.evaluate("location.hash") == "#s02"


def test_pending_follows_line_shift(server, browser):
    with page_session(browser, server.url + "#s02.2") as page:
        add(page, ITEM1, "珍しい語ほど、点数を高くする")
        old_line = page.evaluate("EditorPending.list()[0].src[0]")
        md = server.md.read_text(encoding="utf-8")
        head, rest = md.split("\n---\n", 1)[0], md.split("\n---\n", 1)[1]
        server.md.write_text(head + "\n---\n<!-- メモ -->\n" + rest, encoding="utf-8")   # エディターで上に1行足して保存した
        page.wait_for_function(f"EditorPending.list()[0].src[0] === {old_line + 1}")
        page.wait_for_function("document.querySelectorAll('#stage .sp-ed-pending').length === 1")
        page.click(".sp-edit-apply")
        page.wait_for_function("EditorPending.count() === 0")
        assert "* 珍しい語ほど、点数を高くする" in server.md.read_text(encoding="utf-8")


def test_conflict_kept_in_list(server, browser):
    with page_session(browser, server.url + "#s02.2") as page:
        add(page, ITEM1, "x")
        replace_text(server.md, "点数を高く付ける", "点数を低く付ける")   # エディターで同じ文を変えた
        page.wait_for_function("EditorPending.list()[0].lost === true")
        page.click(".sp-edit-count")
        assert "見つかりません（エディターで変わりました）" in page.inner_text(".sp-edit-list")
        assert page.is_disabled(".sp-edit-apply")


def test_server_conflict_message(server, browser):
    """送る直前に変わった（relocate の前）：サーバーが断り、一覧に文言が出る。"""
    with page_session(browser, server.url + "#s02.2") as page:
        add(page, ITEM1, "x")
        replace_text(server.md, "点数を高く付ける", "点数を低く付ける")
        # live.js の聞き直し（300ms）より先に apply を呼ぶ：同じ処理の中で続けて呼ぶ
        page.evaluate("EditorPending.apply()")
        page.wait_for_function("document.querySelector('.sp-edit-toast')?.textContent.includes('エディターでこの文字が変わっているので、反映しませんでした')", timeout=3000)
        assert page.evaluate("EditorPending.list().length") == 1
        page.click(".sp-edit-count")
        assert page.locator(".sp-edit-row-msg").count() == 1


def test_live_reload_waits_while_open(server, browser):
    with page_session(browser, server.url + "#s02.2") as page:
        page.wait_for_selector(".sp-edit-bar")
        page.evaluate("window.EditorInline = { isOpen: () => true, confirm() {} }")   # 入力欄が開いている
        replace_text(server.md, ITEM2, "どの人にも出る語は、新しい文")
        page.wait_for_timeout(800)
        assert "新しい文" not in page.inner_text("#stage")
        page.evaluate("window.EditorInline.isOpen = () => false")
        page.wait_for_function("document.querySelector('#stage').textContent.includes('新しい文')", timeout=2000)


def test_pending_survives_reload(server, browser):
    with page_session(browser, server.url + "#s02.2") as page:
        add(page, ITEM1, "x")
        page.reload()
        page.wait_for_selector("#stage .sp-ed-pending")
        assert page.evaluate("EditorPending.count()") == 1


def test_beforeunload_with_pending(server, browser):
    with page_session(browser, server.url + "#s02.2") as page:
        add(page, ITEM1, "x")
        page.keyboard.press("Shift")      # beforeunload の確かめは、ページに操作があったときだけ出る（Chrome の決まり）
        kinds = []
        page.on("dialog", lambda d: (kinds.append(d.type), d.dismiss()))
        page.close(run_before_unload=True)
        end = time.monotonic() + 2
        while not kinds and time.monotonic() < end:
            time.sleep(0.02)
        assert kinds == ["beforeunload"]


def test_ids_added_on_first_apply(server, browser):
    """最後のページには ID がない。直して反映すると ID が入り、舞台の hash は同じ。"""
    assert "<!-- id: p" not in server.md.read_text(encoding="utf-8")
    with page_session(browser, server.url + "#s02") as page:
        page.evaluate("location.hash = '#' + slideDeck.info.slides.at(-1).id")
        hash_ = page.evaluate("location.hash")
        add(page, LAST_ITEM, "仮の ID が付きます")
        page.click(".sp-edit-apply")
        page.wait_for_function("EditorPending.count() === 0 && !document.querySelector('#stage .sp-ed-pending')", timeout=3000)
        md = server.md.read_text(encoding="utf-8")
        assert re.search(r"<!-- id: p\d+ -->\n\n# ID のないページ", md) and "仮の ID が付きます" in md
        assert page.evaluate("location.hash") == hash_


def test_connection_lost_banner(server, browser):
    with page_session(browser, server.url) as page:
        page.wait_for_selector(".sp-edit-bar")
        server.stop()
        page.wait_for_selector(".sp-edit-error", timeout=3000)
        assert page.inner_text(".sp-edit-error") == "サーバーにつながりません。slide-edit open で開き直してください"


def test_add_paints_in_place_and_keeps_stroke(server, browser):
    """add は舞台を差し替えず（同じ要素のまま）、書きかけの線も切らない。"""
    with page_session(browser, server.url + "#s02.2") as page:
        page.evaluate("document.querySelector('#stage').__tag = 1; document.querySelector('#stage [data-src]').__tag = 1")
        page.keyboard.press("d")
        page.mouse.move(*LINE[0])
        page.mouse.down()
        page.mouse.move(*LINE[1], steps=4)
        add(page, ITEM1, "珍しい語ほど、点数を高くする")
        page.mouse.move(*LINE[2], steps=4)
        page.mouse.up()
        assert ink_alpha(page, 700, 300) > 0 and ink_alpha(page, 900, 300) > 0
        assert page.evaluate("document.querySelector('#stage').__tag === 1 && document.querySelector('#stage [data-src]').__tag === 1")
        assert page.locator("#stage .sp-ed-pending").count() == 1


def test_blur_add_does_not_swallow_click(server, browser):
    """焦点が外れたときに add を呼んでも、次に押した文のクリックは舞台に届く。"""
    with page_session(browser, server.url + "#s02.2") as page:
        page.evaluate("""() => { const el = document.querySelector('#stage [data-src]'); el.setAttribute('tabindex', '0');
          el.addEventListener('blur', () => EditorPending.add({ key: el.dataset.src, slide: 's02', before: slideDeck.editor.textAt(el.dataset.src), after: 'x' }));
          window.__clicks = 0; document.querySelector('#stage').addEventListener('click', () => window.__clicks++); el.focus(); }""")
        page.locator("#stage [data-src]").nth(3).click()
        assert page.evaluate("window.__clicks") == 1
        assert page.evaluate("EditorPending.count()") == 1


def test_remove_restores_original(server, browser):
    with page_session(browser, server.url + "#s02.2") as page:
        add(page, ITEM1, "珍しい語ほど、点数を**高く**する")
        page.evaluate("EditorPending.remove(EditorPending.list()[0].key)")
        assert not page.locator("#stage .sp-ed-before").count() and not page.locator("#stage .sp-ed-pending").count()
        assert ITEM1 in page.inner_text("#stage") and "高くする" not in page.inner_text("#stage")


def test_cancel_lost_edit_does_not_restore_old_text(server, browser):
    """直せなくなった（lost）直しを取り消しても、古い key で古い文を描き戻さない。"""
    with page_session(browser, server.url + "#s02.2") as page:
        add(page, ITEM1, "x")
        replace_text(server.md, "点数を高く付ける", "点数を低く付ける")   # エディターで同じ位置の文を変えた（同じ長さ）
        page.wait_for_function("EditorPending.list()[0].lost === true")
        page.click(".sp-edit-count")
        page.click(".sp-edit-list >> text=取り消す")
        assert page.evaluate("EditorPending.list().length") == 0
        text = page.inner_text("#stage")
        assert "点数を低く付ける" in text and ITEM1 not in text
