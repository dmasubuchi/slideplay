"""Editor の手元のサーバー。Markdown の保存を見張り、変換し直した結果を画面へ渡す。

127.0.0.1 だけで聞く。鍵（?key=）か Cookie（sp_editor）がない求め・Host が自分でない求めは 403。
POST は /api/apply（直しの反映）だけ。Origin が自分でなければ 403、Content-Type が JSON でなければ 415、本文が大きすぎれば 413、形の誤りは 400。
それ以外の POST と GET 以外の方法は 405。
返すのは Editor のページ・部品と、デッキのフォルダーの中のファイルだけ（. で始まるものは返さない）。
使い方：python -m editor.server <md か、md のあるフォルダー> [--port N]
"""
import argparse
import hmac
import json
import mimetypes
import os
import re
import secrets
import signal
import sys
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from .convert import ConvertError, convert, find_markdown
from .shell import deck_html
from .writeback import write_back

REPO = Path(__file__).resolve().parent.parent
POLL_S = 0.2        # 見張りが保存を見に行く間隔
SETTLE_S = 0.15     # 変わってから変換するまで待つ（書き込みの途中を読まない）
WATCH_DIRS = ("fig", "pages")
MAX_BODY = 1_000_000      # POST の本文の上限（バイト）
COOKIE = "sp_editor"      # 実際の名前は sp_editor_<番号>（Cookie は番号が違っても共有されるので、Editor ごとに分ける）

# 部品：道筋 → ファイル
PARTS = {
    "/player.js": REPO / "player" / "player.js",
    "/editor/render.js": REPO / "editor" / "render.js",
    "/editor/live.js": REPO / "editor" / "live.js",
    "/editor/pending.js": REPO / "editor" / "pending.js",
    "/editor/edit.js": REPO / "editor" / "edit.js",
    "/editor/editor.css": REPO / "editor" / "editor.css",
}


def _cookie(header, name):
    """Cookie の見出しから name の値を取る。解釈できない他の Cookie があっても、後ろを捨てない。"""
    for part in header.split(";"):
        k, _, v = part.strip().partition("=")
        if k == name:
            return v.strip()
    return ""


