"""RuleBasedAdapter 基底クラスのテスト

Phase A2 Task 1.1: 共通基底クラスの helper の動作を検証する。
abstract メソッド群はサブクラステストで担保。
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
import requests

from data_collector.adapters.municipality_adapter import (
    MunicipalityAdapter,
    NetworkError,
)
from data_collector.adapters.rule_based.base import RuleBasedAdapter
from data_collector.domain.models import AnimalData, RawAnimalData
from data_collector.llm.config import SiteConfig

# ─────────────────────────── Test fixtures ───────────────────────────


def _site() -> SiteConfig:
    """テスト用最小限の SiteConfig"""
    return SiteConfig(
        name="テストサイト",
        prefecture="高知県",
        prefecture_code="39",
        list_url="https://example.com/list/",
    )


class _ConcreteAdapter(RuleBasedAdapter):
    """abstract method を実装したテスト用具象クラス"""

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        return []

    def extract_animal_details(self, detail_url: str, category: str = "adoption") -> RawAnimalData:
        raise NotImplementedError

    def normalize(self, raw_data: RawAnimalData) -> AnimalData:
        return super()._default_normalize(raw_data)


# ─────────────────────────── Tests ───────────────────────────


class TestRuleBasedAdapterInheritance:
    def test_inherits_from_municipality_adapter(self):
        """MunicipalityAdapter を継承していること"""
        assert issubclass(RuleBasedAdapter, MunicipalityAdapter)

    def test_concrete_subclass_passes_prefecture_to_super(self):
        """具象サブクラスが super().__init__ に正しく値を渡すこと"""
        adapter = _ConcreteAdapter(_site())
        assert adapter.prefecture_code == "39"
        assert adapter.municipality_name == "テストサイト"

    def test_site_config_stored(self):
        """site_config がインスタンスに保持されていること"""
        site = _site()
        adapter = _ConcreteAdapter(site)
        assert adapter.site_config is site


class TestAbsoluteUrl:
    def test_absolute_url_returns_unchanged_when_already_absolute(self):
        adapter = _ConcreteAdapter(_site())
        result = adapter._absolute_url("https://example.com/page", base="https://other.com/")
        assert result == "https://example.com/page"

    def test_absolute_url_resolves_relative_against_base(self):
        adapter = _ConcreteAdapter(_site())
        result = adapter._absolute_url("/sub/page", base="https://example.com/list/")
        assert result == "https://example.com/sub/page"

    def test_absolute_url_uses_site_list_url_when_base_omitted(self):
        adapter = _ConcreteAdapter(_site())
        result = adapter._absolute_url("detail/1")
        assert result == "https://example.com/list/detail/1"


class TestNormalizePhone:
    def test_extract_hyphenated_phone(self):
        adapter = _ConcreteAdapter(_site())
        assert adapter._normalize_phone("お問い合わせ: 088-826-2364 まで") == "088-826-2364"

    def test_extract_phone_without_hyphens(self):
        adapter = _ConcreteAdapter(_site())
        assert adapter._normalize_phone("0888262364") == "088-826-2364"

    def test_returns_empty_when_no_phone_in_text(self):
        adapter = _ConcreteAdapter(_site())
        assert adapter._normalize_phone("電話番号は不明です") == ""

    def test_handles_empty_input(self):
        adapter = _ConcreteAdapter(_site())
        assert adapter._normalize_phone("") == ""


class TestFilterImageUrls:
    def test_filters_template_paths(self):
        """サイトテンプレート画像 (themes 配下) は除外される"""
        adapter = _ConcreteAdapter(_site())
        urls = [
            "https://example.com/wp-content/themes/foo/logo.png",
            "https://example.com/wp-content/uploads/2026/animal1.jpg",
            "https://example.com/wp-content/uploads/2026/animal2.jpg",
        ]
        result = adapter._filter_image_urls(urls, base_url="https://example.com/")
        assert len(result) == 2
        assert all("/uploads/" in u for u in result)

    def test_returns_originals_when_no_uploads_path(self):
        """uploads 画像が無い場合は元リストを返す（データ消失防止）"""
        adapter = _ConcreteAdapter(_site())
        urls = ["https://example.com/img/animal.jpg"]
        result = adapter._filter_image_urls(urls, base_url="https://example.com/")
        assert result == urls


class TestHttpGet:
    def test_returns_text_on_success(self):
        adapter = _ConcreteAdapter(_site())

        class _MockResp:
            text = "<html>ok</html>"
            status_code = 200

            def raise_for_status(self):
                pass

        with patch("requests.get", return_value=_MockResp()) as mock_get:
            result = adapter._http_get("https://example.com/")
            assert result == "<html>ok</html>"
            mock_get.assert_called_once()

    def test_raises_network_error_on_http_error(self):
        adapter = _ConcreteAdapter(_site())

        with patch(
            "requests.get",
            side_effect=requests.exceptions.HTTPError("500 Server Error"),
        ):
            with pytest.raises(NetworkError):
                adapter._http_get("https://example.com/")

    def test_passes_user_agent_header(self):
        adapter = _ConcreteAdapter(_site())

        class _MockResp:
            text = ""
            status_code = 200

            def raise_for_status(self):
                pass

        with patch("requests.get", return_value=_MockResp()) as mock_get:
            adapter._http_get("https://example.com/")
            kwargs = mock_get.call_args.kwargs
            assert "headers" in kwargs
            assert "User-Agent" in kwargs["headers"]


class TestDefaultNormalize:
    def test_delegates_to_data_normalizer(self):
        """_default_normalize は DataNormalizer.normalize に委譲する"""
        adapter = _ConcreteAdapter(_site())
        raw = RawAnimalData(
            species="犬",
            sex="オス",
            age="3歳",
            color="茶",
            size="中型",
            shelter_date="2026-04-01",
            location="高知県",
            phone="088-826-2364",
            image_urls=["https://example.com/img.jpg"],
            source_url="https://example.com/detail/1",
            category="adoption",
        )
        result = adapter.normalize(raw)
        assert isinstance(result, AnimalData)
        assert result.species == "犬"
