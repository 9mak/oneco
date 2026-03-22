"""
LLMプロバイダーの統一インターフェース

各LLMプロバイダー（Anthropic, OpenAI, Google等）が実装すべき
抽象インターフェースを定義する。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class ExtractionResult:
    """LLM抽出結果"""

    fields: Dict[str, Any]
    input_tokens: int = 0
    output_tokens: int = 0


class LlmProvider(ABC):
    """LLMプロバイダー抽象基底クラス"""

    @abstractmethod
    def extract_animal_data(
        self,
        html_content: str,
        source_url: str,
        category: str,
    ) -> ExtractionResult:
        """
        HTMLから動物情報を構造化抽出

        Args:
            html_content: 前処理済みHTML
            source_url: 元ページのURL
            category: カテゴリ ('adoption' or 'lost')

        Returns:
            ExtractionResult: 抽出結果（フィールド辞書 + トークン使用量）
        """
        ...

    @abstractmethod
    def extract_detail_links(
        self,
        html_content: str,
        base_url: str,
    ) -> List[str]:
        """
        HTMLから動物詳細ページへのリンクを推定抽出

        Args:
            html_content: 前処理済みHTML
            base_url: 絶対URL解決用のベースURL

        Returns:
            詳細ページURLのリスト
        """
        ...
