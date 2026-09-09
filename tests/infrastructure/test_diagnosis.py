"""diagnosis.py のユニットテスト (T406)

固定 HTML フィクスチャで4パターン:
- 正常サイト (LIST_LINK_SELECTOR が現ページでもヒット)
- list selector が死んだサイト (0 件)
- ラベル (FIELD_SELECTORS/HEADER_FIELDS) が変わったサイト
- HTTP 404
のいずれも、追加 GET は 1 回だけ・例外で落ちないことを検証する。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from src.data_collector.adapters.rule_based.base import FieldSpec
from src.data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from src.data_collector.infrastructure.diagnosis import (
    diagnose_site,
    diagnose_sites,
)
from src.data_collector.llm.config import SiteConfig

_WORKING_HTML = """
<html><body>
<ul>
<li><a class="animal-link" href="/detail/1">1</a></li>
<li><a class="animal-link" href="/detail/2">2</a></li>
</ul>
<table><tr><th>種別</th><th>収容場所</th></tr><tr><td>犬</td><td>県庁</td></tr></table>
</body></html>
"""

_BROKEN_SELECTOR_HTML = """
<html><body>
<ul>
<li><a class="new-card-link" href="/animals/1">1</a></li>
<li><a class="new-card-link" href="/animals/2">2</a></li>
</ul>
</body></html>
"""

_LABEL_CHANGED_HTML = """
<html><body>
<ul>
<li><a class="animal-link" href="/detail/1">1</a></li>
</ul>
<table><tr><th>タイプ</th><th>保護場所</th></tr><tr><td>犬</td><td>県庁</td></tr></table>
</body></html>
"""


def _site(name: str = "テストサイト") -> SiteConfig:
    return SiteConfig(
        name=name,
        prefecture="テスト県",
        prefecture_code="00",
        list_url="https://example.test/animals/",
        category="adoption",
    )


class _WorkingAdapter:
    LIST_LINK_SELECTOR = "a.animal-link"
    FIELD_SELECTORS: dict[str, FieldSpec] = {
        "location": FieldSpec(label="収容場所"),
    }


def _make_response(status_code: int, text: str, url: str = "https://example.test/animals/"):
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status_code
    resp.text = text
    resp.url = url
    resp.encoding = "utf-8"
    resp.apparent_encoding = "utf-8"
    resp.headers = {"Content-Type": "text/html; charset=utf-8"}
    return resp


@pytest.fixture(autouse=True)
def _no_sleep():
    """politeness throttle の実 sleep をテストで待たない"""
    with patch("src.data_collector.infrastructure.diagnosis.get_throttle_for_url") as m:
        throttle = MagicMock()
        m.return_value = throttle
        yield


@pytest.fixture
def _clean_registry():
    """SiteAdapterRegistry はグローバル静的レジストリなので後始末する"""
    yield
    for name in list(SiteAdapterRegistry._registry.keys()):
        if name.startswith("テストサイト"):
            del SiteAdapterRegistry._registry[name]


class TestDiagnoseSiteWorking:
    def test_working_site_selector_ok(self, _clean_registry):
        site = _site("テストサイト-working")
        SiteAdapterRegistry.register(site.name, _WorkingAdapter)  # type: ignore[arg-type]
        with patch("src.data_collector.infrastructure.diagnosis.requests.get") as mock_get:
            mock_get.return_value = _make_response(200, _WORKING_HTML)
            result = diagnose_site(site)
        assert mock_get.call_count == 1
        assert result.http_status == 200
        assert result.fetch_error is None
        list_check = next(c for c in result.checks if c.name.startswith("LIST_LINK"))
        assert list_check.match_count == 2
        assert list_check.ok
        # 正常なので候補ラベル計算は行わない
        assert result.candidate_labels == []


class TestDiagnoseSiteBrokenSelector:
    def test_dead_list_selector_reports_zero_matches_and_candidates(self, _clean_registry):
        site = _site("テストサイト-broken")
        SiteAdapterRegistry.register(site.name, _WorkingAdapter)  # type: ignore[arg-type]
        with patch("src.data_collector.infrastructure.diagnosis.requests.get") as mock_get:
            mock_get.return_value = _make_response(200, _BROKEN_SELECTOR_HTML)
            result = diagnose_site(site)
        list_check = next(c for c in result.checks if c.name.startswith("LIST_LINK"))
        assert list_check.match_count == 0
        assert not list_check.ok
        # 候補リンクパターンに new-card 側の href パターンが挙がる
        assert result.candidate_href_patterns


class TestDiagnoseSiteLabelChanged:
    def test_label_change_detected_in_field_checks(self, _clean_registry):
        site = _site("テストサイト-label")
        SiteAdapterRegistry.register(site.name, _WorkingAdapter)  # type: ignore[arg-type]
        with patch("src.data_collector.infrastructure.diagnosis.requests.get") as mock_get:
            mock_get.return_value = _make_response(200, _LABEL_CHANGED_HTML)
            result = diagnose_site(site)
        field_check = next(c for c in result.checks if c.name == "FIELD_SELECTORS.location")
        assert field_check.match_count == 0
        assert not field_check.ok
        assert "保護場所" in result.candidate_labels


class TestDiagnoseSiteHttpError:
    def test_http_404_is_reported_without_crash(self, _clean_registry):
        site = _site("テストサイト-404")
        with patch("src.data_collector.infrastructure.diagnosis.requests.get") as mock_get:
            resp = _make_response(404, "")
            mock_get.return_value = resp
            result = diagnose_site(site)
        assert result.http_status == 404
        assert result.fetch_error is None
        assert result.checks == []

    def test_network_exception_is_captured_as_fetch_error(self, _clean_registry):
        site = _site("テストサイト-network")
        with patch("src.data_collector.infrastructure.diagnosis.requests.get") as mock_get:
            mock_get.side_effect = requests.exceptions.ConnectionError("boom")
            result = diagnose_site(site)
        assert result.http_status is None
        assert result.fetch_error is not None
        assert "boom" in result.fetch_error


class TestDiagnoseSites:
    def test_dedup_and_max_sites_cap(self, _clean_registry):
        sites_by_name = {f"テストサイト-{i}": _site(f"テストサイト-{i}") for i in range(7)}
        with patch("src.data_collector.infrastructure.diagnosis.requests.get") as mock_get:
            mock_get.return_value = _make_response(200, _WORKING_HTML)
            names = [
                "テストサイト-0",
                "テストサイト-0",
                "テストサイト-1",
                "テストサイト-2",
                "テストサイト-3",
                "テストサイト-4",
                "テストサイト-5",
                "テストサイト-6",
            ]
            results = diagnose_sites(names, sites_by_name, max_sites=5)
        assert len(results) == 5
        assert mock_get.call_count == 5

    def test_unknown_site_name_is_skipped(self):
        results = diagnose_sites(["存在しないサイト"], {})
        assert results == []
