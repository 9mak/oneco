"""
YAML設定によるサイト定義の読み込みとバリデーション

sites.yaml からサイト定義を読み込み、Pydantic モデルでバリデーションを行う。
グローバルデフォルト設定とサイト別オーバーライドの解決を担う。
"""

from pathlib import Path

import yaml
from pydantic import BaseModel, field_validator

SUPPORTED_PROVIDERS = {"anthropic", "groq"}


class SiteConfig(BaseModel):
    """サイト定義"""

    name: str
    prefecture: str
    prefecture_code: str
    list_url: str
    list_link_pattern: str | None = None
    category: str = "adoption"
    extraction: str | None = None  # None の時は ExtractionConfig.default_extraction が採用される
    single_page: bool = False  # True の場合、list_url 自体が動物情報を含む（detail pageなし）
    max_pages: int | None = None
    provider: str | None = None
    model: str | None = None
    request_interval: float = 1.0
    requires_js: bool = False  # TrueのときPlaywrightを使用
    wait_selector: str | None = None  # JS描画完了を待つCSSセレクター
    pdf_link_pattern: str | None = (
        None  # PDFリンクのCSSセレクター（指定時はPDFをダウンロードして抽出）
    )
    pdf_multi_animal: bool = False  # TrueのときPDF1件から複数動物を抽出（一覧表形式PDF用）
    fallback_to_llm: bool = False  # rule-based 抽出失敗時に LLM 抽出で再試行（rule-basedモードのみ意味あり）

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
    def validate_extraction(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if v not in ("llm", "rule-based"):
            raise ValueError(f"無効な抽出方式: {v}。'llm' または 'rule-based' を指定してください")
        return v

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, v: str | None) -> str | None:
        if v is not None and v not in SUPPORTED_PROVIDERS:
            raise ValueError(
                f"未対応プロバイダー: {v}。サポート対象: {', '.join(sorted(SUPPORTED_PROVIDERS))}"
            )
        return v

    @field_validator("request_interval")
    @classmethod
    def validate_request_interval(cls, v: float) -> float:
        if v < 1.0:
            raise ValueError(f"request_interval は1.0秒以上である必要があります（指定値: {v}）")
        return v


class ExtractionConfig(BaseModel):
    """グローバル抽出設定"""

    default_provider: str = "groq"
    default_model: str = "llama-3.3-70b-versatile"
    # default_extraction: 各サイトに extraction フィールドが指定されていない時のデフォルト
    # "llm": LLM 抽出（default_provider/model を使用） / "rule-based": rule-based 抽出
    default_extraction: str = "llm"

    @field_validator("default_provider")
    @classmethod
    def validate_default_provider(cls, v: str) -> str:
        if v not in SUPPORTED_PROVIDERS:
            raise ValueError(
                f"未対応プロバイダー: {v}。サポート対象: {', '.join(sorted(SUPPORTED_PROVIDERS))}"
            )
        return v

    @field_validator("default_extraction")
    @classmethod
    def validate_default_extraction(cls, v: str) -> str:
        if v not in ("llm", "rule-based"):
            raise ValueError(
                f"無効な default_extraction: {v}。'llm' または 'rule-based' を指定してください"
            )
        return v


class SitesConfig(BaseModel):
    """トップレベル設定（extraction + sites）"""

    extraction: ExtractionConfig = ExtractionConfig()
    sites: list[SiteConfig]

    @field_validator("sites")
    @classmethod
    def must_have_sites(cls, v: list[SiteConfig]) -> list[SiteConfig]:
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

        with open(config_path, encoding="utf-8") as f:
            raw = yaml.safe_load(f)

        if not isinstance(raw, dict):
            raise ValueError(f"設定ファイルの形式が不正です: {config_path}")

        return SitesConfig(**raw)

    @staticmethod
    def resolve_provider(site: SiteConfig, config: SitesConfig) -> tuple[str, str]:
        """
        サイト定義のプロバイダー/モデルをグローバルデフォルトで解決する

        Returns:
            (provider_name, model_name) のタプル
        """
        provider = site.provider or config.extraction.default_provider
        model = site.model or config.extraction.default_model
        return provider, model
