"""追加ページの試験。

書き込みの帯の「白紙を足す」で、今のページのすぐ後ろに白紙のページを足す。
見るのは外から見える結果だけ：試験用の窓口 window.__sp（state・pages・places・writing・memo・motion・entry）、
画面の要素（.sp-pos・.sp-paper・#stage・.sp-write-tools・.sp-side-item・.sp-thumb・.sp-notes・.sp-memo）、location.hash、localStorage。
汎用の見本 examples/generic/proposal.html（9枚。p02 は段階2つ、p03 は段階なし、p04 はリンクあり）と motion.html を使う。
"""
import json

from helpers import page_session
from test_motion import moving  # noqa: F401（fixture）
from test_pen import motion_url
from test_side import proposal, session
from test_writing import stroke, writing

TOOLS = ".sp-write-tools"
ADD_BTN = "白紙を足す"
DEL_BTN = "この追加ページを消す"
CONFIRM = "この追加ページを消しますか？書いたものも消えます"
LINE = [(500, 300), (700, 320), (900, 340)]
LINE2 = [(500, 500), (900, 520)]


def tool(page, text):
    return page.locator(f"{TOOLS} button").filter(has_text=text)


def add_page(page):
    tool(page, ADD_BTN).click()


def st(page):
    return page.evaluate("__sp.state()")


def pos(page):
    return page.inner_text(".sp-pos")


def rect(page, selector):
    return page.evaluate("""(s) => { const e = document.querySelector(s); if (!e) return null;
        const r = e.getBoundingClientRect(); return {left: r.left, top: r.top, width: r.width, height: r.height}; }""", selector)


def start_writing(page):
    page.keyboard.press("d")
    assert writing(page)["active"] is True


def on_slide(page, hash_):
    """hash の所へ移る（読み込み後）。"""
    page.evaluate(f"location.hash = {json.dumps(hash_)}")
    page.wait_for_function(f"__sp.state().id === {json.dumps(hash_.lstrip('#').split('.')[0])}")


def toast(page):
    el = page.query_selector(".sp-toast")
    return el.inner_text() if el else None


def other_storage(page):
    return page.evaluate("""() => { const o = {}; for (let i = 0; i < localStorage.length; i++) { const k = localStorage.key(i);
        if (k !== 'sp-settings-v1') o[k] = localStorage.getItem(k); } return o; }""")


# ---- 足す・番号 ----

def test_add_after_current_and_label(browser, generic_dir):
    with session(browser, proposal(generic_dir, "#p03")) as page:
        assert st(page)["add"] is None
        start_writing(page)
        assert not tool(page, DEL_BTN).is_visible()
        add_page(page)
        s = st(page)
        assert s["index"] == 2 and s["id"] == "p03" and s["add"] and s["label"] == "3（追加ページ） / 9"
        assert pos(page) == "3（追加ページ） / 9"
        paper, stage = rect(page, ".sp-paper"), rect(page, "#stage")
        assert paper and stage and page.is_visible(".sp-paper")
        for k in ("left", "top", "width", "height"):
            assert abs(paper[k] - stage[k]) < 1, k
        # 舞台の中心は紙が覆っている
        assert page.evaluate("""() => { const r = document.getElementById('stage').getBoundingClientRect();
            const e = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2); return !!e && (e.classList.contains('sp-paper') || e.classList.contains('sp-ink')); }""")
        first = st(page)["add"]
        add_page(page)
        assert st(page)["label"] == "3（追加ページ 2） / 9" and st(page)["add"] != first
        # 1つ目に戻って足す：新しいものが1つ目の後ろ、元の2つ目は「3」番目
        page.keyboard.press("ArrowUp")
        assert st(page)["add"] == first
        add_page(page)
        assert st(page)["label"] == "3（追加ページ 2） / 9"
        page.keyboard.press("ArrowDown")
        assert st(page)["label"] == "3（追加ページ 3） / 9"
        assert [p["add"] for p in page.evaluate("__sp.pages()") if p["index"] == 2 and p["add"]][0] == first
        # 元のスライドでは紙は見えない
        page.keyboard.press("ArrowDown")
        page.keyboard.press("ArrowDown")
        assert st(page)["add"] is None and st(page)["index"] == 3
        assert not page.is_visible(".sp-paper")
        assert pos(page).startswith("4 / 9")


