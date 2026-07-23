"""SNS 投稿文生成 (Groq) TDD

design.md 5.3 のプロンプト要件:
- 主観形容詞 NG / 公式情報の要約 / 「詳細・問い合わせは自治体公式へ」必須
- ハッシュタグ #保護犬 or #保護猫 + #里親募集 + #<都道府県>
- 自治体公式 URL 末尾 + utm_source={platform}
- 180 字以内

実装方針:
- Groq client は依存性注入 (テストでは fake)
- LLM 失敗時はテンプレフォールバック (常に投稿文を返せる)
"""

from __future__ import annotations

from datetime import date
from typing import Any
from unittest.mock import MagicMock

import pytest

from data_collector.domain.models import AnimalData
from syndication_service.sns_publisher.text_generator import (
    TextGenerator,
    build_fallback_text,
)


def _animal(**kw: Any) -> AnimalData:
    defaults: dict[str, Any] = {
        "species": "犬",
        "shelter_date": date(2026, 6, 1),
        "location": "高知県須崎市",
        "prefecture": "高知県",
        "source_url": "https://example.jp/animals/123",
        "category": "adoption",
        "sex": "女の子",
        "breed": "柴犬",
        "name": "ハナ",
        "description": "人懐っこい",
        "management_number": "2026-001",
    }
    defaults.update(kw)
    return AnimalData(**defaults)


# ---- Fallback (LLM 不要) ----


class TestFallback:
    def test_fallback_contains_required_elements(self):
        text = build_fallback_text(_animal(), platform="threads")
        # 種別 / 都道府県 / URL / 必須フレーズ / ハッシュタグ
        assert "犬" in text
        assert "高知" in text
        assert "https://example.jp/animals/123" in text or "example.jp" in text
        assert "自治体" in text  # 「自治体公式へ」必須フレーズ
        assert "#保護犬" in text
        assert "#里親募集" in text
        assert "#高知県" in text

    def test_fallback_cat_hashtag(self):
        text = build_fallback_text(_animal(species="猫"), platform="threads")
        assert "#保護猫" in text
        assert "#保護犬" not in text

    def test_fallback_other_species_no_dog_cat_hashtag(self):
        text = build_fallback_text(_animal(species="その他"), platform="threads")
        assert "#保護犬" not in text
        assert "#保護猫" not in text

    def test_fallback_within_180_chars(self):
        text = build_fallback_text(_animal(), platform="threads")
        assert len(text) <= 180

    def test_fallback_utm_source_added(self):
        text = build_fallback_text(_animal(), platform="threads")
        assert "utm_source=threads" in text

    def test_fallback_utm_source_x(self):
        text = build_fallback_text(_animal(), platform="x")
        assert "utm_source=x" in text

    def test_fallback_prefecture_fallback_to_location(self):
        """prefecture=None でも location から都道府県を抜く"""
        text = build_fallback_text(
            _animal(prefecture=None, location="北海道札幌市"), platform="threads"
        )
        assert "#北海道" in text

    def test_fallback_unknown_prefecture_no_pref_hashtag(self):
        text = build_fallback_text(_animal(prefecture=None, location="海外"), platform="threads")
        # 都道府県抽出できなくても落ちず、#里親募集 は必ず出る
        assert "#里親募集" in text

    def test_fallback_no_subjective_adjectives(self):
        """description にあった主観表現 (人懐っこい) を本文に持ち込まない"""
        text = build_fallback_text(_animal(description="人懐っこい"), platform="threads")
        assert "人懐っこい" not in text

    def test_fallback_includes_management_number_when_present(self):
        text = build_fallback_text(_animal(management_number="C-2026-001"), platform="threads")
        assert "C-2026-001" in text or "管理番号" in text

    def test_fallback_without_oneco_url_omits_oneco_link(self):
        """oneco_url 未指定 (id が引けなかった等) では oneco 導線を追加しない"""
        text = build_fallback_text(_animal(), platform="threads")
        assert "oneco" not in text.lower()

    def test_fallback_includes_oneco_url_when_provided(self):
        oneco_url = "https://frontend-psi-ten-73.vercel.app/animals/42?utm_source=threads"
        text = build_fallback_text(_animal(), platform="threads", oneco_url=oneco_url)
        assert oneco_url in text
        # 自治体公式URLも引き続き必須要素として残る
        assert "example.jp/animals/123" in text


# ---- Groq generator ----


