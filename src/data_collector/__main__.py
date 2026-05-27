"""CLI エントリーポイント"""

import asyncio
import contextlib
import logging
import os
import signal
import sys
import time
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from .adapters.kochi_adapter import KochiAdapter
from .adapters.rule_based import (
    sites as _rule_based_sites,  # noqa: F401  全 adapter を Registry に登録
)
from .adapters.rule_based.broken_tracker import BrokenSitesTracker
from .adapters.rule_based.registry import SiteAdapterRegistry
from .domain.diff_detector import DiffDetector
from .infrastructure.database.connection import DatabaseConnection, DatabaseSettings
from .infrastructure.notification_client import NotificationClient, NotificationLevel
from .infrastructure.output_writer import OutputWriter
from .infrastructure.snapshot_store import SnapshotStore
from .llm.adapter import LlmAdapter
from .llm.config import SiteConfigLoader, SitesConfig
from .llm.html_preprocessor import HtmlPreprocessor
from .llm.providers.anthropic_provider import AnthropicProvider
from .llm.providers.base import LlmProvider
from .llm.providers.fallback_provider import FallbackProvider
from .llm.providers.groq_provider import GroqProvider
from .llm.robots_checker import RobotsChecker
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

# 連続失敗回数の自動スキップ閾値（Requirement 6.4 系）
# broken_sites.yaml の consecutive_failures がこの値以上のサイトは、毎回の収集で
# スキップする（人手で adapter を修正したら broken_sites.yaml の当該エントリを
# 削除 or consecutive_failures をリセットすれば再開する）。
BROKEN_SITE_SKIP_THRESHOLD = int(os.getenv("BROKEN_SITE_SKIP_THRESHOLD", "3"))

# スキップ対象サイトの再チェック猶予日数。
# consecutive_failures が閾値以上でも、最終失敗から この日数 経過していれば
# 再試行する。サイト側 / adapter が修正された場合に自動復活させるための仕組み。
# 0 以下を指定するとスキップは恒久的になり、手動で broken_sites.yaml を編集
# しない限り復活しない（旧挙動互換）。
BROKEN_SITE_RECHECK_DAYS = int(os.getenv("BROKEN_SITE_RECHECK_DAYS", "7"))


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


def _effective_extraction(site, config: SitesConfig) -> str:
    """サイトの effective な extraction 値を返す

    site.extraction が明示的に設定されていればそれを使い、
    None ならグローバル default_extraction を採用する。
    """
    if site.extraction is not None:
        return site.extraction
    return config.extraction.default_extraction


