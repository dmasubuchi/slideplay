"""画面の大きさの試験（test_layout.py、test_webkit_reference.py）が共有する、はみ出しの検査。

検査するのは次の3つ（問題があれば文字列の一覧で返す。なければ空）：
- ページ全体：document.scrollingElement.scrollHeight <= innerHeight かつ scrollWidth <= innerWidth、スクロール位置が 0
- 画面に出ている sp- の部品と舞台（#stage）：getBoundingClientRect が viewport の中（0.5px の誤差は許す）。
  スクロールできる入れ物（overflow: auto・scroll）や切り取る入れ物（overflow: hidden）の中にある部品は、その入れ物自身が
  viewport の中にあれば、入れ物の中で見えるので数えない（縮小一覧のサムネイル、ノートや操作の一覧の中身、目次のカードの中身）。
  visibility: hidden の部品（自動で隠した操作ボタン）と、display: none の部品は数えない
- 切り取る入れ物（sp- の overflow: hidden。サムネイルの枠と、省略記号で切る文字を除く）の中身が切れていない：
  scrollHeight <= clientHeight + 1、幅も同じ
"""

CHECK_JS = """() => {
  const iw = innerWidth, ih = innerHeight, TOL = 0.5, problems = [];
  const se = document.scrollingElement;
  if (se.scrollHeight > ih) problems.push(`縦にスクロールできる: scrollHeight ${se.scrollHeight} > innerHeight ${ih}`);
  if (se.scrollWidth > iw) problems.push(`横にスクロールできる: scrollWidth ${se.scrollWidth} > innerWidth ${iw}`);
  if (scrollX !== 0 || scrollY !== 0) problems.push(`スクロール位置が 0 でない: ${scrollX}, ${scrollY}`);

  const name = e => e.tagName.toLowerCase() + (e.id ? '#' + e.id : '') + Array.from(e.classList).map(c => '.' + c).join('');
  const isPart = e => e.id === 'stage' || Array.from(e.classList).some(c => c.startsWith('sp-'));
  const clips = e => { const s = getComputedStyle(e); return s.overflowX !== 'visible' || s.overflowY !== 'visible'; };
  const insideClip = e => { for (let a = e.parentElement; a && a !== document.body && a !== document.documentElement; a = a.parentElement) if (clips(a)) return true; return false; };
  const shown = e => e.getClientRects().length > 0 && getComputedStyle(e).visibility === 'visible';
  const outside = r => r.left < -TOL || r.top < -TOL || r.right > iw + TOL || r.bottom > ih + TOL;

  for (const e of document.querySelectorAll('body *')) {
    if (!isPart(e) || !shown(e) || insideClip(e)) continue;
    const r = e.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) continue;                 // 大きさのない層（.sp-linkmarks など）
    if (outside(r)) problems.push(`画面の外にはみ出す: ${name(e)} [${r.left.toFixed(1)}, ${r.top.toFixed(1)}, ${r.right.toFixed(1)}, ${r.bottom.toFixed(1)}] (viewport ${iw}x${ih})`);
  }
  for (const e of document.querySelectorAll('body *')) {
    if (!isPart(e) || !shown(e) || e.classList.contains('sp-thumb-frame')) continue;
    const s = getComputedStyle(e);
    if ((s.overflowX !== 'hidden' && s.overflowY !== 'hidden') || s.textOverflow === 'ellipsis') continue;     // 省略記号で切る文字（サムネイルの題）は、切れているのが仕様
    if (e.scrollHeight > e.clientHeight + 1 || e.scrollWidth > e.clientWidth + 1)
      problems.push(`中身が切れている: ${name(e)} (scroll ${e.scrollWidth}x${e.scrollHeight}, client ${e.clientWidth}x${e.clientHeight})`);
  }
  return problems;
}"""


def layout_problems(page) -> list[str]:
    """page の今の表示のはみ出しの一覧（なければ空）。"""
    return page.evaluate(CHECK_JS)
