"""editor/server.py（Editor の手元のサーバー）と editor/live.js（保存で描き直す画面）の試験。"""
import http.client
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tests"))

from editor.server import EditorServer  # noqa: E402
from helpers import page_session  # noqa: E402

BASIC = REPO / "tests" / "editor_decks" / "basic"


class Resp:
    def __init__(self, r):
        self.status = r.status
        self.headers = dict(r.getheaders())
        self.body = r.read()


def get(server, path, cookie=None, host=None, method="GET"):
    c = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
    try:
        headers = {"Host": host or f"127.0.0.1:{server.port}"}
        if cookie:
            headers["Cookie"] = cookie
        c.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
        for k, v in headers.items():
            c.putheader(k, v)
        c.endheaders()
        return Resp(c.getresponse())
    finally:
        c.close()


def api_deck(server):
    r = get(server, "/api/deck", cookie=server.cookie_name + "=" + server.key)
    return json.loads(r.body)


def wait_until(cond, timeout=1.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.02)
    return cond()


def wait_api_deck(server, cond, timeout=3.0):
    wait_until(lambda: cond(api_deck(server)), timeout)
    d = api_deck(server)
    assert cond(d), d
    return d


def post(server, path, body, *, cookie=True, origin="own", ctype="application/json"):
    """POST の道具。origin="own" は自分の Origin、None は送らない。"""
    c = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
    try:
        c.putrequest("POST", path, skip_host=True, skip_accept_encoding=True)
        c.putheader("Host", f"127.0.0.1:{server.port}")
        if cookie:
            c.putheader("Cookie", server.cookie_name + "=" + server.key)
        if origin:
            c.putheader("Origin", f"http://127.0.0.1:{server.port}" if origin == "own" else origin)
        c.putheader("Content-Type", ctype)
        c.putheader("Content-Length", str(len(body)))
        c.endheaders()
        try:
            c.send(body)
        except OSError:          # 大きすぎる本文は、サーバーが読まずに閉じることがある
            pass
        return Resp(c.getresponse())
    finally:
        c.close()


def find_src(server, text):
    """/api/deck の中から、text を含む文を探し、text の部分だけの src（行, 始め, 終わり）を返す。（飾りのない文が前提）"""
    def walk(x):
        if isinstance(x, dict):
            if isinstance(x.get("text"), str) and text in x["text"] and isinstance(x.get("src"), list) and len(x["src"]) == 3:
                i = x["text"].index(text)
                line, start, _ = x["src"]
                return [line, start + i, start + i + len(text)]
            for v in x.values():
                r = walk(v)
                if r:
                    return r
        elif isinstance(x, list):
            for v in x:
                r = walk(v)
                if r:
                    return r
        return None
    return walk(api_deck(server)["deck"])


def append(md, text):
    md.write_text(md.read_text(encoding="utf-8") + text, encoding="utf-8")


def replace_text(md, old, new):
    t = md.read_text(encoding="utf-8")
    assert old in t
    md.write_text(t.replace(old, new), encoding="utf-8")


def touch(path):
    st = path.stat()
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))


def fix_last_comment(md):
    t = md.read_text(encoding="utf-8")
    md.write_text(t.replace("<!-- 閉じていない\n", "<!-- 閉じた -->\n"), encoding="utf-8")


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


def test_requires_key(server):
    assert get(server, "/").status == 403
    r = get(server, "/?key=" + server.key)
    assert r.status == 200 and server.cookie_name + "=" in r.headers["Set-Cookie"]
    assert "HttpOnly" in r.headers["Set-Cookie"] and "SameSite=Strict" in r.headers["Set-Cookie"]
    assert get(server, "/player.js", cookie=server.cookie_name + "=" + server.key).status == 200
    assert get(server, "/player.js", cookie=server.cookie_name + "=x").status == 403


