"""UI 刷新（2026-11-15。agy と作った試作プレビューの UI・文言・動線を本番の build.py に移す。ネットワークなし）。

- 区分は利用者の目的で 2 つ: 里親募集（adoption）と迷子情報（sheltered・stray・lost）。バッジは 里親募集・保護中・飼い主が探してます（保護中は市民が保護している子もいるので場所を断定しない）
- トップ: 地域を探す見出し、3 タブ（すべて・里親募集・迷子情報）、地方ブロックごとの 47 都道府県タイル（0 頭は薄く出す）、前回見た地域
- 都道府県ページは 0 頭の県も含めて 47 すべて作る。目的の 2 タブ・迷子の内訳・種別・1 列/2 列。状態は戻ったときに復元する
- カード: 区分と種別のバッジ・名前（無ければ名無しの犬。飼い主が探してますの子は迷子の犬）・性別/年齢/種類・掲載元・メモ。日付・場所・大きさ・管理番号は出さない
- 個体ページ: この子の情報（固定順・大きさは出さない）→ 掲載元・所在地 → 連絡の枠。枠の外に日付の脚注
- フッターは 3 リンク・2 行の注記・ブランドだけ（GitHub は外す）。幅は 860px
"""
from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pytest
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).parent / "fixtures"
CONFIG = {"site_name": "oneco", "base_url": "https://oneco.pages.dev", "affiliate": []}


def _mod():
    spec = importlib.util.spec_from_file_location("oneco_site_build_ui_1115", ROOT / "site" / "build.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


B = _mod()
SAGA = json.loads((FIX / "animals_saga.json").read_text(encoding="utf-8"))
BASE: dict[str, Any] = SAGA["animals"][0]   # 佐賀県・保護中の犬・雑種・オス・推定約5歳・黒茶(長毛)・中・多久市東多久町・電話あり・写真あり


def _a(id_: str, **kw: Any) -> dict[str, Any]:
    return {**BASE, "id": id_, **kw}


def _build(tmp_path: Path, animals: list[dict[str, Any]], sources: list[dict[str, Any]] | None = None,
           cfg: dict[str, Any] | None = None) -> Path:
    data = {"date": "2026-11-15", "animals": animals, "sources": sources or SAGA["sources"]}
    out = tmp_path / "dist"
    B.build_site(data, cfg or CONFIG, out)
    return out


def _read(out: Path, rel: str) -> str:
    return (out / rel).read_text(encoding="utf-8")


def _pref(out: Path, pref: str = "佐賀県") -> str:
    return _read(out, f"pref/{pref}/index.html")


def _animal(out: Path, id_: str) -> str:
    return _read(out, f"animals/{id_}/index.html")


def _card(html: str, id_: str) -> str:
    m = re.search(rf'<a class="card" href="/animals/{id_}/".*?</a>\n', html, re.S)
    assert m, id_
    return m.group(0)


def _main(html: str) -> str:
    return html.split("<main", 1)[1].split("</main>", 1)[0]


def _text(html: str) -> str:
    return BeautifulSoup(html, "lxml").get_text(" ", strip=True)


# --- 区分 ----------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("kind,label,group", [
    ("adoption", "里親募集", "adopt"),
    ("sheltered", "保護中", "missing"),
    ("stray", "保護中", "missing"),
    ("lost", "飼い主が探してます", "missing"),
])
def test_kinds_are_shown_as_two_purposes(tmp_path: Path, kind: str, label: str, group: str):
    out = _build(tmp_path, [_a("kind00000001", kind=kind)])
    card = _card(_pref(out), "kind00000001")
    assert f'<span class="badge kd-{kind}">{label}</span>' in card
    assert f'data-group="{group}"' in card
    assert f'<span class="badge kd-{kind}">{label}</span>' in _animal(out, "kind00000001")
    assert "施設で保護中" not in _pref(out) + _animal(out, "kind00000001")   # 市民が保護している子もいる（#126 reviewer F-01・Codex 3）


def test_sort_order_is_kept_adoption_first(tmp_path: Path):
    out = _build(tmp_path, [_a("lost00000001", kind="lost"), _a("stray0000001", kind="stray"),
                            _a("shel00000001", kind="sheltered"), _a("adop00000001", kind="adoption")])
    assert re.findall(r'<a class="card" href="/animals/([^/]+)/"', _pref(out)) == [
        "adop00000001", "shel00000001", "stray0000001", "lost00000001"]


