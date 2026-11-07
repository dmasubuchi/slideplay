"""プレイヤーの骨組み（舞台の置き方、規定の順序、Shift の移動、Home・End、hash の読み書き）の試験。

見るのは player.js の外から見える動きだけ：キー操作、URL の hash、試験用の窓口 window.__sp（通常の表示のときだけ）。
汎用の見本（proposal）と、講座の形の見本の第1章（course_dir。tests/conftest.py が作る）で確かめる。
"""
import json
from pathlib import Path

import pytest

from helpers import page_session, slides_url

REPO = Path(__file__).resolve().parents[1]
PLAYER_JS = REPO / "player" / "player.js"


# ---- 試験の道具 ----

def proposal_url(generic_dir, suffix=""):
    return (generic_dir / "proposal.html").as_uri() + suffix


@pytest.fixture(params=["proposal", "course-ch01"])
def deck_url(request, generic_dir):
    """通常の表示で開くデッキの URL（汎用の見本の提案書と、講座の形の見本の第1章）。"""
    if request.param == "proposal":
        return proposal_url(generic_dir)
    return slides_url(request.getfixturevalue("course_dir"), 1, render=False)


def where(page):
    """今のスライドの (ID, 段階)。"""
    s = page.evaluate("__sp.state()")
    return s["id"], s["step"]


def press(page, key):
    page.keyboard.press(key)
    return where(page)


def toast_text(page):
    """画面に出ている知らせの文字（なければ None）。"""
    el = page.query_selector(".sp-toast")
    return el.inner_text() if el else None


def all_positions(info):
    """規定の順序で並べた (ID, 段階) の一覧。"""
    return [(s["id"], st) for s in info for st in range(s["steps"] + 1)]


def write_variant(tmp_path, generic_dir, name, edit):
    """proposal.html を一時フォルダーに写し、edit(html) で書き換えたものの URL を返す。

    相対パスの読み込みは、元の場所を指す file:// の絶対パスに直す（写しだけで開けるように）。
    """
    html = (generic_dir / "proposal.html").read_text(encoding="utf-8")
    html = html.replace('src="render.js"', f'src="{(generic_dir / "render.js").as_uri()}"')
    html = html.replace('src="../../player/player.js"', f'src="{PLAYER_JS.as_uri()}"')
    html = edit(html)
    path = tmp_path / name
    path.write_text(html, encoding="utf-8")
    return path.as_uri()


def player_tag():
    return f'<script src="{PLAYER_JS.as_uri()}"></script>'


def freeze_clock(page):
    """偽の時計を入れて止める（進めるのは run_for だけ。本物の時間が混ざらないので、秒数の境目の試験がぶれない）。"""
    page.clock.install(time=1_000)
    page.clock.pause_at(2_000)


def write_deck_page(tmp_path, name, slides, render_body):
    """プレイヤーを読み込む小さなデッキのページを一時フォルダーに作り、URL を返す。

    slides：slideDeck.info.slides の中身（そのまま JSON にする。壊れた値を入れて試すため、形の検査はしない）。
    render_body：render(ref, step, target) の本体（JavaScript）。
    """
    html = f"""<!doctype html><html lang="ja"><head><meta charset="utf-8"><title>t</title>
<style>.sp-target {{ position: relative; width: 1920px; height: 1080px; overflow: hidden; background: #fff; font: 64px sans-serif; }}</style>
</head><body><div id="stage" class="sp-target"></div>
<script>
window.slideDeck = {{ contract: 1, info: {{ id: "t", title: "t", slides: {json.dumps(slides, ensure_ascii=False)} }},
  render(ref, step, target) {{ {render_body} }} }};
</script>{player_tag()}</body></html>"""
    path = tmp_path / name
    path.write_text(html, encoding="utf-8")
    return path.as_uri()


# 番号か ID で引いて、「ID 段階」の文字を描くだけの render（壊れた値のデッキでも描ける）
PLAIN_RENDER = """
  const slides = window.slideDeck.info.slides;
  const k = typeof ref === 'string' ? slides.findIndex(s => s.id === ref) : ref;
  target.textContent = 'slide ' + slides[k].id + ' step ' + step;
"""
# 2枚目（位置 1）だけ例外を投げる render
THROWS_ON_SECOND = "if (ref === 1 || ref === 'b') throw new Error('壊れたスライド');" + PLAIN_RENDER


# ---- 規定の順序 ----

def test_order_with_steps(browser, generic_dir):
    with page_session(browser, proposal_url(generic_dir)) as page:
        seq = [where(page)]
        for _ in range(7):
            seq.append(press(page, "ArrowDown"))
    # p03b は段階が1つある（右の列が段階1で出る）ので、p03b の段階0・1 の両方を通ってから p04 へ進む
    assert seq == [("p01", 0), ("p02", 0), ("p02", 1), ("p02", 2), ("p03", 0), ("p03b", 0), ("p03b", 1), ("p04", 0)]


