"""PDF の書き出し（P）の試験。

ブラウザの印刷の画面は Playwright で扱えないので、window.print を差し替えて、呼ばれた時点の様子を window.__printed に残す。
PDF そのものは、beforeprint を起こして emulate_media(print) → page.pdf で作り、pypdf で寸法、PyMuPDF（pdf_check.py）で画像にして画面と比べる。

試験の決め事：
- 操作ボタンは「いつも出す」にして開く（ボタンから押す試験のため）
- 待ち（画像の decode）を試す試験は、init で HTMLImageElement.prototype.decode と slideDeck.render を差し替える
"""
import json
import unicodedata
from contextlib import contextmanager

import pytest

from helpers import page_session
from pdf_check import make_pdf, missing_parts, missing_text, pdf_pages, stage_image

SETTINGS_KEY = "sp-settings-v1"
PLACES_KEY = "sp-places-v1"
DECK_TITLE = "請求業務の効率化のご提案"
PRINT_TITLE = "提案書 " + DECK_TITLE
MSG_TIMEOUT = "画像の読み込みが終わらないので、PDF の書き出しをやめました"
MSG_FAILED = "印刷の画面を開けませんでした"
TITLES = ["請求業務の効率化のご提案", "いまの請求業務の課題", "課題が続いた場合の影響", "他社の事例（補足）", "ご提案する仕組み",
          "導入の効果", "費用と補足の資料", "導入後の進め方", "ご検討をお願いします"]

STUB = """
window.__printed = [];
window.print = () => window.__printed.push({
  boxes: document.querySelectorAll('.sp-print').length,
  pages: document.querySelectorAll('.sp-print .sp-print-page').length,
  targets: document.querySelectorAll('.sp-print .sp-print-page > .sp-target').length,
  title: document.title,
});
"""

# slideDeck.render を包む（deck 側の定義が window.slideDeck に代入された時点で包む）。BODY は (i, step, target, original) を使える関数の本体
WRAP_RENDER = """
(() => {
  let deck;
  Object.defineProperty(window, 'slideDeck', { configurable: true,
    get() { return deck; },
    set(v) {
      if (v && typeof v.render === 'function') {
        const original = v.render.bind(v);
        v.render = (i, step, target) => { %s };
      }
      deck = v;
    } });
})();
"""
IMG_ON_FIRST = "original(i, step, target); if (i === 0) { const im = document.createElement('img'); im.src = %s; target.appendChild(im); }"
GIF = "'data:image/gif;base64,R0lGODlhAQABAAAAACw='"
NEVER_DECODE = "HTMLImageElement.prototype.decode = () => new Promise(() => {});"
SLOW_DECODE = "HTMLImageElement.prototype.decode = () => new Promise(r => setTimeout(r, 1000));"


def wrap_render(body):
    return WRAP_RENDER % body


@contextmanager
def ui_session(browser, url, init=(), viewport=(1440, 900), controls="always"):
    """操作ボタンの出し方を localStorage に入れ、init の script を足してから url を開く。pageerror があれば失敗（page_session）。"""
    with page_session(browser, "about:blank", viewport=viewport) as page:
        value = json.dumps({"controls": controls, "notes": False})
        page.add_init_script(f"try {{ localStorage.setItem({json.dumps(SETTINGS_KEY)}, {json.dumps(value)}); }} catch (e) {{}}")
        for script in init:
            page.add_init_script(script)
        page.goto(url)
        page.wait_for_function("!!window.__sp")
        yield page


def proposal(generic_dir, suffix=""):
    return (generic_dir / "proposal.html").as_uri() + suffix


def printed(page):
    return page.evaluate("window.__printed")


def wait_printed(page, n=1):
    page.wait_for_function("n => window.__printed.length >= n", arg=n)


def boxes(page):
    return page.evaluate("document.querySelectorAll('.sp-print').length")


def after_print(page):
    page.evaluate("window.dispatchEvent(new Event('afterprint'))")


def toast_text(page):
    el = page.query_selector(".sp-toast")
    return el.inner_text() if el else None


def snapshot_of(page):
    return page.evaluate("""() => ({
        state: __sp.state(), hash: location.hash, places: sessionStorage.getItem('sp-places-v1'),
        settings: localStorage.getItem('sp-settings-v1'), stage: document.getElementById('stage').innerHTML,
        notes: !!document.querySelector('.sp-notes'), title: document.title,
    })""")


def press_p_and_wait(page):
    page.keyboard.press("p")
    wait_printed(page)


# ---- 印刷の回 ----