# --- カード --------------------------------------------------------------------------------------------------------
def test_card_shows_only_badges_title_attrs_source_and_note(tmp_path: Path):
    a = _a("card00000001", name=None, sex="オス(去勢済)", age="推定約5歳", breed="雑種(キジ白)", color="黒茶(長毛)", size="中",
           management_no="MN-0099", shelter_date="2026年11月1日", location="多久市東多久町", note="人なつこい子です")
    card = _card(_pref(_build(tmp_path, [a])), "card00000001")
    assert '<div class="card-badges"><span class="badge kd-sheltered">保護中</span><span class="badge sp-dog">犬</span></div>' in card
    assert '<h3 class="card-title">名無しの犬</h3>' in card
    assert '<div class="attr-list"><span class="attr">オス</span><span class="attr">推定約5歳</span><span class="attr">雑種</span></div>' in card
    assert re.search(r'<p class="card-muni"><svg class="ico"[^>]*>.*?</svg><span>佐賀県</span></p>', card, re.S)
    assert '<p class="card-note">人なつこい子です</p>' in card
    for gone in ("黒茶", "中型", "MN-0099", "2026年11月1日", "多久市東多久町", "・"):
        assert gone not in _text(card), gone


def test_card_without_species_has_no_species_badge(tmp_path: Path):
    card = _card(_pref(_build(tmp_path, [_a("nosp00000001", species=None)])), "nosp00000001")
    assert 'class="badge sp-' not in card and '<h3 class="card-title">名無しの動物</h3>' in card
    assert 'data-species="none"' in card


@pytest.mark.parametrize("kw,want", [
    ({"name": "ポチ"}, "ポチ"),
    ({"name": None, "species": "dog"}, "名無しの犬"),
    ({"name": None, "species": "cat"}, "名無しの猫"),
    ({"name": None, "species": "other"}, "名無しの動物"),
    ({"name": None, "species": None}, "名無しの動物"),
    ({"name": "不明", "species": "cat"}, "名無しの猫"),
    ({"name": "  ", "species": "dog"}, "名無しの犬"),
    ({"name": "犬 探しています(フルサワ)", "note": "・名前:あの"}, "あの"),        # 告知の見出しは名前にしない（#124）
    ({"name": "譲渡猫R7ねー35", "management_no": "R7ねー35", "species": "cat"}, "名無しの猫"),
    # 飼い主が探してますの子には名前があるはずなので「名無し」と言わない（#126 Codex 7。2026-11-15 おまえさん決定）
    ({"name": None, "species": "dog", "kind": "lost"}, "迷子の犬"),
    ({"name": None, "species": "cat", "kind": "lost"}, "迷子の猫"),
    ({"name": None, "species": "other", "kind": "lost"}, "迷子の動物"),
    ({"name": None, "species": None, "kind": "lost"}, "迷子の動物"),
    ({"name": "ポチ", "species": "dog", "kind": "lost"}, "ポチ"),
    ({"name": None, "species": "dog", "kind": "stray"}, "名無しの犬"),
])
def test_card_title_is_the_name_or_nameless_species(kw: dict[str, Any], want: str):
    assert B.card_title(_a("x", **kw)) == want


@pytest.mark.parametrize("kw,want", [
    ({"sex": "オス(去勢済)", "age": "推定約5歳", "breed": "雑種"}, ["オス", "推定約5歳", "雑種"]),
    ({"sex": "去勢雄", "age": None, "breed": "MIX"}, ["オス", "雑種"]),
    ({"sex": "メス・不妊済み", "age": "3歳", "breed": None}, ["メス", "3歳"]),
    ({"sex": "オス、去勢済み", "age": None, "breed": "柴犬"}, ["オス", "柴犬"]),
    ({"sex": "♀", "age": "不明", "breed": "犬"}, ["メス"]),
    ({"sex": "メス:4匹 オス:2匹", "age": "10", "breed": "その他"}, []),           # 複数頭の欄・単位の無い数字・種別だけの品種は出さない
    ({"sex": "不明", "age": "2026年6月6日", "breed": "雑種(キジ白)"}, ["2026年6月6日生まれ", "雑種"]),
    ({"sex": "オス", "age": None, "breed": "不詳"}, ["オス"]),                     # 品種にも無効値を当てる（#126 Codex 6）
    ({"sex": "オス", "age": None, "breed": "なし"}, ["オス"]),
    ({"sex": "オス", "age": None, "breed": "無し"}, ["オス"]),
])
def test_card_attrs_are_sex_age_breed_in_this_order(kw: dict[str, Any], want: list[str]):
    assert B.card_attrs(_a("x", color="白", size="大", **kw)) == want


