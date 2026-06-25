"""CLI エントリーポイント"""

import asyncio
import contextlib
import logging
import os
import signal
import subprocess
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
from .adapters.rule_based.field_quality_tracker import FieldDrift, FieldQualityTracker
from .adapters.rule_based.registry import SiteAdapterRegistry
from .domain.diff_detector import DiffDetector
from .domain.quality_metrics import compute_missing_rates, group_animals_by_site
from .infrastructure.database.connection import DatabaseConnection, DatabaseSettings
from .infrastructure.notification_client import NotificationClient, NotificationLevel
from .infrastructure.output_writer import OutputWriter
from .infrastructure.site_baseline_tracker import SiteBaselineTracker, ZeroCountRegression
from .infrastructure.snapshot_store import SnapshotStore
from .llm.adapter import LlmAdapter
from .llm.config import SiteConfigLoader, SitesConfig
from .llm.html_preprocessor import HtmlPreprocessor
from .llm.providers.base import LlmProvider
from .llm.providers.groq_provider import GroqProvider
from .llm.robots_checker import RobotsChecker
from .orchestration.collector_service import CollectorService

# rule-based 100% 運用 (project_extraction_strategy.md)。LLM 経路の fallback
# 用にプロバイダ層は残すが、現状 Groq のみ。Anthropic は採算化後に再評価する。
PROVIDER_REGISTRY = {
    "groq": GroqProvider,
}

# サイト別収集のタイムアウト（秒）
# 209+ サイトを GitHub Actions の 6 時間以内に収まらせるため、ハングしたサイトを
# 切り捨てて次に進む。requires_js=True サイトは Playwright 起動が重いので長め。
# 既定は 300s: 件数増加 (例: 山梨/高知の 100+ 件 detail 取得) で 120s では
# 不十分なケースが頻発したため。サイト個別の override (timeout_sec) で上書き可。
SITE_TIMEOUT_SEC = int(os.getenv("SITE_TIMEOUT_SEC", "300"))
SITE_TIMEOUT_JS_SEC = int(os.getenv("SITE_TIMEOUT_JS_SEC", "360"))

# 並列収集の同時実行ワーカー数。ドメイン単位でグルーピングし、異なるドメインは
# 同時に処理する (同一ドメインは politeness のため引き続きシーケンシャル)。
# 91 unique host あるので 10 workers で十分な並列度を確保しつつ、GitHub Actions
# Linux ランナーの 2 cpu と requests の I/O 待ちのバランスを取る。
COLLECT_MAX_WORKERS = int(os.getenv("ONECO_COLLECT_MAX_WORKERS", "10"))

# ソフトデッドライン: site_timeout 全体の何 % を超えたら adapter に早期終了を促すか。
# 例: timeout=300s, soft=0.8 → 240s 経過時点で「残りの detail 取得をスキップして
# これまでの収集物を返す」フォールバック動作。タイムアウト失敗で全件破棄するより、
# 部分的にでも保存できた方がユーザー価値が高いため。
COLLECT_SOFT_DEADLINE_RATIO = float(os.getenv("ONECO_SOFT_DEADLINE_RATIO", "0.8"))

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
    """プロバイダーインスタンスを生成 (現状 Groq のみ)"""
    cls = PROVIDER_REGISTRY.get(provider_name)
    if cls is None:
        supported = ", ".join(sorted(PROVIDER_REGISTRY.keys()))
        raise ValueError(f"未対応プロバイダー: {provider_name}。サポート対象: {supported}")
    return cls(model=model)


def _effective_extraction(site, config: SitesConfig) -> str:
    """サイトの effective な extraction 値を返す

    site.extraction が明示的に設定されていればそれを使い、
    None ならグローバル default_extraction を採用する。
    """
    if site.extraction is not None:
        return site.extraction
    return config.extraction.default_extraction


