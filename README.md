# slideplay

English | [日本語](README.ja.md)

Version 0.1.0

Demo and introduction: <https://dmasubuchi.github.io/slideplay/> (Japanese: <https://dmasubuchi.github.io/slideplay/index.ja.html>). That page has the content of this README and links to the slide catalog, <https://dmasubuchi.github.io/slideplay/catalog.html> (Japanese: <https://dmasubuchi.github.io/slideplay/catalog.ja.html>). The demo has three decks about slideplay itself, in English and Japanese: an introduction, a quiet deck that uses the subtle motion style, and a numbers deck that uses the bounce motion style. It also has the sample decks from `examples/generic/`.

slideplay is a dependency-free, single-file HTML slide player. A deck is an ordinary HTML page that defines `window.slideDeck` (a list of slides and a `render` function) and loads `player/player.js`. The player adds navigation, steps, an overview, notes, links, memos, drawing, PDF export and a table of contents. It works from `file://`, with no build step and no CDN. MIT licensed.

Two things to know up front:

- The player's own UI text (the key list, buttons, toasts) is Japanese for now. Slide content is whatever your deck renders, in any language.
- The contract between a deck and the player, [CONTRACT.md](CONTRACT.md), is written in Japanese for now.

## What it does

- Separates the slides' content (what to draw and how) from the player (keys, navigation, overview, notes, links). A deck only hands over `window.slideDeck`; key handling, the URL and the recent places belong to the player.
- Steps (parts of a slide that appear one by one), moving in the deck's order, going back and forth through recent places (Left/Right), an overview of thumbnails (O), a side view with all slides listed (T), notes (N), memos (M), links (jump, external, more, copy), a catalog page that lists several decks, PDF export (P) and drawing (D).
- Motion layers (send, entry, point). Only the layers a deck chooses are active.
- The URL hash is the current place (`#s22.2`). Reloading or sharing the URL opens the same place.
- Swipe gestures on iPhone and iPad (swipe left = Right, and so on), the same as the keys.
- Adding `?render` to the URL switches to a plain drawing mode for external tools that produce still images or video.

## Quick start

Make a new folder and put `player.js` and the minimal deck `deck.html` below in it.

```
mkdir my-deck && cd my-deck
cp /path/to/slideplay/player/player.js .
```

`deck.html` (3 slides; the second has 3 steps):

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>First steps</title>
<style>
  /* The look of the stage (1920x1080). Apply it inside .sp-target only. */
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
  { id: 'cover', title: 'First steps', items: [] },
  { id: 'points', title: 'Three points', items: ['One', 'Two', 'Three'] },
  { id: 'end', title: 'The end', items: [] },
];

