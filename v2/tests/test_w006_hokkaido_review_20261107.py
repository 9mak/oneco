"""PR #104 公開ゲートの指摘 F-01・F-02（2026-11-07・ネットワークなし）。

F-01: 檜山の環境生活課「犬猫の新しい飼い主さん募集中！」は移転先の URL で HTTP 200。台帳に足す（link_only）。
F-02: 紋別・遠軽支所のページは結合セルの無い単純な 7 つの表。迷子（okhotsk-5）と飼い主募集（okhotsk-4）を見出し行の下のデータ行で読む。
"""

import re
from pathlib import Path

from collector.fetch import FakeFetcher
from collector.registry import load_sources
from collector.run import Collected, collect_one

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"
SOURCES = {s.slug: s for s in load_sources(ROOT / "registry" / "sources.yaml")}
OK = "w006_hokkaido_okhotsk-4_20261107.html"
STRAY_ROW = r'<tr>\s*<td[^>]*><img alt="DSCF2552.JPG".*?</tr>'
ADOPT_ROW = r'<tr>\s*<td[^>]*>\s*<p[^>]*><strong[^>]*><strong[^>]*>C1</strong>.*?</tr>'
NONE_STRAY = "<tr><td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td><td>現在、迷子の猫はいません。</td></tr>"
NONE_ADOPT = "<tr><td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td><td>現在、飼い主募集中の猫はいません。</td><td>&nbsp;</td></tr>"


def _run(slug: str, fixture: str, mutate=None) -> Collected:
    html = (FIX / fixture).read_text(encoding="utf-8")
    if mutate:
        html = mutate(html)
    return collect_one(SOURCES[slug], FakeFetcher({SOURCES[slug].url: html}))


def _no_stray(h: str) -> str:
    return re.sub(STRAY_ROW, NONE_STRAY, h, flags=re.S)


def _no_adopt(h: str) -> str:
    return re.sub(ADOPT_ROW, NONE_ADOPT, h, flags=re.S)


def test_hiyama_moved_page_is_added_as_link_only():
    s = SOURCES["hokkaido_hiyama-2"]
    assert s.url == "https://www.hiyama.pref.hokkaido.lg.jp/hk/kks/a0003/b0006/kainusisagasi/139924.html"
    assert s.mode == "link_only" and s.photo == "pending" and s.enabled and s.prefecture == "北海道"
    assert s.phone == "0139-52-6491"
    raw = (ROOT / "registry" / "sources.yaml").read_text(encoding="utf-8")
    assert "台帳に足さない" not in raw and "139924.html" in raw


def test_okhotsk_stray_cat_row():
    c = _run("hokkaido_okhotsk-5", OK)
    assert c.status == "ok", c.error
    assert len(c.result.animals) == 1  # 迷子の猫 1 行（3 頭）。「いません」の行は載せない
    a = c.result.animals[0]
    assert a["kind"] == "stray" and a["species"] == "cat"
    assert a["shelter_date"] == "令和8年11月5日" and a["image_url"]
    assert a["age"] == "生後1ヶ月未満" and a["sex"] == "不明"
    assert "キジトラ2匹" in a["note"] and "グレートラ1匹" in a["note"] and "保管期限" in a["note"]
    assert "お問い合わせ先" not in a["note"]


def test_okhotsk_adoption_cat_row():
    c = _run("hokkaido_okhotsk-4", OK)
    assert c.status == "ok", c.error
    assert len(c.result.animals) == 1  # 募集中の猫 1 行（C1・C2）
    a = c.result.animals[0]
    assert a["kind"] == "adoption" and a["species"] == "cat" and a["image_url"]
    assert a["sex"] == "メス" and a["age"] == "12歳" and a["breed"] == "雑種"
    assert "C1" in a["note"] and "C2" in a["note"] and "募集期限" in a["note"]
    assert not a.get("shelter_date")  # 募集期限は収容日ではない


def test_okhotsk_zero_only_when_every_table_of_the_slug_says_none():
    # 「現在、迷子の猫はいません。」は遠軽の表に子のいる日も出る。その slug の表が全部「いません」の日だけ 0 頭
    assert _run("hokkaido_okhotsk-5", OK, _no_stray).status == "empty"
    assert _run("hokkaido_okhotsk-4", OK, _no_adopt).status == "empty"
    # 片方に子がいる日は、もう片方の slug は 0 頭（読めなかったにはならない）
    assert _run("hokkaido_okhotsk-5", OK, _no_adopt).status == "ok"
    assert _run("hokkaido_okhotsk-4", OK, _no_stray).status == "ok"


def test_okhotsk_enkaku_adoption_cat_is_read_too():
    # 遠軽支所の募集猫の見出しは p（h4 でない）。その表の子も落とさず猫と決める
    def enkaku(h: str) -> str:
        i = h.index("飼い主募集中の猫（遠軽支所）")
        j = h.index("現在、飼い主募集中の猫はいません。", i)
        row = ('<tr><td><img alt="x.jpg" src="/fs/x.jpg" /></td><td>オス</td><td>3歳</td>'
               '<td><p>人なつこい</p></td><td>雑種</td></tr>')
        return h[:h.rindex("<tr>", 0, j)] + row + h[h.index("</tr>", j) + 5:]

    c = _run("hokkaido_okhotsk-4", OK, enkaku)
    assert c.status == "ok", c.error
    assert len(c.result.animals) == 2
    assert c.result.animals[-1]["sex"] == "オス" and c.result.animals[-1]["species"] == "cat"


def test_okhotsk_layout_change_is_failed_not_zero():
    # 見出し行の語が変わり、動物の行が残る日は 0 頭にしない（見出し直下の表も数える）
    c = _run("hokkaido_okhotsk-5", OK, lambda h: h.replace("保護日/場所", "保護した日"))
    assert c.status not in {"ok", "empty"}
    c = _run("hokkaido_okhotsk-4", OK, lambda h: h.replace("特徴など", "ようす"))
    assert c.status not in {"ok", "empty"}


def test_kurume_pre_recruitment_remark_is_shown_on_the_row():
    # F-07: 「人ならし中につき正式な募集前」の子（J8008〜J8010 の 1 件）は、その但し書きを note に載せる。他の件には付けない
    c = _run("city_kurume-2", "w006_city_kurume-2_child_20261107.html")
    assert c.status == "ok", c.error
    by_no = {a["management_no"]: a.get("note") for a in c.result.animals}
    assert "正式な募集前" in by_no["J8008、J8009、J8010"]
    assert not by_no["J8013"] and not by_no["J8005"] and not by_no["J8014、J8015"]
