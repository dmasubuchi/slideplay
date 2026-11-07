"""editor/convert.py（Markdown をデッキの元に変える）の試験。"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from editor.convert import ConvertError, convert, find_markdown  # noqa: E402

DECKS = Path(__file__).resolve().parent / "editor_decks"


@pytest.fixture
def basic():
    return DECKS / "basic" / "下書き.md"


@pytest.fixture
def tmp_deck(tmp_path):
    def make(md_text):
        p = tmp_path / "下書き.md"
        p.write_text(md_text, encoding="utf-8", newline="")
        return p
    return make


def all_texts(slide):
    """(行, 始め, 終わり, 文字) を、head・箇条書きとその sub・p・h3 の全部について返す。"""
    if slide["head"]:
        yield (*slide["head"]["src"], slide["head"]["text"])
    for b in slide["blocks"]:
        if b["kind"] == "list":
            for it in b["items"]:
                yield (*it["src"], it["text"])
                for sub in it["sub"]:
                    yield (*sub["src"], sub["text"])
        elif b["kind"] == "p":
            for ln in b["lines"]:
                yield (*ln["src"], ln["text"])
        elif b["kind"] == "h3":
            yield (*b["src"], b["text"])


def test_pages_ids_and_types(basic):
    d = convert(basic)
    assert [s["id"] for s in d["slides"]] == ["s01", "s02", "s03", "s04", "p5"]
    assert [s["type"] for s in d["slides"]] == ["表紙", "ふつう", "図と文", "ふつう", "ふつう"]
    assert d["info"] == {"id": "deck", "title": "検索のしくみ", "color": "#0b6bcb"}


def test_steps_from_star_items(basic):
    s02 = convert(basic)["slides"][1]
    items = s02["blocks"][0]["items"]
    assert [i["step"] for i in items] == [0, 1, 2] and s02["steps"] == 2
    assert items[0]["sub"][0]["text"] == "前回の「桶狭間」の検索も、この方式だった"
    assert s02["title"] == "キーワード検索は珍しい語ほど重く見る"
    assert s02["head"]["text"] == "キーワード検索は**珍しい語**ほど重く見る"
    assert s02["notes"] == "ここで3分。BM25 の式は話さない"


def test_src_points_at_text(basic):
    lines = basic.read_text(encoding="utf-8").splitlines()
    n = 0
    for s in convert(basic)["slides"]:
        for line, a, b, text in all_texts(s):          # head・list の項目と sub・p・h3 を全部
            assert lines[line - 1][a:b] == text
            n += 1
    assert n >= 10


def test_image_and_html_page(basic):
    s03, s04 = convert(basic, editing=True)["slides"][2:4]
    img = [b for b in s03["blocks"] if b["kind"] == "img"][0]
    assert img["path"] == "fig/flow.svg" and img["missing"] is False and isinstance(img["v"], int)
    assert s04["html"].strip() == '<div class="rrf">RRF = Σ 1/(k + rank)</div>'
    assert "v" not in [b for b in convert(basic)["slides"][2]["blocks"] if b["kind"] == "img"][0]


def test_warnings(tmp_deck):          # tmp_deck(md_text) が tmp_path に下書き.md を書いてパスを返す
    d = convert(tmp_deck("# a\n\n![x](fig/none.svg)\n\n---\n<!-- _class: 三段 -->\n# b\n\n![y](../out.png)\n"))
    assert [w["message"] for w in d["warnings"]] == [
        "fig/none.svg がありません", "型「三段」はありません。ふつうで描きます", "../out.png はデッキのフォルダーの外なので使えません"]


@pytest.mark.parametrize("md, line, message", [
    ("<!-- id: a -->\n# a\n---\n<!-- id: a -->\n# b\n", 4, "ID a が2つあります（1行目と4行目）"),
    ("<!-- id: 1a -->\n# a\n", 1, "ID 1a は使えません。英字で始め、英数字・-・_ だけにしてください"),
    ("---\nmarp: true\n# a\n", 1, "先頭の --- が閉じていません"),
    ("# a\n<!-- ノート\n", 2, "<!-- が閉じていません"),
    ("---\nmarp: true\n---\n", 1, "ページがありません"),
])
def test_errors(tmp_deck, md, line, message):
    with pytest.raises(ConvertError) as e:
        convert(tmp_deck(md))
    assert (e.value.line, e.value.message) == (line, message)
    assert str(e.value) == f"{line}行目：{message}"


def test_marp_directives_are_not_notes(tmp_deck):
    s = convert(tmp_deck("<!-- paginate: true -->\n<!-- TODO: 図を足す -->\n# a\n"))["slides"][0]
    assert s["notes"] == "TODO: 図を足す"


def test_separator_inside_code_fence(tmp_deck):
    d = convert(tmp_deck("# a\n\n```\n---\n```\n"))
    assert len(d["slides"]) == 1 and d["slides"][0]["blocks"][0]["kind"] == "pre"


def test_bom_and_crlf(tmp_deck):
    path = tmp_deck("﻿---\r\ntitle: T\r\n---\r\n# a\r\n- b\r\n")
    d = convert(path)
    assert d["info"]["title"] == "T"
    item = d["slides"][0]["blocks"][0]["items"][0]
    assert item["src"] == [5, 2, 3]


def test_find_markdown(tmp_path):
    one = tmp_path / "one"; one.mkdir(); (one / "下書き.md").write_text("# a\n", encoding="utf-8")
    assert find_markdown(one) == one / "下書き.md" and find_markdown(one / "下書き.md") == one / "下書き.md"
    empty = tmp_path / "empty"; empty.mkdir()
    with pytest.raises(ValueError, match="に .md がありません$"): find_markdown(empty)
    (one / "別.md").write_text("# b\n", encoding="utf-8")
    with pytest.raises(ValueError, match="に .md が2つあります。ファイルを指定してください$"): find_markdown(one)
    with pytest.raises(ValueError, match="がありません$"): find_markdown(tmp_path / "ない")


def test_provisional_id_skips_explicit(tmp_deck):
    d = convert(tmp_deck("# a\n---\n<!-- id: p1 -->\n# b\n---\n<!-- id: p4 -->\n# c\n---\n# d\n"))
    assert [s["id"] for s in d["slides"]] == ["p1b", "p1", "p4", "p4b"]
    d = convert(tmp_deck("<!-- id: p2 -->\n# a\n---\n# b\n"))
    assert [s["id"] for s in d["slides"]] == ["p2", "p2b"]


@pytest.mark.parametrize("key", [
    "theme", "paginate", "_paginate", "header", "_header", "footer", "_footer", "backgroundColor",
    "_backgroundColor", "backgroundImage", "_backgroundImage", "color", "_color", "size", "style",
    "headingDivider", "lang", "title", "description", "author", "image", "marp", "math"])
def test_marp_directive_list_is_discarded(tmp_deck, key):
    s = convert(tmp_deck(f"<!-- {key}: x -->\n<!-- メモ: 残す -->\n# a\n"))["slides"][0]
    assert s["notes"] == "メモ: 残す"


@pytest.mark.parametrize("nl", ["\n", "\r\n"])
def test_multiline_paragraph_lines(tmp_deck, nl):
    path = tmp_deck(nl.join(["# a", "", "一行目です", "  二行目です", "", "- x"]) + nl)
    p = [b for b in convert(path)["slides"][0]["blocks"] if b["kind"] == "p"][0]
    assert p["text"] == "一行目です\n二行目です" and p["src"] == [3, 0, 5]
    lines = path.read_bytes().decode("utf-8").splitlines()
    assert [l["text"] for l in p["lines"]] == ["一行目です", "二行目です"]
    for l in p["lines"]:
        no, a, b = l["src"]
        assert lines[no - 1][a:b] == l["text"]


def test_title_falls_back_to_id(tmp_deck):
    d = convert(tmp_deck("<!-- id: x1 -->\n- a\n---\n- b\n"))
    assert [s["title"] for s in d["slides"]] == ["x1", "p2"]


def test_auto_id_flag(tmp_deck):
    d = convert(tmp_deck("<!-- id: s01 -->\n# 一\n\n---\n\n# 二\n"))
    assert [(s["id"], s["auto_id"]) for s in d["slides"]] == [("s01", False), ("p2", True)]


def test_title_strips_bigger_marks(tmp_deck):
    d = convert(tmp_deck("# ++大きな++題名\n"))
    assert d["slides"][0]["title"] == "大きな題名"
