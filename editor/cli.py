"""Editor の開く・止めるコマンド（scripts/slide-edit から呼ぶ）。

  slide-edit open <デッキのフォルダーか .md> [--no-open] [--port N]
  slide-edit stop <デッキのフォルダーか .md>

サーバー本体は editor/server.py。ここは起こす・見つける・止めるだけ。
"""
import argparse
import http.client
import json
import os
import signal
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

from editor.convert import find_markdown

REPO = Path(__file__).resolve().parent.parent
START_WAIT_S = 5.0   # 起こしてから server.json ができるまで
STOP_WAIT_S = 3.0    # 止めてから server.json が消えるまで


def _info_path(md):
    return md.parent / ".editor" / "server.json"


def _read_info(path):
    try:
        info = json.loads(path.read_text(encoding="utf-8"))
        return {"pid": int(info["pid"]), "port": int(info["port"]), "key": str(info["key"])}
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _pid_alive(pid):
    try:
        # 自分の子が終わっていたら回収する（回収しないと終了済みでも kill(pid, 0) が通る）
        if os.waitpid(pid, os.WNOHANG) != (0, 0):
            return False
    except ChildProcessError:
        pass   # 自分の子ではない（別の端末から起こしたもの）
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _answers(info):
    """pid が生きていて、/api/rev が鍵で 200 を返すか。"""
    if not _pid_alive(info["pid"]):
        return False
    try:
        c = http.client.HTTPConnection("127.0.0.1", info["port"], timeout=1)
        try:
            c.request("GET", f"/api/rev?key={info['key']}")
            return c.getresponse().status == 200
        finally:
            c.close()
    except (OSError, http.client.HTTPException):
        return False


def _is_editor_process(pid, md):
    """生きているが答えない pid が、この .md の Editor サーバーか（ps の起動行で確かめる）。"""
    try:
        out = subprocess.run(["ps", "-p", str(pid), "-o", "command="], capture_output=True, text=True, timeout=3).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return "editor.server" in out and str(md) in out


def _url(info):
    return f"http://127.0.0.1:{info['port']}/?key={info['key']}"


def _resolve(path):
    try:
        return find_markdown(path)
    except ValueError as e:
        print(e, file=sys.stderr)
        return None


def _start(md, port):
    """サーバーを別のセッションで起こす（端末を閉じても残る）。起こせたら info、だめなら None。"""
    info_path = _info_path(md)
    info_path.parent.mkdir(exist_ok=True)
    info_path.unlink(missing_ok=True)   # 古い印を残さない
    cmd = [sys.executable, "-B", "-m", "editor.server", str(md)]
    if port:
        cmd += ["--port", str(port)]
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    with open(info_path.parent / "server.log", "ab") as log:
        proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                start_new_session=True, env=env)
    end = time.monotonic() + START_WAIT_S
    while time.monotonic() < end:
        info = _read_info(info_path)
        if info and info["pid"] == proc.pid and _answers(info):
            return info
        if proc.poll() is not None:
            break
        time.sleep(0.05)
    print(f"サーバーが起きませんでした（{info_path.parent / 'server.log'} を見てください）", file=sys.stderr)
    return None


def cmd_open(args):
    md = _resolve(args.path)
    if md is None:
        return 1
    info = _read_info(_info_path(md))
    if not (info and _answers(info)):
        info = _start(md, args.port)
        if info is None:
            return 1
    url = _url(info)
    print(url, flush=True)
    if not args.no_open:
        webbrowser.open(url)
    return 0


def cmd_stop(args):
    md = _resolve(args.path)
    if md is None:
        return 1
    info_path = _info_path(md)
    info = _read_info(info_path)
    if not (info and _pid_alive(info["pid"]) and (_answers(info) or _is_editor_process(info["pid"], md))):
        info_path.unlink(missing_ok=True)   # 古い印だけ片づける（別のプロセスに pid が移っていても止めない）
        print("動いていません")
        return 0
    os.kill(info["pid"], signal.SIGTERM)
    end = time.monotonic() + STOP_WAIT_S
    while time.monotonic() < end:
        if not info_path.exists() and not _pid_alive(info["pid"]):
            break
        time.sleep(0.05)
    if info_path.exists() or _pid_alive(info["pid"]):
        print("止まりませんでした", file=sys.stderr)
        return 1
    print("止めました")
    return 0


def main(argv):
    ap = argparse.ArgumentParser(prog="slide-edit")
    sub = ap.add_subparsers(dest="cmd", required=True)
    po = sub.add_parser("open", help="サーバーを起こして（動いていればそれを使って）ブラウザーに出す")
    po.add_argument("path", help="デッキのフォルダーか .md")
    po.add_argument("--no-open", action="store_true", help="ブラウザーを開かず、URL だけ出す")
    po.add_argument("--port", type=int, default=0)
    ps = sub.add_parser("stop", help="サーバーを止める")
    ps.add_argument("path", help="デッキのフォルダーか .md")
    try:
        args = ap.parse_args(argv)
    except SystemExit as e:
        return 1 if e.code else 0
    return cmd_open(args) if args.cmd == "open" else cmd_stop(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
