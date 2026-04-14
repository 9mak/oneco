"""
LLMプロバイダーの統一インターフェース

各LLMプロバイダー（Anthropic, OpenAI, Google等）が実装すべき
抽象インターフェースを定義する。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class ExtractionResult:
    """LLM抽出結果"""

    fields: dict[str, Any]
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class MultiExtractionResult:
    """複数動物LLM抽出結果（PDF一覧表など複数頭が1ページに記載される場合用）"""

    animals: list[dict[str, Any]]
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
    ) -> list[str]:
        """
        HTMLから動物詳細ページへのリンクを推定抽出

        Args:
            html_content: 前処理済みHTML
            base_url: 絶対URL解決用のベースURL

        Returns:
            詳細ページURLのリスト
        """
        ...

    def extract_multiple_animals(
        self,
        content: str,
        source_url: str,
        category: str,
        hint_species: str = "",
    ) -> MultiExtractionResult:
        """
        一覧表形式のコンテンツ（PDF等）から複数動物情報を抽出

        デフォルト実装は extract_animal_data を1回呼ぶだけ（後方互換）。
        複数件抽出に対応するプロバイダーはこのメソッドをオーバーライドする。

        Args:
            content: 抽出対象テキスト（PDF抽出テキスト等）
            source_url: 元ページのURL
            category: カテゴリ ('adoption' or 'lost')
            hint_species: 種別ヒント（'犬' / '猫' / ''）。URLから判明している場合に渡す

        Returns:
            MultiExtractionResult: 複数動物の抽出結果リスト
        """
        result = self.extract_animal_data(content, source_url, category)
        return MultiExtractionResult(
            animals=[result.fields] if result.fields else [],
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
        )
