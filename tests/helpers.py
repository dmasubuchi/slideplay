"""ブラウザでデッキのページを開く試験用の関数。

撮影の条件はどの試験でも同じ：Chromium、viewport 1920×1080、device_scale_factor=1。
ページが pageerror（捕まえていない例外）を出したら、その試験は失敗にする。
切り替えの動き（View Transitions）は、既存の試験が結果を待たずに確かめられるよう、既定では止める（reduced_motion="reduce"）。
動きを確かめる試験（test_motion.py）だけ、reduced_motion="no-preference" で開く。
"""
from contextlib import contextmanager
from pathlib import Path

VIEWPORT = {"width": 1920, "height": 1080}
REDUCED_MOTION = "reduce"                 # 既定：OS の「視差効果を減らす」が入っている状態（プレイヤーは動きを止める）

# Chromium の起動オプション。既定のままだと、同じ入力でも画素が揺れて、前と後の比較に意味がなくなる。
# - --disable-gpu-rasterization：GPU での描画だと、見出しの大きな数字の端が、撮るたびに1ピクセル（色が1違う）揺れる
# - --disable-partial-raster：描き直した範囲だけを描き足す仕組みのせいで、直前に何を描いたかによって、
#   箱の縁や文字の端の数ピクセルが変わる（メインの舞台に描いても、別の描画先に描いても、見た目の画素が同じになる）
# どちらも描画の仕組みだけを固定する。デッキの中身（DOM・CSS）には触れない。
CHROMIUM_ARGS = ["--disable-gpu-rasterization", "--disable-partial-raster"]


def slides_url(course_dir: Path, ch: int, render: bool = True) -> str:
    """ch-NN/slides.html の file:// の URL。render=True なら ?render を付ける。"""
    url = (Path(course_dir).resolve() / f"ch-{ch:02d}" / "slides.html").as_uri()
    return url + ("?render" if render else "")


def _errors_message(errors: list[str]) -> str:
    return "ページが例外を出した:\n" + "\n".join(errors)


def assert_no_page_errors(page) -> None:
    """open_page・open_deck で開いたページが pageerror を出していれば、AssertionError で失敗させる。"""
    if page.sp_errors:
        raise AssertionError(_errors_message(page.sp_errors))


def _new_recording_page(browser, viewport, reduced_motion=REDUCED_MOTION):
    """pageerror（捕まえていない例外）を page.sp_errors に記録する新しいページを返す。"""
    width, height = viewport
    page = browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=1, reduced_motion=reduced_motion)
    page.sp_errors = []
    page.on("pageerror", lambda e: page.sp_errors.append(str(e)))
    return page


@contextmanager
def page_session(browser, url: str, viewport=(1440, 900), reduced_motion=REDUCED_MOTION):
    """url をそのまま開いて（?render は付けない。付けたければ url に書く）ページを渡し、抜けるときに閉じる。

    ページが pageerror を出していたら、抜けるときに AssertionError で失敗させる（呼ぶ側が確かめ忘れない）。
    with の中の試験が先に例外で終わったときは、その例外と pageerror の両方を知らせる（元の例外は __cause__）。

    限界：見えるのは、ページを閉じるまでに届いた pageerror だけ。ページを閉じた後に起きる例外（閉じた後に走る
    setTimeout や非同期の処理が投げるもの）は、ページと一緒に消えて見えない。時間をかけて起きる処理を確かめたいときは、
    試験の中でその処理が終わるまで待ってから、with を抜ける。
    """
    page = _new_recording_page(browser, viewport, reduced_motion)
    try:
        page.goto(url)
        yield page
    except BaseException as exc:
        page.close()                          # 先に閉じる：直前の操作が起こした遅れの例外（setTimeout など）は、閉じるまでに届く
        if page.sp_errors:
            raise AssertionError(f"{_errors_message(page.sp_errors)}\n（試験の中でも例外が出た: {exc!r}）") from exc
        raise
    else:
        page.close()                          # 先に閉じてから、記録を読む（上と同じ理由）
        if page.sp_errors:
            raise AssertionError(_errors_message(page.sp_errors))


def open_page(browser, url: str, viewport=(1440, 900), reduced_motion=REDUCED_MOTION):
    """新しいページで url をそのまま開いて返す（?render は付けない。付けたければ url に書く）。閉じるのは呼んだ側。

    pageerror を page.sp_errors に記録する（assert_no_page_errors が使える）。
    開く途中で pageerror が出たら、ページを閉じて AssertionError にする。
    開いたあとの pageerror も自動で確かめたいときは、page_session を使う。
    """
    page = _new_recording_page(browser, viewport, reduced_motion)
    try:
        page.goto(url)
        assert_no_page_errors(page)
    except BaseException:
        page.close()
        raise
    return page


def open_deck(browser, course_dir: Path, ch: int, render: bool = True):
    """新しいページで第 ch 章を開いて返す。閉じるのは呼んだ側。

    開く途中で pageerror が出たら、ページを閉じて AssertionError にする。
    開いた後の例外は assert_no_page_errors(page) で確かめる。
    """
    return open_page(browser, slides_url(course_dir, ch, render), (VIEWPORT["width"], VIEWPORT["height"]))


def evaluate(browser, course_dir: Path, ch: int, expr: str):
    """新しい ?render のページで expr を評価して返し、ページを閉じる。"""
    page = open_deck(browser, course_dir, ch)
    try:
        result = page.evaluate(expr)
        assert_no_page_errors(page)
        return result
    finally:
        page.close()


def deck_info(browser, course_dir: Path, ch: int) -> list[dict]:
    """第 ch 章の deckInfo() を返し、ページを閉じる。"""
    return evaluate(browser, course_dir, ch, "deckInfo()")


def deck_with_motion(src_html: Path, out_dir: Path, motion: dict | None, name: str | None = None) -> Path:
    """汎用の見本のデッキ src_html の写しを out_dir に作り、info.motion を motion で上書きして、その HTML の場所を返す。

    examples/generic と player/ を今と同じ相対の位置で写す（リンク・目次・player.js の場所が元と同じに働く）。
    上書きは scripts/motion_preview.py の inject_motion で、player.js を読む直前に入れる。motion が None なら入れない。
    """
    import shutil
    import sys

    repo = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(repo / "scripts"))
    from motion_preview import inject_motion

    generic = out_dir / "examples" / "generic"
    if not generic.exists():
        shutil.copytree(repo / "examples" / "generic", generic)
        shutil.copytree(repo / "player", out_dir / "player")
    dest = generic / (name or Path(src_html).name)
    dest.write_text(inject_motion(Path(src_html).read_text(encoding="utf-8"), None, motion), encoding="utf-8")
    return dest
