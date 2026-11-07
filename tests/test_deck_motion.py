"""デッキが選ぶ動きの層（info.motion）と、見る人の設定（? の「動き」「光」）の試験。

info.motion がないデッキは今と同じ（送りだけ）。壊れた値は選んでいない扱いにする。
見る人は、デッキが選んだ層を止められるが、選んでいない層は足せない。保存するのは見る人が選んだ項目だけ。
"""
import json
import sys
from pathlib import Path

import pytest

from helpers import deck_with_motion, page_session
from test_motion import ARRIVE_KEY, SETTINGS_KEY, calls, kind, navigate, opened, where

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from motion_preview import inject_motion  # noqa: E402

DEFAULT = {"send": True, "entry": None, "point": False}


@pytest.fixture
def moving(browser):
    return lambda url, **kw: opened(browser, url, "no-preference", **kw)


@pytest.fixture
def still(browser):
    return lambda url, **kw: opened(browser, url, "reduce", **kw)


def proposal(generic_dir):
    return generic_dir / "proposal.html"


def stored(page):
    text = page.evaluate(f"localStorage.getItem({json.dumps(SETTINGS_KEY)})")
    return None if text is None else json.loads(text)


def test_default_deck_motion(still, generic_dir):
    with still(proposal(generic_dir).as_uri()) as page:
        assert page.evaluate("__sp.deckMotion()") == DEFAULT


def test_bad_motion_values_are_ignored(browser, generic_dir, tmp_path):
    deck = deck_with_motion(proposal(generic_dir), tmp_path, {"entry": "foo", "point": "yes", "send": 1})
    with page_session(browser, "about:blank") as page:
        warnings = []
        page.on("console", lambda m: warnings.append(m.text) if m.type == "warning" and "motion" in m.text else None)
        page.goto(deck.as_uri())
        page.wait_for_function("!!window.__sp")
        assert page.evaluate("__sp.deckMotion()") == DEFAULT
        assert len(warnings) == 1, warnings


def test_entry_styles_are_accepted_and_old_names_are_ignored(browser, generic_dir, tmp_path):
    """入場の型は subtle・bounce だけ。旧い名前（ppt・meiji）は知らない値として、foo と同じく選んでいない扱いにして1回だけ知らせる。"""
    with page_session(browser, "about:blank") as page:
        warnings = []
        page.on("console", lambda m: warnings.append(m.text) if m.type == "warning" and "motion" in m.text else None)
        for style in ("subtle", "bounce"):
            deck = deck_with_motion(proposal(generic_dir), tmp_path, {"entry": style}, name=f"{style}.html")
            page.goto(deck.as_uri())
            page.wait_for_function("!!window.__sp")
            assert page.evaluate("__sp.deckMotion()") == {**DEFAULT, "entry": style}
            assert warnings == []
        for old in ("ppt", "meiji"):
            warnings.clear()
            deck = deck_with_motion(proposal(generic_dir), tmp_path, {"entry": old}, name=f"{old}.html")
            page.goto(deck.as_uri())
            page.wait_for_function("!!window.__sp")
            assert page.evaluate("__sp.deckMotion()") == DEFAULT
            assert len(warnings) == 1, warnings


def test_send_off_deck_does_not_transition(moving, generic_dir, tmp_path):
    deck = deck_with_motion(proposal(generic_dir), tmp_path, {"send": False})
    with moving(deck.as_uri() + "#p01") as page:
        assert page.evaluate("__sp.deckMotion()") == {**DEFAULT, "send": False}
        page.keyboard.press("ArrowDown")
        assert where(page) == ("p02", 0) and kind(page) == "none" and calls(page) == 0


def test_saved_motion_false_stops_send(moving, generic_dir, tmp_path):
    deck = deck_with_motion(proposal(generic_dir), tmp_path, {"send": True, "entry": "bounce", "point": True})
    with moving(deck.as_uri() + "#p01", settings=json.dumps({"motion": False})) as page:
        page.keyboard.press("ArrowDown")
        assert where(page) == ("p02", 0) and kind(page) == "none" and calls(page) == 0


def test_help_section_is_named_motion(still, generic_dir):
    with still(proposal(generic_dir).as_uri()) as page:
        page.keyboard.press("?")
        sections = page.locator(".sp-help-section").all_inner_texts()
        assert "動き" in sections and "切り替えの動き" not in sections


def test_help_light_row_only_for_point_decks(still, generic_dir, tmp_path):
    with still(proposal(generic_dir).as_uri()) as page:
        page.keyboard.press("?")
        assert page.locator(".sp-help [data-sp-light]").count() == 0
    deck = deck_with_motion(proposal(generic_dir), tmp_path, {"point": True})
    with still(deck.as_uri()) as page:
        page.keyboard.press("?")
        assert page.locator(".sp-help-section", has_text="光").count() == 1
        on, off = page.locator('.sp-help [data-sp-light="on"]'), page.locator('.sp-help [data-sp-light="off"]')
        assert (on.get_attribute("aria-checked"), off.get_attribute("aria-checked")) == ("true", "false")


def test_choosing_light_saves_light_but_not_motion(still, generic_dir, tmp_path):
    deck = deck_with_motion(proposal(generic_dir), tmp_path, {"point": True})
    with still(deck.as_uri()) as page:
        page.keyboard.press("?")
        page.locator('.sp-help [data-sp-light="off"]').click()
        assert page.locator('.sp-help [data-sp-light="off"]').get_attribute("aria-checked") == "true"
        saved = stored(page)
        assert saved["light"] is False and "motion" not in saved


