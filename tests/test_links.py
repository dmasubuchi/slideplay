"""リンクの試験（約束 §2.4・§3.3）。

見るのは player.js の外から見える動きだけ：画面の要素（data-sp-kind・.sp-linkview・.sp-linktag・.sp-more）、
キー操作、URL、sessionStorage、試験用の窓口 window.__sp。

試験の決め事：
- 試験台は examples/generic/proposal.html。p04＝4種類のリンクが全部ある、p05＝段階2から見えるリンク、
  p06＝場所のないリンク・壊れたリンク・許可しない種類のリンク・範囲外の番号の要素
- 操作ボタンは、ボタンを使う試験だけ「いつも出す」にする（ほかは出さない：クリックを覆わないように）
- クリップボード・新しいタブ・window.open は、ページごとに作る context（session）で確かめる
- 「何も起きなかった」ことの確認だけ、短い待ち（stays）を使う。ほかは待たずにその場で確かめる
"""
import json
from contextlib import contextmanager
from pathlib import Path

import pytest

from helpers import page_session

SETTINGS_KEY = "sp-settings-v1"
PLACES_KEY = "sp-places-v1"
CLIPBOARD = ["clipboard-read", "clipboard-write"]

# window.open を差し替えて、呼ばれ方を記録する（開く先の本物のタブは、別の試験で見る）
OPEN_RECORDER = "window.__opened = []; window.open = (...args) => { window.__opened.push(args); return null; };"

# proposal の題名（examples/generic/proposal.html）
TITLE = {"p01": "請求業務の効率化のご提案", "p02": "いまの請求業務の課題", "p05": "導入の効果", "p07": "導入後の進め方"}


# ---- 試験の道具 ----

@contextmanager
def session(browser, url, controls="never", init=None, permissions=(), viewport=(1440, 900)):
    """context を作って url を開く（設定は localStorage に先に入れる）。どのページが pageerror を出しても、抜けるときに失敗にする。

    https://example.com/ は、外に出ずに空のページを返す（external の本物のタブの試験のため）。
    """
    ctx = browser.new_context(viewport={"width": viewport[0], "height": viewport[1]}, device_scale_factor=1,
                              permissions=list(permissions), reduced_motion="reduce")      # 切り替えの動きは止める（test_motion.py が確かめる）
    errors = []
    ctx.on("page", lambda p: p.on("pageerror", lambda e: errors.append(f"{p.url}: {e}")))
    ctx.route("https://example.com/**", lambda r: r.fulfill(status=200, content_type="text/html", body="<title>example</title>"))
    value = json.dumps({"controls": controls, "notes": False})
    ctx.add_init_script(f"try {{ localStorage.setItem({json.dumps(SETTINGS_KEY)}, {json.dumps(value)}); }} catch (e) {{}}")
    if init:
        ctx.add_init_script(init)
    page = ctx.new_page()
    page.set_default_timeout(5000)                                # 動かないときに、長く待たずに失敗させる
    try:
        page.goto(url)
        yield page
    except BaseException as exc:
        ctx.close()
        if errors:
            raise AssertionError("ページが例外を出した:\n" + "\n".join(errors) + f"\n（試験の中でも例外が出た: {exc!r}）") from exc
        raise
    else:
        ctx.close()
        if errors:
            raise AssertionError("ページが例外を出した:\n" + "\n".join(errors))


def url_of(generic_dir, name="proposal.html", suffix=""):
    return (generic_dir / name).as_uri() + suffix


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


def listing(page):
    """直近の場所の並び（ref, step）と今の位置。"""
    p = places(page)
    return [(i["ref"], i["step"]) for i in p["items"]], p["pos"]


def toast_text(page):
    el = page.query_selector(".sp-toast")
    return el.inner_text() if el else None


def button(page, label):
    return page.locator(".sp-controls button", has_text=label).first


def spot(page, index):
    """舞台の上の data-link="index" の最初の要素。"""
    return page.locator(f'#stage [data-link="{index}"]').first


def marks(page):
    """舞台の上の data-link の要素の [番号, data-sp-kind]（文書の順）。"""
    return page.evaluate("""Array.from(document.querySelectorAll('#stage [data-link]'))
        .map(n => [n.getAttribute('data-link'), n.getAttribute('data-sp-kind')])""")


def badges(page):
    """印の文字の層にある [種類, リンクの番号, 文字]（層の中の順）。"""
    return page.evaluate("""Array.from(document.querySelectorAll('.sp-linkmarks .sp-linkmark'))
        .map(b => [b.dataset.kind, b.dataset.index, b.textContent])""")


def set_link(page, slide_id, index, **fields):
    """デッキの links の1件を書き換える（描き直した（別のスライドを経た）あとの印と、クリックの動きを見るため）。"""
    page.evaluate("""([id, i, fields]) => Object.assign(slideDeck.info.slides.find(s => s.id === id).links[i], fields)""",
                  [slide_id, index, fields])


def stays(page, url):
    """別のページへ移らなかったことの確認（移るなら、この短い間に始まる）。"""
    page.wait_for_timeout(300)
    assert page.url == url


def navigate(page, action):
    """action の結果の別のページへの移動を待ち、プレイヤーが動き出すまで待つ。"""
    with page.expect_navigation():
        action()
    page.wait_for_function("!!window.__sp")


def tag_texts(page):
    return page.locator(".sp-linktag").all_inner_texts()


def rect_of(page, selector):
    return page.evaluate("""s => { const r = document.querySelector(s).getBoundingClientRect();
        return {x: r.x, y: r.y, right: r.right, bottom: r.bottom}; }""", selector)


def active_in(page, selector):
    return page.evaluate("s => !!document.activeElement && !!document.activeElement.closest(s)", selector)


# ---- 印 ----

def test_marks_by_kind(browser, generic_dir):
    with session(browser, url_of(generic_dir, suffix="#p04")) as page:
        # 本文に出る順（導入後の進め方・用語・製品・事例・コマンド）で、番号と種類が対応する
        assert marks(page) == [["0", "jump"], ["3", "more"], ["2", "external"], ["1", "jump"], ["4", "copy"]]
        # 種類ごとに違う印の文字（→ ↗ ＋ ⧉）。舞台の中には足さず、舞台の外の層に重ねる（中身の配置を変えないため）
        assert sorted(badges(page)) == sorted([["jump", "0", "→"], ["more", "3", "＋"], ["external", "2", "↗"], ["jump", "1", "→"], ["copy", "4", "⧉"]])
        assert page.evaluate("document.querySelectorAll('#stage .sp-linkmark, #stage .sp-linkmarks').length") == 0
        assert page.evaluate("getComputedStyle(document.querySelector('#stage [data-link]'), '::after').content") in ("none", "normal")
        # 文字は、リンクの要素の右端の上（肩つき）にある。クリックを通す
        for dx, dy_center, hit in page.evaluate("""Array.from(document.querySelectorAll('.sp-linkmark')).map(b => {
                const n = document.querySelector('#stage [data-link="' + b.dataset.index + '"]').getBoundingClientRect(), r = b.getBoundingClientRect();
                const at = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2);
                return [r.left - n.right, (r.top + r.height / 2) - (n.top + n.height / 2), !!at && !!at.closest('.sp-linkmarks')]; })"""):
            assert -8 <= dx <= 8 and dy_center < 0 and not hit, (dx, dy_center, hit)
        # 押せるしるし（カーソル、焦点）
        assert page.evaluate("""Array.from(document.querySelectorAll('#stage [data-link]'))
            .every(n => getComputedStyle(n).cursor === 'pointer' && n.tabIndex === 0)""")
        # 舞台の外には、印も data-link もない（描いたものの外は変えない）
        assert page.evaluate("document.querySelectorAll('[data-sp-kind]').length") == 5


