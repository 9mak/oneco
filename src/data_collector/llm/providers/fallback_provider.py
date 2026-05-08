"""
フォールバックプロバイダー

プライマリプロバイダーがクォータ超過 / レート制限 / 一時的な API 失敗
（Groq の tool_use_failed 等）を起こした場合、自動的にフォールバック
プロバイダーへ切り替える。

現在の用途: 主に Groq (primary) → Anthropic (fallback)。Groq の
非決定的な tool_use_failed が 3 リトライしても収束しないケースで、
信頼性の高い Anthropic にエスカレートする。
"""

import logging

from .base import ExtractionResult, LlmProvider, MultiExtractionResult

logger = logging.getLogger(__name__)

_FALLBACK_TRIGGERS = (
    "quota",
    "resource_exhausted",
    "429",
    "rate limit",
    "tool_use_failed",
    "500",
    "503",
    "service unavailable",
)


def _should_fallback(e: Exception) -> bool:
    """フォールバック対象のエラーか判定する。

    クォータ超過・レート制限・一時的な API 障害・Groq の tool_use_failed
    のいずれかにマッチすれば True。
    """
    error_str = str(e).lower()
    return any(k in error_str for k in _FALLBACK_TRIGGERS)


class FallbackProvider(LlmProvider):
    """プライマリ → フォールバックの2段階プロバイダー"""

    def __init__(self, primary: LlmProvider, fallback: LlmProvider) -> None:
        self.primary = primary
        self.fallback = fallback

    def _try_with_fallback(self, op_name: str, primary_call, fallback_call):
        try:
            return primary_call()
        except Exception as e:
            if _should_fallback(e):
                logger.warning(
                    f"[{op_name}] プライマリ失敗 → フォールバックに切替: "
                    f"{type(e).__name__}: {str(e)[:200]}"
                )
                return fallback_call()
            raise

    def extract_animal_data(
        self,
        html_content: str,
        source_url: str,
        category: str,
    ) -> ExtractionResult:
        return self._try_with_fallback(
            "extract_animal_data",
            lambda: self.primary.extract_animal_data(html_content, source_url, category),
            lambda: self.fallback.extract_animal_data(html_content, source_url, category),
        )

    def extract_multiple_animals(
        self,
        content: str,
        source_url: str,
        category: str,
        hint_species: str = "",
    ) -> MultiExtractionResult:
        return self._try_with_fallback(
            "extract_multiple_animals",
            lambda: self.primary.extract_multiple_animals(
                content, source_url, category, hint_species
            ),
            lambda: self.fallback.extract_multiple_animals(
                content, source_url, category, hint_species
            ),
        )

    def extract_detail_links(
        self,
        html_content: str,
        base_url: str,
    ) -> list[str]:
        return self._try_with_fallback(
            "extract_detail_links",
            lambda: self.primary.extract_detail_links(html_content, base_url),
            lambda: self.fallback.extract_detail_links(html_content, base_url),
        )
