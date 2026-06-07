"""ParallelRunner のユニットテスト。

検証ポイント:
- 異なるドメインの site は並列実行される (= 合計実行時間が和ではなく max)
- 同一ドメインの site は sequential 実行される (politeness throttle 維持)
- 1 サイトの timeout は他サイトを巻き込まない
- collect_fn 内の例外は outcome.error に集まり次サイトに進む
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from data_collector.orchestration.parallel_runner import (
    SiteRunOutcome,
    group_sites_by_domain,
    run_sites_parallel,
)


@dataclass
class FakeSite:
    name: str
    list_url: str


def test_group_sites_by_domain_buckets_same_host_together() -> None:
    sites = [
        FakeSite("a", "https://www.pref.yamanashi.jp/doubutsu/m_dog/index.html"),
        FakeSite("b", "https://www.pref.yamanashi.jp/doubutsu/m_cat/index.html"),
        FakeSite("c", "https://kochi-apc.com/center-data/"),
    ]
    buckets = group_sites_by_domain(sites)
    assert set(buckets.keys()) == {"www.pref.yamanashi.jp", "kochi-apc.com"}
    assert [s.name for s in buckets["www.pref.yamanashi.jp"]] == ["a", "b"]
    assert [s.name for s in buckets["kochi-apc.com"]] == ["c"]


def test_group_sites_by_domain_lowercases_host() -> None:
    sites = [FakeSite("a", "https://Example.COM/list")]
    buckets = group_sites_by_domain(sites)
    assert "example.com" in buckets


def test_parallel_run_executes_different_domains_concurrently() -> None:
    """異なるドメインは並列に動くため、3 サイト × 0.3s が 1s 未満で完了する。"""
    sites = [FakeSite(f"site-{i}", f"https://host-{i}.example.jp/") for i in range(3)]

    def collect_fn(site: FakeSite, timeout: float) -> str:
        time.sleep(0.3)
        return f"ok:{site.name}"

    start = time.monotonic()
    outcomes = run_sites_parallel(
        sites=sites,
        collect_fn=collect_fn,
        timeout_resolver=lambda _s: 5.0,
        max_workers=3,
    )
    elapsed = time.monotonic() - start

    assert len(outcomes) == 3
    assert all(o.status == "success" for o in outcomes)
    # シーケンシャルなら 0.9s。並列なら 0.3s+α。0.7s 未満を期待。
    assert elapsed < 0.7, f"parallel run too slow: {elapsed}s"


def test_same_domain_sites_run_sequentially() -> None:
    """同一ドメインのサイトは同時に走らない (politeness 維持)。"""
    same_domain_sites = [FakeSite(f"a-{i}", "https://shared.example.jp/list") for i in range(3)]
    active_count = {"current": 0, "max": 0}
    lock = threading.Lock()

    def collect_fn(site: FakeSite, timeout: float) -> str:
        with lock:
            active_count["current"] += 1
            active_count["max"] = max(active_count["max"], active_count["current"])
        time.sleep(0.1)
        with lock:
            active_count["current"] -= 1
        return site.name

    outcomes = run_sites_parallel(
        sites=same_domain_sites,
        collect_fn=collect_fn,
        timeout_resolver=lambda _s: 5.0,
        max_workers=10,
    )
    assert len(outcomes) == 3
    assert active_count["max"] == 1, "same-domain sites must not overlap"


def test_per_site_timeout_does_not_kill_other_sites() -> None:
    """遅いサイトが timeout しても、別ドメインの他サイトは完走する。"""
    sites = [
        FakeSite("slow", "https://slow.example.jp/"),
        FakeSite("fast", "https://fast.example.jp/"),
    ]

    def collect_fn(site: FakeSite, timeout: float) -> str:
        if site.name == "slow":
            time.sleep(2.0)
        return site.name

    outcomes_by_name = {
        o.site_name: o
        for o in run_sites_parallel(
            sites=sites,
            collect_fn=collect_fn,
            timeout_resolver=lambda s: 0.2 if s.name == "slow" else 5.0,
            max_workers=2,
        )
    }
    assert outcomes_by_name["slow"].status == "timeout"
    assert outcomes_by_name["fast"].status == "success"


def test_collect_fn_exception_is_captured_in_outcome() -> None:
    """例外発生時に outcome.status='failure', outcome.error がセットされる。"""
    sites = [FakeSite("err", "https://e.example.jp/")]

    def collect_fn(site: FakeSite, timeout: float) -> str:
        raise RuntimeError("boom")

    outcomes = run_sites_parallel(
        sites=sites,
        collect_fn=collect_fn,
        timeout_resolver=lambda _s: 5.0,
        max_workers=1,
    )
    assert outcomes[0].status == "failure"
    assert isinstance(outcomes[0].error, RuntimeError)
    assert "boom" in str(outcomes[0].error)


def test_on_outcome_callback_is_called_per_site() -> None:
    sites = [FakeSite(f"s{i}", f"https://h{i}.example.jp/") for i in range(3)]
    received: list[SiteRunOutcome] = []

    run_sites_parallel(
        sites=sites,
        collect_fn=lambda _s, _t: "ok",
        timeout_resolver=lambda _s: 5.0,
        max_workers=3,
        on_outcome=received.append,
    )
    assert len(received) == 3
    assert {o.site_name for o in received} == {"s0", "s1", "s2"}


def test_empty_sites_returns_empty_list() -> None:
    outcomes = run_sites_parallel(
        sites=[],
        collect_fn=lambda _s, _t: "ok",
        timeout_resolver=lambda _s: 5.0,
    )
    assert outcomes == []
