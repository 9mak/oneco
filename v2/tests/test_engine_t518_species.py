"""T518 ① 犬か猫か決められない子を、捨てずに種別なし（species: None）で載せる（ネットワークなし）。

2026-10-05 おまえさん判断:「犬猫の区別ないなら区別しないでいい。無理やりやる必要はなく、収集できるデータによって
収集した側のサイト構成は変えていい。犬猫が判断できなければ、それはフィルターやデータに格納する必要はない」。
- 台帳 species が mixed で、レシピの map・infer で決まらない行は species を None（JSON の null）で載せる
- allow_other: true のレシピ（map に当たらない＝犬猫以外の動物、と言い切れる一覧）は従来どおり other
- これまで「犬か猫か分からない」で偶然落ちていた動物でない行（譲渡が決まった報告・飼い主に戻った報告・表の見出し行）は、
  そのレシピの row_filter・rows で明示的に落とす（釜石・水戸・山形）。HTML は 2026-10-05 の実ページから必要な部分だけを抜いたもの
"""

from pathlib import Path

from bs4 import BeautifulSoup
from collector.extract import build
from collector.recipe import Doc, Recipe
from collector.registry import Source, load_sources

ROOT = Path(__file__).resolve().parent.parent


def _doc(html: str, url: str = "https://x.jp/a/") -> Doc:
    return Doc(url=url, html=html, soup=BeautifulSoup(html, "lxml"))


def _mixed() -> Source:
    return Source(slug="t", name="t", municipality="t", prefecture="山口県", url="https://x.jp/a/", kind="sheltered", species="mixed")


def _real(slug: str, html: str):
    src = next(s for s in load_sources(ROOT / "registry" / "sources.yaml") if s.slug == slug)
    recipe = Recipe.load(ROOT / "recipes" / f"{slug}.yaml")
    return build(src, recipe, [_doc(html, src.url)])


def _shunan_table(no: str, img: str, breed: str, size: str, color: str, place: str = "下松市西豊井") -> str:
    """周南健康福祉センター（10022.html）の 1 頭 = table 1 つ。2023 年 3 月から「動物種」欄が無い。"""
    return f"""<table style="width:92%"><tbody>
<tr><td>管理番号</td><td><p>{no}</p></td><td rowspan="10"><p><img alt="{no.rsplit('-', maxsplit=1)[-1]}" src="/uploaded/image/{img}.jpg">\u200b</p></td></tr>
<tr><td>掲載年月日</td><td>R8.10.1</td></tr>
<tr><td>保護場所</td><td>{place}</td></tr>
<tr><td>品種</td><td>{breed}</td></tr>
<tr><td>性別</td><td>オス</td></tr>
<tr><td>大きさ</td><td>{size}</td></tr>
<tr><td>毛色</td><td>{color}</td></tr>
<tr><td>その他の特徴</td><td></td></tr>
</tbody></table>"""


SHUNAN_20261005 = ('<div id="main_body"><div class="detail_free"><p>保護・収容している犬・猫の情報を掲載しています。</p>'
                   + "<p></p>".join([
                       _shunan_table("8-3-98", "152043", "雑種", "小", "白茶"),
                       _shunan_table("8-3-99", "152045", "雑種", "小", "黒白", place="周南市月丘町"),
                       _shunan_table("8-3-100", "152044", "雑種", "中", "うす茶", place="周南市徳山"),
                       _shunan_table("8-3-101", "152088", "雑種", "小", "白茶"),
                   ]) + "</div></div>")


# --- エンジン -------------------------------------------------------------------------
def test_undetermined_species_is_kept_without_species():
    recipe = Recipe.from_dict({"rows": "table", "fields": {"management_no": {"label": "管理番号", "regex": "\\d+-\\d+-\\d+"},
                                                           "species": {"label": "動物種"}},
                               "species": {"from": "field", "map": {"犬": "dog", "猫": "cat"}, "infer": True}})
    res = build(_mixed(), recipe, [_doc(SHUNAN_20261005)])
    assert [(a["management_no"], a["species"]) for a in res.animals] == [
        ("8-3-98", None), ("8-3-99", None), ("8-3-100", None), ("8-3-101", None)]
    assert all("犬か猫" not in d.reason for d in res.dropped)