def test_meaningless_note_is_not_on_the_card(tmp_path: Path):
    out = _build(tmp_path, [_a("note00000001", note="無"), _a("note00000002", note="募集中"), _a("note00000003", note=None)])
    for id_ in ("note00000001", "note00000002", "note00000003"):
        assert "card-note" not in _card(_pref(out), id_)


def test_list_card_text_is_escaped(tmp_path: Path):
    out = _build(tmp_path, [_a("xss000000001", name="<b>ポチ</b>", note="<script>alert(1)</script>", municipality="A&B <市>")])
    h = _pref(out)
    assert "<script>alert(1)</script>" not in h and "&lt;script&gt;alert(1)&lt;/script&gt;" in h
    assert "<b>ポチ</b>" not in h and "&lt;b&gt;ポチ&lt;/b&gt;" in h
    assert "A&amp;B &lt;市&gt;" in h
    assert "innerHTML" not in h and "innerHTML" not in _read(out, "index.html")   # 状態や前回の県を HTML として差し込まない


# --- トップ --------------------------------------------------------------------------------------------------------
def _top_data(tmp_path: Path) -> Path:
    toku = json.loads((FIX / "animals_tokushima.json").read_text(encoding="utf-8"))
    animals = toku["animals"] + [_a("shel00000001"), _a("lost00000001", kind="lost", species="cat"),
                                 _a("othr00000001", species="other"), _a("nosp00000001", species=None)]
    return _build(tmp_path, animals, toku["sources"] + SAGA["sources"])


def test_top_hero_and_stats(tmp_path: Path):
    h = _read(_top_data(tmp_path), "index.html")
    assert "<h1>お住まいの地域の保護動物を探す</h1>" in h
    assert "保護犬・保護猫をはじめ、地域ごとの里親募集と迷子情報を毎日更新しています。" in h
    assert '<p class="hero-stats">2026年11月15日時点：犬 <b>21</b> ・ 猫 <b>1</b> ・ その他 <b>2</b></p>' in h


def test_top_stats_without_other_animals(tmp_path: Path):
    h = _read(_build(tmp_path, [_a("dog000000001")]), "index.html")
    assert '<p class="hero-stats">2026年11月15日時点：犬 <b>1</b> ・ 猫 <b>0</b></p>' in h


def test_top_has_three_tabs_and_no_species_filter(tmp_path: Path):
    h = _read(_top_data(tmp_path), "index.html")
    assert '<button type="button" class="tab-btn" data-top-tab="all" aria-pressed="true">すべて <span class="tab-cnt">24</span></button>' in h
    assert '<button type="button" class="tab-btn" data-top-tab="adopt" aria-pressed="false">里親募集 <span class="tab-cnt">20</span></button>' in h
    assert '<button type="button" class="tab-btn" data-top-tab="missing" aria-pressed="false">迷子情報 <span class="tab-cnt">4</span></button>' in h
    assert "data-sp=" not in h and "data-filter" not in h and "区分の意味" not in h


REGIONS = {
    "北海道・東北": ["北海道", "青森", "岩手", "宮城", "秋田", "山形", "福島"],
    "関東": ["東京", "神奈川", "埼玉", "千葉", "茨城", "栃木", "群馬"],
    "中部": ["新潟", "富山", "石川", "福井", "山梨", "長野", "岐阜", "静岡", "愛知"],
    "近畿": ["三重", "滋賀", "京都", "大阪", "兵庫", "奈良", "和歌山"],
    "中国・四国": ["鳥取", "島根", "岡山", "広島", "山口", "徳島", "香川", "愛媛", "高知"],
    "九州・沖縄": ["福岡", "佐賀", "長崎", "熊本", "大分", "宮崎", "鹿児島", "沖縄"],
}


def test_top_lists_all_47_prefectures_by_region(tmp_path: Path):
    soup = BeautifulSoup(_read(_top_data(tmp_path), "index.html"), "lxml")
    groups = soup.select("section.region-group")
    got = {g.select_one("h2.region-title").get_text(): [t.select_one(".pref-name").get_text() for t in g.select("a.pref-tile")]
           for g in groups}
    assert list(got) == list(REGIONS) and got == REGIONS
    tiles = soup.select("a.pref-tile")
    assert len(tiles) == 47 and {t["data-pref"] for t in tiles} == set(B.PREF_ORDER)
    for t in tiles:
        assert t["href"] == f"/pref/{quote(t['data-pref'])}/"


