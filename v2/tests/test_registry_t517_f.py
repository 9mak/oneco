"""T517 ⑤・⑨: 台帳とレシピの変更のテスト（ネットワークなし。2026-10-05 に実ページから抜いた HTML を直書き）。

⑤-1 広島県（迷い犬・迷い猫）: 管理番号 h2 → 写真 p → 属性 p の並びで、属性 p が行。写真 p は行と同じ p なので image に stop_at: row が要る
⑤-2 一関・大船渡: 迷子と譲渡を slug で分け、kind を正しくする
⑤-3 兵庫県動物愛護センター: 支所ごと（hogo1〜5.html）に slug を分け、url を各ページに固定する
⑨   旭川市あにまある: 「その他の動物」の一覧（探しています = lost、保護しています = sheltered）
"""

from pathlib import Path

from bs4 import BeautifulSoup

from collector.extract import Result, build
from collector.fetch import FakeFetcher
from collector.recipe import Executor, Recipe
from collector.registry import Source, load_sources


def _load(slug: str) -> tuple[Source, Recipe]:
    src = next(s for s in load_sources() if s.slug == slug)
    recipe = Recipe.load(src.recipe_path)
    recipe.encoding = None
    return src, recipe


def _run(slug: str, pages: dict[str, str]) -> tuple[Source, Result]:
    """台帳の url から入口を辿り、レシピで読む（本番の run と同じ流れ）。"""
    src, recipe = _load(slug)
    ex = Executor(FakeFetcher(pages), recipe)
    docs = ex.resolve(src.url)
    return src, build(src, recipe, docs, ex.visited)


# --- ⑤-1 広島県 ------------------------------------------------------------------------
HIROSHIMA_DOG = "https://www.pref.hiroshima.lg.jp/site/apc/jouto-stray-dog-list.html"
HIROSHIMA_CAT = "https://www.pref.hiroshima.lg.jp/site/apc/jouto-stray-cat-list.html"

_INTRO = "<p><strong>この情報は、迷い{x}を探している飼い主さんのための情報提供です。</strong></p>"


def _hiroshima(x: str, nested: bool) -> str:
    def one(no: str, photo: str, attrs: str) -> str:
        body = (f'<h2>管理番号：{no}</h2><p><img alt="１" src="/uploaded/image/{photo}1.JPG"><img alt="２" src="/uploaded/image/{photo}2.JPG"></p>'
                f"<p>{attrs}</p>")
        return f"<div>{body}</div>" if nested else body
    a = one("1HD20260205", "5095", "雑種、推定13歳、雄<br>センターに収容された日：令和8年9月29日<br>保護された状況：令和8年9月27日 12 時半頃に三次市十日市中付近で保護されました。")
    b = one("1HD20260206", "5096", "柴、推定3歳、雌<br>センターに収容された日：令和8年9月30日<br>保護された状況：令和8年9月30日 8 時頃に庄原市中本町付近で保護されました。")
    return f'<html><body><div class="detail_free">{_INTRO.format(x=x)}{a}{b}</div></body></html>'


def test_hiroshima_stray_dog_gets_each_dogs_own_photo_flat_and_nested():
    for nested in (False, True):
        _, res = _run("pref_hiroshima-1", {HIROSHIMA_DOG: _hiroshima("犬", nested)})
        assert [a["management_no"] for a in res.animals] == ["1HD20260205", "1HD20260206"], nested
        # 写真 p の先頭の 1 枚（その子の写真）。前の子の写真を拾わない・取りこぼさない
        assert [a["image_url"] for a in res.animals] == [
            "https://www.pref.hiroshima.lg.jp/uploaded/image/50951.JPG",
            "https://www.pref.hiroshima.lg.jp/uploaded/image/50961.JPG",
        ], nested


def test_hiroshima_stray_cat_gets_photos_and_still_reads_empty_day():
    _, res = _run("pref_hiroshima-2", {HIROSHIMA_CAT: _hiroshima("猫", False)})
    assert len(res.animals) == 2
    assert all(a["image_url"] and a["species"] == "cat" for a in res.animals)
    empty = '<html><body><div class="detail_free"><p>現在迷い猫はいません</p></div></body></html>'
    _, res0 = _run("pref_hiroshima-2", {HIROSHIMA_CAT: empty})
    assert res0.animals == [] and res0.empty_confirmed is True


