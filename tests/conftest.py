"""pytest の共通設定。"""
import json
import os
import shutil
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

# 作業フォルダー：環境変数 SLIDE_PLAYER_WORK_ROOT が空でなければその値（試験を別の場所で走らせるとき）、
# なければ OS の一時フォルダーの下の slide-player-tests。pytest の一時フォルダー（basetemp）と
# WebKit の記録（webkit-report.json）は、この下に置く。
WORK_ROOT = (
    Path(os.environ["SLIDE_PLAYER_WORK_ROOT"]).expanduser()
    if os.environ.get("SLIDE_PLAYER_WORK_ROOT")
    else Path(tempfile.gettempdir()) / "slide-player-tests"
)


def pytest_configure(config):
    basetemp = WORK_ROOT / "pytest-tmp"
    basetemp.parent.mkdir(parents=True, exist_ok=True)
    config.option.basetemp = basetemp


# ---- 試験台（プレイヤーを試す2つの中身） ----

@pytest.fixture(scope="session")
def generic_dir():
    """汎用の見本（商談の提案書など）。リポジトリの examples/generic。"""
    return REPO / "examples" / "generic"


def _chapter_def(n: int) -> dict:
    """第 n 章のデッキの定義（GenericSlides.createDeck に渡すもの）。ch-01 は25枚（縮小一覧が何行にもなる）、ch-02〜ch-07 は7枚。"""
    sections = [{"id": "A", "title": "節A"}, {"id": "B", "title": "節B"}] + ([{"id": "C", "title": "節C"}] if n == 1 else [])
    per_section = 8 if n == 1 else 3
    slides = [{"id": "s01", "type": "title", "title": f"第{n}章", "subtitle": "講座の形の見本", "minutes": 1, "notes": f"第{n}章の表紙。"}]
    k = 1
    for section in sections:
        for j in range(1, per_section + 1):
            k += 1
            slides.append({
                "id": f"s{k:02d}", "type": "bullets", "section": section["id"], "title": f"{section['title']}の{j}枚目", "minutes": 2,
                "items": [f"項目 {k}-1", {"text": f"項目 {k}-2（段階で出る）", "at": 1}] if k % 3 == 0 else [f"項目 {k}-1", f"項目 {k}-2"],
                "notes": f"スライド s{k:02d} のノート。"})
    return {"id": f"ch-{n:02d}", "title": f"第{n}章の見本", "label": f"第{n}章", "color": "#0b6bcb", "home": "../index.html",
            "sections": sections, "slides": slides}


def _script_json(value) -> str:
    """<script> の中に置く JSON（文字の中の < で script が閉じないように）。"""
    return json.dumps(value, ensure_ascii=False, indent=1).replace("<", "\\u003c")


