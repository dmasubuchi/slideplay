"""editor/writeback.py（直しを Markdown に書き戻す）の試験。"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from editor.convert import convert  # noqa: E402
from editor.writeback import EDIT_CONFLICT, apply_edits, write_back  # noqa: E402

MD = "---\nmarp: true\n---\n\n<!-- id: s01 -->\n# 題名\n\n- 点数を高く付ける\n- a **b** c\n\n---\n\n# 二枚目\n\n本文\n"


def edit(key, line, a, b, before, after):
    return {"key": key, "src": [line, a, b], "before": before, "after": after}


def test_apply_replaces_range():
    text, res = apply_edits(MD, [edit("k1", 8, 2, 10, "点数を高く付ける", "点数を**高く**する")])
    assert text.splitlines()[7] == "- 点数を**高く**する"
    assert res == {"applied": ["k1"], "conflicts": [], "ids_added": []}


def test_two_edits_same_line():
    text, res = apply_edits("あいうえお\n", [edit("a", 1, 0, 1, "あ", "ア"), edit("b", 1, 3, 5, "えお", "エオ")])
    assert text == "アいうエオ\n" and sorted(res["applied"]) == ["a", "b"]


def test_overlapping_second_conflicts():
    text, res = apply_edits("あいうえお\n", [edit("a", 1, 0, 3, "あいう", "x"), edit("b", 1, 2, 4, "うえ", "y")])
    assert text == "xえお\n" and res["applied"] == ["a"] and res["conflicts"][0]["key"] == "b"


def test_conflict_when_text_changed():
    text, res = apply_edits(MD, [edit("k1", 8, 2, 10, "点数を低く付ける", "x"), edit("k2", 6, 2, 4, "題名", "新しい題名")])
    assert res["applied"] == ["k2"] and res["conflicts"] == [{"key": "k1", "message": EDIT_CONFLICT}]
    assert "- 点数を高く付ける" in text and "# 新しい題名" in text


def test_line_out_of_range_conflicts():
    _, res = apply_edits(MD, [edit("k", 999, 0, 1, "x", "y")])
    assert res["conflicts"] == [{"key": "k", "message": EDIT_CONFLICT}]


@pytest.mark.parametrize("after, message", [
    ("a\nb", "改行は入れられません"), ("a\rb", "改行は入れられません"),
    ("", "空にはできません。消すときはエディターで消してください"), ("   ", "空にはできません。消すときはエディターで消してください"),
    ("x <!-- y", "<!-- と --> は入れられません"), ("x --> y", "<!-- と --> は入れられません"),
    ("---", "--- だけの行にはできません"),
])
def test_rejects_bad_after(after, message):
    text, res = apply_edits(MD, [edit("k", 6, 2, 4, "題名", after)])
    assert text == MD and res["conflicts"] == [{"key": "k", "message": message}]


def test_ids_inserted_before_page_line():
    text, res = apply_edits(MD, [], ids=[(12, "p2")])
    assert text.splitlines()[11:14] == ["<!-- id: p2 -->", "", "# 二枚目"] and res["ids_added"] == ["p2"]


def test_keeps_bom_crlf_and_no_final_newline(tmp_path):
    p = tmp_path / "下書き.md"
    p.write_bytes("﻿# 題名\r\n\r\n- 点数\r\n- 二つ目".encode("utf-8"))
    p.chmod(0o640)
    res = write_back(p, [edit("k", 3, 2, 4, "点数", "得点")])
    assert p.read_bytes() == "﻿<!-- id: p1 -->\r\n# 題名\r\n\r\n- 得点\r\n- 二つ目".encode("utf-8")
    assert res["ids_added"] == ["p1"] and (p.stat().st_mode & 0o777) == 0o640


def test_write_back_adds_ids_that_convert_keeps(tmp_path):
    p = tmp_path / "下書き.md"
    p.write_text(MD, encoding="utf-8")
    write_back(p, [edit("k", 15, 0, 2, "本文", "本文です")])
    d = convert(p)
    assert [s["id"] for s in d["slides"]] == ["s01", "p2"] and not any(s["auto_id"] for s in d["slides"])


def test_write_back_skips_ids_when_convert_fails(tmp_path):
    p = tmp_path / "下書き.md"
    p.write_text("# 題名\n\n本文\n\n<!-- 閉じていない\n", encoding="utf-8")
    res = write_back(p, [edit("k", 3, 0, 2, "本文", "本文です")])
    assert res["ids_added"] == [] and p.read_text(encoding="utf-8").startswith("# 題名\n\n本文です\n")


def test_write_back_no_change_does_not_touch_file(tmp_path):
    p = tmp_path / "下書き.md"
    p.write_text("<!-- id: s01 -->\n# 題名\n", encoding="utf-8")
    ino = p.stat().st_ino
    res = write_back(p, [edit("k", 2, 2, 4, "違う", "x")])
    assert res["applied"] == [] and p.stat().st_ino == ino and not (tmp_path / ".editor" / "write.tmp").exists()
