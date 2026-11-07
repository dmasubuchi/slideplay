"""直近の場所（←→）と、ページに着いたときの処理の試験（約束 §3.4）。

見るのは player.js の外から見える動きだけ：キー操作、URL、history.state、sessionStorage、試験用の窓口 window.__sp。

試験の決め事：
- 「リンクで移る」は、page.goto(URL) の普通のページの移動で代える。
  ただし「リンクの前に復元先を消す」ことそのものを見る試験（test_aborted_restore_then_link）は、本物のリンクのクリックで移る
- アドレス欄で hash だけを変えるのは、同じ URL の hash 違いへの page.goto で行う。Chromium では、同じ文書の中の移動になり、
  履歴の項目が1つ増え、その項目の state は null、popstate と hashchange が続けて起きる
  （test_address_bar_is_same_document_navigation で毎回確かめる）
- Chromium は file:// のページをページキャッシュ（bfcache）に入れない（ブラウザの戻るは読み込み直しになる）。
  本物のページキャッシュからの復帰は、127.0.0.1 の http で開く試験（test_bfcache_return_real_cache）で確かめる。
  この試験は Playwright の Chromium の完全版（python3 -m playwright install chromium）が要る。なければ skip せず失敗にする
"""
import functools
import http.server
import json
import re
import threading
from contextlib import contextmanager
from pathlib import Path

import pytest

from helpers import CHROMIUM_ARGS, page_session

REPO = Path(__file__).resolve().parents[1]
KEY = "sp-places-v1"
VID_RE = re.compile(r"^[a-z0-9]{8,16}$")

# 起きたイベントを数える（プレイヤーより先に登録される）
EVENTS = """
window.__ev = [];
addEventListener('popstate', () => __ev.push('popstate'));
addEventListener('hashchange', () => __ev.push('hashchange'));
addEventListener('pageshow', e => __ev.push(e.persisted ? 'pageshow-persisted' : 'pageshow'));
"""


# ---- 試験の道具 ----

def url_of(generic_dir, name, suffix=""):
    return (generic_dir / name).as_uri() + suffix


@contextmanager
def session(browser, url, init=None):
    """イベントを数える仕掛け（と init）を入れてから url を開く。pageerror があれば失敗（page_session）。"""
    with page_session(browser, "about:blank") as page:
        page.add_init_script(EVENTS)
        if init:
            page.add_init_script(init)
        page.goto(url)
        yield page


def where(page):
    s = page.evaluate("__sp.state()")
    return s["id"], s["step"]


def press(page, key):
    page.keyboard.press(key)
    return where(page)


def toast_text(page):
    el = page.query_selector(".sp-toast")
    return el.inner_text() if el else None


def clear_toast(page):
    """出ている知らせを消す（次の操作で知らせが出なかったことを確かめるため）。"""
    page.evaluate("(() => { const t = document.querySelector('.sp-toast'); if (t) t.remove(); })()")


def places(page):
    return page.evaluate("__sp.places()")


def listing(page):
    """並び（ref, step）と今の位置。"""
    p = places(page)
    return [(i["ref"], i["step"]) for i in p["items"]], p["pos"]


def vids(page):
    return [i["vid"] for i in places(page)["items"]]


def current_vid(page):
    p = places(page)
    return p["items"][p["pos"]]["vid"]


def stored(page):
    return page.evaluate(f"JSON.parse(sessionStorage.getItem('{KEY}'))")


def store(page, data):
    """保存した並びを直接書き換える（data が文字列ならそのまま、それ以外は JSON にして）。"""
    text = data if isinstance(data, str) else json.dumps(data)
    page.evaluate(f"t => sessionStorage.setItem('{KEY}', t)", text)


def state_vid(page):
    return page.evaluate("history.state && history.state.spVid")


def count(page, name):
    return page.evaluate(f"__ev.filter(e => e === '{name}').length")


def wait_hashchange(page, before):
    """hashchange が before 回より多く起きるまで待つ。1つのイベントの処理（数える仕掛けとプレイヤーの arrive）は
    同じタスクの中で全部終わるので、数が増えたのが見えた時点で、プレイヤーの処理も済んでいる。"""
    page.wait_for_function(f"__ev.filter(e => e === 'hashchange').length > {before}")


def address_bar(page, url):
    """アドレス欄で hash だけを変えて開く（同じ文書の中の移動）。hashchange の処理が終わるまで待つ。"""
    n = count(page, "hashchange")
    page.goto(url)
    wait_hashchange(page, n)


def browser_back(page):
    """同じ文書の中で、ブラウザの戻る。"""
    n = count(page, "hashchange")
    page.go_back()
    wait_hashchange(page, n)


def browser_forward(page):
    n = count(page, "hashchange")
    page.go_forward()
    wait_hashchange(page, n)


def link(page, url):
    """リンクで別のページを開く代わり（普通のページの移動）。"""
    page.goto(url)


def key_away(page, key):
    """別のページへ移るキーを押し、移った先の読み込みを待つ。"""
    with page.expect_navigation():
        page.keyboard.press(key)
    page.wait_for_function("!!window.__sp")


def reload_with_url(page, url_expr):
    """今の履歴項目の state を残したまま URL だけを変えて（replaceState）、再読み込みする。"""
    page.evaluate(f"history.replaceState(history.state, '', {url_expr})")
    page.reload()


# history.replaceState が呼ばれた時点の、起きたイベントの数（__ev の長さ）を記録する。
# イベントを数える仕掛け（EVENTS）より後に呼ばれたかどうかで、popstate と hashchange のどちらの処理で呼ばれたかが分かる
COUNT_REPLACE = """
window.__rs = [];
(() => {
  const orig = History.prototype.replaceState;
  History.prototype.replaceState = function (...a) { window.__rs.push(window.__ev.length); return orig.apply(this, a); };
})();
"""

# replaceState が使えない：例外を投げる、または黙って何もしない（呼び出しが間引かれた状態）
REPLACE_THROWS = "History.prototype.replaceState = function () { throw new DOMException('拒否', 'SecurityError'); };"
REPLACE_IGNORED = "History.prototype.replaceState = function () {};"


# ---- 例 ----

def test_example_9_22_23(browser, generic_dir):
    # 例：9枚目からリンクで22枚目へ、↓ で23枚目。← で22枚目、← で9枚目。→ で22枚目、→ で23枚目
    # （p04・p07・p08 で置き換え、リンクの代わりにアドレス欄で hash を変える）
    P = url_of(generic_dir, "proposal.html")
    with session(browser, P + "#p04") as page:
        address_bar(page, P + "#p07")
        assert where(page) == ("p07", 0)
        assert press(page, "ArrowDown") == ("p08", 0)
        before = vids(page)
        assert press(page, "ArrowLeft") == ("p07", 0)
        assert press(page, "ArrowLeft") == ("p04", 0)
        assert press(page, "ArrowRight") == ("p07", 0)
        assert press(page, "ArrowRight") == ("p08", 0)
        assert vids(page) == before                                   # ←→ は並びを変えない
        assert listing(page) == ([("p04", 0), ("p07", 0), ("p08", 0)], 2)


def test_example_keeps_step_left_at(browser, generic_dir):
    # ← で戻ると、離れたときの段階が出る
    P = url_of(generic_dir, "proposal.html")
    with session(browser, P + "#p05") as page:
        assert press(page, "ArrowDown") == ("p05", 1)
        assert press(page, "ArrowDown") == ("p05", 2)
        address_bar(page, P + "#p07")
        assert press(page, "ArrowDown") == ("p08", 0)
        assert press(page, "ArrowLeft") == ("p07", 0)
        assert press(page, "ArrowLeft") == ("p05", 2)
        assert page.evaluate("location.hash") == "#p05.2"
        assert press(page, "ArrowRight") == ("p07", 0)
        assert press(page, "ArrowRight") == ("p08", 0)