def test_marks_follow_rendering(browser, generic_dir):
    # 別のスライドへ動いても、段階だけ動いて描き直されても、印はそのスライドのリンクに付く（前のスライドの印は残らない）
    with session(browser, url_of(generic_dir, suffix="#p04")) as page:
        press(page, "Shift+ArrowDown")                              # p05 段階0：リンクは隠れているが、印は付く。印の文字は出ない（見えていない）
        assert marks(page) == [["0", "jump"]] and badges(page) == []
        assert press(page, "ArrowDown") == ("p05", 1) and marks(page) == [["0", "jump"]] and badges(page) == []    # 段階だけ動いて描き直された
        assert press(page, "ArrowDown") == ("p05", 2) and badges(page) == [["jump", "0", "→"]]                   # 見えると、印の文字も出る
        press(page, "Shift+ArrowDown")                              # p06
        assert marks(page) == [["1", "broken"], ["2", "broken"], ["9", None]]
        assert badges(page) == [["broken", "1", "⚠"], ["broken", "2", "⚠"]]      # 範囲外の番号の要素には出ない
        assert press(page, "Shift+ArrowUp") == ("p05", 3) and marks(page) == [["0", "jump"]] and badges(page) == [["jump", "0", "→"]]
        press(page, "Shift+ArrowUp")
        assert marks(page) == [["0", "jump"], ["3", "more"], ["2", "external"], ["1", "jump"], ["4", "copy"]] and len(badges(page)) == 5


def test_badges_follow_the_stage(browser, generic_dir):
    # N でノートを開くと舞台が縮んで動く。印の文字は、要素について行く（画面の大きさを変えたときも）
    def offsets(page):
        return page.evaluate("""Array.from(document.querySelectorAll('.sp-linkmark')).map(b => {
            const n = document.querySelector('#stage [data-link="' + b.dataset.index + '"]').getBoundingClientRect(), r = b.getBoundingClientRect();
            return [Math.round(r.left - n.right), Math.round(r.top - n.top)]; })""")
    with session(browser, url_of(generic_dir, suffix="#p04")) as page:
        before = page.evaluate("document.querySelector('.sp-linkmark').getBoundingClientRect().left")
        page.keyboard.press("n")
        assert page.query_selector(".sp-notes") is not None
        assert page.evaluate("document.querySelector('.sp-linkmark').getBoundingClientRect().left") != before        # 舞台が動いた
        assert all(-8 <= dx <= 8 and dy < 0 for dx, dy in offsets(page))
        page.set_viewport_size({"width": 900, "height": 700})
        assert all(-8 <= dx <= 8 and dy < 0 for dx, dy in offsets(page))
        assert len(badges(page)) == 5


def test_badges_are_covered_by_overlays(browser, generic_dir):
    # 印の文字の層は、モーダルの重なり（リンクを表示・補足）の下にある（舞台と一緒に暗くなる）
    with session(browser, url_of(generic_dir, suffix="#p04")) as page:
        page.keyboard.press("l")
        z = page.evaluate("""[getComputedStyle(document.querySelector('.sp-linkmarks')).zIndex, getComputedStyle(document.querySelector('.sp-linkview')).zIndex]""")
        assert int(z[0]) < int(z[1])


def test_no_marks_in_render_mode(browser, generic_dir):
    # ?render：印も、プレイヤーの部品も、CSS も出さない
    with page_session(browser, url_of(generic_dir, suffix="?render")) as page:
        page.evaluate("renderSlide(4, 0)")
        assert page.evaluate("document.querySelectorAll('#stage [data-link]').length") == 5
        assert page.evaluate("document.querySelectorAll('[data-sp-kind], [tabindex], .sp-style, .sp-linkmarks, .sp-linkmark').length") == 0
        assert page.evaluate("getComputedStyle(document.querySelector('#stage [data-link]')).cursor") != "pointer"
        assert page.evaluate("getComputedStyle(document.querySelector('#stage [data-link]'), '::after').content") in ("none", "normal")


# 印は中身の配置を変えない（約束 §3.2・§2.5）：通常の表示で、印の付いた要素の幅・行の高さ・折り返し・まわりの位置が、
# 印がないときと同じ。印を外した状態は、舞台の data-sp-kind を外すこと（印の CSS はすべてその属性に付いている）で作る
BOXES_WITH_AND_WITHOUT_MARKS = """() => {
    const boxes = () => Array.from(document.querySelectorAll('#stage, #stage *')).map(n => {
        const r = n.getBoundingClientRect();
        return [n.tagName + (n.className && typeof n.className === 'string' ? '.' + n.className.trim().split(/\\s+/).join('.') : ''), r.x, r.y, r.width, r.height];
    });
    const nodes = Array.from(document.querySelectorAll('#stage [data-sp-kind]'));
    const kinds = nodes.map(n => n.getAttribute('data-sp-kind'));
    const withMarks = boxes();
    nodes.forEach(n => n.removeAttribute('data-sp-kind'));
    const without = boxes();
    nodes.forEach((n, i) => n.setAttribute('data-sp-kind', kinds[i]));        // 元に戻す
    return {marked: nodes.length, withMarks, without};
}"""
LAYOUT_TOLERANCE = 0.5          # px（浮動小数点の誤差）


def layout_differences(page, slides, label):
    """全スライド・全段階で、印を付けたときと外したときの #stage の中の全要素の箱（x・y・幅・高さ）を比べる。

    返すもの：(違った箱の説明の一覧, 印の付いたスライド・段階の数, 比べた箱の数)
    """
    differences, marked_scenes, compared = [], 0, 0
    for slide in slides:
        for step in range(slide["steps"] + 1):
            page.evaluate(f"location.hash = '#{slide['id']}.{step}'")
            page.wait_for_function("([id, st]) => { const s = __sp.state(); return s.id === id && s.step === st; }", arg=[slide["id"], step])
            result = page.evaluate(BOXES_WITH_AND_WITHOUT_MARKS)
            if not result["marked"]:
                continue
            marked_scenes += 1
            assert len(result["withMarks"]) == len(result["without"])
            for i, (a, b) in enumerate(zip(result["withMarks"], result["without"])):
                compared += 1
                if a[0] != b[0] or any(abs(x - y) > LAYOUT_TOLERANCE for x, y in zip(a[1:], b[1:])):
                    differences.append(f"{label} {slide['id']} 段階 {step}: 要素[{i}] {a[0]} 印あり {[round(v, 1) for v in a[1:]]} / 印なし {[round(v, 1) for v in b[1:]]}")
    return differences, marked_scenes, compared


def test_marks_do_not_change_layout_proposal(browser, generic_dir):
    with session(browser, url_of(generic_dir, suffix="#p01"), viewport=(1920, 1080)) as page:
        slides = page.evaluate("slideDeck.info.slides.map(s => ({id: s.id, steps: s.steps}))")
        differences, marked_scenes, compared = layout_differences(page, slides, "proposal")
    assert not differences, f"{len(differences)} 件の箱が、印で変わった:\n" + "\n".join(differences[:12])
    assert marked_scenes >= 6 and compared > 50, (marked_scenes, compared)          # 比べずに通る空振りを防ぐ（p04・p05（4段階）・p06）


STAGE_BOXES = """() => Array.from(document.querySelectorAll('#stage, #stage *')).map(n => {
    const r = n.getBoundingClientRect();
    return [n.tagName + (n.className && typeof n.className === 'string' ? '.' + n.className.trim().split(/\\s+/).join('.') : ''), r.x, r.y, r.width, r.height];
})"""


def layout_vs_render(normal, render, slides, label):
    """通常の表示（印あり）と、?render（プレイヤーが何も足さない元の見た目）で、全スライド・全段階の #stage の中の全要素の箱を比べる。

    どちらも 1920×1080 の画面で、舞台は倍率 1・左上（0, 0）に置かれるので、座標がそのまま比べられる。返すもの：(違った箱の一覧, 印の付いた場面の数, 比べた箱の数)
    """
    differences, marked_scenes, compared = [], 0, 0
    for i, slide in enumerate(slides):
        for step in range(slide["steps"] + 1):
            normal.evaluate(f"location.hash = '#{slide['id']}.{step}'")
            normal.wait_for_function("([id, st]) => { const s = __sp.state(); return s.id === id && s.step === st; }", arg=[slide["id"], step])
            render.evaluate("([i, st]) => renderSlide(i, st)", [i, step])
            a, b = normal.evaluate(STAGE_BOXES), render.evaluate(STAGE_BOXES)
            marked_scenes += 1 if normal.evaluate("document.querySelectorAll('#stage [data-sp-kind]').length") else 0
            if len(a) != len(b):
                differences.append(f"{label} {slide['id']} 段階 {step}: 要素の数が違う {len(a)} / {len(b)}")
                continue
            for n, (x, y) in enumerate(zip(a, b)):
                compared += 1
                if x[0] != y[0] or any(abs(u - v) > LAYOUT_TOLERANCE for u, v in zip(x[1:], y[1:])):
                    differences.append(f"{label} {slide['id']} 段階 {step}: 要素[{n}] {x[0]} 通常 {[round(v, 1) for v in x[1:]]} / ?render {[round(v, 1) for v in y[1:]]}")
    return differences, marked_scenes, compared


