"""W006 北海道の振興局・保健所のページ（環境省リンク集のリンク先 39 ページ）の追加（2026-11-07・ネットワークなし）。

子が載っている 10 ページ（8 レシピ + 江別保健所の 2 slug）は 2026-11-07 の保存ページに当て、頭数と主な項目を確かめる。
読めなかったページは link_only（理由は台帳の note）。写真の規約は未確認なので全部 photo: pending。
どのレシピも 0 頭の文言を根拠にしていない（節ごとの「現在いません」が子のいる日にも出るため）ので、
子が載らない日・作りが変わった日は 0 行で「読めなかった」になる（偽の 0 頭を出さない側）。
"""

from pathlib import Path

from collector.fetch import FakeFetcher
from collector.registry import load_sources
from collector.run import Collected, collect_one

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"
SOURCES = {s.slug: s for s in load_sources(ROOT / "registry" / "sources.yaml")}
HOKKAIDO = {k: v for k, v in SOURCES.items() if k.startswith("hokkaido_")}


def _fx(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def _run(slug: str, fixture: str, mutate=None) -> Collected:
    html = _fx(fixture)
    if mutate:
        html = mutate(html)
    return collect_one(SOURCES[slug], FakeFetcher({SOURCES[slug].url: html}))


def _nos(c: Collected, key: str = "management_no") -> list[str | None]:
    assert c.result is not None
    return [a[key] for a in c.result.animals]


def test_registry_all_pending_photo_and_modes():
    assert len(HOKKAIDO) == 41  # 2026-11-07 の指摘で檜山 -2 と紋別 -5 を足した（もとは 39）
    for slug, s in HOKKAIDO.items():
        assert s.prefecture == "北海道" and s.photo == "pending" and s.enabled, slug
        assert s.phone and s.address and s.url.startswith("https://www."), slug
        assert (s.mode == "recipe") == bool(s.recipe), slug
        if s.mode == "recipe":
            assert s.recipe_path.exists(), slug
    recipes = sorted(k for k, v in HOKKAIDO.items() if v.mode == "recipe")
    assert recipes == [
        "hokkaido_hidaka-1", "hokkaido_hidaka-2", "hokkaido_hiyama-1", "hokkaido_iburi-1", "hokkaido_iburi-3",
        "hokkaido_ishikari-1", "hokkaido_ishikari-2", "hokkaido_ishikari-3", "hokkaido_kamikawa-1",
        "hokkaido_kamikawa-3", "hokkaido_kamikawa-4", "hokkaido_kushiro-1", "hokkaido_kushiro-2", "hokkaido_nemuro-1",
        "hokkaido_nemuro-2", "hokkaido_okhotsk-1", "hokkaido_okhotsk-2", "hokkaido_okhotsk-3", "hokkaido_okhotsk-4",
        "hokkaido_okhotsk-5", "hokkaido_oshima-1", "hokkaido_oshima-2", "hokkaido_oshima-3", "hokkaido_rumoi-1",
        "hokkaido_shiribeshi-1", "hokkaido_shiribeshi-2", "hokkaido_sorachi-1", "hokkaido_sorachi-4",
        "hokkaido_souya-1", "hokkaido_souya-2", "hokkaido_tokachi-1", "hokkaido_tokachi-2",
    ]


def test_tokachi_five_cats_with_shelter():
    c = _run("hokkaido_tokachi-1", "w006_hokkaido_tokachi-1_20261107.html")
    assert c.status == "ok", c.error
    assert _nos(c) == ["H-6", "Hー7", "H-8", "H-9", "H-2"]
    assert {a["species"] for a in c.result.animals} == {"cat"}
    assert {a["location"] for a in c.result.animals} == {"帯広保健所"}
    assert c.result.animals[0]["name"] == "ボーピープ" and c.result.animals[0]["sex"] == "メス"


def test_kushiro_five_dogs_skips_graduated():
    c = _run("hokkaido_kushiro-1", "w006_hokkaido_kushiro-1_20261107.html")
    assert c.status == "ok", c.error
    assert _nos(c) == ["D10-2", "D10-3", "D10-4", "D6-1", "D4-2"]  # 「卒業」の 6 件（D10-1 ほか）は載せない
    assert c.result.animals[0]["note"] == "◆譲渡日程調整中"


def test_nemuro_nakashibetsu_only():
    c = _run("hokkaido_nemuro-1", "w006_hokkaido_nemuro-1_20261107.html")
    assert c.status == "ok", c.error
    assert _nos(c) == ["D1", "C7&C8", "C9"]  # 道東センター（h4 が「犬 No.D16」等）は載せない
    assert [a["species"] for a in c.result.animals] == ["dog", "cat", "cat"]
    assert {a["location"] for a in c.result.animals} == {"中標津保健所"}


def test_oshima_one_injured_cat():
    c = _run("hokkaido_oshima-1", "w006_hokkaido_oshima-1_20261107.html")
    assert c.status == "ok", c.error
    a = c.result.animals[0]
    assert len(c.result.animals) == 1 and a["species"] == "cat" and a["sex"] == "メス"
    assert a["shelter_date"] == "令和8年(2026年)5月15日"


def test_shiribeshi_table_five_cats_by_color():
    c = _run("hokkaido_shiribeshi-1", "w006_hokkaido_shiribeshi-1_20261107.html")
    assert c.status == "ok", c.error
    assert _nos(c, "name") == ["リン", "キキ", "トラ子", "チビ", "ミミ"]
    assert {a["species"] for a in c.result.animals} == {"cat"}


def test_sorachi_three_skips_taken_and_aniwel():
    c = _run("hokkaido_sorachi-1", "w006_hokkaido_sorachi-1_20261107.html")
    assert c.status == "ok", c.error
    assert [a["species"] for a in c.result.animals] == ["cat", "cat", "dog"]
    assert _nos(c, "name")[:2] == ["しゅう", "りょう"]
    # 協力動物病院の猫（引取となりました）とあいにきたの 3 頭は載せない
    assert len(c.result.animals) == 3


def test_ishikari_ebetsu_stray_and_adoption():
    s = _run("hokkaido_ishikari-1", "w006_hokkaido_ishikari-12_20261107.html")
    assert s.status == "ok", s.error
    assert _nos(s) == ["振興局3158"] and s.result.animals[0]["shelter_date"] == "令和8年11月2日"
    a = _run("hokkaido_ishikari-2", "w006_hokkaido_ishikari-12_20261107.html")
    assert a.status == "ok", a.error
    assert _nos(a) == ["石狩94-3", "江別8-C14", "石狩94-4"]


def test_ishikari_chitose_one_cat_only_when_one():
    c = _run("hokkaido_ishikari-3", "w006_hokkaido_ishikari-3_20261107.html")
    assert c.status == "ok", c.error
    assert len(c.result.animals) == 1 and c.result.animals[0]["species"] == "cat"
    # 2 匹になった日は 1 つの行に混ざるので読まない（0 行 → 読めなかった）
    two = _run("hokkaido_ishikari-3", "w006_hokkaido_ishikari-3_20261107.html",
               lambda h: h.replace("・猫1匹", "・猫2匹"))
    assert two.status not in {"ok", "empty"}


def test_iburi_muroran_three_cats_only_under_adoption_heading():
    c = _run("hokkaido_iburi-1", "w006_hokkaido_iburi-1_20261107.html")
    assert c.status == "ok", c.error
    assert _nos(c, "name") == ["くろ", "もうふ", "くつした"]
    assert all(a["image_url"] for a in c.result.animals)


def test_kamikawa_no1():
    c = _run("hokkaido_kamikawa-1", "w006_hokkaido_kamikawa-1_20261107.html")
    assert c.status == "ok", c.error
    a = c.result.animals[0]
    assert a["management_no"] == "1" and a["species"] == "cat" and a["color"] == "茶トラ" and a["sex"] == "オス"


def test_structure_change_is_failed_not_zero():
    # 見出しの作りが変わって行が取れなくなった日は 0 頭にしない（0 頭の文言を根拠にしていない）
    for slug, fixture, old, new in (
        ("hokkaido_tokachi-1", "w006_hokkaido_tokachi-1_20261107.html", "<h4>猫（", "<h5>猫（"),
        ("hokkaido_kushiro-1", "w006_hokkaido_kushiro-1_20261107.html", "<h4>犬D", "<h5>犬D"),
        ("hokkaido_kamikawa-1", "w006_hokkaido_kamikawa-1_20261107.html", "No.1</h2>", "ID1</h2>"),
    ):
        c = _run(slug, fixture, lambda h, o=old, n=new: h.replace(o, n))
        assert c.status not in ("ok", "empty"), (slug, c.status)


def test_ishikari_adoption_note_keeps_nested_parens_and_drops_link_text():
    # PR #104 F-05: 「中（小柄）」の括弧で切れない。写真・特集・近況のリンク文字は載せない
    a = _run("hokkaido_ishikari-2", "w006_hokkaido_ishikari-12_20261107.html")
    assert a.status == "ok", a.error
    assert _nos(a, "note") == [
        "石狩支所、雑種、オス、中、キジ白・8~9歳",
        "江別保健所、雑種1、去勢オス1、中、キジ白1、成猫",
        "石狩支所、雑種、メス、中(小柄)、三毛、10歳",
    ]