# ---- 並びの決まり ----

def test_step_change_updates_current(browser, generic_dir):
    with session(browser, url_of(generic_dir, "proposal.html", "#p02")) as page:
        first = vids(page)
        assert press(page, "ArrowDown") == ("p02", 1)
        assert press(page, "ArrowDown") == ("p02", 2)
        assert listing(page) == ([("p02", 2)], 0)                     # 件数は増えず、今の場所の段階が 2
        assert vids(page) == first
        assert press(page, "ArrowUp") == ("p02", 1)
        assert listing(page) == ([("p02", 1)], 0)
        assert press(page, "ArrowDown") == ("p02", 2)
        assert press(page, "ArrowDown") == ("p03", 0)                 # 別のスライドへ移ると足す
        assert listing(page) == ([("p02", 2), ("p03", 0)], 1)


def test_step_change_keeps_forward(browser, generic_dir):
    # 段階だけが変わるときは、先の場所を捨てない
    with session(browser, url_of(generic_dir, "proposal.html", "#p01")) as page:
        press(page, "Shift+ArrowDown")
        press(page, "Shift+ArrowDown")
        before = vids(page)
        assert listing(page) == ([("p01", 0), ("p02", 0), ("p03", 0)], 2)
        assert press(page, "ArrowLeft") == ("p02", 0)
        assert press(page, "ArrowDown") == ("p02", 1)
        assert listing(page) == ([("p01", 0), ("p02", 1), ("p03", 0)], 1)
        assert vids(page) == before
        assert press(page, "ArrowRight") == ("p03", 0)
        assert press(page, "ArrowLeft") == ("p02", 1)


def test_same_slide_again_is_not_merged(browser, generic_dir):
    # 同じスライドへもう一度来たときも、まとめずに足す
    with session(browser, url_of(generic_dir, "proposal.html")) as page:
        press(page, "ArrowDown")
        press(page, "ArrowUp")
        press(page, "ArrowDown")
        assert listing(page) == ([("p01", 0), ("p02", 0), ("p01", 0), ("p02", 0)], 3)
        assert len(set(vids(page))) == 4
        press(page, "End")
        press(page, "Home")
        assert listing(page)[0][-2:] == [("p08", 0), ("p01", 0)]


def test_cap_10(browser, generic_dir):
    # ↓ で p08 まで（9か所）、↑ で3か所（12か所）。10件だけ残り、一番古い2つが消えている
    with session(browser, url_of(generic_dir, "proposal.html")) as page:
        while where(page) != ("p08", 0):
            press(page, "ArrowDown")
        assert len(vids(page)) == 9
        first_two = vids(page)[:2]
        keep = vids(page)[2:]
        for _ in range(3):
            press(page, "ArrowUp")
        refs, pos = listing(page)
        assert refs == [("p03", 0), ("p03b", 1), ("p04", 0), ("p05", 3), ("p06", 0), ("p07", 0), ("p08", 0),
                        ("p07", 0), ("p06", 0), ("p05", 3)]
        assert pos == 9
        assert vids(page)[:7] == keep
        assert not set(first_two) & set(vids(page))
        assert len(stored(page)["items"]) == 10
        # 先頭の場所（p03）まで ← で戻れて、そこで止まる
        for _ in range(9):
            page.keyboard.press("ArrowLeft")
        assert where(page) == ("p03", 0) and listing(page)[1] == 0
        assert press(page, "ArrowLeft") == ("p03", 0)
        assert toast_text(page)


def test_truncate_forward(browser, generic_dir):
    with session(browser, url_of(generic_dir, "proposal.html", "#p06")) as page:
        press(page, "ArrowDown")
        press(page, "ArrowDown")
        old = vids(page)
        assert listing(page) == ([("p06", 0), ("p07", 0), ("p08", 0)], 2)
        assert press(page, "ArrowLeft") == ("p07", 0)
        assert press(page, "ArrowLeft") == ("p06", 0)
        assert press(page, "ArrowDown") == ("p07", 0)
        assert listing(page) == ([("p06", 0), ("p07", 0)], 1)        # 先の場所が消え、末尾が新しい場所
        new = vids(page)
        assert new[0] == old[0] and new[1] not in old
        assert press(page, "ArrowRight") == ("p08", 0)                 # もう先の場所はないので、→ は ↓ と同じ
        assert toast_text(page) is None
        assert listing(page) == ([("p06", 0), ("p07", 0), ("p08", 0)], 2)
        assert vids(page)[:2] == new                                   # 新しい場所が足されるだけで、前の場所は同じ


def test_edges(browser, generic_dir):
    # ← は先頭で動かず知らせる。→ は先の場所がないとき ↓ と同じ（知らせない）
    with session(browser, url_of(generic_dir, "proposal.html")) as page:
        length = page.evaluate("history.length")
        assert press(page, "ArrowLeft") == ("p01", 0)
        first_msg = toast_text(page)
        assert first_msg == "これより前の場所はありません"
        clear_toast(page)
        assert press(page, "ArrowRight") == ("p02", 0)                 # 先の場所がない：↓ と同じ
        assert toast_text(page) is None
        assert listing(page) == ([("p01", 0), ("p02", 0)], 1)
        assert press(page, "Shift+ArrowDown") == ("p03", 0)
        before = places(page)
        assert press(page, "ArrowLeft") == ("p02", 0)
        assert press(page, "ArrowLeft") == ("p01", 0)
        assert press(page, "ArrowLeft") == ("p01", 0)
        assert toast_text(page) == first_msg
        assert places(page)["items"] == before["items"]
        assert page.evaluate("location.hash") == "#p01"
        assert page.evaluate("history.length") == length              # ←→ は履歴を増やさない


# ---- 先の場所がないときの → は ↓ と同じ ----

def trace(page):
    """今の表示（ID・段階）、URL の hash、知らせ、直近の場所の並び（ref・段階と今の位置）。"""
    p = places(page)
    return where(page), page.evaluate("location.hash"), toast_text(page), [(i["ref"], i["step"]) for i in p["items"]], p["pos"]


def walk_to_the_end(page, key):
    """key を押し続け、最後の知らせが出るまで（さらに2回押す）の trace を押すたびに集める。"""
    traces = []
    for _ in range(100):
        page.keyboard.press(key)
        traces.append(trace(page))
        if traces[-1][2]:
            break
    assert traces[-1][2], "最後まで進まなかった"
    for _ in range(2):
        page.keyboard.press(key)
        traces.append(trace(page))
    return traces


def test_right_without_next_place_walks_like_down(browser, generic_dir):
    # 開いたばかりのデッキで → を押し続ける＝別に開いた同じデッキで ↓ を押し続ける。
    # 表示・hash・知らせ・直近の場所の並びが、最後の知らせまで毎回一致する
    P = url_of(generic_dir, "proposal.html")
    with session(browser, P) as page:
        by_down = walk_to_the_end(page, "ArrowDown")
    with session(browser, P) as page:
        by_right = walk_to_the_end(page, "ArrowRight")
    assert by_right == by_down
    shown = [t[0] for t in by_right]
    assert ("p02", 1) in shown and ("p05", 2) in shown                 # 段階も1つずつ進む（スライドを飛ばない）
    assert [t[2] for t in by_right if t[2]] == ["最後のスライドです"] * 3        # 知らせは ↓ と同じ。「これより先の場所はありません」ではない
    assert by_right[-1][0] == by_right[-3][0] and by_right[-1][3:] == by_right[-3][3:]     # 最後は動かない
    refs, pos = by_right[-1][3:]
    assert len(refs) == len(set(r for r, _ in refs)) == 9 and pos == 8      # 全9枚、スライドごとに場所が1つ