@pytest.mark.parametrize("key", ["ArrowDown", "PageDown", "Space"])
def test_next_keys(browser, generic_dir, key):
    with page_session(browser, proposal_url(generic_dir, "#p02")) as page:
        assert press(page, key) == ("p02", 1)
        assert press(page, key) == ("p02", 2)
        assert press(page, key) == ("p03", 0)


@pytest.mark.parametrize("key", ["ArrowUp", "PageUp"])
def test_previous_keys(browser, generic_dir, key):
    with page_session(browser, proposal_url(generic_dir, "#p02.2")) as page:
        assert press(page, key) == ("p02", 1)
        assert press(page, key) == ("p02", 0)
        assert press(page, key) == ("p01", 0)


def test_up_goes_to_previous_last_step(browser, generic_dir):
    with page_session(browser, proposal_url(generic_dir, "#p03")) as page:
        assert press(page, "ArrowUp") == ("p02", 2)
    with page_session(browser, proposal_url(generic_dir, "#p06")) as page:
        assert press(page, "ArrowUp") == ("p05", 3)
    with page_session(browser, proposal_url(generic_dir, "#p04")) as page:
        assert press(page, "ArrowUp") == ("p03b", 1)


def test_full_walk_down_and_up(browser, deck_url):
    # 全スライドの全段階を ↓ で順にたどり、最後でさらに ↓ を押しても動かない。↑ で逆にたどって先頭に戻る
    with page_session(browser, deck_url) as page:
        expected = all_positions(page.evaluate("deckInfo()"))
        assert len(set(expected)) == len(expected)
        assert len(expected) > len({i for i, _ in expected}) > 1        # 段階を持つスライドがある
        assert where(page) == expected[0]
        walked = [press(page, "ArrowDown") for _ in expected[1:]]
        assert walked == expected[1:]
        assert press(page, "ArrowDown") == expected[-1]
        assert toast_text(page)
        back = [press(page, "ArrowUp") for _ in expected[1:]]
        assert back == expected[-2::-1]
        assert press(page, "ArrowUp") == expected[0]


# ---- Shift の移動、Home・End ----

def test_shift_moves_by_slide(browser, generic_dir):
    with page_session(browser, proposal_url(generic_dir, "#p02.1")) as page:
        assert press(page, "Shift+ArrowDown") == ("p03", 0)
    with page_session(browser, proposal_url(generic_dir, "#p05")) as page:
        assert press(page, "Shift+ArrowUp") == ("p04", 0)
    with page_session(browser, proposal_url(generic_dir, "#p06")) as page:
        assert press(page, "Shift+ArrowUp") == ("p05", 3)          # 段階が多いスライドは、最後の段階へ
        assert press(page, "Shift+ArrowUp") == ("p04", 0)
    with page_session(browser, proposal_url(generic_dir, "#p05.2")) as page:
        assert press(page, "Shift+ArrowDown") == ("p06", 0)        # 段階の途中からでも、次のスライドの段階0


def test_shift_walk(browser, deck_url):
    with page_session(browser, deck_url) as page:
        info = page.evaluate("deckInfo()")
        down = [press(page, "Shift+ArrowDown") for _ in info[1:]]
        assert down == [(s["id"], 0) for s in info[1:]]
        assert press(page, "Shift+ArrowDown") == (info[-1]["id"], 0)      # 最後のスライドでは動かない
        assert toast_text(page)
        up = [press(page, "Shift+ArrowUp") for _ in info[1:]]
        assert up == [(s["id"], s["steps"]) for s in reversed(info[:-1])]
        assert press(page, "Shift+ArrowUp") == (info[0]["id"], info[0]["steps"])
        assert toast_text(page)


def test_home_end(browser, generic_dir):
    with page_session(browser, proposal_url(generic_dir, "#p03")) as page:
        assert press(page, "End") == ("p08", 0)
        assert press(page, "Home") == ("p01", 0)
    with page_session(browser, proposal_url(generic_dir, "#p05.2")) as page:
        assert press(page, "Home") == ("p01", 0)


def test_home_end_at_edges_toast(browser, generic_dir):
    with page_session(browser, proposal_url(generic_dir)) as page:
        assert press(page, "Home") == ("p01", 0)
        assert toast_text(page)
    with page_session(browser, proposal_url(generic_dir, "#p08")) as page:
        assert press(page, "End") == ("p08", 0)
        assert toast_text(page)


def test_edges_toast(browser, generic_dir):
    # 知らせは 2.5 秒出て消える。時間は偽の時計で進める（実時間に頼らない）
    with page_session(browser, proposal_url(generic_dir)) as page:
        freeze_clock(page)
        assert toast_text(page) is None
        assert press(page, "ArrowUp") == ("p01", 0)
        assert toast_text(page) == "最初のスライドです"
        page.clock.run_for(2400)
        assert toast_text(page) == "最初のスライドです"             # 2.5 秒の前は出たまま
        page.clock.run_for(200)                                    # 合わせて 2.6 秒
        assert toast_text(page) is None                            # 消えている（消すのは時計の動きの中で同期に行われる）
    with page_session(browser, proposal_url(generic_dir, "#p08")) as page:
        assert press(page, "ArrowDown") == ("p08", 0)
        assert toast_text(page)