def test_top_tiles_carry_counts_per_tab_and_zero_prefectures_are_dimmed(tmp_path: Path):
    soup = BeautifulSoup(_read(_top_data(tmp_path), "index.html"), "lxml")
    tile = {t["data-pref"]: t for t in soup.select("a.pref-tile")}
    saga, toku, shimane = tile["佐賀県"], tile["徳島県"], tile["島根県"]
    assert (saga["data-all"], saga["data-adopt"], saga["data-missing"]) == ("4", "0", "4")
    assert (toku["data-all"], toku["data-adopt"], toku["data-missing"]) == ("20", "20", "0")
    assert saga.select_one(".pref-num").get_text() == "4頭" and "is-zero" not in saga["class"]
    assert "is-zero" in shimane["class"] and shimane.select_one(".pref-num").get_text() == "0頭"


def test_top_remembers_the_last_prefecture(tmp_path: Path):
    h = _read(_top_data(tmp_path), "index.html")
    assert '<a class="resume-box" id="resume" href="/" hidden>' in h and "前回見た地域" in h
    assert "localStorage.getItem('oneco_last_pref')" in h
    assert "encodeURIComponent" in h and "textContent" in h


# --- 都道府県ページ -------------------------------------------------------------------------------------------------
def test_every_prefecture_has_a_page_even_with_nothing_today(tmp_path: Path):
    out = _build(tmp_path, [_a("dog000000001")])
    for p in B.PREF_ORDER:
        assert (out / "pref" / p / "index.html").exists(), p
    sitemap = _read(out, "sitemap.xml")
    assert all(f"https://oneco.pages.dev/pref/{quote(p)}/" in sitemap for p in B.PREF_ORDER)
    shimane = _pref(out, "島根県")
    assert "<h1>島根県</h1>" in shimane
    box = BeautifulSoup(shimane, "lxml").select_one("#empty")
    assert box is not None and not box.has_attr("hidden") and "empty-box" in box["class"]
    assert box.get_text() == "現在掲載されている子はありません。自治体の公式ページに掲載がある場合もあるため、情報源の一覧もあわせてご確認ください。"
    assert box.select_one("a")["href"].startswith("/sources/")


def test_pref_header_has_back_link_date_and_neighbors(tmp_path: Path):
    h = _pref(_build(tmp_path, [_a("dog000000001")]))
    assert '<a class="back-link" href="/">‹ 地域を選ぶ</a>' in h
    assert '<span class="date-note">2026年11月15日時点</span>' in h
    assert "<h1>佐賀県</h1>" in h and "掲載元：" not in h
    nb = BeautifulSoup(h, "lxml").select_one(".neighbor-bar")
    assert nb.select_one(".neighbor-label").get_text() == "九州・沖縄"
    assert [c.get_text() for c in nb.select("a.neighbor-chip")] == REGIONS["九州・沖縄"]
    active = nb.select("a.neighbor-chip.active")
    assert [c.get_text() for c in active] == ["佐賀"] and active[0]["aria-current"] == "page"


def _btn(soup: BeautifulSoup, attr: str, value: str):
    return soup.select_one(f'button[data-{attr}="{value}"]')


def test_pref_has_two_purpose_tabs_with_counts(tmp_path: Path):
    out = _build(tmp_path, [_a("adop00000001", kind="adoption"), _a("shel00000001"), _a("lost00000001", kind="lost")])
    soup = BeautifulSoup(_pref(out), "lxml")
    assert _btn(soup, "tab", "adopt").get_text(" ", strip=True) == "里親募集 1"
    assert _btn(soup, "tab", "missing").get_text(" ", strip=True) == "迷子情報 2"
    assert _btn(soup, "tab", "adopt")["aria-pressed"] == "true"          # 里親募集がいれば里親募集から
    cards = {c["href"].split("/")[2]: c for c in soup.select("a.card")}
    assert not cards["adop00000001"].has_attr("hidden")
    assert cards["shel00000001"].has_attr("hidden") and cards["lost00000001"].has_attr("hidden")
    assert soup.select_one("#count").get_text() == "1"


