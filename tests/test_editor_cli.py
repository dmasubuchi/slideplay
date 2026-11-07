"""editor/cli.py（slide-edit の open / stop）の試験。ブラウザーは開かない（--no-open）。"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.request import urlopen

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from editor.cli import main  # noqa: E402

BASIC = REPO / "tests" / "editor_decks" / "basic"


def urlopen_status(url):
    with urlopen(url, timeout=5) as r:
        return r.status


def pid_alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


@pytest.fixture
def deck(tmp_path):
    d = tmp_path / "deck"
    shutil.copytree(BASIC, d)
    yield d
    main(["stop", str(d)])   # 試験のサーバーを残さない


def test_open_reuses_running_server(deck, capsys):
    assert main(["open", str(deck), "--no-open"]) == 0
    url1 = capsys.readouterr().out.strip()
    assert main(["open", str(deck / "下書き.md"), "--no-open"]) == 0
    assert capsys.readouterr().out.strip() == url1
    assert urlopen_status(url1) == 200


def test_stop_ends_server(deck):
    main(["open", str(deck), "--no-open"])
    pid = json.loads((deck / ".editor/server.json").read_text())["pid"]
    assert main(["stop", str(deck)]) == 0
    assert not pid_alive(pid) and not (deck / ".editor/server.json").exists()


def test_stop_when_not_running(deck, capsys):
    assert main(["stop", str(deck)]) == 0
    assert "動いていません" in capsys.readouterr().out


def test_open_rejects_two_markdown_files(deck, capsys):
    (deck / "別.md").write_text("# x\n", encoding="utf-8")
    assert main(["open", str(deck), "--no-open"]) == 1
    assert "に .md が2つあります。ファイルを指定してください" in capsys.readouterr().err


def test_open_rejects_missing_path(tmp_path, capsys):
    assert main(["open", str(tmp_path / "ない"), "--no-open"]) == 1


def test_stale_server_json_is_replaced(deck, capsys):
    dead = subprocess.Popen(["true"])
    dead.wait()   # もう動いていない pid
    (deck / ".editor").mkdir()
    (deck / ".editor/server.json").write_text(
        json.dumps({"pid": dead.pid, "port": 9, "key": "x", "md": str(deck / "下書き.md")}))
    assert main(["open", str(deck), "--no-open"]) == 0
    assert urlopen_status(capsys.readouterr().out.strip()) == 200


def test_sample_deck_converts():
    from editor.convert import convert, find_markdown
    md = find_markdown(str(REPO / "examples" / "editor"))
    assert md.name == "下書き.md"
    r = convert(md)   # 例外なし・注意なし。5つの型がそろっている
    assert r["warnings"] == []
    types = {s["type"] for s in r["slides"]}
    assert {"表紙", "ふつう", "二段", "図と文", "強調"} <= types


def test_stop_does_not_kill_unrelated_process(tmp_path, capsys):
    """古い server.json の pid が別の生きたプロセスに使われていても、止めない。"""
    d = tmp_path / "deck"
    shutil.copytree(BASIC, d)
    (d / ".editor").mkdir(exist_ok=True)
    victim = subprocess.Popen(["sleep", "30"])
    try:
        (d / ".editor/server.json").write_text(json.dumps({"pid": victim.pid, "port": 9, "key": "k"}))
        assert main(["stop", str(d)]) == 0
        assert victim.poll() is None and pid_alive(victim.pid)
        assert "動いていません" in capsys.readouterr().out
        assert not (d / ".editor/server.json").exists()
    finally:
        victim.kill()
        victim.wait()
