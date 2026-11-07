"""PDF を画像にして、画面（メインの舞台）と比べる道具（test_pdf.py など）。

ページ数と寸法が合っていても、背景が途中で切れたり下の文が欠けたりすることがある
（1280×720 の用紙に scale(2/3) で縮めた試作がそうだった）。なので、PDF のページを画像にして、
そのスライドの最後の段階の画面と比べる。PDF と画面は描き方が違う（文字の縁の滑らかさなど）ので、
完全な一致は求めず、「全体」「下の 1/3 の帯」「右の 1/3 の帯」ごとに、色の平均と、はっきり違う画素の割合を見る。
"""
import unicodedata
from pathlib import Path

import fitz                                    # PyMuPDF
import numpy as np
from PIL import Image

W, H = 1920, 1080
PDF_PT_W, PDF_PT_H = 1440, 810                 # 用紙 1920×1080 CSS px = 1440×810 pt

# 欠けの閾値。汎用の見本（proposal 9枚）で測った、正しい PDF の差より十分上で、欠け（下の 1/3 を白にしたもの）より十分下に置く。
MEAN_DIFF_MAX = 3.0                            # 領域の色の平均の差（RGB の絶対値の平均、0〜255）。背景が白に抜けると、淡い背景（#f5f7fa）でも約 7 になる
PIXEL_DIFF = 64                                # この値以上違う画素を「はっきり違う」と数える（RGB のうち最大の差）
TILE_PX = 120                                  # 小さい領域の比べ：1920×1080 を 120px の升（16×9）に分け、升ごとの色の平均の差を見る
TILE_DIFF_MAX = 18.0                           # 升の差の上限。正しい PDF の差より十分上、欠け（1 列の箱が丸ごと・箱の中の文・最後の箇条書き 1 行）より十分下に置く
                                               # （欠けを見つけられることは test_pdf.py の test_tile_check_finds_hidden_column などが確かめる）
PIXEL_RATIO_MAX = 0.02                         # 領域のうち、はっきり違う画素の割合の上限（文字の縁の違いでは 0.5% 未満）


def make_pdf(page, path) -> Path:
    """beforeprint を起こして印刷用の表示にし、PDF を書く。終わったら画面の表示に戻す。"""
    path = Path(path)
    page.evaluate("window.dispatchEvent(new Event('beforeprint'))")
    page.emulate_media(media="print")
    try:
        page.pdf(path=str(path), prefer_css_page_size=True, print_background=True)
    finally:
        page.emulate_media(media="screen")
    return path


def pdf_pages(path) -> list[Image.Image]:
    """PDF の各ページを 1920×1080 の RGB 画像にする。"""
    images = []
    with fitz.open(str(path)) as doc:
        for p in doc:
            zoom = W / p.rect.width            # 1440pt → 1920px
            pix = p.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            if img.size != (W, H):
                img = img.resize((W, H), Image.LANCZOS)
            images.append(img)
    return images


# プレイヤーの部品は撮らない（帯・知らせ・リンクの印の文字・壊れたリンクの枠は、PDF にない）
_HIDE_PLAYER_PARTS = """
.sp-controls, .sp-toast, .sp-linkmarks, .sp-jumpmsg { visibility: hidden !important; }
body:not(.render) #stage [data-sp-kind] { outline: none !important; }
"""


def _show_last_step(page, index):
    """メインの舞台を index 番目のスライドの最後の段階にする。"""
    info = page.evaluate("window.slideDeck.info.slides.map(s => ({id: s.id, steps: s.steps}))")
    slide = info[index]
    step = int(slide["steps"] or 0)
    page.evaluate("(h) => { location.hash = h; }", f"#{slide['id']}.{step}" if step else f"#{slide['id']}")
    page.wait_for_function(
        "([id, step]) => { const s = __sp.state(); return s.id === id && s.step === step; }", arg=[slide["id"], step]
    )


def stage_image(page, index) -> Image.Image:
    """メインの舞台を index 番目のスライドの最後の段階にして撮り、1920×1080 にする。"""
    _show_last_step(page, index)
    page.add_style_tag(content=_HIDE_PLAYER_PARTS)
    png = page.locator("#stage").screenshot()
    from io import BytesIO

    img = Image.open(BytesIO(png)).convert("RGB")
    if img.size != (W, H):
        img = img.resize((W, H), Image.LANCZOS)
    return img


# メインの舞台の、いま見えている文字（文字の節点ごと）。親が描かれていて、visibility が visible、不透明度が 0 でないもの
_VISIBLE_TEXT_JS = """() => {
  const out = [], root = document.getElementById('stage');
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    const el = n.parentElement;
    if (!el || /^(STYLE|SCRIPT|NOSCRIPT)$/i.test(el.tagName) || !n.data.trim()) continue;
    if (el.getClientRects().length === 0) continue;
    const cs = getComputedStyle(el);
    if (cs.visibility !== 'visible') continue;
    let hidden = false;
    for (let a = el; a && a !== root.parentElement; a = a.parentElement) if (parseFloat(getComputedStyle(a).opacity) === 0) hidden = true;
    if (!hidden) out.push(n.data);
  }
  return out;
}"""


