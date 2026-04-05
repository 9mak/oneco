"""
Anthropic Claude APIを使った構造化抽出プロバイダー

tool_use + strict mode で RawAnimalData スキーマに準拠した構造化データを抽出する。
"""

import logging
import os
import time

import anthropic

from .base import ExtractionResult, LlmProvider

logger = logging.getLogger(__name__)

# RawAnimalData の JSON Schema（tool_use 用）
ANIMAL_EXTRACTION_TOOL = {
    "name": "extract_animal_data",
    "description": "保護動物の詳細ページから動物情報を構造化抽出する",
    "input_schema": {
        "type": "object",
        "properties": {
            "species": {
                "type": "string",
                "description": (
                    "動物種別。犬か猫かを判定して '犬' または '猫' を返す。"
                    "品種名（雑種等）からも推定する。判定不能な場合は 'その他'"
                ),
            },
            "sex": {
                "type": "string",
                "description": "性別。オス/メス等の表記をそのまま返す",
            },
            "age": {
                "type": "string",
                "description": ("年齢。テキスト表記（高齢、成犬、生年月日等）をそのまま返す"),
            },
            "color": {
                "type": "string",
                "description": "毛色",
            },
            "size": {
                "type": "string",
                "description": "体格（大型、中型、小型等）",
            },
            "shelter_date": {
                "type": "string",
                "description": (
                    "収容日・保護日。ISO 8601形式（YYYY-MM-DD）に変換して返す。"
                    "令和表記や年なし日付も変換する"
                ),
            },
            "location": {
                "type": "string",
                "description": "収容場所・保護場所",
            },
            "phone": {
                "type": "string",
                "description": "連絡先電話番号",
            },
            "image_urls": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "動物の写真URLのみ。サイトテンプレート画像"
                    "（ロゴ、アイコン、装飾画像）は除外する"
                ),
            },
        },
        "required": [
            "species",
            "sex",
            "age",
            "color",
            "size",
            "shelter_date",
            "location",
            "phone",
            "image_urls",
        ],
    },
}

LINK_EXTRACTION_TOOL = {
    "name": "extract_detail_links",
    "description": "一覧ページから動物詳細ページへのリンクURLを抽出する",
    "input_schema": {
        "type": "object",
        "properties": {
            "links": {
                "type": "array",
                "items": {"type": "string"},
                "description": "動物の詳細ページへのURL一覧（絶対URL）",
            },
        },
        "required": ["links"],
    },
}

EXTRACTION_SYSTEM_PROMPT = """あなたは日本の自治体の保護動物サイトから動物情報を抽出する専門家です。
HTMLから以下のルールに従って正確に情報を抽出してください:

1. 種別（species）: 犬か猫かを判定。品種名（「雑種」「チワワ」「ミックス」等）から推定する。判定不能なら「その他」
2. 性別（sex）: ページに記載されたまま返す（オス、メス、不明等）
3. 年齢（age）: ページに記載されたまま返す（「高齢」「成犬」「約2歳」「生年月日：R1.5/19」等）
4. 毛色（color）: ページに記載されたまま返す
5. 体格（size）: ページに記載されたまま返す（大型、中型、小型等）。記載がなければ空文字
6. 収容日（shelter_date）: ISO 8601形式（YYYY-MM-DD）に変換。令和/平成表記も変換する
7. 収容場所（location）: 記載された場所名をそのまま返す
8. 電話番号（phone）: 記載された電話番号をそのまま返す
9. 画像URL（image_urls）: 動物の写真のURLのみ。サイトのロゴ、アイコン、装飾画像、バナーは除外する

情報がページに存在しない場合は空文字を返してください。"""

LINK_EXTRACTION_SYSTEM_PROMPT = """あなたは日本の自治体の保護動物サイトを分析する専門家です。
一覧ページのHTMLから、個別の動物の詳細ページへのリンクを抽出してください。

ルール:
- 動物の個体詳細ページへのリンクのみを抽出する
- サイトのナビゲーション、ヘッダー、フッターのリンクは除外する
- 「一覧に戻る」「トップへ」等のリンクは除外する
- URLは絶対URLで返す"""


class AnthropicProvider(LlmProvider):
    """Anthropic Claude API を使った構造化抽出の実装"""

    def __init__(
        self,
        model: str = "claude-haiku-4-5-20251001",
        api_key: str | None = None,
        max_retries: int = 3,
    ) -> None:
        self.model = model
        self.max_retries = max_retries
        self.client = anthropic.Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))

    def extract_animal_data(
        self,
        html_content: str,
        source_url: str,
        category: str,
    ) -> ExtractionResult:
        """HTMLから動物情報をtool_useで構造化抽出"""
        user_message = (
            f"以下のHTMLから保護動物の情報を抽出してください。\n"
            f"出典URL: {source_url}\n"
            f"カテゴリ: {category}\n\n"
            f"```html\n{html_content}\n```"
        )

        response = self._call_with_retry(
            system=EXTRACTION_SYSTEM_PROMPT,
            user_message=user_message,
            tools=[ANIMAL_EXTRACTION_TOOL],
            tool_choice={"type": "tool", "name": "extract_animal_data"},
        )

        # tool_use ブロックからフィールドを取得
        fields = {}
        for block in response.content:
            if block.type == "tool_use":
                fields = block.input
                break

        return ExtractionResult(
            fields=fields,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )

    def extract_detail_links(
        self,
        html_content: str,
        base_url: str,
    ) -> list[str]:
        """HTMLから動物詳細ページへのリンクをLLMで推定抽出"""
        user_message = (
            f"以下の一覧ページHTMLから、動物の詳細ページへのリンクを抽出してください。\n"
            f"ベースURL: {base_url}\n\n"
            f"```html\n{html_content}\n```"
        )

        response = self._call_with_retry(
            system=LINK_EXTRACTION_SYSTEM_PROMPT,
            user_message=user_message,
            tools=[LINK_EXTRACTION_TOOL],
            tool_choice={"type": "tool", "name": "extract_detail_links"},
        )

        for block in response.content:
            if block.type == "tool_use":
                return block.input.get("links", [])

        return []

    def _call_with_retry(
        self,
        system: str,
        user_message: str,
        tools: list,
        tool_choice: dict,
    ) -> anthropic.types.Message:
        """指数バックオフ付きリトライでAPI呼び出し"""
        last_error = None

        for attempt in range(self.max_retries):
            try:
                return self.client.messages.create(
                    model=self.model,
                    max_tokens=4096,
                    system=system,
                    messages=[{"role": "user", "content": user_message}],
                    tools=tools,
                    tool_choice=tool_choice,
                )
            except (
                anthropic.RateLimitError,
                anthropic.APIStatusError,
            ) as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    wait = 2**attempt  # 1s, 2s, 4s
                    logger.warning(
                        f"API呼び出し失敗 (attempt {attempt + 1}/{self.max_retries}): "
                        f"{e}. {wait}秒後にリトライ..."
                    )
                    time.sleep(wait)
                else:
                    logger.error(f"API呼び出し失敗 (最大リトライ回数到達): {e}")

        raise last_error  # type: ignore[misc]