def test_right_after_link_follows_places_then_down(browser, generic_dir):
    # p04 のリンクで p07 へ → ← で p04 → → で p07（先の場所があるので、↓ の p05 ではない）→ → で ↓ と同じ
    P = url_of(generic_dir, "proposal.html")
    with session(browser, P + "#p04") as page:
        address_bar(page, P + "#p07")
        assert listing(page) == ([("p04", 0), ("p07", 0)], 1)
        assert press(page, "ArrowLeft") == ("p04", 0)
        placed = vids(page)
        assert press(page, "ArrowRight") == ("p07", 0)
        assert toast_text(page) is None
        assert listing(page) == ([("p04", 0), ("p07", 0)], 1) and vids(page) == placed     # 先の場所へ移るだけで、並びは変えない
        assert press(page, "ArrowRight") == ("p08", 0)                 # 先の場所はもうない：↓ と同じ
        assert toast_text(page) is None
        assert page.evaluate("location.hash") == "#p08"
        assert listing(page) == ([("p04", 0), ("p07", 0), ("p08", 0)], 2)            # 場所が ↓ と同じに増える
        assert vids(page)[:2] == placed and vids(page)[2] not in placed


def test_right_without_next_place_rewrites_current_for_steps(browser, generic_dir):
    # ↓ が段階だけを進めるとき（同じスライド）、→ も今の場所を書き換える（場所は増えない）
    with session(browser, url_of(generic_dir, "proposal.html", "#p05")) as page:
        first = vids(page)
        assert press(page, "ArrowRight") == ("p05", 1)
        assert page.evaluate("location.hash") == "#p05.1"
        assert listing(page) == ([("p05", 1)], 0) and vids(page) == first
        assert press(page, "ArrowRight") == ("p05", 2)
        assert press(page, "ArrowRight") == ("p05", 3)
        assert listing(page) == ([("p05", 3)], 0) and vids(page) == first
        assert press(page, "ArrowRight") == ("p06", 0)                 # 次のスライドは新しい場所
        assert listing(page) == ([("p05", 3), ("p06", 0)], 1) and vids(page)[0] == first[0]
        assert toast_text(page) is None


def test_cross_page_right_refused_when_storage_cannot_be_written(browser, generic_dir):
    # 先の場所はあるが別のページで、保存領域に書けない：→ は ↓ にならず、今まで通り知らせて動かない
    P, M = url_of(generic_dir, "proposal.html"), url_of(generic_dir, "minimal.html")
    with session(browser, P + "#p02") as page:
        link(page, M)
        key_away(page, "ArrowLeft")                                    # proposal の p02 に戻る。先の場所は minimal の m1
        assert page.url == P + "#p02" and listing(page) == ([("p02", 0), ("m1", 0)], 0)
        page.evaluate("() => { Storage.prototype.setItem = function () { throw new DOMException('満杯', 'QuotaExceededError'); }; }")
        length = page.evaluate("history.length")
        assert press(page, "ArrowRight") == ("p02", 0)                 # ↓ なら p02 の段階 1。そうならない
        page.wait_for_timeout(300)
        assert page.url == P + "#p02"
        assert toast_text(page) == "これより先の場所はありません"
        assert listing(page) == ([("p02", 0), ("m1", 0)], 0)
        assert page.evaluate("history.length") == length


def test_left_right_key_rules(browser, generic_dir):
    record = """
      window.__prevented = [];
      window.addEventListener('keydown', e => window.__prevented.push([e.key, e.defaultPrevented]));
    """
    with session(browser, url_of(generic_dir, "proposal.html")) as page:
        press(page, "ArrowDown")
        page.evaluate(record)
        for key in ["Shift+ArrowLeft", "Control+ArrowLeft", "Shift+ArrowRight"]:
            assert press(page, key) == ("p02", 0), key
        assert not any(prevented for _, prevented in page.evaluate("__prevented"))
        assert press(page, "ArrowLeft") == ("p01", 0)
        assert page.evaluate("__prevented")[-1] == ["ArrowLeft", True]
        page.evaluate("document.body.insertAdjacentHTML('beforeend', '<input id=\"t\" style=\"position:fixed;left:0;top:0\">')")
        page.focus("#t")
        assert press(page, "ArrowRight") == ("p01", 0)                 # 入力中は動かない
        page.evaluate("document.activeElement.blur()")
        assert press(page, "ArrowRight") == ("p02", 0)


# ---- history.state ----

def test_place_shape_and_storage(browser, generic_dir):
    # 場所の形、保存の形、state の形（共通の決め事）。page は # と ? 以降を除いたもの
    with session(browser, url_of(generic_dir, "proposal.html", "?x=1#p02.1")) as page:
        p = places(page)
        assert p["pos"] == 0 and len(p["items"]) == 1
        item = p["items"][0]
        assert VID_RE.match(item["vid"])
        assert item == {"vid": item["vid"], "page": url_of(generic_dir, "proposal.html"), "kind": "deck", "ref": "p02", "step": 1}
        assert stored(page) == {"v": 1, "items": p["items"], "pos": 0, "restore": None}
        assert page.evaluate("history.state") == {"spVid": item["vid"]}


def test_state_follows_current_place(browser, generic_dir):
    with session(browser, url_of(generic_dir, "proposal.html", "#p02")) as page:
        page.evaluate("history.replaceState({foo: 1}, '')")           # 中身の state は残す（{...history.state, spVid}）
        length = page.evaluate("history.length")
        press(page, "ArrowDown")
        assert page.evaluate("history.state") == {"foo": 1, "spVid": current_vid(page)}
        press(page, "Shift+ArrowDown")
        assert page.evaluate("history.state") == {"foo": 1, "spVid": current_vid(page)}
        assert state_vid(page) == vids(page)[1]
        press(page, "ArrowLeft")
        assert state_vid(page) == vids(page)[0]                        # ページの中の ← でも書き換える
        assert page.evaluate("location.hash") == "#p02.1"
        press(page, "ArrowRight")
        assert state_vid(page) == vids(page)[1]
        assert page.evaluate("history.length") == length


def test_state_not_rewritten_when_same_on_reload(browser, generic_dir):
    # 手順4「今の state と同じなら書かない」：再読み込みでは、hash も state も同じなので replaceState を呼ばない
    with session(browser, url_of(generic_dir, "proposal.html", "#p02.1"), init=COUNT_REPLACE) as page:
        assert page.evaluate("__rs") != []                              # 最初の読み込みでは書いた（記録の仕掛けが効いている確認）
        page.reload()
        assert state_vid(page) == current_vid(page)
        assert page.evaluate("__rs") == []
        page.evaluate("dispatchEvent(new PageTransitionEvent('pageshow', {persisted: true}))")      # ページキャッシュからの復帰も同じ
        assert page.evaluate("__rs") == []


