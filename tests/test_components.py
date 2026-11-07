"""汎用の描画の部品（points・stat・bars・flow）と、動きの層が読む役目の印（data-sp-*）の試験。

見本は examples/generic/motion.html（架空の題材。m01 表紙・m02 points・m03 bars・m04 stat・m05 flow・m06 bullets）。
印は属性だけで、見た目を変えない。
"""
import pytest

from helpers import page_session

MOTION = {"send": True, "entry": "bounce", "point": True}


def motion_page(browser, generic_dir, viewport=(1440, 900)):
    return page_session(browser, (generic_dir / "motion.html").as_uri(), viewport=viewport)


def render_and(page, slide_id, step, expr):
    """メインの舞台に slide_id の step を描いて、expr（stage を使える式）を評価する。"""
    return page.evaluate(f"""(() => {{
      const stage = document.getElementById('stage');
      slideDeck.render({slide_id!r}, {step}, stage);
      return ({expr});
    }})()""")


def test_motion_deck_motion(browser, generic_dir):
    with motion_page(browser, generic_dir) as page:
        page.wait_for_function("!!window.__sp")
        assert page.evaluate("__sp.deckMotion()") == MOTION
        ids = page.evaluate("slideDeck.info.slides.map(s => s.id)")
    assert ids[:6] == ["m01", "m02", "m03", "m04", "m05", "m06"]


@pytest.mark.parametrize("values, max_value", [([40, 35, 25], 100), ([3, 1, 0], 4)])
def test_bars_are_proportional(browser, generic_dir, values, max_value):
    # 塗りの幅は value / max（0 から始める。目分量で描かない）。舞台は縮めずに測る
    with motion_page(browser, generic_dir) as page:
        page.wait_for_function("!!window.__sp")
        bars = page.evaluate("""([values, max]) => {
          const deck = GenericSlides.createDeck({ id: 'b', title: 'b', slides: [{ id: 'b1', type: 'bars', title: 'b', max,
            items: values.map((v, i) => ({ label: 'L' + i, value: v, display: String(v) })) }] });
          const target = document.createElement('div');
          target.className = 'sp-target';
          document.body.appendChild(target);
          deck.render(0, 0, target);
          return [...target.querySelectorAll('[data-sp-role="bar"]')].map(f => [f.offsetWidth, f.parentElement.clientWidth]);
        }""", [values, max_value])
    assert len(bars) == len(values)
    for (w, track), v in zip(bars, values):
        assert abs(w - track * v / max_value) <= 1, (w, track, v)


EXPECTED_ROLES = {
    "m01": {"title": 1, "sub": 1},
    "m02": {"title": 1, "card": 3},
    "m03": {"title": 1, "bar": 3},
    "m04": {"title": 1, "stat": 2, "count": 2},
    "m05": {"title": 1, "node": 3, "arrow": 2},
    "m06": {"title": 1, "item": 3},
}


@pytest.mark.parametrize("slide_id", sorted(EXPECTED_ROLES))
def test_roles_are_marked(browser, generic_dir, slide_id):
    with motion_page(browser, generic_dir) as page:
        page.wait_for_function("!!window.__sp")
        steps = page.evaluate(f"slideDeck.info.slides.find(s => s.id === {slide_id!r}).steps")
        roles = render_and(page, slide_id, steps, """[...stage.querySelectorAll('[data-sp-role]')].reduce((m, e) => {
          const r = e.getAttribute('data-sp-role'); m[r] = (m[r] || 0) + 1; return m; }, {})""")
    assert roles == EXPECTED_ROLES[slide_id]


def test_hover_groups_are_marked(browser, generic_dir):
    with motion_page(browser, generic_dir) as page:
        page.wait_for_function("!!window.__sp")
        r = {sid: render_and(page, sid, 1 if sid == "m02" else 0, """({
          groups: stage.querySelectorAll('[data-sp-group]').length,
          hovers: [...stage.querySelectorAll('[data-sp-hover]')].map(h => h.parentElement.hasAttribute('data-sp-group')) })""")
             for sid in ["m02", "m03", "m04", "m05"]}
    assert r["m02"] == {"groups": 1, "hovers": [True] * 3}
    assert r["m03"] == {"groups": 1, "hovers": [True] * 3}
    assert r["m04"] == {"groups": 1, "hovers": [True] * 2}
    assert r["m05"]["groups"] == 1 and r["m05"]["hovers"] == [True] * 3