def test_pref_opens_missing_tab_when_no_adoption(tmp_path: Path):
    soup = BeautifulSoup(_pref(_build(tmp_path, [_a("shel00000001"), _a("shel00000002")])), "lxml")
    assert _btn(soup, "tab", "missing")["aria-pressed"] == "true" and _btn(soup, "tab", "adopt")["aria-pressed"] == "false"
    assert soup.select_one("#list")["data-default-tab"] == "missing"
    assert soup.select_one("#count").get_text() == "2" and soup.select_one("#empty").has_attr("hidden")


def test_missing_sub_filter_only_when_there_are_lost_reports(tmp_path: Path):
    with_lost = BeautifulSoup(_pref(_build(tmp_path / "a", [_a("shel00000001"), _a("lost00000001", kind="lost")])), "lxml")
    seg = with_lost.select_one(".sub-seg")
    assert seg is not None and [b.get_text() for b in seg.select("button")] == ["すべて", "保護中", "飼い主が探してます"]
    assert [b["data-sub"] for b in seg.select("button")] == ["all", "shelter", "lost"]
    cards = {c["href"].split("/")[2]: c for c in with_lost.select("a.card")}
    assert cards["shel00000001"]["data-sub"] == "shelter" and cards["lost00000001"]["data-sub"] == "lost"
    no_lost = BeautifulSoup(_pref(_build(tmp_path / "b", [_a("shel00000001"), _a("stray0000001", kind="stray")])), "lxml")
    assert no_lost.select_one(".sub-seg") is None


def test_sub_filter_is_hidden_while_the_adoption_tab_is_open(tmp_path: Path):
    soup = BeautifulSoup(_pref(_build(tmp_path, [_a("adop00000001", kind="adoption"), _a("lost00000001", kind="lost")])), "lxml")
    assert soup.select_one(".sub-seg").has_attr("hidden")


def test_species_chips_offer_other_only_when_there_is_one(tmp_path: Path):
    plain = BeautifulSoup(_pref(_build(tmp_path / "a", [_a("dog000000001")])), "lxml")
    assert [b.get_text() for b in plain.select(".filter-row button")] == ["すべて", "犬", "猫"]
    assert plain.select_one('.chips[aria-label="動物の種類"]') is not None
    other = BeautifulSoup(_pref(_build(tmp_path / "b", [_a("dog000000001"), _a("othr00000001", species="other")])), "lxml")
    assert [b["data-sp"] for b in other.select(".filter-row button")] == ["all", "dog", "cat", "other"]
    nosp = BeautifulSoup(_pref(_build(tmp_path / "c", [_a("dog000000001"), _a("nosp00000001", species=None)])), "lxml")
    assert _btn(nosp, "sp", "other") is not None              # 種類の記載なしの子も「その他」で絞れる（2026-11-13 agy ⑤）
    assert _btn(nosp, "sp", "none") is None


def test_other_chip_is_hidden_when_the_open_tab_has_no_other(tmp_path: Path):
    soup = BeautifulSoup(_pref(_build(tmp_path, [_a("adop00000001", kind="adoption"), _a("othr00000001", species="other")])), "lxml")
    assert _btn(soup, "sp", "other").has_attr("hidden")


def test_view_bar_counts_and_toggles_one_or_two_columns(tmp_path: Path):
    h = _pref(_build(tmp_path, [_a("shel00000001"), _a("shel00000002")]))
    assert '<span aria-live="polite">該当 <b id="count">2</b> 頭</span>' in h
    soup = BeautifulSoup(h, "lxml")
    assert _btn(soup, "view", "list").get_text() == "1列表示" and _btn(soup, "view", "list")["aria-pressed"] == "true"
    assert _btn(soup, "view", "grid").get_text() == "2列表示" and _btn(soup, "view", "grid")["aria-pressed"] == "false"
    assert soup.select_one("#list")["class"] == ["animal-list"]
    css = B.CSS
    assert ".animal-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr))" in css
    assert re.search(r"@media \(min-width:600px\)\{\.animal-grid\{grid-template-columns:repeat\(3,minmax\(0,1fr\)\)", css)
    assert ".animal-grid .card-note{display:none}" in css


def test_old_kind_urls_open_the_matching_tab():
    # 旧 URL（?kind=lost 等。旧ページの絞り込みが URL に書いていた）は、区分に合うタブと内訳で開く（#126 Codex 1）
    js = B.PREF_JS
    assert "adoption:'adopt/all',sheltered:'missing/shelter',stray:'missing/shelter',lost:'missing/lost'" in js
    assert "Object.prototype.hasOwnProperty.call(KIND,kd)" in js