def test_state_written_once_for_popstate_and_hashchange(browser, generic_dir):
    # アドレス欄で hash を変えると、新しい履歴項目は state なしで popstate → hashchange と続く。
    # state を書くのは 1 つ目（popstate）の処理だけで、2 つ目（hashchange）は先の処理が書いた識別子に合うので書かない
    P = url_of(generic_dir, "proposal.html")
    with session(browser, P + "#p01", init=COUNT_REPLACE) as page:
        page.evaluate("window.__rs.length = 0")
        events = page.evaluate("__ev.length")
        address_bar(page, P + "#p03")
        assert page.evaluate("__ev")[events:] == ["popstate", "hashchange"]
        assert page.evaluate("__rs") == [events + 1]                    # popstate の処理の中で 1 回だけ。hashchange では呼ばない
        assert state_vid(page) == current_vid(page)


def test_state_not_rewritten_on_browser_back_and_forward(browser, generic_dir):
    # ブラウザの戻る・進む：履歴項目の state に識別子が残っているので、popstate も hashchange も書かない
    P = url_of(generic_dir, "proposal.html")
    with session(browser, P + "#p01", init=COUNT_REPLACE) as page:
        address_bar(page, P + "#p03")
        page.evaluate("window.__rs.length = 0")
        browser_back(page)
        browser_forward(page)
        assert page.evaluate("__ev").count("popstate") >= 3 and page.evaluate("__ev").count("hashchange") >= 3
        assert page.evaluate("__rs") == []
        assert where(page) == ("p03", 0) and state_vid(page) == current_vid(page)


@pytest.mark.parametrize("stub", [REPLACE_THROWS, REPLACE_IGNORED], ids=["throws", "ignored"])
def test_state_write_fails_load_and_pageshow_add_one_place(browser, generic_dir, stub):
    # replaceState が失敗したり間引かれたりして state に識別子が残らなくても、読み込み（と続く pageshow）で場所は 1 つだけ
    # （この文書が最後に書いた識別子を、state にないときの代わりに使う。着いたときの処理は毎回通す）
    P = url_of(generic_dir, "proposal.html")
    for url in (P + "#p02", P):                                       # hash があるとき・ないとき（ないときは hash の書き込みも失敗する）
        with session(browser, url, init=stub) as page:
            assert page.evaluate("__ev").count("pageshow") == 1       # 読み込みの処理と pageshow の処理の 2 回が通っている
            assert state_vid(page) is None                            # 本当に書けていない
            assert len(places(page)["items"]) == 1 and listing(page)[1] == 0
            page.evaluate("dispatchEvent(new PageTransitionEvent('pageshow', {persisted: true}))")    # もう一度通しても増えない
            assert len(places(page)["items"]) == 1
            assert stored(page)["items"] == places(page)["items"]


@pytest.mark.parametrize("stub", [REPLACE_THROWS, REPLACE_IGNORED], ids=["throws", "ignored"])
def test_state_write_fails_popstate_and_hashchange_add_one_place(browser, generic_dir, stub):
    # アドレス欄で hash を変えて popstate → hashchange と続いても、場所は 1 つだけ増える
    P = url_of(generic_dir, "proposal.html")
    with session(browser, P + "#p01", init=stub) as page:
        assert listing(page) == ([("p01", 0)], 0)
        events = page.evaluate("__ev.length")
        address_bar(page, P + "#p03")
        assert page.evaluate("__ev")[events:] == ["popstate", "hashchange"]
        assert where(page) == ("p03", 0)
        assert listing(page) == ([("p01", 0), ("p03", 0)], 1)
        events = page.evaluate("__ev.length")
        address_bar(page, P + "#p05")                                 # もう一度
        assert page.evaluate("__ev")[events:] == ["popstate", "hashchange"]
        assert listing(page) == ([("p01", 0), ("p03", 0), ("p05", 0)], 2)
        assert press(page, "ArrowLeft") == ("p03", 0)                 # ページの中の ←→ は動く
        assert press(page, "ArrowRight") == ("p05", 0)


def test_state_write_failure_does_not_hide_a_later_hash_entered(browser, generic_dir):
    # 書けなかった識別子を代わりに使うのは、その識別子の場所に合わせるだけ。表示する所と違えば、新しい場所として足す（飛ばさない）
    P = url_of(generic_dir, "proposal.html")
    with session(browser, P + "#p02", init=REPLACE_THROWS) as page:
        address_bar(page, P + "#p04")
        address_bar(page, P + "#p02")                                 # 前に来た所へ戻っても、別の場所として足す
        assert listing(page) == ([("p02", 0), ("p04", 0), ("p02", 0)], 2)


def test_state_write_recovers_after_failure(browser, generic_dir):
    # 失敗が止んだら、次の移動から state に書ける（識別子が合って、重ならない）
    P = url_of(generic_dir, "proposal.html")
    with session(browser, P + "#p02") as page:
        page.evaluate("window.__orig = History.prototype.replaceState; History.prototype.replaceState = function () { throw new DOMException('x', 'SecurityError'); }; 0")
        assert press(page, "Shift+ArrowDown") == ("p03", 0)
        assert state_vid(page) != current_vid(page)                    # 書けていない
        page.evaluate("History.prototype.replaceState = window.__orig; 0")
        assert press(page, "Shift+ArrowDown") == ("p03b", 0)
        assert state_vid(page) == current_vid(page)
        assert listing(page) == ([("p02", 0), ("p03", 0), ("p03b", 0)], 2)


# ---- ページに着いたときの処理 ----

def test_address_bar_is_same_document_navigation(browser, generic_dir):
    # 前提の確認：hash だけ違う URL への page.goto は、同じ文書の中の移動で、
    # 履歴が1つ増え、新しい項目の state は null で、popstate と hashchange が続けて起きる
    P = url_of(generic_dir, "proposal.html")
    with session(browser, P + "#p01") as page:
        page.evaluate("window.__same = 1; history.replaceState({probe: 1}, '')")
        length = page.evaluate("history.length")
        events = page.evaluate("__ev.length")
        page.evaluate("addEventListener('popstate', e => { window.__popState = e.state; }, {capture: true})")
        address_bar(page, P + "#p03")
        assert page.evaluate("window.__same") == 1
        assert page.evaluate("history.length") == length + 1
        assert page.evaluate("__ev")[events:] == ["popstate", "hashchange"]
        assert page.evaluate("window.__popState") is None
        assert listing(page) == ([("p01", 0), ("p03", 0)], 1)         # 2つのイベントで二重に足されない


def test_address_bar_hash_adds_place(browser, generic_dir):
    # hash を直接入れるのは新しい場所（同じスライドの段階違いでも）
    P = url_of(generic_dir, "proposal.html")
    with session(browser, P + "#p02") as page:
        address_bar(page, P + "#p02.2")
        assert where(page) == ("p02", 2)
        assert listing(page) == ([("p02", 0), ("p02", 2)], 1)
        assert state_vid(page) == current_vid(page)


def test_hash_beats_saved_step(browser, generic_dir):
    P = url_of(generic_dir, "proposal.html")
    # 再読み込み：state が指す場所は p05.0、URL は #p05.2 → 段階2が出て、その場所の段階を書き換える
    with session(browser, P + "#p05") as page:
        vid = current_vid(page)
        reload_with_url(page, "'#p05.2'")
        assert where(page) == ("p05", 2)
        assert listing(page) == ([("p05", 2)], 0) and vids(page) == [vid]
    # 別のページから #p05.2 を開く（リンク）：保存位置が p05.0 でも段階2
    with session(browser, P + "#p05") as page:
        link(page, url_of(generic_dir, "minimal.html"))
        link(page, P + "#p05.2")
        assert where(page) == ("p05", 2)
        assert listing(page) == ([("p05", 0), ("m1", 0), ("p05", 2)], 2)


