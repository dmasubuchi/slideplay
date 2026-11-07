"""静止画の撮影と比較の関数、同じ入力を2回撮ったときの一致、描画先の独立性の試験（CONTRACT.md §2.5、§3.1）。

撮影の条件（?render の静止画を撮る条件）：Chromium、viewport 1920×1080、DSF 1、ページ全体の撮影、URL に ?render。
合格は画素がすべて一致すること。試験台は講座の形の見本（course_dir。tests/conftest.py が作る ch-01〜ch-07）。
"""
import json
import shutil

import pytest
from PIL import Image

import stills
from helpers import CHROMIUM_ARGS, VIEWPORT, assert_no_page_errors, deck_info, open_deck


# ---- 出力先と、基準の静止画 ----

@pytest.fixture(scope="session")
def out_dir(tmp_path_factory):
    """静止画の出力先。作業フォルダー（tests/conftest.py の WORK_ROOT）の下に置く。"""
    return tmp_path_factory.mktemp("stills")


@pytest.fixture(scope="session")
def course_stills(browser, course_dir, out_dir):
    """講座の形の見本の静止画（基準）を、章ごとに初めて要るときに1回だけ撮る。章番号 → 静止画の一覧。"""
    cache = {}

    def get(ch):
        if ch not in cache:
            cache[ch] = stills.capture(course_dir, ch, out_dir / "baseline", browser)
        return cache[ch]

    return get


def fresh_dir(path):
    """空のフォルダーを作り直す（前の実行の画像が残って、比較が古い画像に当たるのを防ぐ）。"""
    shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True)
    return path


# ---- 比較の関数そのものの試験（比べる側が壊れていて、何も検出しない、を防ぐ） ----

def make_png(path, size=(8, 6), color=(255, 255, 255), dot=None):
    img = Image.new("RGB", size, color)
    if dot:
        img.putpixel(dot, (0, 0, 0))
    img.save(path)
    return path


def test_diff_identical_images_is_none(tmp_path):
    a = make_png(tmp_path / "a.png")
    b = make_png(tmp_path / "b.png")
    assert stills.diff(a, b) is None


def test_diff_finds_single_pixel(tmp_path):
    a = make_png(tmp_path / "a.png")
    b = make_png(tmp_path / "b.png", dot=(5, 3))
    assert stills.diff(a, b) == (5, 3, 6, 4)          # (左, 上, 右, 下)。右と下は含まない


def test_diff_finds_range_of_changes(tmp_path):
    a = make_png(tmp_path / "a.png", dot=(1, 1))
    b = make_png(tmp_path / "b.png", dot=(6, 4))
    assert stills.diff(a, b) == (1, 1, 7, 5)          # 両方の点を含む範囲


def test_diff_different_sizes_is_a_difference(tmp_path):
    a = make_png(tmp_path / "a.png", size=(8, 6))
    b = make_png(tmp_path / "b.png", size=(8, 7))
    assert stills.diff(a, b) == (0, 0, 8, 7)          # 大きさが違えば、全体が違う


# ---- 撮影の関数の試験 ----

def test_capture_names_count_and_env(browser, course_dir, out_dir):
    out = fresh_dir(out_dir / "capture-check")
    info = deck_info(browser, course_dir, 2)
    paths = stills.capture(course_dir, 2, out, browser)
    expected = [stills.still_name(2, i, s["id"], st) for i, s in enumerate(info) for st in range(s["steps"] + 1)]
    assert expected                                    # 1枚もない、という空振りを防ぐ
    assert [p.name for p in paths] == expected
    assert all(p.parent == out and p.is_file() for p in paths)
    assert sorted(p.name for p in out.glob("*.png")) == sorted(expected)
    assert all(Image.open(p).size == (VIEWPORT["width"], VIEWPORT["height"]) for p in paths)
    env = json.loads((out / "env.json").read_text(encoding="utf-8"))
    assert set(env) == {"chromium", "chromium_args", "platform", "viewport", "device_scale_factor"}
    assert env["chromium"] == browser.version and env["platform"] and env["chromium_args"] == CHROMIUM_ARGS
    assert env["viewport"] == VIEWPORT and env["device_scale_factor"] == 1


# ---- 比べる土台：同じ入力を2回撮ると、画素が一致する ----

@pytest.mark.parametrize("ch", [1, 3])      # 描画の仕組み（GPU）によっては、大きな文字の端が1ピクセル揺れる。揺れる環境では、比較に意味がない
def test_capture_is_deterministic(browser, course_dir, out_dir, course_stills, ch):
    first = course_stills(ch)
    second = stills.capture(course_dir, ch, out_dir / "baseline-again", browser)
    assert len(first) == len(second) > 0
    assert [p.name for p in first] == [p.name for p in second]
    bad = [(p.name, box) for p, q in zip(first, second) if (box := stills.diff(p, q))]
    assert bad == []                                   # 揺れる環境では、前と後の比較に意味がない


# ---- 描画先の独立性：メイン以外に描いても、メインの舞台は変わらない ----