def test_rejects_foreign_host(server):
    assert get(server, "/?key=" + server.key, host="evil.example").status == 403
    assert get(server, "/?key=" + server.key, host=f"localhost:{server.port}").status == 200


def test_get_only(server):
    assert get(server, "/?key=" + server.key, method="POST").status == 405
    assert get(server, "/", method="POST").status == 403


@pytest.mark.parametrize("path", ["/fig/../../x", "/%2e%2e/%2e%2e/etc/hosts", "/.editor/server.json", "/fig/%2e%2e/%2e%2e/x"])
def test_serves_only_inside_deck(server, path):
    assert get(server, path, cookie=server.cookie_name + "=" + server.key).status == 404


def test_serves_deck_files_with_query(server):
    r = get(server, "/fig/flow.svg?v=123", cookie=server.cookie_name + "=" + server.key)
    assert r.status == 200 and b"<svg" in r.body


def test_rev_bumps_on_save(server):
    rev = server.rev
    append(server.md, "\n- 足した\n")
    assert wait_until(lambda: server.rev > rev, timeout=1.0)


def test_rev_bumps_on_atomic_replace(server):
    rev = server.rev
    tmp = server.md.with_suffix(".tmp")
    tmp.write_text(server.md.read_text(encoding="utf-8") + "\n- 足した\n", encoding="utf-8")
    os.replace(tmp, server.md)
    assert wait_until(lambda: server.rev > rev, timeout=1.0)


def test_fig_change_bumps_rev(server):
    rev = server.rev
    touch(server.md.parent / "fig" / "flow.svg")
    assert wait_until(lambda: server.rev > rev, timeout=1.0)


def test_error_keeps_last_good_deck(server):
    good = api_deck(server)["deck"]
    append(server.md, "\n---\n<!-- id: s02 -->\n# 重複\n")
    d = wait_api_deck(server, lambda d: d["error"])
    assert d["error"]["message"].startswith("ID s02 が2つあります") and d["deck"] == good


def test_live_update_within_one_second(server, browser):
    with page_session(browser, server.url + "#s02.1") as page:
        page.wait_for_selector(".sp-edit-pill")
        replace_text(server.md, "点数を高く付ける", "点数を高くする")
        t = time.monotonic()
        page.wait_for_function("document.querySelector('#stage').textContent.includes('点数を高くする')", timeout=3000)
        assert time.monotonic() - t < 1.5
        assert page.evaluate("location.hash") == "#s02.1"
        assert page.title() == "検索のしくみ — 編集"


def test_error_banner_then_recover(server, browser):
    with page_session(browser, server.url + "#s02") as page:
        page.wait_for_selector(".sp-edit-pill")
        before = page.inner_text("#stage")
        append(server.md, "\n<!-- 閉じていない\n")
        page.wait_for_selector(".sp-edit-error")
        assert "行目：<!-- が閉じていません" in page.inner_text(".sp-edit-error") and page.inner_text("#stage") == before
        fix_last_comment(server.md)
        page.wait_for_selector(".sp-edit-error", state="detached")


def test_warning_banner(server, browser):
    rev = server.rev
    append(server.md, "\n---\n# 図\n\n![x](fig/nai.svg)\n")
    assert wait_until(lambda: server.rev > rev, timeout=1.0)
    with page_session(browser, server.url) as page:
        page.wait_for_selector(".sp-edit-warn")
        assert "fig/nai.svg がありません" in page.inner_text(".sp-edit-warn")


def test_pill_shows_file_and_time(server, browser):
    with page_session(browser, server.url) as page:
        page.wait_for_selector(".sp-edit-pill")
        assert re.fullmatch(r"下書き\.md · \d\d:\d\d:\d\d に描き直し", page.inner_text(".sp-edit-pill"))