class _FakeGroqClient:
    """Groq の OpenAI 互換クライアントを模した最小 fake。"""

    def __init__(self, return_text: str):
        self._return_text = return_text
        self.calls: list[dict[str, Any]] = []

        chat = MagicMock()
        completions = MagicMock()
        completions.create.side_effect = self._create
        chat.completions = completions
        self.chat = chat

    def _create(self, **kw: Any) -> Any:
        self.calls.append(kw)
        return MagicMock(
            choices=[MagicMock(message=MagicMock(content=self._return_text))],
            usage=MagicMock(prompt_tokens=10, completion_tokens=20),
        )


class TestGroqGenerator:
    def test_generate_returns_llm_text(self):
        fake = _FakeGroqClient(return_text="保護犬の柴犬さんが里親募集中 #保護犬 #里親募集")
        gen = TextGenerator(client=fake, model="llama-3.3-70b-versatile")
        text = gen.generate(_animal(), platform="threads")
        assert "保護犬" in text
        assert len(fake.calls) == 1

    def test_generate_prompt_contains_animal_facts(self):
        fake = _FakeGroqClient(return_text="ok")
        gen = TextGenerator(client=fake)
        gen.generate(_animal(species="猫", prefecture="千葉県"), platform="threads")
        call = fake.calls[0]
        msgs = call["messages"]
        prompt = "\n".join(m["content"] for m in msgs)
        assert "猫" in prompt
        assert "千葉県" in prompt
        assert "threads" in prompt.lower() or "Threads" in prompt

    def test_generate_appends_url_if_missing(self):
        """LLM 出力に URL が含まれていなければ末尾に付ける (utm 付き)"""
        fake = _FakeGroqClient(return_text="保護犬の柴犬さん #保護犬 #里親募集")
        gen = TextGenerator(client=fake)
        text = gen.generate(_animal(), platform="threads")
        assert "utm_source=threads" in text

    def test_generate_keeps_url_if_already_present(self):
        """LLM が URL を入れていれば utm を付加するか維持する。重複は作らない。"""
        fake = _FakeGroqClient(
            return_text="柴犬さん #保護犬 #里親募集 https://example.jp/animals/123?utm_source=threads"
        )
        gen = TextGenerator(client=fake)
        text = gen.generate(_animal(), platform="threads")
        # URL は 1 つだけ
        assert text.count("https://example.jp/animals/123") == 1

    def test_generate_falls_back_on_llm_exception(self):
        """LLM 失敗 → フォールバックテンプレ"""
        fake = _FakeGroqClient(return_text="ignored")
        fake.chat.completions.create.side_effect = RuntimeError("upstream 503")
        gen = TextGenerator(client=fake)
        text = gen.generate(_animal(), platform="threads")
        # フォールバックの特徴: 「自治体公式へ」必須フレーズ
        assert "自治体" in text
        assert "#里親募集" in text

    def test_generate_falls_back_on_empty_llm_output(self):
        fake = _FakeGroqClient(return_text="")
        gen = TextGenerator(client=fake)
        text = gen.generate(_animal(), platform="threads")
        assert "自治体" in text

    def test_no_client_uses_fallback(self):
        """client=None なら全件フォールバック (GROQ_API_KEY 未設定環境用)"""
        gen = TextGenerator(client=None)
        text = gen.generate(_animal(), platform="threads")
        assert "#里親募集" in text

    def test_unknown_platform_raises(self):
        gen = TextGenerator(client=None)
        with pytest.raises(ValueError):
            gen.generate(_animal(), platform="myspace")

    def test_generate_appends_oneco_url_to_llm_text(self):
        """LLM 出力に oneco_url が含まれていなくても末尾に付加する"""
        fake = _FakeGroqClient(
            return_text="柴犬さん #保護犬 #里親募集 https://example.jp/animals/123"
        )
        gen = TextGenerator(client=fake)
        oneco_url = "https://frontend-psi-ten-73.vercel.app/animals/42?utm_source=threads"
        text = gen.generate(_animal(), platform="threads", oneco_url=oneco_url)
        assert oneco_url in text

    def test_generate_fallback_on_exception_includes_oneco_url(self):
        fake = _FakeGroqClient(return_text="ignored")
        fake.chat.completions.create.side_effect = RuntimeError("upstream 503")
        gen = TextGenerator(client=fake)
        oneco_url = "https://frontend-psi-ten-73.vercel.app/animals/42?utm_source=threads"
        text = gen.generate(_animal(), platform="threads", oneco_url=oneco_url)
        assert oneco_url in text

    def test_generate_no_oneco_url_by_default(self):
        """oneco_url を渡さなければ従来どおり oneco 導線を追加しない"""
        gen = TextGenerator(client=None)
        text = gen.generate(_animal(), platform="threads")
        assert "vercel.app" not in text