@pytest.fixture(scope="session")
def course_dir(tmp_path_factory):
    """講座の形の見本：目次 index.html（ch-01〜ch-07 の7枚のカード）と、各章の ch-NN/slides.html。

    汎用の描画（examples/generic/render.js）だけで作る。player.js と render.js は deck/ に写して読む。
    各章のページは、内容の CSS が #stage の位置を決めている場合（left:50%・top:50%）の見本にもなる
    （プレイヤーが style で決め直す）。作業フォルダー（WORK_ROOT）の下に作り、リポジトリには何も書かない。
    """
    root = tmp_path_factory.mktemp("course")
    (root / "deck").mkdir()
    shutil.copy2(REPO / "player" / "player.js", root / "deck" / "player.js")
    shutil.copy2(REPO / "examples" / "generic" / "render.js", root / "deck" / "render.js")
    decks = []
    for n in range(1, 8):
        info = _chapter_def(n)
        (root / f"ch-{n:02d}").mkdir()
        (root / f"ch-{n:02d}" / "slides.html").write_text(
            '<!doctype html>\n<html lang="ja">\n<head>\n<meta charset="utf-8">\n'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">\n<title>{info["title"]}</title>\n'
            "<style>#stage { position: absolute; left: 50%; top: 50%; }</style>\n</head>\n<body>\n"
            '<div id="stage" class="sp-target"></div>\n<script src="../deck/render.js"></script>\n'
            f"<script>\nwindow.slideDeck = GenericSlides.createDeck({_script_json(info)});\n</script>\n"
            '<script src="../deck/player.js"></script>\n</body>\n</html>\n', encoding="utf-8")
        minutes = sum(s.get("minutes") or 0 for s in info["slides"])
        decks.append({"id": info["id"], "href": f"ch-{n:02d}/slides.html", "label": info["label"], "title": info["title"],
                      "color": info["color"], "items": [x["title"] for x in info["sections"]],
                      "meta": f"{len(info['slides'])}枚・約{minutes}分"})
    catalog = {"contract": 1, "title": "講座の形の見本", "lead": f"全{len(decks)}章", "decks": decks}
    (root / "index.html").write_text(
        '<!doctype html>\n<html lang="ja">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "<title>講座の形の見本</title>\n</head>\n<body>\n"
        f"<script>\nwindow.slideCatalog = {_script_json(catalog)};\n</script>\n"
        '<script src="deck/player.js"></script>\n</body>\n</html>\n', encoding="utf-8")
    return root


@pytest.fixture(scope="session")
def playwright_instance():
    """Playwright を1回だけ起動する（Playwright は1つの thread で1つしか動かせないので、Chromium も WebKit もここから起動する）。"""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        yield p


@pytest.fixture(scope="session")
def browser(playwright_instance):
    """Chromium を1回だけ起動する。"""
    from helpers import CHROMIUM_ARGS

    b = playwright_instance.chromium.launch(args=CHROMIUM_ARGS)
    yield b
    b.close()


# ---- WebKit の参考の試験（@pytest.mark.webkit）の結果を、1つの JSON に書く ----

WEBKIT_REPORT = WORK_ROOT / "webkit-report.json"
_webkit_results: list[dict] = []


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if not item.get_closest_marker("webkit"):
        return
    # 試験の本体の結果（call）。準備（setup）で止まったとき（WebKit が入っていない skip など）も1件として数える
    if report.when == "call" or (report.when == "setup" and report.outcome != "passed"):
        message = ""
        if report.outcome == "failed":
            crash = getattr(report.longrepr, "reprcrash", None)
            message = (crash.message if crash else str(report.longrepr))[:1500]
        elif report.outcome == "skipped" and isinstance(report.longrepr, tuple):
            message = str(report.longrepr[2])
        _webkit_results.append({
            "test": item.nodeid.split("::", 1)[1],
            "area": item.name.split("_")[1] if item.name.startswith("test_") else "",
            "outcome": report.outcome,
            "seconds": round(report.duration, 3),
            "message": message,
        })


def pytest_sessionfinish(session, exitstatus):
    """WebKit の試験が1つでも走った（または skip された）ときだけ、結果を書く。"""
    if not _webkit_results:
        return
    import datetime
    import platform

    info = getattr(session.config, "_webkit_info", {})
    count = {k: sum(1 for r in _webkit_results if r["outcome"] == k) for k in ("passed", "failed", "skipped")}
    areas: dict[str, dict] = {}
    for r in _webkit_results:
        a = areas.setdefault(r["area"], {"passed": 0, "failed": 0, "skipped": 0})
        a[r["outcome"]] += 1
    report = {
        "generated": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "browser": "webkit",
        "webkit_version": info.get("version"),
        "playwright_webkit_build": info.get("note"),
        "platform": platform.platform(),
        "purpose": "iPad の Safari に向けた参考。完成の条件には含めない（対象は Chrome 系のブラウザー）",
        "summary": count,
        "areas": areas,
        "tests": _webkit_results,
    }
    WEBKIT_REPORT.parent.mkdir(parents=True, exist_ok=True)
    WEBKIT_REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
