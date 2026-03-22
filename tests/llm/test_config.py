"""SiteConfigLoader のユニットテスト"""

import pytest
import yaml
from pathlib import Path
from pydantic import ValidationError

from src.data_collector.llm.config import (
    SiteConfig,
    ExtractionConfig,
    SitesConfig,
    SiteConfigLoader,
)


@pytest.fixture
def valid_yaml(tmp_path: Path) -> Path:
    config = {
        "extraction": {
            "default_provider": "anthropic",
            "default_model": "claude-haiku-4-5-20251001",
        },
        "sites": [
            {
                "name": "徳島県動物愛護管理センター",
                "prefecture": "徳島県",
                "prefecture_code": "36",
                "list_url": "https://douai-tokushima.com/",
                "list_link_pattern": "a[href*='detail']",
                "category": "adoption",
            }
        ],
    }
    path = tmp_path / "sites.yaml"
    path.write_text(yaml.dump(config, allow_unicode=True), encoding="utf-8")
    return path


@pytest.fixture
def minimal_yaml(tmp_path: Path) -> Path:
    """必須フィールドのみの最小設定"""
    config = {
        "sites": [
            {
                "name": "テストサイト",
                "prefecture": "テスト県",
                "prefecture_code": "99",
                "list_url": "https://example.com/",
            }
        ],
    }
    path = tmp_path / "sites.yaml"
    path.write_text(yaml.dump(config, allow_unicode=True), encoding="utf-8")
    return path


class TestSiteConfigLoader:
    def test_load_valid_yaml(self, valid_yaml: Path):
        config = SiteConfigLoader.load(valid_yaml)
        assert len(config.sites) == 1
        assert config.sites[0].name == "徳島県動物愛護管理センター"
        assert config.sites[0].prefecture == "徳島県"
        assert config.sites[0].list_url == "https://douai-tokushima.com/"
        assert config.sites[0].list_link_pattern == "a[href*='detail']"
        assert config.extraction.default_provider == "anthropic"

    def test_load_minimal_yaml_with_defaults(self, minimal_yaml: Path):
        config = SiteConfigLoader.load(minimal_yaml)
        site = config.sites[0]
        assert site.category == "adoption"
        assert site.extraction == "llm"
        assert site.request_interval == 1.0
        assert site.max_pages is None
        assert site.provider is None
        assert site.model is None
        assert config.extraction.default_provider == "anthropic"
        assert config.extraction.default_model == "claude-haiku-4-5-20251001"

    def test_load_file_not_found(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError, match="設定ファイルが見つかりません"):
            SiteConfigLoader.load(tmp_path / "nonexistent.yaml")

    def test_load_invalid_yaml_format(self, tmp_path: Path):
        path = tmp_path / "bad.yaml"
        path.write_text("just a string", encoding="utf-8")
        with pytest.raises(ValueError, match="設定ファイルの形式が不正"):
            SiteConfigLoader.load(path)

    def test_load_empty_sites_raises(self, tmp_path: Path):
        config = {"sites": []}
        path = tmp_path / "empty.yaml"
        path.write_text(yaml.dump(config), encoding="utf-8")
        with pytest.raises(ValidationError, match="1つ以上のサイト定義が必要"):
            SiteConfigLoader.load(path)


class TestSiteConfigValidation:
    def test_missing_name_raises(self):
        with pytest.raises(ValidationError, match="name"):
            SiteConfig(
                name="",
                prefecture="テスト県",
                prefecture_code="99",
                list_url="https://example.com/",
            )

    def test_missing_prefecture_raises(self):
        with pytest.raises(ValidationError, match="prefecture"):
            SiteConfig(
                name="テスト",
                prefecture="",
                prefecture_code="99",
                list_url="https://example.com/",
            )

    def test_missing_list_url_raises(self):
        with pytest.raises(ValidationError, match="list_url"):
            SiteConfig(
                name="テスト",
                prefecture="テスト県",
                prefecture_code="99",
                list_url="",
            )

    def test_invalid_category_raises(self):
        with pytest.raises(ValidationError, match="無効なカテゴリ"):
            SiteConfig(
                name="テスト",
                prefecture="テスト県",
                prefecture_code="99",
                list_url="https://example.com/",
                category="invalid",
            )

    def test_sheltered_category_is_valid(self):
        config = SiteConfig(
            name="テスト",
            prefecture="テスト県",
            prefecture_code="99",
            list_url="https://example.com/",
            category="sheltered",
        )
        assert config.category == "sheltered"

    def test_invalid_extraction_raises(self):
        with pytest.raises(ValidationError, match="無効な抽出方式"):
            SiteConfig(
                name="テスト",
                prefecture="テスト県",
                prefecture_code="99",
                list_url="https://example.com/",
                extraction="other",
            )

    def test_unsupported_provider_raises(self):
        with pytest.raises(ValidationError, match="未対応プロバイダー"):
            SiteConfig(
                name="テスト",
                prefecture="テスト県",
                prefecture_code="99",
                list_url="https://example.com/",
                provider="azure",
            )

    def test_request_interval_too_low_raises(self):
        with pytest.raises(ValidationError, match="1.0秒以上"):
            SiteConfig(
                name="テスト",
                prefecture="テスト県",
                prefecture_code="99",
                list_url="https://example.com/",
                request_interval=0.5,
            )

    def test_valid_providers_accepted(self):
        for provider in ["anthropic", "openai", "google"]:
            site = SiteConfig(
                name="テスト",
                prefecture="テスト県",
                prefecture_code="99",
                list_url="https://example.com/",
                provider=provider,
            )
            assert site.provider == provider


class TestExtractionConfigValidation:
    def test_unsupported_default_provider_raises(self):
        with pytest.raises(ValidationError, match="未対応プロバイダー"):
            ExtractionConfig(default_provider="unsupported")


class TestResolveProvider:
    def test_uses_global_defaults(self):
        config = SitesConfig(
            extraction=ExtractionConfig(
                default_provider="anthropic",
                default_model="claude-haiku-4-5-20251001",
            ),
            sites=[
                SiteConfig(
                    name="テスト",
                    prefecture="テスト県",
                    prefecture_code="99",
                    list_url="https://example.com/",
                )
            ],
        )
        provider, model = SiteConfigLoader.resolve_provider(
            config.sites[0], config
        )
        assert provider == "anthropic"
        assert model == "claude-haiku-4-5-20251001"

    def test_site_override_takes_precedence(self):
        config = SitesConfig(
            extraction=ExtractionConfig(
                default_provider="anthropic",
                default_model="claude-haiku-4-5-20251001",
            ),
            sites=[
                SiteConfig(
                    name="テスト",
                    prefecture="テスト県",
                    prefecture_code="99",
                    list_url="https://example.com/",
                    provider="openai",
                    model="gpt-4o-mini",
                )
            ],
        )
        provider, model = SiteConfigLoader.resolve_provider(
            config.sites[0], config
        )
        assert provider == "openai"
        assert model == "gpt-4o-mini"
