"""slideplay の版の試験：人に伝える版は1つ（セマンティックバージョニング）で、書く場所すべてに同じ数字がある。

- 版は slideplay の版だけ（最初の公開版は 0.1.0）。`contract: 1` はデッキと目次の形の番号で、人に伝える版ではない
- 約束の版の古い書き方（v1.6・v1.5・v1.4 など）が、README・CONTRACT.md・紹介のページ・目次・デモ・player.js に残っていない
- player.js の1行目が `// slideplay <版>`。コメントに約束の版の注記（「v1.4」「約束 v1.6」など）がない
- デッキ・目次が宣言する `contract` はどれも 1

版を上げるときは、下の VERSION と、VERSION_PLACES に並ぶ場所のすべてを同じ数字にする。
"""
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

VERSION = "0.1.0"

# 版を書く場所。README の先頭の行は、紹介のページの先頭にも出る（scripts/build_portal.py が README から読む）
VERSION_PLACES = [
    "README.md", "README.ja.md", "CONTRACT.md", "index.html", "index.ja.html",
    "catalog.html", "catalog.ja.html", "demo/en/intro.html", "demo/ja/intro.html",
    "player/player.js",
]
# 約束の版の古い書き方を探す場所
OLD_STYLE_PLACES = [
    "README.md", "README.ja.md", "CONTRACT.md", "index.html", "index.ja.html", "catalog.html", "catalog.ja.html",
    *[f"demo/{lang}/{deck}.html" for lang in ("en", "ja") for deck in ("intro", "chic", "bounce")],
    "player/player.js", "examples/generic/render.js", "examples/generic/motion.html",
]
# v1.6 のような書き方。保存のキー（sp-memo-v1 など。ドットが続かない）は対象外
OLD_STYLE = re.compile(r"(?<![\w-])v1\.\d")
OLD_STYLE_JA = re.compile(r"約束\s*v\d|契約\s*v\d|約束（v\d")


def read(name):
    return (REPO / name).read_text(encoding="utf-8")


def test_version_is_semver():
    assert re.fullmatch(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", VERSION)


@pytest.mark.parametrize("name", VERSION_PLACES)
def test_version_is_written(name):
    assert VERSION in read(name), f"{name} に版 {VERSION} がない"


def test_the_version_in_each_place_is_the_only_one():
    """どの場所にも、別の x.y.z の版（0.2.0 など）が混ざっていない。player.js はコメントの1行目だけを見る。"""
    semver = re.compile(r"(?<![\w.])(\d+\.\d+\.\d+)(?![\w.])")
    for name in VERSION_PLACES:
        text = read(name)
        if name == "player/player.js":
            text = text.splitlines()[0]
        if name == "CONTRACT.md":
            text = text.replace("「0.2.0 で追加」", "")  # §6 の書き方の例
        if name.endswith(".html"):
            text = re.sub(r"<style>.*?</style>", "", text, flags=re.S)
        found = set(semver.findall(text))
        assert found <= {VERSION}, f"{name} に別の版らしい数字がある: {sorted(found - {VERSION})}"


def test_readmes_show_the_version_near_the_top_and_the_portals_follow():
    en, ja = read("README.md"), read("README.ja.md")
    assert f"\nVersion {VERSION}\n" in en[:300]
    assert f"\nバージョン {VERSION}\n" in ja[:300]
    assert f'<p class="version">Version {VERSION}</p>' in read("index.html")
    assert f'<p class="version">バージョン {VERSION}</p>' in read("index.ja.html")


def test_readmes_explain_that_contract_is_the_format_number():
    en, ja = read("README.md"), read("README.ja.md")
    assert "`contract: 1`" in en and "not the version of slideplay" in en and "version to cite" in en
    assert "`contract: 1`" in ja and "slideplay の版ではない" in ja and "人に伝える版" in ja


def test_contract_md_has_one_version_and_a_format_number():
    text = read("CONTRACT.md")
    assert text.splitlines()[0] == "# slideplay：中身とプレイヤーの約束（contract 1）"
    sections = re.findall(r"^## (\d+)\. ", text, re.M)
    assert sections == ["0", "1", "2", "3", "4", "5", "6"]
    section6 = text.split("## 6. 版", 1)[1]
    assert VERSION in section6 and "セマンティックバージョニング" in section6
    assert "`contract: 1`" in section6 and "2 に上げる" in section6
    assert "で追加" in section6  # 以降の追加には、足した版を付ける（例：「0.2.0 で追加」）


@pytest.mark.parametrize("name", OLD_STYLE_PLACES)
def test_no_old_contract_version_strings(name):
    text = read(name)
    assert OLD_STYLE.findall(text) == [], f"{name} に約束の版の古い書き方（v1.x）が残っている"
    assert OLD_STYLE_JA.findall(text) == [], f"{name} に「約束 v…」の書き方が残っている"


def test_player_header_and_comments_have_no_contract_version():
    lines = read("player/player.js").splitlines()
    assert lines[0] == f"// slideplay {VERSION}"
    # コメントの中の「約束 §N」はそのまま。版の注記はない
    comments = [line.split("//", 1)[1] for line in lines if "//" in line]
    assert any("約束 §" in c for c in comments)
    for c in comments:
        assert OLD_STYLE.search(c) is None and OLD_STYLE_JA.search(c) is None, c


def test_decks_and_catalogs_declare_contract_1():
    names = ["catalog.html", "catalog.ja.html", *[f"demo/{lang}/{deck}.html" for lang in ("en", "ja") for deck in ("intro", "chic", "bounce")]]
    for name in names:
        text = read(name)
        declared = re.findall(r"^\s*contract:\s*(\d+)", text, re.M)
        # デッキは GenericSlides.createDeck が contract を足すので、宣言がないものもある（あれば 1）
        assert set(declared) <= {"1"}, f"{name}: contract が 1 でない"
    assert re.search(r"contract:\s*1\b", read("examples/generic/render.js"))
