"""AniwelOkinawaAdapter のテスト

沖縄県動物愛護管理センター (aniwel-pref.okinawa) 用 rule-based adapter の
動作を検証する。

- JS 描画必須サイトのため `PlaywrightFetchMixin` を併用する想定
  (テスト中は `_http_get` を patch して合成 HTML を返す)
- 6 サイト (収容/行方不明/迷い込み保護 × 犬/猫) を 1 adapter で束ねる
- 詳細ページ URL 形式: `/animals/{accommodate,missing,protection}_view/{ID}`
- 詳細ページは `<dl><dt><dd>` または `<table><th><td>` 形式
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from data_collector.adapters.municipality_adapter import ParsingError
from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.aniwel_okinawa import (
    AniwelOkinawaAdapter,
)
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig

# ─────────────────── サイト構成 ───────────────────

_SITE_DEFS: list[tuple[str, str, str, str]] = [
    # (name, list_url path, category, expected species)
    (
        "沖縄県動物愛護管理センター（収容犬）",
        "animals/accommodate/dogs",
        "sheltered",
        "犬",
    ),
    (
        "沖縄県動物愛護管理センター（収容猫）",
        "animals/accommodate/cats",
        "sheltered",
        "猫",
    ),
    (
        "沖縄県動物愛護管理センター（行方不明犬）",
        "animals/missing/dogs",
        "lost",
        "犬",
    ),
    (
        "沖縄県動物愛護管理センター（行方不明猫）",
        "animals/missing/cats",
        "lost",
        "猫",
    ),
    (
        "沖縄県動物愛護管理センター（迷い込み保護犬）",
        "animals/protection/dogs",
        "sheltered",
        "犬",
    ),
    (
        "沖縄県動物愛護管理センター（迷い込み保護猫）",
        "animals/protection/cats",
        "sheltered",
        "猫",
    ),
]

_BASE = "https://www.aniwel-pref.okinawa"


def _site(idx: int = 0) -> SiteConfig:
    name, path, category, _species = _SITE_DEFS[idx]
    return SiteConfig(
        name=name,
        prefecture="沖縄県",
        prefecture_code="47",
        list_url=f"{_BASE}/{path}",
        category=category,
        requires_js=True,
    )


# ─────────────────── 合成 HTML 生成 ───────────────────


def _list_html(view_prefix: str, ids: list[int]) -> str:
    """一覧ページ HTML を生成する

    Args:
        view_prefix: "accommodate" / "missing" / "protection"
        ids: 出力する詳細 ID のリスト
    """
    cards = "\n".join(
        f'<li><a href="/animals/{view_prefix}_view/{i}">詳細 {i}</a></li>' for i in ids
    )
    return f"""
    <html><body><main>
      <ul class="animal-list">
        {cards}
      </ul>
    </main></body></html>
    """


def _detail_html_dl(
    *,
    species: str = "犬",
    sex: str = "オス",
    age: str = "推定3歳",
    color: str = "茶",
    size: str = "中型",
    shelter_date: str = "2026年5月10日",
    location: str = "沖縄県動物愛護管理センター",
    phone: str = "098-945-3043",
    image_path: str = "/files/animals/1/photo.jpg",
) -> str:
    """`<dl>` 形式の詳細ページ HTML"""
    img = f'<figure><img src="{image_path}" alt="個体写真"/></figure>' if image_path else ""
    return f"""
    <html><body><main>
      {img}
      <dl>
        <dt>種類</dt><dd>{species}</dd>
        <dt>性別</dt><dd>{sex}</dd>
        <dt>年齢</dt><dd>{age}</dd>
        <dt>毛色</dt><dd>{color}</dd>
        <dt>大きさ</dt><dd>{size}</dd>
        <dt>収容日</dt><dd>{shelter_date}</dd>
        <dt>収容場所</dt><dd>{location}</dd>
        <dt>連絡先</dt><dd>{phone}</dd>
      </dl>
    </main></body></html>
    """


def _detail_html_table(**kwargs) -> str:
    """`<table>` 形式の詳細ページ HTML (label 経由抽出のフォールバック検証用)"""
    species = kwargs.get("species", "猫")
    sex = kwargs.get("sex", "メス")
    age = kwargs.get("age", "1歳")
    color = kwargs.get("color", "白黒")
    size = kwargs.get("size", "")
    shelter_date = kwargs.get("shelter_date", "2026-05-01")
    location = kwargs.get("location", "沖縄県動物愛護管理センター")
    phone = kwargs.get("phone", "0989453043")
    return f"""
    <html><body><main>
      <table>
        <tr><th>種類</th><td>{species}</td></tr>
        <tr><th>性別</th><td>{sex}</td></tr>
        <tr><th>年齢</th><td>{age}</td></tr>
        <tr><th>毛色</th><td>{color}</td></tr>
        <tr><th>大きさ</th><td>{size}</td></tr>
        <tr><th>収容日</th><td>{shelter_date}</td></tr>
        <tr><th>収容場所</th><td>{location}</td></tr>
        <tr><th>連絡先</th><td>{phone}</td></tr>
      </table>
    </main></body></html>
    """


# 実サイト (2026-05 時点) の `<table><th><td>` 構造を忠実に再現したフィクスチャ。
# 3 系統 (収容/行方不明/迷い込み) でラベルが異なるのが要点。
_REAL_DETAIL_ACCOMMODATE = """
<html><body><main>
  <table>
    <tr><th>記号</th><td>2026.5.25＿C-1</td></tr>
    <tr><th>収容日</th><td>2026年5月25日</td></tr>
    <tr><th>収容期限</th><td>2026年6月2日</td></tr>
    <tr><th>場所</th><td>読谷村儀間</td></tr>
    <tr><th>毛色</th><td>黒</td></tr>
    <tr><th>性別</th><td>オス</td></tr>
    <tr><th>体格</th><td>小</td></tr>
    <tr><th>推定年齢</th><td>3</td></tr>
    <tr><th>首輪</th><td>有り 青</td></tr>
    <tr><th>備考</th><td>Bw:2.7kg／マイクロチップ入り</td></tr>
  </table>