# PDF の抽出で康熙部首・CJK 部首補助の字（⻑ など）が出ることがある。康熙部首（⾒ など）は NFKC で元の字になるが、
# CJK 部首補助の一部（U+2EC1 ⻁・U+2ED1 ⻑・U+2EE9 ⻩）は NFKC で変わらず、康熙部首の ⿊（U+2FCA）は NFKC で異体字の 黑 になる。ここで画面の字に直す（読み取りの不一致だけを直す。文字の欠けは直さない）
_RADICAL_FIX = {"\u2ec1": "\u864e", "\u2ed1": "\u9577", "\u2ee9": "\u9ec4", "\u9ed1": "\u9ed2"}     # ⻁ → 虎、⻑ → 長、⻩ → 黄、黑（⿊ の NFKC）→ 黒（全ページの照合で出たもの。新しい字が出たら、欠けとして報告されるので、ここへ足す）


def norm_text(text) -> str:
    """文字の比べ方：NFKC にして、空白を全部除き、大文字小文字を区別しない（PDF の抽出は改行・字間の空白が違う）。"""
    t = unicodedata.normalize("NFKC", text)
    return "".join(_RADICAL_FIX.get(c, c) for c in "".join(t.split())).casefold()


def missing_text(page, pdf_path) -> list[str]:
    """各スライドの最後の段階で画面に見えている文字が、PDF の同じページの文字に入っているかを調べる。欠けの一覧（空なら合格）。

    画面側の文字は、メインの舞台（印刷用の入れ物ではない）から読む。印刷の側だけが文を隠しても見つけるため。
    2 文字未満の断片は比べない（記号・1 文字の飾りは PDF で字体が変わる）。
    """
    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    problems = []
    for i, pdf_page in enumerate(reader.pages):
        _show_last_step(page, i)
        pdf_text = norm_text(pdf_page.extract_text())
        for chunk in page.evaluate(_VISIBLE_TEXT_JS):
            c = norm_text(chunk)
            if len(c) >= 2 and c not in pdf_text:
                problems.append(f"{i + 1}ページ目：文字が PDF にない「{chunk.strip()[:30]}」")
    return problems


def _region_problems(a: np.ndarray, b: np.ndarray, name: str) -> list[str]:
    diff = np.abs(a.astype(np.int16) - b.astype(np.int16))
    mean = float(diff.mean())
    ratio = float((diff.max(axis=2) >= PIXEL_DIFF).mean())
    problems = []
    if mean > MEAN_DIFF_MAX:
        problems.append(f"{name}：色の平均の差が大きい（{mean:.2f} > {MEAN_DIFF_MAX}）")
    if ratio > PIXEL_RATIO_MAX:
        problems.append(f"{name}：はっきり違う画素が多い（{ratio:.1%} > {PIXEL_RATIO_MAX:.0%}）")
    return problems


def _tile_problems(a: np.ndarray, b: np.ndarray) -> list[str]:
    diff = np.abs(a.astype(np.int16) - b.astype(np.int16)).mean(axis=2)
    tiles = diff.reshape(H // TILE_PX, TILE_PX, W // TILE_PX, TILE_PX).mean(axis=(1, 3))
    worst = float(tiles.max())
    if worst <= TILE_DIFF_MAX:
        return []
    row, col = np.unravel_index(int(tiles.argmax()), tiles.shape)
    n = int((tiles > TILE_DIFF_MAX).sum())
    return [f"小さい領域：升の差が大きい（最大 {worst:.1f} > {TILE_DIFF_MAX}、{n} 升。最大は {row + 1} 行 {col + 1} 列目）"]


def missing_parts(pdf_img, stage_img) -> list[str]:
    """PDF のページ画像に、画面と比べて欠けの疑いがあるところの一覧。空なら合格。

    見る領域：全体、下の 1/3 の帯、右の 1/3 の帯（背景が途中で切れる・下や右の文が欠ける、を見つけるため）と、
    小さい升（図・箱が 1 つ欠ける、を見つけるため。全体の平均では薄まる）。文字の欠けは missing_text で見る。
    """
    a = np.asarray(pdf_img.convert("RGB").resize((W, H)))
    b = np.asarray(stage_img.convert("RGB").resize((W, H)))
    regions = {
        "全体": (slice(0, H), slice(0, W)),
        "下の 1/3": (slice(H * 2 // 3, H), slice(0, W)),
        "右の 1/3": (slice(0, H), slice(W * 2 // 3, W)),
    }
    problems = []
    for name, (ys, xs) in regions.items():
        problems += _region_problems(a[ys, xs], b[ys, xs], name)
    problems += _tile_problems(a, b)
    return problems
