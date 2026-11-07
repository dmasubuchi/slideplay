// Editor のデッキの描画（CONTRACT.md §2.2〜2.5）。convert.py が作ったデッキの元（JSON）を、約束の形のデッキにする。
// 作りは examples/generic/render.js にならう：CSS は1回だけ入れて .sp-target の中だけに効かせ、段階は .hide（visibility: hidden）、
// 描いた中に id 属性を付けない、役目の印は data-sp-role。
// 使い方：window.slideDeck = EditorSlides.createDeck(data, { editing });
// editing が true のときだけ、文字の要素に data-src="行:始め-終わり" を付ける（画面から Markdown へ書き戻すための印）。
(() => {
  const DEFAULT_ACCENT = '#0b6bcb';

  const css = `
.sp-target { position: relative; width: 1920px; height: 1080px; overflow: hidden; background: #f5f7fa; color: #1d2733;
  font-family: "Hiragino Sans", "Hiragino Kaku Gothic ProN", "Meiryo", sans-serif; --accent: ${DEFAULT_ACCENT}; }
.sp-target, .sp-target * { box-sizing: border-box; }
.sp-target .hide { visibility: hidden; }
.sp-target .bigger { font-size: 1.3em; }
.sp-target mark { background: #fff1a8; color: inherit; padding: 0 .1em; border-radius: 4px; }
.sp-target .cover { position: absolute; inset: 0; padding: 0 180px; display: flex; flex-direction: column; justify-content: center;
  gap: 32px; background: #fff; border-left: 36px solid var(--accent); }
.sp-target .cover h1 { margin: 0; font-size: 92px; line-height: 1.3; font-weight: 800; }
.sp-target .cover p { margin: 0; font-size: 44px; line-height: 1.5; color: #5b6675; }
.sp-target .frame { position: absolute; inset: 0; padding: 72px 120px; display: flex; flex-direction: column; gap: 40px; }
.sp-target .frame h2 { margin: 12px 0 16px; padding-bottom: 24px; font-size: 68px; line-height: 1.25; font-weight: 800; border-bottom: 6px solid var(--accent); }
.sp-target .frame p { margin: 0; font-size: 44px; line-height: 1.6; }
.sp-target ul { margin: 0; padding: 0; list-style: none; display: flex; flex-direction: column; gap: 24px; }
.sp-target li { position: relative; padding-left: 48px; font-size: 48px; line-height: 1.5; }
.sp-target li::before { content: ""; position: absolute; left: 6px; top: 25px; width: 16px; height: 16px; border-radius: 50%; background: var(--accent); }
.sp-target li ul { margin-top: 16px; gap: 12px; }
.sp-target li li { font-size: 40px; color: #44505f; }
.sp-target li li::before { top: 21px; width: 12px; height: 12px; background: transparent; border: 3px solid var(--accent); }
.sp-target pre { margin: 0; padding: 24px 32px; background: #1d2733; color: #f5f7fa; border-radius: 12px; font-size: 32px; line-height: 1.5; white-space: pre-wrap; }
.sp-target .fig { margin: 0; }
.sp-target .fig img { display: block; max-width: 100%; max-height: 640px; }
.sp-target .missing { display: flex; align-items: center; justify-content: center; min-height: 240px; padding: 24px;
  background: #e3e8ef; color: #5b6675; font-size: 36px; border-radius: 12px; text-align: center; }
.sp-target .blocks { display: flex; flex-direction: column; gap: 32px; }
.sp-target .cols { display: flex; gap: 80px; align-items: flex-start; }
.sp-target .col { flex: 1; min-width: 0; padding: 40px 48px; background: #fff; border-radius: 16px; border-top: 10px solid var(--accent); }
.sp-target .col h3 { margin: 0 0 28px; font-size: 44px; }
.sp-target .col li { font-size: 42px; }
.sp-target .figtext { display: flex; gap: 80px; align-items: center; }
.sp-target .figtext > .blocks { flex: 1; min-width: 0; }
.sp-target .figtext > .fig { flex: 1; min-width: 0; }
.sp-target .frame .big { margin: auto 0; font-size: 84px; line-height: 1.4; font-weight: 800; text-align: center; }
.sp-target .html { position: absolute; inset: 0; }
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
    if (text != null) e.textContent = text;
    return e;
  };
  const mark = (e, attrs) => { for (const [k, v] of Object.entries(attrs)) e.setAttribute('data-sp-' + k, v); return e; };

  // 飾り：**…** を <b>、==…== を <mark>、++…++ を大きく（.bigger）にする。中身はもう一度かける（入れ子）。
  // 1つの交互にして、いちばん近くで閉じる。それ以外はすべて文字として入れる（HTML として解釈しない）
  const INLINE_RE = /\*\*(.+?)\*\*|==(.+?)==|\+\+(.+?)\+\+/g;
  function inline(parent, text) {
    const re = new RegExp(INLINE_RE.source, 'g');
    let last = 0, m;
    while ((m = re.exec(text))) {
      if (m.index > last) parent.append(text.slice(last, m.index));
      const e = m[1] != null ? el('b') : m[2] != null ? el('mark') : el('span', 'bigger');
      inline(e, m[1] != null ? m[1] : m[2] != null ? m[2] : m[3]);
      parent.append(e);
      last = re.lastIndex;
    }
    if (last < text.length) parent.append(text.slice(last));
  }
  const appendInline = inline;

  function createDeck(data, opts) {
    const editing = !!(opts && opts.editing);
    const slides = data.slides;
    const info = { id: data.info.id, title: data.info.title };
    if (data.info.color) info.color = data.info.color;
    info.slides = slides.map(s => ({ id: s.id, title: s.title, steps: s.steps, notes: s.notes || '' }));

    // 編集中だけ、書き戻しの印を付ける
    const withSrc = (e, src) => { if (editing && src) e.setAttribute('data-src', `${src[0]}:${src[1]}-${src[2]}`); return e; };
    const textEl = (tag, className, text, src) => {
      const e = el(tag, className);
      appendInline(e, text);
      return withSrc(e, src);
    };

    function listEl(items, step) {
      const ul = el('ul');
      for (const it of items) {
        const li = mark(el('li', it.step > step ? 'hide' : ''), { role: 'item' });
        li.append(textEl('span', '', it.text, it.src));        // 文字は span に包む（入れ子の ul を含めないため）
        if (it.sub && it.sub.length) {
          const sub = el('ul');
          for (const s of it.sub) {
            const sli = mark(el('li'), { role: 'item' });      // 下の項目の隠れ方は親の li から引き継ぐ
            sli.append(textEl('span', '', s.text, s.src));
            sub.append(sli);
          }
          li.append(sub);
        }
        ul.append(li);
      }
      return ul;
    }

    function pEl(b, className) {
      const p = el('p', className);
      b.lines.forEach((ln, i) => {
        if (i > 0) p.append(document.createElement('br'));
        if (editing) p.append(textEl('span', '', ln.text, ln.src));
        else appendInline(p, ln.text);
      });
      return p;
    }

    function imgEl(b) {
      if (b.missing) return el('div', 'missing', `${b.path} がありません`);
      const fig = mark(el('figure', 'fig'), { role: 'figure' });
      const img = document.createElement('img');
      img.setAttribute('src', b.path + (b.v != null ? `?v=${b.v}` : ''));
      img.setAttribute('alt', b.alt || '');
      fig.append(img);
      return fig;
    }

    function blockEl(b, step) {
      if (b.kind === 'list') return listEl(b.items, step);
      if (b.kind === 'p') return pEl(b);
      if (b.kind === 'pre') return el('pre', '', b.text);
      if (b.kind === 'img') return imgEl(b);
      if (b.kind === 'h3') return textEl('h3', '', b.text, b.src);
      return el('div');
    }

    const blocksEl = (blocks, step) => {
      const box = el('div', 'blocks');
      for (const b of blocks) box.append(blockEl(b, step));
      return box;
    };

    function headEl(s, tag) {
      return s.head ? mark(textEl(tag, '', s.head.text, s.head.src), { role: 'title' }) : null;
    }

    // 二段：h3 ごとに列を分ける。h3 がなければ箇条書きの項目を半分ずつ
    function columns(s, step) {
      const blocks = s.blocks;
      const cols = el('div', 'cols');
      const before = [];
      if (blocks.some(b => b.kind === 'h3')) {
        let cur = null;
        for (const b of blocks) {
          if (b.kind === 'h3') {
            cur = el('div', 'col');
            cur.append(blockEl(b, step));
            cols.append(cur);
          } else if (cur) {
            cur.append(blockEl(b, step));
          } else {
            before.push(b);
          }
        }
      } else {
        const items = [];
        for (const b of blocks) (b.kind === 'list' ? items.push(...b.items) : before.push(b));
        const half = Math.ceil(items.length / 2);
        for (const part of [items.slice(0, half), items.slice(half)]) {
          const col = el('div', 'col');
          col.append(listEl(part, step));
          cols.append(col);
        }
      }
      return { before, cols };
    }

    function build(s, step) {
      if (s.html != null) {
        const box = el('div', 'html');
        box.innerHTML = s.html;                                // html の指示は、部品をそのまま入れる
        return box;
      }
      if (s.type === '表紙') {
        const cover = el('div', 'cover');
        const h = headEl(s, 'h1');
        if (h) cover.append(h);
        for (const b of s.blocks) cover.append(blockEl(b, step));
        return cover;
      }
      const frame = el('div', 'frame');
      const h = headEl(s, 'h2');
      if (h) frame.append(h);
      if (s.type === '二段') {
        const { before, cols } = columns(s, step);
        if (before.length) frame.append(blocksEl(before, step));
        frame.append(cols);
      } else if (s.type === '図と文') {
        const k = s.blocks.findIndex(b => b.kind === 'img');
        const row = el('div', 'figtext');
        row.append(blocksEl(s.blocks.filter((_, i) => i !== k), step));
        if (k >= 0) row.append(imgEl(s.blocks[k]));
        frame.append(row);
      } else if (s.type === '強調') {
        const k = s.blocks.findIndex(b => b.kind === 'p');
        if (k >= 0) {
          const big = pEl(s.blocks[k], 'big');
          mark(big, { role: 'emphasis' });
          frame.append(big);
        }
        const rest = s.blocks.filter((_, i) => i !== k);
        if (rest.length) frame.append(blocksEl(rest, step));
      } else {
        frame.append(blocksEl(s.blocks, step));
      }
      return frame;
    }

    // 編集中だけ：描いた文（data-src の値）から元の文・ページを引く。keys は Markdown の順（ページ→見出し→ブロック→項目→下の項目→段落の行）
    let editor;
    if (editing) {
      const texts = new Map(), owner = new Map(), order = [];
      const add = (src, text, id) => {
        if (!src) return;
        const key = `${src[0]}:${src[1]}-${src[2]}`;
        texts.set(key, text); owner.set(key, id); order.push(key);
      };
      for (const s of slides) {
        if (s.head) add(s.head.src, s.head.text, s.id);
        for (const b of s.blocks || []) {
          if (b.kind === 'h3') add(b.src, b.text, s.id);
          else if (b.kind === 'list') for (const it of b.items) { add(it.src, it.text, s.id); for (const sub of it.sub || []) add(sub.src, sub.text, s.id); }
          else if (b.kind === 'p') for (const ln of b.lines) add(ln.src, ln.text, s.id);
        }
      }
      editor = { textAt: k => (texts.has(k) ? texts.get(k) : null), slideAt: k => (owner.has(k) ? owner.get(k) : null), keys: () => order.slice() };
    }

    function render(ref, step, target) {
      const k = typeof ref === 'string' ? slides.findIndex(s => s.id === ref) : ref;
      if (!slides[k]) throw new Error(typeof ref === 'string' ? `スライド ID「${ref}」は、このデッキにありません` : `スライドの位置 ${ref} は、このデッキにありません`);
      target.style.setProperty('--accent', info.color || DEFAULT_ACCENT);
      target.replaceChildren(build(slides[k], step));
      // 編集中だけ、ためている直しの印を重ねる（EditorPending は呼ぶときに探す。失敗しても描画は止めない）
      if (editing && window.EditorPending && typeof window.EditorPending.decorate === 'function') {
        try { window.EditorPending.decorate(target, slides[k].id); } catch (e) { console.warn('EditorPending.decorate に失敗しました', e); }
      }
    }

    const deck = { contract: 1, info, render };
    if (editor) deck.editor = editor;
    return deck;
  }

  window.EditorSlides = { createDeck, inline };
})();
