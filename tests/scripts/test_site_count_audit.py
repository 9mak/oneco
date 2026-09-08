"""site_count_audit.py の純粋ロジックのテスト (T141)

audit_site() 自体は実 HTTP fetch を伴うため、ここでは
count_pattern_links_paginated (ページ送り追従・循環検知・上限打ち切り) と
group_and_flag (comparable 判定・delta 算出・pagination_truncated の除外) を
BeautifulSoup 断片 / モック response で検証する。

大分・沖縄・徳島の掲載漏れ (T132) はいずれも一覧ページのページ送り未追従が原因で、
セレクタ解決だけでは再現できない (2ページ目以降のリンクを取りこぼす)。
test_follows_pagination_and_counts_all_pages がこの回帰を再現する固定テスト。
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import site_count_audit as sca  # noqa: E402


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


def _response(html: str, status: int = 200) -> MagicMock:
    res = MagicMock()
    res.status_code = status
    res.content = html.encode("utf-8")
    return res


class TestCountPatternLinksPaginated:
    def test_single_page_no_next_selector(self):
        soup = _soup(
            "<html><body>"
            "<a class='d' href='/animals/1'>1</a>"
            "<a class='d' href='/animals/2'>2</a>"
            "</body></html>"
        )
        count, truncated = sca.count_pattern_links_paginated(
            soup, "https://example.jp/list", "a.d", "", 1
        )
        assert count == 2
        assert truncated is False

    def test_follows_pagination_and_counts_all_pages(self):
        """大分・沖縄・徳島 (T132) 型: 1ページ目だけでは2頭しか見えないが2ページ目に
        追加で2頭いる。ページ送りを追従しないと過小カウントになる。"""
        page1 = _soup(
            "<html><body>"
            "<a class='d' href='/animals/1'>1</a>"
            "<a class='d' href='/animals/2'>2</a>"
            "<div class='paging'><a rel='next' href='/list?page=2'>次へ</a></div>"
            "</body></html>"
        )
        page2_html = (
            "<html><body>"
            "<a class='d' href='/animals/3'>3</a>"
            "<a class='d' href='/animals/4'>4</a>"
            "</body></html>"
        )
        with patch.object(sca.requests, "get", return_value=_response(page2_html)) as mock_get:
            count, truncated = sca.count_pattern_links_paginated(
                page1, "https://example.jp/list", "a.d", ".paging a[rel='next']", 5
            )
        assert count == 4
        assert truncated is False
        mock_get.assert_called_once()
        assert mock_get.call_args[0][0] == "https://example.jp/list?page=2"

    def test_cycle_is_truncated(self):
        """next リンクが既訪問ページ (1ページ目) を指す循環は打ち切りとして扱う"""
        page1 = _soup(
            "<html><body>"
            "<a class='d' href='/animals/1'>1</a>"
            "<div class='paging'><a rel='next' href='/list'>次へ</a></div>"
            "</body></html>"
        )
        count, truncated = sca.count_pattern_links_paginated(
            page1, "https://example.jp/list", "a.d", ".paging a[rel='next']", 5
        )
        assert count == 1
        assert truncated is True

    def test_max_pages_cap_is_truncated(self):
        """次ページがまだ残っているのに上限に達したら打ち切りを立てる"""

        def _page_with_next(n: int) -> str:
            return (
                "<html><body>"
                f"<a class='d' href='/animals/{n}'>{n}</a>"
                f"<div class='paging'><a rel='next' href='/list?page={n + 1}'>次へ</a></div>"
                "</body></html>"
            )

        page1 = _soup(_page_with_next(1))
        responses = [_response(_page_with_next(n)) for n in range(2, 6)]
        with patch.object(sca.requests, "get", side_effect=responses):
            count, truncated = sca.count_pattern_links_paginated(
                page1, "https://example.jp/list", "a.d", ".paging a[rel='next']", 3
            )
        assert count == 3  # page 1,2,3 分 (上限 max_pages=3)
        assert truncated is True

    def test_no_next_link_on_page_stops_cleanly(self):
        page1 = _soup("<html><body><a class='d' href='/animals/1'>1</a></body></html>")
        count, truncated = sca.count_pattern_links_paginated(
            page1, "https://example.jp/list", "a.d", ".paging a[rel='next']", 5
        )
        assert count == 1
        assert truncated is False

    def test_http_error_on_next_page_is_truncated(self):
        page1 = _soup(
            "<html><body>"
            "<a class='d' href='/animals/1'>1</a>"
            "<div class='paging'><a rel='next' href='/list?page=2'>次へ</a></div>"
            "</body></html>"
        )
        with patch.object(sca.requests, "get", return_value=_response("", status=500)):
            count, truncated = sca.count_pattern_links_paginated(
                page1, "https://example.jp/list", "a.d", ".paging a[rel='next']", 5
            )
        assert count == 1
        assert truncated is True


class TestGroupAndFlag:
    def _row(self, name, host, pattern_count, pagination_truncated=False, is_pdf=False):
        return {
            "name": name,
            "host": host,
            "status": "ok",
            "selector": "a.d",
            "selector_source": "registry_list_link",
            "is_pdf_selector": is_pdf,
            "pattern_count": pattern_count,
            "pagination_truncated": pagination_truncated,
            "pagination": [],
            "zero_canary": False,
        }

    def test_truncated_site_excluded_from_comparable(self):
        rows = [self._row("A県（犬）", "a.example.jp", 10, pagination_truncated=True)]
        api_animals = [{"source_url": f"https://a.example.jp/{i}"} for i in range(10)]
        groups = sca.group_and_flag(rows, api_animals)
        assert len(groups) == 1
        assert groups[0]["comparable"] is False
        assert "undercount_suspect" not in groups[0]["flags"]
        assert groups[0]["pagination_truncated"] is True

    def test_comparable_host_computes_delta(self):
        rows = [self._row("B県（犬）", "b.example.jp", 12)]
        api_animals = [{"source_url": f"https://b.example.jp/{i}"} for i in range(10)]
        groups = sca.group_and_flag(rows, api_animals)
        assert groups[0]["comparable"] is True
        assert groups[0]["delta"] == 2
        assert "undercount_suspect" in groups[0]["flags"]
