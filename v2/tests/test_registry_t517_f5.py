"""T517 10/5 監査（群 F5）: 広島市・広島県・福山市・静岡県・石川県・島根県・豊中市・大阪府・山形県・愛知県わんにゃんナビのレシピと台帳（ネットワークなし）。

島根県の tests/fixtures/t517f5_shimane_*.html は 2026-10-05 に取った実ページ（犬 dobutu5・猫 dobutu7・知らせ syuyouari）から本文だけを抜いたもの。
ほかは同じ日の実ページの文言を小さい HTML に直書きしている。
"""

from pathlib import Path

from collector.extract import Result, build
from collector.fetch import FakeFetcher
from collector.recipe import Executor, Recipe, _make_doc
from collector.registry import Source, load_sources

FIX = Path(__file__).parent / "fixtures"


def _load(slug: str) -> tuple[Source, Recipe]:
    src = next(s for s in load_sources() if s.slug == slug)
    recipe = Recipe.load(src.recipe_path)
    recipe.encoding = None
    return src, recipe


def _run(slug: str, pages: dict[str, str]) -> tuple[Source, Result]:
    src, recipe = _load(slug)
    ex = Executor(FakeFetcher(pages), recipe)
    docs = ex.resolve(src.url)
    return src, build(src, recipe, docs, ex.visited)


# --- 台帳の区分 -----------------------------------------------------------------------------
def test_registry_kinds_follow_the_page_wording():
    by = {s.slug: s for s in load_sources()}
    # 「元の飼い主さんに返すための情報提供」「迷い犬情報一覧」「迷子の犬・猫情報」は迷子（飼い主不明のまま保護）
    for slug in ("city_fukuyama-1", "pref_shizuoka", "pref_ishikawa"):
        assert by[slug].kind == "stray", slug
    assert by["city_fukuyama-1"].name == "福山市（迷い犬）"


# --- 広島市 ---------------------------------------------------------------------------------
HIROSHIMA_CITY = "https://www.city.hiroshima.lg.jp/living/pet-doubutsu/1021301/1026245/1037461.html"


def _hiroshima_city(h2: str) -> str:
    return (
        '<html><body><div id="voice"><p>案内</p>'
        f'<h2>{h2}</h2><p class="imagecenter"><img src="a.jpeg"></p>'
        "<dl><dt>収容月日</dt><dd>令和8年9月29日</dd><dt>種類</dt><dd>柴犬</dd><dt>推定年齢</dt><dd>4～5歳</dd>"
        "<dt>毛色</dt><dd>茶</dd><dt>性別</dt><dd>オス</dd><dt>拾得等の場所</dt><dd>安芸区畑賀町3丁目</dd><dt>備考</dt><dd>マイクロチップなし</dd></dl>"
        "</div></body></html>"
    )


def test_hiroshima_city_management_no_with_or_without_prefix():
    for h2, want in (("8-9-2", "8-9-2"), ("整理番号：8-9-12", "8-9-12"), ("整理番号:8-9-13", "8-9-13")):
        _, res = _run("city_hiroshima-1", {HIROSHIMA_CITY: _hiroshima_city(h2)})
        assert [a["management_no"] for a in res.animals] == [want], h2
        assert res.animals[0]["breed"] == "柴犬"


def test_hiroshima_city_management_no_ignores_other_headings():
    # 直前の見出しが数字で始まらない（「関連情報」等）ときは管理番号にしない
    _, res = _run("city_hiroshima-1", {HIROSHIMA_CITY: _hiroshima_city("関連情報")})
    assert len(res.animals) == 1 and res.animals[0]["management_no"] is None


# --- 広島県 ---------------------------------------------------------------------------------
HIROSHIMA_PREF = "https://www.pref.hiroshima.lg.jp/site/apc/jouto-stray-dog-list.html"


def test_hiroshima_pref_note_is_the_line_after_the_circumstances():
    html = (
        '<html><body><div class="detail_free"><p><strong>案内</strong></p><div><h2>管理番号：1HD20260205</h2>'
        '<p><img src="/uploaded/image/509535.JPG"></p>'
        "<p>雑種、推定13歳、雄<br>センターに収容された日：令和8年9月29日<br>"
        "保護された状況：令和8年9月27日 12 時半頃に三次市十日市中付近で保護されました。<br>保護時に茶色の皮の首輪を装着</p></div></div></body></html>"
    )
    _, res = _run("pref_hiroshima-1", {HIROSHIMA_PREF: html})
    a = res.animals[0]
    assert a["note"] == "保護時に茶色の皮の首輪を装着"
    assert a["location"] == "三次市十日市中付近" and a["management_no"] == "1HD20260205" and a["breed"] == "雑種"
    # 状況の次の行が無い子は note なし（別の項目を拾わない）
    html2 = html.replace("<br>保護時に茶色の皮の首輪を装着", "")
    _, res2 = _run("pref_hiroshima-1", {HIROSHIMA_PREF: html2})
    assert res2.animals[0]["note"] is None