def test_no_hash_uses_matched_place(browser, generic_dir):
    # hash がないときは、state で合わせた場所を出す（再読み込み）。URL にも書く
    with session(browser, url_of(generic_dir, "proposal.html", "#p05.2")) as page:
        before = places(page)
        reload_with_url(page, "location.href.replace(/#.*$/, '')")
        assert where(page) == ("p05", 2)
        assert page.evaluate("location.hash") == "#p05.2"
        assert places(page) == before
        assert toast_text(page) is None


def test_empty_hash_entered(browser, generic_dir):
    # アドレス欄で空の hash（#）にした：hash がない扱い。新しい履歴項目には state がないので、先頭を出し、URL も合わせる
    P = url_of(generic_dir, "proposal.html")
    with session(browser, P + "#p05") as page:
        address_bar(page, P + "#")
        assert where(page) == ("p01", 0)
        assert page.evaluate("location.hash") == "#p01"
        assert listing(page) == ([("p05", 0), ("p01", 0)], 1)
        assert toast_text(page) is None
        assert press(page, "ArrowLeft") == ("p05", 0)


@pytest.mark.parametrize("bad", ["#missing", "#p02.x", "#99", "#%E0%A4%A"])
def test_bad_hash_with_saved_place(browser, generic_dir, bad):
    # 読めない hash は、保存した場所があっても先頭を出して知らせる
    P = url_of(generic_dir, "proposal.html")
    with session(browser, P + "#p05.2") as page:
        address_bar(page, P + bad)
        assert where(page) == ("p01", 0) and toast_text(page)
        assert page.evaluate("location.hash") == "#p01"
    with session(browser, P + "#p05.2") as page:                         # 再読み込み（state は p05.2 の場所を指す）
        reload_with_url(page, json.dumps(bad))
        assert where(page) == ("p01", 0) and toast_text(page)
        assert page.evaluate("location.hash") == "#p01"


def test_browser_back_in_document(browser, generic_dir):
    # アドレス欄で #p01→#p02→#p03。ブラウザの戻るで p02・p01、進むで p02・p03。2往復。件数は3のまま
    P = url_of(generic_dir, "proposal.html")
    with session(browser, P + "#p01") as page:
        address_bar(page, P + "#p02")
        address_bar(page, P + "#p03")
        ids = vids(page)
        assert listing(page) == ([("p01", 0), ("p02", 0), ("p03", 0)], 2)

        def check(slide, pos):
            assert where(page) == (slide, 0)
            assert page.evaluate("location.hash") == "#" + slide
            assert listing(page)[1] == pos
            assert vids(page) == ids                                    # 件数は3のまま、並びも同じ
            assert state_vid(page) == ids[pos]

        for _ in range(2):
            pops, hashes = count(page, "popstate"), count(page, "hashchange")
            browser_back(page)
            check("p02", 1)
            browser_back(page)
            check("p01", 0)
            browser_forward(page)
            check("p02", 1)
            browser_forward(page)
            check("p03", 2)
            # popstate と hashchange の両方が、4回とも起きている（それでも二重に足されない）
            assert count(page, "popstate") - pops == 4 and count(page, "hashchange") - hashes == 4
        # ←→ の移動先も合っている
        assert press(page, "ArrowLeft") == ("p02", 0)
        assert press(page, "ArrowLeft") == ("p01", 0)
        assert press(page, "ArrowRight") == ("p02", 0)
        assert vids(page) == ids


def test_cross_page_round_trip(browser, generic_dir):
    # proposal#p04 → minimal.html#m1（リンク）→ ← で proposal の p04 に戻る（復元先）→ → で minimal
    P, M = url_of(generic_dir, "proposal.html"), url_of(generic_dir, "minimal.html")
    with session(browser, P + "#p04") as page:
        link(page, M + "#m1")
        ids = vids(page)
        key_away(page, "ArrowLeft")
        assert page.url == P + "#p04" and where(page) == ("p04", 0)
        assert listing(page) == ([("p04", 0), ("m1", 0)], 0) and vids(page) == ids
        key_away(page, "ArrowRight")
        assert page.url == M + "#m1" and where(page) == ("m1", 0)
        assert listing(page) == ([("p04", 0), ("m1", 0)], 1) and vids(page) == ids


def test_cross_page_round_trip_keeps_step(browser, generic_dir):
    # proposal#p05.2 → minimal（リンク）→ ← で proposal の p05.2（復元先）→ → で minimal
    P, M = url_of(generic_dir, "proposal.html"), url_of(generic_dir, "minimal.html")
    with session(browser, P + "#p04") as page:
        press(page, "ArrowDown")
        press(page, "ArrowDown")
        press(page, "ArrowDown")
        assert where(page) == ("p05", 2)
        link(page, M + "#m1")
        ids = vids(page)
        assert listing(page) == ([("p04", 0), ("p05", 2), ("m1", 0)], 2)
        key_away(page, "ArrowLeft")
        assert page.url == P + "#p05.2"
        assert where(page) == ("p05", 2)
        assert listing(page)[1] == 1 and vids(page) == ids
        assert state_vid(page) == ids[1]
        assert stored(page)["restore"] is None                            # 使った復元先は消す
        assert press(page, "ArrowLeft") == ("p04", 0)                     # 同じページの中はそのまま動く
        assert press(page, "ArrowRight") == ("p05", 2)
        key_away(page, "ArrowRight")
        assert page.url == M + "#m1"
        assert where(page) == ("m1", 0)
        assert listing(page)[1] == 2 and vids(page) == ids
        key_away(page, "ArrowLeft")
        assert where(page) == ("p05", 2) and vids(page) == ids


def test_bfcache_return(browser, generic_dir):
    # A→B（リンク）→ ブラウザの戻る → A の場所に合い、→ で B。B で増えた場所が A に戻った後も残っている
    # （Chromium は file:// をページキャッシュに入れないので、ここでは読み込み直しの戻る。本物のページキャッシュは次の試験）
    P, M = url_of(generic_dir, "proposal.html"), url_of(generic_dir, "minimal.html")
    with session(browser, P + "#p04") as page:
        press(page, "ArrowDown")
        link(page, M)
        ids = vids(page)
        assert listing(page) == ([("p04", 0), ("p05", 0), ("m1", 0)], 2)
        page.go_back()
        assert where(page) == ("p05", 0)
        assert listing(page)[1] == 1 and vids(page) == ids                # 並びは変わらない
        assert state_vid(page) == ids[1]
        key_away(page, "ArrowRight")
        assert where(page) == ("m1", 0) and listing(page)[1] == 2 and vids(page) == ids


def test_link_a_b_a_then_history(browser, generic_dir):
    # リンクで A→B→A。ブラウザの戻るで B、もう一度戻るで最初の A、進むで B、もう一度進むで2回目の A
    P, M = url_of(generic_dir, "proposal.html"), url_of(generic_dir, "minimal.html")
    with session(browser, P + "#p02") as page:
        link(page, M)
        link(page, P + "#p02")
        ids = vids(page)
        assert listing(page) == ([("p02", 0), ("m1", 0), ("p02", 0)], 2)
        page.go_back()
        assert where(page) == ("m1", 0) and listing(page)[1] == 1
        page.go_back()
        assert where(page) == ("p02", 0) and listing(page)[1] == 0
        page.go_forward()
        assert where(page) == ("m1", 0) and listing(page)[1] == 1
        page.go_forward()
        assert where(page) == ("p02", 0) and listing(page)[1] == 2
        assert vids(page) == ids