def test_single_slide_deck(browser, generic_dir):
    # 1枚だけのデッキ（minimal）：どのキーでも動かず、知らせるだけ
    with page_session(browser, (generic_dir / "minimal.html").as_uri()) as page:
        for key in ["ArrowDown", "ArrowUp", "Shift+ArrowDown", "Shift+ArrowUp", "End", "Home", "PageDown", "Space"]:
            assert press(page, key) == ("m1", 0), key
        assert toast_text(page)


# ---- hash の読み書き ----

def test_hash_written_and_read(browser, generic_dir):
    with page_session(browser, proposal_url(generic_dir)) as page:
        press(page, "ArrowDown")
        press(page, "ArrowDown")
        assert page.evaluate("location.hash") == "#p02.1"
        press(page, "ArrowUp")
        assert page.evaluate("location.hash") == "#p02"             # 段階0は ID だけ
    with page_session(browser, proposal_url(generic_dir, "#p05.2")) as page:
        assert where(page) == ("p05", 2)
        assert page.evaluate("location.hash") == "#p05.2"
    with page_session(browser, proposal_url(generic_dir, "#p05.9")) as page:
        assert where(page) == ("p05", 3)                           # 範囲の外の段階は最後の段階にそろえる
        assert page.evaluate("location.hash") == "#p05.3"
    with page_session(browser, proposal_url(generic_dir, "#3.0")) as page:
        assert where(page) == ("p03", 0)                           # 旧形式（1から数えた位置）
        assert page.evaluate("location.hash") == "#p03"
    with page_session(browser, proposal_url(generic_dir, "#p03b")) as page:
        assert where(page) == ("p03b", 0)


def test_no_hash_opens_first(browser, deck_url):
    with page_session(browser, deck_url) as page:
        first = page.evaluate("deckInfo()[0].id")
        assert where(page) == (first, 0)
        assert toast_text(page) is None                            # 知らせない
        assert page.evaluate("location.hash") == "#" + first       # 今の場所を URL に書く


@pytest.mark.parametrize("bad", ["#nope", "#p02.x", "#0.0", "#99", "#%E0%A4%A", "#P01", "#p02.", "#p02.1.2", "#-1"])
def test_bad_hash_opens_first(browser, generic_dir, bad):
    with page_session(browser, proposal_url(generic_dir, bad)) as page:
        assert where(page) == ("p01", 0)
        assert toast_text(page)
        assert page.evaluate("location.hash") == "#p01"


def test_bad_hash_on_course_deck(browser, course_dir):
    with page_session(browser, slides_url(course_dir, 1, render=False) + "#nope") as page:
        assert where(page) == (page.evaluate("deckInfo()[0].id"), 0)
        assert toast_text(page)


def test_hash_change_in_page(browser, generic_dir):
    # アドレス欄で hash だけを変えたとき（hashchange）も、同じ決まりで読む
    with page_session(browser, proposal_url(generic_dir)) as page:
        page.evaluate("location.hash = '#p05.2'")
        page.wait_for_function("__sp.state().id === 'p05'")
        assert where(page) == ("p05", 2)
        page.evaluate("location.hash = '#nope'")
        page.wait_for_function("__sp.state().id === 'p01'")
        assert where(page) == ("p01", 0)
        assert toast_text(page)


PARSE_CASES = [
    # (hash, 期待する結果)
    ("", {"kind": "none"}),
    ("#", {"kind": "none"}),
    ("#p01", {"kind": "ok", "index": 0, "step": 0}),
    ("#p02.1", {"kind": "ok", "index": 1, "step": 1}),
    ("#p02.0", {"kind": "ok", "index": 1, "step": 0}),
    ("#p02.9", {"kind": "ok", "index": 1, "step": 2}),                       # 大きければ steps にそろえる
    ("#p02.99999999999999999999", {"kind": "ok", "index": 1, "step": 2}),
    ("#p01.5", {"kind": "ok", "index": 0, "step": 0}),                       # 段階のないスライド
    ("#p03b", {"kind": "ok", "index": 3, "step": 0}),
    ("#p%30%32.1", {"kind": "ok", "index": 1, "step": 1}),                   # パーセント表記は戻して読む
    ("#1", {"kind": "ok", "index": 0, "step": 0}),                           # 旧形式
    ("#3.0", {"kind": "ok", "index": 2, "step": 0}),
    ("#9", {"kind": "ok", "index": 8, "step": 0}),
    ("#6.9", {"kind": "ok", "index": 5, "step": 3}),
    ("#03", {"kind": "ok", "index": 2, "step": 0}),
    ("#0", {"kind": "bad"}), ("#0.0", {"kind": "bad"}), ("#10", {"kind": "bad"}), ("#99", {"kind": "bad"}),
    ("#99999999999999999999", {"kind": "bad"}),
    ("#nope", {"kind": "bad"}), ("#p99", {"kind": "bad"}), ("#P01", {"kind": "bad"}),
    ("#p02.x", {"kind": "bad"}), ("#p02.", {"kind": "bad"}), ("#p02.1.2", {"kind": "bad"}), ("#p02.-1", {"kind": "bad"}),
    ("#-1", {"kind": "bad"}), ("#3.x", {"kind": "bad"}), ("#1.5.2", {"kind": "bad"}),
    ("#%E0%A4%A", {"kind": "bad"}), ("#%", {"kind": "bad"}), ("#p 01", {"kind": "bad"}), ("#日本語", {"kind": "bad"}),
    ("p02", {"kind": "bad"}),                                                  # # のない文字は hash ではない
]


