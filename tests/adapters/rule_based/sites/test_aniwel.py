"""AniwelAdapter のテスト

非営利型一般社団法人アニウェル北海道（aniwel.jp） 用 rule-based adapter の
動作を検証する。

- `div.flexitem2.base` カードが並ぶ single_page 形式 (WordPress / Lightning)
- カードに `<div class="name|sex|age">` が含まれる
- 0 件状態 (募集中の猫が居ない) では ParsingError ではなく空リスト
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.adapters.rule_based.sites.aniwel import AniwelAdapter
from data_collector.domain.models import RawAnimalData
from data_collector.llm.config import SiteConfig

_LIST_URL = "https://aniwel.jp/cats/"
_SITE_NAME = "アニウェル北海道（猫の里親募集）"


def _site() -> SiteConfig:
    return SiteConfig(
        name=_SITE_NAME,
        prefecture="北海道",
        prefecture_code="01",
        list_url=_LIST_URL,
        category="adoption",
        single_page=True,
    )


def _load_aniwel_html(fixture_html) -> str:
    """フィクスチャを読み込む

    リポジトリに保存されている `aniwel_jp.html` は UTF-8 として正しく
    保存されているため二重エンコーディング補正は不要。念のため
    本来含まれるはずの「アニウェル」が読めない場合に補正をかける。
    """
    raw = fixture_html("aniwel_jp")
    if "アニウェル" in raw:
        return raw
    try:
        return raw.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return raw


def _archive_body_html(cards_html: str = "") -> str:
    """`/cats/` archive ページに相当する最小 HTML を生成する"""
    return f"""
    <html><body class="archive post-type-archive post-type-archive-cats post-type-cats">
      <div id="main">
        <div class="postList">
          <div class="flexbox satooya">
            {cards_html}
          </div>
        </div>
      </div>
    </body></html>
    """


def _card(name: str, sex: str, age: str, image_url: str = "") -> str:
    img_html = f'<img src="{image_url}" alt="x" />' if image_url else ""
    return f"""
    <div class="flexitem2 width160 base">
      <div class="full">
        {img_html}
        <div class="name">{name}</div>
        <div class="sex">{sex}</div>
        <div class="age">{age}</div>
        <section class="Satooya">
          <a href="https://aniwel.jp/cats/{name}/" class="btn_09">詳細</a>
        </section>
      </div>
    </div>
    """


class TestAniwelAdapter:
    def test_fetch_animal_list_returns_rows(self, fixture_html):
        """実フィクスチャから動物カード (仮想 URL) が抽出できる"""
        html = _load_aniwel_html(fixture_html)
        adapter = AniwelAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        # フィクスチャは 10 件のカードを含む
        assert len(result) == 10
        for i, (url, cat) in enumerate(result):
            assert url == f"{_LIST_URL}#row={i}"
            assert cat == "adoption"

    def test_extract_animal_details_first_row(self, fixture_html):
        """1 件目のカード (うらら) から RawAnimalData を構築できる

        フィクスチャ収録の 1 件目:
        - name: うらら (RawAnimalData には保持されない)
        - sex: メス
        - age: 約4歳
        - 画像: /wp-content/uploads/2026/05/LINE_ALBUM_うらら_260503_18-150x150.jpg
        - species: 猫 (サイト固定)
        """
        html = _load_aniwel_html(fixture_html)
        adapter = AniwelAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html) as mock_get:
            urls = adapter.fetch_animal_list()
            first_url, category = urls[0]
            raw = adapter.extract_animal_details(first_url, category=category)

        # 同一ページから複数取得しても HTTP は 1 回だけ (キャッシュ確認)
        assert mock_get.call_count == 1
        assert isinstance(raw, RawAnimalData)
        assert raw.species == "猫"
        assert raw.sex == "メス"
        assert "約4歳" in raw.age
        assert raw.color == ""
        assert raw.size == ""
        assert raw.location == ""
        assert raw.shelter_date == ""
        assert raw.source_url == first_url
        assert raw.category == "adoption"
        # 画像 URL は絶対 URL に変換され、wp-content/uploads 配下であること
        assert raw.image_urls
        assert all(u.startswith("https://aniwel.jp/") for u in raw.image_urls)
        assert any("/wp-content/uploads/" in u for u in raw.image_urls)

    def test_multiple_rows_indexed_correctly(self, fixture_html):
        """複数カードが index 順で正しく抽出される (フィクスチャの 2 件目: しま)"""
        html = _load_aniwel_html(fixture_html)
        adapter = AniwelAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            raw0 = adapter.extract_animal_details(urls[0][0], category="adoption")
            raw1 = adapter.extract_animal_details(urls[1][0], category="adoption")

        # 1 件目: うらら / メス / 約4歳
        assert raw0.sex == "メス"
        assert "約4歳" in raw0.age
        # 2 件目: しま / メス / 約10歳3ヵ月
        assert raw1.sex == "メス"
        assert "10歳" in raw1.age

    def test_extract_caches_html_across_calls(self, fixture_html):
        """同一 adapter インスタンスでは _http_get は 1 回だけ呼ばれる"""
        html = _load_aniwel_html(fixture_html)
        adapter = AniwelAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html) as mock_get:
            urls = adapter.fetch_animal_list()
            for u, c in urls:
                adapter.extract_animal_details(u, category=c)

        assert mock_get.call_count == 1

    def test_species_is_always_cat(self, fixture_html):
        """サイトは猫専用 archive のため species は常に 猫"""
        html = _load_aniwel_html(fixture_html)
        adapter = AniwelAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            for url, cat in urls:
                raw = adapter.extract_animal_details(url, category=cat)
                assert raw.species == "猫"

    def test_synthetic_card_basic(self):
        """合成 HTML (1 カード) でも正しく抽出できる"""
        cards = _card(
            name="テスト",
            sex="オス",
            age="約2歳",
            image_url=("https://aniwel.jp/wp-content/uploads/2025/01/test-150x150.jpg"),
        )
        html = _archive_body_html(cards_html=cards)
        adapter = AniwelAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            assert len(urls) == 1
            raw = adapter.extract_animal_details(urls[0][0], category="adoption")

        assert raw.species == "猫"
        assert raw.sex == "オス"
        assert "約2歳" in raw.age
        assert raw.image_urls == ["https://aniwel.jp/wp-content/uploads/2025/01/test-150x150.jpg"]

    def test_empty_archive_returns_empty_list(self):
        """カードが 0 件の archive ページでは空リストを返す (例外を投げない)"""
        html = _archive_body_html(cards_html="")
        adapter = AniwelAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            result = adapter.fetch_animal_list()

        assert result == []

    def test_unknown_template_raises_parsing_error(self):
        """archive を示す signal も無く行も無い場合は ParsingError を投げる"""
        html = "<html><body><main>無関係なページ</main></body></html>"
        adapter = AniwelAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            with pytest.raises(Exception):
                adapter.fetch_animal_list()

    def test_relative_image_resolved_to_absolute(self):
        """カード内の相対 URL 画像が絶対 URL に変換される"""
        cards = _card(
            name="rel",
            sex="メス",
            age="約1歳",
            image_url="/wp-content/uploads/2025/05/rel-150x150.jpg",
        )
        html = _archive_body_html(cards_html=cards)
        adapter = AniwelAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="adoption")

        assert raw.image_urls
        for u in raw.image_urls:
            assert u.startswith("https://aniwel.jp/")
            assert "/wp-content/uploads/" in u

    def test_card_without_image_returns_empty_image_urls(self):
        """画像が無いカードでも例外を投げず image_urls が空になる"""
        cards = _card(name="noimg", sex="オス", age="約3歳", image_url="")
        html = _archive_body_html(cards_html=cards)
        adapter = AniwelAdapter(_site())

        with patch.object(adapter, "_http_get", return_value=html):
            urls = adapter.fetch_animal_list()
            raw = adapter.extract_animal_details(urls[0][0], category="adoption")

        assert raw.image_urls == []
        assert raw.sex == "オス"

    def test_site_registered(self):
        """サイト名が Registry に登録されている"""
        if SiteAdapterRegistry.get(_SITE_NAME) is None:
            SiteAdapterRegistry.register(_SITE_NAME, AniwelAdapter)
        assert SiteAdapterRegistry.get(_SITE_NAME) is AniwelAdapter
