"""
Google Gemini APIを使った構造化抽出プロバイダー

Function Calling で RawAnimalData スキーマに準拠した構造化データを抽出する。
Google AI Studio の無料APIキーで動作する。
"""

import logging
import os
import time
from typing import List, Optional

from google import genai
from google.genai import types

from .base import ExtractionResult, LlmProvider

logger = logging.getLogger(__name__)

# RawAnimalData の関数定義（Gemini Function Calling 用）
ANIMAL_EXTRACTION_FUNCTION = types.FunctionDeclaration(
    name="extract_animal_data",
    description="保護動物の詳細ページから動物情報を構造化抽出する",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "species": types.Schema(
                type=types.Type.STRING,
                description=(
                    "動物種別。犬か猫かを判定して '犬' または '猫' を返す。"
                    "品種名（雑種等）からも推定する。判定不能な場合は 'その他'"
                ),
            ),
            "sex": types.Schema(
                type=types.Type.STRING,
                description="性別。オス/メス等の表記をそのまま返す",
            ),
            "age": types.Schema(
                type=types.Type.STRING,
                description="年齢。テキスト表記（高齢、成犬、生年月日等）をそのまま返す",
            ),
            "color": types.Schema(
                type=types.Type.STRING,
                description="毛色",
            ),
            "size": types.Schema(
                type=types.Type.STRING,
                description="体格（大型、中型、小型等）。記載がなければ空文字",
            ),
            "shelter_date": types.Schema(
                type=types.Type.STRING,
                description=(
                    "収容日・保護日。ISO 8601形式（YYYY-MM-DD）に変換して返す。"
                    "令和表記や年なし日付も変換する"
                ),
            ),
            "location": types.Schema(
                type=types.Type.STRING,
                description="収容場所・保護場所",
            ),
            "phone": types.Schema(
                type=types.Type.STRING,
                description="連絡先電話番号",
            ),
            "image_urls": types.Schema(
                type=types.Type.ARRAY,
                items=types.Schema(type=types.Type.STRING),
                description=(
                    "動物の写真URLのみ。サイトテンプレート画像"
                    "（ロゴ、アイコン、装飾画像）は除外する"
                ),
            ),
        },
        required=[
            "species", "sex", "age", "color", "size",
            "shelter_date", "location", "phone", "image_urls",
        ],
    ),
)

LINK_EXTRACTION_FUNCTION = types.FunctionDeclaration(
    name="extract_detail_links",
    description="一覧ページから動物詳細ページへのリンクURLを抽出する",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "links": types.Schema(
                type=types.Type.ARRAY,
                items=types.Schema(type=types.Type.STRING),
                description="動物の詳細ページへのURL一覧（絶対URL）",
            ),
        },
        required=["links"],
    ),
)

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
9. 画像URL（image_urls）: 動物の写真のURLのみ。ロゴ、アイコン、装飾画像は除外する

情報がページに存在しない場合は空文字を返してください。"""

LINK_EXTRACTION_SYSTEM_PROMPT = """あなたは日本の自治体の保護動物サイトを分析する専門家です。
一覧ページのHTMLから、個別の動物の詳細ページへのリンクを抽出してください。