def test_marks_do_not_change_layout_vs_render_proposal(browser, generic_dir):
    with session(browser, url_of(generic_dir, suffix="#p01"), viewport=(1920, 1080)) as normal, \
            page_session(browser, url_of(generic_dir, suffix="?render"), (1920, 1080)) as render:
        slides = normal.evaluate("slideDeck.info.slides.map(s => ({id: s.id, steps: s.steps}))")
        differences, marked_scenes, compared = layout_vs_render(normal, render, slides, "proposal")
    assert not differences, f"{len(differences)} 件の箱が、?render と違う:\n" + "\n".join(differences[:12])
    assert marked_scenes >= 6 and compared > 100, (marked_scenes, compared)


def test_marks_do_not_change_layout_detector_sees_a_change(browser, generic_dir):
    # 上の確かめが、本当に変化を見つけること：印の CSS に、幅を足す指定を加えると、違いが出る
    with session(browser, url_of(generic_dir, suffix="#p04"), viewport=(1920, 1080)) as page:
        page.add_style_tag(content="#stage [data-sp-kind] { padding-right: 20px; }")
        differences, marked_scenes, _ = layout_differences(page, [{"id": "p04", "steps": 0}], "proposal")
        assert marked_scenes == 1 and len(differences) >= 5


def test_thumbnails_have_no_link_behaviour(browser, generic_dir):
    # 縮小一覧のサムネイルのリンクの要素には、印も動きもない（inert のまま）。押すとそのスライドが開くだけ
    with session(browser, url_of(generic_dir, suffix="#p01"), init=OPEN_RECORDER) as page:
        page.keyboard.press("o")
        thumb = page.locator('.sp-thumb[data-index="4"]')
        assert thumb.locator("[data-link]").count() == 5
        assert thumb.locator("[data-sp-kind]").count() == 0 and thumb.locator("[tabindex='0']").count() == 0
        box = thumb.locator('[data-link="0"]').bounding_box()                 # 「導入後の進め方」（p07 へのリンク）
        page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        assert where(page) == ("p04", 0) and overlay(page) == "none"        # p07 へは飛ばない
        assert page.evaluate("__opened.length") == 0 and toast_text(page) is None


# ---- jump ----

def test_jump_same_deck(browser, generic_dir):
    with session(browser, url_of(generic_dir, suffix="#p04")) as page:
        spot(page, 0).click()
        assert where(page) == ("p07", 0)
        assert page.url.endswith("proposal.html#p07")
        assert listing(page) == ([("p04", 0), ("p07", 0)], 1)        # 直近の場所に足される
        assert press(page, "ArrowLeft") == ("p04", 0)                 # ← で戻れる
        assert overlay(page) == "none" and toast_text(page) is None


@pytest.mark.parametrize("target, expected", [
    ("p05.2", ("p05", 2)),          # 「ID.段階」
    ("p05.9", ("p05", 3)),          # 段階が範囲の外なら最後の段階
    ("p05.0", ("p05", 0)),
])
def test_jump_same_deck_with_step(browser, generic_dir, target, expected):
    with session(browser, url_of(generic_dir, suffix="#p04")) as page:
        set_link(page, "p04", 0, target=target)
        press(page, "ArrowDown")
        press(page, "ArrowUp")                                        # 描き直して、印を付け直す
        assert marks(page)[0] == ["0", "jump"]
        spot(page, 0).click()
        assert where(page) == expected


def test_jump_other_page(browser, generic_dir):
    with session(browser, url_of(generic_dir, suffix="#p04")) as page:
        navigate(page, spot(page, 1).click)
        assert page.url == url_of(generic_dir, "minimal.html", "#m1")
        assert where(page) == ("m1", 0)
        assert listing(page) == ([("p04", 0), ("m1", 0)], 1)          # 直近の場所は、ページをまたいで続く


def test_cross_page_link_clears_restore(browser, generic_dir):
    # 別のページへ移るリンクは、残っていた復元先を消してから移る（openPage を通る）。
    # 消えていなければ、移った先で復元先が使われ、新しい場所が足されずに前の場所に合ってしまう
    with session(browser, url_of(generic_dir, "minimal.html")) as page:
        navigate(page, lambda: page.goto(url_of(generic_dir, suffix="#p04")))
        first = places(page)["items"][0]["vid"]
        page.evaluate("""([key, vid]) => { const d = JSON.parse(sessionStorage.getItem(key));
            d.restore = {vid, t: Date.now()}; sessionStorage.setItem(key, JSON.stringify(d)); }""", [PLACES_KEY, first])
        navigate(page, spot(page, 1).click)
        assert listing(page) == ([("m1", 0), ("p04", 0), ("m1", 0)], 2)
        assert page.evaluate(f"JSON.parse(sessionStorage.getItem('{PLACES_KEY}')).restore") is None


# ---- external ----

def test_external_opens_new_tab(browser, generic_dir):
    # 本物の新しいタブが https://example.com/ で開く。もとのページは動かない
    with session(browser, url_of(generic_dir, suffix="#p04")) as page:
        before = page.url
        with page.context.expect_page() as info:
            spot(page, 2).click()
        tab = info.value
        tab.wait_for_load_state()
        assert tab.url == "https://example.com/"
        assert page.url == before and where(page) == ("p04", 0)
        assert listing(page) == ([("p04", 0)], 0)                      # 直近の場所に残らない


def test_external_window_open_arguments(browser, generic_dir):
    with session(browser, url_of(generic_dir, suffix="#p04"), init=OPEN_RECORDER) as page:
        spot(page, 2).click()
        assert page.evaluate("__opened") == [["https://example.com/", "_blank", "noopener"]]
        assert toast_text(page) is None


@pytest.mark.parametrize("target", [
    "javascript:alert(1)", "data:text/html,<script>alert(1)</script>", "ftp://example.com/x", "file:///etc/hosts",
    "//example.com/x", "example.com", "",
])
def test_external_only_http(browser, generic_dir, target):
    with session(browser, url_of(generic_dir, suffix="#p04"), init=OPEN_RECORDER) as page:
        set_link(page, "p04", 2, target=target)
        press(page, "ArrowDown")
        press(page, "ArrowUp")
        assert marks(page)[2] == ["2", "broken"]
        spot(page, 2).click()
        assert page.evaluate("__opened") == []
        assert toast_text(page) and where(page) == ("p04", 0)


# ---- more ----

def test_more_and_esc(browser, generic_dir):
    with session(browser, url_of(generic_dir, suffix="#p04")) as page:
        spot(page, 3).click()
        assert overlay(page) == "more"
        more = page.locator(".sp-more")
        assert more.locator(".sp-more-title").inner_text() == "突合とは"
        assert more.locator(".sp-more-text").inner_text() == \
            "請求書と注文書・納品書を照らし合わせて、金額や数量が合っているかを確かめる作業。"
        # 移動しない・直近の場所に残らない
        assert where(page) == ("p04", 0) and listing(page) == ([("p04", 0)], 0)
        # modal：移動のキーは効かない（焦点は窓の中にある。閉じるボタンに乗った Space はそのボタンを押す動作なので、ここでは試さない）
        for key in ["ArrowDown", "Space", "PageDown", "End", "l", "o"]:
            page.keyboard.press(key)
            assert overlay(page) == "more" and where(page) == ("p04", 0), key
        for key in ["Tab", "Tab", "Tab", "Shift+Tab"]:                # Tab は中だけを巡る
            page.keyboard.press(key)
            assert overlay(page) == "more" and active_in(page, ".sp-more"), key
        page.keyboard.press("Escape")
        assert overlay(page) == "none" and page.query_selector(".sp-more") is None
        assert page.evaluate("document.activeElement.getAttribute('data-link')") == "3"      # 開いたリンクへ焦点が戻る
        assert press(page, "ArrowDown") == ("p05", 0)                                         # 閉じたあとは動く


