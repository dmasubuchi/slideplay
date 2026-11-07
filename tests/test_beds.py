"""試験台の試験：汎用の見本（examples/generic）。

後の作業でプレイヤーを試すときの土台なので、「約束（CONTRACT.md §2〜§4）の形になっているか」と
「後の試験が頼る仕掛け（段階で現れるリンク、範囲外の番号、HTML を含むノートなど）があるか」を確かめる。
"""
import math
import re

import pytest

from helpers import page_session

ID_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")


# ページは page_session で開く：with を抜けるときに閉じ、ページが例外を出していれば試験が失敗になる
def generic_page(browser, generic_dir, name):
    return page_session(browser, (generic_dir / name).as_uri())


def deck_info_of(browser, generic_dir, name):
    with generic_page(browser, generic_dir, name) as page:
        return page.evaluate("slideDeck.info")


def slide_of(info, slide_id):
    return next(s for s in info["slides"] if s["id"] == slide_id)


# ---- 汎用の見本 ----

def test_generic_pages_load(browser, generic_dir):
    for name in ["proposal.html", "minimal.html", "motion.html", "index.html"]:
        with generic_page(browser, generic_dir, name) as page:
            assert page.evaluate("!!(window.slideDeck || window.slideCatalog)")


def test_generic_pages_are_self_contained(generic_dir):
    # 外部の CDN を使わない。読み込むのは相対パスのファイルだけ（約束 §2.1）
    for name in ["proposal.html", "minimal.html", "motion.html", "handout.html", "index.html"]:
        html = (generic_dir / name).read_text(encoding="utf-8")
        for src in re.findall(r'<(?:script|link)[^>]*?(?:src|href)="([^"]+)"', html):
            assert not re.match(r"^[a-z]+:|^//", src), f"{name}: 外部の読み込み {src}"
    for name in ["proposal.html", "minimal.html", "motion.html"]:
        html = (generic_dir / name).read_text(encoding="utf-8")
        assert '<div id="stage" class="sp-target"></div>' in html
        assert '<script src="../../player/player.js"></script>' in html
        assert html.index("window.slideDeck") < html.index("player/player.js")     # 先に定義する（約束 §2.1）


def test_proposal_contract_shape(browser, generic_dir):
    info = deck_info_of(browser, generic_dir, "proposal.html")
    assert info["id"] == "proposal" and info["home"] == "index.html"
    assert [x["id"] for x in info["sections"]] == ["A", "B", "C"]
    assert [s["id"] for s in info["slides"]] == ["p01", "p02", "p03", "p03b", "p04", "p05", "p06", "p07", "p08"]
    assert all(ID_PATTERN.match(s["id"]) for s in info["slides"])
    section_ids = {x["id"] for x in info["sections"]}
    assert all(s.get("section") in section_ids | {None} for s in info["slides"])
    assert all(s.get("section") for s in info["slides"] if s["id"] not in ("p01", "p08"))     # 表紙と最後だけ節なし
    assert all(isinstance(s["steps"], int) and s["steps"] >= 0 for s in info["slides"])
    assert slide_of(info, "p02")["steps"] == 2 and slide_of(info, "p05")["steps"] == 3
    assert sum(1 for s in info["slides"] if s["steps"] > 0) >= 3
    # 題名は飾りの記法なし（約束 §2.3）
    assert all(not re.search(r"==|\*\*|`|<br|\[\[", s["title"]) for s in info["slides"])


def test_proposal_links(browser, generic_dir):
    info = deck_info_of(browser, generic_dir, "proposal.html")
    links = slide_of(info, "p04")["links"]
    assert {l["kind"] for l in links} == {"jump", "external", "more", "copy"}
    by_target = {l.get("target"): l for l in links if l["kind"] in ("jump", "external")}
    assert set(by_target) == {"p07", "minimal.html#m1", "https://example.com/"}
    assert by_target["p07"]["kind"] == "jump" and by_target["minimal.html#m1"]["kind"] == "jump"
    assert by_target["https://example.com/"]["kind"] == "external"
    assert next(l for l in links if l["kind"] == "more")["text"]
    assert next(l for l in links if l["kind"] == "copy")["text"] == "npm install"
    # p06：場所のないリンク、壊れたリンク、許可しない種類のリンク
    p06 = slide_of(info, "p06")["links"]
    assert {(l["kind"], l["target"]) for l in p06} == {("jump", "p01"), ("jump", "p99"), ("jump", "javascript:alert(1)")}
    # p05：段階2で初めて見えるリンクは p02 へ
    assert [(l["kind"], l["target"]) for l in slide_of(info, "p05")["links"]] == [("jump", "p02")]
    # リンクを持たないスライドは links が空（または無い）
    assert not any(slide_of(info, i).get("links") for i in ["p01", "p02", "p03", "p03b", "p07", "p08"])


def test_proposal_notes(browser, generic_dir):
    info = deck_info_of(browser, generic_dir, "proposal.html")
    for i in ["p01", "p02", "p03", "p03b", "p04", "p05"]:
        assert slide_of(info, i)["notes"].strip(), i
    for i in ["p06", "p07", "p08"]:
        assert slide_of(info, i)["notes"] == "", i
    assert "<b>太字にならない</b>" in slide_of(info, "p03")["notes"]


