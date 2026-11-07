// Editor：舞台の文字をクリックして、その場で直す入力欄。確定した直しは EditorPending（ためる）へ渡す。
// 開く・確定・やめるはどれも、押した（打った）同じ処理の中で行う（await・setTimeout を挟まない）。
// 入力欄の中身は serialize で Markdown の文（**…**・==…==・++…++）に戻す。位置は計算せず、key（data-src）はそのまま使う。
// 使い方：window.EditorInline = { isOpen, confirm, cancel, serialize }（live.js・pending.js が毎回探して呼ぶ）
(function () {
  "use strict";
  const TOOLS = [['bold', 'B 太く'], ['bigger', 'A＋ 大きく']];
  const BOLD = 'b, strong', BIGGER = 'span.bigger';
  let cur = null;       // 開いている入力欄 { el, key, slide, before, saved, label, tools, observer, on }

  const stage = () => document.getElementById('stage');
  const inline = (el, text) => window.EditorSlides.inline(el, text);
  const plain = text => { const s = document.createElement('span'); inline(s, text); return s.textContent; };

  // ---- 入力欄の中身 → Markdown の文 ----
  function serialize(el) {
    let out = '';
    for (const n of el.childNodes) {
      if (n.nodeType === 3) { out += n.data.replace(/ /g, ' '); continue; }
      if (n.nodeType !== 1 || n.tagName === 'BR' || n.classList.contains('sp-ed-before')) continue;
      const inner = serialize(n);
      const mark = n.tagName === 'B' || n.tagName === 'STRONG' ? '**' : n.tagName === 'MARK' ? '==' : n.matches(BIGGER) ? '++' : '';
      out += inner && mark ? mark + inner + mark : inner;
    }
    return out;
  }

  // ---- 太く・大きく（選んだ範囲を包む。範囲がすべて中なら、その飾りを外す）----
  function selectedTexts(el) {
    const sel = getSelection();
    if (!sel.rangeCount) return null;
    const r = sel.getRangeAt(0);
    if (r.collapsed || !el.contains(r.commonAncestorContainer)) return null;
    // 範囲の両端が文字の途中なら、そこで文字を割って、範囲を文字の境目に合わせる
    const ec = r.endContainer, eo = r.endOffset, sc = r.startContainer, so = r.startOffset;
    if (ec.nodeType === 3 && eo > 0 && eo < ec.length) ec.splitText(eo);
    if (sc.nodeType === 3 && so > 0 && so < sc.length) {
      const right = sc.splitText(so);
      if (sc === ec) r.setEnd(right, eo - so);
      r.setStart(right, 0);
    }
    const out = [], w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    for (let n; (n = w.nextNode());) {
      if (n.length && !n.parentElement.closest('.sp-ed-before') && r.comparePoint(n, 0) === 0 && r.comparePoint(n, n.length) === 0) out.push(n);
    }
    return out.length ? out : null;
  }
  const inside = (n, sel, root) => { const a = n.parentElement.closest(sel); return a && root.contains(a) && a !== root ? a : null; };
  // 飾りの要素 a のうち、選んだ文字（first〜last）だけを外す：前後は同じ飾りのまま残す
  function unwrapPart(a, first, last) {
    const side = (setup, before) => {
      const r = document.createRange();
      setup(r);
      const frag = r.extractContents();
      if (!frag.textContent) return;
      const copy = a.cloneNode(false);
      copy.append(frag);
      if (before) a.before(copy); else a.after(copy);
    };
    side(r => { r.setStartAfter(last); r.setEnd(a, a.childNodes.length); }, false);
    side(r => { r.setStart(a, 0); r.setEndBefore(first); }, true);
    a.replaceWith(...a.childNodes);
  }
  function mergeAdjacent(root, sel) {     // 隣り合う同じ飾りを1つにする（**a****b** を作らない）
    for (const a of root.querySelectorAll(sel)) {
      const p = a.previousSibling;
      if (p && p.nodeType === 1 && p.matches(sel) && p.tagName === a.tagName) { p.append(...a.childNodes); a.remove(); }
    }
  }
  function decorate(kind) {
    if (!cur) return;
    const el = cur.el, sel = kind === 'bold' ? BOLD : BIGGER;
    const texts = selectedTexts(el);
    if (!texts) return;
    if (texts.every(n => inside(n, sel, el))) {
      for (const a of new Set(texts.map(n => inside(n, sel, el)))) {
        const mine = texts.filter(n => a.contains(n));
        unwrapPart(a, mine[0], mine[mine.length - 1]);
      }
      for (const e of [...el.querySelectorAll('b, strong, mark, span.bigger')]) if (!e.textContent) e.remove();   // 空になった飾りは残さない
    } else {
      for (const n of texts) {
        if (inside(n, sel, el)) continue;
        const w = document.createElement(kind === 'bold' ? 'b' : 'span');
        if (kind === 'bigger') w.className = 'bigger';
        n.replaceWith(w);
        w.append(n);
      }
      mergeAdjacent(el, kind === 'bold' ? 'b' : 'span.bigger');
    }
    const r = document.createRange();
    r.setStart(texts[0], 0);
    r.setEnd(texts[texts.length - 1], texts[texts.length - 1].length);
    const s = getSelection();
    s.removeAllRanges();
    s.addRange(r);
    placeTools();
  }

  // ---- 開く・閉じる ----
  const visible = () => [...stage().querySelectorAll('[data-src]')].filter(e => !e.closest('.hide'));

  // 前の文の札：文字は要素の 0.6 倍（兄弟なので em が効かない）。要素の真上に置き、上に余白がなければ下に置く
  function placeLabel(el, label) {
    label.style.fontSize = `${parseFloat(getComputedStyle(el).fontSize) * 0.6}px`;
    label.style.left = `${el.offsetLeft}px`;
    label.style.top = `${el.offsetTop}px`;
    label.style.transform = 'translateY(-100%)';
    const s = stage();
    if (s && label.getBoundingClientRect().top < s.getBoundingClientRect().top) {
      label.style.top = `${el.offsetTop + el.offsetHeight}px`;
      label.style.transform = 'none';
    }
  }

  // 道具は要素の右上（札と重ならない所）に置く。重なる・上に出せないときは右下
  function placeTools() {
    if (!cur) return;
    const r = cur.el.getBoundingClientRect(), lr = cur.label.isConnected ? cur.label.getBoundingClientRect() : null;
    const h = cur.tools.offsetHeight, w = cur.tools.offsetWidth;
    const left = Math.max(4, Math.min(r.right - w, innerWidth - w - 4));
    const lbelow = !!lr && lr.top >= r.bottom - 1;
    const clear = !lr || left + w <= lr.left || left >= lr.right;         // 札と横に重ならない
    let top = (clear || lbelow ? r.top : lr.top) - h - 6;
    if (top < 4 || lbelow) top = (lbelow ? lr.bottom : r.bottom) + 6;      // 上に出せないときは下に
    cur.tools.style.top = `${top}px`;
    cur.tools.style.left = `${left}px`;
  }

  function makeTools() {
    const box = document.createElement('div');
    box.className = 'sp-ed-tools';
    for (const [kind, text] of TOOLS) {
      const b = document.createElement('button');
      b.type = 'button';
      b.textContent = text;
      b.addEventListener('mousedown', e => e.preventDefault());      // 押しても焦点（と選んだ範囲）を動かさない
      b.addEventListener('click', e => { e.preventDefault(); decorate(kind); });
      box.append(b);
    }
    return box;
  }

  // 入力欄を閉じる（飾りの道具・札・監視・聞き手を外す）。中身は触らない
  function teardown() {
    const c = cur;
    cur = null;
    c.observer.disconnect();
    for (const [target, type, fn] of c.on) target.removeEventListener(type, fn);
    c.tools.remove();
    c.label.remove();
    c.el.removeAttribute('contenteditable');
    c.el.removeAttribute('spellcheck');
    c.el.classList.remove('sp-ed-open');
    return c;
  }

  function confirm() {
    if (!cur) return;
    const c = teardown();
    const after = serialize(c.el);
    if (!after.trim()) {                                  // 空にはできない：元の姿に戻して知らせる
      if (c.el.isConnected) c.el.replaceChildren(...c.saved);
      if (window.EditorPending && window.EditorPending.toast) window.EditorPending.toast('空にはできません。消すときはエディターで消してください');
      return;
    }
    const pend = window.EditorPending && window.EditorPending.get(c.key);
    const before = pend ? pend.before : c.before;
    if (after === before && !pend && c.el.isConnected) c.el.replaceChildren(...c.saved);   // 変わらなかった：作りを元どおりに
    if (window.EditorPending) window.EditorPending.add({ key: c.key, slide: c.slide, before, after });
  }

  function cancel() {
    if (!cur) return;
    const c = teardown();
    if (c.el.isConnected) c.el.replaceChildren(...c.saved);
  }

  function open(el, point) {
    if (cur) { if (cur.el === el) return; confirm(); }
    const ed = window.slideDeck && window.slideDeck.editor;
    const key = el.getAttribute('data-src');
    if (!ed || ed.textAt(key) == null) return;
    const pend = window.EditorPending && window.EditorPending.get(key);
    const saved = [...el.childNodes].map(n => n.cloneNode(true));                  // やめたとき戻す姿（ためた直しの札つき）
    el.querySelectorAll(':scope > .sp-ed-before').forEach(n => n.remove());       // ためた直しの前の文は、入力欄では取り換える
    const before = pend ? pend.before : ed.textAt(key);
    const label = document.createElement('span');
    label.className = 'sp-ed-before';
    label.setAttribute('contenteditable', 'false');
    label.textContent = plain(before);
    label.classList.add('out');
    el.before(label);                                      // 入力欄の外（兄弟）に置く：中に置くとカーソルの置き場がなくなる
    placeLabel(el, label);
    el.setAttribute('contenteditable', 'true');
    el.setAttribute('spellcheck', 'false');
    el.classList.add('sp-ed-open');
    const tools = makeTools();
    document.body.append(tools);
    const on = [];
    const listen = (type, fn, target) => { (target || el).addEventListener(type, fn); on.push([target || el, type, fn]); };
    const observer = new MutationObserver(() => { if (cur && cur.el === el && !el.isConnected) confirm(); });   // 舞台が描き直されて外れた
    observer.observe(stage(), { childList: true, subtree: true });
    cur = { el, key, slide: ed.slideAt(key), before, saved, label, tools, observer, on };

    listen('keydown', onKey);
    listen('paste', onPaste);
    listen('drop', e => e.preventDefault());
    listen('blur', () => { if (cur && cur.el === el) confirm(); });
    listen('input', placeTools);
    listen('resize', placeTools, window);

    el.focus();
    const sel = getSelection();
    let range = null;
    if (point && document.caretRangeFromPoint) range = document.caretRangeFromPoint(point.x, point.y);
    if (range && (!el.contains(range.startContainer) || range.startContainer.parentElement.closest('.sp-ed-before'))) range = null;
    if (!range) { range = document.createRange(); range.selectNodeContents(el); range.collapse(false); }
    if (point === 'all') { range = document.createRange(); range.selectNodeContents(el); }
    sel.removeAllRanges();
    sel.addRange(range);
    placeTools();
  }

  // ---- キー・貼り付け ----
  function onKey(e) {
    if (e.isComposing || e.keyCode === 229) return;       // 変換中は何もしない
    if (e.key === 'Enter') { e.preventDefault(); confirm(); return; }
    if (e.key === 'Escape') { e.preventDefault(); cancel(); return; }
    if (e.key === 'Tab') {
      e.preventDefault();
      const list = visible(), i = list.indexOf(cur.el), next = list[i + (e.shiftKey ? -1 : 1)];
      confirm();
      if (next && next.isConnected) open(next, 'all');
      return;
    }
    if (e.metaKey || e.ctrlKey) {
      const k = e.key.toLowerCase();
      if (k === 'b') { e.preventDefault(); decorate('bold'); }
      else if (k === 'i' || k === 'u') e.preventDefault();     // 書き戻せない飾りは入れない
    }
  }
  function onPaste(e) {
    e.preventDefault();
    const dt = e.clipboardData;
    let text = dt ? dt.getData('text/plain') : '';
    if (!text && dt) text = new DOMParser().parseFromString(dt.getData('text/html'), 'text/html').body.textContent;
    text = text.replace(/\s*[\r\n]+\s*/g, ' ');
    if (!text || !cur) return;
    // execCommand は、選びが非編集の札を含むと入らないことがあるので、Range で入れる
    const sel = getSelection();
    let r = sel.rangeCount ? sel.getRangeAt(0) : null;
    if (!r || !cur.el.contains(r.commonAncestorContainer)) { r = document.createRange(); r.selectNodeContents(cur.el); r.collapse(false); }
    r.deleteContents();
    const node = document.createTextNode(text);
    r.insertNode(node);
    r.setStartAfter(node);
    r.collapse(true);
    sel.removeAllRanges();
    sel.addRange(r);
    placeTools();
  }

  // ---- 舞台の文字を押した ----
  function onClick(e) {
    if (e.button !== 0 || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;
    const t = e.target && e.target.nodeType === 1 ? e.target : e.target && e.target.parentElement;
    const el = t && t.closest('[data-src]');
    if (!el || !stage().contains(el) || el.closest('.hide') || el.closest('.sp-ed-before')) return;
    if (cur && cur.el === el) return;                       // 開いている欄の中を押した：カーソルを動かすだけ
    open(el, { x: e.clientX, y: e.clientY });
  }

  function init() {
    const s = stage();
    if (s) s.addEventListener('click', onClick);
  }
  if (document.getElementById('stage')) init(); else document.addEventListener('DOMContentLoaded', init);

  window.EditorInline = { isOpen: () => !!cur, confirm, cancel, serialize };
})();
