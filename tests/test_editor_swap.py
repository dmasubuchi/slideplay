"""player.js の「デッキを差し替える口」（window.slideEditor.attach(api)）の試験。Editor が保存のたびに、ページを読み直さずに描き直すための口。

試験のページは tmp_path に書く：examples/generic/render.js で作るデッキ A（a1（段階1）・a2（段階2）・a3）と、
player.js の前に置いた window.slideEditor（attach が api を window.__ed に入れる）。デッキ B は試験の中で createDeck して渡す。
window.slideEditor がないページは今と変わらない（公開ページ・?render）。
"""
import json

import pytest

from helpers import assert_no_page_errors, page_session
from test_pen import LINE, draw, ink_alpha

REPO = __import__("pathlib").Path(__file__).resolve().parent.parent
PLAYER = (REPO / "player" / "player.js").as_uri()
RENDER = (REPO / "examples" / "generic" / "render.js").as_uri()


def slide(id_, title, steps=0):
    s = {"id": id_, "type": "bullets", "title": title, "items": ["あ", "い"]}
    if steps:
        s["items"] = [{"text": f"項目{k}", "at": k} for k in range(1, steps + 1)]
    return s


A1, A2, A3 = slide("a1", "題名1", 1), slide("a2", "題名2", 2), slide("a3", "題名3")
DECK_A = [A1, A2, A3]
B_TITLE_CHANGED = [A1, slide("a2", "新しい題名", 2), A3]
B_REVERSED = [A3, A2, A1]
B_A2_NO_STEPS = [A1, slide("a2", "新しい題名"), A3]
B_WITHOUT_A2 = [A1, A3]
B_FOUR_SLIDES = [A1, A2, A3, slide("a4", "題名4")]

EDITOR = "window.slideEditor = { attach(api) { window.__ed = api; window.__attached = (window.__attached || 0) + 1; } };"