def test_link_same_as_neighbor_is_new(browser, generic_dir):
    P, M = url_of(generic_dir, "proposal.html"), url_of(generic_dir, "minimal.html")
    # 別のページ：p04 → minimal → ← で p04。隣（minimal#m1）と同じ URL をリンクで開くと、新しい場所として足す
    with session(browser, P + "#p04") as page:
        link(page, M + "#m1")
        old = vids(page)
        key_away(page, "ArrowLeft")
        assert listing(page)[1] == 0
        link(page, M + "#m1")
        assert listing(page) == ([("p04", 0), ("m1", 0)], 1)
        assert vids(page)[0] == old[0] and vids(page)[1] != old[1]
    # 同じページ：p06 → ↓ p07 → ← で p06。アドレス欄で #p07 を開くと、新しい場所として足す
    with session(browser, P + "#p06") as page:
        press(page, "ArrowDown")
        old = vids(page)
        press(page, "ArrowLeft")
        address_bar(page, P + "#p07")
        assert listing(page) == ([("p06", 0), ("p07", 0)], 1)
        assert vids(page)[1] != old[1]


BLOCK_UNLOAD = """
  window.__blockUnload = e => { e.preventDefault(); e.returnValue = ''; };
  addEventListener('beforeunload', window.__blockUnload);
"""


def test_aborted_restore_then_link(browser, generic_dir):
    # ← で別のページへ移るのを途中で止める（復元先が残る）。すぐにリンクで同じページを開くと、新しい場所として足す
    P, M = url_of(generic_dir, "proposal.html"), url_of(generic_dir, "minimal.html")
    with session(browser, M) as page:
        link(page, P + "#p04")
        ids = vids(page)
        page.evaluate(BLOCK_UNLOAD)
        page.on("dialog", lambda d: d.dismiss())                        # 「このページを離れますか」で離れない
        page.keyboard.press("ArrowLeft")
        page.wait_for_timeout(300)
        assert page.url == P + "#p04" and where(page) == ("p04", 0)    # 移っていない
        restore = stored(page)["restore"]
        assert restore and restore["vid"] == ids[0]                      # 復元先は残っている
        assert listing(page) == ([("m1", 0), ("p04", 0)], 1)            # 今の位置は動いていない
        page.evaluate("removeEventListener('beforeunload', window.__blockUnload)")
        with page.expect_navigation():
            page.click('#stage [data-link="1"]')                        # 本物のリンク（p04 の「事例の資料」→ minimal.html#m1）。復元先を消してから移る
        page.wait_for_function("!!window.__sp")
        assert listing(page) == ([("m1", 0), ("p04", 0), ("m1", 0)], 2)
        assert vids(page)[:2] == ids and vids(page)[2] not in ids
        assert stored(page)["restore"] is None


def restore_case(page, vid, age_ms):
    data = stored(page)
    data["restore"] = {"vid": vid, "t": page.evaluate("Date.now()") - age_ms}
    store(page, data)


@pytest.mark.parametrize("case", ["fresh-own", "stale", "other-page", "unknown"])
def test_restore_rules(browser, generic_dir, case):
    # 復元先は「10秒以内」「並びの中にある」「このページの場所」のときだけ使う。使っても使わなくても消す
    P, M = url_of(generic_dir, "proposal.html"), url_of(generic_dir, "minimal.html")
    with session(browser, M) as page:
        link(page, P + "#p04")
        link(page, M)
        ids = vids(page)                                                # [m1, p04, m1]、今は2つ目の m1（state もそれ）
        vid, age = {"fresh-own": (ids[0], 1000), "stale": (ids[0], 11000),
                    "other-page": (ids[1], 1000), "unknown": ("zzzzzzzz9999", 1000)}[case]
        restore_case(page, vid, age)
        page.reload()
        assert listing(page)[1] == (0 if case == "fresh-own" else 2)
        assert vids(page) == ids
        assert stored(page)["restore"] is None
        assert state_vid(page) == ids[listing(page)[1]]


def test_reload_keeps_list(browser, generic_dir):
    with session(browser, url_of(generic_dir, "proposal.html", "#p01")) as page:
        press(page, "ArrowDown")
        press(page, "ArrowDown")
        press(page, "Shift+ArrowDown")
        press(page, "ArrowLeft")
        before = places(page)
        assert listing(page) == ([("p01", 0), ("p02", 1), ("p03", 0)], 1)
        for _ in range(2):
            page.reload()
            assert where(page) == ("p02", 1)
            assert places(page) == before
        press(page, "ArrowRight")
        before = places(page)
        page.reload()
        assert where(page) == ("p03", 0) and places(page) == before


def test_pageshow_rereads_storage(browser, generic_dir):
    # ページキャッシュから戻ったときと同じ：メモリーの並びは古く、保存した並びが新しい。pageshow で読み直す
    with session(browser, url_of(generic_dir, "proposal.html", "#p02")) as page:
        press(page, "Shift+ArrowDown")
        data = stored(page)
        data["items"].append({"vid": "other0000001", "page": url_of(generic_dir, "minimal.html"), "kind": "deck",
                              "ref": "m1", "step": 0})
        store(page, data)
        page.evaluate("dispatchEvent(new PageTransitionEvent('pageshow', {persisted: true}))")
        assert listing(page) == ([("p02", 0), ("p03", 0), ("m1", 0)], 1)
        assert where(page) == ("p03", 0)
        key_away(page, "ArrowRight")
        assert where(page) == ("m1", 0) and listing(page)[1] == 2


# ---- 本物のページキャッシュ（http で開く） ----

@pytest.fixture(scope="module")
def http_base():
    """リポジトリを 127.0.0.1 の http で出す（Chromium は file:// をページキャッシュに入れないため）。"""
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(REPO)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/examples/generic/"
    server.shutdown()


BFCACHE_BROWSER_MISSING = (
    "ページキャッシュの試験に使う Playwright の Chromium の完全版（新しい headless）が起動できません。"
    "README の手順で入れてください：python3 -m playwright install chromium"
)


def launch_bfcache_browser(browser_type):
    """ページキャッシュが効く Chromium を起動する（Playwright が既定で付ける --disable-back-forward-cache を外し、
    新しい headless の Chromium を使う。headless shell はページキャッシュを使わない）。
    起動できないときは、黙って skip せず、入れ方を知らせて失敗させる（本物のページキャッシュの試験が空振りで終わらないように）。"""
    from playwright.sync_api import Error

    try:
        return browser_type.launch(channel="chromium", args=CHROMIUM_ARGS,
                                   ignore_default_args=["--disable-back-forward-cache"])
    except Error as exc:
        pytest.fail(f"{BFCACHE_BROWSER_MISSING}\n（起動時のエラー: {exc}）", pytrace=False)


@pytest.fixture(scope="module")
def bfcache_browser(browser):
    """ページキャッシュが効く Chromium。Playwright は1つの thread で1つしか動かせないので、browser と同じ Playwright から起動する。"""
    b = launch_bfcache_browser(browser.browser_type)
    yield b
    b.close()


def test_bfcache_browser_missing_fails_instead_of_skipping():
    # ブラウザが起動できないときは skip ではなく、入れ方を書いた失敗になる
    from playwright.sync_api import Error

    class Missing:
        def launch(self, **kwargs):
            raise Error("Executable doesn't exist at /nowhere/chrome")

    with pytest.raises(pytest.fail.Exception) as info:
        launch_bfcache_browser(Missing())
    message = str(info.value)
    assert "python3 -m playwright install chromium" in message and "README" in message
    assert "Executable doesn't exist" in message


