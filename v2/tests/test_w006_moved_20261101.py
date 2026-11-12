"""W006 T624 見守り運転: 掲載元の引っ越しと一時停止への対応（2026-11-01。ネットワークなし）。

- 甲府市（city_kofu-1・-2）: 市のサイトが www.city.kofu.yamanashi.jp から www.city.kofu.lg.jp へ移った。旧 URL は 301 で新ページへ飛ぶが、
  fetch は登録ドメインが違う転送を「別のサイトへ転送された」として取得不能にするので、10/28 0:05 から failed。台帳の url を移転先にする（レシピは変えない）
- 福岡市（わんにゃんよかネット）: 全 URL が 2026-10-21 から HTTP 503（メンテナンス・再開時期は未定）。停止中の画面が案内する市の公式サイトの暫定ページ
  「センターに収容されている犬・猫」（www.city.fukuoka.lg.jp）を、新しい 2 件（city_fukuoka_interim-1・-2）で読む。元の wannyan_fukuoka-1・-2 は
  旧 URL のまま毎晩見に行くので、再開した日に「読めるようになった自治体」の通知が出る

fixture は 2026-10-27〜11-01 に保存した実ページから script・style を落としたもの。福岡の暫定ページには収容中の子の実例がまだ無い（今は犬 1 頭が返還済・猫 1 頭が死亡）ので、
収容中の子が載った形は「状況」の欄だけを書き換えた合成ページ（テスト名に synthetic）で確かめる。
"""

import dataclasses
import re
import sys
from pathlib import Path

import pytest
import yaml
from bs4 import BeautifulSoup
from collector.discover import load_known
from collector.extract import Result
from collector.fetch import FakeFetcher, Page, validate_response
from collector.notify import build_message
from collector.registry import load_sources
from collector.run import Collected, collect_one

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ops"))

import verify_registry as vr

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures"
SOURCES = {s.slug: s for s in load_sources(ROOT / "registry" / "sources.yaml")}


