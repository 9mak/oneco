"""
フォールバックプロバイダー

プライマリプロバイダーがクォータ超過した場合、自動的にフォールバックプロバイダーへ切り替える。
"""

import logging

from .base import ExtractionResult, LlmProvider, MultiExtractionResult

logger = logging.getLogger(__name__)


def _is_quota_error(e: Exception) -> bool:
    error_str = str(e).lower()
    return any(k in error_str for k in ["quota", "resource_exhausted", "429", "rate limit"])


class FallbackProvider(LlmProvider):
    """プライマリ → フォールバックの2段階プロバイダー"""

    def __init__(self, primary: LlmProvider, fallback: LlmProvider) -> None:
        self.primary = primary
        self.fallback = fallback

    def extract_animal_data(
        self,
        html_content: str,
        source_url: str,
        category: str,
    ) -> ExtractionResult:
        try:
            return self.primary.extract_animal_data(html_content, source_url, category)
        except Exception as e:
            if _is_quota_error(e):
                logger.warning(
                    f"プライマリプロバイダーのクォータ超過、Groqにフォールバック: {type(e).__name__}"
                )
                return self.fallback.extract_animal_data(html_content, source_url, category)
            raise

    def extract_multiple_animals(
        self,
        content: str,
        source_url: str,
        category: str,
        hint_species: str = "",
    ) -> MultiExtractionResult:
        try:
            return self.primary.extract_multiple_animals(
                content, source_url, category, hint_species
            )
        except Exception as e:
            if _is_quota_error(e):
                logger.warning(
                    f"プライマリプロバイダーのクォータ超過、Groqにフォールバック: {type(e).__name__}"
                )
                return self.fallback.extract_multiple_animals(
                    content, source_url, category, hint_species
                )
            raise

    def extract_detail_links(
        self,
        html_content: str,
        base_url: str,
    ) -> list[str]:
        try:
            return self.primary.extract_detail_links(html_content, base_url)
        except Exception as e:
            if _is_quota_error(e):
                logger.warning(
                    f"プライマリプロバイダーのクォータ超過、Groqにフォールバック: {type(e).__name__}"
                )
                return self.fallback.extract_detail_links(html_content, base_url)
            raise