def write_page(tmp_path, with_editor=True):
    path = tmp_path / "editor.html"
    path.write_text(f"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><title>編集</title></head>
<body><div id="stage" class="sp-target"></div>
<script src="{RENDER}"></script>
<script>
window.slideDeck = GenericSlides.createDeck({{ id: 'ed', title: '編集', slides: {json.dumps(DECK_A)} }});
{EDITOR if with_editor else ""}
</script>
<script src="{PLAYER}"></script>
</body></html>""", encoding="utf-8")
    return path


@pytest.fixture
def editor_page(browser, tmp_path):
    with page_session(browser, write_page(tmp_path).as_uri() + "#a2.1") as page:
        page.set_default_timeout(10000)
        page.wait_for_function("!!window.__ed")
        yield page


def replace(page, slides):
    return page.evaluate(
        "(slides) => __ed.replaceDeck(GenericSlides.createDeck({ id: 'ed', title: '編集', slides }))", slides)


def history_length(page):
    return page.evaluate("history.length")


def go_to(page, id_):
    page.evaluate(f"location.hash = {json.dumps('#' + id_)}")
    page.wait_for_function(f"__sp.state().id === {json.dumps(id_)}")


def add_blank_page_after_current(page):
    if not page.evaluate("__sp.writing().active"):
        page.keyboard.press("d")
    page.locator(".sp-write-tools button").filter(has_text="白紙を足す").click()
    page.wait_for_function("__sp.state().add !== null")


def test_replace_keeps_slide_and_step(editor_page):
    n = history_length(editor_page)
    items = editor_page.evaluate("__sp.places().items.length")
    at = replace(editor_page, B_TITLE_CHANGED)
    assert at == {"id": "a2", "step": 1}
    assert "新しい題名" in editor_page.inner_text("#stage")
    assert editor_page.evaluate("location.hash") == "#a2.1"
    assert history_length(editor_page) == n
    assert editor_page.evaluate("__sp.places().items.length") == items
    assert editor_page.evaluate("__ed.place()") == {"id": "a2", "step": 1, "add": None}


def test_replace_follows_id_when_reordered(editor_page):
    assert replace(editor_page, B_REVERSED) == {"id": "a2", "step": 1}
    assert editor_page.evaluate("__sp.state().index") == 1
    assert editor_page.evaluate("location.hash") == "#a2.1"


def test_replace_clamps_step(editor_page):
    assert replace(editor_page, B_A2_NO_STEPS) == {"id": "a2", "step": 0}
    assert editor_page.evaluate("location.hash") == "#a2"


def test_replace_removed_slide_goes_to_neighbor(editor_page):
    add_blank_page_after_current(editor_page)
    assert replace(editor_page, B_WITHOUT_A2) == {"id": "a3", "step": 0}
    assert editor_page.evaluate("__ed.place()")["add"] is None
    assert editor_page.evaluate("__sp.pages().length") == 2          # 消えた a2 の追加ページも一緒に消える
    assert editor_page.evaluate("location.hash") == "#a3"
    assert_no_page_errors(editor_page)


def test_replace_removed_last_slide_goes_to_new_last(browser, tmp_path):
    with page_session(browser, write_page(tmp_path).as_uri() + "#a3") as page:
        page.wait_for_function("!!window.__ed")
        assert replace(page, [A1, A2]) == {"id": "a2", "step": 0}


def test_replace_keeps_ink_and_added_page(editor_page):
    editor_page.keyboard.press("d")
    draw(editor_page, LINE)
    add_blank_page_after_current(editor_page)
    editor_page.keyboard.press("d")                                  # 書き込みを終える
    replace(editor_page, B_REVERSED)
    pages = editor_page.evaluate("__sp.pages()")
    assert [(p["index"], p["add"] is not None) for p in pages] == [(0, False), (1, False), (1, True), (2, False)]   # 追加ページは a2 のすぐ後ろのまま
    go_to(editor_page, "a2")
    assert ink_alpha(editor_page, 700, 300) > 0
    editor_page.keyboard.press("Shift+ArrowDown")
    editor_page.keyboard.press("Shift+ArrowUp")
    editor_page.keyboard.press("ArrowDown")
    assert editor_page.evaluate("__ed.place()")["add"] is not None
    assert_no_page_errors(editor_page)


def test_replace_keeps_ink_of_slide(browser, tmp_path):
    with page_session(browser, write_page(tmp_path).as_uri() + "#a2.1") as page:
        page.wait_for_function("!!window.__ed")
        page.keyboard.press("d")
        draw(page, LINE)
        page.keyboard.press("d")
        assert ink_alpha(page, 700, 300) > 0
        replace(page, B_REVERSED)
        assert ink_alpha(page, 700, 300) > 0                         # 同じスライドのまま。線もそのまま
        go_to(page, "a1")
        assert ink_alpha(page, 700, 300) == 0
        go_to(page, "a2")
        assert ink_alpha(page, 700, 300) > 0
        assert_no_page_errors(page)


def test_added_page_follows_slide_id(editor_page):
    add_blank_page_after_current(editor_page)
    editor_page.keyboard.press("d")
    at = replace(editor_page, B_REVERSED)
    assert at == {"id": "a2", "step": 2}                              # 追加ページの上では、元のスライドの最後の段階
    place = editor_page.evaluate("__ed.place()")
    assert place["id"] == "a2" and place["add"] is not None          # 追加ページの上にいたら、そのまま
    assert editor_page.evaluate("location.hash") == "#a2.2"


def test_replace_refreshes_side_list(editor_page):
    editor_page.keyboard.press("t")
    assert editor_page.locator(".sp-side-item").count() == 3
    replace(editor_page, B_FOUR_SLIDES)
    assert editor_page.locator(".sp-side-item").count() == 4
    assert "sp-current" in editor_page.locator(".sp-side-item").nth(1).get_attribute("class")


def test_replace_refreshes_notes_overview_memo(editor_page):
    editor_page.keyboard.press("n")
    replace(editor_page, B_TITLE_CHANGED)
    assert "新しい題名" in editor_page.inner_text(".sp-notes")
    editor_page.keyboard.press("o")
    editor_page.wait_for_selector(".sp-overview")
    replace(editor_page, B_FOUR_SLIDES)
    assert editor_page.locator(".sp-overview .sp-thumb").count() == 4
    assert_no_page_errors(editor_page)


def test_replace_plays_no_motion(browser, tmp_path):
    with page_session(browser, "about:blank", reduced_motion="no-preference") as page:
        page.add_init_script("window.__vtCalls = 0; const o = document.startViewTransition && document.startViewTransition.bind(document);"
                             "if (o) document.startViewTransition = cb => { window.__vtCalls++; return o(cb); };")
        page.goto(write_page(tmp_path).as_uri() + "#a2.1")
        page.wait_for_function("!!window.__ed")
        before = page.evaluate("window.__vtCalls")
        replace(page, B_REVERSED)
        assert page.evaluate("window.__vtCalls") == before
        assert page.evaluate("__sp.motion().kind") == "none"


def test_attach_called_once(editor_page):
    assert editor_page.evaluate("window.__attached") == 1
    replace(editor_page, B_REVERSED)
    assert editor_page.evaluate("window.__attached") == 1


def test_render_mode_does_not_attach(browser, tmp_path):
    with page_session(browser, write_page(tmp_path).as_uri() + "?render") as page:
        assert page.evaluate("typeof window.__attached") == "undefined"


def test_without_editor_nothing_changes(generic_dir, browser):
    with page_session(browser, (generic_dir / "proposal.html").as_uri()) as page:
        assert page.evaluate("typeof window.slideEditor === 'undefined' && typeof window.__ed === 'undefined'")
        page.keyboard.press("ArrowDown")                            # ふつうに動く（例外は page_session が見る）
