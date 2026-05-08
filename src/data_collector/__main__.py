"""CLI エントリーポイント"""

import asyncio
import contextlib
import logging
import os
import signal
import sys
import time
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from .adapters.kochi_adapter import KochiAdapter
from .domain.diff_detector import DiffDetector
from .infrastructure.database.connection import DatabaseConnection, DatabaseSettings
from .infrastructure.notification_client import NotificationClient
from .infrastructure.output_writer import OutputWriter
from .infrastructure.snapshot_store import SnapshotStore
from .llm.adapter import LlmAdapter
from .llm.config import SiteConfigLoader, SitesConfig
from .llm.html_preprocessor import HtmlPreprocessor
from .llm.providers.anthropic_provider import AnthropicProvider
from .llm.providers.base import LlmProvider
from .llm.providers.fallback_provider import FallbackProvider
from .llm.providers.groq_provider import GroqProvider
from .orchestration.collector_service import CollectorService

PROVIDER_REGISTRY = {
    "anthropic": AnthropicProvider,
    "groq": GroqProvider,
}

# Groq の非決定的な tool_use_failed や 500/503 をリトライしても収まらない場合に
# Anthropic Claude（信頼性高い）に自動フォールバックする。ANTHROPIC_API_KEY が
# 環境変数にある場合のみ有効化。
ANTHROPIC_FALLBACK_MODEL = os.getenv("ANTHROPIC_FALLBACK_MODEL", "claude-haiku-4-5-20251001")

# サイト別収集のタイムアウト（秒）
# 209+ サイトを GitHub Actions の 6 時間以内に収まらせるため、ハングしたサイトを
# 切り捨てて次に進む。requires_js=True サイトは Playwright 起動が重いので長め。
SITE_TIMEOUT_SEC = int(os.getenv("SITE_TIMEOUT_SEC", "120"))
SITE_TIMEOUT_JS_SEC = int(os.getenv("SITE_TIMEOUT_JS_SEC", "180"))


class SiteCollectionTimeoutError(Exception):
    """1 サイトの収集処理がタイムアウトした"""


@contextlib.contextmanager
def site_timeout(seconds: int, site_name: str):
    """SIGALRM ベースで site collection 全体のタイムアウトを設ける。

    Linux/macOS のみ動作（CI は Linux）。Windows では noop（signal が無い）。
    """

    def _handler(signum, frame):
        raise SiteCollectionTimeoutError(f"site collection timed out after {seconds}s: {site_name}")

    if hasattr(signal, "SIGALRM"):
        old_handler = signal.signal(signal.SIGALRM, _handler)
        signal.alarm(seconds)
        try:
            yield
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)
    else:
        yield


def create_provider(provider_name: str, model: str) -> LlmProvider:
    """プロバイダーインスタンスを生成。

    Groq を選んだ場合、ANTHROPIC_API_KEY が利用可能なら自動で
    Groq → Anthropic フォールバックでラップする。
    """
    cls = PROVIDER_REGISTRY.get(provider_name)
    if cls is None:
        supported = ", ".join(sorted(PROVIDER_REGISTRY.keys()))
        raise ValueError(f"未対応プロバイダー: {provider_name}。サポート対象: {supported}")

    primary = cls(model=model)

    if provider_name == "groq" and os.getenv("ANTHROPIC_API_KEY"):
        fallback = AnthropicProvider(model=ANTHROPIC_FALLBACK_MODEL)
        return FallbackProvider(primary=primary, fallback=fallback)

    return primary