def test_url_rewrite_keeps_other_params_and_the_hash():
    # 初めに必ず replaceState するので、utm_ などの他のクエリとハッシュを消さない（GA4 の流入元が消えないように。#126 Codex）
    js = B.PREF_JS
    assert "['tab','sub','species','view','kind'].forEach(function(k){p.delete(k);})" in js
    assert "history.replaceState(history.state,'',location.pathname+'?'+p.toString()+location.hash)" in js


def test_unknown_tab_in_the_url_falls_back_to_the_default_tab():
    # ?tab=不正値 で来たら、サーバーが決めた初めのタブ（里親募集 0 頭なら迷子情報）に戻す（PR #126 reviewer F-02）
    assert "if(!known('tab'))state.tab=list.getAttribute('data-default-tab')||'adopt';" in B.PREF_JS


def test_cards_of_the_other_tab_are_reachable_without_javascript(tmp_path: Path):
    # JS が動かないと絞り込みのボタンは効かないので、隠していたカードを全部出し、効かないボタンは隠す（PR #126 reviewer F-03）
    h = _pref(_build(tmp_path, [_a("adop00000001", kind="adoption"), _a("shel00000001")]))
    head = h.split("</head>", 1)[0]
    m = re.search(r"<noscript><style>(.*?)</style></noscript>", head)
    assert m and ".card[hidden]{display:grid!important}" in m.group(1)
    for sel in (".tablist", ".sub-seg", ".filter-row", ".view-bar"):
        assert sel in m.group(1), sel


def test_pref_script_remembers_and_restores_the_view():
    js = B.PREF_JS
    assert "localStorage.setItem('oneco_last_pref'" in js            # トップの「前回見た地域」
    assert "sessionStorage" in js and "replaceState" in js          # 個体ページから戻ったときに状態を戻す
    assert "q.get('tab')" in js                                    # URL の tab はクエリを優先
    assert "fetch(" not in js and "innerHTML" not in js


# --- 個体ページ ----------------------------------------------------------------------------------------------------
FULL = {"name": None, "breed": "雑種", "color": "茶白", "sex": "オス", "age": "3歳", "size": "中", "shelter_date": "2026/11/1",
        "location": "多久市東多久町", "management_no": "D-12", "note": "人なつこい"}