# --- ⑤-2 一関 -----------------------------------------------------------------------
ICHI_INDEX = "https://www.pref.iwate.jp/kennan/ichi_hoken/doubutsu/index.html"
ICHI_STRAY = "https://www.pref.iwate.jp/kennan/ichi_hoken/doubutsu/1013648.html"
ICHI_ADOPT = "https://www.pref.iwate.jp/kennan/ichi_hoken/doubutsu/1074707.html"

ICHI_INDEX_HTML = f"""<main><h1>一関保健所　動物情報</h1><ul>
<li><a href="{ICHI_STRAY}">一関保健所　保護動物情報</a></li>
<li><a href="{ICHI_ADOPT}">一関保健所　譲渡動物情報</a></li></ul></main>"""

ICHI_STRAY_HTML = """<main><h1>一関保健所　保護動物情報</h1>
<h2>【迷子】　飼い主さんをさがしています</h2>
<p class="imageright"><img src="../../../_res/projects/default_project/_page_/001/013/648/20260914.jpg" alt="inu"></p>
<p>管理番号 ：　9-1<br>保護日　&nbsp;：　2026.09.14<br>保護場所 ：　一関市花泉町永井字東方地内<br>動物種　&nbsp;：　犬<br>大きさ &nbsp; ：　中<br>種　　類 ：&nbsp; 雑種<br>性　　別 ：　メス<br>備　　考 ：　保護時、泥だらけ<br>&nbsp;</p>
<h3>譲渡動物については下記リンクから御覧ください。</h3>
<ul class="objectlink"><li><a href="1074707.html">一関保健所　譲渡動物情報</a></li></ul></main>"""

ICHI_ADOPT_HTML = """<main><h1>一関保健所　譲渡動物情報</h1>
<h2>現在、里親さんを募集している犬猫は次のとおりです。</h2>
<h2>【譲渡】新しい飼い主さんを探しています。</h2>
<p class="imageright"><img src="../../../_res/projects/default_project/_page_/001/074/707/102-2-8rannmaru.jpg" alt="rannmaru"></p>
<p>名前：蘭丸（らんまる）<br>動物種別：猫<br>大きさ：小<br>種類：雑種<br>性別：オス<br>推定年月齢：不明（推定5か月齢）<br>毛色：キジトラ<br>備考：FIV（猫エイズ）陽性。</p>
<h2>迷子になっていた動物は以下に掲載しています。</h2>
<ul class="objectlink"><li><a href="1013648.html">一関保健所　保護動物情報</a></li></ul></main>"""

ICHI_PAGES = {ICHI_INDEX: ICHI_INDEX_HTML, ICHI_STRAY: ICHI_STRAY_HTML, ICHI_ADOPT: ICHI_ADOPT_HTML}


def test_ichinoseki_is_split_into_stray_and_adoption():
    src, res = _run("pref_iwate_ichinoseki", ICHI_PAGES)
    assert src.kind == "stray" and src.url == ICHI_INDEX
    assert [(a["species"], a["management_no"], a["kind"]) for a in res.animals] == [("dog", "9-1", "stray")]
    assert res.animals[0]["image_url"].endswith("/013/648/20260914.jpg")

    src2, res2 = _run("pref_iwate_ichinoseki-2", ICHI_PAGES)
    assert src2.kind == "adoption" and src2.municipality == src.municipality and src2.phone == src.phone
    assert [(a["species"], a["name"], a["kind"]) for a in res2.animals] == [("cat", "蘭丸(らんまる)", "adoption")]
    assert res2.animals[0]["image_url"].endswith("/074/707/102-2-8rannmaru.jpg")


def test_ichinoseki_each_slug_follows_only_its_own_page():
    """片方の slug がもう片方のページを読まない（0 頭の確認も混ざらない）。"""
    _, recipe = _load("pref_iwate_ichinoseki")
    _, recipe2 = _load("pref_iwate_ichinoseki-2")
    soup = BeautifulSoup(ICHI_INDEX_HTML, "lxml")
    assert [a["href"] for a in soup.select(recipe.steps[0]["follow_all"])] == [ICHI_STRAY]
    assert [a["href"] for a in soup.select(recipe2.steps[0]["follow_all"])] == [ICHI_ADOPT]


