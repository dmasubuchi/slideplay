# slideplay

[English](README.md) | 日本語

デモ：<https://dmasubuchi.github.io/slideplay/>（日本語の目次は <https://dmasubuchi.github.io/slideplay/index.ja.html>。このプレイヤーで動く紹介のデッキと見本）

slideplay は、HTML のスライドを、同じ操作で発表・閲覧できる共通のプレイヤー。1ファイル（`player/player.js`）・依存なし・CSS 込み・`file://` で動く。

## 何ができるか

- スライドの「中身」（何をどう描くか）と「プレイヤー」（操作・移動・一覧・ノート・リンク）を分ける。中身は `window.slideDeck`（スライドの一覧と `render` 関数）を渡すだけで、キー操作・URL・直近の場所はプレイヤーが受け持つ
- 段階（1枚の中で順に出る表示）、規定の順序の移動、直近の場所を戻る・進む（←→）、縮小一覧（O）、一覧つきの画面（T）、ノート（N）、メモ（M）、リンク（移動・外部・補足・コピー）、複数のデッキを並べる目次、PDF の書き出し（P）、書き込み（D）
- 動きの層（送り・入場・指す）。デッキが選んだ層だけが効く
- URL の hash が場所を表す（`#s22.2`）。再読み込み・共有で同じ場所が開く
- iPhone・iPad の指で払う操作（左へ払う＝→ など）。キーと同じ動きをする
- `?render` を付けると、静止画や動画をつくる外部の道具のための描画モードになる

## すぐ試す

新しいフォルダーに `player.js` と、次の最小のデッキ `deck.html` を置く。

```
mkdir my-deck && cd my-deck
cp /path/to/slideplay/player/player.js .
```

`deck.html`（3枚。2枚目は3段階）：

```html
<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>はじめの一歩</title>
<style>
  /* 舞台（1920×1080）の見た目。.sp-target の中だけに効かせる */
  .sp-target { position: relative; width: 1920px; height: 1080px; overflow: hidden;
    background: #fff; color: #1d2733; font-family: sans-serif; }
  .sp-target h1 { margin: 0; padding: 140px 160px 40px; font-size: 96px; }
  .sp-target ul { margin: 0; padding: 0 160px; list-style: none; font-size: 56px; line-height: 2; }
  .sp-target .hide { visibility: hidden; }
</style>
</head>
<body>
<div id="stage" class="sp-target"></div>
<script>
const slides = [
  { id: 'cover', title: 'はじめの一歩', items: [] },
  { id: 'points', title: '3つのポイント', items: ['1つ目', '2つ目', '3つ目'] },
  { id: 'end', title: 'おわり', items: [] },
];

window.slideDeck = {
  contract: 1,
  info: {
    id: 'hello',
    title: 'はじめの一歩',
    // steps は最後の段階の番号（段階がなければ 0）
    slides: slides.map(s => ({ id: s.id, title: s.title, steps: s.items.length })),
  },
  // ref はスライドの位置（数）か id、step は 0〜steps、target は描画先
  render(ref, step, target) {
    const s = typeof ref === 'number' ? slides[ref] : slides.find(x => x.id === ref);
    const h1 = document.createElement('h1');
    h1.textContent = s.title;
    const ul = document.createElement('ul');
    s.items.forEach((text, k) => {
      const li = document.createElement('li');
      li.textContent = text;
      if (k >= step) li.className = 'hide';   // 段階 step では、先頭から step 個を見せる
      ul.append(li);
    });
    target.replaceChildren(h1, ul);
  },
};
</script>
<script src="player.js"></script>
</body>
</html>
```

`deck.html` をブラウザで開く（ダブルクリックでよい。サーバーは要らない）。↓・PageDown・Space で次へ（2枚目は段階を1つずつ進めてから3枚目へ）、↑ で戻る。`?` で操作の一覧、`O` で縮小一覧、`F` で全画面、`P` で PDF。URL の hash（`#points.2` など）が今の場所を表す。

見本は `examples/generic/index.html`（目次）から開く。紹介のデッキ（英語・日本語）は `demo/` にある。