def run_llm_sites(
    config: SitesConfig,
    snapshot_store: SnapshotStore,
    diff_detector: DiffDetector,
    output_writer: OutputWriter,
    notification_client: NotificationClient,
    db_connection: DatabaseConnection | None,
    logger: logging.Logger,
    broken_tracker: BrokenSitesTracker | None = None,
) -> tuple[int, int, list[str]]:
    """LLMベースのサイト群を収集

    Returns:
        (成功サイト数, 失敗サイト数, 0件で完了したサイト名一覧)。
        0 件サイトは success 扱いだが、HTML 構造変化で行抽出が空配列に
        なっている可能性があるため、ログ上で別途可視化する。
    """
    succeeded = 0
    failed = 0
    zero_count_sites: list[str] = []
    robots = RobotsChecker()

    for site in config.sites:
        if _effective_extraction(site, config) != "llm":
            continue

        if broken_tracker and broken_tracker.should_skip(
            site.name,
            threshold=BROKEN_SITE_SKIP_THRESHOLD,
            grace_days=BROKEN_SITE_RECHECK_DAYS if BROKEN_SITE_RECHECK_DAYS > 0 else None,
        ):
            logger.warning(
                f"[{site.name}] 連続失敗 "
                f"{broken_tracker.consecutive_failures(site.name)}回 — "
                f"自動スキップ (閾値={BROKEN_SITE_SKIP_THRESHOLD}, "
                f"再チェック猶予={BROKEN_SITE_RECHECK_DAYS}日)"
            )
            continue

        site_start = time.time()
        logger.info(f"=== LLM収集開始: {site.name} ===")

        # robots.txt を尊重: disallow なサイトはスキップ（成功・失敗どちらにもカウントしない）
        if not robots.is_allowed(site.list_url):
            logger.warning(
                f"[{site.name}] robots.txt により disallow されています。スキップします: "
                f"{site.list_url}"
            )
            continue

        # タイムアウト解決優先順位: サイト個別 (sites.yaml の timeout_sec) > requires_js 既定 > 通常既定
        if site.timeout_sec is not None:
            timeout = site.timeout_sec
        elif getattr(site, "requires_js", False):
            timeout = SITE_TIMEOUT_JS_SEC
        else:
            timeout = SITE_TIMEOUT_SEC

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
                succeeded += 1
                if result.total_collected == 0:
                    zero_count_sites.append(site.name)
            else:
                logger.error(f"[{site.name}] 収集失敗: {', '.join(result.errors)}")
                failed += 1

        except SiteCollectionTimeoutError as e:
            elapsed = time.time() - site_start
            logger.warning(
                f"[{site.name}] タイムアウト ({elapsed:.1f}秒, limit={timeout}秒): "
                f"{e}. 次のサイトに進みます。"
            )
            failed += 1
            continue
        except Exception as e:
            elapsed = time.time() - site_start
            logger.error(
                f"[{site.name}] エラー発生 ({elapsed:.1f}秒): {e}",
                exc_info=True,
            )
            failed += 1
            continue  # 他のサイトの処理を継続

    return succeeded, failed, zero_count_sites