</main></body></html>
"""

_REAL_DETAIL_MISSING = """
<html><body><main>
  <table>
    <tr><th>受付番号</th><td>2026.5.26＿No.53</td></tr>
    <tr><th>行方不明日</th><td>2026年5月20日</td></tr>
    <tr><th>行方不明場所</th><td>那覇市 栄町リウボウ付近</td></tr>
    <tr><th>品種</th><td>雑種（ミケネコ）</td></tr>
    <tr><th>毛色</th><td>（キジトラ混じり）</td></tr>
    <tr><th>性別</th><td>不妊メス</td></tr>
    <tr><th>体格</th><td>大</td></tr>
    <tr><th>年齢</th><td>９才</td></tr>
    <tr><th>備考</th><td></td></tr>
  </table>
</main></body></html>
"""

_REAL_DETAIL_PROTECTION = """
<html><body><main>
  <table>
    <tr><th>受付番号</th><td>2026.5.25＿No.79</td></tr>
    <tr><th>受付月日</th><td>2026年5月26日</td></tr>
    <tr><th>迷い込んだ場所</th><td>沖縄県南城市</td></tr>
    <tr><th>品種</th><td>雑種</td></tr>
    <tr><th>毛色</th><td>茶</td></tr>
    <tr><th>性別</th><td>オス</td></tr>
    <tr><th>体格</th><td>中</td></tr>
    <tr><th>年齢</th><td>5か月程度</td></tr>
    <tr><th>保護日</th><td>2026年5月25日</td></tr>
  </table>
