"""W006 T640 掲載漏れ 3 回目 A: 岩手県 中部保健所の保護（迷子）情報（1020659。2026-11-18・ネットワークなし）。

- 既存の pref_iwate_chubu は【譲渡】の節だけを読むので、同じページの迷子の子が載っていなかった。県の他の保健所（県央・大船渡・宮古）の迷子と同じに、別 slug（stray）で読む。
- 見出しは日で変わる（Wayback 2022・2024-04・2025-10・今日）。0 頭の日（2020-11・2026-02）は 0 頭の文が出ず、案内の p だけになる。
"""


from pathlib import Path

from collector.fetch import FakeFetcher
from collector.registry import load_sources
from collector.run import Collected, collect_one

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"
SOURCES = {s.slug: s for s in load_sources(ROOT / "registry" / "sources.yaml")}


def _fx(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def _run(slug: str, html: str) -> Collected:
    return collect_one(SOURCES[slug], FakeFetcher({SOURCES[slug].url: html}))


def _zero(c: Collected) -> bool:
    return c.status == "empty" and c.result is not None and c.result.animals == []


# --- 岩手県 中部保健所 保護（迷子）情報 -----------------------------------------
IWATE = "pref_iwate_chubu-2"
IWATE_URL = "https://www.pref.iwate.jp/kennan/hana_hoken/1013542/1020659.html"
IWATE_FX = "w006_pref_iwate_chubu-2_20261118.html"
IWATE_IMG = "https://www.pref.iwate.jp/_res/projects/default_project/_page_/001/020/659/"


def test_iwate_registry():
    s = SOURCES[IWATE]
    assert (s.url, s.kind, s.species, s.mode, s.enabled) == (IWATE_URL, "stray", "mixed", "recipe", True)
    assert (s.municipality, s.prefecture, s.phone) == ("中部保健所", "岩手県", "0198-41-3276")
    assert s.photo == "ok" and s.recipe_path.exists()   # 既存の pref_iwate_chubu と同じ（未指定＝ok）


def test_iwate_today_reads_the_4_stray_animals_the_adoption_slug_does_not_read():
    c = _run(IWATE, _fx(IWATE_FX))
    assert c.status == "ok", c.error
    animals = c.result.animals
    assert [(a["management_no"], a["species"], a["breed"], a["color"], a["sex"], a["age"]) for a in animals] == [
        ("R8-53", "cat", "雑種", "グレー", "不明", "2~3か月齢"),
        ("R8-52", "dog", "柴犬", "黒", "オス", "不明(成犬)"),
        ("R8-51", "dog", "雑種", "黒茶", "オス", "不明(成犬)"),   # 写真の alt は「猫の写真」だが、動物種の欄は犬
        ("R8-50", "cat", "雑種", "キジ白", "去勢済オス", "不明(成猫)"),
    ]
    assert len({a["id"] for a in animals}) == 4
    assert [a["image_url"] for a in animals] == [IWATE_IMG + n for n in ("1113.jpg", "1110.jpg", "1105.jpg", "1102.jpg")]
    assert [(a["shelter_date"], a["location"]) for a in animals] == [
        ("R8年11月12日", "北上市九年橋1丁目地内"), ("R8年11月10日", "遠野市土淵町栃内7地割38番地付近"),
        ("R8年11月5日", "遠野市土淵町柏崎7地割"), ("R8年11月2日", "遠野市綾織町下綾織地内 国道396号線沿い")]
    # 収容期限は note に出す（過ぎた行も、ページが外すまで載せる。期限で絞らない）。特記事項「なし」は出さない
    assert [a["note"] for a in animals] == [
        "収容期限：R8年11月26日", "収容期限：R8年11月20日", "収容期限：R8年11月18日 識別器具：チェーンの首輪", "収容期限：R8年11月18日 応急治療済"]


def test_iwate_other_days_in_wayback_have_other_headings_but_the_same_rows():
    # 見出しの作りは日で変わる: 2022 は h2「犬、猫の保護情報」→ h3「【保護】もとの飼い主さんを捜しています。」→ 写真 → 欄、2024-04 は h2 → h3【保護】、2025-10 は h2「【保護】もとの飼い主さんを探しています。」（動物種の欄が無い）
    c = _run(IWATE, _fx("w006_pref_iwate_chubu-2_wb20221003.html"))
    assert c.status == "ok", c.error
    assert [(a["management_no"], a["species"], a["sex"], a["shelter_date"]) for a in c.result.animals] == [
        ("R4-95", "cat", "オス", "R4年9月15日"), ("R4-94", "dog", "メス", "R4年9月15日"), ("R4-93", "cat", "メス", "R4年9月13日")]
    assert "左前脚を怪我しています。" in c.result.animals[0]["note"] and "識別器具：首輪(赤茶)" in c.result.animals[1]["note"]
    assert len({a["id"] for a in c.result.animals}) == 3 and all(a["image_url"] for a in c.result.animals)
    c = _run(IWATE, _fx("w006_pref_iwate_chubu-2_wb20240420.html"))
    assert c.status == "ok" and [(a["management_no"], a["species"], a["color"]) for a in c.result.animals] == [("R6-3", "cat", "茶白")]
    assert "応急治療中" in c.result.animals[0]["note"]
    # 2025-10 は動物種の欄が無いので、犬か猫かは決めない（種別なし。alt の「猫の写真」は犬にも付くので根拠にしない）
    c = _run(IWATE, _fx("w006_pref_iwate_chubu-2_wb20251006.html"))
    assert c.status == "ok" and [(a["management_no"], a["species"], a["breed"], a["sex"]) for a in c.result.animals] == [("R7-56", None, "雑種", "メス")]


def test_iwate_zero_days_in_wayback_have_only_the_intro_and_no_zero_sentence():
    # 迷子の子がいない日（2020-11・2026-02）は、h2「犬、猫の保護(迷子）情報」と案内の p（「新しい飼い主さんを探すものではありません」等は子のいる日にも出る）だけ。写真も管理番号も無い
    for name in ("w006_pref_iwate_chubu-2_wb20201121.html", "w006_pref_iwate_chubu-2_wb20260211.html"):
        html = _fx(name)
        assert "p class=\"imageright\"" not in html and "管理番号" not in html, name
        c = _run(IWATE, html)
        assert _zero(c), (name, c.status, c.error)
    # 子のいる日（今日・2022-10・2024-04・2025-10）に 0 頭の根拠は成り立たない
    for name in (IWATE_FX, "w006_pref_iwate_chubu-2_wb20221003.html", "w006_pref_iwate_chubu-2_wb20240420.html", "w006_pref_iwate_chubu-2_wb20251006.html"):
        assert _run(IWATE, _fx(name)).result.empty_confirmed is False, name
    # 子のいない日に、写真が載った・管理番号が載った日は 0 頭にしない
    zero = _fx("w006_pref_iwate_chubu-2_wb20260211.html")
    assert not _zero(_run(IWATE, zero.replace("</h2>", "</h2><p>管理番号：R8-99</p>", 1)))
    assert not _zero(_run(IWATE, zero.replace("</h2>", '</h2><p class="imageright"><img src="a.jpg"></p>', 1)))
    # 枠（h1）が変わった日は 0 頭にしない
    assert not _zero(_run(IWATE, zero.replace("岩手県中部保健所保護動物情報", "保護動物情報")))
