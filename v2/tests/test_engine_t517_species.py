"""T517 ⑧ 動物種の欄が無い表で、品種・毛色から犬猫が確実に言える子だけを拾う（ネットワークなし）。

山口県 周南健康福祉センター（10022.html）の表は 2023 年 3 月から「動物種」欄が無く、犬猫が混在する。
species に infer: true を書いたレシピだけ、行内の語で決まらない行を品種・毛色の欄の語（柴・チワワ・キジトラ・三毛 等）で決める。
大きさ（小・中・大、小型・中型・大型）は猫にも使われる（周南の 8-3-99 は猫で「小」）ので使わない。
"""

from bs4 import BeautifulSoup

from collector.extract import build, infer_species
from collector.recipe import Doc, Recipe
from collector.registry import Source


def _doc(html: str, url: str = "https://www.pref.yamaguchi.lg.jp/site/doubutuaigo/10022.html") -> Doc:
    return Doc(url=url, html=html, soup=BeautifulSoup(html, "lxml"))


def _src() -> Source:
    return Source(slug="t", name="t", municipality="t", prefecture="山口県", url="https://x.jp/a/", kind="sheltered", species="mixed")


def _table(no: str, img: str, breed: str, size: str, color: str, place: str = "下松市西豊井", species: str | None = None) -> str:
    """周南の 1 頭 = table 1 つ（2026-10-05 の実ページから。写真セルは rowspan）。species を渡すと他センターと同じ「動物種」行を足す。"""
    sp = f"<tr><td>動物種</td><td>{species}</td></tr>" if species else ""
    return f"""<table style="width:92%"><tbody>
<tr><td>管理番号</td><td><p>{no}</p></td><td rowspan="10"><p><img alt="{no.split('-')[-1]}" src="/uploaded/image/{img}.jpg">​</p></td></tr>
<tr><td>掲載年月日</td><td>R8.10.1</td></tr>
<tr><td>保護場所</td><td>{place}</td></tr>{sp}
<tr><td>品種</td><td>{breed}</td></tr>
<tr><td>性別</td><td>オス</td></tr>
<tr><td>大きさ</td><td>{size}</td></tr>
<tr><td>毛色</td><td>{color}</td></tr>
<tr><td>その他の特徴</td><td></td></tr>
</tbody></table>"""


def _page(*tables: str) -> str:
    return '<div id="main_body"><div class="detail_free"><p>保護・収容している犬・猫の情報を掲載しています。</p>' + "<p></p>".join(tables) + "</div></div>"


def _recipe(infer: bool = True) -> Recipe:
    species: dict[str, object] = {"from": "field", "map": {"犬": "dog", "猫": "cat"}}
    if infer:
        species["infer"] = True
    return Recipe.from_dict({
        "rows": "table",
        "fields": {
            "management_no": {"label": "管理番号", "regex": "\\d+-\\d+-\\d+"},
            "location": {"label": "保護場所"},
            "breed": {"label": "品種"},
            "size": {"label": "大きさ"},
            "color": {"label": "毛色"},
            "species": {"label": "動物種"},
        },
        "species": species,
    })


def _by_no(res: object) -> dict[str, str | None]:
    return {a["management_no"]: a["species"] for a in res.animals}  # type: ignore[attr-defined]


# --- 決まる子 ------------------------------------------------------------------
def test_infer_cat_from_cat_only_coat_name():
    # 2025-12-01 の周南（Wayback）: 7-3-185 / 7-3-187 は品種「雑種」・毛色「キジトラ」・大きさ「中」で動物種欄なし
    page = _page(_table("7-3-185", "143818", "雑種", "中", "キジトラ"), _table("7-3-187", "143868", "雑種", "中", "キジトラ"))
    res = build(_src(), _recipe(), [_doc(page)])
    assert _by_no(res) == {"7-3-185": "cat", "7-3-187": "cat"}


def test_infer_dog_from_breed_name():
    page = _page(_table("8-3-120", "152100", "柴犬", "中", "赤"), _table("8-3-121", "152101", "ミックス(チワワ系)", "小", "白茶"))
    res = build(_src(), _recipe(), [_doc(page)])
    assert _by_no(res) == {"8-3-120": "dog", "8-3-121": "dog"}


def test_infer_cat_from_breed_name_and_species_word_in_breed():
    page = _page(_table("8-3-122", "152102", "スコティッシュフォールド", "中", "グレー"), _table("8-3-123", "152103", "雑種(三毛猫)", "小", "白黒茶"))
    res = build(_src(), _recipe(), [_doc(page)])
    assert _by_no(res) == {"8-3-122": "cat", "8-3-123": "cat"}


# --- 決めない子 -------------------------------------------------------------------
# T518（2026-10-05 おまえさん判断）で仕様変更: 決まらない子は「犬か猫か分からない」で捨てずに、種別なし（species: None）で載せる。
# 「決めない」ことの確認は変えず、捨てる → None で載る、に期待値だけ変えた
def test_shunan_20261005_rows_stay_undetermined():
    # 2026-10-05 の実ページそのまま。8-3-99 だけ猫（写真で確認）だが、品種・大きさ・毛色に犬猫を分ける語が無い
    page = _page(
        _table("8-3-98", "152043", "雑種", "小", "白茶"),
        _table("8-3-99", "152045", "雑種", "小", "黒白", place="周南市月丘町"),
        _table("8-3-100", "152044", "雑種", "中", "うす茶", place="周南市徳山"),
        _table("8-3-101", "152088", "雑種", "小", "白茶"),
    )
    res = build(_src(), _recipe(), [_doc(page)])
    assert _by_no(res) == {"8-3-98": None, "8-3-99": None, "8-3-100": None, "8-3-101": None}
    assert res.dropped == []


def test_dog_and_cat_words_together_are_not_decided():
    page = _page(_table("8-3-124", "152104", "柴系雑種", "中", "三毛"))
    res = build(_src(), _recipe(), [_doc(page)])
    assert _by_no(res) == {"8-3-124": None}


def test_ambiguous_words_are_not_used():
    # 茶トラ・サビ・虎・ブリンドルは犬にも使われた例がある（山梨「黒(お尻の部分が茶トラ)」・高知「茶サビ」・甲斐犬の「虎毛」）
    for color in ["茶トラ", "茶サビ", "虎毛", "トラ柄", "黒白", "白茶"]:
        assert infer_species({"breed": "雑種", "color": color, "size": "小型"}) is None, color
    for breed in ["雑種", "MIX", "ミックス", "不明", "雑"]:
        assert infer_species({"breed": breed, "color": "茶", "size": "大型"}) is None, breed


def test_only_breed_and_color_fields_are_looked_at():
    # 保護場所「柴田町」の「柴」で犬にしない
    page = _page(_table("8-3-125", "152105", "雑種", "中", "茶白", place="宮城県柴田町"))
    res = build(_src(), _recipe(), [_doc(page)])
    assert _by_no(res) == {"8-3-125": None}


# --- 既存の挙動 -----------------------------------------------------------------
def test_without_infer_coat_name_is_not_decided():
    page = _page(_table("7-3-185", "143818", "雑種", "中", "キジトラ"))
    res = build(_src(), _recipe(infer=False), [_doc(page)])
    assert _by_no(res) == {"7-3-185": None}


def test_species_field_wins_over_inference():
    # 他センターの表は「動物種」欄がある。欄で決まればそれを使う（推定は欄で決まらない行だけ）
    page = _page(_table("8-4-34", "151980", "雑種", "中", "キジトラ", species="犬"))
    res = build(_src(), _recipe(), [_doc(page)])
    assert _by_no(res) == {"8-4-34": "dog"}