- `proposal.html`：商談の提案書。リンク4種類・節・段階・ノートが一通り入っている
- `minimal.html`：スライド1枚だけの最小のデッキ
- `handout.html`：デッキではないただのページ（目次から開く）
- `motion.html`：動きの層（送り・入場・指す）を選んだデッキ。目次には載せていないので直接開く
- `render.js`：見本の描画（`GenericSlides.createDeck`）。自分のデッキで使ってもよい

## デッキの形

詳しい決まりは [CONTRACT.md](CONTRACT.md)。ここでは要点だけ。

`window.slideDeck`（`player.js` を読み込む前に定義する）：

```js
window.slideDeck = {
  contract: 1,
  info: {
    id: "ch-01",          // デッキの ID（目次の中で一意）
    title: "導入の概要",
    label: "第1章",        // 任意
    home: "../index.html", // 任意。H で開く目次
    color: "#0b6bcb",      // 任意。強調色
    sections: [{ id: "A", title: "現状と課題" }],   // 任意
    motion: { send: true, entry: "bounce", point: true },   // 任意。動きの層
    slides: [
      { id: "s01", title: "表紙", steps: 0 },
      { id: "s02", title: "要点", section: "A", steps: 2, notes: "話す人のメモ", minutes: 2,
        links: [{ label: "費用の内訳", kind: "jump", target: "s05" }] },
    ],
  },
  render(ref, step, target) { /* target の中身だけを置き換える。同期で描き終える */ },
};
```

- スライドの `id` は英字で始まる名前で、一度付けたら変えない（途中に足すときは新しい ID。`s05` と `s06` の間なら `s05b`）
- `render` は同じ `ref` と `step` なら、いつ・どの描画先に呼んでも同じ見た目にする。プレイヤーは、メインの舞台（`#stage`）のほかに、縮小一覧・一覧つきの画面・PDF の印刷用の写しにも同じ `render` で描く
- リンク（`links`）の `kind`：`jump`（スライドや別のページへ移る）・`external`（新しいタブで開く）・`more`（補足を重ねて出す）・`copy`（クリップボードに写す）。スライドの上の場所は、描いた要素に `data-link="番号"` を付けて示す
- 動きの層のための印（`data-sp-role` など）は、属性を付けるだけで見た目は変わらない

目次（複数のデッキの一覧）は、`slideDeck` の代わりに `window.slideCatalog` を定義して、同じ `player.js` を読み込む：

```js
window.slideCatalog = {
  contract: 1,
  title: "セルフトレーニング講座",
  lead: "全3章・合計約60分",   // 任意
  decks: [
    { id: "ch-01", href: "ch-01/slides.html", label: "第1章", title: "導入の概要",
      items: ["現状と課題"], meta: "20枚・約20分" },
    { id: "cheatsheet", kind: "page", href: "cheatsheet.pdf", title: "チートシート" },
  ],
};
```

## キー操作

デッキの中（`?` でも一覧が出る）：

- ↓・PageDown・Space：次へ（段階があれば次の段階、なければ次のスライド）
- ↑・PageUp：前へ（前の段階、なければ前のスライドの最後の段階）
- Shift＋↓・Shift＋↑：次のスライドの最初へ・前のスライドの最後の段階へ
- ←・→：直近の場所を戻る・進む（最大10か所。別のページの場所へも移れる）。先の場所がないときの → は ↓ と同じ
- Home・End：最初・最後のスライドへ
- O：縮小一覧　T：一覧つきの画面（左に全スライドの縮小）　L：リンクを表示　H：目次へ戻る（`info.home` があるとき）
- N：ノート　M：メモの帯　P：PDF に書き出す　F：全画面　?：操作の一覧　Esc：開いているものを閉じる
- D：書き込みを始める・終える。書き込みの間は、⌘Z・Ctrl＋Z でひとつ戻す、E で今のページの書き込みを全部消す、右クリックで文字を置く、ダブルクリックで選ぶ、Delete・Backspace で選んだものを消す
- Tab：操作ボタンを出す（操作ボタンは、読み込み直後は隠れている。マウスを動かしても出る。`?` の一覧で「自動で消す・いつも出す・出さない」を選べる）

