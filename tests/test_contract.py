"""約束の形（CONTRACT.md §2.2〜2.5、§3.1）の試験：window.slideDeck、renderSlide、deckInfo。

試験台は講座の形の見本（course_dir。tests/conftest.py が作る ch-01〜ch-07）。
"""
import json

import pytest

from helpers import evaluate, open_deck, assert_no_page_errors


def test_slidedeck_info_shape(browser, course_dir):
    info = evaluate(browser, course_dir, 1, "slideDeck.info")
    assert info["id"] == "ch-01" and info["home"] == "../index.html" and info["label"] == "第1章"
    assert [s["id"] for s in info["slides"]][:3] == ["s01", "s02", "s03"]
    assert all("==" not in s["title"] and "**" not in s["title"] and "<br" not in s["title"] for s in info["slides"])
    assert all(isinstance(s["steps"], int) and s["steps"] >= 0 for s in info["slides"])


# 同じスライドを位置と ID で描き、#stage の innerHTML を比べる（全段階）
RENDER_BY_ID_AND_INDEX = """(() => {
  const stage = document.getElementById('stage');
  const mismatches = [];
  let compared = 0;
  slideDeck.info.slides.forEach((s, k) => {
    for (let st = 0; st <= s.steps; st++) {
      slideDeck.render(k, st, stage);
      const byIndex = stage.innerHTML;
      slideDeck.render(s.id, st, stage);
      if (stage.innerHTML !== byIndex) mismatches.push(s.id + '@' + st);
      compared++;
    }
  });
  const expected = slideDeck.info.slides.reduce((n, s) => n + s.steps + 1, 0);
  return { compared, expected, mismatches };
})()"""


@pytest.mark.parametrize("ch", range(1, 8))
def test_render_by_id_equals_render_by_index(browser, course_dir, ch):
    r = evaluate(browser, course_dir, ch, RENDER_BY_ID_AND_INDEX)
    assert r["mismatches"] == []
    assert r["compared"] == r["expected"] > 0     # 1件も比べていない、という空振りを防ぐ


@pytest.mark.parametrize("ref", ["nope", "S01", 99, -1])
def test_render_unknown_ref_throws_japanese_error(browser, course_dir, ref):
    r = evaluate(browser, course_dir, 1, f"""(() => {{
      const stage = document.getElementById('stage');
      slideDeck.render('s01', 0, stage);
      const before = stage.innerHTML;
      let err = null;
      try {{ slideDeck.render({json.dumps(ref)}, 0, stage); }} catch (e) {{ err = {{ name: e.name, message: e.message }}; }}
      return {{ err, unchanged: stage.innerHTML === before }};
    }})()""")
    assert r["err"] is not None, "存在しないスライドを指しても例外にならなかった"
    assert r["err"]["name"] == "Error"                                # TypeError ではない
    assert "スライド" in r["err"]["message"] and str(ref) in r["err"]["message"]
    assert r["unchanged"]                                             # 失敗しても描画先は触らない


@pytest.mark.parametrize("render", [True, False])
def test_player_defines_functions_and_render_class(browser, course_dir, render):
    page = open_deck(browser, course_dir, 1, render=render)
    try:
        got = page.evaluate("({ cls: document.body.classList.contains('render'), fns: [typeof renderSlide, typeof deckInfo] })")
        assert_no_page_errors(page)
    finally:
        page.close()
    assert got == {"cls": render, "fns": ["function", "function"]}    # ?render のときだけ class。関数はどちらでも定義される
