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
    fallback_to_llm: bool = (
        False  # rule-based 抽出失敗時に LLM 抽出で再試行（rule-basedモードのみ意味あり）
    )
    timeout_sec: int | None = None  # サイト個別タイムアウト秒。未指定時はグローバル値を使用
    # 利用規約・ライセンスの棚卸し用（オープンデータ適法性の根拠記録）。
    # license: 'public_data'|'cc_by'|'gov_standard'|'unknown'|'prohibited' 等
    # terms_url: そのサイトの利用規約 / オープンデータ規約の URL
    license: str = "unknown"
    terms_url: str | None = None

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

    # 民間団体・指定管理者・財団が運営するドメイン（自治体公式ではない）。
    # オープンデータ規約の対象外で、利用規約は個別。商用利用時は必ず個別確認が必要。
    _NON_GOV_DOMAINS: frozenset[str] = frozenset(
        {
            "aniwel.jp",
            "douai-tokushima.com",
            "hyogo-douai.sakura.ne.jp",
            "kochi-apc.com",
            "kyoto-ani-love.com",
            "mie-dakc.server-shared.com",
            "nyantomo.jp",
            "oita-aigo.com",
            "toyohashi-aikuru.jp",
            "www.aniwel-pref.okinawa",
            "www.aomori-animal.jp",
            "www.douaicenter.jp",
            "www.hama-aikyou.jp",
            "www.kumamoto-doubutuaigo.jp",
            "www.sapca.jp",
            "www.yokosuka-doubutu.com",
            "www.zaidan-fukuoka-douai.or.jp",
            "animal-net.pref.nagasaki.jp",
            "wannyan-navi.pref.aichi.jp",
            "wannyapia.akita.jp",
        }
    )

    @staticmethod
    def infer_license(list_url: str) -> str:
        """list_url のドメインからライセンス区分を推定する（L5 棚卸し）。

        自治体公式ドメインは 'gov_standard'（政府標準/公共データ利用規約準拠を推定）、
        民間団体ドメインは 'unknown'（個別の利用規約確認が必須）。
        いずれも推定。商用利用（マネタイズ）前には実際の規約確認が必要。
        """
        from urllib.parse import urlparse

        domain = urlparse(list_url).netloc.lower()
        if domain in SiteConfigLoader._NON_GOV_DOMAINS:
            return "unknown"
        if (
            domain.endswith(".lg.jp")
            or domain.endswith(".go.jp")
            or ".pref." in domain
            or domain.startswith("www.pref.")
            or ".city." in domain
            or domain.startswith("www.city.")
            or ".metro." in domain
        ):
            return "gov_standard"
        return "unknown"

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

        config = SitesConfig(**raw)

        # ライセンス自動推定（L5 棚卸し）: sites.yaml で明示されていないサイトに
        # ドメイン推定値を埋める。明示済み（unknown 以外）はそのまま尊重。
        for site in config.sites:
            if site.license == "unknown":
                site.license = SiteConfigLoader.infer_license(site.list_url)

        return config

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