def test_add_on_slide_goes_to_front_of_slides_list(browser, generic_dir):
    with session(browser, proposal(generic_dir, "#p03")) as page:
        start_writing(page)
        add_page(page)
        first = st(page)["add"]
        page.keyboard.press("ArrowUp")           # 3枚目に戻って足す → 1つ目の前
        assert st(page)["add"] is None
        add_page(page)
        assert st(page)["add"] != first and st(page)["label"] == "3（追加ページ） / 9"
        seq = [p for p in page.evaluate("__sp.pages()") if p["index"] == 2]
        assert [p["add"] for p in seq][0] is None and [p["add"] for p in seq][2] == first
        assert len(page.evaluate("__sp.pages()")) == 11


# ---- 移る ----

def test_order_moves_pass_through(browser, generic_dir):
    with session(browser, proposal(generic_dir, "#p02.2")) as page:
        start_writing(page)
        add_page(page)
        a = st(page)["add"]
        page.keyboard.press("ArrowUp")
        s = st(page)
        assert (s["id"], s["step"], s["add"]) == ("p02", 2, None)
        page.keyboard.press("ArrowDown")
        assert st(page)["add"] == a
        page.keyboard.press("ArrowDown")
        s = st(page)
        assert (s["id"], s["step"], s["add"]) == ("p03", 0, None)
        page.keyboard.press("ArrowUp")
        assert st(page)["add"] == a
        page.keyboard.press("ArrowUp")
        s = st(page)
        assert (s["id"], s["step"], s["add"]) == ("p02", 2, None)
        # Shift＋↓↑ も追加ページを1ページとして通る
        page.keyboard.press("Shift+ArrowDown")
        assert st(page)["add"] == a
        page.keyboard.press("Shift+ArrowDown")
        assert (st(page)["id"], st(page)["add"]) == ("p03", None)
        page.keyboard.press("Shift+ArrowUp")
        assert st(page)["add"] == a
        page.keyboard.press("Shift+ArrowUp")
        s = st(page)
        assert (s["id"], s["step"], s["add"]) == ("p02", 2, None)
        page.keyboard.press("Home")
        assert (st(page)["index"], st(page)["add"]) == (0, None)
        page.keyboard.press("End")
        assert (st(page)["index"], st(page)["add"]) == (8, None)


def test_hash_stays_on_parent(browser, generic_dir):
    with session(browser, proposal(generic_dir, "#p03")) as page:
        start_writing(page)
        add_page(page)
        assert st(page)["add"]
        assert page.evaluate("location.hash") == "#p03"
        page.reload()
        page.wait_for_function("!!window.__sp")
        s = st(page)
        assert (s["id"], s["add"]) == ("p03", None)
        assert len([p for p in page.evaluate("__sp.pages()") if p["add"]]) == 0
        assert not page.is_visible(".sp-paper")


# ---- 直近の場所 ----

def test_places_record_added_page(browser, generic_dir):
    with session(browser, proposal(generic_dir, "#p03")) as page:
        start_writing(page)
        add_page(page)
        a = st(page)["add"]
        page.keyboard.press("ArrowDown")
        assert st(page)["index"] == 3 and st(page)["add"] is None
        page.keyboard.press("ArrowLeft")
        assert (st(page)["index"], st(page)["add"]) == (2, a)
        page.keyboard.press("ArrowLeft")
        assert (st(page)["index"], st(page)["add"]) == (2, None)
        page.keyboard.press("ArrowRight")
        assert (st(page)["index"], st(page)["add"]) == (2, a)
        assert page.evaluate("location.hash") == "#p03"
        page.keyboard.press("o")
        page.wait_for_selector(".sp-overview")
        labels = page.locator(".sp-recent-item").all_inner_texts()
        assert any("（追加ページ）" in t for t in labels), labels