ルール:
- 動物の個体詳細ページへのリンクのみを抽出する
- ナビゲーション、ヘッダー、フッターのリンクは除外する
- 「一覧に戻る」「トップへ」等のリンクは除外する
- URLは絶対URLで返す"""


class GoogleProvider(LlmProvider):
    """Google Gemini API を使った構造化抽出の実装"""

    def __init__(
        self,
        model: str = "gemini-2.5-flash",
        api_key: Optional[str] = None,
        max_retries: int = 3,
    ) -> None:
        self.model_name = model
        self.max_retries = max_retries
        self._api_key = api_key or os.environ.get("GOOGLE_API_KEY")
        self._client: Optional[genai.Client] = None  # 遅延初期化

    @property
    def client(self) -> genai.Client:
        """APIクライアントの遅延初期化（API呼び出し時に初めて生成）"""
        if self._client is None:
            self._client = genai.Client(api_key=self._api_key)
        return self._client

    def extract_animal_data(
        self,
        html_content: str,
        source_url: str,
        category: str,
    ) -> ExtractionResult:
        """HTMLから動物情報をFunction Callingで構造化抽出"""
        prompt = (
            f"以下のHTMLから保護動物の情報を抽出してください。\n"
            f"出典URL: {source_url}\n"
            f"カテゴリ: {category}\n\n"
            f"```html\n{html_content}\n```"
        )

        response = self._call_with_retry(
            system=EXTRACTION_SYSTEM_PROMPT,
            prompt=prompt,
            tool=ANIMAL_EXTRACTION_FUNCTION,
            function_name="extract_animal_data",
        )

        fields = self._extract_function_args(response, "extract_animal_data")
        usage = response.usage_metadata

        return ExtractionResult(
            fields=fields,
            input_tokens=getattr(usage, "prompt_token_count", 0),
            output_tokens=getattr(usage, "candidates_token_count", 0),
        )

    def extract_detail_links(
        self,
        html_content: str,
        base_url: str,
    ) -> List[str]:
        """HTMLから動物詳細ページへのリンクをFunction Callingで抽出"""
        prompt = (
            f"以下の一覧ページHTMLから、動物の詳細ページへのリンクを抽出してください。\n"
            f"ベースURL: {base_url}\n\n"
            f"```html\n{html_content}\n```"
        )

        response = self._call_with_retry(
            system=LINK_EXTRACTION_SYSTEM_PROMPT,
            prompt=prompt,
            tool=LINK_EXTRACTION_FUNCTION,
            function_name="extract_detail_links",
        )

        args = self._extract_function_args(response, "extract_detail_links")
        return args.get("links", [])

    def _call_with_retry(
        self,
        system: str,
        prompt: str,
        tool: types.FunctionDeclaration,
        function_name: str,
    ):
        """指数バックオフ付きリトライでAPI呼び出し"""
        config = types.GenerateContentConfig(
            system_instruction=system,
            tools=[types.Tool(function_declarations=[tool])],
            tool_config=types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(
                    mode="ANY",
                    allowed_function_names=[function_name],
                )
            ),
        )

        last_error = None
        for attempt in range(self.max_retries):
            try:
                return self.client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                    config=config,
                )
            except Exception as e:
                last_error = e
                error_str = str(e).lower()
                if any(k in error_str for k in ["quota", "rate", "429", "500", "503"]):
                    if attempt < self.max_retries - 1:
                        wait = self._parse_retry_delay(str(e)) or (2 ** attempt)
                        logger.warning(
                            f"Gemini API呼び出し失敗 (attempt {attempt + 1}/{self.max_retries}): "
                            f"{e}. {wait}秒後にリトライ..."
                        )
                        time.sleep(wait)
                    else:
                        logger.error(f"Gemini API呼び出し失敗（最大リトライ到達）: {e}")
                else:
                    raise

        raise last_error  # type: ignore[misc]

    @staticmethod
    def _parse_retry_delay(error_str: str) -> Optional[float]:
        """APIエラーメッセージから推奨待機秒数を抽出する。
        例: 'Please retry in 47.25s' または retryDelay: '47s'
        """
        import re
        # "retry in 47.25s" / "retry in 47s" 形式
        m = re.search(r"retry[^0-9]*(\d+(?:\.\d+)?)\s*s", error_str, re.IGNORECASE)
        if m:
            return float(m.group(1)) + 1  # 1秒のバッファを追加
        # "retryDelay":"47s" 形式
        m = re.search(r"retryDelay[^0-9]*(\d+(?:\.\d+)?)", error_str, re.IGNORECASE)
        if m:
            return float(m.group(1)) + 1
        return None

    def _extract_function_args(self, response, function_name: str) -> dict:
        """レスポンスからFunction Callの引数を取得"""
        try:
            for part in response.candidates[0].content.parts:
                if (
                    hasattr(part, "function_call")
                    and part.function_call
                    and part.function_call.name == function_name
                ):
                    return dict(part.function_call.args)
        except (AttributeError, IndexError):
            pass
        return {}