def test_allow_other_still_labels_map_miss_as_other():
    # 千葉県・横浜市などの「犬猫以外」の一覧: map に当たらない＝犬猫以外と言い切れるので other のまま
    html = '<h3>犬</h3><table class="a"><tr><td><img src="d.jpg"></td></tr></table><h3>うさぎ</h3><table class="a"><tr><td><img src="r.jpg"></td></tr></table>'
    recipe = Recipe.from_dict({"rows": "table.a", "image": "img@src",
                               "species": {"from": "heading", "selector": "h3", "allow_other": True}})
    res = build(_mixed(), recipe, [_doc(html)])
    assert [a["species"] for a in res.animals] == ["dog", "other"]


def test_heading_miss_without_allow_other_is_none_not_other():
    html = '<h3>猫</h3><table class="a"><tr><td><img src="c.jpg"></td></tr></table><h3>セキセイインコ</h3><table class="a"><tr><td><img src="b.jpg"></td></tr></table>'
    recipe = Recipe.from_dict({"rows": "table.a", "image": "img@src", "species": {"from": "heading", "selector": "h3"}})
    res = build(_mixed(), recipe, [_doc(html)])
    assert [a["species"] for a in res.animals] == ["cat", None]


def test_fixed_species_source_is_unchanged():
    src = _mixed()
    src.species = "dog"
    recipe = Recipe.from_dict({"rows": "table.a", "image": "img@src"})
    res = build(src, recipe, [_doc('<table class="a"><tr><td><img src="x.jpg">うさぎ</td></tr></table>')])
    assert [a["species"] for a in res.animals] == ["dog"]


# --- 実レシピ ---------------------------------------------------------------------------
def test_yamaguchi_shunan_rows_are_listed_without_species():
    res = _real("pref_yamaguchi", SHUNAN_20261005)
    got = [(a["management_no"], a["species"], a["breed"], a["color"], a["location"]) for a in res.animals]
    assert got == [
        ("8-3-98", None, "雑種", "白茶", "下松市西豊井"),
        ("8-3-99", None, "雑種", "黒白", "周南市月丘町"),
        ("8-3-100", None, "雑種", "うす茶", "周南市徳山"),
        ("8-3-101", None, "雑種", "白茶", "下松市西豊井"),
    ]
    assert all(a["image_url"] for a in res.animals)


def test_machida_bird_is_listed_without_species():
    html = """<div class="h2bg"><div><h2>現在のペットの保護情報</h2></div></div>
<div class="h3bg"><div><h3>猫（めす）</h3></div></div>
<div class="img-area-r"><p class="imglink-txt-right"><img src="hogo.images/260911hogoneko.jpg" alt="猫の写真"> <span>猫</span></p>
<ul><li>種類：雑種</li><li>性別：めす</li><li>毛色：茶トラ</li><li>保護日：2026年8月19日</li><li>保護場所：玉川学園2丁目</li></ul></div>
<div class="h3bg"><div><h3>セキセイインコ</h3></div></div>
<div class="img-area-r"><p class="imglink-txt-right"><img src="hogo.images/260902hogotori.jpg" alt="セキセイインコの写真"> <span>セキセイインコ</span></p>
<ul><li>種類：セキセイインコ</li><li>性別：不明</li><li>毛色　水色白</li><li>保護日：2026年8月12日</li><li>保護場所：金井ヶ丘2丁目</li></ul></div>"""
    res = _real("city_machida-1", html)
    assert [(a["breed"], a["species"]) for a in res.animals] == [("雑種", "cat"), ("セキセイインコ", None)]