def test_p_key_builds_all_pages_then_prints(browser, generic_dir):
    with ui_session(browser, proposal(generic_dir), init=[STUB]) as page:
        press_p_and_wait(page)
        got = printed(page)
        assert len(got) == 1
        assert got[0] == {"boxes": 1, "pages": 9, "targets": 9, "title": PRINT_TITLE}
        same = page.evaluate("""() => Array.from(document.querySelectorAll('.sp-print .sp-print-page > .sp-target')).map((t, i) => {
            const d = document.createElement('div'); d.className = 'sp-target';
            slideDeck.render(i, slideDeck.info.slides[i].steps, d);
            return d.innerHTML !== '' && d.innerHTML === t.innerHTML;
        })""")
        assert same == [True] * 9


def test_button_prints_same_as_key(browser, generic_dir):
    with ui_session(browser, proposal(generic_dir), init=[STUB]) as page:
        page.locator(".sp-controls button", has_text="P PDF").click()
        wait_printed(page)
        assert printed(page) == [{"boxes": 1, "pages": 9, "targets": 9, "title": PRINT_TITLE}]


def test_afterprint_restores_everything(browser, generic_dir):
    with ui_session(browser, proposal(generic_dir, "#p02.1"), init=[STUB]) as page:
        page.keyboard.press("n")
        before = snapshot_of(page)
        assert before["notes"] and before["title"] == DECK_TITLE and before["state"]["id"] == "p02"
        press_p_and_wait(page)
        after_print(page)
        assert boxes(page) == 0
        assert snapshot_of(page) == before


def test_print_return_does_not_clean_up(browser, generic_dir):
    with ui_session(browser, proposal(generic_dir), init=[STUB]) as page:
        press_p_and_wait(page)
        page.wait_for_timeout(300)
        assert boxes(page) == 1
        assert page.title() == PRINT_TITLE


def test_double_press_prints_once(browser, generic_dir):
    # 準備中（画像の読み込み待ち）の P は受けない
    init = [STUB, SLOW_DECODE, wrap_render(IMG_ON_FIRST % GIF)]
    with ui_session(browser, proposal(generic_dir), init=init) as page:
        page.keyboard.press("p")
        page.keyboard.press("p")
        wait_printed(page)
        page.wait_for_timeout(300)
        assert len(printed(page)) == 1
        assert boxes(page) == 1


def test_cancel_then_second_print(browser, generic_dir):
    with ui_session(browser, proposal(generic_dir), init=[STUB]) as page:
        press_p_and_wait(page)
        after_print(page)
        assert page.title() == DECK_TITLE
        page.keyboard.press("p")
        wait_printed(page, 2)
        got = printed(page)
        assert len(got) == 2
        assert got[1] == {"boxes": 1, "pages": 9, "targets": 9, "title": PRINT_TITLE}
        after_print(page)
        assert page.title() == DECK_TITLE and boxes(page) == 0


def test_second_p_works_without_afterprint(browser, generic_dir):
    # afterprint が来ない環境でも、window.print() から戻ったあとの P は効く（入れ物は1つのまま、題名は最初に覚えたもの）
    with ui_session(browser, proposal(generic_dir), init=[STUB]) as page:
        press_p_and_wait(page)
        page.keyboard.press("p")
        wait_printed(page, 2)
        assert len(printed(page)) == 2 and boxes(page) == 1
        after_print(page)
        assert boxes(page) == 0 and page.title() == DECK_TITLE


def test_wait_timeout_aborts_with_message(browser, generic_dir):
    init = [STUB, NEVER_DECODE, wrap_render(IMG_ON_FIRST % GIF)]
    with ui_session(browser, proposal(generic_dir), init=init) as page:
        page.keyboard.press("p")
        page.wait_for_function("document.querySelector('.sp-toast')", timeout=8000)
        assert toast_text(page) == MSG_TIMEOUT
        assert printed(page) == []
        assert boxes(page) == 0
        assert page.title() == DECK_TITLE


def test_broken_image_does_not_abort(browser, generic_dir):
    init = [STUB, wrap_render(IMG_ON_FIRST % "'no-such-image.png'")]
    with ui_session(browser, proposal(generic_dir), init=init) as page:
        press_p_and_wait(page)
        assert len(printed(page)) == 1


def test_print_exception_cleans_up(browser, generic_dir):
    with ui_session(browser, proposal(generic_dir)) as page:
        page.evaluate("void (window.print = () => { throw new Error('no print'); })")
        page.keyboard.press("p")
        page.wait_for_function("document.querySelector('.sp-toast')")
        assert toast_text(page) == MSG_FAILED
        assert boxes(page) == 0
        assert page.title() == DECK_TITLE