def _dts(html: str, section: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    h2 = next(h for h in soup.select("h2.detail-sec") if h.get_text() == section)
    return [dt.get_text() for dt in h2.find_next_sibling("dl").select("dt")]


def test_detail_header_and_back_link(tmp_path: Path):
    h = _animal(_build(tmp_path, [_a("dog000000001", **FULL)]), "dog000000001")
    assert f'<a class="back-link" href="/pref/{quote("佐賀県")}/">‹ 佐賀県の一覧へ</a>' in h
    assert '<div class="card-badges"><span class="badge kd-sheltered">保護中</span><span class="badge sp-dog">犬</span></div>' in h
    assert '<h1 class="detail-title">名無しの犬</h1>' in h
    assert 'class="muni"' not in h and "kind-help" not in h


def test_detail_facts_are_in_a_fixed_order_without_size(tmp_path: Path):
    out = _build(tmp_path, [_a("dog000000001", **FULL), _a("lost00000001", kind="lost", **FULL)])
    assert _dts(_animal(out, "dog000000001"), "この子の情報") == ["種類", "毛色", "性別", "年齢", "保護日", "保護・発見場所", "管理番号", "メモ"]
    assert _dts(_animal(out, "lost00000001"), "この子の情報") == ["種類", "毛色", "性別", "年齢", "いなくなった日", "いなくなった場所", "管理番号", "メモ"]
    h = _animal(out, "dog000000001")
    assert "<dt>保護日</dt><dd>2026年11月1日</dd>" in h and "<dt>メモ</dt><dd>人なつこい</dd>" in h
    assert "大きさ" not in h and "中型" not in h and "<dt>名前</dt>" not in h


def test_detail_facts_skip_empty_values(tmp_path: Path):
    a = _a("dog000000001", **{**FULL, "color": "不明", "sex": "-", "age": "不明", "note": "無"})
    assert _dts(_animal(_build(tmp_path, [a]), "dog000000001"), "この子の情報") == ["種類", "保護日", "保護・発見場所", "管理番号"]


def test_detail_contact_section_and_action_card(tmp_path: Path):
    out = _build(tmp_path, [_a("shel00000001", address="佐賀市八丁畷町"), _a("adop00000001", kind="adoption")])
    h = _animal(out, "shel00000001")
    assert _dts(h, "掲載元・所在地") == ["掲載元", "所在地"]
    assert "<dt>掲載元</dt><dd>佐賀県</dd>" in h
    soup = BeautifulSoup(h, "lxml")
    card = soup.select_one(".action-card")
    assert card.select_one(".action-lead").get_text() == "お心当たりのある方は掲載元へご連絡ください"
    tel = card.select_one("a.btn-primary")
    assert tel["href"] == "tel:0952301350" and tel.get_text() == "0952-30-1350 に電話する"
    src = card.select_one("a.btn-secondary")
    assert src["href"] == BASE["source_url"] and src.get_text() == "自治体の公式ページを見る ↗"
    assert src["target"] == "_blank" and src["rel"] == ["noopener"]
    assert h.index("掲載元・所在地") < h.index('class="action-card"')
    lead = BeautifulSoup(_animal(out, "adop00000001"), "lxml").select_one(".action-lead").get_text()
    assert lead == "お迎えのご相談は掲載元の自治体へ"


def test_detail_without_phone_or_source(tmp_path: Path):
    out = _build(tmp_path, [_a("nophone00001", phone=None), _a("nosrc0000001", source_url="javascript:alert(1)")])
    h = _animal(out, "nophone00001")
    assert "<dt>電話</dt><dd>自治体のページでご確認ください</dd>" in h and "btn-primary" not in h
    s = _animal(out, "nosrc0000001")
    assert "btn-secondary" not in s and "javascript:" not in s
    assert "元ページの URL が取れていません。佐賀県にお問い合わせください。" in _text(s)


def test_detail_fine_print_is_outside_the_card(tmp_path: Path):
    out = _build(tmp_path, [_a("shel00000001"), _a("lost00000001", kind="lost")])
    h = _animal(out, "shel00000001")
    fine = '<p class="detail-fine">2026年11月15日時点の自治体公開情報です。<br>すでに飼い主さんの元に戻ったり、譲渡されたりしている場合があります。</p>'
    assert fine in h and h.index("</article>") < h.index(fine)
    assert "すでに見つかっている場合があります。</p>" in _animal(out, "lost00000001")


def test_photo_button_only_for_withheld_photos_with_a_source(tmp_path: Path):
    sources = SAGA["sources"] + [{**SAGA["sources"][0], "slug": "pref_saga-pending", "photo": "pending"}]
    out = _build(tmp_path, [_a("withheld0001", source="pref_saga-pending"),
                            _a("withheld0002", source="pref_saga-pending", source_url=None),
                            _a("nophoto00001", image_url=None)], sources)
    w = BeautifulSoup(_animal(out, "withheld0001"), "lxml").select_one(".detail-media .ph-btn")
    assert w is not None and w["href"] == BASE["source_url"] and w.get_text() == "自治体のページで写真を見る ↗"
    assert "ph-btn" not in _animal(out, "withheld0002") and "ph-btn" not in _animal(out, "nophoto00001")
    card = _card(_pref(out), "withheld0001")
    assert 'aria-label="写真は自治体のページでご確認ください"' in card and "写真は自治体の<br>ページでご確認<br>ください" in card


def test_detail_media_is_contained_not_cropped():
    css = B.CSS
    rule = css.split(".detail-media{", 1)[1].split("}", 1)[0]
    assert "aspect-ratio:4/3" in rule and "max-height:360px" in rule
    assert "object-fit:contain" in css.split(".detail-media img{", 1)[1].split("}", 1)[0]
    assert "object-fit:contain" in css.split(".thumb img{", 1)[1].split("}", 1)[0]
    assert "object-fit:cover" not in css


def test_affiliate_box_comes_after_the_fine_print(tmp_path: Path):
    cfg = {**CONFIG, "affiliate": [{"title": "ケージ", "url": "https://example.com/cage", "note": ""}]}
    h = _animal(_build(tmp_path, [_a("adop00000001", kind="adoption")], cfg=cfg), "adop00000001")
    assert h.index('class="detail-fine"') < h.index('<aside class="prep">')
    assert h.index("このページはアフィリエイト広告を利用しています") < h.index('<article class="detail-box"')


# --- ヘッダー・フッター・CSS ---------------------------------------------------------------------------------------------
def test_footer_has_three_links_a_two_line_note_and_the_brand(tmp_path: Path):
    out = _build(tmp_path, [_a("dog000000001")], cfg={**CONFIG, "repo_url": "https://github.com/9mak/oneco"})
    for rel in ("index.html", "pref/佐賀県/index.html", "animals/dog000000001/index.html", "about/index.html",
                "sources/index.html", "404.html"):
        foot = BeautifulSoup(_read(out, rel), "lxml").select_one("footer.site-foot")
        links = [(a.get_text(), a["href"]) for a in foot.select(".foot-links a")]
        assert links == [("このサイトについて", "/about/"), ("情報源の一覧", "/sources/"), ("運営への問い合わせ", "/contact/")], rel
        assert len(foot.select("a")) == 3, rel
        assert "github" not in str(foot).lower() and "取り下げ" not in foot.get_text(), rel
        assert "掲載情報は各自治体の公開データに基づきます。<br/>最新の状況は掲載元のページ・電話でご確認ください。" in str(foot.select_one(".foot-note"))
        brand = foot.select_one(".foot-brand")
        assert brand.select_one("img")["src"] == "/brand/oneco-mark.svg" and brand.select_one("img")["width"] == "18"
        assert brand.get_text(strip=True) == "oneco"
        assert "All Rights Reserved" not in _read(out, rel)


def test_header_keeps_brand_tagline_and_nav(tmp_path: Path):
    h = _read(_build(tmp_path, [_a("dog000000001")]), "index.html")
    assert '<span class="tagline">全国の保護動物情報をひとつに</span>' in h
    nav = BeautifulSoup(h, "lxml").select_one("header .nav")
    assert [(a.get_text(), a["href"]) for a in nav.select("a")] == [("都道府県", "/"), ("情報源", "/sources/"), ("このサイトについて", "/about/")]


def test_zero_tiles_are_dimmed_without_making_the_text_unreadable():
    # 0 頭の県も押せるリンクなので、全体を半透明にせず（文字のコントラスト 2.7:1 になる）、背景と枠と文字色で区別する（#126 Codex 4）
    rule = B.CSS.split(".pref-tile.is-zero{", 1)[1].split("}", 1)[0]
    assert "opacity" not in rule and "background:" in rule and "dashed" in rule


@pytest.mark.parametrize("sel", [".neighbor-chip{", ".ph-btn{", ".chip-btn{", ".sub-seg-btn{", ".view-toggle button{"])
def test_tap_targets_are_at_least_42px(sel: str):
    rule = B.CSS.split(sel, 1)[1].split("}", 1)[0]
    m = re.search(r"min-height:(\d+)px", rule)
    assert m and int(m.group(1)) >= 42, sel


def test_css_width_and_colors():
    css = B.CSS
    for sel in (".wrap{", ".site-head-in{", ".site-foot{"):
        assert "max-width:860px" in css.split(sel, 1)[1].split("}", 1)[0], sel
    assert "1040px" not in css
    assert "--lost:#ffedd5" in css and "--lost-ink:#9a3412" in css and "#ede9fe" not in css
    assert "--accent-soft:#f0f9ff" in css


# --- about・情報源 ---------------------------------------------------------------------------------------------------
def test_about_uses_the_new_category_names(tmp_path: Path):
    t = _text(_read(_build(tmp_path, [_a("dog000000001")]), "about/index.html"))
    for w in ("「里親募集」", "「迷子情報」", "「保護中」", "「飼い主が探してます」"):
        assert w in t, w
    assert "4 つに分けています" not in t and "施設で保護中" not in t
    assert "「保護中」（自治体の施設や、市民の方に保護されている子）" in t   # 千葉市・越谷市などの市民保護（T518）
    assert "「自治体の公式ページを見る」" in t and "自治体のページで詳細を見る" not in t


def test_sources_page_uses_the_new_category_names(tmp_path: Path):
    srcs = [{**SAGA["sources"][0], "slug": f"s-{k}", "name": f"テスト{k}", "municipality": "テスト市", "kind": k}
            for k in ("adoption", "stray", "lost")]
    t = _text(_read(_build(tmp_path, [], srcs), "sources/index.html"))
    assert "里親募集" in t and "保護中" in t and "飼い主が探してます" in t and "施設で保護中" not in t
    assert " 迷子 " not in t and "探してます" not in t.replace("飼い主が探してます", "")   # 旧呼称（迷子・探してます）は残さない