def run_rule_based_sites(
    config: SitesConfig,
    snapshot_store: SnapshotStore,
    diff_detector: DiffDetector,
    output_writer: OutputWriter,
    notification_client: NotificationClient,
    db_connection: DatabaseConnection | None,
    logger: logging.Logger,
    broken_tracker: BrokenSitesTracker | None = None,
    previous_site_counts: dict[str, int] | None = None,
) -> tuple[int, int, list[str]]:
    """rule-based 抽出方式でサイト群を収集

    SiteAdapterRegistry に登録された adapter のみ rule-based 経路で実行。
    未登録サイトは run_llm_sites 側で拾われる（混在運用を前提）。
    rule 失敗 + fallback_to_llm=True のサイトは LLM 抽出で再試行する。

    Args:
        previous_site_counts: `{site_name: 前回件数}` の dict。snapshot_store
            から計算される。「前回 ≥ 1 件 → 今回 0 件」を件数低下として監視
            ログに記録するために使う。在庫はけ (真の 0 件) と adapter 破損は
            件数だけでは区別できないため、スキップ対象化 (record_failure) は
            せず、本物の破損は list_error/detail_error/timeout で検知する。

    Returns:
        (成功サイト数, 失敗サイト数, 0件で完了したサイト名一覧)。
    """
    succeeded = 0
    failed = 0
    zero_count_sites: list[str] = []
    if previous_site_counts is None:
        previous_site_counts = {}

    for site in config.sites:
        if _effective_extraction(site, config) != "rule-based":
            continue

        adapter_cls = SiteAdapterRegistry.get(site.name)
        if adapter_cls is None:
            logger.warning(
                f"[{site.name}] rule-based 指定だが adapter 未登録 — スキップ "
                f"(run_llm_sites 側で fallback)"
            )
            continue

        if broken_tracker and broken_tracker.should_skip(
            site.name,
            threshold=BROKEN_SITE_SKIP_THRESHOLD,
            grace_days=BROKEN_SITE_RECHECK_DAYS if BROKEN_SITE_RECHECK_DAYS > 0 else None,
        ):
            logger.warning(
                f"[{site.name}] 連続失敗 "
                f"{broken_tracker.consecutive_failures(site.name)}回 — "
                f"自動スキップ (閾値={BROKEN_SITE_SKIP_THRESHOLD}, "
                f"再チェック猶予={BROKEN_SITE_RECHECK_DAYS}日)"
            )
            continue

        site_start = time.time()
        logger.info(f"=== rule-based 収集開始: {site.name} ===")
        # タイムアウト解決優先順位: サイト個別 (sites.yaml の timeout_sec) > requires_js 既定 > 通常既定
        # ※ run_llm_sites と同じロジック。過去 run で `run_rule_based_sites` だけ
        # `site.timeout_sec` を読まず、高知 (timeout_sec=240 設定済) が常に 120s で
        # timeout していたため修正。
        if site.timeout_sec is not None:
            timeout = site.timeout_sec
        elif getattr(site, "requires_js", False):
            timeout = SITE_TIMEOUT_JS_SEC
        else:
            timeout = SITE_TIMEOUT_SEC

        try:
            adapter = adapter_cls(site)
            service = CollectorService(
                adapter=adapter,
                diff_detector=diff_detector,
                output_writer=output_writer,
                notification_client=notification_client,
                snapshot_store=snapshot_store,
                db_connection=db_connection,
            )

            with site_timeout(timeout, site.name):
                result = service.run_collection()

            elapsed = time.time() - site_start

            # 件数低下: result.success かつ 今回 0 件 かつ 前回 ≥ 1 件。
            # かつては「adapter 破損」として record_failure し自動スキップ
            # 対象にしていたが、result.success=True は adapter が正常終了した
            # 証左であり、0 件の大半は在庫はけ (真の 0 件) の誤検知だった。
            # 在庫 0 が続くと 3 回でスキップされ、動物が戻っても grace 期間
            # (既定 7 日) は再収集されない副作用があったため、ここでは監視
            # ログ + zero_count_sites 記録のみとし、スキップ対象化はしない。
            # 本物の破損は list_error/detail_error/timeout で別途 record_failure
            # される。
            prev_count = previous_site_counts.get(site.name, 0)
            is_zero_count_drop = result.success and result.total_collected == 0 and prev_count >= 1

            if result.success:
                logger.info(
                    f"[{site.name}] rule-based 収集完了: "
                    f"{result.total_collected}件, "
                    f"新規{result.new_count}, "
                    f"更新{result.updated_count}, "
                    f"処理時間{elapsed:.1f}秒"
                )
                if broken_tracker:
                    broken_tracker.record_success(site.name)
                succeeded += 1
                if result.total_collected == 0:
                    zero_count_sites.append(site.name)
                    if is_zero_count_drop:
                        logger.warning(
                            f"[{site.name}] 件数低下: 前回 {prev_count} 件 → 今回 0 件 "
                            f"(在庫 0 の可能性。adapter は正常終了したためスキップ対象化"
                            f"はしない。構造変更が疑わしい場合は手動確認)"
                        )
            else:
                err_msg = "; ".join(result.errors)
                logger.error(f"[{site.name}] rule-based 収集失敗: {err_msg}")
                if broken_tracker:
                    broken_tracker.record_failure(site.name, err_msg)
                # fallback_to_llm: True ならLLM経路で再試行
                if getattr(site, "fallback_to_llm", False):
                    logger.info(f"[{site.name}] fallback_to_llm 有効 — LLM 抽出で再試行")
                    try:
                        provider_name, model = SiteConfigLoader.resolve_provider(site, config)
                        provider = create_provider(provider_name, model)
                        llm_adapter = LlmAdapter(
                            site_config=site,
                            provider=provider,
                            preprocessor=HtmlPreprocessor(),
                        )
                        llm_service = CollectorService(
                            adapter=llm_adapter,
                            diff_detector=diff_detector,
                            output_writer=output_writer,
                            notification_client=notification_client,
                            snapshot_store=snapshot_store,
                            db_connection=db_connection,
                        )
                        with site_timeout(timeout, site.name):
                            llm_result = llm_service.run_collection()
                        if llm_result.success:
                            logger.info(
                                f"[{site.name}] LLM フォールバック成功: "
                                f"{llm_result.total_collected}件"
                            )
                            succeeded += 1
                            if llm_result.total_collected == 0:
                                zero_count_sites.append(site.name)
                            continue
                    except Exception as fb_e:
                        logger.error(f"[{site.name}] LLM フォールバックも失敗: {fb_e}")
                failed += 1

        except SiteCollectionTimeoutError as e:
            elapsed = time.time() - site_start
            logger.warning(f"[{site.name}] タイムアウト ({elapsed:.1f}秒, limit={timeout}秒): {e}")
            if broken_tracker:
                broken_tracker.record_failure(site.name, f"timeout: {e}")
            failed += 1
            continue
        except Exception as e:
            elapsed = time.time() - site_start
            logger.error(f"[{site.name}] エラー発生 ({elapsed:.1f}秒): {e}", exc_info=True)
            if broken_tracker:
                broken_tracker.record_failure(site.name, str(e))
            failed += 1
            continue

    return succeeded, failed, zero_count_sites