def test_removed_added_page_in_places_falls_back(browser, generic_dir):
    with session(browser, proposal(generic_dir, "#p03")) as page:
        start_writing(page)
        add_page(page)
        tool(page, "ひとつ戻す").click()             # 書いていない追加ページ：ページごと消えて前のページへ
        assert (st(page)["index"], st(page)["add"]) == (2, None)
        assert len([p for p in page.evaluate("__sp.pages()") if p["add"]]) == 0
        page.keyboard.press("ArrowLeft")             # 消えた追加ページの場所：元の3枚目に着く
        assert (st(page)["index"], st(page)["add"]) == (2, None)
        assert pos(page) == "3 / 9"
        page.keyboard.press("ArrowRight")
        assert (st(page)["index"], st(page)["add"]) == (2, None)
        page.keyboard.press("ArrowLeft")
        before = page.evaluate("__sp.places()")
        page.reload()
        page.wait_for_function("!!window.__sp")
        assert (st(page)["index"], st(page)["add"]) == (2, None)
        after = page.evaluate("__sp.places()")
        assert len(after["items"]) == len(before["items"])
        assert "add" not in after["items"][after["pos"]]


# ---- 一覧つき・縮小一覧 ----

def test_side_and_overview_list_added_pages(browser, generic_dir):
    with session(browser, proposal(generic_dir, "#p03")) as page:
        start_writing(page)
        add_page(page)
        a = st(page)["add"]
        stroke(page, LINE)                           # 追加ページの書き込みは、どのサムネイルにも入らない
        page.keyboard.press("t")
        page.wait_for_selector(".sp-side")
        items = page.locator(".sp-side-item")
        assert items.count() == 10
        item = items.nth(3)
        assert item.get_attribute("data-add") == a and item.get_attribute("data-index") == "2"
        assert "白紙" in item.inner_text() or "白紙" in item.locator(".sp-side-frame").inner_text()
        assert item.locator(".sp-side-caption").inner_text() == "（追加ページ）"
        assert "sp-current" in item.get_attribute("class")
        assert items.nth(2).get_attribute("data-add") is None and "sp-current" not in items.nth(2).get_attribute("class")
        assert page.locator(".sp-side canvas.sp-ink, .sp-side canvas").count() == 0
        items.nth(2).click()
        assert (st(page)["index"], st(page)["add"]) == (2, None)
        assert "sp-current" in items.nth(2).get_attribute("class")
        items.nth(3).click()
        assert (st(page)["index"], st(page)["add"]) == (2, a)
        assert "sp-current" in items.nth(3).get_attribute("class")
        # 足すと開いている一覧にも入る
        add_page(page)
        assert page.locator(".sp-side-item").count() == 11
        assert page.locator(".sp-side-item").nth(4).locator(".sp-side-caption").inner_text() == "（追加ページ 2）"
        tool(page, DEL_BTN).click()
        assert page.locator(".sp-side-item").count() == 10
        page.keyboard.press("t")
        # 縮小一覧
        page.keyboard.press("ArrowUp")               # 3枚目へ
        assert st(page)["add"] is None
        page.keyboard.press("o")
        page.wait_for_selector(".sp-overview")
        assert page.locator(".sp-thumb").count() == 10
        assert page.locator(".sp-thumb canvas").count() == 0
        thumb = page.locator(".sp-thumb").nth(3)
        assert thumb.get_attribute("data-add") == a and thumb.locator(".sp-thumb-caption").inner_text() == "（追加ページ）"
        assert "白紙" in thumb.inner_text()
        page.keyboard.press("ArrowRight")
        assert page.locator(".sp-thumb.sp-selected").get_attribute("data-add") == a
        page.keyboard.press("Enter")
        assert (st(page)["index"], st(page)["add"]) == (2, a)
        assert page.query_selector(".sp-overview") is None
        # 追加ページが現在のとき、縮小一覧でも印が付く
        page.keyboard.press("o")
        page.wait_for_selector(".sp-overview")
        assert page.locator(".sp-thumb.sp-current").get_attribute("data-add") == a
        page.keyboard.press("ArrowRight")
        page.keyboard.press("Enter")
        assert st(page)["index"] == 3 and st(page)["add"] is None