def test_more_opens_with_enter_and_closes_on_backdrop_and_button(browser, generic_dir):
    with session(browser, url_of(generic_dir, suffix="#p04")) as page:
        spot(page, 3).focus()
        page.keyboard.press("Enter")
        assert overlay(page) == "more"
        page.mouse.click(5, 5)                                       # 背景
        assert overlay(page) == "none"
        spot(page, 3).focus()
        page.keyboard.press("Enter")
        page.locator(".sp-more button", has_text="閉じる").click()
        assert overlay(page) == "none" and where(page) == ("p04", 0)


def test_more_text_is_not_html(browser, generic_dir):
    with session(browser, url_of(generic_dir, suffix="#p04")) as page:
        text = "<img src=x onerror=alert(1)><b>太字</b>"
        set_link(page, "p04", 3, text=text, title="<i>題</i>")
        spot(page, 3).click()
        assert page.locator(".sp-more-text").inner_text() == text
        assert page.locator(".sp-more-title").inner_text() == "<i>題</i>"
        assert page.locator(".sp-more b, .sp-more i, .sp-more img").count() == 0


def test_more_title_falls_back_to_label(browser, generic_dir):
    with session(browser, url_of(generic_dir, suffix="#p04")) as page:
        set_link(page, "p04", 3, title="")
        spot(page, 3).click()
        assert page.locator(".sp-more-title").inner_text() == "用語：突合"


# ---- copy ----

def test_copy_success(browser, generic_dir):
    with session(browser, url_of(generic_dir, suffix="#p04"), permissions=CLIPBOARD) as page:
        spot(page, 4).click()
        page.wait_for_function("!!document.querySelector('.sp-toast')")
        assert toast_text(page) == "コピーしました"
        assert page.evaluate("navigator.clipboard.readText()") == "npm install"
        assert overlay(page) == "none" and page.query_selector(".sp-more") is None    # 写せたときは重ねて出さない
        assert where(page) == ("p04", 0) and listing(page) == ([("p04", 0)], 0)       # 移動しない


def fake_clipboard(write):
    return f"Object.defineProperty(navigator, 'clipboard', {{value: {{writeText: {write}}}, configurable: true}});"


COPY_REJECTS = fake_clipboard("() => Promise.reject(new DOMException('denied', 'NotAllowedError'))")
COPY_THROWS = fake_clipboard("() => { throw new Error('blocked'); }")
COPY_ABSENT = "Object.defineProperty(navigator, 'clipboard', {value: undefined, configurable: true});"


@pytest.mark.parametrize("init", [COPY_REJECTS, COPY_THROWS, COPY_ABSENT], ids=["reject", "throw", "absent"])
def test_copy_failure(browser, generic_dir, init):
    with session(browser, url_of(generic_dir, suffix="#p04"), init=init) as page:
        spot(page, 4).click()
        page.wait_for_selector(".sp-more")
        assert overlay(page) == "more"
        assert page.locator(".sp-more-text").inner_text() == "npm install"
        assert "手でコピーしてください" in page.locator(".sp-more").inner_text()
        assert page.evaluate("window.getSelection().toString()") == "npm install"     # 文字が選ばれている
        assert toast_text(page) is None                                                # 成功とは知らせない
        page.keyboard.press("Escape")
        assert overlay(page) == "none"


def test_copy_failure_keeps_selection_when_focus_moves(browser, generic_dir):
    # Tab で動いても、選んだ文字が残る（手で写せる）
    with session(browser, url_of(generic_dir, suffix="#p04"), init=COPY_REJECTS) as page:
        spot(page, 4).click()
        page.wait_for_selector(".sp-more")
        assert page.evaluate("window.getSelection().toString()") == "npm install"
        page.keyboard.press("Tab")
        assert page.evaluate("window.getSelection().toString()") == "npm install"


# ---- 壊れたリンク・許可しない種類・範囲外 ----

def test_broken_link(browser, generic_dir):
    with session(browser, url_of(generic_dir, suffix="#p06")) as page:
        assert dict((n, k) for n, k in marks(page))["1"] == "broken"
        before = (where(page), listing(page), page.url)
        spot(page, 1).click()
        assert "p99" in toast_text(page)
        assert (where(page), listing(page), page.url) == before
        assert overlay(page) == "none"
        assert badges(page) == [["broken", "1", "⚠"], ["broken", "2", "⚠"]]


def test_blocked_scheme(browser, generic_dir):
    dialogs = []
    with session(browser, url_of(generic_dir, suffix="#p06"), init=OPEN_RECORDER) as page:
        page.on("dialog", lambda d: (dialogs.append(d.message), d.dismiss()))
        page.evaluate("window.__alive = true")
        before = (where(page), listing(page), page.url)
        spot(page, 2).click()
        assert toast_text(page)
        stays(page, before[2])
        assert dialogs == [] and page.evaluate("window.__alive") is True       # alert が出ず、ページが入れ替わっていない
        assert (where(page), listing(page)) == before[:2]
        assert page.evaluate("__opened") == [] and len(page.context.pages) == 1


@pytest.mark.parametrize("target", [
    "data:text/html,<script>alert(1)</script>", "vbscript:msgbox(1)", "mailto:a@example.com", "blob:null/abc", "ftp://example.com/x", "javascript:alert(1)",
])
def test_blocked_schemes_in_jump(browser, generic_dir, target):
    dialogs = []
    with session(browser, url_of(generic_dir, suffix="#p04")) as page:
        page.on("dialog", lambda d: (dialogs.append(d.message), d.dismiss()))
        page.evaluate("window.__alive = true")
        set_link(page, "p04", 0, target=target)
        press(page, "ArrowDown")
        press(page, "ArrowUp")
        spot(page, 0).click()
        assert toast_text(page)
        stays(page, url_of(generic_dir, suffix="#p04"))
        assert dialogs == [] and page.evaluate("window.__alive") is True and where(page) == ("p04", 0)


def test_empty_jump_target_does_not_move(browser, generic_dir):
    with session(browser, url_of(generic_dir, suffix="#p04")) as page:
        set_link(page, "p04", 0, target="")
        press(page, "ArrowDown")
        press(page, "ArrowUp")
        spot(page, 0).click()
        assert toast_text(page)
        stays(page, url_of(generic_dir, suffix="#p04"))
        assert where(page) == ("p04", 0)


def test_out_of_range_index(browser, generic_dir):
    with session(browser, url_of(generic_dir, suffix="#p06")) as page:
        extra = spot(page, 9)
        assert extra.get_attribute("data-sp-kind") is None and extra.get_attribute("tabindex") is None
        assert page.evaluate("getComputedStyle(document.querySelector('#stage [data-link=\"9\"]')).cursor") != "pointer"
        before = (where(page), listing(page), page.url)
        extra.click()
        page.keyboard.press("Enter")
        assert (where(page), listing(page), page.url) == before
        assert toast_text(page) is None and overlay(page) == "none"
        # 番号が整数でない要素も同じ
        page.evaluate("""() => { const n = document.createElement('span'); n.setAttribute('data-link', 'x'); n.textContent = 'x';
            document.getElementById('stage').appendChild(n); n.click(); }""")
        assert toast_text(page) is None and where(page) == before[0]


# ---- 別のページへ移ってよい URL の種類は 1 か所（LINK_PAGE_SCHEMES）----

PLAYER_JS = Path(__file__).resolve().parents[1] / "player" / "player.js"


def test_allowed_page_schemes_are_listed_once():
    # リンクの jump・目次のカード・H の目次・保存した場所のページが、同じ一覧を使う（別々に書き写さない）
    source = PLAYER_JS.read_text(encoding="utf-8")
    assert source.count("'file:'") == 1 and source.count("'https:'") == 2       # 一覧の 1 か所と、外部リンク（http・https だけ）の 1 か所
    assert source.count("LINK_PAGE_SCHEMES") >= 5                             # 定義 1 + 使う 4（リンク・カード・H・保存した場所）


