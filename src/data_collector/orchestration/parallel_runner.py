"""ドメイン単位で並列収集を行う runner。

設計方針:
- 同一ドメイン内のサイトはシーケンシャル (politeness throttle が adapter インスタンス
  内部にあり、同一ドメインへの連続アクセスは 2s 間隔を保証する必要があるため)。
- 異なるドメインは並列に実行する。91 unique host を 10 worker で処理することで
  最も遅いドメイン (= 最も多サイトを持つドメイン) の処理時間がボトルネックになる。
- 1 サイトの timeout は ThreadPoolExecutor.submit(...).result(timeout=) で実装。
  SIGALRM は main thread でしか動かないため、worker thread からは使えない。

スレッド安全性:
- file 書き込み (OutputWriter, SnapshotStore, BrokenSitesTracker) は呼び出し側で
  Lock を用意してこの runner に渡す。本 runner はサイト 1 件を処理する関数
  (collect_fn) を受け取るだけで、共有状態には触らない。
- collect_fn 内部での lock 取得は collect_fn の責務。
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SiteRunOutcome:
    """1 サイト処理の結果ラベル。collect_fn の戻り値は data に保持する。"""

    site_name: str
    domain: str
    status: str  # "success" | "failure" | "timeout"
    elapsed_seconds: float
    data: Any = None
    error: BaseException | None = None


def _domain_of(list_url: str) -> str:
    """list_url から politeness 対象のドメインを取り出す。

    scheme を含まない URL は warn して空文字を返し、呼び出し側で
    「単独ドメイン」扱いされる (= 並列バケットが 1 つ増えるだけ)。
    """
    try:
        netloc = urlparse(list_url).netloc
    except Exception:
        netloc = ""
    if not netloc:
        logger.warning("could not extract domain from list_url=%r", list_url)
    return netloc.lower()


def group_sites_by_domain(sites: list[Any]) -> dict[str, list[Any]]:
    """sites を list_url のドメイン単位でグルーピングする。

    同一ドメインへの複数 list_url (例: 山梨県 6 サイト) は同じバケットに入れて
    sequential 処理することで politeness throttle を維持する。
    """
    buckets: dict[str, list[Any]] = defaultdict(list)
    for site in sites:
        domain = _domain_of(getattr(site, "list_url", "") or "")
        buckets[domain].append(site)
    return dict(buckets)


def _run_one_site_with_timeout(
    site: Any,
    collect_fn: Callable[[Any, float], Any],
    timeout_seconds: float,
) -> SiteRunOutcome:
    """1 サイトを timeout 付きで処理する。

    collect_fn は内部で長時間 I/O を行うため、別 worker thread で実行して
    future.result(timeout=) で打ち切る。collect_fn は協調的に止まれるよう
    SoftDeadline を受け取る (秒数を渡す形にして runner 側で組み立てる)。
    """
    site_name = getattr(site, "name", "unknown")
    domain = _domain_of(getattr(site, "list_url", "") or "")
    start = time.monotonic()

    with ThreadPoolExecutor(max_workers=1) as inner:
        future = inner.submit(collect_fn, site, timeout_seconds)
        try:
            result = future.result(timeout=timeout_seconds)
            return SiteRunOutcome(
                site_name=site_name,
                domain=domain,
                status="success",
                elapsed_seconds=time.monotonic() - start,
                data=result,
            )
        except FutureTimeoutError:
            return SiteRunOutcome(
                site_name=site_name,
                domain=domain,
                status="timeout",
                elapsed_seconds=time.monotonic() - start,
                error=TimeoutError(f"site {site_name} timed out after {timeout_seconds}s"),
            )
        except BaseException as e:
            return SiteRunOutcome(
                site_name=site_name,
                domain=domain,
                status="failure",
                elapsed_seconds=time.monotonic() - start,
                error=e,
            )


def _process_domain_bucket(
    domain: str,
    sites_in_domain: list[Any],
    collect_fn: Callable[[Any, float], Any],
    timeout_resolver: Callable[[Any], float],
) -> list[SiteRunOutcome]:
    """1 ドメイン内のサイトを順次処理して outcome リストを返す。

    同一ドメインの politeness throttle を維持するため、必ず sequential。
    """
    outcomes: list[SiteRunOutcome] = []
    for site in sites_in_domain:
        timeout_seconds = timeout_resolver(site)
        outcome = _run_one_site_with_timeout(site, collect_fn, timeout_seconds)
        outcomes.append(outcome)
    return outcomes


def run_sites_parallel(
    sites: list[Any],
    collect_fn: Callable[[Any, float], Any],
    timeout_resolver: Callable[[Any], float],
    max_workers: int = 10,
    on_outcome: Callable[[SiteRunOutcome], None] | None = None,
) -> list[SiteRunOutcome]:
    """sites をドメイン単位で並列収集する。

    Args:
        sites: SiteConfig のリスト (list_url / name 属性を持つ任意のオブジェクト)。
        collect_fn: ``collect_fn(site, timeout_seconds) -> Any`` シングルサイト処理。
            戻り値は outcome.data に保持される。長時間処理は collect_fn 内部で
            SoftDeadline 等を使って協調的に早期終了することを推奨。
        timeout_resolver: ``timeout_resolver(site) -> float`` サイト個別の
            timeout を返す。
        max_workers: ドメイン並列数の上限。
        on_outcome: 各サイト完了時に呼ばれるコールバック (進捗ログ用)。

    Returns:
        sites と同じ順序ではなく、完了順の outcome リスト。
    """
    buckets = group_sites_by_domain(sites)
    if not buckets:
        return []

    # max_workers をバケット数で頭打ちにする (バケット数 < max_workers のとき無駄が出る)
    effective_workers = min(max_workers, len(buckets))
    logger.info(
        "並列収集開始: %d サイト / %d ドメイン / %d ワーカー",
        sum(len(s) for s in buckets.values()),
        len(buckets),
        effective_workers,
    )

    outcomes: list[SiteRunOutcome] = []
    with ThreadPoolExecutor(
        max_workers=effective_workers, thread_name_prefix="oneco-collect"
    ) as ex:
        future_to_domain = {
            ex.submit(
                _process_domain_bucket,
                domain,
                sites_in_domain,
                collect_fn,
                timeout_resolver,
            ): domain
            for domain, sites_in_domain in buckets.items()
        }
        for fut in as_completed(future_to_domain):
            domain = future_to_domain[fut]
            try:
                bucket_outcomes = fut.result()
            except BaseException as e:
                logger.exception("domain bucket %s failed: %s", domain, e)
                continue
            outcomes.extend(bucket_outcomes)
            if on_outcome is not None:
                for o in bucket_outcomes:
                    on_outcome(o)

    return outcomes