def test_keys_pair_label_and_bar(browser, generic_dir):
    with motion_page(browser, generic_dir) as page:
        page.wait_for_function("!!window.__sp")
        keys = render_and(page, "m03", 0, """[...stage.querySelectorAll('[data-sp-key]')].reduce((m, e) => {
          const k = e.getAttribute('data-sp-key'); (m[k] = m[k] || []).push(e.getAttribute('data-sp-role') || 'label'); return m; }, {})""")
    assert keys == {"b0": ["label", "bar"], "b1": ["label", "bar"], "b2": ["label", "bar"]}


def test_step_items_hidden(browser, generic_dir):
    # step の付いた項目は、その段階より前は visibility:hidden（場所は取ったまま、位置は動かない）
    with motion_page(browser, generic_dir) as page:
        page.wait_for_function("!!window.__sp")
        assert page.evaluate("slideDeck.info.slides.find(s => s.id === 'm02').steps") == 1
        expr = """[...stage.querySelectorAll('[data-sp-role="card"]')].map(c => [getComputedStyle(c).visibility, Math.round(c.getBoundingClientRect().left)])"""
        s0, s1 = render_and(page, "m02", 0, expr), render_and(page, "m02", 1, expr)
    assert [v for v, _ in s0] == ["visible", "visible", "hidden"]
    assert [v for v, _ in s1] == ["visible"] * 3
    assert [x for _, x in s0] == [x for _, x in s1]


def test_stat_value_text(browser, generic_dir):
    with motion_page(browser, generic_dir) as page:
        page.wait_for_function("!!window.__sp")
        texts = render_and(page, "m04", 0, "[...stage.querySelectorAll('[data-sp-role=\"count\"]')].map(e => e.textContent)")
    assert texts[0] == "3,200件"


def test_unknown_type_still_throws(browser, generic_dir):
    with motion_page(browser, generic_dir) as page:
        page.wait_for_function("!!window.__sp")
        msg = page.evaluate("""(() => { try {
          GenericSlides.createDeck({ id: 'x', title: 'x', slides: [{ id: 'x1', type: 'nope', title: 'x' }] })
            .render(0, 0, document.createElement('div')); return null; } catch (e) { return e.message; } })()""")
    assert msg == "未知のスライドの種類「nope」です"


# ---- 決めた数の項目が舞台に収まる ----

FIT = """(def) => {
  const deck = GenericSlides.createDeck({ id: 'f', title: 'f', slides: [def] });
  const target = document.createElement('div');
  target.className = 'sp-target';
  document.body.appendChild(target);
  deck.render(0, 0, target);
  const box = target.getBoundingClientRect();
  const out = [];
  for (const e of target.querySelectorAll('.frame *')) {
    const r = e.getBoundingClientRect();
    if (r.width === 0) continue;
    if (r.left < box.left - 0.5 || r.right > box.right + 0.5 || r.bottom > box.bottom + 0.5) out.push(e.className + ' 舞台の外');
    if (e.scrollWidth > e.clientWidth + 1 && getComputedStyle(e).overflow !== 'visible') out.push(e.className + ' 切れ');
    if (e.children.length === 0 && e.scrollWidth > e.clientWidth + 1) out.push(e.className + ' はみ出し');
  }
  target.remove();
  return out;
}"""


@pytest.mark.parametrize("n", [1, 2, 3, 4])
def test_stat_fits_stage(browser, generic_dir, n):
    slide = {"id": "s1", "type": "stat", "title": "対応件数",
             "items": [{"value": "3,200件", "label": f"1か月の問い合わせ{i}", "sub": "見本の数字"} for i in range(n)]}
    with motion_page(browser, generic_dir) as page:
        page.wait_for_function("!!window.__sp")
        assert page.evaluate(FIT, slide) == []


@pytest.mark.parametrize("slide", [
    {"id": "p", "type": "points", "title": "5枚", "items": [{"text": "答えられる人が限られている", "sub": "詳しい人に質問が集まる"}] * 5},
    {"id": "f", "type": "flow", "title": "5つ", "rows": [{"nodes": [{"t": "担当者が確認", "s": "直してから送る"}] * 5,
                                                         "arrows": [{"text": "確認へ"}] * 4}]},
    {"id": "b", "type": "bars", "title": "棒", "max": 100,
     "items": [{"label": "くり返しの質問と個別の相談", "value": 100, "display": "100%"}] * 3},
], ids=["points5", "flow5", "bars-long-label"])
def test_components_fit_stage(browser, generic_dir, slide):
    with motion_page(browser, generic_dir) as page:
        page.wait_for_function("!!window.__sp")
        assert page.evaluate(FIT, slide) == []