# --- 豊中市 ---------------------------------------------------------------------------------
TOYONAKA = "https://www.city.toyonaka.osaka.jp/kurashi/pettp-inuneko/shuyou.html"
_TOYONAKA_NOTE = "<p>情報の更新は原則収容当日ですが、収容する時間帯によっては翌開庁日になることがあります。</p>"


def test_toyonaka_zero_is_confirmed_only_by_the_no_info_image():
    html = f'<html><body>{_TOYONAKA_NOTE}<div class="img-area"><img src="no_info.gif" alt="現在、掲載する情報はありません"></div></body></html>'
    _, res = _run("spec_city_toyonaka", {TOYONAKA: html})
    assert res.animals == [] and res.empty_confirmed


def test_toyonaka_constant_note_no_longer_hides_a_broken_page():
    # 動物がいる日も載っている案内文だけでは 0 頭と確定しない（構造が変わって行が取れない日は通知に載る）
    html = f'<html><body>{_TOYONAKA_NOTE}<div class="x"><img src="a.jpg"> 管理番号 A1</div></body></html>'
    _, res = _run("spec_city_toyonaka", {TOYONAKA: html})
    assert res.animals == [] and not res.empty_confirmed


def test_toyonaka_animal_day_still_reads():
    html = (f'<html><body>{_TOYONAKA_NOTE}<div class="img-area"><img src="a.jpg"><p>管理番号 A1 性別 オス 収容日 2026年10月3日 犬種 雑種 毛色 茶</p></div></body></html>')
    _, res = _run("spec_city_toyonaka", {TOYONAKA: html})
    assert [a["species"] for a in res.animals] == ["dog"] and not res.empty_confirmed


# --- 大阪府 ---------------------------------------------------------------------------------
OSAKA = "https://www.pref.osaka.lg.jp/o120200/doaicenter/doaicenter/maigoken.html"


def _osaka_table(date: str) -> str:
    return (
        '<table><tr><th>受付番号</th><td>26-00189</td></tr><tr><th>写真</th><td><img src="a.png"></td></tr>'
        f"<tr><th>収容日</th><td>{date}</td></tr><tr><th>収容場所</th><td>守口市竜田通</td></tr>"
        "<tr><th>種類</th><td>雑種</td></tr><tr><th>性別</th><td>去勢雄</td></tr></table>"
    )


def test_osaka_shelter_date_western_and_japanese_eras():
    for date, want in (("2026年10月3日", "2026年10月3日"), ("令和8年10月3日", "令和8年10月3日"), ("令和 8 年 10 月 3 日", "令和 8 年 10 月 3 日")):
        _, res = _run("pref_osaka", {OSAKA: f"<html><body><h4>猫</h4>{_osaka_table(date)}</body></html>"})
        assert [(a["species"], a["shelter_date"], a["location"]) for a in res.animals] == [("cat", want, "守口市竜田通")], date


# --- 山形県 ---------------------------------------------------------------------------------
YAMAGATA_HUB = "https://www.pref.yamagata.jp/020071/kenfuku/doubutsuaigo/aigo/kainushisagashi/keijiban.html"


def _yamagata(notes: str) -> dict[str, str]:
    hub = '<html><body><h2>県で保護・収容している動物の情報</h2><ul><li><a href="/m.html">最上</a></li></ul></body></html>'
    page = (
        '<html><body><div id="tmp_main"><table><tr><th>収容月日</th><th>保護した場所</th><th>種類</th><th>特徴</th><th>写真</th></tr>'
        f'<tr><td>R8.9.7</td><td>最上町赤倉ダム付近（R8.9.5）</td><td>柴犬</td><td>{notes}</td><td><img src="/i.jpg"></td></tr></table></div></body></html>'
    )
    return {YAMAGATA_HUB: hub, "https://www.pref.yamagata.jp/m.html": page}


def test_yamagata_color_from_the_notes_only_when_it_is_a_coat_color():
    _, res = _run("pref_yamagata", _yamagata("メス、5歳前後と推定、黒毛、しっぽ短め、首輪なし"))
    assert [(a["color"], a["sex"], a["age"]) for a in res.animals] == [("黒毛", "メス", "5歳前後と推定")]
    # 毛の長さ（短毛）や首輪の色（白い首輪）は毛色にしない
    _, res2 = _run("pref_yamagata", _yamagata("オス、3歳、短毛、白い首輪"))
    assert res2.animals[0]["color"] is None