# ---- N・M・L ----

def test_notes_memo_links_on_added_page(browser, generic_dir):
    with session(browser, proposal(generic_dir, "#p04"), viewport=(1440, 900)) as page:
        page.keyboard.press("m")
        page.wait_for_selector("textarea.sp-memo-text")
        page.click("textarea.sp-memo-text")
        page.keyboard.type("四枚目ではなく五枚目のメモ")
        page.wait_for_timeout(700)
        page.keyboard.press("Escape")
        page.keyboard.press("n")
        page.wait_for_selector(".sp-notes")
        page.click(".sp-notes-own-toggle")
        before = other_storage(page)
        assert before
        start_writing(page)
        add_page(page)
        title = page.inner_text(".sp-notes-title")
        assert title == "（追加ページ）"
        assert page.inner_text(".sp-notes-body").strip() in ("", "ノートはありません")
        assert page.evaluate("""() => { const b = document.querySelector('.sp-notes-own-toggle'); return !b || b.offsetParent === null; }""")
        assert page.evaluate("""() => { const t = document.querySelector('.sp-notes-memo'); return !t || t.offsetParent === null; }""")
        memo = page.locator("textarea.sp-memo-text")
        assert memo.evaluate("t => t.readOnly") is True
        assert memo.get_attribute("placeholder") == "追加ページにはメモを書けません"
        assert memo.input_value() == ""
        page.click("textarea.sp-memo-text", force=True)
        page.keyboard.type("書けない")
        page.wait_for_timeout(700)
        assert memo.input_value() == ""
        page.keyboard.press("Escape")
        assert other_storage(page) == before
        # L：リンクがないときと同じ知らせ
        page.keyboard.press("l")
        assert toast(page) == "このスライドに、いま押せるリンクはありません"
        assert page.evaluate("__sp.overlay()") != "links"
        # 元のスライドへ戻ると、メモは元のまま
        page.keyboard.press("ArrowUp")
        assert st(page)["add"] is None
        assert memo.evaluate("t => t.readOnly") is False
        assert memo.input_value() == "四枚目ではなく五枚目のメモ"
        assert other_storage(page) == before
        page.keyboard.press("l")
        page.wait_for_selector(".sp-linkview")


# ---- 動き ----

def test_no_motion_to_added_page(moving, generic_dir):
    with moving(motion_url(generic_dir, "#m03")) as page:
        page.keyboard.press("ArrowDown")
        assert page.evaluate("__sp.motion().kind") == "next"       # 対照：ふつうの送りは動く
        page.evaluate("__sp.motionDone()")
        page.keyboard.press("ArrowUp")
        page.evaluate("__sp.motionDone()")
        start_writing(page)
        add_page(page)
        assert st(page)["add"] and page.evaluate("__sp.motion().kind") == "none"
        page.keyboard.press("ArrowUp")
        assert st(page)["add"] is None and page.evaluate("__sp.motion().kind") == "none"
        page.keyboard.press("ArrowDown")
        assert st(page)["add"] and page.evaluate("__sp.motion().kind") == "none"
        page.keyboard.press("ArrowDown")                            # 追加ページから次のスライドへ：動きはないが、入場は今どおり
        assert st(page)["add"] is None and st(page)["id"] == "m04"
        assert page.evaluate("__sp.motion().kind") == "none"
        assert page.evaluate("__sp.entry().style") == "bounce"


# ---- 消す ----