def _apply_robots_policy(site, robots: RobotsChecker, logger: logging.Logger) -> bool:
    """robots.txt を尊重して 1 サイトの収集可否を判定する（LLM/rule-based 経路で共有）。

    - disallow なサイトは警告ログを出して False を返す（呼び出し側で continue させる）。
    - allow なら robots.txt の Crawl-delay を site.request_interval に反映し
      （指定があり既存間隔より大きい場合のみ）、True を返す。

    判定不能（非 http / fetch 失敗 / robots.txt 未配置）は is_allowed が True を返す
    best-effort。従来 LLM 経路にのみ存在したこのロジックを共通化し、本番主力の
    rule-based 経路でも robots を尊重させる（terms の「robots を尊重」との言行一致）。
    """
    if not robots.is_allowed(site.list_url):
        logger.warning(
            f"[{site.name}] robots.txt により disallow されています。スキップします: "
            f"{site.list_url}"
        )
        return False

    crawl_delay = robots.crawl_delay(site.list_url)
    if crawl_delay is not None and crawl_delay > site.request_interval:
        logger.info(
            f"[{site.name}] robots.txt Crawl-delay={crawl_delay}s を採用 "
            f"(request_interval={site.request_interval}s)"
        )
        site.request_interval = crawl_delay
    return True