def test_japanese_paths(tmp_path, browser):
    deck = tmp_path / "見本 講座"
    (deck / "fig").mkdir(parents=True)
    shutil.copy(BASIC / "fig" / "flow.svg", deck / "fig" / "検索の図.svg")
    (deck / "下書き.md").write_text("# 図\n\n![図](fig/検索の図.svg)\n", encoding="utf-8")
    s = EditorServer(deck / "下書き.md")
    s.start()
    try:
        with page_session(browser, s.url) as page:
            page.wait_for_function("document.querySelector('#stage img')?.naturalWidth > 0", timeout=3000)
    finally:
        s.stop()


def test_main_writes_and_removes_server_json(tmp_path):
    deck = tmp_path / "deck"
    shutil.copytree(BASIC, deck)
    p = subprocess.Popen([sys.executable, "-m", "editor.server", str(deck / "下書き.md"), "--port", "0"],
                         cwd=REPO, stdout=subprocess.PIPE, text=True)
    info = deck / ".editor" / "server.json"
    try:
        url = p.stdout.readline().strip()
        assert url.startswith("http://127.0.0.1:")
        assert wait_until(info.exists, 3)
        assert info.stat().st_mode & 0o777 == 0o600
        data = json.loads(info.read_text(encoding="utf-8"))
        assert data["pid"] == p.pid and data["md"] == str(deck / "下書き.md") and data["key"] in url
        p.send_signal(signal.SIGTERM)
        assert p.wait(timeout=5) == 0
        assert not info.exists()
    finally:
        if p.poll() is None:
            p.kill()
            p.wait()
        p.stdout.close()


def test_cookie_is_per_port(server):
    assert get(server, "/player.js", cookie="sp_editor=" + server.key).status == 403


def test_long_path_is_404(server):
    assert get(server, "/" + "a" * 5000, cookie=server.cookie_name + "=" + server.key).status == 404


def test_two_editors_in_one_browser(tmp_path, browser):
    servers = []
    try:
        for n in ("a", "b"):
            deck = tmp_path / n
            shutil.copytree(BASIC, deck)
            s = EditorServer(deck / "下書き.md")
            s.start()
            servers.append(s)
        a, b = servers
        ctx = browser.new_context()
        pa, pb = ctx.new_page(), ctx.new_page()
        try:
            pa.goto(a.url + "#s02.1")
            pa.wait_for_selector(".sp-edit-pill")
            pb.goto(b.url + "#s02.1")
            pb.wait_for_selector(".sp-edit-pill")
            replace_text(a.md, "点数を高く付ける", "点数を高くする")
            replace_text(b.md, "点数を高く付ける", "点数をもっと高くする")
            pa.wait_for_function("document.querySelector('#stage').textContent.includes('点数を高くする')", timeout=3000)
            pb.wait_for_function("document.querySelector('#stage').textContent.includes('点数をもっと高くする')", timeout=3000)
        finally:
            ctx.close()
    finally:
        for s in servers:
            s.stop()


def test_broken_first_conversion_serves_placeholder(tmp_path):
    deck = tmp_path / "deck"
    shutil.copytree(BASIC, deck)
    good = (deck / "下書き.md").read_text(encoding="utf-8")
    (deck / "下書き.md").write_text(good + "\n<!-- 閉じていない\n", encoding="utf-8")
    s = EditorServer(deck / "下書き.md")
    s.start()
    try:
        d = api_deck(s)
        assert d["error"]["message"] == "<!-- が閉じていません"
        assert d["deck"]["slides"][0]["id"] == "editor-error"
        (deck / "下書き.md").write_text(good, encoding="utf-8")
        d = wait_api_deck(s, lambda d: d["error"] is None)
        assert d["deck"]["slides"][0]["id"] == "s01"
    finally:
        s.stop()


