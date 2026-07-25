"""zero_count_verifier のユニットテスト

baseline>=1 のサイトが 2 日連続 0 件で検知された直後、baseline の大小に
関係なく毎回「本当に 0 件か」を軽量に(LLM を使わず)再確認する。
- 再取得したら実は非 0 件だった → 一時的な在庫切れ、正常
- 再取得しても 0 件だが、サイト側に明示的な「該当なし」メッセージがある → 正常
- 再取得しても 0 件で、該当メッセージも無い → 壊れている疑いが濃厚、修理候補に残す
"""

from __future__ import annotations

from src.data_collector.infrastructure.zero_count_verifier import verify_zero_count


class _FakeAdapter:
    """fetch_animal_list() / _http_get() のみ差し替え可能な最小 fake"""

    def __init__(
        self,
        urls: list[tuple[str, str]],
        html: str = "",
        raise_on_list: Exception | None = None,
        raise_on_html: Exception | None = None,
    ):
        self._urls = urls
        self._html = html
        self._raise_on_list = raise_on_list
        self._raise_on_html = raise_on_html

    def fetch_animal_list(self):
        if self._raise_on_list:
            raise self._raise_on_list
        return self._urls

    def _http_get(self, url: str) -> str:
        if self._raise_on_html:
            raise self._raise_on_html
        return self._html


class TestVerifyZeroCount:
    def test_recovered_on_refetch_is_not_flagged(self):
        """再取得したら実は件数があった → 一時的な揺らぎ、正常扱い"""
        adapter = _FakeAdapter(urls=[("https://example.com/1", "sheltered")])
        result = verify_zero_count(adapter, list_url="https://example.com/")

        assert result.should_flag is False
        assert "再取得" in result.reason

    def test_explicit_zero_message_is_not_flagged(self):
        """再取得も0件だが、サイト側に明示的な「該当なし」メッセージがある → 正常な0件"""
        adapter = _FakeAdapter(
            urls=[],
            html="<body>現在、保護収容動物情報はありません。</body>",
        )
        result = verify_zero_count(adapter, list_url="https://example.com/")

        assert result.should_flag is False
        assert "メッセージ" in result.reason

    def test_no_message_and_still_zero_is_flagged(self):
        """再取得も0件で、該当なしメッセージも見当たらない → 壊れている疑い、要修理候補"""
        adapter = _FakeAdapter(
            urls=[],
            html="<body><header>サイトメニュー</header></body>",
        )
        result = verify_zero_count(adapter, list_url="https://example.com/")

        assert result.should_flag is True
        assert result.reason

    def test_various_zero_message_phrasings_are_recognized(self):
        phrasings = [
            "該当する動物情報はありません。",
            "対象となる動物はいません。",
            "只今、収容動物はありません。",
            "現在公開できる情報はありません",
        ]
        for html in phrasings:
            adapter = _FakeAdapter(urls=[], html=f"<body>{html}</body>")
            result = verify_zero_count(adapter, list_url="https://example.com/")
            assert result.should_flag is False, f"failed to recognize: {html!r}"

    def test_list_fetch_exception_is_flagged_conservatively(self):
        """再取得で例外 → 安全側に倒して修理候補として残す"""
        adapter = _FakeAdapter(urls=[], raise_on_list=RuntimeError("boom"))
        result = verify_zero_count(adapter, list_url="https://example.com/")

        assert result.should_flag is True

    def test_html_fetch_exception_is_flagged_conservatively(self):
        """0件確定後のHTML再取得で例外 → 安全側に倒して修理候補として残す"""
        adapter = _FakeAdapter(urls=[], html="", raise_on_html=RuntimeError("boom"))
        result = verify_zero_count(adapter, list_url="https://example.com/")

        assert result.should_flag is True