def run_llm_sites(
    config: SitesConfig,
    snapshot_store: SnapshotStore,
    diff_detector: DiffDetector,
    output_writer: OutputWriter,
    notification_client: NotificationClient,
    db_connection: DatabaseConnection | None,
    logger: logging.Logger,
) -> bool:
    """LLMベースのサイト群を収集"""
    all_success = True

    for site in config.sites:
        if site.extraction != "llm":
            continue

        site_start = time.time()
        logger.info(f"=== LLM収集開始: {site.name} ===")

        # サイトの種類に応じたタイムアウト値を選択
        timeout = SITE_TIMEOUT_JS_SEC if getattr(site, "requires_js", False) else SITE_TIMEOUT_SEC

        try:
            # プロバイダー解決
            provider_name, model = SiteConfigLoader.resolve_provider(site, config)
            provider = create_provider(provider_name, model)

            # LlmAdapter生成
            adapter = LlmAdapter(
                site_config=site,
                provider=provider,
                preprocessor=HtmlPreprocessor(),
            )

            # CollectorServiceで実行
            service = CollectorService(
                adapter=adapter,
                diff_detector=diff_detector,
                output_writer=output_writer,
                notification_client=notification_client,
                snapshot_store=snapshot_store,
                db_connection=db_connection,
            )

            # SIGALRM タイムアウトでハング対策
            with site_timeout(timeout, site.name):
                result = service.run_collection()

            elapsed = time.time() - site_start
            adapter.log_stats()

            if result.success:
                logger.info(
                    f"[{site.name}] 収集完了: "
                    f"{result.total_collected}件, "
                    f"新規{result.new_count}, "
                    f"更新{result.updated_count}, "
                    f"処理時間{elapsed:.1f}秒"
                )
            else:
                logger.error(f"[{site.name}] 収集失敗: {', '.join(result.errors)}")
                all_success = False

        except SiteCollectionTimeoutError as e:
            elapsed = time.time() - site_start
            logger.warning(
                f"[{site.name}] タイムアウト ({elapsed:.1f}秒, limit={timeout}秒): "
                f"{e}. 次のサイトに進みます。"
            )
            all_success = False
            continue
        except Exception as e:
            elapsed = time.time() - site_start
            logger.error(
                f"[{site.name}] エラー発生 ({elapsed:.1f}秒): {e}",
                exc_info=True,
            )
            all_success = False
            continue  # 他のサイトの処理を継続

    return all_success


def main():
    """
    CLI エントリーポイント

    Usage:
        python -m data_collector
        python -m data_collector --llm-only     # LLMサイトのみ
        python -m data_collector --kochi-only    # 高知県のみ

    Exit codes:
        0: 成功
        1: 失敗
    """
    # ロギング設定
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    logger = logging.getLogger(__name__)

    db_connection: DatabaseConnection | None = None

    # コマンドライン引数
    args = sys.argv[1:]
    llm_only = "--llm-only" in args
    kochi_only = "--kochi-only" in args

    try:
        # 共通依存
        snapshot_store = SnapshotStore()
        diff_detector = DiffDetector(snapshot_store)
        output_writer = OutputWriter()

        notification_config: dict[str, str] = {}
        if email := os.environ.get("NOTIFICATION_EMAIL"):
            notification_config["email"] = email
        if slack_url := os.environ.get("SLACK_WEBHOOK_URL"):
            notification_config["slack_webhook_url"] = slack_url
        notification_client = NotificationClient(notification_config)

        database_url = os.environ.get("DATABASE_URL")
        if database_url:
            logger.info("Initializing database connection...")
            db_settings = DatabaseSettings(database_url=database_url)
            db_connection = DatabaseConnection(settings=db_settings)
            logger.info("Database connection initialized")

        success = True

        # === 高知県（ルールベース） ===
        if not llm_only:
            logger.info("=== 高知県（ルールベース）収集開始 ===")
            adapter = KochiAdapter()
            service = CollectorService(
                adapter=adapter,
                diff_detector=diff_detector,
                output_writer=output_writer,
                notification_client=notification_client,
                snapshot_store=snapshot_store,
                db_connection=db_connection,
            )
            result = service.run_collection()

            if result.success:
                logger.info(
                    f"高知県収集完了: {result.total_collected}件, "
                    f"新規{result.new_count}, 更新{result.updated_count}"
                )
            else:
                logger.error(f"高知県収集失敗: {', '.join(result.errors)}")
                success = False

        # === LLMサイト群 ===
        if not kochi_only:
            config_path = Path(__file__).parent / "config" / "sites.yaml"
            if config_path.exists():
                config = SiteConfigLoader.load(config_path)
                logger.info(
                    f"LLMサイト設定読込: {len(config.sites)}サイト "
                    f"(provider={config.extraction.default_provider}, "
                    f"model={config.extraction.default_model})"
                )
                llm_success = run_llm_sites(
                    config=config,
                    snapshot_store=snapshot_store,
                    diff_detector=diff_detector,
                    output_writer=output_writer,
                    notification_client=notification_client,
                    db_connection=db_connection,
                    logger=logger,
                )
                if not llm_success:
                    success = False
            else:
                logger.info("LLMサイト設定なし（sites.yaml が見つかりません）")

        sys.exit(0 if success else 1)

    except Exception as e:
        logger.error(f"Unexpected error: {e!s}", exc_info=True)
        sys.exit(1)

    finally:
        if db_connection:
            try:
                asyncio.run(db_connection.close())
                logger.info("Database connection closed")
            except Exception as e:
                logger.warning(f"Error closing database connection: {e!s}")


if __name__ == "__main__":
    main()
