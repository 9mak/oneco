"""zero_count_verifier のユニットテスト

baseline>=1 のサイトが 2 日連続 0 件で検知された直後、baseline の大小に
関係なく毎回「本当に 0 件か」を再確認する。
- 再取得したら実は非 0 件だった → 一時的な在庫切れ、正常
- 再取得しても 0 件だが、サイト側に明示的な「該当なし」メッセージがある → 正常
- どちらでも判定できない残りは LLM 分類 (LISTED/NONE/UNCLEAR) にかけ、
  NONE (ページ上も0件表示) のみ正常扱い、他は安全側で修理候補に残す
"""

from __future__ import annotations

from src.data_collector.infrastructure import zero_count_verifier
from src.data_collector.infrastructure.zero_count_verifier import (
    _compress_for_judge,
    _llm_judge_page_animals,
    verify_zero_count,
)


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
        # 真の0件ではない (今回はたまたま在庫が揺らいだだけ) ので "none" にはしない (T106)
        assert result.verdict == "transient_nonzero"

    def test_explicit_zero_message_is_not_flagged(self):
        """再取得も0件だが、サイト側に明示的な「該当なし」メッセージがある → 正常な0件"""
        adapter = _FakeAdapter(
            urls=[],
            html="<body>現在、保護収容動物情報はありません。</body>",
        )
        result = verify_zero_count(adapter, list_url="https://example.com/")

        assert result.should_flag is False
        assert "メッセージ" in result.reason
        assert result.verdict == "none"

    def test_no_message_and_still_zero_is_flagged(self, monkeypatch):
        """再取得も0件・メッセージ無し・LLM判定も不能 → 壊れている疑い、要修理候補"""
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        adapter = _FakeAdapter(
            urls=[],
            html="<body><header>サイトメニュー</header></body>",
        )
        result = verify_zero_count(adapter, list_url="https://example.com/")

        assert result.should_flag is True
        assert result.reason
        assert result.verdict == "unclear"

    def test_various_zero_message_phrasings_are_recognized(self):
        phrasings = [
            "該当する動物情報はありません。",
            "対象となる動物はいません。",
            "只今、収容動物はありません。",
            "現在公開できる情報はありません",
            # 2026-07-25 実サイトの手動トリアージで発見した「いません」型
            # (既存パターンは「ありません」中心で「いません」の網羅が甘かった)
            "現在、対象となる犬はいません。",  # 千葉市
            "現在、収容（保護）されている猫はいません。",  # 川崎市
            "現在、迷い猫は収容されていません。",  # 広島県
            "現在保護中の動物はいません",  # 佐賀県
        ]
        for html in phrasings:
            adapter = _FakeAdapter(urls=[], html=f"<body>{html}</body>")
            result = verify_zero_count(adapter, list_url="https://example.com/")
            assert result.should_flag is False, f"failed to recognize: {html!r}"
            assert result.verdict == "none", f"failed to recognize: {html!r}"

    def test_list_fetch_exception_is_flagged_conservatively(self):
        """再取得で例外 → 安全側に倒して修理候補として残す"""
        adapter = _FakeAdapter(urls=[], raise_on_list=RuntimeError("boom"))
        result = verify_zero_count(adapter, list_url="https://example.com/")

        assert result.should_flag is True
        assert result.verdict == "unclear"

    def test_html_fetch_exception_is_flagged_conservatively(self):
        """0件確定後のHTML再取得で例外 → 安全側に倒して修理候補として残す"""
        adapter = _FakeAdapter(urls=[], html="", raise_on_html=RuntimeError("boom"))
        result = verify_zero_count(adapter, list_url="https://example.com/")

        assert result.should_flag is True
        assert result.verdict == "unclear"


