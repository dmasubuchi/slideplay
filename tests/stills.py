"""静止画の撮影と比較。

?render の静止画を撮る撮り方：Chromium、viewport 1920×1080、
device_scale_factor=1、ページ全体の撮影（page.screenshot(path=…)）、URL に ?render。
"""
import json
import platform
from pathlib import Path

from PIL import Image, ImageChops

from helpers import CHROMIUM_ARGS, VIEWPORT, assert_no_page_errors, open_deck

DEVICE_SCALE_FACTOR = 1


def still_name(ch: int, i: int, slide_id: str, step: int) -> str:
    """静止画のファイル名。i は 0 から数えたスライドの位置。"""
    return f"{ch:02d}_{i + 1:02d}_{slide_id}_{step}.png"


def shoot(page, path: Path) -> Path:
    """ページ全体を撮って path に保存する（切り出しなし）。?render の静止画を撮るときの呼び方。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(path))
    return path


def write_env(out: Path, browser) -> None:
    """撮影した環境（Chromium の版と起動オプション、OS、viewport、DSF）を out/env.json に書く。"""
    env = {
        "chromium": browser.version,
        "chromium_args": CHROMIUM_ARGS,
        "platform": platform.platform(),
        "viewport": VIEWPORT,
        "device_scale_factor": DEVICE_SCALE_FACTOR,
    }
    (out / "env.json").write_text(json.dumps(env, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def capture(course_dir: Path, ch: int, out: Path, browser) -> list[Path]:
    """第 ch 章を ?render で開き、全スライドの段階 0〜steps を renderSlide(i, step) で描いて撮る。

    撮った画像のパスを、スライドの順・段階の順に返す。out に env.json も書く。
    """
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob(f"{ch:02d}_*.png"):      # 前の撮影の画像が混ざって、一覧と中身がずれないように
        old.unlink()
    write_env(out, browser)
    page = open_deck(browser, course_dir, ch)
    try:
        paths = []
        for i, slide in enumerate(page.evaluate("deckInfo()")):
            for step in range(slide["steps"] + 1):
                page.evaluate("([i, st]) => renderSlide(i, st)", [i, step])
                paths.append(shoot(page, out / still_name(ch, i, slide["id"], step)))
        assert_no_page_errors(page)
    finally:
        page.close()
    return paths


def diff(a: Path, b: Path) -> tuple[int, int, int, int] | None:
    """2枚の画像の違う範囲 (左, 上, 右, 下) を返す。1ピクセルも違わなければ None。

    右と下は範囲に含まない（Pillow の getbbox と同じ）。大きさが違うときは、大きい方に合わせた全体を返す。
    """
    with Image.open(a) as ia, Image.open(b) as ib:
        if ia.size != ib.size:
            return (0, 0, max(ia.width, ib.width), max(ia.height, ib.height))
        # RGB にそろえる：RGBA のままだと getbbox が透明度だけを見て、色の違いを見落とす
        return ImageChops.difference(ia.convert("RGB"), ib.convert("RGB")).getbbox()