def test_cmd_p_path_builds_on_beforeprint(browser, generic_dir):
    with ui_session(browser, proposal(generic_dir)) as page:
        page.evaluate("window.dispatchEvent(new Event('beforeprint'))")
        assert boxes(page) == 1
        assert page.evaluate("document.querySelectorAll('.sp-print .sp-print-page').length") == 9
        assert page.title() == PRINT_TITLE
        page.evaluate("window.dispatchEvent(new Event('beforeprint'))")        # 重ねて来ても1つのまま・題名は元を覚えたまま
        assert boxes(page) == 1
        after_print(page)
        assert boxes(page) == 0
        assert page.title() == DECK_TITLE


def test_cmd_p_during_wait_keeps_one_box(browser, generic_dir):
    init = [STUB, SLOW_DECODE, wrap_render(IMG_ON_FIRST % GIF)]
    with ui_session(browser, proposal(generic_dir), init=init) as page:
        page.keyboard.press("p")
        page.evaluate("window.dispatchEvent(new Event('beforeprint'))")
        assert boxes(page) == 1
        wait_printed(page)
        assert len(printed(page)) == 1 and boxes(page) == 1
        after_print(page)
        assert page.title() == DECK_TITLE and boxes(page) == 0


def test_stale_preparation_does_not_release_current(browser, generic_dir):
    # 古い準備 A の完了が、今の準備 B の「準備中」を解除してはいけない（P が2回印刷を呼ばない）
    hold = "window.__resolvers = []; HTMLImageElement.prototype.decode = () => new Promise(r => window.__resolvers.push(r));"
    init = [STUB, hold, wrap_render(IMG_ON_FIRST % GIF)]
    with ui_session(browser, proposal(generic_dir), init=init) as page:
        page.keyboard.press("p")                                            # A：画像の待ち
        page.wait_for_function("window.__resolvers.length === 1")
        page.evaluate("window.dispatchEvent(new Event('beforeprint')); window.dispatchEvent(new Event('afterprint'))")    # A の入れ物を片付ける
        assert boxes(page) == 0
        page.keyboard.press("p")                                            # B：画像の待ち
        page.wait_for_function("window.__resolvers.length === 2")
        page.evaluate("window.__resolvers[0]()")                            # A の待ちが終わる（古い回）
        page.wait_for_timeout(200)
        page.keyboard.press("p")                                            # B の準備中の P は受けない
        page.wait_for_timeout(200)
        assert page.evaluate("window.__resolvers.length") == 2
        page.evaluate("window.__resolvers[1]()")
        wait_printed(page)
        page.wait_for_timeout(300)
        assert len(printed(page)) == 1 and boxes(page) == 1


# ---- PDF の中身 ----

def test_pdf_pages_size_and_content(browser, generic_dir, tmp_path):
    from pypdf import PdfReader

    with ui_session(browser, proposal(generic_dir), viewport=(1920, 1080)) as page:
        page.keyboard.press("n")                                            # ノートを開いたままでも、PDF に入らない
        pdf = make_pdf(page, tmp_path / "proposal.pdf")
        reader = PdfReader(str(pdf))
        assert len(reader.pages) == 9
        for i, p in enumerate(reader.pages):
            assert abs(float(p.mediabox.width) - 1440) <= 0.5 and abs(float(p.mediabox.height) - 810) <= 0.5
            text = unicodedata.normalize('NFKC', p.extract_text())       # PDF の文字は康熙部首（⾜ など）で出ることがある
            assert unicodedata.normalize('NFKC', TITLES[i]) in text, f"{i + 1}ページ目に題名がない: {text[:80]!r}"
            assert "↓ 次" not in text and "ノート" not in text
        images = pdf_pages(pdf)
        assert missing_text(page, pdf) == []
        page.keyboard.press("n")                                            # 画面の側は、ノートを閉じて舞台を1920×1080 の等倍にして撮る
        for i, img in enumerate(images):
            assert missing_parts(img, stage_image(page, i)) == [], f"{i + 1}ページ目に欠けの疑い"


def test_missing_parts_finds_cut_page(browser, generic_dir):
    from PIL import Image

    with ui_session(browser, proposal(generic_dir), viewport=(1920, 1080)) as page:
        page.keyboard.press("n")
        for i in (1, 3, 4):                                                 # 表紙（0）と最後（8）は背景が白に近く、白で塗っても差が出ないので使わない
            stage = stage_image(page, i)
            assert missing_parts(stage.copy(), stage) == []
            bottom = stage.copy()
            bottom.paste(Image.new("RGB", (1920, 360), "white"), (0, 720))
            assert missing_parts(bottom, stage), f"{i + 1}枚目：下の 1/3 の欠けを見つけられない"
            right = stage.copy()
            right.paste(Image.new("RGB", (640, 1080), "white"), (1280, 0))
            assert missing_parts(right, stage), f"{i + 1}枚目：右の 1/3 の欠けを見つけられない"