# --- 愛知県わんにゃんナビ -----------------------------------------------------------------------
def _wannyan(basic: str):
    src, recipe = _load("wannyan_navi_aichi")
    html = (
        f"<html><body><div>No . 尾263012 尾張支所(一宮市) {basic} 特徴 人なつこい 管理番号 x</div>"
        '<img src="https://x/y.jpg?w=1024"><a>猫の飼い方講習会へ</a></body></html>'
    )
    return build(src, recipe, [_make_doc("https://wannyan-navi.pref.aichi.jp/?page=list_dc_m&no=1", html)])


def test_wannyan_size_is_the_weight_after_sex_and_none_without_weight():
    res = _wannyan("雑種 白黒 オス 4.20kg 10歳5ヵ月")
    a = res.animals[0]
    assert (a["size"], a["age"], a["sex"], a["color"]) == ("4.20kg", "10歳5ヵ月", "オス", "白黒")
    res2 = _wannyan("雑種 黒 オス 3歳4ヵ月")
    assert res2.animals[0]["size"] is None and res2.animals[0]["age"] == "3歳4ヵ月"


# --- 島根県 ---------------------------------------------------------------------------------
SHIMANE_DIR = "https://www.pref.shimane.lg.jp/infra/nature/animal/matsue_hoken/doubutu/"   # 台帳の url（リンクは /infra/… の絶対パスなので、辿った先もこの下）
SHIMANE_PAST = SHIMANE_DIR + "hogozyouhou_kakobunn/"


def _shimane_list(*items: tuple[str, str]) -> str:
    lis = "".join(f'<li><img alt="" class="img-icon" src="/images/page.png"><a href="{h}">{t}</a></li>' for h, t in items)
    return (
        f'<html><body><main><h1>保護情報（松江・安来）</h1>\n\n<ul class="page_list">{lis}</ul>\n\n<br>\n'
        f'<h2>フォルダ一覧</h2><ul><li><a href="{SHIMANE_PAST}">保護情報_過去分</a></li></ul></main></body></html>'
    )


def _fx(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def test_shimane_points_at_the_current_list_not_the_past_folder():
    src, _ = _load("pref_shimane")
    assert src.url == SHIMANE_DIR and "kakobunn" not in src.url


def test_shimane_empty_current_list_is_zero():
    # 現行一覧が空の日（10/5 の実物は <ul class="page_list"></ul>）。過去分のフォルダへのリンクは辿らない
    _, res = _run("pref_shimane", {SHIMANE_DIR: _shimane_list()})
    assert res.animals == [] and res.empty_confirmed


def _link(name: str, title: str) -> tuple[str, str]:
    return (f"/infra/nature/animal/matsue_hoken/doubutu/{name}.html", title)


def test_shimane_reads_one_animal_per_page_and_skips_the_dead_one_and_the_notice():
    pages = {
        SHIMANE_DIR: _shimane_list(
            _link("dobutu5", "動物情報（犬２) ＊安来（ 8月28日）"),
            _link("dobutu7", "動物情報（負傷猫２３）（ 9月 9日）"),
            _link("syuyouari", "【松江保健所】保護・収容情報はありません（ 9月17日）"),
        ),
        SHIMANE_DIR + "dobutu5.html": _fx("t517f5_shimane_dog.html"),
        SHIMANE_DIR + "dobutu7.html": _fx("t517f5_shimane_cat_dead.html"),
        SHIMANE_DIR + "syuyouari.html": _fx("t517f5_shimane_notice.html"),
    }
    _, res = _run("pref_shimane", pages)
    assert len(res.animals) == 1      # 収容後に死亡した猫と、空の表だけの知らせは載せない
    a = res.animals[0]
    assert a["species"] == "dog" and a["management_no"] == "26D4" and a["shelter_date"] == "令和8年8月28日"   # 全角の数字は半角にそろう（エンジンの正規化）
    assert a["location"] == "安来市切川町地内" and a["breed"] == "雑種" and a["sex"] == "オス" and a["color"] == "クリーム"
    assert a["size"] == "中" and a["age"] == "不明(成犬)" and a["note"] == "*マイクロチップなし"
    assert a["image_url"].endswith("/dobutu5.data/IMG_2382.jpeg")


def test_shimane_notice_only_day_is_zero_and_broken_list_is_not():
    pages = {
        SHIMANE_DIR: _shimane_list(_link("syuyouari", "【松江保健所】保護・収容情報はありません（ 9月17日）")),
        SHIMANE_DIR + "syuyouari.html": _fx("t517f5_shimane_notice.html"),
    }
    _, res = _run("pref_shimane", pages)
    assert res.animals == [] and res.empty_confirmed
    # 知らせでない題の項目があるのに行が取れない日は「読めなかった」（0 頭と確定しない）
    pages2 = {
        SHIMANE_DIR: _shimane_list(_link("x", "動物情報（犬９）")),
        SHIMANE_DIR + "x.html": "<html><body><h1>動物情報（犬９）</h1><p>工事中</p></body></html>",
    }
    _, res2 = _run("pref_shimane", pages2)
    assert res2.animals == [] and not res2.empty_confirmed