class TestLlmJudgeIntegration:
    """パターンで判定できなかった残りに対する LLM 分類の組み込み。

    2026-07-25 の手動トリアージで、文言パターンでは表現のバリエーション
    (「いません」型、空テンプレート型) を追い切れないことが判明。表層の
    文言ではなく「ページに動物が掲載されているか」を直接 LLM に分類させる。
    """

    _NO_PATTERN_HTML = "<body><div>本文にパターン該当なし</div></body>"

    def test_llm_listed_flags_as_broken(self, monkeypatch):
        """LLM が LISTED (実ページに動物掲載あり) → adapter 0件と矛盾 = 破損濃厚"""
        monkeypatch.setattr(zero_count_verifier, "_llm_judge_page_animals", lambda html: "listed")
        adapter = _FakeAdapter(urls=[], html=self._NO_PATTERN_HTML)
        result = verify_zero_count(adapter, list_url="https://example.com/")

        assert result.should_flag is True
        assert "掲載" in result.reason
        assert result.verdict == "listed"

    def test_llm_none_unflags(self, monkeypatch):
        """LLM が NONE (ページ上も0件表示) → 正常な0件として除外"""
        monkeypatch.setattr(zero_count_verifier, "_llm_judge_page_animals", lambda html: "none")
        adapter = _FakeAdapter(urls=[], html=self._NO_PATTERN_HTML)
        result = verify_zero_count(adapter, list_url="https://example.com/")

        assert result.should_flag is False
        assert result.verdict == "none"

    def test_llm_unclear_keeps_flag(self, monkeypatch):
        """LLM が UNCLEAR (判断不能、JS必須ページ等) → 安全側で候補に残す"""
        monkeypatch.setattr(zero_count_verifier, "_llm_judge_page_animals", lambda html: "unclear")
        adapter = _FakeAdapter(urls=[], html=self._NO_PATTERN_HTML)
        result = verify_zero_count(adapter, list_url="https://example.com/")

        assert result.should_flag is True
        assert result.verdict == "unclear"


class TestLlmJudgePageAnimals:
    # _JUDGE_MIN_TEXT_CHARS (200字) を超える判定可能な本文
    _JUDGABLE_HTML = "<body><div>" + ("保護動物の情報ページです。" * 30) + "</div></body>"

    def test_no_api_key_returns_unclear(self, monkeypatch):
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        assert _llm_judge_page_animals(self._JUDGABLE_HTML) == "unclear"

    def test_too_short_body_returns_unclear_without_llm_call(self, monkeypatch):
        """本文がほぼ無い (JSレンダリング必須・別ページ収集構成等) → LLM を
        呼ばず unclear。静的 HTML に動物が載らない構成のサイト (実測: 高知県は
        本文 26 字) で「0件だ」と誤断定して正常扱いしてしまう事故を防ぐ。"""
        monkeypatch.setenv("GROQ_API_KEY", "test-key")

        import openai

        class ExplodingClient:
            def __init__(self, **_kw):
                raise AssertionError("LLM should not be called for short bodies")

        monkeypatch.setattr(openai, "OpenAI", ExplodingClient)
        assert _llm_judge_page_animals("<body>短い</body>") == "unclear"

    def test_parses_listed_response(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "test-key")
        self._patch_fake_client(monkeypatch, "LISTED")
        assert _llm_judge_page_animals(self._JUDGABLE_HTML) == "listed"

    def test_parses_none_response(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "test-key")
        self._patch_fake_client(monkeypatch, "NONE")
        assert _llm_judge_page_animals(self._JUDGABLE_HTML) == "none"

    def test_garbage_response_returns_unclear(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "test-key")
        self._patch_fake_client(monkeypatch, "わかりません")
        assert _llm_judge_page_animals(self._JUDGABLE_HTML) == "unclear"

    def test_api_exception_returns_unclear(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "test-key")

        import openai

        class FakeClient:
            def __init__(self, **_kw):
                raise RuntimeError("api down")

        monkeypatch.setattr(openai, "OpenAI", FakeClient)
        assert _llm_judge_page_animals(self._JUDGABLE_HTML) == "unclear"

    def test_reasoning_truncated_empty_response_returns_unclear(self, monkeypatch):
        """2026-08-27 reviewer 指摘 (PR #294 F-02): openai/gpt-oss-120b は
        reasoning モデルで、reasoning_effort 未指定 (既定 "medium") だと
        max_tokens=10 では reasoning トークンだけで使い切り content が常に
        空になる (実測: reasoning_tokens=8/10, content="")。この切り詰め
        ケースをモックし、(1) 安全側の unclear に丸まること
        (2) 再発防止のため reasoning_effort="low" が実際に送られていること
        の両方を確認する。"""
        monkeypatch.setenv("GROQ_API_KEY", "test-key")

        import openai

        captured_kwargs: dict = {}

        def fake_create(**kwargs):
            captured_kwargs.update(kwargs)
            msg = type("M", (), {"content": ""})()  # reasoning 切り詰めで空文字
            return type("Resp", (), {"choices": [type("C", (), {"message": msg})()]})()

        class FakeClient:
            def __init__(self, **_kw):
                self.chat = type(
                    "Chat",
                    (),
                    {"completions": type("Comp", (), {"create": staticmethod(fake_create)})()},
                )()

        monkeypatch.setattr(openai, "OpenAI", FakeClient)
        assert _llm_judge_page_animals(self._JUDGABLE_HTML) == "unclear"
        assert captured_kwargs.get("reasoning_effort") == "low"
        # reasoning + completion (1語の分類結果) 両方に足りるだけの余裕を持たせてあること
        assert captured_kwargs.get("max_tokens", 0) >= 100

    @staticmethod
    def _patch_fake_client(monkeypatch, response_text: str) -> None:
        import openai

        def fake_create(**_kwargs):
            msg = type("M", (), {"content": response_text})()
            return type("Resp", (), {"choices": [type("C", (), {"message": msg})()]})()

        class FakeClient:
            def __init__(self, **_kw):
                self.chat = type(
                    "Chat",
                    (),
                    {"completions": type("Comp", (), {"create": staticmethod(fake_create)})()},
                )()

        monkeypatch.setattr(openai, "OpenAI", FakeClient)


