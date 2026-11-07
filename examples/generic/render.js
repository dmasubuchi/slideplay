// 汎用の見本の描画（CONTRACT.md §2.2〜2.5）。商談の提案書のような、特定の題材に結びつかない中身を想定した小さな実装。
// 部品は title（表紙）・bullets（箇条書き）・two（2列）と、points（カード）・stat（大きな数字）・bars（棒）・flow（流れ）。
// 段階は、points・stat・bars は項目ごとに step、bullets・two は at で決める（flow は段階なし）。SVG は使わず、描いた中に id 属性を付けない。
// 動きの層のための役目の印（data-sp-role・data-sp-hover・data-sp-group・data-sp-key）を付ける。属性だけなので見た目は変わらない
// 使い方：window.slideDeck = GenericSlides.createDeck({ id, title, label, home, color, sections, slides });
(() => {
  const DEFAULT_ACCENT = '#0b6bcb';

  // 中身の CSS は .sp-target の中だけに効くように書く（§2.5）。舞台の見た目は .sp-target に付ける
  const css = `
.sp-target { position: relative; width: 1920px; height: 1080px; overflow: hidden; background: #f5f7fa; color: #1d2733;
  font-family: "Hiragino Sans", "Hiragino Kaku Gothic ProN", "Meiryo", sans-serif; --accent: ${DEFAULT_ACCENT}; }
.sp-target, .sp-target * { box-sizing: border-box; }
.sp-target .hide { visibility: hidden; }
.sp-target .cover { position: absolute; inset: 0; padding: 0 180px; display: flex; flex-direction: column; justify-content: center;
  gap: 32px; background: #fff; border-left: 36px solid var(--accent); }
.sp-target .cover h1 { margin: 0; font-size: 92px; line-height: 1.3; font-weight: 800; }
.sp-target .cover .sub { margin: 0; font-size: 44px; line-height: 1.5; color: #5b6675; }
.sp-target .frame { position: absolute; inset: 0; padding: 72px 120px; }
.sp-target .kicker { height: 40px; font-size: 32px; font-weight: 700; color: var(--accent); }
.sp-target .frame h2 { margin: 12px 0 56px; padding-bottom: 24px; font-size: 68px; line-height: 1.25; font-weight: 800; border-bottom: 6px solid var(--accent); }
.sp-target ul { margin: 0; padding: 0; list-style: none; display: flex; flex-direction: column; gap: 32px; }
.sp-target li { position: relative; padding-left: 48px; font-size: 48px; line-height: 1.5; }
.sp-target li::before { content: ""; position: absolute; left: 6px; top: 25px; width: 16px; height: 16px; border-radius: 50%; background: var(--accent); }
.sp-target .cols { display: flex; gap: 80px; }
.sp-target .col { flex: 1; padding: 40px 48px; background: #fff; border-radius: 16px; border-top: 10px solid var(--accent); }
.sp-target .col h3 { margin: 0 0 28px; font-size: 44px; }
.sp-target .col li { font-size: 42px; }
.sp-target .lnk { color: var(--accent); font-weight: 700; }
.sp-target .pts { display: flex; gap: 40px; }
.sp-target .pt { flex: 1; padding: 40px 44px; background: #fff; border-radius: 16px; border-top: 10px solid var(--accent); }
.sp-target .pt-t { font-size: 44px; line-height: 1.4; font-weight: 700; }
.sp-target .pt-s { margin-top: 20px; font-size: 34px; line-height: 1.5; color: #5b6675; }
.sp-target .stats { display: flex; gap: 48px; }
.sp-target .st { flex: 1; min-width: 0; padding: 48px; background: #fff; border-radius: 16px; text-align: center; overflow-wrap: anywhere; }
.sp-target .st-v { font-size: 120px; line-height: 1.1; font-weight: 800; color: var(--accent); }
.sp-target .stats.n3 .st-v { font-size: 96px; }
.sp-target .stats.n4 { gap: 32px; }
.sp-target .stats.n4 .st { padding: 40px 28px; }
.sp-target .stats.n4 .st-v { font-size: 76px; }
.sp-target .st-l { margin-top: 16px; font-size: 40px; font-weight: 700; }
.sp-target .st-s { margin-top: 12px; font-size: 30px; color: #5b6675; }
.sp-target .bars { display: flex; flex-direction: column; gap: 36px; }
.sp-target .bar-row { display: grid; grid-template-columns: 360px 1fr 180px; gap: 32px; align-items: center; }
.sp-target .bar-l { font-size: 40px; font-weight: 700; }
.sp-target .bar-track { position: relative; height: 64px; background: #e3e8ef; border-radius: 10px; }
.sp-target .bar-fill { position: absolute; left: 0; top: 0; bottom: 0; background: var(--accent); border-radius: 10px; }
.sp-target .bar-d { font-size: 44px; font-weight: 800; color: var(--accent); }
.sp-target .flow { display: flex; flex-direction: column; gap: 40px; }
.sp-target .flow-row { display: flex; gap: 20px; align-items: stretch; }
.sp-target .fn { flex: 1; padding: 36px 28px; background: #fff; border: 4px solid var(--accent); border-radius: 16px; text-align: center; }
.sp-target .fn-t { font-size: 42px; font-weight: 800; }
.sp-target .fn-s { margin-top: 12px; font-size: 30px; line-height: 1.4; color: #5b6675; }
.sp-target .fa { align-self: center; display: flex; flex-direction: column; align-items: center; font-size: 56px; color: var(--accent); }
.sp-target .fa-t { font-size: 24px; color: #5b6675; }
/* ?render（動画づくり）のとき、舞台を左上に縮小せずに置く（§3.1） */
body.render { margin: 0; }
.render #stage { left: 0; top: 0; transform: none !important; }
`;
  const style = document.createElement('style');
  style.textContent = css;
  document.head.appendChild(style);

  const el = (tag, className, text) => {
    const e = document.createElement(tag);
    if (className) e.className = className;
    if (text != null) e.textContent = text;       // 文字は textContent で入れる（HTML として解釈しない。§2.3）
    return e;
  };

  // 項目は 文字列 か { text, at, link }。at はその項目が現れる段階（既定 0）。link は data-link の番号を直接指す（文字全体がリンクになる）
  const normalize = item => (typeof item === 'string' ? { text: item, at: 0 } : { at: 0, ...item });
  // points・stat・bars の項目が現れる段階（step。既定 0）
  const stepOf = item => (item && typeof item === 'object' && Number.isInteger(item.step) && item.step > 0 ? item.step : 0);

  // 役目の印を付ける（動きの層が読む。CONTRACT.md §2.6）
  const mark = (e, attrs) => { for (const [k, v] of Object.entries(attrs)) e.setAttribute('data-sp-' + k, v); return e; };

  // 文字の中の [[ラベル]] を、links の同じ label のリンクの印（data-link）にする。ラベルが links になければ、そのまま文字で出す
  function appendText(parent, text, links) {
    text.split(/(\[\[.+?\]\])/).forEach(part => {
      const m = /^\[\[(.+?)\]\]$/.exec(part);
      const n = m ? links.findIndex(l => l.label === m[1]) : -1;
      if (n < 0) { if (part) parent.append(part); return; }
      const span = el('span', 'lnk', m[1]);
      span.setAttribute('data-link', String(n));
      parent.append(span);
    });
  }

  function bulletList(items, links, step) {
    const ul = el('ul');
    items.map(normalize).forEach(item => {
      const li = mark(el('li', item.at > step ? 'hide' : ''), { role: 'item' });
      if (item.link != null) {
        const span = el('span', 'lnk', item.text);
        span.setAttribute('data-link', String(item.link));
        li.append(span);
      } else {
        appendText(li, item.text, links);
      }
      ul.append(li);
    });
    return ul;
  }

  // 部品：points（カード）・stat（大きな数字）・bars（棒）・flow（流れ）。s：スライドの定義、links：そのスライドのリンク
  function points(s, links, step) {
    const box = mark(el('div', 'pts'), { group: '' });
    for (const item of s.items || []) {
      const card = mark(el('div', 'pt' + (stepOf(item) > step ? ' hide' : '')), { role: 'card', hover: '' });
      const t = el('div', 'pt-t');
      appendText(t, item.text || '', links);
      card.append(t);
      if (item.sub) card.append(el('div', 'pt-s', item.sub));
      box.append(card);
    }
    return box;
  }

  function stats(s, step) {
    const n = (s.items || []).length;
    const box = mark(el('div', 'stats' + (n >= 3 ? ' n' + Math.min(n, 4) : '')), { group: '' });   // 3つ・4つのときは数字を小さくして、舞台に収める
    for (const item of s.items || []) {
      const one = mark(el('div', 'st' + (stepOf(item) > step ? ' hide' : '')), { role: 'stat', hover: '' });
      one.append(mark(el('div', 'st-v', item.value), { role: 'count' }), el('div', 'st-l', item.label));
      if (item.sub) one.append(el('div', 'st-s', item.sub));
      box.append(one);
    }
    return box;
  }

  // 塗りの幅は value / max（0 から。目分量で描かない）。数でない値・max が 0 以下なら 0
  function bars(s, step) {
    const box = mark(el('div', 'bars'), { group: '' });
    const max = Number(s.max);
    (s.items || []).forEach((item, i) => {
      const key = 'b' + i;
      const row = mark(el('div', 'bar-row' + (stepOf(item) > step ? ' hide' : '')), { hover: '' });
      const v = Number(item.value);
      const ratio = Number.isFinite(v) && Number.isFinite(max) && max > 0 ? Math.min(Math.max(v / max, 0), 1) : 0;
      const track = el('div', 'bar-track');
      const fill = mark(el('div', 'bar-fill'), { role: 'bar', key });
      fill.style.width = (ratio * 100) + '%';
      track.append(fill);
      row.append(mark(el('div', 'bar-l', item.label), { key }), track, el('div', 'bar-d', item.display));
      box.append(row);
    });
    return box;
  }

  function flow(s) {
    const box = el('div', 'flow');
    for (const r of s.rows || []) {
      const row = mark(el('div', 'flow-row'), { group: '' });
      (r.nodes || []).forEach((n, i) => {
        if (i > 0) {
          const a = mark(el('div', 'fa'), { role: 'arrow' });
          const label = (r.arrows || [])[i - 1];
          if (label && label.text) a.append(el('div', 'fa-t', label.text));
          a.append('→');
          row.append(a);
        }
        const node = mark(el('div', 'fn'), { role: 'node', hover: '' });
        node.append(el('div', 'fn-t', n.t));
        if (n.s) node.append(el('div', 'fn-s', n.s));
        row.append(node);
      });
      box.append(row);
    }
    return box;
  }

  const ITEM_STEP_TYPES = ['points', 'stat', 'bars'];

  function slideSteps(s) {
    if (ITEM_STEP_TYPES.includes(s.type)) return Math.max(0, ...(s.items || []).map(stepOf));
    const items = [...(s.items || []), ...(s.left ? s.left.items : []), ...(s.right ? s.right.items : [])];
    return Math.max(0, ...items.map(i => normalize(i).at));
  }

  function createDeck(def) {
    const slides = def.slides;
    const sectionTitle = id => (def.sections || []).find(x => x.id === id)?.title || '';
    const info = { id: def.id, title: def.title };
    for (const key of ['label', 'home', 'color', 'sections', 'motion']) if (def[key] != null) info[key] = def[key];
    info.slides = slides.map(s => ({
      id: s.id, title: s.title, section: s.section, steps: slideSteps(s),
      notes: s.notes || '', minutes: s.minutes, links: s.links || [],
    }));

    function build(s, step) {
      if (s.type === 'title') {
        const cover = el('div', 'cover');
        cover.append(mark(el('h1', '', s.title), { role: 'title' }), mark(el('p', 'sub', s.subtitle), { role: 'sub' }));
        return cover;
      }
      if (!['bullets', 'two', ...ITEM_STEP_TYPES, 'flow'].includes(s.type)) throw new Error(`未知のスライドの種類「${s.type}」です`);
      const frame = el('div', 'frame');
      frame.append(el('div', 'kicker', sectionTitle(s.section)), mark(el('h2', '', s.title), { role: 'title' }));
      const links = s.links || [];
      if (s.type === 'bullets') {
        frame.append(bulletList(s.items, links, step));
      } else if (s.type === 'points') {
        frame.append(points(s, links, step));
      } else if (s.type === 'stat') {
        frame.append(stats(s, step));
      } else if (s.type === 'bars') {
        frame.append(bars(s, step));
      } else if (s.type === 'flow') {
        frame.append(flow(s));
      } else {
        const cols = el('div', 'cols');
        [s.left, s.right].forEach(c => {
          const col = el('div', 'col');
          col.append(el('h3', '', c.heading), bulletList(c.items, links, step));
          cols.append(col);
        });
        frame.append(cols);
      }
      return frame;
    }

    function render(ref, step, target) {
      const k = typeof ref === 'string' ? slides.findIndex(s => s.id === ref) : ref;
      if (!slides[k]) throw new Error(typeof ref === 'string' ? `スライド ID「${ref}」は、このデッキにありません` : `スライドの位置 ${ref} は、このデッキにありません`);
      target.style.setProperty('--accent', def.color || DEFAULT_ACCENT);
      target.replaceChildren(build(slides[k], step));
    }

    return { contract: 1, info, render };
  }

  window.GenericSlides = { createDeck };
})();