def run_llm_sites(
    config: SitesConfig,
    snapshot_store: SnapshotStore,
    diff_detector: DiffDetector,
    output_writer: OutputWriter,
    notification_client: NotificationClient,
    db_connection: DatabaseConnection | None,
    logger: logging.Logger,
    broken_tracker: BrokenSitesTracker | None = None,
) -> tuple[int, int, list[str], list[str]]:
    """LLMベースのサイト群を収集

    Returns:
        (成功サイト数, 失敗サイト数, 0件で完了したサイト名一覧,
         成功した site_name 一覧)。
        0 件サイトは success 扱いだが、HTML 構造変化で行抽出が空配列に
        なっている可能性があるため、ログ上で別途可視化する。
        成功 site_name 一覧は SiteBaselineTracker の filter 用。
        robots-disallowed / skip 対象 / 失敗サイトを baseline=0 で記録すると
        永続ファイル汚染になるため、main() ではこの一覧でループを絞る。
    """
    succeeded = 0
    failed = 0
    zero_count_sites: list[str] = []
    succeeded_site_names: list[str] = []
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

        # robots.txt を尊重: disallow ならスキップ、allow なら Crawl-delay を反映
        # （成功・失敗どちらにもカウントしない）。rule-based 経路と共有する。
        if not _apply_robots_policy(site, robots, logger):
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
                succeeded_site_names.append(site.name)
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

    return succeeded, failed, zero_count_sites, succeeded_site_names


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
) -> tuple[int, int, list[str], list[str]]:
    """rule-based 抽出方式でサイト群をドメイン単位の並列で収集

    SiteAdapterRegistry に登録された adapter のみ rule-based 経路で実行。
    未登録サイトは run_llm_sites 側で拾われる（混在運用を前提）。
    rule 失敗 + fallback_to_llm=True のサイトは LLM 抽出で再試行する。

    並列化方針 (Phase 1):
    - sites を list_url のドメイン単位でグルーピング
    - 異なるドメインは ThreadPoolExecutor で並列処理
    - 同一ドメインはシーケンシャル (politeness throttle / 偽計業務妨害リスク低減)
    - 1 サイトの timeout は future.result(timeout=) で実装 (SIGALRM 非依存で worker
      thread でも動作)

    フォールバック (Phase 3):
    - ハード timeout の手前で SoftDeadline.should_soft_stop() が True になる
    - CollectorService の detail ループがそれを見て早期 break → 既収集分を保存

    Args:
        previous_site_counts: `{site_name: 前回件数}` の dict。snapshot_store
            から計算される。「前回 ≥ 1 件 → 今回 0 件」を件数低下として監視
            ログに記録するために使う。在庫はけ (真の 0 件) と adapter 破損は
            件数だけでは区別できないため、スキップ対象化 (record_failure) は
            せず、本物の破損は list_error/detail_error/timeout で検知する。

    Returns:
        (成功サイト数, 失敗サイト数, 0件で完了したサイト名一覧,
         成功した site_name 一覧)。
        成功 site_name 一覧は SiteBaselineTracker の filter 用。
        robots-disallowed / 未登録 adapter / skip 対象 / 失敗サイトを baseline=0
        で記録すると永続ファイル汚染 (永久 0 件回帰扱い) になるため、
        main() ではこの一覧でループを絞る。
    """
    from .orchestration.parallel_runner import run_sites_parallel
    from .orchestration.soft_deadline import SoftDeadline

    if previous_site_counts is None:
        previous_site_counts = {}

    # 並列対象を絞り込み: rule-based & adapter 登録あり & 未スキップ & robots allow
    robots = RobotsChecker()
    eligible_sites = []
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
        # robots.txt を尊重: disallow ならスキップ、allow なら Crawl-delay を反映。
        # 逐次実行のこのフィルタ段で評価する（並列収集前なのでスレッド安全）。
        if not _apply_robots_policy(site, robots, logger):
            continue
        eligible_sites.append(site)

    def _resolve_timeout(site) -> float:
        if site.timeout_sec is not None:
            return float(site.timeout_sec)
        if getattr(site, "requires_js", False):
            return float(SITE_TIMEOUT_JS_SEC)
        return float(SITE_TIMEOUT_SEC)

    def _collect_one(site, timeout_seconds: float):
        """worker thread から呼ばれる 1 サイトの収集処理。

        戻り値は (result, fallback_result, prev_count) のタプル。outcome.data に
        入って main thread で集計される。例外は parallel_runner が outcome.error
        に詰めてくれるため、ここでは握り潰さない。
        """
        logger.info(f"=== rule-based 収集開始: {site.name} ===")
        soft = SoftDeadline(seconds=timeout_seconds, soft_ratio=COLLECT_SOFT_DEADLINE_RATIO)
        adapter_cls_local = SiteAdapterRegistry.get(site.name)
        assert adapter_cls_local is not None  # eligible_sites フィルタで保証済
        adapter = adapter_cls_local(site)
        service = CollectorService(
            adapter=adapter,
            diff_detector=diff_detector,
            output_writer=output_writer,
            notification_client=notification_client,
            snapshot_store=snapshot_store,
            db_connection=db_connection,
        )
        result = service.run_collection(soft_deadline=soft)
        prev_count = previous_site_counts.get(site.name, 0)

        # fallback_to_llm: rule-based 失敗時に LLM 経路で再試行
        fallback_result = None
        if not result.success and getattr(site, "fallback_to_llm", False):
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
                # フォールバック側も soft deadline を共有 (残り時間で打ち切り)
                fallback_result = llm_service.run_collection(soft_deadline=soft)
            except Exception as fb_e:
                logger.error(f"[{site.name}] LLM フォールバックも失敗: {fb_e}")
        return result, fallback_result, prev_count

    succeeded = 0
    failed = 0
    zero_count_sites: list[str] = []
    succeeded_site_names: list[str] = []

    def _on_outcome(outcome) -> None:
        nonlocal succeeded, failed
        site_name = outcome.site_name
        if outcome.status == "timeout":
            logger.warning(
                f"[{site_name}] タイムアウト ({outcome.elapsed_seconds:.1f}秒): {outcome.error}"
            )
            if broken_tracker:
                broken_tracker.record_failure(site_name, f"timeout: {outcome.error}")
            failed += 1
            return
        if outcome.status == "failure":
            logger.error(
                f"[{site_name}] エラー発生 ({outcome.elapsed_seconds:.1f}秒): {outcome.error}",
                exc_info=outcome.error,
            )
            if broken_tracker:
                broken_tracker.record_failure(site_name, str(outcome.error))
            failed += 1
            return

        # success path
        result, fallback_result, prev_count = outcome.data
        elapsed = outcome.elapsed_seconds
        is_zero_count_drop = result.success and result.total_collected == 0 and prev_count >= 1

        if result.success:
            logger.info(
                f"[{site_name}] rule-based 収集完了: "
                f"{result.total_collected}件, "
                f"新規{result.new_count}, "
                f"更新{result.updated_count}, "
                f"処理時間{elapsed:.1f}秒"
            )
            if broken_tracker:
                broken_tracker.record_success(site_name)
            succeeded += 1
            succeeded_site_names.append(site_name)
            if result.total_collected == 0:
                zero_count_sites.append(site_name)
                if is_zero_count_drop:
                    logger.warning(
                        f"[{site_name}] 件数低下: 前回 {prev_count} 件 → 今回 0 件 "
                        f"(在庫 0 の可能性。adapter は正常終了したためスキップ対象化"
                        f"はしない。構造変更が疑わしい場合は手動確認)"
                    )
            return

        # rule-based 失敗 → fallback 結果を見る
        err_msg = "; ".join(result.errors)
        logger.error(f"[{site_name}] rule-based 収集失敗: {err_msg}")
        if broken_tracker:
            broken_tracker.record_failure(site_name, err_msg)
        if fallback_result is not None and fallback_result.success:
            logger.info(
                f"[{site_name}] LLM フォールバック成功: {fallback_result.total_collected}件"
            )
            succeeded += 1
            succeeded_site_names.append(site_name)
            if fallback_result.total_collected == 0:
                zero_count_sites.append(site_name)
        else:
            failed += 1

    run_sites_parallel(
        sites=eligible_sites,
        collect_fn=_collect_one,
        timeout_resolver=_resolve_timeout,
        max_workers=COLLECT_MAX_WORKERS,
        on_outcome=_on_outcome,
    )

    return succeeded, failed, zero_count_sites, succeeded_site_names