class TestCompressForJudgeEmptyTable:
    """ヘッダー行+全セル空データ行のみの表 (在庫0件のプレースホルダ) は、
    テキスト化するとヘッダーの項目名だけが動物データのように見えてしまい
    LLM が LISTED と誤判定する (2026-07-27 実サイト調査: 鳥取県で、中部/西部
    収容動物表のヘッダー行「収容日時 収容場所 種類 品種 毛色...」だけが
    テキストに残り、値セルが全て空なのに LLM が『品種・毛色等の項目がある
    = 動物が掲載されている』と誤認した)。ヘッダー行以外に実データを持たない
    表はテキスト抽出前に除去する。"""

    _EMPTY_TABLE_HTML = """
    <body>
    <h2 class="Title">中部総合事務所収容動物</h2>
    <div class="Contents">
    <table><tbody>
    <tr><th>収容日時</th><th>収容場所</th><th>種類</th><th>品種</th><th>毛色</th></tr>
    <tr><td></td><td></td><td></td><td></td><td></td></tr>
    </tbody></table>
    </div>
    </body>
    """

    def test_header_only_empty_data_table_is_stripped(self):
        compressed = _compress_for_judge(self._EMPTY_TABLE_HTML)
        assert "品種" not in compressed
        assert "毛色" not in compressed

    def test_table_with_actual_data_row_is_kept(self):
        html = """
        <body>
        <table><tbody>
        <tr><th>収容日時</th><th>品種</th></tr>
        <tr><td>令和8年7月20日</td><td>柴犬</td></tr>
        </tbody></table>
        </body>
        """
        compressed = _compress_for_judge(html)
        assert "柴犬" in compressed


class TestLlmJudgePageAnimalsTottoriRegression:
    """鳥取県の実サイト構造 (中部/西部それぞれヘッダー行+空データ行のみの
    表が2つ並ぶ) を模した回帰テスト。空表除去前は LLM が LISTED と誤判定
    していた (2026-07-27 発見)。"""

    _TOTTORI_LIKE_HTML = (
        "<body><div>"
        + "迷い犬猫収容情報。鳥取県内の保健所で収容した犬・猫等の情報を掲載しています。" * 5
        + "</div>"
        + '<h2 class="Title">中部総合事務所収容動物</h2>'
        "<table><tbody>"
        "<tr><th>収容日時</th><th>収容場所</th><th>種類</th><th>品種</th>"
        "<th>毛色</th><th>性別</th><th>推定年齢</th><th>体格、その他特徴</th></tr>"
        "<tr><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td></tr>"
        "</tbody></table>"
        '<h2 class="Title">西部総合事務所収容動物</h2>'
        "<table><tbody>"
        "<tr><td>収容日時</td><td>収容場所</td><td>種類</td><td>品種</td>"
        "<td>毛色</td><td>性別</td><td>推定年齢</td><td>体格、その他特徴</td></tr>"
        "<tr><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td></tr>"
        "</tbody></table>"
        "</body>"
    )

    def test_empty_placeholder_tables_do_not_trigger_llm_call(self, monkeypatch):
        """空テーブル除去後は本文が短くなり、_JUDGE_MIN_TEXT_CHARS 未満で
        unclear に倒れるか、あるいは LLM を呼んでも項目名の羅列が消えて
        いるため listed とは誤判定されないことを確認する。"""
        monkeypatch.setenv("GROQ_API_KEY", "test-key")

        import openai

        def fake_create(**_kwargs):
            # 空表除去後に LLM へ渡ればヘッダー項目名は残っていないはず
            msg = type("M", (), {"content": "NONE"})()
            return type("Resp", (), {"choices": [type("C", (), {"message": msg})()]})()

        class FakeClient:
            def __init__(self, **_kw):
                self.chat = type(
                    "Chat",
                    (),
                    {"completions": type("Comp", (), {"create": staticmethod(fake_create)})()},
                )()

        monkeypatch.setattr(openai, "OpenAI", FakeClient)
        result = _llm_judge_page_animals(self._TOTTORI_LIKE_HTML)
        assert result in ("none", "unclear")