def test_minimal_shape(browser, generic_dir):
    info = deck_info_of(browser, generic_dir, "minimal.html")
    assert info["id"] == "minimal"
    assert "home" not in info and not info.get("sections")
    assert [s["id"] for s in info["slides"]] == ["m1"]
    s = info["slides"][0]
    assert s["steps"] == 0 and not s.get("notes") and not s.get("links")


def test_handout_is_plain_page(browser, generic_dir):
    html = (generic_dir / "handout.html").read_text(encoding="utf-8")
    assert "player.js" not in html and "slideDeck" not in html
    with generic_page(browser, generic_dir, "handout.html") as page:
        assert page.evaluate("!window.slideDeck && !window.slideCatalog")


def test_generic_catalog_shape(browser, generic_dir):
    with generic_page(browser, generic_dir, "index.html") as page:
        cat = page.evaluate("window.slideCatalog")
    assert cat["contract"] == 1 and cat["title"] == "汎用の見本"
    assert [(d["id"], d.get("kind", "deck")) for d in cat["decks"]] == [
        ("proposal", "deck"), ("minimal", "deck"), ("handout", "page")]
    handout = cat["decks"][2]
    assert handout["href"] == "handout.html" and handout["title"] and "items" not in handout
    # デッキの id と題名は、デッキの info と同じ（約束 §4）
    for d in cat["decks"][:2]:
        info = deck_info_of(browser, generic_dir, d["href"])
        assert d["id"] == info["id"] and d["title"] == info["title"], d["href"]
        assert (generic_dir / d["href"]).is_file()
    proposal, minimal = cat["decks"][:2]
    info = deck_info_of(browser, generic_dir, "proposal.html")
    assert proposal["items"] == [x["title"] for x in info["sections"]]
    minutes = sum(s.get("minutes") or 0 for s in info["slides"])
    assert proposal["meta"] == f"{len(info['slides'])}枚・約{math.floor(minutes + 0.5)}分"
    assert minimal["meta"] == "1枚"


# ---- 汎用の見本の描画（約束 §2.5） ----

RENDER_ALL = """(() => {
  const info = slideDeck.info;
  const stage = document.getElementById('stage');
  const off = document.createElement('div');
  off.className = 'sp-target';
  document.body.appendChild(off);
  const outside = () => {                            // 描画先の外の DOM
    const clone = document.body.cloneNode(true);
    clone.querySelectorAll('.sp-target').forEach(el => { el.replaceChildren(); el.removeAttribute('style'); });
    return clone.innerHTML;
  };
  const before = outside();
  const forward = [], backward = [], offstage = [], byId = [];
  const keys = [];
  info.slides.forEach((s, k) => { for (let st = 0; st <= s.steps; st++) keys.push([k, st, s.id]); });
  keys.forEach(([k, st]) => { slideDeck.render(k, st, stage); forward.push(stage.innerHTML); });
  keys.slice().reverse().forEach(([k, st]) => { slideDeck.render(k, st, stage); backward.unshift(stage.innerHTML); });
  keys.forEach(([k, st]) => { slideDeck.render(k, st, off); offstage.push(off.innerHTML); });
  keys.forEach(([, st, id]) => { slideDeck.render(id, st, stage); byId.push(stage.innerHTML); });
  const idCount = keys.map(([k, st]) => { slideDeck.render(k, st, stage); return stage.querySelectorAll('[id]').length; });
  return {
    n: keys.length, expected: info.slides.reduce((n, s) => n + s.steps + 1, 0),
    forward, backward, offstage, byId, idCount,
    outsideUnchanged: outside() === before,
    textEmpty: forward.filter(h => !h.trim()).length,
  };
})()"""


@pytest.mark.parametrize("name, at_least", [("proposal.html", 10), ("motion.html", 7)])
def test_proposal_render_is_deterministic(browser, generic_dir, name, at_least):
    with generic_page(browser, generic_dir, name) as page:
        r = page.evaluate(RENDER_ALL)
    assert r["n"] == r["expected"] >= at_least                    # 全段階を描いた。1件も描いていない、という空振りを防ぐ
    assert r["textEmpty"] == 0
    assert r["forward"] == r["backward"] == r["byId"]             # 前に何を描いたか、位置か ID かに左右されない
    assert r["offstage"] == r["forward"]                          # どの描画先でも同じ
    assert r["idCount"] == [0] * r["n"]                           # 描いた中に id 属性がない
    assert r["outsideUnchanged"]                                  # 描画先の外の DOM を変えない


def test_proposal_render_steps_differ(browser, generic_dir):
    # 段階が進むと見える中身が増える（隠すのは visibility:hidden。位置は動かない）
    with generic_page(browser, generic_dir, "proposal.html") as page:
        counts = page.evaluate("""(() => {
          const stage = document.getElementById('stage');
          const visibleText = () => [...stage.querySelectorAll('li')]
            .filter(el => getComputedStyle(el).visibility !== 'hidden').length;
          return ['p02', 'p05'].map(id => {
            const s = slideDeck.info.slides.find(x => x.id === id);
            const out = [];
            for (let st = 0; st <= s.steps; st++) { slideDeck.render(id, st, stage); out.push(visibleText()); }
            return out;
          });
        })()""")
    for c in counts:
        assert c == sorted(c) and c[0] < c[-1], c


