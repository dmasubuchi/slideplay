// Editor：ためている直し（その場で直した文）の持ち物。画面の置き換え・札・一覧・「反映」を受け持つ。
// 直しは sessionStorage に持ち（読み直しでは消えない）、サーバーには「反映」のときだけ送る。
// 位置（src の始め・終わり）は Python の文字の番号のまま、JavaScript は計算せず送り返す。
// 使い方：window.EditorPending（render.js の decorate が描くたびに呼び、live.js が札と relocate を呼ぶ）
(function () {
  "use strict";
  const STORE = 'sp-editor-pending';
  const LOST = '見つかりません（エディターで変わりました）';
  const SAME = 'エディターでこの文字が変わっているので、反映しませんでした';
  let edits = [];              // { key, src, slide, before, after, lost, message, sent }（足した順）
  let bar = null, countEl = null, applyEl = null, hintEl = null, listEl = null, toastEl = null, toastTimer = 0;
  let sending = false;
  let needRelocate = false;    // 読み込み直後の1回（この時点ではデッキがまだない。最初の decorate の前に回す）

  const inline = (el, text) => window.EditorSlides.inline(el, text);
  const live = () => window.EditorLive;
  const inlineApi = () => window.EditorInline;     // edit.js が作る。毎回探す（ないときは「開いていない」）
  const parseKey = key => { const m = /^(\d+):(\d+)-(\d+)$/.exec(key); return m ? [+m[1], +m[2], +m[3]] : null; };
  const plain = text => { const s = document.createElement('span'); inline(s, text); return s.textContent; };   // 飾りを外した文
  const slideTitle = id => {
    const d = window.slideDeck, s = d && d.info && d.info.slides.find(x => x.id === id);
    return (s && s.title) || id;
  };

  function save() {
    try { sessionStorage.setItem(STORE, JSON.stringify(edits)); } catch (e) { /* 書けなくても続ける */ }
  }
  function load() {
    try {
      const v = JSON.parse(sessionStorage.getItem(STORE) || '[]');
      if (Array.isArray(v)) edits = v.filter(e => e && parseKey(e.key) && typeof e.before === 'string' && typeof e.after === 'string');
    } catch (e) { edits = []; }
    needRelocate = edits.length > 0;
  }

  // 1つの文の要素に、直し（e）の印を付ける。e が null なら元の文（text）に戻す
  function paint(el, e, text) {
    el.replaceChildren();
    if (e) {
      const old = document.createElement('span');
      old.className = 'sp-ed-before';
      old.setAttribute('contenteditable', 'false');
      old.textContent = plain(e.before);
      el.append(old);
      inline(el, e.after);
    } else inline(el, text);
    el.classList.toggle('sp-ed-pending', !!e);
  }
  // 描いてある要素（舞台・縮小・一覧のうち、いま文書にあるもの）をその場で付け替える。デッキは差し替えない
  function repaint(key, e, text) {
    for (const el of document.querySelectorAll(`[data-src="${key}"]`)) paint(el, e, text);
  }
  function changed() {       // 直しが変わったときの後始末：保存・札（描き直しはしない）
    save();
    updateBar();
    renderList();
  }

  const get = key => edits.find(e => e.key === key) || null;
  function remove(key) {
    const i = edits.findIndex(e => e.key === key);
    if (i < 0) return;
    const [gone] = edits.splice(i, 1);
    if (!gone.lost) repaint(key, null, gone.before);       // 直せなくなった直しの key は古い：描き戻すと別の文を上書きする
    changed();
  }
  function add({ key, slide, before, after }) {
    const src = parseKey(key);
    if (!src) return;
    const i = edits.findIndex(e => e.key === key);
    if (after === before) { if (i >= 0) remove(key); return; }
    const e = { key, src, slide, before, after, lost: false, message: '' };
    if (i >= 0) edits[i] = e; else edits.push(e);
    repaint(key, e);
    changed();
  }
  const list = () => edits.slice();
  const count = () => edits.filter(e => !e.lost && !e.sent).length;
  const shown = () => edits.filter(e => !e.sent);        // 札・一覧に出す直し（送り済みは新しいデッキが来るまでの仮置き）

  // 新しいデッキで、各直しの場所を探し直す（live.js が差し替える前に呼ぶ）
  function relocate(deck) {
    const ed = deck && deck.editor;
    if (!ed) return;
    needRelocate = false;
    const keys = ed.keys();
    // text と同じ文の場所：同じページを先に、なければほかのページも。元の行に一番近いもの
    const find = (e, text) => {
      const hits = keys.filter(k => ed.textAt(k) === text);
      const near = list => list.reduce((best, k) => (!best || Math.abs(parseKey(k)[0] - e.src[0]) < Math.abs(parseKey(best)[0] - e.src[0]) ? k : best), null);
      return near(hits.filter(k => ed.slideAt(k) === e.slide)) || near(hits);
    };
    const keep = [];
    for (const e of edits) {
      if (e.sent) {                                      // 送った直し：新しいデッキに after があれば（なければ before があるときだけ）もう少し待つ
        if (ed.textAt(e.key) === e.after || find(e, e.after) || !find(e, e.before)) continue;
        keep.push(e);
        continue;
      }
      if (e.lost && e.message !== LOST) { keep.push(e); continue; }     // サーバーに断られたものは、場所では戻さない
      const k = ed.textAt(e.key) === e.before ? e.key : find(e, e.before);
      if (k) {
        e.key = k; e.src = parseKey(k); e.slide = ed.slideAt(k); e.lost = false; e.message = '';
      } else { e.lost = true; e.message = LOST; }
      keep.push(e);
    }
    edits = keep;
    save();
    updateBar();
    renderList();
  }

  // 描いた1ページ（舞台・縮小）に、そのページの直しを重ねる
  function decorate(target, slideId) {
    if (needRelocate) relocate(window.slideDeck);
    for (const e of edits) {
      if (e.lost || e.slide !== slideId) continue;
      const el = target.querySelector(`[data-src="${e.key}"]`);
      if (!el) continue;
      paint(el, e);
    }
  }

  // ---- 札・一覧・知らせ ----
  function mount(b) {
    bar = b;
    hintEl = document.createElement('span');
    hintEl.className = 'sp-edit-hint';
    hintEl.textContent = '文字をクリックすると直せます';
    countEl = document.createElement('button');
    countEl.className = 'sp-edit-count';
    countEl.type = 'button';
    countEl.addEventListener('click', () => { if (listEl) { listEl.hidden = !listEl.hidden; renderList(); } else renderList(true); });
    applyEl = document.createElement('button');
    applyEl.className = 'sp-edit-apply';
    applyEl.type = 'button';
    applyEl.textContent = '反映';
    applyEl.addEventListener('click', () => { apply(); });
    bar.append(hintEl, countEl, applyEl);
    updateBar();
  }
  function updateBar() {
    if (!bar) return;
    const n = shown().length;
    countEl.hidden = n === 0;
    countEl.textContent = `直し ${n}`;
    applyEl.disabled = count() === 0 || sending;
  }
  function renderList(open) {
    if (!listEl) {
      if (!open) return;
      listEl = document.createElement('div');
      listEl.className = 'sp-edit-list';
      document.body.append(listEl);
    }
    if (open) listEl.hidden = false;
    listEl.replaceChildren();
    for (const e of shown()) {
      const row = document.createElement('div');
      row.className = 'sp-edit-row' + (e.lost ? ' lost' : '');
      const text = document.createElement('span');
      text.className = 'sp-edit-row-text';
      text.textContent = `${slideTitle(e.slide)}：${plain(e.before)} → ${plain(e.after)}`;
      text.addEventListener('click', () => { location.hash = '#' + e.slide; });
      const cancel = document.createElement('button');
      cancel.type = 'button';
      cancel.textContent = '取り消す';
      cancel.addEventListener('click', () => remove(e.key));
      row.append(text, cancel);
      if (e.lost) {
        const msg = document.createElement('div');
        msg.className = 'sp-edit-row-msg';
        msg.textContent = e.message;
        row.append(msg);
      }
      listEl.append(row);
    }
    if (!listEl.children.length) listEl.hidden = true;
  }
  function toast(text) {
    if (!toastEl) {
      toastEl = document.createElement('div');
      toastEl.className = 'sp-edit-toast';
      document.body.append(toastEl);
    }
    toastEl.textContent = text;
    toastEl.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { toastEl.hidden = true; }, 2500);
  }

  // ---- 反映：開いている入力欄を確定して、lost でない直しを一度に送る ----
  async function apply() {
    if (sending) return;
    const inl = inlineApi();
    if (inl && typeof inl.isOpen === 'function' && inl.isOpen() && typeof inl.confirm === 'function') inl.confirm();
    const todo = edits.filter(e => !e.lost && !e.sent);
    if (!todo.length) return;
    sending = true;
    updateBar();
    try {
      const res = await fetch('/api/apply', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ edits: todo.map(e => ({ key: e.key, src: e.src, before: e.before, after: e.after })) }),
      });
      if (!res.ok) throw new Error('HTTP ' + res.status);
      const data = await res.json();
      for (const e of todo) {
        if (data.applied.includes(e.key)) e.sent = true;
        const c = data.conflicts.find(x => x.key === e.key);
        if (c) { e.lost = true; e.message = c.message; repaint(e.key, null, e.before); }
      }
      const parts = [];
      if (data.applied.length) parts.push(`${data.applied.length}か所を反映しました`);
      if (data.conflicts.length) parts.push(`${data.conflicts.length}か所は、${SAME}`);
      toast(parts.join('。'));
    } catch (err) {
      toast('反映できませんでした');
    } finally {
      sending = false;
      changed();
      if (live() && typeof live().refresh === 'function') live().refresh();     // 新しいデッキをすぐ聞く
    }
  }

  window.addEventListener('beforeunload', e => {
    if (shown().length) { e.preventDefault(); e.returnValue = ''; }
  });

  load();
  window.EditorPending = { add, get, remove, list, count, decorate, relocate, mount, apply, toast };
})();