def test_broken_first_conversion_in_browser(tmp_path, browser):
    deck = tmp_path / "deck"
    shutil.copytree(BASIC, deck)
    good = (deck / "下書き.md").read_text(encoding="utf-8")
    (deck / "下書き.md").write_text(good + "\n<!-- 閉じていない\n", encoding="utf-8")
    s = EditorServer(deck / "下書き.md")
    s.start()
    try:
        with page_session(browser, s.url) as page:
            page.wait_for_selector(".sp-edit-error")
            assert "まだ描けません" in page.inner_text("#stage")
            (deck / "下書き.md").write_text(good, encoding="utf-8")
            page.wait_for_selector(".sp-edit-error", state="detached")
            page.wait_for_function("document.querySelector('#stage').textContent.includes('検索のしくみ')", timeout=3000)
            assert "まだ描けません" not in page.inner_text("#stage")
    finally:
        s.stop()


def test_main_missing_md_exits_1(tmp_path):
    p = subprocess.run([sys.executable, "-m", "editor.server", str(tmp_path / "nai.md")], cwd=REPO,
                       capture_output=True, text=True, timeout=10)
    assert p.returncode == 1


def test_apply_writes_and_bumps_rev(server):
    rev = server.rev
    line, a, b = find_src(server, "点数を高く付ける")     # /api/deck の中から、その文の src を探す
    r = post(server, "/api/apply", json.dumps({"edits": [{"key": "k", "src": [line, a, b], "before": "点数を高く付ける", "after": "点数を高くする"}]}).encode())
    body = json.loads(r.body)
    assert r.status == 200 and body["applied"] == ["k"] and body["rev"] > rev
    assert "点数を高くする" in server.md.read_text(encoding="utf-8")
    assert "点数を高くする" in json.dumps(api_deck(server)["deck"], ensure_ascii=False)


def test_apply_requires_key(server):
    assert post(server, "/api/apply", b'{"edits": []}', cookie=False).status == 403


@pytest.mark.parametrize("origin", [None, "http://evil.example", "http://127.0.0.1:1"])
def test_apply_rejects_foreign_origin(server, origin):
    assert post(server, "/api/apply", b'{"edits": []}', origin=origin).status == 403


def test_apply_rejects_non_json(server):
    assert post(server, "/api/apply", b"edits=1", ctype="application/x-www-form-urlencoded").status == 415


def test_apply_rejects_large_body(server):
    assert post(server, "/api/apply", b" " * 1_000_001).status == 413


@pytest.mark.parametrize("body", [b"{", b'{"edits": 1}', b'{"edits": [{"key": "k"}]}', b'{"edits": [{"key": "k", "src": ["a", 0, 1], "before": "", "after": "x"}]}'])
def test_apply_rejects_bad_shape(server, body):
    assert post(server, "/api/apply", body).status == 400


def test_post_elsewhere_is_405(server):
    assert post(server, "/api/deck", b"{}").status == 405


def test_placeholder_is_not_editable(tmp_path):
    deck = tmp_path / "d"
    deck.mkdir()
    (deck / "下書き.md").write_text("<!-- 閉じていない\n", encoding="utf-8")
    s = EditorServer(deck / "下書き.md")
    s.start()
    try:
        sl = api_deck(s)["deck"]["slides"][0]
        assert sl["id"] == "editor-error" and sl["head"]["src"] is None and sl["blocks"][0]["src"] is None
        assert sl["blocks"][0]["lines"][0]["src"] is None
    finally:
        s.stop()


def test_page_loads_edit_scripts_in_order(server):
    html = get(server, "/?key=" + server.key).body.decode()
    i = [html.index(s) for s in ("/editor/render.js", "/editor/pending.js", "/editor/edit.js", "EditorSlides.createDeck", "/editor/live.js", "/player.js")]
    assert i == sorted(i)


@pytest.mark.parametrize("front", ['a={"x":1}', "a=b c", "a=é", "Path=/", "a=\\x"])
def test_foreign_cookie_does_not_hide_ours(server, front):
    cookie = f"{front}; {server.cookie_name}={server.key}"
    assert get(server, "/player.js", cookie=cookie).status == 200