LINK_ELEMENTS = """(() => {
  const stage = document.getElementById('stage');
  const out = {};
  slideDeck.info.slides.forEach((s, k) => {
    out[s.id] = [];
    for (let st = 0; st <= s.steps; st++) {
      slideDeck.render(k, st, stage);
      out[s.id].push([...stage.querySelectorAll('[data-link]')].map(el => ({
        n: el.getAttribute('data-link'), text: el.textContent,
        visible: getComputedStyle(el).visibility !== 'hidden',
      })));
    }
  });
  return out;
})()"""


def test_proposal_link_elements(browser, generic_dir):
    with generic_page(browser, generic_dir, "proposal.html") as page:
        els = page.evaluate(LINK_ELEMENTS)
        info = page.evaluate("slideDeck.info")
    links = {s["id"]: s.get("links") or [] for s in info["slides"]}
    # p04：5つのリンクすべてに、スライドの上の場所（data-link の要素）がある
    p04 = els["p04"][-1]
    assert sorted(e["n"] for e in p04) == ["0", "1", "2", "3", "4"] and len(links["p04"]) == 5
    assert all(e["visible"] for e in p04)
    # p06：番号 0 は場所なし、壊れたリンクと許可しない種類のリンクは場所あり、範囲外の 9 がある
    numbers = sorted(e["n"] for e in els["p06"][-1])
    assert len(links["p06"]) == 3 and "9" in numbers
    placed = [int(n) for n in numbers if int(n) < 3]
    assert placed and len(placed) == 2                               # 3つのうち場所があるのは2つ
    unplaced = ({0, 1, 2} - set(placed)).pop()
    assert (links["p06"][unplaced]["kind"], links["p06"][unplaced]["target"]) == ("jump", "p01")
    assert {links["p06"][i]["target"] for i in placed} == {"p99", "javascript:alert(1)"}
    # p05：段階2から見える（0・1 では隠れている）
    by_step = [[e["visible"] for e in step] for step in els["p05"]]
    assert by_step == [[False], [False], [True], [True]]
    # 範囲外の番号はほかのスライドにない
    for sid, steps in els.items():
        for step in steps:
            for e in step:
                assert int(e["n"]) < len(links[sid]) or sid == "p06", (sid, e)


def test_render_inserts_text_safely(browser, generic_dir):
    # 題名・項目の文字は HTML として解釈しない（約束 §2.3）。[[ラベル]] だけが、作った側が付ける link の印になる
    with generic_page(browser, generic_dir, "minimal.html") as page:
        r = page.evaluate("""(() => {
          const evil = '<img src=x onerror="window.__pwned = 1"><script>window.__pwned = 2<\\/script>';
          const deck = GenericSlides.createDeck({
            id: 'evil', title: evil,
            slides: [
              { id: 'e1', type: 'title', title: evil, subtitle: evil },
              { id: 'e2', type: 'bullets', title: evil, items: [evil, 'a [[<b>x</b>]] b', 'c [[リンク]] d'],
                links: [{ label: 'リンク', kind: 'jump', target: 'e1' }, { label: '<b>x</b>', kind: 'more', text: evil }] },
              { id: 'e3', type: 'two', title: evil, left: { heading: evil, items: [evil] }, right: { heading: evil, items: [evil] } },
              { id: 'e4', type: 'points', title: evil, items: [{ text: evil, sub: evil }] },
              { id: 'e5', type: 'stat', title: evil, items: [{ value: evil, label: evil, sub: evil }] },
              { id: 'e6', type: 'bars', title: evil, max: 1, items: [{ label: evil, value: 1, display: evil }] },
              { id: 'e7', type: 'flow', title: evil, rows: [{ nodes: [{ t: evil, s: evil }, { t: evil }], arrows: [{ text: evil }] }] },
            ],
          });
          const target = document.createElement('div');
          target.className = 'sp-target';
          document.body.appendChild(target);
          const out = [];
          deck.info.slides.forEach((s, k) => {
            deck.render(k, 0, target);
            out.push({
              img: target.querySelectorAll('img, script, b').length,
              text: target.textContent.includes(evil),
              links: [...target.querySelectorAll('[data-link]')].map(el => [el.getAttribute('data-link'), el.textContent]),
            });
          });
          return { out, title: deck.info.title };
        })()""")
        page.wait_for_timeout(200)                                # 画像の onerror などが遅れて動いても見つかるように待つ
        pwned = page.evaluate("window.__pwned !== undefined")
    assert not pwned
    assert all(o["img"] == 0 for o in r["out"])
    assert all(o["text"] for o in r["out"])                   # 文字としてそのまま出ている
    assert r["out"][1]["links"] == [["1", "<b>x</b>"], ["0", "リンク"]]
    assert r["title"] == '<img src=x onerror="window.__pwned = 1"><script>window.__pwned = 2</script>'