目次の中：

- ↑・↓：カードを選ぶ　Shift＋↑・↓：前後のページ　Enter：開く　1〜9：N番目を開く　←・→：直近の場所　?：操作の一覧

指で払う操作（iPhone・iPad。デッキと目次）：左へ払う＝→、右へ払う＝←、上へ払う＝↓、下へ払う＝↑。

スライドをクリックしても進まない（文字やコマンドを選んでコピーできるようにするため）。

## 動き・書き込み・メモ・PDF

- 動き：デッキが `info.motion` で選んだ層だけが効く。何も選ばないデッキは、送り（切り替えの動き）だけが付く。見る人は `?` の一覧で「動き：あり／なし」を選べる（OS の「視差効果を減らす」でも止まる）
  - 送り（`send`）：隣のスライドへ移ると左右に流れる。隣でないスライドへのジャンプは、ふわっと消えてから現れる
  - 入場（`entry`: `"subtle"`（控えめ型）・`"bounce"`（弾む型））：次へ進んで次のスライドに着いたとき、中身が順に出る。中身に付けた役目の印（`data-sp-role`）から動きが決まる
  - 指す（`point`）：ホバーで浮かび、同じ組のほかが薄くなる。マウスのまわりが明るくなる光（`?` の一覧で「光：あり／なし」）
  - 動きの選び方を並べて確かめる道具：`python3 scripts/motion_preview.py <デッキの HTML> --choice send,entry=bounce,point --out <出力先>`（「動きなし」と並べた `compare.html` を作る。元のデッキのフォルダーには書かない）
- 書き込み（D）：どのデッキでも使える。□・○・線・矢印・手書き・文字（右クリックで置く）と蛍光ペン。色・太さ・大きさ・描き味は帯で選ぶ。マウスと Apple Pencil で書ける（指では書かない）。「白紙を足す」で、今のページの後ろに白紙の追加ページを足せる
  - 書き込みと追加ページは、ページを開いている間だけ覚える（保存しない）。残すには P で PDF にする。書き込みか追加ページがあるときに閉じる・再読み込みすると、ブラウザーが確認を出す
- メモ（M）：舞台の下にメモの帯が出る（スライドごと）。N のノートの下の「自分用のメモを開く」で、自分用の書き留めも書ける。メモはこのブラウザの `localStorage` にだけ保存される。帯の「書き出す」で、帯のメモだけを `<デッキの題名>-メモ.md` に保存できる
- PDF（P）：印刷の画面が開くので、送り先を「PDFに保存」にする。全スライドが1枚1ページ（16:9）で入り、書き込みと追加ページも重なる。⌘P でも同じ
- ノート（N）：`notes` を右に出す。舞台は残りの幅に縮む

プレイヤーが保存するのは、設定・直近の場所・メモの3つだけ（`localStorage`・`sessionStorage`。ほかに、ページ移動の直前の時刻を `sessionStorage` に一時的に書く）。保存できなくても、表示とページの中の移動は続く。

## Editor（Markdown の下書き）

Markdown の下書きを、保存のたびに1秒ほどで描き直す手元のサーバー（127.0.0.1 だけで聞く）。Python 3 の標準ライブラリだけで動く。

```
scripts/slide-edit open examples/editor     # フォルダーか .md。ブラウザーに出る
scripts/slide-edit stop examples/editor
```

- ブラウザーは標準ライブラリの `webbrowser` で開く。開けない環境では `--no-open` を付けて、表示された URL を自分で開く
- エディターで保存すると、見ていたスライド・段階・書き込みはそのままで描き直す。書き方の誤りは赤い帯に行と文言で出て、舞台は前のまま。直すと消える
- 舞台の文字をクリックすると、その場で直せる。Enter で確定、Tab で次の文字、Esc でやめる。⌘B で太く、「A＋ 大きく」で大きくする（Markdown では `**…**`・`++…++`。`==…==` は目立たせる）
- 直しはためておき、「反映」を押すとまとめて Markdown に書く。反映の前に、エディターで保存しておく。最初の「反映」で、ID のないページすべてに `<!-- id: pN -->` を書き足す
- Markdown の書き方は `examples/editor/下書き.md` が見本：`---` でページを区切る、`<!-- _class: 表紙 -->` などでページの型（表紙・ふつう・二段・図と文・強調）を選ぶ、`*` の箇条書きは段階で順に出る、ほかの HTML コメントはノートになる
- `<デッキ>/.editor/`（`server.json` に鍵が入る）は公開しない。`.gitignore` に入っている