window.slideDeck = {
  contract: 1,
  info: {
    id: 'hello',
    title: 'First steps',
    // steps is the number of the last step (0 when a slide has no steps)
    slides: slides.map(s => ({ id: s.id, title: s.title, steps: s.items.length })),
  },
  // ref is the slide's position (a number) or its id, step is 0..steps, target is where to draw
  render(ref, step, target) {
    const s = typeof ref === 'number' ? slides[ref] : slides.find(x => x.id === ref);
    const h1 = document.createElement('h1');
    h1.textContent = s.title;
    const ul = document.createElement('ul');
    s.items.forEach((text, k) => {
      const li = document.createElement('li');
      li.textContent = text;
      if (k >= step) li.className = 'hide';   // at step N, show the first N items
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

Open `deck.html` in a browser (double-clicking is fine; no server needed). Down, PageDown or Space goes forward (on slide 2, it goes through the three steps before slide 3), Up goes back. `?` shows the key list, `O` the overview, `F` full screen and `P` PDF. The URL hash (for example `#points.2`) is the current place.

The samples are opened from `examples/generic/index.html` (a catalog). They are written in Japanese.

- `proposal.html`: a business proposal. It has all four kinds of links, sections, steps and notes.
- `minimal.html`: the smallest deck, with one slide.
- `handout.html`: a plain page, not a deck (opened from the catalog).
- `motion.html`: a deck that chooses the motion layers (send, entry, point). It is not in the sample catalog, so open it directly.
- `render.js`: the sample renderer (`GenericSlides.createDeck`). You can use it in your own decks. The introduction decks in `demo/` are built with it.

## The deck format

A deck and a catalog declare `contract: 1`. That is the number of the deck format, not the version of slideplay: it becomes 2 only if the format changes in a way that breaks existing decks. The version to cite is the product version at the top of this README. It follows semantic versioning and is also written in CONTRACT.md section 6 and on the first line of `player/player.js`.

The full rules are in [CONTRACT.md](CONTRACT.md) (in Japanese). In short:

`window.slideDeck` (define it before loading `player.js`):

```js
window.slideDeck = {
  contract: 1,            // the deck format number (not the product version)
  info: {
    id: "ch-01",          // the deck's id (unique within a catalog)
    title: "Overview",
    label: "Chapter 1",    // optional
    home: "../index.html", // optional: the catalog opened by H
    color: "#0b6bcb",      // optional: accent color
    sections: [{ id: "A", title: "Issues" }],   // optional
    motion: { send: true, entry: "bounce", point: true },   // optional: motion layers
    slides: [
      { id: "s01", title: "Cover", steps: 0 },
      { id: "s02", title: "Key points", section: "A", steps: 2, notes: "Speaker notes", minutes: 2,
        links: [{ label: "Cost details", kind: "jump", target: "s05" }] },
    ],
  },
  render(ref, step, target) { /* replace only the contents of target; finish drawing synchronously */ },
};
```

- A slide `id` starts with a letter and never changes once given. When you add a slide in the middle, give it a new id (`s05b` between `s05` and `s06`).
- For the same `ref` and `step`, `render` gives the same result whenever it is called and into whichever target. Besides the main stage (`#stage`), the player draws with the same `render` into the overview, the side view and the print copy for PDF.
- Link `kind`: `jump` (to a slide or another page), `external` (opens a new tab), `more` (shows a note on top) and `copy` (copies text to the clipboard). Mark where a link sits on the slide by adding `data-link="N"` to the drawn element.
- Role marks for the motion layers (`data-sp-role` and so on) are plain attributes; they do not change how the slide looks.

A catalog (a list of decks) defines `window.slideCatalog` instead of `slideDeck` and loads the same `player.js`:

```js
window.slideCatalog = {
  contract: 1,
  title: "Self-training course",
  lead: "3 chapters, about 60 minutes in all",   // optional
  decks: [
    { id: "ch-01", href: "ch-01/slides.html", label: "Chapter 1", title: "Overview",
      items: ["Issues"], meta: "20 slides · about 20 min" },
    { id: "cheatsheet", kind: "page", href: "cheatsheet.pdf", title: "Cheat sheet" },
  ],
};
```

## Keys

Inside a deck (`?` also lists them):

- Down, PageDown, Space: next (the next step if there is one, otherwise the next slide)
- Up, PageUp: back (the previous step, otherwise the last step of the previous slide)
- Shift+Down, Shift+Up: the start of the next slide, the last step of the previous slide
- Left, Right: back and forward through recent places (up to 10, across pages). Right with nowhere to go forward acts as Down
- Home, End: the first and the last slide
- O: overview. T: side view (thumbnails of all slides on the left). L: show links. H: back to the catalog (when `info.home` is set)
- N: notes. M: memo strip. P: export PDF. F: full screen. ?: key list. Esc: close whatever is open
- D: start or stop drawing. While drawing: Cmd+Z or Ctrl+Z undoes one step, E clears the drawing on the current page, right-click places text, double-click selects, Delete or Backspace removes the selection
- Tab: show the control buttons (they are hidden right after loading; moving the mouse also shows them; in the `?` panel you can choose auto-hide, always show or hide)

Inside a catalog:

- Up, Down: select a card. Shift+Up, Shift+Down: previous or next page. Enter: open. 1 to 9: open the Nth card. Left, Right: recent places. ?: key list

Swipes on iPhone and iPad (decks and catalogs): swipe left = Right, swipe right = Left, swipe up = Down, swipe down = Up.

Clicking a slide does not advance it (so you can select and copy text and commands).

## Motion, drawing, memo and PDF

- Motion: only the layers the deck chooses in `info.motion` are active. A deck that chooses nothing gets the send layer only. Viewers can turn motion on or off in the `?` panel (the OS "reduce motion" setting also stops it).
  - Send (`send`): slides move left and right when you go to a neighbor. A jump to a slide that is not a neighbor fades out and in.
  - Entry (`entry`: `"subtle"` or `"bounce"`): when you arrive at the next slide by moving forward, its contents appear in order. The motion is decided by the role marks (`data-sp-role`) on the contents. `subtle` is the quiet style (fade, slide in from the left, wipe); `bounce` is the lively one (blur in, rise, grow, pop, and numbers that count up).
  - Point (`point`): hovering lifts an item and dims the others in the same group; a soft glow follows the mouse (switch it on or off in the `?` panel).
  - A tool to compare motion choices side by side: `python3 scripts/motion_preview.py <deck HTML> --choice send,entry=bounce,point --out <output folder>` (it makes a `compare.html` next to a "no motion" version and never writes into the deck's own folder).
- Drawing (D): works with every deck. Boxes, circles, lines, arrows, freehand, text (placed with a right-click) and a highlighter. Color, width, size and the way it draws are chosen in the toolbar. It works with a mouse and an Apple Pencil (not with a finger). "Add a blank page" adds a blank page after the current one.
  - Drawings and added pages are kept only while the page is open (they are not saved). To keep them, export a PDF with P. The browser asks for confirmation before you close or reload a page that has drawings or added pages.
- Memo (M): a memo strip appears under the stage (one per slide). Under the notes (N), "open my own memo" gives you a place for private notes. Memos are saved only in this browser's `localStorage`. The strip's "export" button saves just the strip's memos as `<deck title>-メモ.md`.
- PDF (P): opens the print dialog; choose "Save as PDF" as the destination. Every slide becomes one 16:9 page, with drawings and added pages on top. Cmd+P does the same.
- Notes (N): shows `notes` on the right. The stage shrinks to the remaining width.

The player saves only three things: settings, recent places and memos (`localStorage` and `sessionStorage`; it also writes the time just before a page change to `sessionStorage` temporarily). If saving fails, display and movement within the page continue.

## Editor (Markdown drafts)

A local server (listening on 127.0.0.1 only) that redraws a Markdown draft about a second after each save. It needs Python 3 and its standard library only.

```
scripts/slide-edit open examples/editor     # a folder or a .md file; opens in the browser
scripts/slide-edit stop examples/editor
```

- The browser is opened with the standard library's `webbrowser`. If it cannot be opened, add `--no-open` and open the printed URL yourself.
- When you save in your editor, the slide, step and drawings you were looking at stay as they are while the stage is redrawn. A syntax error appears in a red strip with the line and the message, and the stage stays as it was. Fix it and the strip disappears.
- Click text on the stage to edit it in place. Enter confirms, Tab goes to the next text, Esc cancels. Cmd+B makes it bold, and "A+ larger" makes it larger (in Markdown these are `**...**` and `++...++`; `==...==` highlights).
- Edits are collected, and "Apply" writes them to the Markdown in one go. Save in your editor before you apply. The first "Apply" adds `<!-- id: pN -->` to every page that has no id.
- The syntax is shown in `examples/editor/下書き.md` (a Japanese sample): `---` separates pages, `*` bullets appear step by step, and any other HTML comment becomes the notes.
- `<!-- _class: 表紙 -->` picks the page type. The type names are Japanese and must be written exactly like this: `表紙` (cover), `ふつう` (normal, the default), `二段` (two columns), `図と文` (figure with text) and `強調` (emphasis). Any other value, including an English name such as `cover`, gives a warning and the page is drawn as `ふつう`.
- `<deck>/.editor/` (`server.json` holds a key) must not be published. It is in `.gitignore`.

## `?render`

Add `?render` to a deck's URL to get a drawing mode with no UI parts, no CSS, no link marks and no key handling. The `body` gets the class `render`, and `window.renderSlide(i, step)` (the same as `render(i, step, #stage)`) and `window.deckInfo()` (returns `[{ id, steps }]` in slide order) are available. It is meant for external tools that turn slides into still images one by one. The rules are in [CONTRACT.md](CONTRACT.md) section 3.1.

## Tests

Python 3 (checked with 3.12). The test suite was verified on macOS.

```
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install pytest playwright pillow pypdf pymupdf numpy
python3 -m playwright install chromium
python3 -m pytest -m "not webkit"
```

- It takes about 7 minutes in all (it depends on your machine). The default in `pytest.ini` is `-m "not webkit"`. The back/forward cache (bfcache) tests need the full Chromium of Playwright (the new headless mode). When it is missing, they do not skip; they fail and tell you how to install it. The `install chromium` line above installs it.
- Reference WebKit tests: run `python3 -m playwright install webkit`, then `python3 -m pytest -m webkit -v` (they skip if WebKit is not installed). They are not a substitute for a real Safari or iPad, and a failure there does not decide whether the work is done. Results are written to `webkit-report.json`.
- The test work folder (pytest's temporary folder `pytest-tmp` and `webkit-report.json`) is the folder named by the environment variable `SLIDE_PLAYER_WORK_ROOT`. When it is not set, it is `slide-player-tests` under the OS temporary folder.
- Run only one pytest at a time. Every run recreates `pytest-tmp`, so two runs delete each other's folder. To run side by side, separate the places with `SLIDE_PLAYER_WORK_ROOT`: `SLIDE_PLAYER_WORK_ROOT=/tmp/sp-a python3 -m pytest -m "not webkit"`.
- `index.html` and `index.ja.html` (the introduction pages) are built from the READMEs. After you edit `README.md` or `README.ja.md`, run `python3 scripts/build_portal.py` to rebuild them; `python3 scripts/build_portal.py --check` and the tests fail when they are out of date.
- Generated test files (pytest's temporary folder and the WebKit results) go to a work folder outside the repository (`.pytest_cache` and `__pycache__` are excluded and listed in `.gitignore`).

## Browser support

- The tests run on Playwright's Chromium, so use a Chrome-family browser.
- WebKit (Safari-like) is covered only by the reference tests. Real Safari, iPad and iPhone, and the feel of Apple Pencil drawing, entry motion and the glow, have not been checked.
- Going back and forward (Left, Right) across decks opened from `file://` depends on whether the browser treats `sessionStorage` as one shared storage. When it does not, you cannot jump to a place on another page, and the places are remembered within each page only.

## Folder layout

```
index.html                  introduction page, English (the top page of GitHub Pages; built from README.md)
index.ja.html               introduction page, Japanese (built from README.ja.md)
catalog.html                demo catalog, English (the demo decks and the samples)
catalog.ja.html             demo catalog, Japanese
demo/en/, demo/ja/          three decks about slideplay (intro, chic, bounce), in English and Japanese; built with examples/generic/render.js
player/player.js            the player (one file, no dependencies)
examples/generic/           sample decks and catalog (render.js is the sample renderer)
examples/editor/            a sample Markdown draft to open with the Editor
editor/                     the Editor (Python standard library only)
scripts/slide-edit          opens and stops the Editor
scripts/motion_preview.py   compares motion choices with a "no motion" version
scripts/build_portal.py     builds index.html and index.ja.html from the READMEs
tests/                      pytest tests (Playwright)
CONTRACT.md                 the contract between a deck and the player (in Japanese)
README.md                   this file
README.ja.md                the same, in Japanese
LICENSE                     MIT
pytest.ini
```

## License

MIT ([LICENSE](LICENSE)).