def test_nothing_saved_by_default(still, generic_dir, tmp_path):
    deck = deck_with_motion(proposal(generic_dir), tmp_path, {"send": True, "entry": "subtle", "point": True})
    with still(deck.as_uri() + "#p01") as page:
        page.keyboard.press("ArrowDown")
        page.keyboard.press("ArrowUp")
        assert stored(page) is None


def test_inject_motion_requires_player_script():
    with pytest.raises(ValueError):
        inject_motion("<html><head></head><body><script src='render.js'></script></body></html>", None, {"send": False})


def test_inject_motion_puts_override_before_player():
    html = "<html><head><title>x</title></head><body><script src='../../player/player.js'></script></body></html>"
    out = inject_motion(html, "file:///tmp/deck/", {"entry": "</script>"})
    assert out.index('<base href="file:///tmp/deck/">') < out.index("<title>")
    assert out.index("window.slideDeck.info.motion") < out.index("player.js")
    assert "</script>\"" not in out                       # 値の中の </script> で script が途切れない


# ---- 別のページから着いたときのフェードインも、着いた側のデッキの送りに従う ----

def test_send_off_deck_has_no_arrival_fade(moving, generic_dir, tmp_path):
    deck = deck_with_motion(proposal(generic_dir), tmp_path, {"send": False})
    deck_with_motion(generic_dir / "minimal.html", tmp_path, {"send": False})
    with moving(deck.as_uri() + "#p04") as page:
        navigate(page, lambda: page.locator('#stage [data-link="1"]').click())        # minimal へ
        assert page.url.endswith("minimal.html#m1")
        assert page.evaluate("__sp.deckMotion().send") is False
        assert page.evaluate("__sp.motion().arrival") is False
        assert page.evaluate(f"sessionStorage.getItem({json.dumps(ARRIVE_KEY)})") is None   # 印は使って消す
        navigate(page, lambda: page.keyboard.press("ArrowLeft"))                          # 直近の場所で proposal へ戻る
        assert page.url.endswith("proposal.html#p04")
        assert page.evaluate("__sp.motion().arrival") is False
        assert page.evaluate(f"sessionStorage.getItem({json.dumps(ARRIVE_KEY)})") is None


def test_send_off_deck_has_no_arrival_fade_from_catalog(moving, generic_dir, tmp_path):
    deck_with_motion(proposal(generic_dir), tmp_path, {"send": False})
    index = tmp_path / "examples" / "generic" / "index.html"
    with moving(index.as_uri()) as page:
        navigate(page, lambda: page.keyboard.press("Enter"))                              # 最初のカード（proposal）を開く
        assert page.url.endswith("proposal.html#p01")
        assert page.evaluate("__sp.motion().arrival") is False


# ---- 上書きの入れ場所は、本物の player.js の script だけ ----

COMMENTED = """<html><head><!-- 読み込み例: <script src="../../player/player.js"></script> --></head>
<body><script>var s = '<script src="player.js"></' + 'script>';</script><script defer src='../../player/player.js'></script></body></html>"""


def test_inject_motion_skips_comment_and_script_text():
    out = inject_motion(COMMENTED, None, {"send": False})
    at = out.index("window.slideDeck.info.motion")
    assert at > out.index("-->") and at > out.index("var s =")
    assert at < out.index("<script defer src='../../player/player.js'>")


def test_inject_motion_rejects_comment_only():
    with pytest.raises(ValueError):
        inject_motion('<html><head></head><body><!-- <script src="player.js"></script> --></body></html>', None, {"send": False})


def test_inject_motion_with_comment_applies_in_browser(still, generic_dir, tmp_path):
    src = tmp_path / "src.html"
    src.write_text(proposal(generic_dir).read_text(encoding="utf-8").replace(
        "<head>", '<head>\n<!-- プレイヤーの読み込み例: <script src="../../player/player.js"></script> -->', 1), encoding="utf-8")
    deck = deck_with_motion(src, tmp_path / "out", {"send": False}, name="commented.html")
    with still(deck.as_uri()) as page:
        assert page.evaluate("__sp.deckMotion()") == {**DEFAULT, "send": False}


# ---- JavaScript として実行されない script は、入れ場所にしない ----

def test_inject_motion_skips_non_js_script():
    html = ('<html><head><script type="text/plain" src="../../player/player.js"></script></head>'
            '<body><script type="module" src="../../player/player.js"></script></body></html>')
    out = inject_motion(html, None, {"send": False})
    at = out.index("window.slideDeck.info.motion")
    assert at > out.index('type="text/plain"') and at < out.index('type="module"')


def test_inject_motion_rejects_non_js_only():
    with pytest.raises(ValueError):
        inject_motion('<html><head></head><body><script type="text/plain" src="player.js"></script></body></html>', None, {"send": False})


def test_inject_motion_with_plain_script_applies_in_browser(still, generic_dir, tmp_path):
    src = tmp_path / "src.html"
    src.write_text(proposal(generic_dir).read_text(encoding="utf-8").replace(
        "<head>", '<head>\n<script type="text/plain" src="../../player/player.js"></script>', 1), encoding="utf-8")
    deck = deck_with_motion(src, tmp_path / "out", {"send": False}, name="plain.html")
    with still(deck.as_uri()) as page:
        assert page.evaluate("__sp.deckMotion()") == {**DEFAULT, "send": False}