## `?render`

デッキの URL に `?render` を付けると、部品・CSS・リンクの印・キー操作を一切出さない描画モードになる。`body` に class `render` が付き、`window.renderSlide(i, step)`（`render(i, step, #stage)` と同じ）と `window.deckInfo()`（`[{ id, steps }]` をスライドの順に返す）が使える。スライドを1枚ずつ静止画にする外部の道具が使う。決まりは [CONTRACT.md](CONTRACT.md) §3.1。

## 試験

Python 3（3.12 で確認）。試験一式は macOS で確かめた。

```
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install pytest playwright pillow pypdf pymupdf numpy
python3 -m playwright install chromium
python3 -m pytest -m "not webkit"
```

- 全部で約7分かかる（環境による）。`pytest.ini` の既定が `-m "not webkit"`。ページキャッシュ（bfcache）の試験は、Playwright の Chromium の完全版（新しい headless）が要る。入っていないときは skip せず、入れ方を書いて失敗する。上の `install chromium` で入る
- WebKit の参考の試験：`python3 -m playwright install webkit` のあと `python3 -m pytest -m webkit -v`（入っていなければ skip）。実機の Safari・iPad の代わりではなく、失敗しても完成の条件ではない。結果は `webkit-report.json` に書く
- 試験の作業フォルダー（pytest の一時フォルダー `pytest-tmp` と `webkit-report.json`）は、環境変数 `SLIDE_PLAYER_WORK_ROOT` が指す場所。未設定なら OS の一時フォルダーの下の `slide-player-tests`
- pytest は同時に1つだけ走らせる。実行のたびに `pytest-tmp` を作り直すため、2つ走らせると互いのフォルダーを消し合う。並べて走らせるときは `SLIDE_PLAYER_WORK_ROOT` で場所を分ける：`SLIDE_PLAYER_WORK_ROOT=/tmp/sp-a python3 -m pytest -m "not webkit"`
- 試験の生成物（pytest の一時フォルダー・WebKit の結果）は Repo の外の作業フォルダーに置く（`.pytest_cache`・`__pycache__` は除き、`.gitignore` 済み）

## 対応ブラウザ

- 試験で動かしているのは Playwright の Chromium。Chrome 系のブラウザーで使う前提
- WebKit（Safari 相当）は参考の試験だけ。実機の Safari・iPad・iPhone と、Apple Pencil での書き心地・入場・光は確かめていない
- `file://` で開いたデッキをまたいだ ←→（別のページの場所へ戻る）は、ブラウザーが `sessionStorage` を同じ保存領域として扱うかで決まる。共有できないときは、別のページの場所へは移れず、そのページの中だけで覚える

## フォルダの形

```
index.html                  デモの目次・英語版（GitHub Pages のトップ）
index.ja.html               デモの目次・日本語版
demo/en/, demo/ja/          紹介のデッキ3つ（intro・chic・bounce）の英語版・日本語版（examples/generic/render.js で作る）
player/player.js            プレイヤー本体（1ファイル・依存なし）
examples/generic/           デッキと目次の見本（render.js は見本の描画）
examples/editor/            Editor で開く Markdown の下書きの見本
editor/                     Editor（Python の標準ライブラリだけ）
scripts/slide-edit          Editor を開く・止める
scripts/motion_preview.py   動きの層の見本を「動きなし」と並べる道具
tests/                      pytest の試験（Playwright）
CONTRACT.md                 中身とプレイヤーの約束（v1.6。日本語）
README.md                   英語の説明
README.ja.md                この文書（日本語の説明）
LICENSE                     MIT
pytest.ini
```

## ライセンス

MIT（[LICENSE](LICENSE)）。