def test_ichinoseki_empty_day_is_per_page():
    stray_empty = ICHI_STRAY_HTML.replace("管理番号", "x").split("<h2>")[0] + "<p>現在、保護されている犬、猫はいません</p></main>"
    pages = {**ICHI_PAGES, ICHI_STRAY: stray_empty}
    _, res = _run("pref_iwate_ichinoseki", pages)
    assert res.animals == [] and res.empty_confirmed is True
    _, res2 = _run("pref_iwate_ichinoseki-2", pages)       # 譲渡側は迷子ページの文言で 0 頭にならない
    assert len(res2.animals) == 1


# --- ⑤-2 大船渡 ---------------------------------------------------------------------
OFUNATO = "https://www.pref.iwate.jp/engan/ofuna_hoken/1014212/1014213.html"
_IMG = "../../../_res/projects/default_project/_page_/001/014/213/"


def _ofunato(stray: str, adopt: str) -> str:
    return f"""<main><h1>大船渡保健所保護動物情報</h1>
{stray}
<h2>＊緊急募集＊一時預かりボランティアさんを募集しています！</h2><p>詳しくは一時預かりボランティアのページをご覧ください</p>
<h2>最近の保護動物さん</h2><h3>なんかようかい？</h3><p class="imagecenter"><img src="{_IMG}take2.jpg"></p>
{adopt}
<h2>【御礼】譲渡が決まりました！</h2><p class="imagecenter"><img src="{_IMG}ashley.jpg"></p><p>アシュリーくん。新しいお家でも元気いっぱいで頑張ってね！</p>
<h2>犬猫の飼主の皆様へ</h2></main>"""


OFUNATO_STRAY = f"""<h2>元の飼い主を探しています</h2><p class="imagecenter"><img src="{_IMG}daily.jpg"></p>
<p>発見場所：岩手県大船渡市立根町字桑原43-1 発見日：9月27日18:30頃 性別：オス 模様：白黒 備考：首輪、マイクロチップなし。人に良く慣れています。</p>
<p>10/2までに引取らないときは譲渡等の処分をされることがあります。</p>"""
OFUNATO_ADOPT = "".join(
    f"""<h2>【譲渡】新しい飼い主さんを募集しています</h2><p class="imagecenter"><img src="{_IMG}{img}.jpg"></p>
<p>動物種：猫 愛称：{name} 種類：雑種 性別：オス（去勢済み） 毛色：白茶 大きさ：中 推定年月齢：不明（成猫） その他：人馴れしています</p>"""
    for name, img in (("ファノ", "fano2"), ("カイノ", "kaino2")))
OFUNATO_STRAY_EMPTY = "<h2>元の飼い主を探しています</h2><h3>現在、元の飼い主さんを探している動物は保護されていません</h3>"


def test_ofunato_is_split_into_adoption_and_stray():
    src, res = _run("pref_iwate_ofunato", {OFUNATO: _ofunato(OFUNATO_STRAY, OFUNATO_ADOPT)})
    assert src.kind == "adoption"
    assert [a["name"] for a in res.animals] == ["ファノ", "カイノ"]
    assert [a["image_url"].rsplit("/", 1)[1] for a in res.animals] == ["fano2.jpg", "kaino2.jpg"]   # 譲渡の子だけ。迷子・最近の保護動物さん・御礼の写真は入らない

    src2, res2 = _run("pref_iwate_ofunato-2", {OFUNATO: _ofunato(OFUNATO_STRAY, OFUNATO_ADOPT)})
    assert src2.kind == "stray" and src2.municipality == src.municipality and src2.phone == src.phone and src2.url == src.url
    assert len(res2.animals) == 1
    a = res2.animals[0]
    assert a["species"] == "cat" and a["kind"] == "stray" and a["image_url"].endswith("/daily.jpg")
    assert a["shelter_date"] == "9月27日18:30頃" and a["location"] == "岩手県大船渡市立根町字桑原43-1"


def test_ofunato_empty_day_is_per_section():
    # 迷子の節だけ 0 頭: 迷子は「0 頭と確認」、譲渡は今までどおり読める
    page = _ofunato(OFUNATO_STRAY_EMPTY, OFUNATO_ADOPT)
    _, stray = _run("pref_iwate_ofunato-2", {OFUNATO: page})
    assert stray.animals == [] and stray.empty_confirmed is True
    _, adopt = _run("pref_iwate_ofunato", {OFUNATO: page})
    assert len(adopt.animals) == 2


