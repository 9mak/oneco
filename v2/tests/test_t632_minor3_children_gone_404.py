"""W006 T632 の小さな直し (3) 全部 404 の判定に、例外の種類を足す。ネットワークなし。"""

from __future__ import annotations

from collector import run as run_mod
from collector.errors import ErrorInfo
from collector.fetch import FetchError


# --- (3) 全部 404 の判定に、例外の種類を足す --------------------------------------------------
def test_all_children_gone_needs_the_error_to_be_a_404():
    trace = ["follow_all → 2 件", "skip https://a/1: HTTP 404: https://a/1", "skip https://a/2: HTTP 404: https://a/2"]
    gone = FetchError("follow_all: 辿った 2 本がすべて取得に失敗（https://a/1: HTTP 404: https://a/1）")
    assert run_mod._all_children_gone(trace, gone) is True
    gone410 = FetchError("x", ErrorInfo("http", status=410))
    assert run_mod._all_children_gone(trace, gone410) is True
    # 同じ trace でも、失敗の本体が 503・接続失敗・別の取得エラーなら「子が全部消えた」ではない
    assert run_mod._all_children_gone(trace, FetchError("HTTP 503: https://a/x", ErrorInfo("http", status=503))) is False
    assert run_mod._all_children_gone(trace, FetchError("接続できない", ErrorInfo("connect"))) is False
    assert run_mod._all_children_gone(trace, FetchError("follow_all: 辿った 2 本がすべて取得に失敗（https://a/1: HTTP 503: https://a/1）")) is False


