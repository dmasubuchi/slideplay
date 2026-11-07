// Editor：保存のたびに、ページを読み直さずデッキを描き直す。player.js より先に読む。
// 使い方：window.slideEditor = { attach(api) }（player.js が起動時に1回呼ぶ）
(function () {
  const POLL_MS = 300;                 // サーバーに rev を聞く間隔
  let api = null;
  let rev = Number(document.body.dataset.rev);   // このページを作ったときの rev
  let first = true;                    // 最初の1回は札・帯のために deck を取る（rev が同じなら描き直さない）
  let busy = false, again = false;     // again：処理中に refresh が呼ばれた（終わったらすぐもう1回）
  let fails = 0;                       // 問い合わせが続けて失敗した回数
  let bar = null, pill = null, errBox = null, warnBox = null, connBox = null;
  const CONN_MSG = 'サーバーにつながりません。slide-edit open で開き直してください';
  const inlineOpen = () => !!(window.EditorInline && typeof window.EditorInline.isOpen === 'function' && window.EditorInline.isOpen());

  function box(cls, old) {
    if (old) return old;
    const e = document.createElement('div');
    e.className = cls;
    document.body.append(e);
    return e;
  }

  function show(data) {
    if (!bar) {                        // 札：描き直しの時刻と、直しの数・「反映」（pending.js が足す）
      bar = box('sp-edit-bar');
      pill = document.createElement('div');
      pill.className = 'sp-edit-pill';
      bar.append(pill);
      if (window.EditorPending) window.EditorPending.mount(bar);
    }
    pill.textContent = `${data.file} · ${data.at} に描き直し`;
    if (data.error) {
      errBox = box('sp-edit-error', errBox);
      errBox.textContent = `${data.error.line}行目：${data.error.message}`;
    } else if (errBox) { errBox.remove(); errBox = null; }
    const w = data.warnings || [];
    if (w.length) {
      warnBox = box('sp-edit-warn', warnBox);
      const head = `${w[0].line}行目：${w[0].message}`;
      warnBox.textContent = w.length > 1 ? `${head} ほか ${w.length - 1} 件` : head;
    } else if (warnBox) { warnBox.remove(); warnBox = null; }
  }

  async function tick() {
    if (busy || !api) return;
    busy = true;
    try {
      const now = (await (await fetch('/api/rev', { cache: 'no-store' })).json()).rev;
      fails = 0;
      if (connBox) { connBox.remove(); connBox = null; }
      if (!first && now === rev) return;
      if (inlineOpen()) return;        // 入力欄が開いている間は差し替えない（rev も進めず、次の回にまた試す）
      const data = await (await fetch('/api/deck', { cache: 'no-store' })).json();
      const changed = data.rev !== rev;
      rev = data.rev;
      first = false;
      if (changed && data.deck && !data.error) {
        const deck = EditorSlides.createDeck(data.deck, { editing: true });
        if (window.EditorPending) window.EditorPending.relocate(deck);   // ためた直しを新しい場所へ（描く前に）
        api.replaceDeck(deck);
        document.title = `${data.deck.info.title} — 編集`;   // 描き直せたときだけ（誤りの間は前のまま）
      }
      show(data);
    } catch (e) {
      // サーバーが止まった・通信が切れた：次の回でまた聞く。3回続けて失敗したら帯で知らせる
      if (++fails >= 3) {
        connBox = box('sp-edit-error', connBox);
        connBox.textContent = CONN_MSG;
      }
    } finally {
      busy = false;
      if (again) { again = false; tick(); }
    }
  }

  // 反映の後などに、すぐ1回聞く
  window.EditorLive = {
    refresh() { if (busy) again = true; else tick(); },
  };

  window.slideEditor = {
    attach(a) {
      api = a;
      tick();
      setInterval(tick, POLL_MS);
    },
  };
})();