class EditorServer:
    def __init__(self, md_path, *, port=0, key=None):
        self.md = Path(md_path).resolve()
        self.base = self.md.parent
        self.key = key or secrets.token_urlsafe(16)
        self._want_port = port
        self.port = 0
        self.rev = 0
        self._lock = threading.Lock()
        self._write_lock = threading.Lock()      # 書き戻しは1つずつ
        self._deck = None
        self._warnings = []
        self._error = None
        self._at = ""
        self._stop = threading.Event()
        self._httpd = None
        self._threads = []

    @property
    def cookie_name(self):
        return f"{COOKIE}_{self.port}"

    @property
    def url(self):
        return f"http://127.0.0.1:{self.port}/?key={self.key}"

    # ---- 変換 ----
    def _placeholder(self, message):
        """最初の変換が誤りのときのデッキ（1枚）。直ると本物のデッキに入れ替わる。"""
        # src は None（描くときに data-src が付かず、直せない）
        line = {"text": message, "src": None}
        slide = {"id": "editor-error", "type": "ふつう", "title": "まだ描けません", "steps": 0, "notes": [],
                 "src": [1, 1], "head": {"text": "まだ描けません", "src": None},
                 "blocks": [{"kind": "p", "text": message, "src": None, "lines": [line]}], "html": None}
        return {"info": {"id": "deck", "title": "まだ描けません"}, "slides": [slide], "warnings": []}

    def _fail(self, line, message):
        with self._lock:
            self._error = {"line": line, "message": message}
            if self._deck is None:
                self._deck = self._placeholder(f"{line}行目：{message}")
                self._at = time.strftime("%H:%M:%S")
            self.rev += 1

    def _convert(self):
        """変換して状態を更新し、rev を1増やす。誤りのときは最後に変換できたデッキを残す。"""
        try:
            data = convert(self.md, editing=True)
        except ConvertError as e:
            self._fail(e.line, e.message)
            return
        except (OSError, UnicodeDecodeError) as e:
            # 保存の途中などで読めない。誤りの帯に出して、次の保存を待つ
            self._fail(1, f"読めません（{e}）")
            return
        with self._lock:
            self._deck = data
            self._warnings = data.get("warnings", [])
            self._error = None
            self._at = time.strftime("%H:%M:%S")
            self.rev += 1

    def apply(self, edits):
        """直しを Markdown に書き戻し、変わったときはすぐ変換し直す。結果に、そのときの rev を足して返す。"""
        with self._write_lock:
            res = write_back(self.md, edits)
            if res["applied"] or res["ids_added"]:
                self._convert()          # 見張りを待たない（見張りがもう1回変換して rev が増えても害はない）
        res["rev"] = self.rev
        return res

    def snapshot(self):
        with self._lock:
            return {"rev": self.rev, "deck": self._deck, "warnings": self._warnings,
                    "error": self._error, "file": self.md.name, "at": self._at}

    def _signature(self):
        """見張る対象（md と fig/・pages/ の中）の (名前, inode, 更新時刻, 大きさ) の組。置き換え保存でも変わる。"""
        sig = []
        paths = [self.md]
        for d in WATCH_DIRS:
            root = self.base / d
            if root.is_dir():
                paths.extend(p for p in root.rglob("*") if p.is_file())
        for p in paths:
            try:
                st = p.stat()
            except OSError:
                sig.append((str(p), None))
                continue
            sig.append((str(p), st.st_ino, st.st_mtime_ns, st.st_size))
        return sorted(sig, key=lambda t: t[0])

    def _watch(self, last):
        while not self._stop.wait(POLL_S):
            now = self._signature()
            if now == last:
                continue
            if self._stop.wait(SETTLE_S):
                return
            last = self._signature()
            self._convert()

    # ---- 起動・停止 ----
    def start(self):
        first_sig = self._signature()      # 変換より先に取る（変換と見張りの開始のあいだの保存を取りこぼさない）
        self._convert()
        server = self
        self._httpd = ThreadingHTTPServer(("127.0.0.1", self._want_port), _make_handler(server))
        self._httpd.daemon_threads = True
        self.port = self._httpd.server_address[1]
        self._stop.clear()
        for target, args in ((self._httpd.serve_forever, ()), (self._watch, (first_sig,))):
            t = threading.Thread(target=target, args=args, daemon=True)
            t.start()
            self._threads.append(t)

    def stop(self):
        self._stop.set()
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
        for t in self._threads:
            t.join(timeout=5)
        self._threads = []

    # ---- ページ ----
    def page(self):
        snap = self.snapshot()
        html = deck_html(snap["deck"], render_src="/editor/render.js", player_src="/player.js", editing=True,
                         live_src="/editor/live.js", css_href="/editor/editor.css",
                         edit_srcs=("/editor/pending.js", "/editor/edit.js"))
        title = snap["deck"]["info"]["title"].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        html = re.sub(r"<title>.*?</title>", lambda m: f"<title>{title} — 編集</title>", html, count=1, flags=re.S)
        return html.replace("<body>", f'<body data-rev="{snap["rev"]}">', 1)

    def resolve(self, raw_path):
        """URL の道筋 → デッキのフォルダーの中のファイル。外・. で始まるもの・ファイルでないものは None。"""
        rel = unquote(raw_path).lstrip("/")
        if "\0" in rel or not rel:
            return None
        try:
            target = (self.base / rel).resolve()
            parts = target.relative_to(self.base).parts
        except (ValueError, OSError):
            return None
        if any(p.startswith(".") for p in parts) or any(p.startswith(".") for p in Path(rel).parts if p != ".."):
            return None
        try:
            return target if target.is_file() else None
        except OSError:                          # 長すぎる名前など
            return None


def _is_int(x):
    return isinstance(x, int) and not isinstance(x, bool)


def _parse_edits(raw):
    """POST の本文 → 直しの list。形が誤りなら None。"""
    try:
        body = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(body, dict) or not isinstance(body.get("edits"), list):
        return None
    edits = []
    for e in body["edits"]:
        if not isinstance(e, dict):
            return None
        src = e.get("src")
        if not all(isinstance(e.get(k), str) for k in ("key", "before", "after")):
            return None
        if not (isinstance(src, list) and len(src) == 3 and all(_is_int(v) for v in src)
                and src[0] >= 1 and 0 <= src[1] <= src[2]):
            return None
        edits.append({"key": e["key"], "src": src, "before": e["before"], "after": e["after"]})
    return edits