def test_remove_added_page(browser, generic_dir):
    with session(browser, proposal(generic_dir, "#p03")) as page:
        dialogs = []
        action = {"accept": True}
        page.on("dialog", lambda d: (dialogs.append(d.message), d.accept() if action["accept"] else d.dismiss()))
        start_writing(page)
        add_page(page)
        a = st(page)["add"]
        assert tool(page, DEL_BTN).is_visible()
        stroke(page, LINE)
        assert writing(page)["count"] == 1
        action["accept"] = False                                     # キャンセル：残る
        tool(page, DEL_BTN).click()
        assert dialogs == [CONFIRM]
        assert st(page)["add"] == a and writing(page)["count"] == 1
        action["accept"] = True                                      # OK：消えて前のページへ
        tool(page, DEL_BTN).click()
        assert dialogs == [CONFIRM, CONFIRM]
        assert (st(page)["index"], st(page)["add"]) == (2, None)
        assert [p for p in page.evaluate("__sp.pages()") if p["add"]] == []
        assert not tool(page, DEL_BTN).is_visible()
        assert page.evaluate("__sp.writing().page") == "s:p03"
        # 書いていないときは確認なしで消える
        add_page(page)
        tool(page, DEL_BTN).click()
        assert len(dialogs) == 2
        assert (st(page)["index"], st(page)["add"]) == (2, None)
        # 1つ目を消すと、2つ目が1つ目になる。消すと前の追加ページへ戻る
        add_page(page)
        add_page(page)
        second = st(page)["add"]
        stroke(page, LINE)
        tool(page, DEL_BTN).click()
        assert len(dialogs) == 3
        assert st(page)["add"] is not None and st(page)["add"] != second
        assert st(page)["label"] == "3（追加ページ） / 9"


def test_writing_is_per_added_page(browser, generic_dir):
    with session(browser, proposal(generic_dir, "#p03")) as page:
        start_writing(page)
        add_page(page)
        a = st(page)["add"]
        stroke(page, LINE)
        assert writing(page)["count"] == 1 and writing(page)["page"] == "a:" + a
        add_page(page)
        b = st(page)["add"]
        assert writing(page)["count"] == 0 and writing(page)["page"] == "a:" + b
        stroke(page, LINE)
        stroke(page, LINE2)
        assert writing(page)["count"] == 2
        page.keyboard.press("ArrowUp")
        assert writing(page)["count"] == 1
        page.keyboard.press("ArrowUp")
        assert writing(page)["page"] == "s:p03" and writing(page)["count"] == 0
        # ひとつ戻すも追加ページごと
        page.keyboard.press("ArrowDown")
        page.keyboard.press("ArrowDown")
        for _ in range(4):                                          # 2本の線：それぞれ「形に直した」「描いた」の2段
            tool(page, "ひとつ戻す").click()
        assert writing(page)["count"] == 0
        assert st(page)["add"] == b
        tool(page, "ひとつ戻す").click()                              # 戻すものがない：ページごと消えて前のページへ
        assert st(page)["add"] == a


def test_stage_untouched(browser, generic_dir):
    with session(browser, proposal(generic_dir, "#p03")) as page:
        before = page.evaluate("document.getElementById('stage').innerHTML")
        assert before
        start_writing(page)
        add_page(page)
        assert page.evaluate("document.getElementById('stage').innerHTML") == before
        add_page(page)
        assert page.evaluate("document.getElementById('stage').innerHTML") == before
        page.keyboard.press("ArrowUp")
        assert page.evaluate("document.getElementById('stage').innerHTML") == before
        # 追加ページへ別のスライドから移っても、リンクの印は出ない
        on_slide(page, "#p04")
        add_page(page)
        assert page.locator(".sp-linkmark").count() == 0


