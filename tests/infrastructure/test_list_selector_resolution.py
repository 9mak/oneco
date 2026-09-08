"""list_selector_resolution のテスト (T141)

scripts/site_count_audit.py (T105) の掲載数比較・scripts/full_publication_audit.py の
count_audit_blind_hosts (T140) が共通で使う「一覧セレクタ解決ロジック」を検証する。
実 adapter を registry から instantiate せずに class 属性だけを読む契約
(HTTP/DB を発生させない) を固定する。
"""

from __future__ import annotations

from typing import ClassVar
from unittest.mock import patch

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry
from data_collector.infrastructure.list_selector_resolution import (
    resolve_list_selector,
    resolve_pagination,
)


class _FakeListLinkAdapter:
    LIST_LINK_SELECTOR: ClassVar[str] = "a.detail-link"
    NEXT_PAGE_SELECTOR: ClassVar[str] = ".paging a[rel='next']"
    MAX_LIST_PAGES: ClassVar[int] = 5

    def __init__(self, *args, **kwargs):
        raise AssertionError("adapter must not be instantiated by selector resolution")


class _FakeRowAdapter:
    ROW_SELECTOR: ClassVar[str] = "table tr"

    def __init__(self, *args, **kwargs):
        raise AssertionError("adapter must not be instantiated by selector resolution")


class _FakeNoSelectorAdapter:
    """LIST_LINK_SELECTOR/ROW_SELECTOR どちらも空 (基底クラス相当)。"""

    def __init__(self, *args, **kwargs):
        raise AssertionError("adapter must not be instantiated by selector resolution")


class TestResolveListSelector:
    def test_registry_list_link_selector_wins(self):
        with patch.object(SiteAdapterRegistry, "get", return_value=_FakeListLinkAdapter):
            selector, source, is_pdf = resolve_list_selector("架空サイト", {})
        assert selector == "a.detail-link"
        assert source == "registry_list_link"
        assert is_pdf is False

    def test_registry_row_selector_is_fallback(self):
        with patch.object(SiteAdapterRegistry, "get", return_value=_FakeRowAdapter):
            selector, source, is_pdf = resolve_list_selector("架空サイト", {})
        assert selector == "table tr"
        assert source == "registry_row"
        assert is_pdf is False

    def test_falls_back_to_sites_yaml_list_link_pattern(self):
        with patch.object(SiteAdapterRegistry, "get", return_value=None):
            selector, source, is_pdf = resolve_list_selector(
                "未登録サイト", {"list_link_pattern": "a[href*='/detail/']"}
            )
        assert selector == "a[href*='/detail/']"
        assert source == "sites_yaml_list_link"
        assert is_pdf is False

    def test_falls_back_to_sites_yaml_pdf_pattern_last(self):
        with patch.object(SiteAdapterRegistry, "get", return_value=None):
            selector, source, is_pdf = resolve_list_selector(
                "PDFサイト", {"pdf_link_pattern": "a[href$='.pdf']"}
            )
        assert selector == "a[href$='.pdf']"
        assert source == "sites_yaml_pdf"
        assert is_pdf is True

    def test_registry_selector_takes_priority_over_sites_yaml(self):
        with patch.object(SiteAdapterRegistry, "get", return_value=_FakeListLinkAdapter):
            selector, source, _is_pdf = resolve_list_selector(
                "架空サイト", {"list_link_pattern": "a.legacy"}
            )
        assert selector == "a.detail-link"
        assert source == "registry_list_link"

    def test_no_selector_resolvable(self):
        with patch.object(SiteAdapterRegistry, "get", return_value=_FakeNoSelectorAdapter):
            selector, source, is_pdf = resolve_list_selector("空セレクタサイト", {})
        assert selector == ""
        assert source == "none"
        assert is_pdf is False

    def test_unregistered_site_without_any_pattern_is_unresolvable(self):
        with patch.object(SiteAdapterRegistry, "get", return_value=None):
            selector, source, _is_pdf = resolve_list_selector("未登録サイト", {})
        assert selector == ""
        assert source == "none"


class TestResolvePagination:
    def test_registered_adapter_with_next_page_selector(self):
        with patch.object(SiteAdapterRegistry, "get", return_value=_FakeListLinkAdapter):
            next_selector, max_pages = resolve_pagination("架空サイト")
        assert next_selector == ".paging a[rel='next']"
        assert max_pages == 5

    def test_registered_adapter_without_next_page_selector(self):
        with patch.object(SiteAdapterRegistry, "get", return_value=_FakeRowAdapter):
            next_selector, max_pages = resolve_pagination("架空サイト")
        assert next_selector == ""
        assert max_pages == 1

    def test_unregistered_site_has_no_pagination(self):
        with patch.object(SiteAdapterRegistry, "get", return_value=None):
            next_selector, max_pages = resolve_pagination("未登録サイト")
        assert next_selector == ""
        assert max_pages == 1
