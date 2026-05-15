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

    def test_fetch_animal_list_raises_when_no_links(self) -> None:
        """detail link が 1 つも見つからない場合は ParsingError"""
        adapter = AniwelOkinawaAdapter(_site(0))
        html = "<html><body><main>準備中</main></body></html>"

        with patch.object(adapter, "_http_get", return_value=html):
            with pytest.raises(ParsingError):
                adapter.fetch_animal_list()

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