def test_places_add_field_is_validated(browser, generic_dir):
    """保存した並びの項目の add は、形（x と数字）が合うときだけ読む。壊れた add の並びは捨てる（今の壊れた並びと同じ）。"""
    url = proposal(generic_dir, "#p03")
    base = {"vid": "abcdefgh1234", "page": url.split("#")[0], "kind": "deck", "ref": "p03", "step": 0}

    def load(item):
        text = json.dumps({"v": 1, "items": [item], "pos": 0, "restore": None})
        with page_session(browser, url.split("#")[0]) as page:
            page.evaluate("t => sessionStorage.setItem('sp-places-v1', t)", text)
            page.goto(url)
            page.reload()
            page.wait_for_function("!!window.__sp")
            return page.evaluate("__sp.places()")

    ok = load({**base, "add": "x12"})
    assert any(p["vid"] == "abcdefgh1234" and p.get("add") == "x12" for p in ok["items"])
    for broken in ("bad", "x", "x1234567", 12, None):
        got = load({**base, "add": broken})
        assert all(p["vid"] != "abcdefgh1234" for p in got["items"]), broken


# ---- 入力中の文字 ----

def type_text_on_added_page(page):
    """追加ページで右クリックの文字欄に文字を入れる（Enter で確定しない）。"""
    start_writing(page)
    add_page(page)
    page.mouse.click(600, 400, button="right")
    page.wait_for_selector("textarea.sp-write-text")
    page.keyboard.type("書きかけ")


def test_remove_button_commits_typing_first(browser, generic_dir):
    with session(browser, proposal(generic_dir, "#p03")) as page:
        dialogs, action = [], {"accept": False}
        page.on("dialog", lambda d: (dialogs.append(d.message), d.accept() if action["accept"] else d.dismiss()))
        type_text_on_added_page(page)
        a = st(page)["add"]
        tool(page, DEL_BTN).click()
        assert dialogs == [CONFIRM]                                  # 文字が書いたものとして確定されたので、確認が出る
        assert st(page)["add"] == a and writing(page)["count"] == 1
        assert writing(page)["objects"][0]["t"] == "text"
        action["accept"] = True
        tool(page, DEL_BTN).click()
        assert len(dialogs) == 2
        assert (st(page)["index"], st(page)["add"]) == (2, None)


def test_undo_commits_typing_then_undoes_only_text(browser, generic_dir):
    with session(browser, proposal(generic_dir, "#p03")) as page:
        type_text_on_added_page(page)
        a = st(page)["add"]
        tool(page, "ひとつ戻す").click()
        assert st(page)["add"] == a and writing(page)["count"] == 0   # 文字だけが戻る。追加ページは残る
        tool(page, "ひとつ戻す").click()
        assert st(page)["add"] is None                                # 次は履歴が空：ページごと消える


# ---- 識別子の衝突 ----

def test_new_add_id_skips_ids_in_saved_places(browser, generic_dir):
    url = proposal(generic_dir, "#p03")
    page_url = url.split("#")[0]
    item = {"vid": "abcdefgh1234", "page": page_url, "kind": "deck", "ref": "p03", "step": 0, "add": "x1"}
    seed = json.dumps({"v": 1, "items": [item], "pos": 0, "restore": None})
    with page_session(browser, "about:blank") as page:
        page.set_default_timeout(10000)
        page.add_init_script("Math.random = () => 0;")               # 連番の始まりを x1 に固定する
        page.goto(page_url)
        page.evaluate("t => sessionStorage.setItem('sp-places-v1', t)", seed)
        page.goto(url)
        page.reload()
        page.wait_for_function("!!window.__sp")
        start_writing(page)
        add_page(page)
        assert st(page)["add"] not in (None, "x1")
        page.keyboard.press("ArrowUp")
        for _ in range(3):                                           # 古い場所（x1）まで ← でさかのぼる：親のスライドに着く
            page.keyboard.press("ArrowLeft")
            if page.evaluate("__sp.places()")["pos"] == 0:
                break
        assert page.evaluate("__sp.places()")["pos"] == 0
        assert (st(page)["index"], st(page)["add"]) == (2, None)