def test_kamaishi_adopted_reports_are_dropped_by_row_filter():
    # 【御報告】譲渡が決まりました の子は「仮名・管理番号」だけの p。募集中の子は動物種別・種類・性別などを持つ
    html = """<div id="tmp_contents">
<h2>【御報告】譲渡が決まりました🌸🌸</h2>
<figure class="imagecenter"><img src="../../../_res/projects/default_project/_page_/001/014/123/20260630-1.jpg" alt="ヨミィちゃん"><figcaption class="imgcaption">2026-6-006C</figcaption></figure>
<p>仮名：ヨミィちゃん<br> 管理番号：2026-6-006C</p>
<p>トライアルから譲渡が決まりました。ありがとうございました。</p>
<h2>【譲渡】新しい飼い主さんを募集しています</h2>
<figure class="imagecenter"><img src="../../../_res/projects/default_project/_page_/001/014/123/202600603taro.jpg" alt="タロ君"><figcaption class="imgcaption">2026-1-004D</figcaption></figure>
<p>仮名：タロ君<br> 管理番号：2026-1-004D<br> 動物種別：犬<br> 大きさ：中<br> 種類：雑種<br> 性別：オス<br> 年齢：14歳(5/1現在）<br> 毛色：茶</p>
</div>"""
    res = _real("pref_iwate_kamaishi", html)
    assert [(a["name"], a["species"]) for a in res.animals] == [("タロ君", "dog")]
    assert res.animals[0]["image_url"].endswith("/202600603taro.jpg")


def test_mito_returned_to_owner_is_dropped_by_row_filter():
    html = """<div id="main_body">
<table style="padding:0px"><tbody>
<tr><td colspan="2"><p><img alt="公表182犬正面から" src="/uploaded/image/54159.png"></p></td></tr>
<tr><th><strong>管理番号</strong>　　　</th><td>公表182</td></tr>
<tr><th colspan="2">飼い主に戻りました</th></tr></tbody></table>
<table style="border-collapse:collapse; padding:0px"><tbody>
<tr><td colspan="2"><img alt="公表181犬正面から" src="/uploaded/image/54021.png"></td></tr>
<tr><th><strong>管理番号</strong>　　　</th><td>公表181</td><th><strong>体格</strong></th><td>中</td></tr>
<tr><th><strong>収容日時</strong></th><td>令和8年9月26日</td><th><strong>年齢</strong></th><td>成犬</td></tr>
<tr><th><strong>収容場所</strong></th><td>水戸市鯉淵町</td><th><strong>毛色</strong></th><td>茶</td></tr>
<tr><th><p><strong>犬種</strong></p></th><td>雑種</td><th><strong>首輪</strong></th><td>無し</td></tr>
<tr><th><strong>性別</strong></th><td>雄</td><th><strong>その他</strong></th><td>リードが付属</td></tr></tbody></table>
</div>"""
    res = _real("city_mito-1", html)
    assert [(a["management_no"], a["species"]) for a in res.animals] == [("公表181", "dog")]


def test_yamagata_header_row_is_not_listed():
    # 最上保健所: 見出し行（th だけ）は、表の下の行の値を label で拾ってしまい、写真の無い 2 頭目になっていた
    html = """<div id="tmp_main">
<table class="datatable"><tbody>
<tr><th scope="col">収容月日</th><th scope="col">保護した場所</th><th scope="col">種類</th><th scope="col">特徴</th><th scope="col">写真</th></tr>
<tr><td>R8.9.7</td><td>最上町赤倉ダム付近（R8.9.5）</td><td>柴犬</td><td><p>メス、5歳前後と推定、黒毛</p></td>
<td><p><img alt="R8-D2-1" src="/images/4579/img_20260907_115458cut.jpg"></p></td></tr></tbody></table>
<table class="datatable"><tbody>
<tr><th scope="col">収容月日</th><th scope="col">保護した場所</th><th scope="col">種類</th><th scope="col">特徴</th><th scope="col">写真</th></tr>
</tbody></table>
</div>"""
    res = _real("pref_yamagata", html)
    assert [(a["breed"], a["shelter_date"], a["species"]) for a in res.animals] == [("柴犬", "R8.9.7", "dog")]
    assert res.animals[0]["image_url"].endswith("/img_20260907_115458cut.jpg")
