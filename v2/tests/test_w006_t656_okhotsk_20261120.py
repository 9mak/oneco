"""T656 直し 1 回目・項目 1（2026-11-20・ネットワークなし）: オホーツク 紋別保健所・遠軽支所の表の「いません」。

2026-11-19 の実ページは、紋別保健所の迷子の犬 2 頭（令和8年11月13日・紋別市元紋別）が載っているのに「本日は 0 頭」だった。
行を「いません」を含むセルのある行ごと外していたため、1 頭目は特徴の「譲渡対象にはなっていません。」で、
2 頭目は担当者が画面外に残した「現在、迷い犬はいません。」（left: -5000px の span）で子の行が消えていた。
子のいない行は、写真も保護日も無い「いません」だけの行で、エンジンの動物の条件（写真・管理番号・収容日・個体ページのどれか）で落ちる。
"""

import re
from dataclasses import replace
from pathlib import Path

from collector.fetch import FakeFetcher
from collector.registry import load_sources
from collector.run import Collected, collect_one

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"
SOURCES = {s.slug: s for s in load_sources(ROOT / "registry" / "sources.yaml")}
LIVE = "w006_hokkaido_okhotsk-4_20261120.html"   # 2026-11-20 の実ページ（迷子の犬 2 頭・募集の猫 1 行）
KITAMI = "w006_hokkaido_okhotsk-6_20261117.html"
NONE_DOG = "<tr><td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td><td><p>&nbsp;</p></td><td><p>現在、迷い犬はいません。</p></td></tr>"
NONE_ADOPT = "<tr><td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td><td>現在、飼い主募集中の猫はいません。</td><td>&nbsp;</td></tr>"


def _run(slug: str, fixture: str, mutate=None) -> Collected:
    html = (FIX / fixture).read_text(encoding="utf-8")
    if mutate:
        html = mutate(html)
    return collect_one(replace(SOURCES[slug], mode="recipe"), FakeFetcher({SOURCES[slug].url: html}))


def _first_row_to_none(h: str) -> str:
    """迷子の犬（紋別保健所）の表の見出し行だけを残し、データ行（2 頭）を「いません」の行 1 つに置く。"""
    i = h.index("迷子の犬（紋別保健所）")
    start = h.index("<tr>", i)
    first_data = h.index("<tr>", h.index("</tr>", start) + 5)
    end = h.index("</tbody>", first_data)
    return h[:first_data] + NONE_DOG + h[end:]


def test_okhotsk_stray_two_dogs_with_nothing_sentences_in_cells():
    c = _run("hokkaido_okhotsk-5", LIVE)
    assert c.status == "ok", c.error
    assert len(c.result.animals) == 2
    for a in c.result.animals:
        assert a["kind"] == "stray" and a["species"] == "dog" and a["image_url"]
        assert a["shelter_date"] == "令和8年11月13日" and a["sex"] == "オス" and a["age"] == "成犬"
        assert a["location"] and "紋別市元紋別" in a["location"]
    first, second = c.result.animals
    assert "マスティフ風" in first["note"] and "譲渡対象にはなっていません" in first["note"]
    # 2 頭目の特徴の欄には、画面外の span に「現在、迷い犬はいません。」が残っている。note に混ぜない
    assert "中型" in second["note"] and "カーキ色の首輪" in second["note"]
    assert "現在、迷い犬" not in second["note"]
    assert first["id"] != second["id"]


def test_okhotsk_stray_zero_only_when_every_row_is_the_nothing_sentence():
    c = _run("hokkaido_okhotsk-5", LIVE, _first_row_to_none)
    assert c.status == "empty", c.error
    assert c.result.empty_evidence == "empty_absent"


def test_okhotsk_stray_one_dog_row_is_not_zero():
    # 犬の表のデータ行を 1 頭目だけにしても 0 頭にしない（2 頭目の画面外の文が残る行だけでも同じ）
    def second_only(h: str) -> str:
        i = h.index("迷子の犬（紋別保健所）")
        a = h.index("<tr>", h.index("</tr>", h.index("<tr>", i)) + 5)   # データ行 1 の始まり
        b = h.index("<tr>", h.index("</tr>", a) + 5)                      # データ行 2 の始まり
        return h[:a] + h[b:]

    c = _run("hokkaido_okhotsk-5", LIVE, second_only)
    assert c.status == "ok", c.error
    assert len(c.result.animals) == 1 and "カーキ色の首輪" in c.result.animals[0]["note"]


def test_okhotsk_stray_layout_change_is_failed_not_zero():
    c = _run("hokkaido_okhotsk-5", LIVE, lambda h: h.replace("保護日/場所", "保護した日"))
    assert c.status not in {"ok", "empty"}


def test_okhotsk_adoption_child_whose_note_says_imasen_is_read():
    # 飼い主募集の表（-4）も同じ書き方。特徴に「いません」を含む子（ワクチン未接種の注意書きなど）を丸ごと外さない
    def imasen(h: str) -> str:
        assert "にゃんこたちに会いに来てくださいね♫" in h
        return h.replace("にゃんこたちに会いに来てくださいね♫", "ワクチンはまだ接種していません。")

    c = _run("hokkaido_okhotsk-4", LIVE, imasen)
    assert c.status == "ok", c.error
    assert len(c.result.animals) == 1 and "接種していません" in c.result.animals[0]["note"]


def test_okhotsk_adoption_hidden_nothing_sentence_in_child_row_is_still_read():
    def hidden(h: str) -> str:
        span = '<span style="left: -5000px; position: absolute;">現在、飼い主募集中の猫はいません。</span>'
        return h.replace("<p>😺", f"<p>{span}😺", 1) if "<p>😺" in h else h.replace("😺", span + "😺", 1)

    c = _run("hokkaido_okhotsk-4", LIVE, hidden)
    assert c.status == "ok", c.error
    assert len(c.result.animals) == 1


def test_okhotsk_adoption_zero_only_when_every_table_says_none():
    def no_cat(h: str) -> str:
        return re.sub(r"<tr>\s*<td[^>]*>\s*<p[^>]*><strong[^>]*><strong[^>]*>C1</strong>.*?</tr>", NONE_ADOPT, h, flags=re.S)

    assert _run("hokkaido_okhotsk-4", LIVE, no_cat).status == "empty"


def test_okhotsk_kitami_adoption_child_whose_note_says_imasen_is_read():
    # 北見保健所の飼い主募集（-6）。特徴に「いません」を含む子は載せる。決まりました・見つかりましたの行は従来どおり載せない
    imasen = "散歩には行けないので、トイレは室内でしています。"
    assert imasen in (FIX / KITAMI).read_text(encoding="utf-8")
    base = _run("hokkaido_okhotsk-6", KITAMI)
    assert base.status == "ok" and len(base.result.animals) == 1
    c = _run("hokkaido_okhotsk-6", KITAMI, lambda h: h.replace(imasen, "他の犬とは暮らしていません。"))
    assert c.status == "ok", c.error
    assert len(c.result.animals) == 1 and "暮らしていません" in c.result.animals[0]["note"]
    assert c.result.animals[0]["management_no"] == "8-10-1"


def test_okhotsk_kitami_zero_when_only_none_rows():
    def none_dog(h: str) -> str:
        row = "<tr><td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td><td>現在、新しい飼い主さんを探している犬はいません。</td><td>&nbsp;</td></tr>"
        out = re.sub(r"<tr>\s*<td>\u3000\u3000<img.*?</tr>", row, h, count=1, flags=re.S)
        assert out != h
        return out

    c = _run("hokkaido_okhotsk-6", KITAMI, none_dog)
    assert c.status == "empty", c.error