# 全体失敗率がこの値を超えると CRITICAL、超えないが critical_sites>0 なら WARNING
_RUN_FAIL_RATIO_CRITICAL = 0.2


def _send_run_summary_alert(
    *,
    notification_client: NotificationClient,
    broken_tracker: BrokenSitesTracker | None,
    total_sites: int,
    total_succeeded: int,
    total_failed: int,
    threshold: int,
    logger: logging.Logger,
) -> None:
    """1 回の run 終了時に Slack へサマリアラートを送る。

    判定:
      - failure_ratio > 0.2 OR 全件失敗 → CRITICAL
      - critical_sites (consec>=threshold) > 0 OR total_failed > 0 → WARNING
      - 何も無ければ通知しない

    Slack webhook 未設定時は NotificationClient が自動的に no-op になる。
    """
    if total_sites == 0:
        return

    critical_sites_list: list[str] = []
    if broken_tracker is not None:
        try:
            critical_sites_list = broken_tracker.critical_sites(threshold=threshold)
        except Exception as e:
            logger.warning(f"critical_sites 取得失敗: {e}")

    failure_ratio = total_failed / total_sites if total_sites else 0.0
    is_critical = failure_ratio > _RUN_FAIL_RATIO_CRITICAL or (
        total_succeeded == 0 and total_failed > 0
    )
    has_warning = bool(critical_sites_list) or total_failed > 0

    if not (is_critical or has_warning):
        return

    level = NotificationLevel.CRITICAL if is_critical else NotificationLevel.WARNING
    message = (
        f"収集完了: 成功 {total_succeeded}/{total_sites} (失敗 {total_failed}, "
        f"失敗率 {failure_ratio:.1%})"
    )
    details: dict[str, Any] = {
        "total_sites": total_sites,
        "succeeded": total_succeeded,
        "failed": total_failed,
        "failure_ratio": f"{failure_ratio:.1%}",
        "auto_skip_threshold": threshold,
        "critical_sites_count": len(critical_sites_list),
    }
    if critical_sites_list:
        details["critical_sites_sample"] = ", ".join(critical_sites_list[:10]) + (
            "..." if len(critical_sites_list) > 10 else ""
        )
    try:
        notification_client.send_alert(level, message, details)
    except Exception as e:
        logger.warning(f"run summary alert 送信失敗: {e}")


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

        # === sites.yaml に基づく実行 (rule-based + LLM 混在) ===
        if not kochi_only:
            config_path = Path(__file__).parent / "config" / "sites.yaml"
            if config_path.exists():
                config = SiteConfigLoader.load(config_path)
                logger.info(
                    f"サイト設定読込: {len(config.sites)}サイト "
                    f"(default_provider={config.extraction.default_provider}, "
                    f"default_extraction={config.extraction.default_extraction})"
                )

                # 前回スナップショットから各サイトの件数を集計する。
                # 「前回 ≥ 1 件 → 今回 0 件」のサイトを件数低下として監視ログに
                # 記録するために使う (Task #9, 誤検知削減で改訂)。
                site_list_urls = {s.name: s.list_url for s in config.sites}
                previous_site_counts = snapshot_store.load_counts_by_site_url_prefix(site_list_urls)
                drop_watch_eligible = [n for n, c in previous_site_counts.items() if c >= 1]
                logger.info(
                    f"前回スナップショット: {sum(previous_site_counts.values())} 件, "
                    f"件数低下監視対象 {len(drop_watch_eligible)} サイト"
                )

                # 前回件数の計算が終わったら snapshot / output をリセット。
                # CollectorService が **サイトごと** に save_snapshot / write_output を
                # 呼ぶ仕様のため、両ファイルは merge モードで累積される。run の境界を
                # クリアにするため、ここで一度だけ削除して fresh state からスタート。
                # これを忘れると過去 run のデータが残り続ける。
                snapshot_store.reset()
                output_writer.reset()
                logger.info("snapshot / output をリセット (fresh run 開始)")

                # rule-based サイト群 (Registry 登録済み adapter を使用)
                # BROKEN_SITES_PATH env でパス差し替え可能（テスト分離のため）。
                broken_tracker_path = Path(
                    os.environ.get("BROKEN_SITES_PATH", "data/broken_sites.yaml")
                )
                broken_tracker = BrokenSitesTracker(broken_tracker_path)
                rule_succeeded, rule_failed, rule_zero = run_rule_based_sites(
                    config=config,
                    snapshot_store=snapshot_store,
                    diff_detector=diff_detector,
                    output_writer=output_writer,
                    notification_client=notification_client,
                    db_connection=db_connection,
                    logger=logger,
                    broken_tracker=broken_tracker,
                    previous_site_counts=previous_site_counts,
                )

                # LLM サイト群（rule-based 化されてないサイト）
                llm_succeeded, llm_failed, llm_zero = run_llm_sites(
                    config=config,
                    snapshot_store=snapshot_store,
                    diff_detector=diff_detector,
                    output_writer=output_writer,
                    notification_client=notification_client,
                    db_connection=db_connection,
                    logger=logger,
                    broken_tracker=broken_tracker,
                )

                total_succeeded = rule_succeeded + llm_succeeded
                total_failed = rule_failed + llm_failed
                zero_count_sites = rule_zero + llm_zero
                logger.info(
                    f"収集サマリ: 成功 {total_succeeded}サイト "
                    f"(うち 0 件 {len(zero_count_sites)}サイト), "
                    f"失敗 {total_failed}サイト "
                    f"(rule-based: {rule_succeeded}/{rule_succeeded + rule_failed}, "
                    f"LLM: {llm_succeeded}/{llm_succeeded + llm_failed})"
                )
                if zero_count_sites:
                    logger.warning(
                        f"抽出 0 件のサイト {len(zero_count_sites)}件: "
                        + ", ".join(zero_count_sites[:20])
                        + ("..." if len(zero_count_sites) > 20 else "")
                    )

                # 部分失敗は exit 0 で許容（commit & push を進めるため）。
                # 全件失敗（成功 0 かつ失敗 > 0）の場合のみ pipeline failure 扱い。
                if total_succeeded == 0 and total_failed > 0:
                    logger.error("全サイトで収集に失敗しました")
                    success = False

                # Slack 通知: 連続失敗サイト / 全体失敗率に応じて Warning/Critical
                _send_run_summary_alert(
                    notification_client=notification_client,
                    broken_tracker=broken_tracker,
                    total_sites=len(config.sites),
                    total_succeeded=total_succeeded,
                    total_failed=total_failed,
                    threshold=BROKEN_SITE_SKIP_THRESHOLD,
                    logger=logger,
                )

                # 進捗ログ
                stats = SiteAdapterRegistry.coverage_stats([s.name for s in config.sites])
                logger.info(
                    f"rule-based 進捗: {stats['rule_based']}/{stats['total']} "
                    f"(LLM 残り {stats['llm_only']})"
                )
            else:
                logger.info("サイト設定なし（sites.yaml が見つかりません）")

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
