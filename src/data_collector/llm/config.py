"""
YAML設定によるサイト定義の読み込みとバリデーション

sites.yaml からサイト定義を読み込み、Pydantic モデルでバリデーションを行う。
グローバルデフォルト設定とサイト別オーバーライドの解決を担う。
"""

from pathlib import Path
from typing import List, Optional

import yaml
from pydantic import BaseModel, field_validator


SUPPORTED_PROVIDERS = {"anthropic", "openai", "google"}


class SiteConfig(BaseModel):
    """サイト定義"""

    name: str
    prefecture: str
    prefecture_code: str
    list_url: str
    list_link_pattern: Optional[str] = None
    category: str = "adoption"
    extraction: str = "llm"
    single_page: bool = False  # True の場合、list_url 自体が動物情報を含む（detail pageなし）
    max_pages: Optional[int] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    request_interval: float = 1.0
    requires_js: bool = False  # TrueのときPlaywrightを使用
    wait_selector: Optional[str] = None  # JS描画完了を待つCSSセレクター

    @field_validator("name", "prefecture", "list_url")
    @classmethod
    def must_not_be_empty(cls, v: str, info) -> str:
        if not v or not v.strip():
            raise ValueError(f"{info.field_name} は空にできません")
        return v

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        if v not in ("adoption", "lost", "sheltered"):
            raise ValueError(
                f"無効なカテゴリ: {v}。'adoption', 'lost' または 'sheltered' を指定してください"
            )
        return v

    @field_validator("extraction")
    @classmethod
    def validate_extraction(cls, v: str) -> str:
        if v not in ("llm", "rule-based"):
            raise ValueError(
                f"無効な抽出方式: {v}。'llm' または 'rule-based' を指定してください"
            )
        return v

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in SUPPORTED_PROVIDERS:
            raise ValueError(
                f"未対応プロバイダー: {v}。"
                f"サポート対象: {', '.join(sorted(SUPPORTED_PROVIDERS))}"
            )
        return v

    @field_validator("request_interval")
    @classmethod
    def validate_request_interval(cls, v: float) -> float:
        if v < 1.0:
            raise ValueError(
                f"request_interval は1.0秒以上である必要があります（指定値: {v}）"
            )
        return v


class ExtractionConfig(BaseModel):
    """グローバル抽出設定"""

    default_provider: str = "anthropic"
    default_model: str = "claude-haiku-4-5-20251001"

    @field_validator("default_provider")
    @classmethod
    def validate_default_provider(cls, v: str) -> str:
        if v not in SUPPORTED_PROVIDERS:
            raise ValueError(
                f"未対応プロバイダー: {v}。"
                f"サポート対象: {', '.join(sorted(SUPPORTED_PROVIDERS))}"
            )
        return v


class SitesConfig(BaseModel):
    """トップレベル設定（extraction + sites）"""

    extraction: ExtractionConfig = ExtractionConfig()
    sites: List[SiteConfig]

    @field_validator("sites")
    @classmethod
    def must_have_sites(cls, v: List[SiteConfig]) -> List[SiteConfig]:
        if not v:
            raise ValueError("sites には1つ以上のサイト定義が必要です")
        return v


class SiteConfigLoader:
    """YAML設定ファイルの読み込みとバリデーション"""

    @staticmethod
    def load(config_path: Path) -> SitesConfig:
        """
        YAML設定ファイルを読み込みバリデーション

        Args:
            config_path: sites.yaml のパス

        Returns:
            SitesConfig: バリデーション済みの設定

        Raises:
            FileNotFoundError: 設定ファイルが存在しない場合
            yaml.YAMLError: YAML構文エラーの場合
            ValidationError: バリデーションエラーの場合
        """
        if not config_path.exists():
            raise FileNotFoundError(f"設定ファイルが見つかりません: {config_path}")

        with open(config_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)

        if not isinstance(raw, dict):
            raise ValueError(f"設定ファイルの形式が不正です: {config_path}")

        return SitesConfig(**raw)

    @staticmethod
    def resolve_provider(
        site: SiteConfig, config: SitesConfig
    ) -> tuple[str, str]:
        """
        サイト定義のプロバイダー/モデルをグローバルデフォルトで解決する

        Returns:
            (provider_name, model_name) のタプル
        """
        provider = site.provider or config.extraction.default_provider
        model = site.model or config.extraction.default_model
        return provider, model