@pytest.mark.parametrize("target", ["ftp://example.com/x", "data:text/html,x", "mailto:a@example.com", "blob:null/x", "javascript:void(0)"])
def test_unsupported_schemes_are_refused_at_every_entry_point(browser, generic_dir, tmp_path, target):
    # 許可していない種類の URL は、どの入り口からも別のページへ移れない：リンクの jump・目次のカード・H の目次
    with session(browser, url_of(generic_dir, suffix="#p04")) as page:                       # リンクの jump
        set_link(page, "p04", 0, target=target)
        press(page, "ArrowDown")
        press(page, "ArrowUp")
        assert marks(page)[0] == ["0", "broken"]
        spot(page, 0).click()
        stays(page, url_of(generic_dir, suffix="#p04"))
        assert toast_text(page) and where(page) == ("p04", 0)
    catalog = {"contract": 1, "title": "t", "decks": [{"id": "bad", "href": target, "title": "危ない"}]}
    payload = json.dumps(catalog, ensure_ascii=False)
    page_path = tmp_path / "index.html"                                                       # 目次のカード
    page_path.write_text(f'<!doctype html><html><head><meta charset="utf-8"></head><body><script>window.slideCatalog = {payload};</script>'
                         f'<script src="{PLAYER_JS.as_uri()}"></script></body></html>', encoding="utf-8")
    with session(browser, page_path.as_uri()) as page:
        page.keyboard.press("Enter")
        stays(page, page_path.as_uri() + "#bad")
        assert "開けません" in toast_text(page)
    html = (generic_dir / "proposal.html").read_text(encoding="utf-8")                       # H の目次
    html = html.replace('src="render.js"', f'src="{(generic_dir / "render.js").as_uri()}"')
    html = html.replace('src="../../player/player.js"', f'src="{PLAYER_JS.as_uri()}"').replace("home: 'index.html'", f"home: {json.dumps(target)}")
    home_path = tmp_path / "home.html"
    home_path.write_text(html, encoding="utf-8")
    with session(browser, home_path.as_uri()) as page:
        page.keyboard.press("h")
        stays(page, home_path.as_uri() + "#p01")


# ---- 段階で隠れたリンク ----

def test_hidden_link_inactive(browser, generic_dir):
    with session(browser, url_of(generic_dir, suffix="#p05")) as page:
        clickable = "document.querySelector('#stage [data-link=\"0\"]').click()"
        for step in (0, 1):
            assert where(page) == ("p05", step)
            assert page.evaluate("getComputedStyle(document.querySelector('#stage [data-link=\"0\"]')).visibility") == "hidden"
            page.evaluate(clickable)                                  # 隠れたままクリックの出来事だけ起こしても、何も起きない
            assert where(page) == ("p05", step) and toast_text(page) is None and overlay(page) == "none"
            press(page, "ArrowDown")
        assert where(page) == ("p05", 2)                              # 段階2：見えるので押せる
        page.evaluate(clickable)
        assert where(page) == ("p02", 0)


def test_hidden_link_not_clickable_with_mouse_and_keyboard(browser, generic_dir):
    with session(browser, url_of(generic_dir, suffix="#p05")) as page:
        box = page.evaluate("""(() => { const r = document.querySelector('#stage [data-link="0"]').getBoundingClientRect();
            return {x: r.x + r.width / 2, y: r.y + r.height / 2}; })()""")
        page.mouse.click(box["x"], box["y"])                          # 見えていない場所を押しても何も起きない
        assert where(page) == ("p05", 0) and toast_text(page) is None
        assert marks(page) == [["0", "jump"]]                         # （押せる印は付いている。隠れているので動かないだけ）
        page.evaluate("document.querySelector('#stage [data-link=\"0\"]').focus()")
        assert page.evaluate("document.activeElement === document.body")   # 隠れた要素には焦点が乗らない
        press(page, "Enter")
        assert where(page) == ("p05", 0)
        press(page, "ArrowDown")
        press(page, "ArrowDown")                                      # 段階2：同じ場所を押すと、リンクが開く（空振りでないことの確かめ）
        page.mouse.click(box["x"], box["y"])
        assert where(page) == ("p02", 0)


# ---- クリックの既定の動き（<a href> を使う中身、修飾キー、中ボタン） ----

# click の出来事の最後（document の泡の段階。プレイヤーの舞台の listener より後）で、既定の動きが止められていたかを記録する
RECORD_DEFAULT_PREVENTED = "window.__dp = []; document.addEventListener('click', e => window.__dp.push(e.defaultPrevented));"


def make_anchor(page, index, href):
    """舞台の data-link="index" の最初の要素を、<a href> に置き換える（中身が <a href> を data-link に使う場合）。"""
    page.evaluate("""([i, href]) => {
        const old = document.querySelector(`#stage [data-link="${i}"]`);
        const a = document.createElement('a');
        a.href = href;
        a.setAttribute('data-link', String(i));
        a.textContent = old.textContent;
        old.replaceWith(a);
    }""", [index, href])


def test_handled_click_prevents_default(browser, generic_dir):
    # プレイヤーがリンクとして扱ったクリックは preventDefault する。扱わなかったクリックは止めない
    with session(browser, url_of(generic_dir, suffix="#p04"), init=RECORD_DEFAULT_PREVENTED) as page:
        spot(page, 3).click()                                          # more：扱った
        assert page.evaluate("__dp") == [True]
        page.keyboard.press("Escape")
        page.mouse.click(40, 450)                                      # 舞台の余白（リンクではない）：止めない
        assert page.evaluate("__dp") == [True, False]
    with session(browser, url_of(generic_dir, suffix="#p06"), init=RECORD_DEFAULT_PREVENTED) as page:
        spot(page, 9).click()                                          # 範囲の外の番号：扱わない（中身自身の動きに任せる）
        assert page.evaluate("__dp") == [False]
    with session(browser, url_of(generic_dir, suffix="#p05"), init=RECORD_DEFAULT_PREVENTED) as page:
        page.evaluate("document.querySelector('#stage [data-link=\"0\"]').click()")      # 段階で隠れたリンク：扱わない
        assert page.evaluate("__dp") == [False]


def test_anchor_external_does_not_navigate_this_tab(browser, generic_dir):
    # 中身が <a href="https://…"> を data-link に使っても、このタブは移らない（新しいタブで 1 回だけ開く）
    with session(browser, url_of(generic_dir, suffix="#p04"), init=OPEN_RECORDER) as page:
        before = page.url
        make_anchor(page, 2, "https://example.com/")
        spot(page, 2).click()
        stays(page, before)
        assert page.evaluate("__opened") == [["https://example.com/", "_blank", "noopener"]]
        assert where(page) == ("p04", 0)


def test_anchor_jump_does_not_double_move(browser, generic_dir):
    # <a href="#p03"> を data-link に使い、リンクの先は p07：プレイヤーの移動だけが起きる（href の p03 へは移らない）
    with session(browser, url_of(generic_dir, suffix="#p04")) as page:
        make_anchor(page, 0, "#p03")
        spot(page, 0).click()
        assert where(page) == ("p07", 0) and page.url.endswith("#p07")
        assert listing(page) == ([("p04", 0), ("p07", 0)], 1)
        assert press(page, "ArrowLeft") == ("p04", 0)


def test_anchor_more_stays_open(browser, generic_dir):
    # <a href="#p03"> を data-link に使った more：補足の窓が開いたまま、スライドも移らない
    with session(browser, url_of(generic_dir, suffix="#p04")) as page:
        make_anchor(page, 3, "#p03")
        spot(page, 3).click()
        assert overlay(page) == "more" and where(page) == ("p04", 0) and page.url.endswith("#p04")
        stays(page, page.url)
        assert overlay(page) == "more" and where(page) == ("p04", 0)


def test_anchor_enter_does_not_double_move(browser, generic_dir):
    # Enter で <a> を押した（ブラウザが click を起こす）ときも、二重に移らない
    with session(browser, url_of(generic_dir, suffix="#p04")) as page:
        make_anchor(page, 0, "#p03")
        spot(page, 0).focus()
        assert press(page, "Enter") == ("p07", 0)
        assert listing(page) == ([("p04", 0), ("p07", 0)], 1)


def add_plain_anchor(page, href):
    """舞台の上に、data-link のない <a href> を足す（中身が本文に置く、ふつうのリンク）。"""
    page.evaluate("""href => {
        const a = document.createElement('a');
        a.className = 'plain';
        a.setAttribute('href', href);
        a.textContent = '本文のリンク';
        a.style.cssText = 'position:absolute;left:300px;top:20px;font-size:40px;z-index:5';
        document.getElementById('stage').appendChild(a);
    }""", href)