# 第 i スライドの段階 step をメインに描き、同じ i と他の4枚を新しい描画先5つに逆順で描いて消す。
# もう一度5つ描き、今度は消さずに画面の外（position:fixed; left:-10000px）に残す。返すのは、空振りを見分ける数。
# 呼ぶ側が、描画先が存在している間のメインを撮り、REMOVE_OFFSTAGE で消してからもう一度撮る。
OFFSTAGE_PROCEDURE = r"""([i, step, others]) => {
  const five = [[i, step], ...others];
  const drawFive = () => [...five].reverse().map(([ref, st]) => {
    const t = document.createElement('div');
    t.className = 'sp-target';
    t.style.cssText = 'position:fixed; left:-10000px; top:0';
    t.dataset.testOffstage = '';                          // 後で消すための印
    document.body.append(t);
    slideDeck.render(ref, st, t);
    return t;
  });
  renderSlide(i, step);                                 // 1) メインに描く
  const first = drawFive();                             // 2) 新しい描画先5つに逆順で描く
  const firstDrawn = first.filter(t => t.childElementCount > 0).length;
  first.forEach(t => t.remove());                       // 3) 消して、もう一度5つ描く（今度は残す）
  const second = drawFive();
  const secondDrawn = second.filter(t => t.childElementCount > 0).length;
  const offscreen = second.every(t => t.getBoundingClientRect().right <= 0);     // 5つとも画面の外にある
  return { firstDrawn, secondDrawn, offscreen, targetsPresent: document.querySelectorAll('.sp-target').length };
}"""

REMOVE_OFFSTAGE = r"""() => {
  document.querySelectorAll('[data-test-offstage]').forEach(t => t.remove());
  return document.querySelectorAll('.sp-target').length;
}"""


@pytest.mark.parametrize("ch", [1, 2])
def test_main_stage_unchanged_after_offstage_renders(browser, course_dir, out_dir, course_stills, ch):
    baseline = {p.name: p for p in course_stills(ch)}
    out = fresh_dir(out_dir / "offstage-main" / f"ch-{ch:02d}")
    info = deck_info(browser, course_dir, ch)
    n = len(info)
    page = open_deck(browser, course_dir, ch)
    try:
        compared = 0
        bad = []
        for i, s in enumerate(info):
            # 同じ i と、他の4枚（次の4枚。章の終わりでは先頭に戻る）をそれぞれの最後の段階で描く
            others = [[(i + d) % n, info[(i + d) % n]["steps"]] for d in range(1, 5)]
            for step in range(s["steps"] + 1):
                r = page.evaluate(OFFSTAGE_PROCEDURE, [i, step, others])
                # 描画先が画面の外に5つ残っている（#stage と合わせて6つ）
                assert r == {"firstDrawn": 5, "secondDrawn": 5, "offscreen": True, "targetsPresent": 6}
                name = stills.still_name(ch, i, s["id"], step)
                # 描画先が存在している間のメインを撮って、基準と比べる
                got = stills.shoot(page, out / "with-targets" / name)
                box = stills.diff(baseline[name], got)
                compared += 1
                if box:
                    bad.append(("描画先あり", name, box))
                # 描画先を消してから撮って、基準と比べる
                assert page.evaluate(REMOVE_OFFSTAGE) == 1                              # 残るのは #stage だけ
                got = stills.shoot(page, out / "removed" / name)
                box = stills.diff(baseline[name], got)
                compared += 1
                if box:
                    bad.append(("描画先を消した後", name, box))
        assert_no_page_errors(page)
    finally:
        page.close()
    assert compared == 2 * sum(s["steps"] + 1 for s in info) > 0     # 0枚で通さない（描画先ありと消した後の2回ずつ）
    assert bad == []


# 新しい描画先を main と同じ位置（左上 (0,0)、縮小なし）に重ねる。メインの舞台には別のスライドを描いておく
TARGET_LOOKS_LIKE_MAIN = r"""([i, steps, otherIndex]) => {
  renderSlide(otherIndex, 0);                             // メインには別のスライドがある（重なりの確認）
  const t = document.createElement('div');
  t.className = 'sp-target';
  t.style.cssText = 'position:fixed; left:0; top:0; z-index:9';
  t.dataset.testTarget = '';                               // 後で消すための印（#stage にも style が付くので、style では見分けられない）
  document.body.append(t);
  slideDeck.render(i, steps, t);
  return t.childElementCount;
}"""


@pytest.mark.parametrize("ch", [1, 2])
def test_offstage_target_looks_like_main(browser, course_dir, out_dir, course_stills, ch):
    baseline = {p.name: p for p in course_stills(ch)}
    out = fresh_dir(out_dir / "offstage-target" / f"ch-{ch:02d}")
    info = deck_info(browser, course_dir, ch)
    n = len(info)
    page = open_deck(browser, course_dir, ch)
    try:
        compared = 0
        bad = []
        for i, s in enumerate(info):
            drawn = page.evaluate(TARGET_LOOKS_LIKE_MAIN, [i, s["steps"], (i + 1) % n])
            assert drawn > 0
            name = stills.still_name(ch, i, s["id"], s["steps"])
            got = stills.shoot(page, out / name)
            box = stills.diff(baseline[name], got)
            compared += 1
            if box:
                bad.append((name, box))
            page.evaluate("document.querySelector('[data-test-target]').remove()")      # 次のスライドのために消す
        assert_no_page_errors(page)
    finally:
        page.close()
    assert compared == n > 0                                    # 0枚で通さない
    assert bad == []