def test_parse_hash(browser, generic_dir):
    with page_session(browser, proposal_url(generic_dir)) as page:
        got = page.evaluate(
            "(cases) => cases.map(h => __sp.parseHash(h, slideDeck.info.slides))", [h for h, _ in PARSE_CASES])
    for (h, want), have in zip(PARSE_CASES, got):
        assert have == want, h


def test_format_hash(browser, generic_dir):
    with page_session(browser, proposal_url(generic_dir)) as page:
        got = page.evaluate("[['p02', 0], ['p02', 3], ['p03b', 1], ['s01', 12]].map(([id, st]) => __sp.formatHash(id, st))")
    assert got == ["#p02", "#p02.3", "#p03b.1", "#s01.12"]


def test_hash_rewritten_only_when_changed(browser, generic_dir):
    # 読んだ hash がそのままの形なら、URL を書き換えない。形が違うときだけ書き換える
    spy = """
      window.__urlWrites = [];
      const orig = history.replaceState.bind(history);
      history.replaceState = (state, title, url) => {
        const before = location.href;
        const r = orig(state, title, url);
        if (location.href !== before) window.__urlWrites.push(location.hash);
        return r;
      };
    """
    with page_session(browser, proposal_url(generic_dir, "#p05.2")) as page:
        page.add_init_script(spy)
        page.reload()
        assert where(page) == ("p05", 2)
        assert page.evaluate("__urlWrites") == []                   # 書き換えなし
        press(page, "ArrowDown")
        assert page.evaluate("__urlWrites") == ["#p05.3"]
    with page_session(browser, "about:blank") as page:
        page.add_init_script(spy)
        page.goto(proposal_url(generic_dir, "#p05.9"))
        assert page.evaluate("__urlWrites") == ["#p05.3"]           # 範囲の外の段階を直した


def test_history_not_grown(browser, generic_dir):
    # hash の書き換えは履歴の件数を増やさない
    with page_session(browser, proposal_url(generic_dir)) as page:
        before = page.evaluate("history.length")
        for _ in range(5):
            press(page, "ArrowDown")
        assert page.evaluate("history.length") == before


def test_replace_state_failure_is_harmless(browser, generic_dir):
    # history.replaceState が使えなくても、表示と移動は続く
    with page_session(browser, proposal_url(generic_dir, "#p02")) as page:
        page.add_init_script("history.replaceState = () => { throw new DOMException('拒否', 'SecurityError'); };")
        page.reload()
        assert where(page) == ("p02", 0)
        assert press(page, "ArrowDown") == ("p02", 1)
        assert press(page, "End") == ("p08", 0)


# ---- 壊れた中身（描画の例外、steps の欠け、形に合わない ID） ----

def test_render_exception_shows_placeholder_and_deck_keeps_moving(browser, tmp_path):
    # 2枚目の render が例外を投げても、舞台に代わりの表示を出し、場所は通常どおり進む。pageerror は出ない（page_session が確かめる）
    slides = [{"id": "a", "title": "A", "steps": 1}, {"id": "b", "title": "B", "steps": 0}, {"id": "c", "title": "C", "steps": 0}]
    url = write_deck_page(tmp_path, "broken.html", slides, THROWS_ON_SECOND)
    placeholder = "このスライドは表示できません（b）"
    with page_session(browser, url) as page:
        warnings = []
        page.on("console", lambda m: warnings.append(m.text) if m.type == "warning" else None)
        assert where(page) == ("a", 0)
        assert press(page, "ArrowDown") == ("a", 1)
        assert press(page, "ArrowDown") == ("b", 0)                # ↓ で2枚目へ（例外で止まらない）
        assert page.inner_text("#stage") == placeholder
        assert toast_text(page) == placeholder
        assert page.evaluate("location.hash") == "#b"
        assert page.text_content(".sp-pos") == "2 / 3"
        assert [i["ref"] for i in page.evaluate("__sp.places()")["items"]] == ["a", "b"]
        assert any("b" in w for w in warnings), warnings           # console.warn
        assert press(page, "ArrowDown") == ("c", 0)                # そのスライドを越えて進める
        assert page.inner_text("#stage") == "slide c step 0"      # 代わりの表示は残らない
        assert press(page, "ArrowUp") == ("b", 0)
        assert page.inner_text("#stage") == placeholder
        assert press(page, "ArrowUp") == ("a", 1)
        # Shift＋↓・Shift＋↑ でも越えられる
        assert press(page, "Home") == ("a", 0)
        assert press(page, "Shift+ArrowDown") == ("b", 0)
        assert press(page, "Shift+ArrowDown") == ("c", 0)
        assert press(page, "Shift+ArrowUp") == ("b", 0)
        # URL（hash）で来ても越えられる
        page.evaluate("location.hash = '#c'")
        page.wait_for_function("__sp.state().id === 'c'")
        page.evaluate("location.hash = '#b'")
        page.wait_for_function("__sp.state().id === 'b'")
        assert page.inner_text("#stage") == placeholder
        assert press(page, "Shift+ArrowDown") == ("c", 0)