def _make_handler(server):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def log_message(self, *args):
            pass

        def _send(self, status, body=b"", ctype="text/plain; charset=utf-8", cookie=None):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            if cookie:
                self.send_header("Set-Cookie", cookie)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _deny(self, status):
            self._send(status, status.phrase.encode())

        def _apply(self):
            origin = self.headers.get("Origin", "")
            if origin not in (f"http://127.0.0.1:{server.port}", f"http://localhost:{server.port}"):
                return self._deny(HTTPStatus.FORBIDDEN)
            ctype = self.headers.get("Content-Type", "").split(";")[0].strip().lower()
            if ctype != "application/json":
                return self._deny(HTTPStatus.UNSUPPORTED_MEDIA_TYPE)
            length = self.headers.get("Content-Length", "")
            if not length.isascii() or not length.isdigit():
                return self._deny(HTTPStatus.BAD_REQUEST)
            length = int(length)
            if length > MAX_BODY:
                return self._deny(HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
            raw = self.rfile.read(length)
            edits = _parse_edits(raw)
            if edits is None:
                return self._deny(HTTPStatus.BAD_REQUEST)
            try:
                res = server.apply(edits)
            except (OSError, UnicodeDecodeError):
                return self._deny(HTTPStatus.INTERNAL_SERVER_ERROR)
            self._send(200, json.dumps(res, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def _handle(self):
            host = self.headers.get("Host", "")
            if host not in (f"127.0.0.1:{server.port}", f"localhost:{server.port}"):
                return self._deny(HTTPStatus.FORBIDDEN)
            url = urlsplit(self.path)
            qkey = (parse_qs(url.query).get("key") or [""])[0]
            cname = server.cookie_name
            ckey = _cookie(self.headers.get("Cookie", ""), cname)
            q_ok = bool(qkey) and hmac.compare_digest(qkey.encode(), server.key.encode())
            c_ok = bool(ckey) and hmac.compare_digest(ckey.encode(), server.key.encode())
            if not (q_ok or c_ok):
                return self._deny(HTTPStatus.FORBIDDEN)
            if self.command == "POST" and unquote(url.path) == "/api/apply":
                return self._apply()
            if self.command != "GET":
                return self._deny(HTTPStatus.METHOD_NOT_ALLOWED)
            cookie = f"{cname}={server.key}; HttpOnly; SameSite=Strict; Path=/" if q_ok else None
            path = unquote(url.path)
            if path == "/":
                return self._send(200, server.page().encode("utf-8"), "text/html; charset=utf-8", cookie)
            if path == "/api/rev":
                body = json.dumps({"rev": server.rev}).encode()
                return self._send(200, body, "application/json", cookie)
            if path == "/api/deck":
                body = json.dumps(server.snapshot(), ensure_ascii=False).encode("utf-8")
                return self._send(200, body, "application/json; charset=utf-8", cookie)
            target = PARTS.get(path) or server.resolve(url.path)
            if target is None:
                return self._deny(HTTPStatus.NOT_FOUND)
            try:
                body = target.read_bytes()
            except OSError:
                return self._deny(HTTPStatus.NOT_FOUND)
            ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
                ctype += "; charset=utf-8"
            self._send(200, body, ctype, cookie)

        do_GET = do_POST = do_PUT = do_DELETE = do_PATCH = do_HEAD = do_OPTIONS = _handle

    return Handler


def main(argv):
    ap = argparse.ArgumentParser(prog="python -m editor.server")
    ap.add_argument("md", help="Markdown のファイル（または、それが1つだけあるフォルダー）")
    ap.add_argument("--port", type=int, default=0)
    args = ap.parse_args(argv)
    try:
        md = find_markdown(args.md)
    except ValueError as e:
        print(e, file=sys.stderr)
        return 1
    server = EditorServer(md, port=args.port)
    server.start()
    info = server.base / ".editor" / "server.json"
    info.parent.mkdir(exist_ok=True)
    fd = os.open(info, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        os.fchmod(f.fileno(), 0o600)
        json.dump({"pid": os.getpid(), "port": server.port, "key": server.key, "md": str(server.md)}, f)
    done = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: done.set())
    signal.signal(signal.SIGINT, lambda *_: done.set())
    print(server.url, flush=True)
    try:
        done.wait()
    finally:
        server.stop()
        info.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