@pytest.mark.parametrize("href", ["#foo", "#", "#nope.3", "#p99"])
def test_content_hash_link_that_is_not_a_slide_does_nothing(browser, generic_dir, href):
    # 中身の <a href="#foo">（data-link でなく、スライドの hash でもない同じ文書の hash）：preventDefault して、先頭に戻らない
    with session(browser, url_of(generic_dir, suffix="#p04"), init=RECORD_DEFAULT_PREVENTED) as page:
        add_plain_anchor(page, href)
        page.locator("#stage a.plain").click()
        assert page.evaluate("__dp") == [True]
        stays(page, page.url)
        assert where(page) == ("p04", 0) and page.url.endswith("#p04")
        assert toast_text(page) is None and listing(page) == ([("p04", 0)], 0)


@pytest.mark.parametrize("href, expected", [("#p03", ("p03", 0)), ("#p05.2", ("p05", 2)), ("#3", ("p03", 0))])
def test_content_hash_link_to_a_slide_still_moves(browser, generic_dir, href, expected):
    # スライドの hash なら、今までどおりブラウザの hash の変更として移る（プレイヤーは止めない）
    with session(browser, url_of(generic_dir, suffix="#p04"), init=RECORD_DEFAULT_PREVENTED) as page:
        add_plain_anchor(page, href)
        page.locator("#stage a.plain").click()
        page.wait_for_function("__sp.state().id !== 'p04'")
        assert where(page) == expected and page.evaluate("__dp") == [False]


def test_content_link_to_another_page_is_left_alone(browser, generic_dir):
    # hash でない普通のリンク（別のページ）には触らない
    with session(browser, url_of(generic_dir, suffix="#p04"), init=RECORD_DEFAULT_PREVENTED) as page:
        add_plain_anchor(page, "minimal.html")
        with page.expect_navigation():
            page.locator("#stage a.plain").click()
        assert page.url.split("#")[0].endswith("/minimal.html")


@pytest.mark.parametrize("modifier", ["Shift", "Alt", "Control", "Meta"])
def test_modified_click_is_left_to_browser(browser, generic_dir, modifier):
    # Ctrl・Cmd・Shift・Alt を押したクリックは、プレイヤーが扱わず、ブラウザの既定の動きに任せる
    # （<a href> の新しいタブ・窓で開く、保存する、などを横取りしない）。リンクの動きも preventDefault もない
    with session(browser, url_of(generic_dir, suffix="#p04"), init=OPEN_RECORDER + RECORD_DEFAULT_PREVENTED) as page:
        for index in (0, 2, 3):                                        # jump・external・more
            spot(page, index).click(modifiers=[modifier])
        assert where(page) == ("p04", 0) and overlay(page) == "none" and toast_text(page) is None
        assert page.evaluate("__opened") == [] and True not in page.evaluate("__dp")        # （Mac の Control＋クリックは右クリックで、click は起きない）
        assert listing(page) == ([("p04", 0)], 0)


def test_ctrl_click_on_anchor_opens_only_a_native_tab(browser, generic_dir):
    # <a href> を Ctrl（Mac は Cmd）＋クリック：ブラウザの新しいタブが 1 つ開き、プレイヤーは window.open も移動もしない
    with session(browser, url_of(generic_dir, suffix="#p04"), init=OPEN_RECORDER) as page:
        before = page.url
        make_anchor(page, 2, "https://example.com/")
        with page.context.expect_page() as info:
            spot(page, 2).click(modifiers=["ControlOrMeta"])
        info.value.wait_for_url("https://example.com/")
        assert page.evaluate("__opened") == [] and page.url == before and where(page) == ("p04", 0)
        assert len(page.context.pages) == 2


def test_middle_click_is_left_to_browser(browser, generic_dir):
    # 中ボタンのクリック（auxclick）：プレイヤーは扱わない。<a href> ならブラウザが新しいタブで 1 つ開く
    with session(browser, url_of(generic_dir, suffix="#p04"), init=OPEN_RECORDER) as page:
        before = page.url
        spot(page, 0).click(button="middle")
        assert where(page) == ("p04", 0) and listing(page) == ([("p04", 0)], 0)
        make_anchor(page, 2, "https://example.com/")
        with page.context.expect_page() as info:
            spot(page, 2).click(button="middle")
        info.value.wait_for_url("https://example.com/")
        assert page.evaluate("__opened") == [] and page.url == before and len(page.context.pages) == 2


# ---- キーボード ----

def test_tab_reaches_links_in_order(browser, generic_dir):
    with session(browser, url_of(generic_dir, suffix="#p04"), controls="always") as page:
        order = []
        for _ in range(5):
            page.keyboard.press("Tab")
            order.append(page.evaluate("document.activeElement.getAttribute('data-link')"))
        assert order == ["0", "3", "2", "1", "4"]                     # 本文に出る順
        page.keyboard.press("Tab")
        assert active_in(page, ".sp-controls")                        # そのあとは操作ボタン


def test_enter_on_focused_link(browser, generic_dir):
    with session(browser, url_of(generic_dir, suffix="#p04")) as page:
        spot(page, 0).focus()
        assert press(page, "Enter") == ("p07", 0)
        assert listing(page) == ([("p04", 0), ("p07", 0)], 1)


def test_enter_on_focused_link_other_kinds(browser, generic_dir):
    with session(browser, url_of(generic_dir, suffix="#p04"), init=OPEN_RECORDER) as page:
        spot(page, 2).focus()
        page.keyboard.press("Enter")
        assert page.evaluate("__opened") == [["https://example.com/", "_blank", "noopener"]]      # 1回だけ
        spot(page, 3).focus()
        page.keyboard.press("Enter")
        assert overlay(page) == "more"


# 中身が data-link に使う要素の種類。描き直しのたびに、リンクの要素を指定の種類に置き換える（markLinks の前に。本物の中身と同じ順序）
WRAP_RENDER = """([index, tag, href]) => {
    const orig = slideDeck.render;
    slideDeck.render = function (ref, step, target) {
        orig.call(this, ref, step, target);
        const old = target.querySelector(`[data-link="${index}"]`);
        if (!old) return;
        const node = document.createElement(tag);
        if (href !== null) node.setAttribute('href', href);
        node.setAttribute('data-link', String(index));
        node.textContent = old.textContent;
        old.replaceWith(node);
    };
}"""
ELEMENT_KINDS = [("a", "https://example.com/"), ("a", None), ("span", None), ("button", None)]
ELEMENT_IDS = ["a-href", "a-without-href", "span", "button"]


def use_element_kind(page, index, tag, href):
    """リンク index の要素を tag（href があれば付ける）にして、p04 を描き直す（↓↑ で p05 を往復する）。"""
    page.evaluate(WRAP_RENDER, [index, tag, href])
    assert press(page, "ArrowDown") == ("p05", 0)
    assert press(page, "ArrowUp") == ("p04", 0)
    assert page.evaluate(f"document.querySelector('#stage [data-link=\"{index}\"]').tagName") == tag.upper()


def tab_to_link(page, index):
    for _ in range(8):
        page.keyboard.press("Tab")
        if page.evaluate("document.activeElement.getAttribute('data-link')") == str(index):
            return
    raise AssertionError(f"Tab で data-link={index} に着かない")


@pytest.mark.parametrize("tag, href", ELEMENT_KINDS, ids=ELEMENT_IDS)
def test_tab_enter_opens_once_and_space_advances(browser, generic_dir, tag, href):
    # href のある a・button は、Enter でブラウザが click を起こす（プレイヤーは二重にしない）。href のない a・span は、プレイヤーが開く。
    # どれも Tab→Enter でちょうど1回。Space は（リンクを開かず）規定の順序で進む
    with session(browser, url_of(generic_dir, suffix="#p04"), init=OPEN_RECORDER) as page:
        use_element_kind(page, 2, tag, href)                           # external（https://example.com/）
        tab_to_link(page, 2)
        page.keyboard.press("Enter")
        assert page.evaluate("__opened") == [["https://example.com/", "_blank", "noopener"]]      # ちょうど1回
        assert where(page) == ("p04", 0) and overlay(page) == "none"
        assert press(page, "Space") == ("p05", 0)                       # Space は次へ
        assert page.evaluate("__opened.length") == 1


@pytest.mark.parametrize("tag, href", ELEMENT_KINDS, ids=ELEMENT_IDS)
def test_tab_enter_jump_moves_once(browser, generic_dir, tag, href):
    # jump も同じ：リンク0（p07 へ）。移動は1回で、直近の場所に p07 が1つだけ足される
    with session(browser, url_of(generic_dir, suffix="#p04")) as page:
        use_element_kind(page, 0, tag, "#p03" if href else None)       # href のある a は、同じ文書の hash（p03）にする。移り先は p07
        before = listing(page)
        tab_to_link(page, 0)
        assert press(page, "Enter") == ("p07", 0)
        assert listing(page)[0] == before[0] + [("p07", 0)]


