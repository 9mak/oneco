"""T630（2026-10-27 富山県の返事）: 写真は表示してよい。ただし連絡先は犬・猫を収容している厚生センター（支所）のものに。

県のまとめページ 1 件（pref_toyama。動物管理センターを「問い合わせ先」に出していた）を、厚生センター・支所の 8 ページに分け、
各ページ本文の「連絡先」にある電話・住所をそのまま出す。ページ下の「お問い合わせ」欄は中部・高岡・氷見で県庁の番号
（076-444-3229）になっており、魚津支所・砺波も本文と番号が違うので使わない。

fixture は実ページの本文（div#tmp_contents）だけを抜いたもの: 魚津支所 2026-10-27（犬 1 頭）、中部 2026-10-29（0 頭）。
"""

from pathlib import Path

from bs4 import BeautifulSoup
from collector.extract import build
from collector.recipe import Doc, Recipe
from collector.registry import load_sources

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"
BASE = "https://www.pref.toyama.jp/"

# slug: (ページ, 名称, 電話, 住所)。電話・住所は 2026-10-29 に各ページ本文の「連絡先」で確認した値
CENTERS = {
    "pref_toyama_niikawa": ("1268/kurashi/seikatsu/seikatsu/doubutsuaigo/syuyou/niikawa.html",
                            "新川厚生センター", "0765-52-1225", "富山県黒部市堀切新343"),
    "pref_toyama_uozu": ("2200/kurashi/seikatsu/seikatsu/doubutsuaigo/syuyou/uozu.html",
                         "新川厚生センター魚津支所", "0765-24-0359", "富山県魚津市本江1397"),
    "pref_toyama_chubu": ("1267/kurashi/seikatsu/seikatsu/doubutsuaigo/syuyou/tyubu.html",
                          "中部厚生センター", "076-472-4094", "富山県中新川郡上市町横法音寺40"),
    "pref_toyama_takaoka": ("1266/kurashi/seikatsu/seikatsu/doubutsuaigo/syuyou/takaoka.html",
                            "高岡厚生センター", "0766-26-8417", "富山県高岡市赤祖父211番地"),
    "pref_toyama_imizu": ("2202/kurashi/seikatsu/seikatsu/doubutsuaigo/syuyou/imizu.html",
                          "高岡厚生センター射水支所", "0766-56-2666", "富山県射水市戸破1875-1"),
    "pref_toyama_himi": ("2203/kurashi/seikatsu/seikatsu/doubutsuaigo/syuyou/himi.html",
                         "高岡厚生センター氷見支所", "0766-74-1780", "富山県氷見幸町34-9"),
    "pref_toyama_tonami": ("1273/kurashi/seikatsu/seikatsu/doubutsuaigo/syuyou/tonami.html",
                           "砺波厚生センター", "0763-22-4507", "富山県南砺市高儀147"),
    "pref_toyama_oyabe": ("2204/kurashi/seikatsu/seikatsu/doubutsuaigo/syuyou/oyabe.html",
                          "砺波厚生センター小矢部支所", "0766-67-1070", "富山県小矢部市綾子5532"),
}


def _by_slug():
    return {s.slug: s for s in load_sources()}


def test_toyama_is_split_into_the_eight_centers_with_their_own_contacts():
    by = _by_slug()
    assert "pref_toyama" not in by
    assert sorted(s for s in by if s.startswith("pref_toyama")) == sorted(CENTERS)
    for slug, (path, center, phone, address) in CENTERS.items():
        s = by[slug]
        assert s.url == BASE + path
        assert s.municipality == center
        assert (s.phone, s.address) == (phone, address)
        assert s.verified_phone_url == s.url and s.verified_address_url == s.url
        assert s.contact_scope == "facility"     # 収容している厚生センター・支所そのものの連絡先
        assert s.photo == "ok"                   # 富山県庁生活衛生課 2026-10-27「表示して差し支えありません」
        assert s.recipe == "recipes/pref_toyama_center.yaml"
        assert (s.prefecture, s.kind, s.mode, s.enabled) == ("富山県", "stray", "recipe", True)


def _run(slug: str, fixture: str):
    src = _by_slug()[slug]
    recipe = Recipe.load(ROOT / src.recipe)
    html = (FIX / fixture).read_text(encoding="utf-8")
    return build(src, recipe, [Doc(url=src.url, html=html, soup=BeautifulSoup(html, "lxml"))])


def test_center_page_reads_the_dog_with_the_centers_contact():
    res = _run("pref_toyama_uozu", "t630_toyama_uozu_20261027.html")
    assert len(res.animals) == 1
    a = res.animals[0]
    assert (a["species"], a["management_no"], a["sex"]) == ("dog", "魚犬-01", "未去勢 雄")
    assert a["image_url"] == "https://www.pref.toyama.jp/images/13924/dog01.jpg"
    assert (a["phone"], a["address"], a["contact_scope"]) == ("0765-24-0359", "富山県魚津市本江1397", "facility")
    assert a["source_url"] == BASE + CENTERS["pref_toyama_uozu"][0]


def test_center_page_with_no_animals_is_confirmed_empty():
    res = _run("pref_toyama_chubu", "t630_toyama_tyubu_20261029.html")
    assert res.animals == [] and res.empty_confirmed