def test_render_exception_on_first_load_from_url(browser, tmp_path):
    slides = [{"id": "a", "title": "A"}, {"id": "b", "title": "B"}, {"id": "c", "title": "C"}]
    url = write_deck_page(tmp_path, "broken2.html", slides, THROWS_ON_SECOND)
    with page_session(browser, url + "#b") as page:
        assert where(page) == ("b", 0)
        assert page.inner_text("#stage") == "このスライドは表示できません（b）"
        assert press(page, "ArrowDown") == ("c", 0)
        assert press(page, "ArrowUp") == ("b", 0)
        assert press(page, "ArrowUp") == ("a", 0)


def test_steps_are_normalized(browser, tmp_path):
    # steps のない・数でない・負の値は 0、小数は切り捨て。URL に NaN が出ない
    slides = [{"id": "a1", "title": "1"}, {"id": "a2", "title": "2", "steps": "x"}, {"id": "a3", "title": "3", "steps": -2},
              {"id": "a4", "title": "4", "steps": 1.7}, {"id": "a5", "title": "5", "steps": None}]
    url = write_deck_page(tmp_path, "steps.html", slides, PLAIN_RENDER)
    with page_session(browser, url) as page:
        walked, hashes = [], []
        for _ in range(6):
            walked.append(press(page, "ArrowDown"))
            hashes.append(page.evaluate("location.hash"))
        assert walked == [("a2", 0), ("a3", 0), ("a4", 0), ("a4", 1), ("a5", 0), ("a5", 0)]
        assert hashes == ["#a2", "#a3", "#a4", "#a4.1", "#a5", "#a5"]
        assert "NaN" not in page.text_content(".sp-pos")
        assert press(page, "ArrowUp") == ("a4", 1)                 # 小数の steps は切り捨てた 1 が最後の段階
        assert press(page, "Shift+ArrowUp") == ("a3", 0)
        assert press(page, "Shift+ArrowDown") == ("a4", 0)
    with page_session(browser, url + "#a4.9") as page:
        assert where(page) == ("a4", 1)                            # 範囲の外の段階は切り捨てたあとの最後の段階にそろう


def test_bad_and_duplicate_ids_warn(browser, tmp_path):
    slides = [{"id": "a1", "title": "1"}, {"id": "bad id", "title": "2"}, {"id": "a1", "title": "3"}, {"id": "9x", "title": "4"}]
    url = write_deck_page(tmp_path, "ids.html", slides, PLAIN_RENDER)
    with page_session(browser, "about:blank") as page:
        warnings = []
        page.on("console", lambda m: warnings.append(m.text) if m.type == "warning" else None)
        page.goto(url)
        page.wait_for_function("!!window.__sp")
        text = "\n".join(warnings)
        assert "bad id" in text and "9x" in text                   # 形に合わない ID
        assert text.count("a1") >= 1 and "重複" in text            # 重複した ID
        assert where(page) == ("a1", 0)                            # 警告だけで、表示と移動は続く
        assert press(page, "End") == ("9x", 0)


def test_bad_id_slide_is_not_recorded_in_places(browser, tmp_path):
    # 形に合わない ID のスライドを通っても、直近の場所の並びは壊れない（並び全体が捨てられない）。再読み込みのあとも残る
    slides = [{"id": "a1", "title": "1"}, {"id": "bad id", "title": "2"}, {"id": "a3", "title": "3"}]
    url = write_deck_page(tmp_path, "badid.html", slides, PLAIN_RENDER)
    refs = lambda page: [i["ref"] for i in page.evaluate("__sp.places()")["items"]]
    with page_session(browser, url) as page:
        assert press(page, "ArrowDown") == ("bad id", 0)
        assert page.inner_text("#stage") == "slide bad id step 0"
        assert page.evaluate("location.hash") == "#2"              # ID の形でないので、位置で書く（再読み込みで同じスライドが開く）
        assert refs(page) == ["a1"] and page.evaluate("__sp.places().pos") == 0     # 記録しない
        page.reload()                                              # そのスライドで再読み込み
        assert where(page) == ("bad id", 0) and toast_text(page) is None
        assert refs(page) == ["a1"]
        assert press(page, "ArrowDown") == ("a3", 0)
        assert refs(page) == ["a1", "a3"] and page.evaluate("__sp.places().pos") == 1
        page.reload()
        assert where(page) == ("a3", 0)
        assert refs(page) == ["a1", "a3"] and page.evaluate("__sp.places().pos") == 1      # 並びが保たれている
        assert press(page, "ArrowLeft") == ("a1", 0)