def test_enter_does_not_repeat(browser, generic_dir):
    with session(browser, url_of(generic_dir, suffix="#p04"), init=OPEN_RECORDER) as page:
        spot(page, 2).focus()
        page.keyboard.down("Enter")
        page.keyboard.down("Enter")                                   # 押しっぱなし（repeat）
        page.keyboard.up("Enter")
        assert page.evaluate("__opened.length") == 1


def test_space_on_focused_link_still_advances(browser, generic_dir):
    with session(browser, url_of(generic_dir, suffix="#p05.2")) as page:
        spot(page, 0).focus()
        assert page.evaluate("document.activeElement.getAttribute('data-link')") == "0"
        assert press(page, "Space") == ("p05", 3)                     # リンクは開かない。段階が進む
        assert listing(page)[0] == [("p05", 3)]


def test_enter_elsewhere_does_nothing(browser, generic_dir):
    with session(browser, url_of(generic_dir, suffix="#p04")) as page:
        assert press(page, "Enter") == ("p04", 0)
        assert toast_text(page) is None and overlay(page) == "none"


# ---- リンクを表示（L） ----

def test_link_view(browser, generic_dir):
    with session(browser, url_of(generic_dir, suffix="#p04")) as page:
        page.keyboard.press("l")
        assert overlay(page) == "links"
        view = page.locator(".sp-linkview")
        assert view.count() == 1
        # 舞台を暗くする
        assert page.evaluate("getComputedStyle(document.querySelector('.sp-linkview')).backgroundColor") not in (
            "rgba(0, 0, 0, 0)", "transparent")
        # 札の数がスライドのリンクの数と同じ。移動先が分かる（同じデッキは題名、別のページ・外部は URL、補足は題、コピーは文字）
        assert page.evaluate("slideDeck.info.slides.find(s => s.id === 'p04').links.length") == 5 == page.locator(".sp-linktag").count()
        assert sorted(tag_texts(page)) == sorted([
            TITLE["p07"], "minimal：m1", "https://example.com/", "突合とは", "コピー：npm install",
        ])
        assert page.locator(".sp-linklist-item").count() == 0        # 場所のないリンクはない
        # 各リンクの要素を枠で囲む：枠が要素を含み、少しだけ大きい
        frames = page.evaluate("""Array.from(document.querySelectorAll('.sp-linkframe')).map(f => {
            const n = document.querySelector('#stage [data-link="' + f.dataset.index + '"]').getBoundingClientRect();
            const r = f.getBoundingClientRect();
            return {l: n.left - r.left, t: n.top - r.top, r: r.right - n.right, b: r.bottom - n.bottom};
        })""")
        assert len(frames) == 5
        for f in frames:
            assert all(0 <= v <= 12 for v in f.values()), f
        # 開いている間は、スライドは動かない
        assert where(page) == ("p04", 0)
        page.keyboard.press("Escape")
        assert overlay(page) == "none" and page.query_selector(".sp-linkview") is None


@pytest.mark.parametrize("target,label", [
    ("minimal.html#m1", "minimal：m1"),
    ("../ch-02/slides.html#s20.2", "ch-02：s20・段階2"),           # slides は上のフォルダー名。段階があれば「・段階N」
    ("../s-03/slides.html#s12", "s-03：s12"),
    ("../idx/index.html#a1.3", "idx：a1・段階3"),
    ("minimal.html", "minimal"),                                  # hash がなければ、ページ名だけ
    ("minimal.html#12.0", "minimal"),                             # ID でない hash（旧形式の位置）も、ページ名だけ
    ("%E7%AC%AC2%E7%AB%A0/slides.html#s1", "第2章：s1"),
    ("100%/slides.html#p02", "100%：p02"),                        # 復号できない % を含むフォルダー：元の URL（手元のフルパス）は出さず、その文字のまま
    ("deck-100%/talk.html#s2", "talk：s2"),                       # ファイル名は復号できる。フォルダーの % は使わない
    ("50%.html#s3", "50%：s3"),                                   # 復号できないファイル名：生の文字列から拡張子を除く
])
def test_link_view_cross_page_tag_is_short_label(browser, generic_dir, target, label):
    # 別のページへ移る jump の札は、解決した file:/// の URL ではなく「ページ名：ID」（場所の列のラベルと同じ関数）
    with session(browser, url_of(generic_dir, suffix="#p04")) as page:
        set_link(page, "p04", 1, target=target)
        page.keyboard.press("l")
        tags = tag_texts(page)
        assert label in tags and not any(t.startswith("file:") for t in tags), tags
        assert "https://example.com/" in tags                          # 外部は URL のまま
        assert label in page.locator(".sp-linkframe[data-index='1']").get_attribute("aria-label")


def test_link_view_external_tag_is_shortened(browser, generic_dir):
    # 外部リンクの札も、長い URL は短くする（80 文字まで＋「…」）。短い URL はそのまま
    long_url = "https://example.com/" + "a" * 200 + "?q=1"
    with session(browser, url_of(generic_dir, suffix="#p04")) as page:
        set_link(page, "p04", 2, target=long_url)
        page.keyboard.press("l")
        tags = tag_texts(page)
        long_tags = [t for t in tags if t.startswith("https://example.com/aaa")]
        assert len(long_tags) == 1 and long_tags[0] == long_url[:80] + "…", tags
        assert page.locator(".sp-linkframe[data-index='2']").get_attribute("aria-label").endswith(long_tags[0])
        assert "https://example.com/" not in tags                       # 変えたのは1件だけ。ほかの外部リンクは元のまま
    with session(browser, url_of(generic_dir, suffix="#p04")) as page:
        page.keyboard.press("l")
        assert "https://example.com/" in tag_texts(page)                # 短い URL はそのまま


def test_link_view_toggles_with_l_and_button(browser, generic_dir):
    with session(browser, url_of(generic_dir, suffix="#p04"), controls="always") as page:
        assert button(page, "L リンク").get_attribute("aria-pressed") in (None, "false")
        page.keyboard.press("l")
        assert overlay(page) == "links" and button(page, "L リンク").get_attribute("aria-pressed") == "true"
        page.keyboard.press("l")
        assert overlay(page) == "none" and button(page, "L リンク").get_attribute("aria-pressed") == "false"
        page.keyboard.press("Shift+l")                                  # CapsLock・Shift の大文字も同じ
        assert overlay(page) == "links"
        page.keyboard.press("Escape")
        assert overlay(page) == "none"
        button(page, "L リンク").click()
        assert overlay(page) == "links"
        page.mouse.click(1400, 450)                                     # 背景を押しても閉じる（枠のない所）
        assert overlay(page) == "none" and button(page, "L リンク").get_attribute("aria-pressed") == "false"


def test_link_view_tags_for_place_less_and_broken(browser, generic_dir):
    with session(browser, url_of(generic_dir, suffix="#p06")) as page:
        page.keyboard.press("l")
        assert overlay(page) == "links"
        # 場所のあるリンク（壊れたもの・許可しない種類）は札、場所のないリンクは隅の一覧。範囲外の要素は出ない
        assert sorted(tag_texts(page)) == sorted(["見つからない：p99", "開けない：javascript:alert(1)"])
        items = page.locator(".sp-linklist-item")
        assert items.count() == 1
        assert items.first.inner_text().replace("\n", " ") == f"最初の画面に戻る {TITLE['p01']}"
        assert page.locator(".sp-linktag").count() + items.count() == 3 == page.evaluate(
            "slideDeck.info.slides.find(s => s.id === 'p06').links.length")
        assert page.locator(".sp-linkframe").count() == 2


def test_link_view_place_less_link_is_clickable(browser, generic_dir):
    with session(browser, url_of(generic_dir, suffix="#p06")) as page:
        page.keyboard.press("l")
        page.locator(".sp-linklist-item").first.click()
        assert overlay(page) == "none" and where(page) == ("p01", 0)
        assert listing(page) == ([("p06", 0), ("p01", 0)], 1)
        assert page.query_selector(".sp-linkview") is None