def print_only_pdf(page, tmp_path, css):
    """印刷用の入れ物の中だけに css を当てて PDF にする（メインの舞台は元のまま）。"""
    page.add_style_tag(content=css)
    return make_pdf(page, tmp_path / "broken.pdf")


def test_text_check_finds_hidden_last_bullet(browser, generic_dir, tmp_path):
    # p05（6ページ目）の最後の箇条書きを印刷側だけ隠す。全体・帯の比べでは通ってしまう欠けを、文字の照合が見つける
    with ui_session(browser, proposal(generic_dir), viewport=(1920, 1080)) as page:
        pdf = print_only_pdf(page, tmp_path, ".sp-print .sp-print-page:nth-child(6) li:last-child { visibility: hidden !important; }")
        problems = missing_text(page, pdf)
        assert problems and all(p.startswith("6ページ目") for p in problems), problems
        assert any("浮いた時間" in p for p in problems), problems


@pytest.mark.parametrize("css", [
    ".sp-print .sp-print-page:nth-child(4) .col:first-child { visibility: hidden !important; }",        # 2 列のうち 1 列の箱ごと
    ".sp-print .sp-print-page:nth-child(4) .col:first-child ul { visibility: hidden !important; }",     # 1 列の箱の中の一覧だけ
])
def test_tile_check_finds_hidden_column(browser, generic_dir, tmp_path, css):
    with ui_session(browser, proposal(generic_dir), viewport=(1920, 1080)) as page:
        pdf = print_only_pdf(page, tmp_path, css)
        img = pdf_pages(pdf)[3]
        problems = missing_parts(img, stage_image(page, 3))
        assert any(p.startswith("小さい領域") for p in problems), problems


def test_render_failure_keeps_other_pages(browser, generic_dir):
    body = "if (target.id !== 'stage' && i === 1) throw new Error('boom'); return original(i, step, target);"
    with ui_session(browser, proposal(generic_dir), init=[STUB, wrap_render(body)]) as page:
        press_p_and_wait(page)
        assert printed(page)[0]["pages"] == 9
        result = page.evaluate("""() => Array.from(document.querySelectorAll('.sp-print .sp-print-page > .sp-target')).map(t => ({
            error: (t.querySelector('.sp-render-error') || {}).textContent || null, filled: t.children.length > 0 }))""")
        assert result[1]["error"] == "このスライドは表示できません（p02）"
        for i, r in enumerate(result):
            if i != 1:
                assert r["error"] is None and r["filled"], f"{i + 1}ページ目が描けていない"


# ---- P の出ない所 ----

def test_catalog_has_no_pdf(browser, generic_dir):
    with ui_session(browser, (generic_dir / "index.html").as_uri(), init=[STUB]) as page:
        assert page.locator(".sp-controls button", has_text="P PDF").count() == 0
        page.keyboard.press("p")
        page.wait_for_timeout(300)
        assert printed(page) == []
        assert boxes(page) == 0


def test_catalog_print_is_unchanged(browser, generic_dir, tmp_path):
    # 目次の ⌘P は今のまま：印刷の指定（@page・@media print）を入れないので、白紙にならず、用紙も変わらない
    from pypdf import PdfReader

    with ui_session(browser, (generic_dir / "index.html").as_uri()) as page:
        assert page.evaluate("document.querySelectorAll('style.sp-print-style').length") == 0
        title = page.locator(".sp-catalog-title").inner_text()
        page.emulate_media(media="print")
        page.pdf(path=str(tmp_path / "catalog.pdf"), prefer_css_page_size=True, print_background=True)
        page.emulate_media(media="screen")
        reader = PdfReader(str(tmp_path / "catalog.pdf"))
        text = unicodedata.normalize("NFKC", reader.pages[0].extract_text())
        assert unicodedata.normalize("NFKC", title) in text
        box = reader.pages[0].mediabox
        assert not (abs(float(box.width) - 1440) <= 0.5 and abs(float(box.height) - 810) <= 0.5)


def test_render_mode_ignores_print(browser, generic_dir):
    with page_session(browser, proposal(generic_dir, "?render")) as page:
        page.evaluate("window.dispatchEvent(new Event('beforeprint'))")
        assert boxes(page) == 0
        assert page.evaluate("document.querySelectorAll('.sp-controls').length") == 0


@pytest.mark.webkit
def test_webkit_p_prints(playwright_instance, generic_dir):
    from playwright.sync_api import Error

    try:
        b = playwright_instance.webkit.launch()
    except Error as exc:
        pytest.skip(f"WebKit が起動できない: {str(exc).splitlines()[0][:200]}")
    try:
        with ui_session(b, proposal(generic_dir), init=[STUB]) as page:
            page.set_default_timeout(10000)
            press_p_and_wait(page)
            got = printed(page)
            assert len(got) == 1 and got[0]["pages"] == 9
    finally:
        b.close()