</main></body></html>
"""


# ─────────────────── テスト ───────────────────


class TestAniwelOkinawaAdapter:
    def test_six_sites_registered_to_same_adapter(self) -> None:
        """6 サイト全てが AniwelOkinawaAdapter にマップされている"""
        for name, *_ in _SITE_DEFS:
            assert SiteAdapterRegistry.get(name) is AniwelOkinawaAdapter

    def test_uses_playwright_fetch_mixin(self) -> None:
        """JS 描画必須サイトのため PlaywrightFetchMixin を継承している"""
        from data_collector.adapters.rule_based.playwright import (
            PlaywrightFetchMixin,
        )

        assert issubclass(AniwelOkinawaAdapter, PlaywrightFetchMixin)
        # WAIT_SELECTOR が定義されている
        assert AniwelOkinawaAdapter.WAIT_SELECTOR

    def test_fetch_animal_list_accommodate(self) -> None:
        """収容犬: accommodate_view/{ID} 形式の詳細リンクを抽出する"""
        adapter = AniwelOkinawaAdapter(_site(0))  # accommodate dogs
        html = _list_html("accommodate", [101, 102, 103])

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert len(result) == 3
        for (url, cat), expected_id in zip(result, [101, 102, 103], strict=False):
            assert url == f"{_BASE}/animals/accommodate_view/{expected_id}"
            assert cat == "sheltered"

    def test_fetch_animal_list_missing_lost_category(self) -> None:
        """行方不明猫: missing_view/{ID} で category=lost が伝播する"""
        adapter = AniwelOkinawaAdapter(_site(3))  # missing cats
        html = _list_html("missing", [7, 8])

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert len(result) == 2
        assert all(cat == "lost" for _, cat in result)
        assert all("/animals/missing_view/" in url for url, _ in result)

    def test_fetch_animal_list_protection(self) -> None:
        """迷い込み保護犬: protection_view/{ID} 形式も同 LIST_LINK_SELECTOR で拾える"""
        adapter = AniwelOkinawaAdapter(_site(4))  # protection dogs
        html = _list_html("protection", [200, 201])

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert len(result) == 2
        for url, _ in result:
            assert "/animals/protection_view/" in url

    def test_fetch_animal_list_dedupes(self) -> None:
        """同一 detail URL が複数現れた場合は重複排除される"""
        adapter = AniwelOkinawaAdapter(_site(0))
        html = _list_html("accommodate", [1, 2, 1, 2, 3])

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert len(result) == 3
        urls = [u for u, _ in result]
        assert len(set(urls)) == 3

    def test_fetch_animal_list_returns_empty_when_no_links(self) -> None:
        """detail link が 1 つも見つからない = 現在その種別の収容動物がいない真ゼロ"""
        adapter = AniwelOkinawaAdapter(_site(0))
        html = "<html><body><main>準備中</main></body></html>"

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()
        assert result == []

    def test_extract_animal_details_dl_format(self) -> None:
        """`<dl>` 形式の詳細ページから RawAnimalData を構築できる"""
        adapter = AniwelOkinawaAdapter(_site(0))  # accommodate dogs
        detail_url = f"{_BASE}/animals/accommodate_view/101"
        html = _detail_html_dl()

        with patch.object(adapter, "_http_get", return_value=html):
            raw = adapter.extract_animal_details(detail_url, category="sheltered")

        assert isinstance(raw, RawAnimalData)
        assert raw.species == "犬"
        assert raw.sex == "オス"
        assert raw.age == "推定3歳"
        assert raw.color == "茶"
        assert raw.size == "中型"
        assert raw.shelter_date == "2026年5月10日"
        assert raw.location == "沖縄県動物愛護管理センター"
        # 電話番号は正規化されハイフン区切り
        assert raw.phone == "098-945-3043"
        assert raw.source_url == detail_url
        assert raw.category == "sheltered"
        # 画像 URL は絶対 URL に変換される
        assert raw.image_urls
        assert all(u.startswith(_BASE) for u in raw.image_urls)

    def test_extract_animal_details_table_format(self) -> None:
        """`<table>` 形式の詳細ページでも label 経由で抽出できる"""
        adapter = AniwelOkinawaAdapter(_site(1))  # accommodate cats
        detail_url = f"{_BASE}/animals/accommodate_view/55"
        html = _detail_html_table()

        with patch.object(adapter, "_http_get", return_value=html):
            raw = adapter.extract_animal_details(detail_url, category="sheltered")

        assert raw.species == "猫"
        assert raw.sex == "メス"
        assert raw.age == "1歳"
        assert raw.color == "白黒"
        # 区切りなし 10 桁 → 3-3-4 形式に正規化
        assert raw.phone == "098-945-3043"

    def test_species_inferred_from_site_name_when_missing(self) -> None:
        """詳細ページに species が無い場合はサイト名から犬/猫を補完する"""
        adapter = AniwelOkinawaAdapter(_site(2))  # missing dogs
        detail_url = f"{_BASE}/animals/missing_view/9"
        # species を空 (種類 dt 自体を抜く) にしたバリエーション
        html = """
        <html><body><main>
          <dl>
            <dt>性別</dt><dd>不明</dd>
            <dt>毛色</dt><dd>白</dd>
            <dt>収容日</dt><dd>2026-05-12</dd>
            <dt>収容場所</dt><dd>那覇市</dd>
          </dl>
        </main></body></html>
        """

        with patch.object(adapter, "_http_get", return_value=html):
            raw = adapter.extract_animal_details(detail_url, category="lost")

        # サイト名「(行方不明犬)」から species=犬 が補完される
        assert raw.species == "犬"
        assert raw.sex == "不明"
        assert raw.color == "白"
        assert raw.category == "lost"

    def test_extract_raises_when_no_fields(self) -> None:
        """詳細ページから 1 フィールドも抽出できない場合は ParsingError"""
        adapter = AniwelOkinawaAdapter(_site(0))
        html = "<html><body><main>該当ページが見つかりません</main></body></html>"

        with patch.object(adapter, "_http_get", return_value=html):
            with pytest.raises(ParsingError):
                adapter.extract_animal_details(
                    f"{_BASE}/animals/accommodate_view/999",
                    category="sheltered",
                )

    def test_normalize_returns_animal_data(self) -> None:
        """normalize は RawAnimalData -> AnimalData 変換を行う"""
        adapter = AniwelOkinawaAdapter(_site(0))
        detail_url = f"{_BASE}/animals/accommodate_view/1"
        html = _detail_html_dl()

        with patch.object(adapter, "_http_get", return_value=html):
            raw = adapter.extract_animal_details(detail_url, category="sheltered")
            normalized = adapter.normalize(raw)

        # AnimalData に変換され、種別と prefecture が保持される
        assert normalized.species == "犬"
        assert normalized.category == "sheltered"

    def test_no_view_link_filter_excludes_unrelated_anchors(self) -> None:
        """`_view/` を含まない他カテゴリ遷移リンクは抽出されない"""
        adapter = AniwelOkinawaAdapter(_site(0))
        html = """
        <html><body><main>
          <nav>
            <a href="/animals/accommodate/dogs">収容犬</a>
            <a href="/animals/accommodate/cats">収容猫</a>
            <a href="/about">サイトについて</a>
          </nav>
          <ul>
            <li><a href="/animals/accommodate_view/1">詳細1</a></li>
            <li><a href="/animals/accommodate_view/2">詳細2</a></li>
          </ul>
        </main></body></html>
        """

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert len(result) == 2
        for url, _ in result:
            assert "_view/" in url


class TestAniwelOkinawaRealLabels:
    """実サイトの見出しラベルに対する抽出を検証する (2026-05 のブラウザ実査ベース)。

    収容(accommodate)/行方不明(missing)/迷い込み(protection) でラベルが異なり、
    旧実装は location='収容場所'・size='大きさ' 固定だったため実サイトの
    '場所'/'体格' に当たらず location が 100% '不明' になっていた回帰を防ぐ。
    """

    def test_accommodate_extracts_location_size_date(self) -> None:
        """収容: 場所/体格/収容日 を正しく取得する"""
        adapter = AniwelOkinawaAdapter(_site(0))  # 収容犬
        url = f"{_BASE}/animals/accommodate_view/24639"
        with patch.object(adapter, "_http_get", return_value=_REAL_DETAIL_ACCOMMODATE):
            raw = adapter.extract_animal_details(url, category="sheltered")
        assert raw.location == "読谷村儀間"
        assert raw.size == "小"
        assert raw.shelter_date == "2026年5月25日"
        assert raw.sex == "オス"
        assert raw.color == "黒"
        assert raw.species == "犬"  # サイト名から補完

    def test_missing_extracts_location_size_date(self) -> None:
        """行方不明: 行方不明場所/体格/行方不明日 を正しく取得する"""
        adapter = AniwelOkinawaAdapter(_site(3))  # 行方不明猫
        url = f"{_BASE}/animals/missing_view/24643"
        with patch.object(adapter, "_http_get", return_value=_REAL_DETAIL_MISSING):
            raw = adapter.extract_animal_details(url, category="lost")
        assert raw.location == "那覇市 栄町リウボウ付近"
        assert raw.size == "大"
        assert raw.shelter_date == "2026年5月20日"
        assert raw.species == "猫"  # サイト名から補完

    def test_protection_extracts_location_size_date(self) -> None:
        """迷い込み: 迷い込んだ場所/体格/保護日 を正しく取得する"""
        adapter = AniwelOkinawaAdapter(_site(4))  # 迷い込み保護犬
        url = f"{_BASE}/animals/protection_view/24644"
        with patch.object(adapter, "_http_get", return_value=_REAL_DETAIL_PROTECTION):
            raw = adapter.extract_animal_details(url, category="sheltered")
        assert raw.location == "沖縄県南城市"
        assert raw.size == "中"
        assert raw.shelter_date == "2026年5月25日"  # 受付月日(5/26)ではなく保護日(5/25)
        assert raw.species == "犬"

    def test_numeric_only_age_becomes_age_in_years(self) -> None:
        """「推定年齢: 12」のような数値単独表記を「12歳」と解釈する

        2026-05 観測: 沖縄県動愛の収容犬詳細では年齢欄に「12」(年齢=12歳の意)
        のみが書かれているケースがあり、normalizer は「3歳」「6ヶ月」の
        ような単位付き表記しか解釈できないため age_months=null になる。
        adapter 側で「N」を「N歳」に補完して normalizer に渡す。
        """
        adapter = AniwelOkinawaAdapter(_site(0))  # 収容犬
        url = f"{_BASE}/animals/accommodate_view/24647"
        html = """
        <html><body><main>
          <table>
            <tr><th>記号</th><td>2026.5.27＿H-1</td></tr>
            <tr><th>収容日</th><td>2026年5月27日</td></tr>
            <tr><th>場所</th><td>大宜味村大保</td></tr>
            <tr><th>毛色</th><td>黒茶</td></tr>
            <tr><th>性別</th><td>メス</td></tr>
            <tr><th>体格</th><td>中</td></tr>
            <tr><th>推定年齢</th><td>12</td></tr>
            <tr><th>備考</th><td>Bw:11kg</td></tr>
          </table>
        </main></body></html>
        """
        with patch.object(adapter, "_http_get", return_value=html):
            raw = adapter.extract_animal_details(url, category="sheltered")
            normalized = adapter.normalize(raw)
        assert raw.age == "12歳", f"adapter が「12」→「12歳」に補完: {raw.age!r}"
        assert normalized.age_months == 144, (
            f"normalizer が「12歳」→ 144 ヶ月: got {normalized.age_months}"
        )

    def test_numeric_with_kg_age_unchanged(self) -> None:
        """単位付きの年齢 (例: 「5か月程度」) は触らずに渡す (既存挙動の維持)"""
        adapter = AniwelOkinawaAdapter(_site(4))
        url = f"{_BASE}/animals/protection_view/24644"
        with patch.object(adapter, "_http_get", return_value=_REAL_DETAIL_PROTECTION):
            raw = adapter.extract_animal_details(url, category="sheltered")
        assert raw.age == "5か月程度"

    def test_image_urls_extracted_from_slick_slider(self) -> None:
        """`<td class="photo">` 内の slick スライダから動物写真を抽出する

        実サイトは `<td class="photo"><ul class="slick-main">...
        <img src="/files/animal/image/{ID}/large_image.JPG"></ul></td>` 構造。
        装飾画像 (`/images/header/`, `/images/sidebar/`, `pdf_icon.png` 等)
        と区別する必要がある。
        """
        adapter = AniwelOkinawaAdapter(_site(0))
        url = f"{_BASE}/animals/accommodate_view/24647"
        html = """
        <html><body><main>
          <table>
            <tr><th>場所</th><td>大宜味村大保</td></tr>
            <tr><th>体格</th><td>中</td></tr>
            <tr>
              <th>写真</th>
              <td class="photo">
                <ul class="slick-main">
                  <li><img src="/files/animal/image/24647/large_image.JPG" alt="枚目写真"></li>
                </ul>
                <ul class="slick-nav">
                  <li><img src="/files/animal/image/24647/large_image.JPG" alt="枚目写真"></li>
                </ul>
              </td>
            </tr>
          </table>
          <img src="/images/sidebar/balloon01.png" alt="">
          <img src="/images/animals/pdf_icon.png" alt="">
        </main></body></html>
        """
        with patch.object(adapter, "_http_get", return_value=html):
            raw = adapter.extract_animal_details(url, category="sheltered")
        assert raw.image_urls, "動物画像が抽出されるべき"
        assert all("/files/animal/image/" in u for u in raw.image_urls), (
            f"装飾画像 (/images/...) が混入: {raw.image_urls}"
        )
        # 重複 (slick-main と slick-nav の同一 src) は排除
        assert len(raw.image_urls) == len(set(raw.image_urls))


class TestAniwelOkinawaPhoneInjection:
    """沖縄県動物愛護管理センター本所の代表電話を共通注入する挙動を検証する。

    2026-06 観測 (https://www.aniwel-pref.okinawa/): 詳細ページの動物カード
    本文に電話番号が含まれず、snapshots では 91件全件で phone=null。
    運営は南城市の本所（およびハピアニおきなわ）で代表電話は同一の
    098-945-3043。サイト全体で共通の番号として注入する。
    """

    def test_phone_injected_when_detail_has_no_phone(self) -> None:
        """detail ページに連絡先記載が無いとき、本所代表電話を注入する"""
        adapter = AniwelOkinawaAdapter(_site(0))  # 収容犬
        url = f"{_BASE}/animals/accommodate_view/24639"
        with patch.object(adapter, "_http_get", return_value=_REAL_DETAIL_ACCOMMODATE):
            raw = adapter.extract_animal_details(url, category="sheltered")
        assert raw.phone == "098-945-3043", (
            f"本所代表電話が共通注入されるべき: got {raw.phone!r}"
        )

    def test_phone_injected_for_missing_category(self) -> None:
        """missing (行方不明) 系統でも同じ代表電話を注入する"""
        adapter = AniwelOkinawaAdapter(_site(3))  # 行方不明猫
        url = f"{_BASE}/animals/missing_view/24643"
        with patch.object(adapter, "_http_get", return_value=_REAL_DETAIL_MISSING):
            raw = adapter.extract_animal_details(url, category="lost")
        assert raw.phone == "098-945-3043"

    def test_phone_injected_for_protection_category(self) -> None:
        """protection (迷い込み保護) 系統でも同じ代表電話を注入する"""
        adapter = AniwelOkinawaAdapter(_site(4))  # 迷い込み保護犬
        url = f"{_BASE}/animals/protection_view/24644"
        with patch.object(adapter, "_http_get", return_value=_REAL_DETAIL_PROTECTION):
            raw = adapter.extract_animal_details(url, category="sheltered")
        assert raw.phone == "098-945-3043"

    def test_existing_phone_in_detail_is_preserved(self) -> None:
        """detail ページに電話番号が書かれている場合は上書きしない

        将来サイト側で個別連絡先が記載されるようになっても、
        共通注入は「空のときだけ」走るので個別値を保持する。
        """
        adapter = AniwelOkinawaAdapter(_site(0))  # 収容犬
        url = f"{_BASE}/animals/accommodate_view/101"
        # _detail_html_dl() は phone="098-945-3043" を含むが、わざと別番号にする
        # (parser の _normalize_phone を通る区切りなし 10 桁を使う)
        html = _detail_html_dl(phone="0570111222")
        with patch.object(adapter, "_http_get", return_value=html):
            raw = adapter.extract_animal_details(url, category="sheltered")
        # 個別値 (0570-111-222) が保持され、共通の 098-945-3043 で上書きされない
        assert raw.phone == "057-011-1222", (
            f"detail 側に phone があれば上書きしない: got {raw.phone!r}"
        )