# ---- 舞台の置き方 ----

@pytest.mark.parametrize("viewport", [(1440, 900), (1000, 700), (1180, 820), (820, 1180), (1920, 1080), (640, 300)])
def test_stage_fits(browser, deck_url, viewport):
    w, h = viewport
    with page_session(browser, deck_url, viewport=viewport) as page:
        rect = page.evaluate("(() => { const r = document.getElementById('stage').getBoundingClientRect(); return {x: r.x, y: r.y, w: r.width, h: r.height}; })()")
        k = min(w / 1920, h / 1080)
        assert rect["w"] == pytest.approx(1920 * k, abs=0.5) and rect["h"] == pytest.approx(1080 * k, abs=0.5)
        assert rect["x"] == pytest.approx((w - rect["w"]) / 2, abs=0.5)        # 中央
        assert rect["y"] == pytest.approx((h - rect["h"]) / 2, abs=0.5)
        assert max(rect["w"] - w, rect["h"] - h) <= 0.5 and (abs(rect["w"] - w) <= 0.5 or abs(rect["h"] - h) <= 0.5)     # 最大
        scroll = page.evaluate("({sw: document.documentElement.scrollWidth, sh: document.documentElement.scrollHeight, "
                               "bh: document.body.scrollHeight, iw: innerWidth, ih: innerHeight})")
        assert scroll["sw"] <= scroll["iw"] and scroll["sh"] <= scroll["ih"] and scroll["bh"] <= scroll["ih"]


def test_stage_fits_1440x900_exact(browser, deck_url):
    with page_session(browser, deck_url, viewport=(1440, 900)) as page:
        rect = page.evaluate("(() => { const r = document.getElementById('stage').getBoundingClientRect(); return [r.x, r.y, r.width, r.height]; })()")
        assert rect == [0, 45, 1440, 810]


def test_stage_follows_resize(browser, deck_url):
    with page_session(browser, deck_url, viewport=(1440, 900)) as page:
        page.set_viewport_size({"width": 1000, "height": 400})
        page.wait_for_function("document.getElementById('stage').getBoundingClientRect().height < 410")
        rect = page.evaluate("(() => { const r = document.getElementById('stage').getBoundingClientRect(); return [r.x, r.y, r.width, r.height]; })()")
        assert rect[3] == pytest.approx(400, abs=0.5) and rect[2] == pytest.approx(400 * 1920 / 1080, abs=0.5)
        assert rect[0] == pytest.approx((1000 - rect[2]) / 2, abs=0.5) and rect[1] == pytest.approx(0, abs=0.5)


def test_stage_is_placed_by_player(browser, deck_url):
    # 中身の CSS が #stage の位置を決めていても（講座の形の見本の章は left:50%・top:50%）、プレイヤーが style で決める
    with page_session(browser, deck_url) as page:
        got = page.evaluate("(() => { const s = document.getElementById('stage'); return {"
                            "cls: s.classList.contains('sp-target'), pos: s.style.position, tf: s.style.transform, "
                            "html: getComputedStyle(document.documentElement).overflow, body: getComputedStyle(document.body).overflow, "
                            "margin: getComputedStyle(document.body).margin}; })()")
        assert got["cls"] and got["pos"] == "absolute" and got["tf"].startswith("scale(")
        assert got["html"] == "hidden" and got["body"] == "hidden" and got["margin"] == "0px"


def test_player_adds_sp_target_class(browser, generic_dir, tmp_path):
    url = write_variant(tmp_path, generic_dir, "no-class.html",
                        lambda html: html.replace('<div id="stage" class="sp-target"></div>', '<div id="stage"></div>'))
    with page_session(browser, url, viewport=(1440, 900)) as page:
        assert page.evaluate("document.getElementById('stage').classList.contains('sp-target')")
        rect = page.evaluate("(() => { const r = document.getElementById('stage').getBoundingClientRect(); return [r.x, r.y, r.width, r.height]; })()")
        assert rect == [0, 45, 1440, 810]


# ---- キー操作の決まり ----

HANDLED = ["ArrowDown", "ArrowUp", "PageDown", "PageUp", "Space", "Home", "End", "Shift+ArrowDown", "Shift+ArrowUp"]
RECORD_PREVENTED = """
  window.__prevented = [];
  window.addEventListener('keydown', e => window.__prevented.push([e.key, e.defaultPrevented]));
"""


def test_modifier_keys_ignored(browser, generic_dir):
    with page_session(browser, proposal_url(generic_dir, "#p02")) as page:
        page.evaluate(RECORD_PREVENTED)
        for mod in ["Control", "Alt", "Meta"]:
            for key in ["ArrowDown", "ArrowUp", "PageDown", "Space", "Home", "End"]:
                assert press(page, f"{mod}+{key}") == ("p02", 0), f"{mod}+{key}"
            assert press(page, f"{mod}+Shift+ArrowDown") == ("p02", 0)
        # 修飾キーそのものと、組み合わせの押下は、ブラウザの動きを止めない
        assert not any(prevented for _, prevented in page.evaluate("__prevented"))
        # 修飾キーなしなら動く（空振りの確認）
        assert press(page, "ArrowDown") == ("p02", 1)