def test_ofunato_stray_not_confirmed_empty_when_structure_breaks():
    """迷子の節の見出しも文言も無い（ページ構造が変わった）日は 0 頭の確認にならず failed のまま通知される。"""
    page = _ofunato("", OFUNATO_ADOPT)
    _, stray = _run("pref_iwate_ofunato-2", {OFUNATO: page})
    assert stray.animals == [] and stray.empty_confirmed is False


# --- ⑤-3 兵庫県動物愛護センター -----------------------------------------------------------
HYOGO = {
    "hyogo_douai": ("hogo1.html", "センター", "06-6432-4599"),
    "hyogo_douai-2": ("hogo2.html", "三木", "0794-84-3050"),
    "hyogo_douai-3": ("hogo3.html", "龍野", "0791-63-5146"),
    "hyogo_douai-4": ("hogo4.html", "但馬", "079-666-8071"),
    "hyogo_douai-5": ("hogo5.html", "淡路", "0799-62-5811"),
}


def _hyogo_page(table: str = "", note: str = "") -> str:
    return f"""<html><body><div id="content">
<header><h1 class="entry-title">兵庫県動物愛護センターの収容動物情報</h1></header>
<div><p class="paragraph">兵庫県動物愛護センターで収容している犬・猫の情報を提供します。</p></div>
<header><h1 class="entry-title">犬</h1></header><div>{table}</div>
<header><h1 class="entry-title">猫</h1></header><div>{note}</div></div></body></html>"""


HYOGO_TABLE = """<table><tr><th>種類</th><td>雑種</td></tr><tr><th>性別</th><td>オス</td></tr><tr><th>年齢</th><td>成犬</td></tr>
<tr><th>毛色</th><td>茶</td></tr><tr><th>大きさ</th><td>中</td></tr><tr><th>収容日</th><td>令和8年10月5日</td></tr>
<tr><th>収容場所</th><td>○○市</td></tr><tr><td colspan="2"><img src="/img/dog1.jpg"></td></tr></table>"""


def test_hyogo_is_split_per_branch_with_fixed_urls():
    sources = {s.slug: s for s in load_sources()}
    for slug, (page, branch, phone) in HYOGO.items():
        s = sources[slug]
        assert s.url == f"https://hyogo-douai.sakura.ne.jp/{page}", slug
        assert s.kind == "sheltered" and s.species == "mixed" and s.prefecture == "兵庫県", slug
        assert s.phone == phone, slug
        if slug != "hyogo_douai":
            assert branch in s.municipality and branch in s.name, slug
        _, recipe = _load(slug)
        assert not recipe.steps, slug                      # 一覧からの follow_all はもう使わない（url が各ページに固定）


def test_hyogo_each_branch_reads_its_own_page_and_species_from_heading():
    for slug, (page, _, _) in HYOGO.items():
        url = f"https://hyogo-douai.sakura.ne.jp/{page}"
        src, res = _run(slug, {url: _hyogo_page(HYOGO_TABLE)})
        assert [(a["species"], a["breed"], a["shelter_date"]) for a in res.animals] == [("dog", "雑種", "令和8年10月5日")], slug
        assert res.animals[0]["source"] == slug and res.animals[0]["kind"] == "sheltered"


def test_hyogo_empty_page_is_zero_not_failed():
    for slug, (page, _, _) in HYOGO.items():
        url = f"https://hyogo-douai.sakura.ne.jp/{page}"
        _, res = _run(slug, {url: _hyogo_page()})
        assert res.animals == [] and res.empty_confirmed is True, slug


# --- ⑨ 旭川市あにまある「その他の動物」---------------------------------------------------------
DC_LIST = "https://www.douaicenter.jp/other-animal/list/other"


def _dc_list(*ids: int) -> str:
    return "<html><body>" + "".join(f'<a href="https://www.douaicenter.jp/other-animal/{i}"><img src="/t.jpg"></a>' for i in ids) + "</body></html>"


