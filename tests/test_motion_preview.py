"""動きの確認の見本づくり（scripts/motion_preview.py）の試験。

デッキの HTML から「動きなし」（none.html）と「勧める組み合わせ」（choice.html）の写しと、2つを並べた compare.html を作る。
元のデッキのフォルダーには何も書かない。
"""
import subprocess
import sys
from pathlib import Path

from helpers import page_session

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "motion_preview.py"


def run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True)


def snapshot_dir(d: Path):
    return {p.relative_to(d): p.read_bytes() for p in sorted(d.rglob("*")) if p.is_file()}


def test_preview_writes_three_pages(tmp_path, generic_dir):
    r = run(generic_dir / "proposal.html", "--choice", "send,entry=bounce,point", "--out", tmp_path)
    assert r.returncode == 0, r.stderr
    assert sorted(p.name for p in tmp_path.iterdir()) == ["choice.html", "compare.html", "none.html"]
    compare = (tmp_path / "compare.html").read_text(encoding="utf-8")
    assert compare.count("<iframe") == 2 and 'src="none.html"' in compare and 'src="choice.html"' in compare
    assert "動きなし" in compare and "勧める組み合わせ" in compare


def test_preview_choice_is_applied(browser, tmp_path, generic_dir):
    assert run(generic_dir / "proposal.html", "--choice", "send,entry=bounce,point", "--out", tmp_path).returncode == 0
    with page_session(browser, (tmp_path / "choice.html").as_uri()) as page:
        page.wait_for_function("!!window.__sp")
        assert page.evaluate("__sp.deckMotion()") == {"send": True, "entry": "bounce", "point": True}
        assert page.evaluate("slideDeck.info.slides.length") > 1           # 描画と player.js は元のフォルダーから読めている
    with page_session(browser, (tmp_path / "none.html").as_uri()) as page:
        page.wait_for_function("!!window.__sp")
        assert page.evaluate("__sp.deckMotion()") == {"send": False, "entry": None, "point": False}
    with page_session(browser, (tmp_path / "compare.html").as_uri()) as page:
        page.wait_for_function("document.querySelectorAll('iframe').length === 2")


def test_preview_rejects_bad_choice(tmp_path, generic_dir):
    r = run(generic_dir / "proposal.html", "--choice", "entry=foo", "--out", tmp_path)
    assert r.returncode == 2 and r.stderr.strip()
    for old_name in ("ppt", "meiji"):
        assert run(generic_dir / "proposal.html", "--choice", f"entry={old_name}", "--out", tmp_path).returncode == 2
    r = run(generic_dir / "proposal.html", "--choice", "send,blink", "--out", tmp_path)
    assert r.returncode == 2


def test_preview_rejects_page_without_player(tmp_path):
    (tmp_path / "src").mkdir()
    src = tmp_path / "src" / "plain.html"
    src.write_text("<html><head></head><body><script src='render.js'></script></body></html>", encoding="utf-8")
    r = run(src, "--choice", "none", "--out", tmp_path / "out")
    assert r.returncode == 2 and "player.js" in r.stderr


def test_preview_leaves_source_alone(tmp_path, generic_dir):
    before = snapshot_dir(generic_dir)
    assert run(generic_dir / "motion.html", "--choice", "none", "--out", tmp_path).returncode == 0
    assert snapshot_dir(generic_dir) == before


def test_preview_refuses_to_write_into_source(generic_dir):
    r = run(generic_dir / "proposal.html", "--choice", "none", "--out", generic_dir)
    assert r.returncode == 2