def test_bfcache_browser_launch_passes_the_cache_enabling_options():
    # 起動の引数：ページキャッシュを無効にする既定の引数を外し、新しい headless の Chromium（channel="chromium"）を使う
    seen = {}

    class Recorder:
        def launch(self, **kwargs):
            seen.update(kwargs)
            return "browser"

    assert launch_bfcache_browser(Recorder()) == "browser"
    assert seen["channel"] == "chromium" and seen["ignore_default_args"] == ["--disable-back-forward-cache"]
    assert seen["args"] == CHROMIUM_ARGS


def test_bfcache_return_real_cache(bfcache_browser, http_base):
    with session(bfcache_browser, http_base + "proposal.html#p04") as page:
        press(page, "ArrowDown")
        page.evaluate("window.__frozen = 1")
        link(page, http_base + "minimal.html")
        ids = vids(page)
        assert listing(page) == ([("p04", 0), ("p05", 0), ("m1", 0)], 2)
        page.go_back(wait_until="commit")
        page.wait_for_function("__ev.includes('pageshow-persisted')")
        assert page.evaluate("window.__frozen") == 1                   # ページキャッシュから戻った
        assert where(page) == ("p05", 0)
        assert listing(page)[1] == 1 and vids(page) == ids              # メモリーの古い並びでなく、保存した並び
        key_away(page, "ArrowRight")
        assert where(page) == ("m1", 0) and listing(page)[1] == 2 and vids(page) == ids


# ---- 保存領域が使えない・壊れている ----

STORAGE_THROWS = {
    "methods": """
      Storage.prototype.getItem = function () { throw new DOMException('拒否', 'SecurityError'); };
      Storage.prototype.setItem = function () { throw new DOMException('拒否', 'SecurityError'); };
    """,
    "getter": """
      Object.defineProperty(window, 'sessionStorage', { get() { throw new DOMException('拒否', 'SecurityError'); } });
    """,
}


@pytest.mark.parametrize("how", list(STORAGE_THROWS))
def test_storage_unavailable(browser, generic_dir, how):
    # sessionStorage が例外を投げる：ページは開き、デッキの中の ←→ も、ブラウザの戻る・進むも、ページの中で動く
    P = url_of(generic_dir, "proposal.html")
    with session(browser, P + "#p02", init=STORAGE_THROWS[how]) as page:
        assert where(page) == ("p02", 0)
        assert press(page, "ArrowDown") == ("p02", 1)
        assert press(page, "Shift+ArrowDown") == ("p03", 0)
        assert press(page, "ArrowLeft") == ("p02", 1)
        assert press(page, "ArrowRight") == ("p03", 0)
        assert press(page, "ArrowRight") == ("p03b", 0) and toast_text(page) is None   # 先の場所がない → は ↓ と同じ（ページの中で動く）
        assert press(page, "ArrowLeft") == ("p03", 0)
        address_bar(page, P + "#p05")
        assert listing(page) == ([("p02", 1), ("p03", 0), ("p05", 0)], 2)               # 先の場所（p03b）は、新しい場所を足すとき捨てる
        browser_back(page)
        assert where(page) == ("p03", 0) and listing(page)[1] == 1
        assert press(page, "ArrowLeft") == ("p02", 1)
        page.reload()                                                  # 読み込み直すと、ページの中の並びは空から
        assert where(page) == ("p02", 1)
        assert listing(page) == ([("p02", 1)], 0)


def test_storage_read_fails_cross_page_refused(browser, generic_dir):
    # 途中から読めなくなった：並びはページの中で続き、別のページへの ← は端と同じ知らせで動かない
    P, M = url_of(generic_dir, "proposal.html"), url_of(generic_dir, "minimal.html")
    with session(browser, P) as page:
        page.keyboard.press("ArrowLeft")
        first_edge_msg = toast_text(page)
    with session(browser, M) as page:
        link(page, P + "#p02")
        page.evaluate("() => { Storage.prototype.getItem = function () { throw new DOMException('拒否', 'SecurityError'); }; }")
        address_bar(page, P + "#p03")                                  # 着いたときの処理で読めない
        assert listing(page) == ([("m1", 0), ("p02", 0), ("p03", 0)], 2)
        assert press(page, "ArrowLeft") == ("p02", 0)
        assert press(page, "ArrowLeft") == ("p02", 0)
        page.wait_for_timeout(300)
        assert page.url == P + "#p02"
        assert toast_text(page) == first_edge_msg
        assert listing(page)[1] == 1


def test_storage_write_fails_cross_page_refused(browser, generic_dir):
    # 読めるが書けない（容量の超過など）：ページの中の ←→ は動き、別のページへの ← は端と同じ知らせで動かない
    P, M = url_of(generic_dir, "proposal.html"), url_of(generic_dir, "minimal.html")
    with session(browser, P) as page:
        page.keyboard.press("ArrowLeft")
        first_edge_msg = toast_text(page)                              # 先頭で ← を押したときの知らせ
    with session(browser, M) as page:
        link(page, P + "#p02")
        page.add_init_script("Storage.prototype.setItem = function () { throw new DOMException('満杯', 'QuotaExceededError'); };")
        page.reload()
        assert listing(page) == ([("m1", 0), ("p02", 0)], 1)
        assert press(page, "ArrowDown") == ("p02", 1)
        assert press(page, "Shift+ArrowDown") == ("p03", 0)
        assert press(page, "ArrowRight") == ("p03b", 0) and toast_text(page) is None   # 先の場所がない → は ↓ と同じ
        assert press(page, "ArrowLeft") == ("p03", 0)
        assert press(page, "ArrowLeft") == ("p02", 1)
        assert toast_text(page) is None
        length = page.evaluate("history.length")
        assert press(page, "ArrowLeft") == ("p02", 1)                  # minimal の場所へは移らない
        page.wait_for_timeout(300)
        assert page.url == P + "#p02.1"
        assert page.evaluate("history.length") == length
        assert toast_text(page) == first_edge_msg
        assert listing(page) == ([("m1", 0), ("p02", 1), ("p03", 0), ("p03b", 0)], 1)


def valid_item(vid="abcd1234efgh", page="file:///x/proposal.html", kind="deck", ref="p02", step=0):
    return {"vid": vid, "page": page, "kind": kind, "ref": ref, "step": step}