def _fx(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def _collect(slug: str, pages: dict[str, str | bytes], status: dict[str, int] | None = None) -> Collected:
    """台帳の url から入口を辿り、レシピで読む（本番の収集 collect_one と同じ流れ）。

    enabled は True に固定して読む。福岡の暫定 2 件は、元のサイトが再開したら台帳で enabled: false にして止める手順なので（台帳の note）、
    止めた後もレシピの試験が「無効」で落ちないようにする。台帳の enabled の値そのものは、旧 2 件が true のままであることだけを別の試験で見る。
    """
    return collect_one(dataclasses.replace(SOURCES[slug], enabled=True), FakeFetcher(pages, status=status))


def _res(c: Collected) -> Result:
    assert c.result is not None, c.error
    return c.result


def _pick(a: dict, *keys: str) -> dict:
    return {k: a.get(k) for k in keys}


def _text(html: str) -> str:
    return BeautifulSoup(html, "lxml").get_text(" ", strip=True)


def _swap(html: str, old: str, new: str, count: int = -1) -> str:
    """実ページの一部を置き換えた合成ページ。置き換えが実際に効いたことを確かめる（効かないと試験が素通りする）。"""
    assert old in html, old
    out = html.replace(old, new, count)
    assert out != html
    return out


def _on_the_page(slug: str, html: str) -> vr.GroupResult:
    """台帳の電話・所在地が url のページにあるか。ops/verify_registry.py と同じ判定を、保存したページで（ネットワークなし）。"""
    s = SOURCES[slug]

    def fetch(url: str) -> vr.Fetched:
        return vr.Fetched(url=url, html=html, error=None) if url == s.url else vr.Fetched(url=url, html=None, error="HTTP 404")

    return vr.verify_group(fetch, s.url, s.phone, s.address)


# --- 甲府市（city_kofu-1・-2） -----------------------------------------------------------------------------------------
KOFU_OLD = "https://www.city.kofu.yamanashi.jp/hokenjo/2019mayoiinuneko.html"
KOFU_NEW = "https://www.city.kofu.lg.jp/k053/p001733.html"
KOFU_PAGE = "w006_city_kofu_p001733_20261031.html"            # 2026-10-31 の移転先（保護しています 1 頭・探しています 55 頭）
KOFU_PAGE_OLD = "w006_city_kofu_2019mayoiinuneko_old_20261027.html"   # 10/27 の旧ホスト（直前まで正常。保護 1 頭・探し 52 頭）


def _table_ids(html: str, heading: str) -> list[str]:
    """レシピを使わず、h2 の見出しの後ろの最初の表から ID の欄（先頭の td が 6 桁の数字）を数える。公式の表の独立した数え直し。"""
    soup = BeautifulSoup(html, "lxml")
    h2 = next(h for h in soup.find_all("h2") if heading in h.get_text())
    ids = []
    for tr in h2.find_next("table").find_all("tr"):
        tds = tr.find_all("td")
        if tds and re.fullmatch(r"\d{6}", tds[0].get_text(strip=True)):
            ids.append(tds[0].get_text(strip=True))
    return ids


@pytest.mark.parametrize("slug", ["city_kofu-1", "city_kofu-2"])
def test_kofu_registry_follows_the_city_site_to_the_new_host(slug):
    s = SOURCES[slug]
    assert s.url == KOFU_NEW
    assert s.verified_phone_url == KOFU_NEW and s.verified_address_url == KOFU_NEW
    assert (s.phone, s.address) == ("055-237-2550", "〒400-0858 山梨県甲府市相生2丁目17番1号（健康支援センター2号館2階）")
    assert s.recipe == f"recipes/{slug}.yaml"       # レシピは変えない


def test_kofu_new_page_gives_one_protected_and_fifty_five_searching():
    html = _fx(KOFU_PAGE)
    c1 = _collect("city_kofu-1", {KOFU_NEW: html})
    assert c1.status == "ok", c1.error
    (a,) = _res(c1).animals
    assert _pick(a, "species", "management_no", "shelter_date", "location", "breed", "note", "image_url", "source_url") == {
        "species": "cat", "management_no": "251083", "shelter_date": "11月25日", "location": "甲府市後屋町地内", "breed": "雑種",
        "note": "キジトラ 太っている 爪の手入れがされている", "image_url": "https://www.city.kofu.lg.jp/images/24134/252082.jpeg",
        "source_url": KOFU_NEW}
    assert _table_ids(html, "保護しています") == ["251083"]

    c2 = _collect("city_kofu-2", {KOFU_NEW: html})
    assert c2.status == "ok", c2.error
    animals = _res(c2).animals
    assert len(animals) == 55
    assert [a["management_no"] for a in animals] == _table_ids(html, "探しています")     # 公式の表の ID と同じ順・同じ数
    by_no = {a["management_no"]: a for a in animals}
    assert _pick(by_no["261058"], "species", "breed", "sex", "age", "color", "shelter_date", "location", "name") == {
        "species": "cat", "breed": "雑種", "sex": "オス", "age": "3〜4歳", "color": "茶白", "shelter_date": "10月29日", "location": "和戸町地内",
        "name": "ポンキチ"}
    assert _pick(by_no["261055"], "species", "sex", "age", "color", "shelter_date", "location", "name") == {
        "species": "cat", "sex": "不妊メス", "age": "8歳", "color": "キジトラ", "shelter_date": "10月27日", "location": "羽黒町地内", "name": "ささ"}
    assert len({a["id"] for a in animals}) == 55


def test_kofu_page_before_the_move_is_read_by_the_same_recipes():
    # 10/27 の旧ホストの保存。移転で変わったのは CMS の外枠・画像のパス・探しています 3 頭の追加だけで、レシピはそのまま当たる（直前の正常日 1 頭と 52 頭）
    html = _fx(KOFU_PAGE_OLD)
    c1, c2 = _collect("city_kofu-1", {KOFU_NEW: html}), _collect("city_kofu-2", {KOFU_NEW: html})
    assert (c1.status, len(_res(c1).animals)) == ("ok", 1)
    assert (c2.status, len(_res(c2).animals)) == ("ok", 52)
    assert [a["management_no"] for a in _res(c2).animals] == _table_ids(html, "探しています")
    new_ids = {a["management_no"] for a in _res(_collect("city_kofu-2", {KOFU_NEW: _fx(KOFU_PAGE)})).animals}
    assert new_ids - {a["management_no"] for a in _res(c2).animals} == {"261054", "261055", "261058"}   # 増えたのはこの 3 頭だけ
    assert {a["management_no"] for a in _res(c2).animals} <= new_ids                                       # 消えた子はいない


def test_kofu_old_host_redirect_is_another_site_for_fetch():
    # 台帳の url を旧ホストのままにすると、301 の転送先は登録ドメインが違うので取得不能になる（だから url を移転先にする）
    page = Page(url=KOFU_OLD, final_url=KOFU_NEW, status=200, content=b"<html><body>" + b"x" * 600 + b"</body></html>",
                html="<html><body>x</body></html>", content_type="text/html")
    info = validate_response(page)
    assert info is not None and info.kind == "redirect"


@pytest.mark.parametrize("slug", ["city_kofu-1", "city_kofu-2"])
def test_kofu_phone_and_address_are_on_the_new_page(slug):
    r = _on_the_page(slug, _fx(KOFU_PAGE))
    assert vr.classify(r) == "match" and r.address_match == "full"
    assert vr.verified_urls(r) == (KOFU_NEW, KOFU_NEW)


def test_kofu_both_domains_are_known_to_discover():
    # 環境省のリンク集は甲府市を旧ドメインで載せている。台帳は新ドメイン。どちらも別ドメインの slug で載せている印を一覧に持つ
    known = load_known()
    assert known["city.kofu.yamanashi.jp"].status == "covered" and known["city.kofu.yamanashi.jp"].slugs == ["city_kofu-1", "city_kofu-2"]
    assert known["city.kofu.lg.jp"].status == "covered" and known["city.kofu.lg.jp"].slugs == ["city_kofu-1", "city_kofu-2"]


# --- 福岡市（わんにゃんよかネット停止中の暫定ページ） -------------------------------------------------------------------
FUKUOKA_DOG = "https://www.city.fukuoka.lg.jp/hofuku/dobutsukanri/life/doghoused-.html"
FUKUOKA_CAT = "https://www.city.fukuoka.lg.jp/hofuku/dobutsukanri/life/cathoused.html"
WANNYAN_DOG = "https://www.wannyan.city.fukuoka.lg.jp/yokanet/animal/animal_posts/index?type_id=1&sorting_id=4"
WANNYAN_CAT = "https://www.wannyan.city.fukuoka.lg.jp/yokanet/animal/animal_posts/index?type_id=2&sorting_id=4"
DOG_PAGE = "w006_city_fukuoka_doghoused_20261031.html"       # 犬 d1877（状況 返還済）の 1 件だけ。いま収容中の子は 0
CAT_PAGE = "w006_city_fukuoka_cathoused_20261031.html"       # 猫 ｃ1937（状況 死亡）の 1 件だけ
WANNYAN_503 = "w006_wannyan_fukuoka_503_20261031.html"       # 停止中の画面（HTTP 503・Retry-After 3600）
INTERIM = {"city_fukuoka_interim-1": (FUKUOKA_DOG, DOG_PAGE), "city_fukuoka_interim-2": (FUKUOKA_CAT, CAT_PAGE)}


def _dog(html: str) -> Collected:
    return _collect("city_fukuoka_interim-1", {FUKUOKA_DOG: html})


def _cat(html: str) -> Collected:
    return _collect("city_fukuoka_interim-2", {FUKUOKA_CAT: html})


def _ledger_notes() -> dict[str, str]:
    """台帳の note（Source 型は note を持たないので YAML を直接読む）。"""
    entries = yaml.safe_load((ROOT / "registry" / "sources.yaml").read_text(encoding="utf-8"))["sources"]
    return {e["slug"]: e.get("note", "") for e in entries}


def test_fukuoka_interim_entries_are_added_and_the_wannyan_entries_stay_on_the_old_host():
    d, c = SOURCES["city_fukuoka_interim-1"], SOURCES["city_fukuoka_interim-2"]
    # 暫定 2 件の enabled はここで固定しない（元のサイトが再開したら、まず enabled: false にして二重掲載を止める手順が台帳の note にある）
    assert (d.url, d.species, d.kind, d.mode) == (FUKUOKA_DOG, "dog", "sheltered", "recipe")
    assert (c.url, c.species, c.kind, c.mode) == (FUKUOKA_CAT, "cat", "sheltered", "recipe")
    assert d.recipe == c.recipe and d.recipe_path.exists()
    # 元の 2 件は旧 URL・旧レシピのまま有効（毎晩旧ホストを見るので、再開した日に「読めるようになった自治体」が出る）。これは止めない
    w1, w2 = SOURCES["wannyan_fukuoka-1"], SOURCES["wannyan_fukuoka-2"]
    assert (w1.url, w1.enabled, w1.mode, w1.recipe) == (WANNYAN_DOG, True, "recipe", "recipes/wannyan_fukuoka-1.yaml")
    assert (w2.url, w2.enabled, w2.mode, w2.recipe) == (WANNYAN_CAT, True, "recipe", "recipes/wannyan_fukuoka-2.yaml")


def test_fukuoka_notes_say_how_to_notice_the_return_and_how_to_stop():
    # reviewer F-02: 再開の合図は 2 つ（Discord の「読めるようになった」と、wannyan_fukuoka-1 のエラーが HTTP 503 でなくなること）。
    # 再開を見つけたら、まず暫定 2 件を enabled: false にして二重掲載を即日止め、削除はその後。暫定ページ上部の「更新日」が止まったままなら暫定側を止める目安。
    # 4 件のどの note を読んでも手順が分かるように、同じ手順を 4 件に書く
    notes = _ledger_notes()
    for slug in ("wannyan_fukuoka-1", "wannyan_fukuoka-2", "city_fukuoka_interim-1", "city_fukuoka_interim-2"):
        note = notes[slug]
        assert "読めるようになった自治体" in note, slug
        assert "HTTP 503" in note and "wannyan_fukuoka-1" in note, slug
        assert "enabled: false" in note and "削除はその後" in note, slug
        assert "更新日" in note, slug
        assert "city_fukuoka_interim-1・-2" in note, slug
    assert "台帳から消す" in notes["city_fukuoka_interim-1"] and "revert" in notes["city_fukuoka_interim-1"]


def test_fukuoka_notes_say_what_to_do_when_the_citys_zero_day_wording_shows_up():
    # reviewer F-06: 市のページが 0 頭の日（ブロックが 1 つも無い日）の文言は未確認。出たらその日のページを保存して empty_text を足す
    # 犬のページ（-1）は 2026-11-06 に文言を確認して empty_absent を置いた（#93）。猫のページ（-2）は未確認のまま
    notes = _ledger_notes()
    assert "ブロックが 1 つも無い日" in notes["city_fukuoka_interim-2"] and "empty_text を足す" in notes["city_fukuoka_interim-2"]
    assert "その日のページを保存して empty_absent か empty_text を直す" in notes["city_fukuoka_interim-1"]


def test_fukuoka_note_cites_the_date_and_url_of_the_link_clause_check():
    # reviewer F-07: 「反証担当が確認」でなく、日付と URL で出典を示す
    note = _ledger_notes()["city_fukuoka_interim-1"]
    assert "2026-11-01 確認（https://www.city.fukuoka.lg.jp/sub/tyosakuken.html）" in note
    assert "反証担当が確認" not in note


@pytest.mark.parametrize("slug", sorted(INTERIM))
def test_fukuoka_interim_phone_and_address_are_only_what_the_page_says(slug):
    # T628: 電話・所在地は掲載元ページに書いてあるものだけ（郵便番号と「東部動物愛護管理センター」は暫定ページに無いので載せない）
    url, page = INTERIM[slug]
    s = SOURCES[slug]
    assert s.phone == "092-691-0131" and "〒" not in (s.address or "") and "東部" not in (s.address or "")
    r = _on_the_page(slug, _fx(page))
    assert vr.classify(r) == "match" and r.address_match == "full"
    assert vr.verified_urls(r) == (url, url)
    assert s.verified_phone_url == url and s.verified_address_url == url


# 2026-11-13: 市のページが 11/12 から表と h3 の管理番号の作りに変わり、レシピを今の作りに合わせた。前の作り（このファイルの
# 2026-10-31 の保存ページ）で子を読む試験（状況の書き換え・除外語・備考の死亡・品種と毛色の 1 欄・状況の項目名の変更）は、
# 同じ性質を今の作りの実ページで確かめる試験に置き換えた（tests/test_w006_fix_20261113.py の福岡市の節）。
# 下の 3 つは前の作りのページでも「0 頭にしない（failed）」ことを確かめる試験で、今のレシピでもそのまま成り立つので残す。
def test_fukuoka_a_page_without_any_animal_block_is_not_zero():
    # 一覧に 1 頭もいない日の文言は未確認。ブロックが 1 つも無いページは 0 頭にせず、読めなかったことにする
    html = _fx(DOG_PAGE)
    start = html.index('<div class="f_parallel2">')
    c = _dog(html[:start] + html[html.index("<p>&nbsp;</p>", start):])
    assert c.status == "failed" and _res(c).animals == []


def test_fukuoka_changed_structure_is_not_zero():
    dog = _fx(DOG_PAGE)
    for broken in (_swap(dog, "<h2>収容犬一覧</h2>", "<h2>一覧</h2>"),          # 一覧の見出しが変わった
                   _swap(dog, "<li>管理番号 ", "<li>番号 ")):                    # 項目名が変わった
        c = _dog(broken)
        assert c.status == "failed" and _res(c).animals == []


def test_fukuoka_blocks_that_cannot_be_read_are_not_zero():
    # 管理番号の欄が読めず写真も無い子は、除外語に当たらないので「全部除外」にならない（読めなかったことにする）
    html = _swap(_swap(_fx(CAT_PAGE), "<li>死亡</li>", "<li></li>"), "<li>ｃ1937</li>", "<li></li>")
    c = _cat(html)
    assert c.status == "failed" and _res(c).animals == []


def test_fukuoka_wannyan_maintenance_screen_is_a_failure_so_the_old_entries_watch_for_the_return():
    html = _fx(WANNYAN_503)
    assert "メンテナンス中" in _text(html)
    for slug, url in (("wannyan_fukuoka-1", WANNYAN_DOG), ("wannyan_fukuoka-2", WANNYAN_CAT)):
        c = _collect(slug, {url: html}, status={url: 503})
        assert c.status == "failed"
        assert c.error_info is not None and (c.error_info["kind"], c.error_info["status"]) == ("http", 503)


def test_fukuoka_the_return_of_the_old_entries_is_reported_the_next_morning():
    # 旧 2 件が前日 failed・今日 ok になった日の通知（run の report と state の形）。interim の 2 件はその間ずっと ok のまま
    names = {s: SOURCES[s].name for s in ("wannyan_fukuoka-1", "wannyan_fukuoka-2", "city_fukuoka_interim-1")}
    report = [{"slug": "wannyan_fukuoka-1", "name": names["wannyan_fukuoka-1"], "status": "ok", "count": 3, "error": None},
              {"slug": "wannyan_fukuoka-2", "name": names["wannyan_fukuoka-2"], "status": "empty", "count": 0, "error": None},
              {"slug": "city_fukuoka_interim-1", "name": names["city_fukuoka_interim-1"], "status": "empty", "count": 0, "error": None}]
    state = {"sources": {"wannyan_fukuoka-1": {"prev_status": "failed"}, "wannyan_fukuoka-2": {"prev_status": "failed"},
                         "city_fukuoka_interim-1": {"prev_status": "empty"}}}
    msg = build_message(report, state)
    assert msg is not None and "読めるようになった自治体 2 件" in msg
    assert names["wannyan_fukuoka-1"] in msg and names["wannyan_fukuoka-2"] in msg and names["city_fukuoka_interim-1"] not in msg


def test_fukuoka_discover_knows_the_citys_own_domain():
    k = load_known()["city.fukuoka.lg.jp"]
    assert k.status == "covered" and k.slugs == ["city_fukuoka_interim-1", "city_fukuoka_interim-2"]
    assert "wannyan" in k.note       # リンク集が指すのは wannyan.city.fukuoka.lg.jp。台帳の元の 2 件がそのドメインのまま
