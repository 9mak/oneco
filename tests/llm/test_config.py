"""SiteConfigLoader のユニットテスト"""

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from src.data_collector.llm.config import (
    ExtractionConfig,
    SiteConfig,
    SiteConfigLoader,
    SitesConfig,
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
        # extraction default は None（実効値は ExtractionConfig.default_extraction が決定）
        assert site.extraction is None
        assert site.request_interval == 1.0
        assert site.max_pages is None
        assert site.provider is None
        assert site.model is None
        assert config.extraction.default_provider == "groq"
        assert config.extraction.default_model == "llama-3.3-70b-versatile"

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
        for provider in ["anthropic", "groq"]:
            site = SiteConfig(
                name="テスト",
                prefecture="テスト県",
                prefecture_code="99",
                list_url="https://example.com/",
                provider=provider,
            )
            assert site.provider == provider

    def test_timeout_sec_defaults_to_none(self):
        site = SiteConfig(
            name="テスト",
            prefecture="テスト県",
            prefecture_code="99",
            list_url="https://example.com/",
        )
        assert site.timeout_sec is None

    def test_timeout_sec_accepts_positive_int(self):
        site = SiteConfig(
            name="重いサイト",
            prefecture="テスト県",
            prefecture_code="99",
            list_url="https://example.com/",
            timeout_sec=300,
        )
        assert site.timeout_sec == 300


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
        provider, model = SiteConfigLoader.resolve_provider(config.sites[0], config)
        assert provider == "anthropic"
        assert model == "claude-haiku-4-5-20251001"

    def test_site_override_takes_precedence(self):
        config = SitesConfig(
            extraction=ExtractionConfig(
                default_provider="groq",
                default_model="llama-3.3-70b-versatile",
            ),
            sites=[
                SiteConfig(
                    name="テスト",
                    prefecture="テスト県",
                    prefecture_code="99",
                    list_url="https://example.com/",
                    provider="anthropic",
                    model="claude-haiku-4-5-20251001",
                )
            ],
        )
        provider, model = SiteConfigLoader.resolve_provider(config.sites[0], config)
        assert provider == "anthropic"
        assert model == "claude-haiku-4-5-20251001"


class TestLicenseInference:
    """L5: ドメインからライセンス区分を推定するロジック"""

    def test_lg_jp_is_gov_standard(self):
        from src.data_collector.llm.config import SiteConfigLoader

        assert (
            SiteConfigLoader.infer_license("https://www.city.machida.tokyo.jp/x/y/")
            == "gov_standard"
        )

    def test_go_jp_is_gov_standard(self):
        from src.data_collector.llm.config import SiteConfigLoader

        assert SiteConfigLoader.infer_license("https://example.go.jp/foo") == "gov_standard"

    def test_pref_jp_is_gov_standard(self):
        from src.data_collector.llm.config import SiteConfigLoader

        assert SiteConfigLoader.infer_license("https://www.pref.kyoto.jp/foo") == "gov_standard"

    def test_metro_lg_jp_is_gov_standard(self):
        from src.data_collector.llm.config import SiteConfigLoader

        assert (
            SiteConfigLoader.infer_license("https://shuyojoho.metro.tokyo.lg.jp/foo")
            == "gov_standard"
        )

    def test_non_gov_org_is_unknown(self):
        from src.data_collector.llm.config import SiteConfigLoader

        # 民間団体（指定管理者・財団）
        assert (
            SiteConfigLoader.infer_license("https://www.zaidan-fukuoka-douai.or.jp/") == "unknown"
        )
        assert SiteConfigLoader.infer_license("https://kochi-apc.com/") == "unknown"

    def test_pref_domain_in_non_gov_list_is_unknown(self):
        """pref. を含むが団体運営ドメインは unknown（個別確認必須）"""
        from src.data_collector.llm.config import SiteConfigLoader

        assert SiteConfigLoader.infer_license("https://animal-net.pref.nagasaki.jp/") == "unknown"

    def test_unknown_top_level_is_unknown(self):
        from src.data_collector.llm.config import SiteConfigLoader

        assert SiteConfigLoader.infer_license("https://example.com/foo") == "unknown"


class TestLoadAppliesInferredLicense:
    """L5: load() が明示なしのサイトに推定ライセンスを埋めること"""

    def test_load_fills_inferred_license(self, tmp_path):
        from src.data_collector.llm.config import SiteConfigLoader

        cfg = tmp_path / "sites.yaml"
        cfg.write_text(
            "extraction:\n"
            "  default_provider: groq\n"
            "  default_model: llama-3.3-70b-versatile\n"
            "  default_extraction: rule-based\n"
            "sites:\n"
            "  - name: 政府公式サイト\n"
            "    prefecture: 東京都\n"
            "    prefecture_code: '13'\n"
            "    list_url: https://www.city.machida.tokyo.jp/x/\n"
            "  - name: 民間団体サイト\n"
            "    prefecture: 福岡県\n"
            "    prefecture_code: '40'\n"
            "    list_url: https://www.zaidan-fukuoka-douai.or.jp/y/\n",
            encoding="utf-8",
        )
        config = SiteConfigLoader.load(cfg)
        assert config.sites[0].license == "gov_standard"
        assert config.sites[1].license == "unknown"

    def test_load_does_not_overwrite_explicit_license(self, tmp_path):
        from src.data_collector.llm.config import SiteConfigLoader

        cfg = tmp_path / "sites.yaml"
        cfg.write_text(
            "extraction:\n"
            "  default_provider: groq\n"
            "  default_model: llama-3.3-70b-versatile\n"
            "  default_extraction: rule-based\n"
            "sites:\n"
            "  - name: 明示済みサイト\n"
            "    prefecture: 東京都\n"
            "    prefecture_code: '13'\n"
            "    list_url: https://www.city.machida.tokyo.jp/x/\n"
            "    license: prohibited\n"
            "    terms_url: https://example.com/terms\n",
            encoding="utf-8",
        )
        config = SiteConfigLoader.load(cfg)
        assert config.sites[0].license == "prohibited"
        assert config.sites[0].terms_url == "https://example.com/terms"