def _dc_detail(name: str, label_date: str = "不明日", label_place: str = "不明場所") -> str:
    return f"""<html><body><ul><li>犬・猫の情報</li><li>犬の登録</li></ul>
<h2 class="elementor-heading-title elementor-size-default">{name}</h2>
<div class="animal-image"><div class="large"><a href="/x.jpg"><img alt="" src="https://www.douaicenter.jp/wp-content/uploads/2026/06/{abs(hash(name)) % 9999}.jpg"></a></div></div>
<table class="animal-desc-table"><tr><th>{label_date}</th><td>2026/05/19</td></tr><tr><th>{label_place}</th><td>末広２条８丁目付近</td></tr>
<tr><th>種類</th><td>オカメインコ</td></tr><tr><th>性別</th><td>不明</td></tr><tr><th>連絡先</th><td>サトウ(090-0000-0000)</td></tr></table></body></html>"""


def _dc_pages(**details: str) -> dict[str, str]:
    pages = {DC_LIST: _dc_list(*[int(k[1:]) for k in details])}
    for k, v in details.items():
        pages[f"https://www.douaicenter.jp/other-animal/{k[1:]}"] = v
    return pages


def test_douaicenter_other_lost_picks_only_searching_notices_of_non_dog_cat():
    pages = _dc_pages(
        i15027=_dc_detail("インコ　探しています（サトウ）"),
        i15496=_dc_detail("ウサギ　探してます（ワタナベ）"),
        i99999=_dc_detail("ハムスター　保護しています", label_place="保護場所"),
    )
    src, res = _run("spec_douaicenter-11", pages)
    assert src.kind == "lost" and src.species == "mixed" and src.url == DC_LIST and src.phone == "0166-25-5271"
    assert [(a["name"], a["species"], a["kind"], a["location"]) for a in res.animals] == [
        ("インコ 探しています(サトウ)", "other", "lost", "末広2条8丁目付近"),    # 項目値は NFKC 正規化される（全角空白・括弧は半角に）
        ("ウサギ 探してます(ワタナベ)", "other", "lost", "末広2条8丁目付近"),
    ]
    assert all(a["image_url"] for a in res.animals)
    assert not any("090" in str(v) for a in res.animals for v in a.values())    # 飼い主の連絡先は載せない


def test_douaicenter_other_sheltered_picks_only_found_animals():
    pages = _dc_pages(
        i15027=_dc_detail("インコ　探しています（サトウ）"),
        i99999=_dc_detail("ハムスター　保護しています", label_place="保護場所"),
    )
    src, res = _run("spec_douaicenter-12", pages)
    assert src.kind == "sheltered" and src.species == "mixed" and src.url == DC_LIST
    assert [(a["species"], a["kind"], a["location"]) for a in res.animals] == [("other", "sheltered", "末広2条8丁目付近")]


def test_douaicenter_other_all_searching_means_zero_sheltered_not_failed():
    """一覧が 3 件とも「探しています」の日（今日の実ページ）は、保護しています側は 0 頭と確認できる。"""
    pages = _dc_pages(i15496=_dc_detail("インコ　探しています（ワタナベ）"), i15027=_dc_detail("インコ　探しています（サトウ）"),
                      i14939=_dc_detail("インコ　探しています。（フジノ）"))
    _, lost = _run("spec_douaicenter-11", pages)
    assert len(lost.animals) == 3
    _, sheltered = _run("spec_douaicenter-12", pages)
    assert sheltered.animals == [] and sheltered.empty_confirmed is True


def test_douaicenter_other_dog_and_cat_names_still_map_to_dog_cat():
    pages = _dc_pages(i1=_dc_detail("犬　探しています（ヤマダ）"), i2=_dc_detail("ねこ　探しています（タナカ）"))
    _, res = _run("spec_douaicenter-11", pages)
    assert [a["species"] for a in res.animals] == ["dog", "cat"]


def test_douaicenter_other_empty_list_is_zero():
    for slug in ("spec_douaicenter-11", "spec_douaicenter-12"):
        _, res = _run(slug, {DC_LIST: "<html><body><p>現在、登録がございません。</p></body></html>"})
        assert res.animals == [] and res.empty_confirmed is True, slug


# --- 台帳全体 ------------------------------------------------------------------------
def test_registry_has_unique_slugs_and_every_enabled_recipe_exists():
    sources = load_sources()
    slugs = [s.slug for s in sources]
    assert len(slugs) == len(set(slugs))
    for s in sources:
        if s.mode == "recipe" and s.enabled:
            assert Path(s.recipe_path).exists(), s.slug
            Recipe.load(s.recipe_path)