def test_handled_keys_prevent_default(browser, generic_dir):
    with page_session(browser, proposal_url(generic_dir, "#p03")) as page:
        page.evaluate(RECORD_PREVENTED)
        for key in HANDLED:
            page.evaluate("__prevented.length = 0")
            page.keyboard.press(key)
            assert page.evaluate("__prevented")[-1][1] is True, key       # 最後の keydown（Shift 付きなら矢印の方）が止められている
        for key in ["a", "Tab", "Enter"]:
            page.evaluate("__prevented.length = 0")
            page.keyboard.press(key)
            assert page.evaluate("__prevented")[-1][1] is False, key


def test_shift_is_for_arrows_only(browser, generic_dir):
    # Shift 付きの Space・PageDown・PageUp・Home・End は決めていない：動かず、ブラウザの動きも止めない
    with page_session(browser, proposal_url(generic_dir, "#p03")) as page:
        page.evaluate(RECORD_PREVENTED)
        for key in ["Shift+Space", "Shift+PageDown", "Shift+PageUp", "Shift+Home", "Shift+End"]:
            assert press(page, key) == ("p03", 0), key
        assert not any(prevented for _, prevented in page.evaluate("__prevented"))


def test_position_display_is_updated(browser, generic_dir):
    # 位置の表示（操作ボタンの帯の .sp-pos）は、移動のたびに更新される。
    # 操作ボタンは自動で消える（読み込み直後は見えない）ので、見えるかどうかによらない text_content で読む
    with page_session(browser, proposal_url(generic_dir, "#p03")) as page:
        assert page.text_content(".sp-pos") == "3 / 9"
        press(page, "ArrowUp")
        assert page.text_content(".sp-pos") == "2 / 9　段階 2/2"
        press(page, "End")
        assert page.text_content(".sp-pos") == "9 / 9"                      # 段階のないスライドは段階を出さない


def test_typing_in_input_ignored(browser, generic_dir):
    with page_session(browser, proposal_url(generic_dir, "#p02")) as page:
        page.evaluate("document.body.insertAdjacentHTML('beforeend', '<input id=\"t\" style=\"position:fixed;left:0;top:0\">')")
        page.focus("#t")
        for key in ["ArrowDown", "Space", "PageDown", "End"]:
            assert press(page, key) == ("p02", 0), key
        assert page.input_value("#t") == " "
        page.evaluate("document.activeElement.blur()")
        assert press(page, "ArrowDown") == ("p02", 1)


def test_stage_click_does_not_advance(browser, deck_url):
    with page_session(browser, deck_url) as page:
        before = where(page)
        page.mouse.click(720, 450)
        assert where(page) == before


# ---- ?render のときは何も変えない ----

PAGE_SNAPSHOT = """(() => {
  const st = document.getElementById('stage');
  const spRules = [];
  for (const sheet of document.styleSheets) {
    for (const r of sheet.cssRules) if (r.selectorText && /\\.sp-(?!target)/.test(r.selectorText)) spRules.push(r.selectorText);
  }
  return {
    spElements: document.querySelectorAll('[class*="sp-"]:not(.sp-target)').length,
    spRules,
    stageHtml: st.innerHTML, stageStyle: st.getAttribute('style'),
    bodyClass: document.body.className, bodyStyle: document.body.getAttribute('style'),
    htmlStyle: document.documentElement.getAttribute('style'),
    hash: location.hash, bodyChildren: document.body.children.length,
    sp: typeof window.__sp, renderSlide: typeof renderSlide, deckInfo: typeof deckInfo,
  };
})()"""


def test_render_mode_untouched(browser, deck_url):
    with page_session(browser, deck_url + "?render") as page:
        before = page.evaluate(PAGE_SNAPSHOT)
        assert before["bodyClass"].split() == ["render"]
        assert before["spElements"] == 0 and before["spRules"] == []
        assert before["sp"] == "undefined" and before["renderSlide"] == "function" and before["deckInfo"] == "function"
        assert before["stageStyle"] is None and before["bodyStyle"] is None and before["htmlStyle"] is None
        assert before["hash"] == ""
        for key in ["ArrowDown", "Space", "PageDown", "End", "Home", "Shift+ArrowDown", "ArrowUp", "o", "n", "?", "Escape"]:
            page.keyboard.press(key)
        page.evaluate("window.dispatchEvent(new Event('resize'))")
        assert page.evaluate(PAGE_SNAPSHOT) == before
        # 動画のツールが使う2つの関数は、そのまま動く
        info = page.evaluate("deckInfo()")
        assert info and all(set(s) == {"id", "steps"} for s in info)
        page.evaluate("renderSlide(1, 0)")
        assert page.evaluate("document.getElementById('stage').innerHTML.length") > 0