def test_link_view_frames_are_clickable(browser, generic_dir):
    with session(browser, url_of(generic_dir, suffix="#p04")) as page:
        page.keyboard.press("l")
        page.locator('.sp-linkframe[data-index="0"]').click()
        assert overlay(page) == "none" and where(page) == ("p07", 0)


def test_link_view_more_and_copy_from_frames(browser, generic_dir):
    with session(browser, url_of(generic_dir, suffix="#p04"), init=COPY_REJECTS) as page:
        page.keyboard.press("l")
        page.locator('.sp-linkframe[data-index="3"]').click()           # 補足：一覧を閉じて、補足を出す
        assert overlay(page) == "more" and page.query_selector(".sp-linkview") is None
        page.keyboard.press("Escape")
        page.keyboard.press("l")
        page.locator('.sp-linkframe[data-index="4"]').click()           # コピー（この試験では失敗する）
        page.wait_for_selector(".sp-more")
        assert page.locator(".sp-more-text").inner_text() == "npm install"


def test_link_view_broken_frame_gives_message(browser, generic_dir):
    with session(browser, url_of(generic_dir, suffix="#p06")) as page:
        page.keyboard.press("l")
        page.locator('.sp-linkframe[data-index="1"]').click()
        assert "p99" in toast_text(page) and where(page) == ("p06", 0)


def test_link_view_is_modal_with_tab_cycle_and_focus_restore(browser, generic_dir):
    with session(browser, url_of(generic_dir, suffix="#p04"), controls="always") as page:
        button(page, "L リンク").focus()
        page.keyboard.press("Enter")                                    # ボタンをキーボードで押して開く
        assert overlay(page) == "links" and active_in(page, ".sp-linkview")
        seen = set()
        for key in ["Tab"] * 15 + ["Shift+Tab"] * 15:
            page.keyboard.press(key)
            assert active_in(page, ".sp-linkview"), key
            seen.add(page.evaluate("document.activeElement.outerHTML.slice(0, 120)"))
        assert len(seen) >= 6                                            # 閉じる＋5つの枠を巡る
        assert page.evaluate("document.activeElement.closest('.sp-controls')") is None
        # 移動のキーは効かない（? Esc N F と、L だけが効く）。枠のボタンに乗った Space・Enter はそのボタンを押す動作なので、焦点を重なりの根へ戻して試す
        page.evaluate("document.querySelector('.sp-linkview').focus()")
        before = (where(page), listing(page), page.url)
        for key in ["ArrowDown", "ArrowUp", "ArrowLeft", "ArrowRight", "Space", "PageDown", "End", "Home", "o", "h",
                    "Shift+ArrowDown"]:
            page.keyboard.press(key)
            assert overlay(page) == "links", key
            assert (where(page), listing(page), page.url) == before, key
        page.keyboard.press("Escape")
        assert overlay(page) == "none"
        assert page.evaluate("document.activeElement.textContent") == "L リンク"      # 開く前の焦点へ戻る


def test_link_view_focus_returns_after_following(browser, generic_dir):
    with session(browser, url_of(generic_dir, suffix="#p04"), controls="always") as page:
        button(page, "L リンク").focus()
        page.keyboard.press("Enter")
        page.locator('.sp-linkframe[data-index="3"]').focus()
        page.keyboard.press("Enter")                                    # 枠の上の Enter：そのリンクを開く
        assert overlay(page) == "more"
        page.keyboard.press("Escape")
        assert page.evaluate("document.activeElement.textContent") == "L リンク"


def test_link_view_over_notes_and_help(browser, generic_dir):
    with session(browser, url_of(generic_dir, suffix="#p04")) as page:
        page.keyboard.press("l")
        page.keyboard.press("?")                                         # 操作の一覧は上に重なる
        assert overlay(page) == "help"
        page.keyboard.press("Escape")
        assert overlay(page) == "links"
        page.keyboard.press("Escape")
        assert overlay(page) == "none"


def test_link_view_follows_notes_toggle(browser, generic_dir):
    # N でノートを開くと舞台が縮んで動く。枠は要素に付いてくる
    with session(browser, url_of(generic_dir, suffix="#p04")) as page:
        page.keyboard.press("l")
        page.keyboard.press("n")
        assert overlay(page) == "links" and page.query_selector(".sp-notes") is not None
        for index in range(5):
            node = rect_of(page, f'#stage [data-link="{index}"]')
            frame = rect_of(page, f'.sp-linkframe[data-index="{index}"]')
            assert frame["x"] <= node["x"] + 0.5 and frame["right"] >= node["right"] - 0.5, index
            assert frame["y"] <= node["y"] + 0.5 and frame["bottom"] >= node["bottom"] - 0.5, index
            assert node["x"] - frame["x"] < 12 and node["y"] - frame["y"] < 12, index
        # 隅の一覧は、ノートの左に置く（ノートに重ならない）
        assert rect_of(page, ".sp-linkpanel")["right"] <= rect_of(page, ".sp-notes")["x"]


def test_link_view_closes_when_slide_changes(browser, generic_dir):
    # ブラウザの戻るなどで場所が変わったら、見ている枠は古くなる。閉じる
    with session(browser, url_of(generic_dir, suffix="#p04")) as page:
        page.keyboard.press("l")
        assert overlay(page) == "links"
        page.evaluate("window.__hc = 0; addEventListener('hashchange', () => window.__hc++)")      # プレイヤーの処理のあとに数える
        page.evaluate("location.hash = '#p05'")
        page.wait_for_function("window.__hc > 0")
        assert overlay(page) == "none" and page.query_selector(".sp-linkview") is None
        assert where(page) == ("p05", 0)


def test_link_view_tag_stays_on_screen(browser, generic_dir):
    # 画面の端でも札が見切れない（下に入らなければ上へ、右に入らなければ右そろえ）
    with session(browser, url_of(generic_dir, suffix="#p04"), viewport=(900, 560)) as page:
        page.keyboard.press("l")
        for r in page.evaluate("""Array.from(document.querySelectorAll('.sp-linktag')).map(t => {
                const r = t.getBoundingClientRect(); return {l: r.left, t: r.top, r: r.right, b: r.bottom}; })"""):
            assert r["l"] >= 0 and r["t"] >= 0 and r["r"] <= 900 and r["b"] <= 560, r


def test_link_view_with_nothing_to_show(browser, generic_dir):
    with session(browser, url_of(generic_dir, suffix="#p02")) as page:      # リンクのないスライド
        page.keyboard.press("l")
        assert overlay(page) == "none" and toast_text(page)
        assert where(page) == ("p02", 0)


def test_link_view_hides_links_hidden_by_step(browser, generic_dir):
    with session(browser, url_of(generic_dir, suffix="#p05")) as page:
        page.keyboard.press("l")
        assert overlay(page) == "none" and toast_text(page)                 # 段階0：隠れたリンクしかない。出さない
        assert page.locator(".sp-linklist-item").count() == 0
        press(page, "ArrowDown")
        press(page, "ArrowDown")                                            # 段階2：見える
        page.keyboard.press("l")
        assert overlay(page) == "links"
        assert tag_texts(page) == [TITLE["p02"]] and page.locator(".sp-linklist-item").count() == 0


def test_link_view_text_is_not_html(browser, generic_dir):
    with session(browser, url_of(generic_dir, suffix="#p04")) as page:
        set_link(page, "p04", 4, text="<b>x</b>")
        set_link(page, "p04", 3, title="<i>y</i>")
        page.keyboard.press("l")
        assert "コピー：<b>x</b>" in tag_texts(page) and "<i>y</i>" in tag_texts(page)
        assert page.locator(".sp-linkview b, .sp-linkview i").count() == 0


@pytest.mark.parametrize("target, suffix", [("p05.2", "（段階 2）"), ("p05.9", "（段階 3）"), ("p05.0", ""), ("p05", "")])
def test_link_view_jump_with_step_shows_step(browser, generic_dir, target, suffix):
    # 札には、同じデッキの題名に、0 でない段階を添える（範囲の外の段階は最後の段階にそろえた数）
    with session(browser, url_of(generic_dir, suffix="#p04")) as page:
        set_link(page, "p04", 0, target=target)
        press(page, "ArrowDown")
        press(page, "ArrowUp")
        page.keyboard.press("l")
        assert f"{TITLE['p05']}{suffix}" in tag_texts(page)
