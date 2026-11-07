"""デッキのページ（1枚の HTML）を書く。舞台・描画・（あれば）ライブ更新・プレイヤーの順に置く。"""
import html
import json


def deck_html(data, *, render_src, player_src, editing=False, live_src=None, css_href=None, edit_srcs=()):
    """convert() の結果 data を埋め込んだページの HTML を返す。

    edit_srcs の script は render の後、デッキを作る script の前に、並べた順に置く。
    data の JSON は `</` を `<\\/` にして埋める（script を途中で閉じさせない）。
    """
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    flag = "true" if editing else "false"
    title = html.escape(data["info"]["title"])
    css = f'<link rel="stylesheet" href="{html.escape(css_href, quote=True)}">\n' if css_href else ""
    live = f'<script src="{html.escape(live_src, quote=True)}"></script>\n' if live_src else ""
    edit = "".join(f'<script src="{html.escape(s, quote=True)}"></script>\n' for s in edit_srcs)
    return (
        '<!doctype html>\n<html lang="ja">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{title}</title>\n{css}</head>\n<body>\n"
        '<div id="stage" class="sp-target"></div>\n'
        f'<script src="{html.escape(render_src, quote=True)}"></script>\n'
        f"{edit}"
        f"<script>\nwindow.slideDeck = EditorSlides.createDeck({payload}, {{editing: {flag}}});\n</script>\n"
        f"{live}"
        f'<script src="{html.escape(player_src, quote=True)}"></script>\n'
        "</body>\n</html>\n"
    )
