"""tests/helpers.py の試験：ページが例外を出したら、試験が失敗になること。"""
import pytest

from helpers import evaluate, open_deck, page_session


def make_course(root, script):
    """第1章のページ1枚だけの講座を作る（script はページの中で実行する JS）。"""
    page = root / "ch-01" / "slides.html"
    page.parent.mkdir(parents=True)
    page.write_text(f"<!doctype html><html><body><script>{script}</script></body></html>", encoding="utf-8")
    return root


def test_open_deck_fails_when_page_throws_on_load(browser, tmp_path):
    course = make_course(tmp_path, "throw new Error('読み込み中の例外');")
    with pytest.raises(AssertionError, match="読み込み中の例外"):
        open_deck(browser, course, 1)


def test_evaluate_fails_when_page_throws_later(browser, tmp_path):
    course = make_course(tmp_path, "")
    expr = "(async () => { setTimeout(() => { throw new Error('あとからの例外'); }, 0); await new Promise(r => setTimeout(r, 100)); return 1; })()"
    with pytest.raises(AssertionError, match="あとからの例外"):
        evaluate(browser, course, 1, expr)


def test_open_deck_adds_render_query_only_when_asked(browser, tmp_path):
    course = make_course(tmp_path, "")
    for render in (True, False):
        page = open_deck(browser, course, 1, render=render)
        try:
            assert page.evaluate("location.search") == ("?render" if render else "")
            assert page.viewport_size == {"width": 1920, "height": 1080}
        finally:
            page.close()


# ---- page_session：ページの例外を、確かめ忘れずに失敗にする ----

def write_page(tmp_path, script):
    page = tmp_path / "page.html"
    page.write_text(f"<!doctype html><html><body><script>{script}</script></body></html>", encoding="utf-8")
    return page.as_uri()


def test_page_session_fails_when_page_throws_after_load(browser, tmp_path):
    # 読み込みのあとに、タイマーで例外を出すページ。with の中で何も確かめなくても、抜けるときに失敗になる
    url = write_page(tmp_path, "setTimeout(() => { throw new Error('あとからの例外'); }, 0);")
    with pytest.raises(AssertionError, match="あとからの例外"):
        with page_session(browser, url) as page:
            page.wait_for_timeout(200)
    assert page.is_closed()


def test_page_session_fails_when_page_throws_on_load(browser, tmp_path):
    url = write_page(tmp_path, "throw new Error('読み込み中の例外');")
    with pytest.raises(AssertionError, match="読み込み中の例外"):
        with page_session(browser, url):
            pass


def test_page_session_reports_both_when_body_also_raises(browser, tmp_path):
    url = write_page(tmp_path, "setTimeout(() => { throw new Error('ページの例外'); }, 0);")
    with pytest.raises(AssertionError, match="ページの例外") as info:
        with page_session(browser, url) as page:
            page.wait_for_timeout(200)
            raise ValueError("試験の中の例外")
    assert "試験の中の例外" in str(info.value)
    assert isinstance(info.value.__cause__, ValueError)         # 元の例外も残る


def test_page_session_keeps_body_exception_when_page_is_clean(browser, tmp_path):
    with pytest.raises(ValueError, match="試験の中の例外"):
        with page_session(browser, write_page(tmp_path, "")) as page:
            raise ValueError("試験の中の例外")
    assert page.is_closed()


def test_page_session_passes_and_closes_clean_page(browser, tmp_path):
    with page_session(browser, write_page(tmp_path, "window.answer = 42;"), viewport=(800, 600)) as page:
        assert page.evaluate("window.answer") == 42
        assert page.viewport_size == {"width": 800, "height": 600}
    assert page.is_closed()


def test_page_session_catches_exception_thrown_just_before_exit(browser, tmp_path):
    # 最後の操作が setTimeout で出した例外は、待たずに with を抜けても見つける（閉じてから記録を読む）。一度だけでなく繰り返して確かめる
    url = write_page(tmp_path, "")
    for _ in range(10):
        with pytest.raises(AssertionError, match="直前の例外"):
            with page_session(browser, url) as page:
                page.evaluate("setTimeout(() => { throw new Error('直前の例外'); }, 0)")