def corrupt_cases():
    ok = valid_item()
    base = {"v": 1, "items": [ok], "pos": 0, "restore": None}

    def with_item(**kw):
        return {**base, "items": [{**ok, **kw}]}

    return {
        "not-json": "{broken",
        "array": "[]",
        "null": "null",
        "string": '"text"',
        "version": {**base, "v": 2},
        "items-not-array": {**base, "items": {}},
        "eleven": {**base, "items": [valid_item(vid=f"abcd1234ef{i:02d}") for i in range(11)]},
        "vid-upper": with_item(vid="ABCD1234"),
        "vid-short": with_item(vid="abc123"),
        "vid-long": with_item(vid="a" * 17),
        "vid-duplicate": {**base, "items": [ok, ok], "pos": 1},
        "ref-digit": with_item(ref="1abc"),
        "ref-empty": with_item(ref=""),
        "ref-space": with_item(ref="p 02"),
        "step-negative": with_item(step=-1),
        "step-float": with_item(step=1.5),
        "step-string": with_item(step="2"),
        "step-over-limit": with_item(step=10001),                        # 上限は 10000
        "step-unsafe-integer": with_item(step=2 ** 53),                   # 安全に扱える整数の範囲の外
        "step-exponent": '{"v":1,"items":[{"vid":"abcd1234efgh","page":"file:///x/proposal.html","kind":"deck","ref":"p02","step":1e21}],"pos":0,"restore":null}',
        "kind": with_item(kind="other"),
        "page-javascript": with_item(page="javascript:alert(1)"),
        "page-hash": with_item(page="file:///x/proposal.html#p02"),
        "page-number": with_item(page=3),
        "item-null": {**base, "items": [None]},
        "pos-out": {**base, "pos": 1},
        "pos-missing": {k: v for k, v in base.items() if k != "pos"},
        "pos-float": {**base, "pos": 0.5},
        "restore-shape": {**base, "restore": {"vid": "abcd1234efgh"}},
        "restore-vid": {**base, "restore": {"vid": "x", "t": 1}},
    }


@pytest.mark.parametrize("name", list(corrupt_cases()))
def test_corrupt_storage(browser, generic_dir, name):
    # 壊れた並びは捨てて、空から始まる（再読み込みで、今の場所だけの並びになる）
    with session(browser, url_of(generic_dir, "proposal.html", "#p03")) as page:
        store(page, corrupt_cases()[name])
        page.reload()
        assert where(page) == ("p03", 0)
        assert listing(page) == ([("p03", 0)], 0)
        assert stored(page)["items"] == places(page)["items"]           # 次に書いたときに、正しい形で上書きする
        assert press(page, "ArrowLeft") == ("p03", 0) and toast_text(page)


def test_valid_storage_is_kept(browser, generic_dir):
    # 上の試験が空振りでないことの確認：形の正しい並び（目次の場所を含む）は捨てない
    P = url_of(generic_dir, "proposal.html")
    with session(browser, P + "#p03") as page:
        data = stored(page)
        data["items"].insert(0, valid_item(vid="cat000000001", page=url_of(generic_dir, "index.html"), kind="catalog",
                                           ref="proposal", step=0))
        data["pos"] = 1
        store(page, data)
        page.reload()
        assert listing(page) == ([("proposal", 0), ("p03", 0)], 1)


def test_step_limit_is_inclusive(browser, generic_dir):
    # 上の「step の上限」の境目：10000 は壊れたデータではない（捨てない）。10001 は上の試験で捨てる
    P = url_of(generic_dir, "proposal.html")
    with session(browser, P + "#p03") as page:
        data = stored(page)
        data["items"].insert(0, valid_item(vid="cat000000001", page=url_of(generic_dir, "index.html"), kind="catalog",
                                           ref="proposal", step=10000))
        data["pos"] = 1
        store(page, data)
        page.reload()
        assert listing(page) == ([("proposal", 10000), ("p03", 0)], 1)


def test_left_to_catalog_place(browser, generic_dir):
    # 目次の場所へ ← で移るときは「目次のページ#デッキの ID」を開く
    P = url_of(generic_dir, "proposal.html")
    with session(browser, P + "#p03") as page:
        data = stored(page)
        data["items"].insert(0, valid_item(vid="cat000000001", page=url_of(generic_dir, "index.html"), kind="catalog",
                                           ref="minimal", step=0))
        data["pos"] = 1
        store(page, data)
        page.reload()
        with page.expect_navigation():
            page.keyboard.press("ArrowLeft")
        assert page.url == url_of(generic_dir, "index.html", "#minimal")


# ---- そのほかの決まり ----

def write_variant(tmp_path, generic_dir, name, edit):
    """proposal.html を一時フォルダーに写し、edit(html) で書き換えたものの URL を返す（読み込みは元の場所の絶対パス）。"""
    html = (generic_dir / "proposal.html").read_text(encoding="utf-8")
    html = html.replace('src="render.js"', f'src="{(generic_dir / "render.js").as_uri()}"')
    html = html.replace('src="../../player/player.js"', f'src="{(REPO / "player" / "player.js").as_uri()}"')
    path = tmp_path / name
    path.write_text(edit(html), encoding="utf-8")
    return path.as_uri()


def test_jump_within_slide_updates_current(browser, generic_dir, tmp_path):
    # "jump"（End）で同じスライドの段階0へ戻るときも、場所を足さずに段階を書き換える
    old = "{ id: 'p08', type: 'title', title: 'ご検討をお願いします', subtitle: '不明な点は、次回までにお知らせください',"
    new = ("{ id: 'p08', type: 'bullets', title: 'ご検討をお願いします', items: ['検討事項', { text: '次回の日程', at: 1 }],")
    url = write_variant(tmp_path, generic_dir, "last-steps.html", lambda html: html.replace(old, new))
    with session(browser, url + "#p08.1") as page:
        assert page.evaluate("deckInfo()[8]") == {"id": "p08", "steps": 1}
        assert press(page, "End") == ("p08", 0)
        assert listing(page) == ([("p08", 0)], 0)
        assert press(page, "Home") == ("p01", 0)
        assert listing(page) == ([("p08", 0), ("p01", 0)], 1)


def test_place_with_missing_slide(browser, generic_dir):
    # デッキが書き換わって、保存した場所の ID がもうない：← では先頭を出して知らせる。hash がないときは先頭（知らせない）
    P = url_of(generic_dir, "proposal.html")
    with session(browser, P + "#p03") as page:
        data = stored(page)
        data["items"].insert(0, valid_item(vid="gone00000001", page=P, ref="p99", step=0))
        data["pos"] = 1
        store(page, data)
        page.reload()
        assert listing(page) == ([("p99", 0), ("p03", 0)], 1)
        assert press(page, "ArrowLeft") == ("p01", 0)
        assert toast_text(page)
        assert listing(page) == ([("p99", 0), ("p03", 0)], 0)
        assert state_vid(page) == "gone00000001"
        page.wait_for_selector(".sp-toast", state="detached", timeout=4000)
        reload_with_url(page, "location.href.replace(/#.*$/, '')")
        assert where(page) == ("p01", 0) and toast_text(page) is None
        assert listing(page) == ([("p99", 0), ("p01", 0)], 1)


COUNT_RENDERS = """
  window.__renders = 0;
  let deck;
  Object.defineProperty(window, 'slideDeck', { configurable: true, get: () => deck, set(v) {
    const render = v.render;
    v.render = function (i, st, target) { if (target && target.id === 'stage') window.__renders++; return render.apply(this, arguments); };
    deck = v;
  } });
"""


def test_arrival_does_not_redraw_same_place(browser, generic_dir):
    # 着いたときの処理は毎回行うが、いま出ている所と同じなら舞台を描き直さない（読み込みの直後の pageshow、
    # popstate に続く hashchange、再読み込みのない戻る・進む）
    P = url_of(generic_dir, "proposal.html")
    with session(browser, P + "#p02", init=COUNT_RENDERS) as page:
        assert page.evaluate("__ev").count("pageshow") == 1
        assert page.evaluate("__renders") == 1
        address_bar(page, P + "#p05")
        assert page.evaluate("__renders") == 2
        browser_back(page)
        assert page.evaluate("__renders") == 3
        page.evaluate("dispatchEvent(new PageTransitionEvent('pageshow', {persisted: true}))")
        assert page.evaluate("__renders") == 3
        press(page, "ArrowDown")
        assert page.evaluate("__renders") == 4