def test_normal_mode_has_player_parts(browser, deck_url):
    # ?render の試験が空振りでないことの確認：通常の表示では、プレイヤーの CSS と窓口がある
    with page_session(browser, deck_url) as page:
        snap = page.evaluate(PAGE_SNAPSHOT)
        assert snap["sp"] == "object" and snap["spRules"] and "render" not in snap["bodyClass"].split()
        state = page.evaluate("__sp.state()")
        assert state["kind"] == "deck" and state["index"] == 0 and state["step"] == 0 and state["id"]
        assert page.evaluate("__sp.overlay()") == "none"
        assert page.evaluate("[typeof renderSlide, typeof deckInfo]") == ["function", "function"]   # 通常の表示でも残す


# ---- 読み込みの場所と、デッキのない画面 ----

def head_variant(tmp_path, generic_dir):
    return write_variant(tmp_path, generic_dir, "head.html",
                         lambda html: html.replace(player_tag(), "").replace("<head>", "<head>\n" + player_tag(), 1))


def test_player_in_head(browser, generic_dir, tmp_path):
    url = head_variant(tmp_path, generic_dir)
    html = Path(tmp_path / "head.html").read_text(encoding="utf-8")
    assert html.index("player.js") < html.index("<body>") and html.count("player.js") == 1       # 試験用のページの作り方の確認
    # ?render：body.render が付き、2つの関数があり、プレイヤーの部品は出ない
    with page_session(browser, url + "?render") as page:
        got = page.evaluate("({render: document.body.classList.contains('render'), fns: [typeof renderSlide, typeof deckInfo], "
                            "n: deckInfo().length, sp: typeof window.__sp, parts: document.querySelectorAll('[class*=\"sp-\"]:not(.sp-target)').length})")
        assert got == {"render": True, "fns": ["function", "function"], "n": 9, "sp": "undefined", "parts": 0}
        page.evaluate("renderSlide(1, 1)")
        assert page.evaluate("document.querySelectorAll('#stage li').length") > 0
        page.keyboard.press("ArrowDown")
        assert page.evaluate("location.hash") == ""
    # 通常の表示：↓ が効く
    with page_session(browser, url) as page:
        assert where(page) == ("p01", 0)
        assert press(page, "ArrowDown") == ("p02", 0)
        assert press(page, "End") == ("p08", 0)
    with page_session(browser, url + "#p03") as page:
        assert where(page) == ("p03", 0)
        assert press(page, "ArrowDown") == ("p03b", 0)
        rect = page.evaluate("(() => { const r = document.getElementById('stage').getBoundingClientRect(); return [r.x, r.y, r.width, r.height]; })()")
        assert rect == [0, 45, 1440, 810]


def test_catalog_page_does_not_crash(browser, generic_dir):
    # 目次の画面の試験は test_catalog.py。ここでは、読み込んでも例外を出さず、デッキ用のキー（Space・End など）で何も起きないことだけ見る
    with page_session(browser, (generic_dir / "index.html").as_uri()) as page:
        assert page.evaluate("__sp.state().kind") == "catalog"
        assert page.evaluate("__sp.overlay()") == "none"
        for key in ["Space", "End", "Home", "PageDown", "PageUp", "n", "o", "l", "h"]:
            page.keyboard.press(key)
        assert page.evaluate("__sp.state()") == {"kind": "catalog", "index": 0, "step": 0, "id": "proposal"}
        assert page.evaluate("document.querySelectorAll('.sp-toast').length") == 0
        assert page.evaluate("document.querySelectorAll('.sp-notes, .sp-overview, .sp-help, .sp-linkview').length") == 0


def test_page_without_deck_does_nothing(browser, tmp_path):
    path = tmp_path / "empty.html"
    path.write_text(f'<!doctype html><html><head><meta charset="utf-8"><title>空</title></head><body><p>本文</p>{player_tag()}</body></html>',
                    encoding="utf-8")
    with page_session(browser, path.as_uri()) as page:
        got = page.evaluate("({sp: typeof window.__sp, style: document.head.querySelectorAll('style').length, "
                            "body: document.body.getAttribute('style'), html: document.documentElement.getAttribute('style'), "
                            "margin: getComputedStyle(document.body).margin})")
        assert got["sp"] == "undefined" and got["style"] == 0 and got["body"] is None and got["html"] is None
        assert got["margin"] == "8px"                               # ブラウザの既定のまま
        page.keyboard.press("ArrowDown")
        assert page.evaluate("location.hash") == ""


def test_deck_without_stage_does_nothing(browser, generic_dir, tmp_path):
    url = write_variant(tmp_path, generic_dir, "no-stage.html",
                        lambda html: html.replace('<div id="stage" class="sp-target"></div>', ""))
    with page_session(browser, url) as page:
        assert page.evaluate("typeof window.__sp") == "undefined"
        page.keyboard.press("ArrowDown")
        assert page.evaluate("location.hash") == ""