# 全体失敗率がこの値を超えると CRITICAL、超えないが critical_sites>0 なら WARNING
_RUN_FAIL_RATIO_CRITICAL = 0.2


def _trigger_auto_fix(site_names: list[str], logger: logging.Logger) -> dict[str, Any]:
    """検知された壊れサイトについて auto-fix-adapter.yml ワークフローを起動する。

    Phase 1 の検知シグナル (broken_tracker.critical_sites /
    zero_count_regressions / field_drifts) を集約して、Phase 2 ワーカー
    (.github/workflows/auto-fix-adapter.yml) に橋渡しする。

    安全機構:
    - kill switch: `ONECO_AUTO_FIX_ENABLED=true` でないと一切起動しない
      (デフォルト false: 自己修復は user の明示的な opt-in が必要)
    - dry_run: `ONECO_AUTO_FIX_DRY_RUN` (default 'true') = true なら
      auto-fix worker はパッチ生成 + ガード確認までして PR は作らない。
      安定確認後 false に切り替えて本番自動修復化する段階リリース
    - 上限: `ONECO_AUTO_FIX_MAX_SITES` (default 3) で 1 run あたりの起動数を
      キャップ (並列爆発・LLM コスト爆発防止)
    - dedup: 同じサイトが複数経路 (broken + drift + zero_count) から来ても 1 度だけ
    - best-effort: gh CLI の失敗は logger.warning にとどめ、収集パイプラインは継続

    Returns:
        dict with keys:
        - invoked: dispatch 成功した workflow run 数
        - attempted: dispatch を試行した数 (失敗含む)
        - candidates: 集約された候補数 (dedup 後)
        - disabled: kill switch off だったか

        attempted > invoked は dispatch 失敗 = silent failure シグナル。
        呼び出し側 (`_send_run_summary_alert`) で Discord 通知に折り込み、
        自己修復が静かに動いていない状態を可視化する。
    """
    # 順序保持 dedup (kill switch off でも candidates 数のレポートに使う)
    seen: set[str] = set()
    uniq: list[str] = []
    for name in site_names:
        if name not in seen:
            seen.add(name)
            uniq.append(name)

    if os.environ.get("ONECO_AUTO_FIX_ENABLED", "false").lower() != "true":
        if uniq:
            logger.info(f"auto-fix-adapter: {len(uniq)} 件の検知サイトあり (kill switch off)")
        return {"invoked": 0, "attempted": 0, "candidates": len(uniq), "disabled": True}

    if not uniq:
        return {"invoked": 0, "attempted": 0, "candidates": 0, "disabled": False}

    max_sites = int(os.environ.get("ONECO_AUTO_FIX_MAX_SITES", "3"))
    targets = uniq[:max_sites]
    dry_run = os.environ.get("ONECO_AUTO_FIX_DRY_RUN", "true").lower() == "true"

    if len(uniq) > max_sites:
        logger.warning(
            f"auto-fix-adapter: 検知 {len(uniq)} 件のうち {max_sites} 件のみ起動 "
            f"(残り {len(uniq) - max_sites} 件は次回 run で対象)"
        )

    invoked = 0
    attempted = 0
    for site_name in targets:
        cmd = [
            "gh",
            "workflow",
            "run",
            "auto-fix-adapter.yml",
            "-f",
            f"site_name={site_name}",
            "-f",
            f"dry_run={'true' if dry_run else 'false'}",
        ]
        attempted += 1
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if result.returncode == 0:
                logger.info(f"auto-fix-adapter: 起動成功 site={site_name} dry_run={dry_run}")
                invoked += 1
            else:
                logger.warning(
                    f"auto-fix-adapter: 起動失敗 site={site_name} stderr={result.stderr[:200]}"
                )
        except (FileNotFoundError, OSError) as e:
            # gh CLI 未インストール / 環境不整備でクラッシュしない
            logger.warning(f"auto-fix-adapter: subprocess 失敗 ({e})")
        except Exception as e:
            # best-effort: 想定外でも収集パイプラインは止めない
            logger.warning(f"auto-fix-adapter: 想定外エラー ({e})")
    return {
        "invoked": invoked,
        "attempted": attempted,
        "candidates": len(uniq),
        "disabled": False,
    }


def _send_run_summary_alert(
    *,
    notification_client: NotificationClient,
    broken_tracker: BrokenSitesTracker | None,
    total_sites: int,
    total_succeeded: int,
    total_failed: int,
    threshold: int,
    logger: logging.Logger,
    field_drifts: list[FieldDrift] | None = None,
    zero_count_regressions: list[ZeroCountRegression] | None = None,
    auto_fix_result: dict[str, Any] | None = None,
) -> None:
    """1 回の run 終了時に Slack / Discord へサマリアラートを送る。

    `total_sites` は **実行された** サイト数 (= total_succeeded + total_failed)。
    config.sites の総数を渡してはいけない: robots-disallowed / 未登録 adapter /
    連続失敗 skip 等で実行されなかったサイトで分母が膨らむと failure_ratio が
    希釈され、CRITICAL アラートが WARNING に抑制される。

    判定:
      - failure_ratio > 0.2 OR 全件失敗 → CRITICAL
      - critical_sites (consec>=threshold) > 0
        OR total_failed > 0
        OR field_drifts (フィールド欠損率急増) > 0
        OR zero_count_regressions (過去≥1件→今0件継続) > 0
        OR auto_fix_result の dispatch 失敗 (attempted > invoked) → WARNING
      - 何も無ければ通知しない

    webhook 未設定時は NotificationClient が自動的に no-op になる。

    field_drifts: 自己修復ループ Phase 1 のフィールド欠損率ドリフト検知結果。
    各サイトについて location/age_months 等の欠損率が前回比 +閾値 急増した
    場合に投入される。adapter のラベル/セレクタ不一致シグナルとして通知に
    含める。

    zero_count_regressions: 過去に ≥1 件あったが今 0 件が継続するサイト。
    snapshot とは独立した永続ベースライン (SiteBaselineTracker) で検知され、
    「正常終了したが silent に 0 件」というサイレント破損を可視化する。

    auto_fix_result: `_trigger_auto_fix` の戻り値 dict。
    `attempted > invoked` のとき dispatch 失敗を WARNING シグナルに含め、
    自己修復が静かに動いていない状態を可視化する。
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
    drifts = list(field_drifts) if field_drifts else []
    regressions = list(zero_count_regressions) if zero_count_regressions else []
    # auto-fix dispatch 失敗の signal: attempted > invoked
    af = auto_fix_result or {}
    af_attempted = int(af.get("attempted", 0))
    af_invoked = int(af.get("invoked", 0))
    af_dispatch_failed = af_attempted > af_invoked
    has_warning = (
        bool(critical_sites_list)
        or total_failed > 0
        or bool(drifts)
        or bool(regressions)
        or af_dispatch_failed
    )

    if not (is_critical or has_warning):
        return

    level = NotificationLevel.CRITICAL if is_critical else NotificationLevel.WARNING
    message = (
        f"収集完了: 成功 {total_succeeded}/{total_sites} (失敗 {total_failed}, "
        f"失敗率 {failure_ratio:.1%})"
    )
    if drifts:
        message += f", フィールド品質ドリフト {len(drifts)} 件"
    if regressions:
        message += f", 件数ゼロ回帰 {len(regressions)} 件"
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
    if drifts:
        details["field_drifts_count"] = len(drifts)
        sample = "; ".join(
            f"[{d.site_name}] {d.field}: {d.prev_rate:.0%}→{d.curr_rate:.0%}" for d in drifts[:5]
        )
        if len(drifts) > 5:
            sample += f" ... (+{len(drifts) - 5} more)"
        details["field_drifts_sample"] = sample
    if regressions:
        details["zero_count_regressions_count"] = len(regressions)
        sample = "; ".join(
            f"[{r.site_name}] baseline {r.baseline_count}→0 ({r.consecutive_zero_runs}連続)"
            for r in regressions[:10]
        )
        if len(regressions) > 10:
            sample += f" ... (+{len(regressions) - 10} more)"
        details["zero_count_regressions_sample"] = sample
    # 自己修復ループ Phase 1→2 橋渡しの結果。attempted > invoked = silent failure。
    # candidates > 0 でも disabled なら kill switch off (info only)。
    if af:
        details["auto_fix_candidates"] = af.get("candidates", 0)
        details["auto_fix_attempted"] = af_attempted
        details["auto_fix_invoked"] = af_invoked
        if af.get("disabled"):
            details["auto_fix_disabled"] = True
        if af_dispatch_failed:
            details["auto_fix_dispatch_failures"] = af_attempted - af_invoked
            message += f", 自己修復 dispatch 失敗 {af_attempted - af_invoked} 件"
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
        if discord_url := os.environ.get("DISCORD_WEBHOOK_URL"):
            notification_config["discord_webhook_url"] = discord_url
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
                #
                # 注意: この reset() は cross-run の snapshot 再利用 (既知 source_url の
                # LLM 抽出スキップ) も意図的に無効化している。load_animal_map() は
                # reset 後に空 dict を返すため、再利用分岐は常に毎 run 再抽出になる
                # (rule-based 100% 運用では影響は小さい)。**reset() を消して再利用を
                # 「最適化」しないこと**: ヒットした個体が source_url 消滅まで再抽出
                # されず古い情報で凍結する方が、僅かな Groq コストより有害。
                snapshot_store.reset()
                output_writer.reset()
                logger.info("snapshot / output をリセット (fresh run 開始)")

                # rule-based サイト群 (Registry 登録済み adapter を使用)
                # BROKEN_SITES_PATH env でパス差し替え可能（テスト分離のため）。
                broken_tracker_path = Path(
                    os.environ.get("BROKEN_SITES_PATH", "data/broken_sites.yaml")
                )
                broken_tracker = BrokenSitesTracker(broken_tracker_path)
                rule_succeeded, rule_failed, rule_zero, rule_succeeded_names = run_rule_based_sites(
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
                llm_succeeded, llm_failed, llm_zero, llm_succeeded_names = run_llm_sites(
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
                succeeded_site_names = rule_succeeded_names + llm_succeeded_names
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

                # 失敗率・0件率の閾値ゲート (Codex リリースレビュー I-3)。
                # サイレントな大規模劣化を検知するため、環境変数で閾値を制御。
                # デフォルト 1.0 (=100%) は現状の挙動を維持（=全件失敗時のみ失敗扱い）。
                # リリース後は ONECO_MAX_FAIL_RATIO=0.3、ONECO_MAX_ZERO_RATIO=0.5 等に
                # 絞って急性的劣化を検知できる。
                total_sites = total_succeeded + total_failed
                if total_sites > 0:
                    fail_ratio = total_failed / total_sites
                    zero_ratio = len(zero_count_sites) / total_sites
                    max_fail_ratio = float(os.environ.get("ONECO_MAX_FAIL_RATIO", "1.0"))
                    max_zero_ratio = float(os.environ.get("ONECO_MAX_ZERO_RATIO", "1.0"))
                    if fail_ratio > max_fail_ratio:
                        logger.error(
                            f"失敗率 {fail_ratio:.2%} が閾値 {max_fail_ratio:.2%} を超過 "
                            f"({total_failed}/{total_sites} サイト失敗)"
                        )
                        success = False
                    if zero_ratio > max_zero_ratio:
                        logger.error(
                            f"0件サイト率 {zero_ratio:.2%} が閾値 {max_zero_ratio:.2%} を超過 "
                            f"({len(zero_count_sites)}/{total_sites} サイト)"
                        )
                        success = False

                # フィールド欠損率ドリフト検知 (自己修復ループ Phase 1)。
                # 今 run の snapshot を読み、各サイトについて location/age_months
                # 等の欠損率を計算 → FieldQualityTracker に記録 → 前回比 +閾値
                # 急増を検知。検出されたドリフトは Slack 通知に含めて adapter
                # 修復ワーカー (Phase 2) のシグナルとする。失敗しても収集
                # パイプラインは止めない (best-effort)。
                field_drifts: list[FieldDrift] = []
                try:
                    fq_path = Path(
                        os.environ.get("FIELD_QUALITY_DRIFT_PATH", "data/field_quality_drift.yaml")
                    )
                    fq_tracker = FieldQualityTracker(fq_path)
                    # load_snapshot() は後方互換のため常に空リストを返すスタブ。
                    # 今 run の実データは load_animal_map() (= 後段の件数集計と同じ
                    # ソース) から取る。これを使わないと欠損率が常に空集計になり、
                    # フィールド品質ドリフト検知が無音化する。
                    animals_now = list(snapshot_store.load_animal_map().values())
                    site_groups = group_animals_by_site(animals_now, site_list_urls)
                    for site_name, animals in site_groups.items():
                        rates = compute_missing_rates(animals)
                        fq_tracker.record(site_name, rates, len(animals))
                    field_drifts = fq_tracker.detect_drifts()
                    if field_drifts:
                        logger.warning(f"フィールド欠損率ドリフト検知: {len(field_drifts)} 件")
                        for d in field_drifts[:10]:
                            logger.warning(
                                f"  [{d.site_name}] {d.field}: "
                                f"{d.prev_rate:.0%} → {d.curr_rate:.0%} "
                                f"(+{d.delta:.0%})"
                            )
                except Exception as e:
                    logger.warning(f"フィールド欠損率ドリフト検知失敗: {e}")

                # サイト別件数の永続ベースライン更新 + ゼロ件回帰検知。
                # snapshot は run ごとに reset されるため、0 件回帰が 1 run しか
                # 検知されず 2 run 目以降は沈黙する盲点があった。snapshot とは独立
                # した永続ファイル (data/site_baselines.yaml) で「過去≥1件→今0件」を
                # 毎 run 検知する。
                #
                # 記録対象は **実行成功したサイトのみ** (succeeded_site_names)。
                # robots-disallowed / 未登録 adapter / skip 対象 / 失敗サイトを
                # baseline=0 で記録すると、本来「未実行」のサイトが「過去 ≥1 件
                # だが今 0 件継続」として誤検知され、永続ファイルに残り続ける
                # (auto-fix 候補として誤 dispatch、CRITICAL アラート希釈)。
                # 失敗サイトは broken_tracker / critical_sites 側で扱う。
                # best-effort: 失敗しても収集は止めない。
                zero_regressions: list[ZeroCountRegression] = []
                try:
                    baseline_path = Path(
                        os.environ.get("SITE_BASELINE_PATH", "data/site_baselines.yaml")
                    )
                    baseline_tracker = SiteBaselineTracker(baseline_path)
                    current_site_counts = snapshot_store.load_counts_by_site_url_prefix(
                        site_list_urls
                    )
                    for site_name in succeeded_site_names:
                        baseline_tracker.record(site_name, current_site_counts.get(site_name, 0))
                    zero_drop_threshold = int(os.environ.get("ONECO_ZERO_DROP_THRESHOLD", "2"))
                    zero_regressions = baseline_tracker.detect_zero_count_regressions(
                        threshold=zero_drop_threshold
                    )
                    if zero_regressions:
                        logger.warning(
                            f"件数ゼロ回帰検知: {len(zero_regressions)} サイト "
                            f"(過去≥1件→今0件が{zero_drop_threshold}回以上連続)"
                        )
                        for r in zero_regressions[:10]:
                            logger.warning(
                                f"  [{r.site_name}] baseline {r.baseline_count} → 0 "
                                f"({r.consecutive_zero_runs}連続)"
                            )
                except Exception as e:
                    logger.warning(f"件数ベースライン追跡失敗: {e}")

                # 自己修復ループ Phase 1→2 橋渡し: 検知サイトを auto-fix-adapter に
                # 渡して LLM-assisted patch worker を起動する (kill switch off の
                # 場合は no-op)。失敗時も収集パイプラインは止めない。
                # 順序: summary 通知より先に実行し、auto_fix の dispatch 結果を
                # Discord に折り込めるようにする (silent failure 検知)。
                auto_fix_result: dict[str, Any] = {
                    "invoked": 0,
                    "attempted": 0,
                    "candidates": 0,
                    "disabled": False,
                }
                try:
                    candidate_sites: list[str] = []
                    try:
                        candidate_sites.extend(
                            broken_tracker.critical_sites(threshold=BROKEN_SITE_SKIP_THRESHOLD)
                        )
                    except Exception as e:
                        logger.warning(f"critical_sites 取得失敗: {e}")
                    candidate_sites.extend(r.site_name for r in zero_regressions)
                    candidate_sites.extend(d.site_name for d in field_drifts)
                    auto_fix_result = _trigger_auto_fix(candidate_sites, logger=logger)
                except Exception as e:
                    logger.warning(f"auto-fix 橋渡しでエラー: {e}")

                # Slack / Discord 通知: 連続失敗サイト / 全体失敗率 / 欠損率ドリフト /
                # 件数ゼロ回帰 / 自己修復 dispatch 失敗 に応じて Warning/Critical
                # `total_sites` は実行された数 (= total_succeeded + total_failed)。
                # len(config.sites) を渡すと robots-disallowed / 未登録 adapter /
                # 連続失敗 skip 等で実行されなかったサイトで分母が膨らみ、
                # failure_ratio が希釈されて CRITICAL アラートが WARNING に
                # 抑制される (例: 60 実行中 30 失敗 = 50% が、209 中 30 = 14%
                # に化けて閾値 20% 未満扱い)。
                _send_run_summary_alert(
                    notification_client=notification_client,
                    broken_tracker=broken_tracker,
                    total_sites=total_succeeded + total_failed,
                    total_succeeded=total_succeeded,
                    total_failed=total_failed,
                    threshold=BROKEN_SITE_SKIP_THRESHOLD,
                    logger=logger,
                    field_drifts=field_drifts,
                    zero_count_regressions=zero_regressions,
                    auto_fix_result=auto_fix_result,
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
