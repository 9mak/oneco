"""
Groq API (OpenAI互換) を使った構造化抽出プロバイダー

llama-3.3-70b-versatile 等の無料枠モデルを使用。
"""

import json
import logging
import os
import time
from typing import Any

from .base import ExtractionResult, LlmProvider, MultiExtractionResult

MULTI_ANIMAL_SYSTEM_PROMPT = """あなたは日本の自治体の保護動物PDFから動物情報を抽出する専門家です。
一覧表形式のPDFテキストから、記載されている全ての動物情報を個別に抽出してください。

ルール:
1. 種別（species）: '犬' または '猫' または 'その他' のいずれかを返す
   - ファイル名に 'dog' が含まれていれば全て '犬'、'cat' が含まれていれば全て '猫'
2. 管理番号（management_number）: センター管理番号をそのまま返す（例: 5中-D0524）
3. 性別（sex）: PDFに記載された性別をそのまま返す（オス/メス、去勢済/不妊済等も含める）
4. 年齢（age）: 推定生年月日（例: R5.11.30 → 令和5年11月30日）をISO形式で返す
5. 毛色（color）: PDFに記載された毛色をそのまま返す
6. 体格（size）: 成犬/成猫時の体重や大きさをそのまま返す（例: 約16kg, 15～20㎏）
7. 収容日（shelter_date）: PDFに「掲載日」が記載されている場合はその日付をISO形式で返す
   - 令和表記（R7.3.22 → 2025-03-22）に変換する
   - 令和1年=2019年、令和2年=2020年、令和3年=2021年、令和4年=2022年、令和5年=2023年、令和6年=2024年、令和7年=2025年
8. 場所（location）: センター名や管理番号の「中」「西」「東」「高」等から推定する
9. 電話番号（phone）: 記載があれば返す、なければ空文字
10. 画像URL（image_urls）: PDFには画像URLがないため空リストを返す

記載されている全動物を漏れなく抽出すること。"""

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

logger = logging.getLogger(__name__)

ANIMAL_EXTRACTION_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "extract_animal_data",
        "description": "保護動物の詳細ページから動物情報を構造化抽出する",
        "parameters": {
            "type": "object",
            "properties": {
                "species": {
                    "type": "string",
                    "description": "動物種別。'犬' または '猫' または 'その他'",
                },
                "sex": {"type": "string", "description": "性別"},
                "age": {"type": "string", "description": "年齢"},
                "color": {"type": "string", "description": "毛色"},
                "size": {"type": "string", "description": "体格"},
                "shelter_date": {
                    "type": "string",
                    "description": "収容日（YYYY-MM-DD形式）",
                },
                "location": {"type": "string", "description": "収容場所"},
                "phone": {"type": "string", "description": "電話番号"},
                "image_urls": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "動物写真URLリスト",
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
    },
}

LINK_EXTRACTION_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "extract_detail_links",
        "description": "一覧ページから動物詳細ページへのリンクURLを抽出する",
        "parameters": {
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
    },
}

MULTI_ANIMAL_EXTRACTION_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "extract_multiple_animals",
        "description": "一覧表形式から複数の動物情報をリストで構造化抽出する",
        "parameters": {
            "type": "object",
            "properties": {
                "animals": {
                    "type": "array",
                    "description": "抽出した動物情報のリスト",
                    "items": {
                        "type": "object",
                        "properties": {
                            "species": {"type": "string"},
                            "management_number": {"type": "string"},
                            "sex": {"type": "string"},
                            "age": {"type": "string"},
                            "color": {"type": "string"},
                            "size": {"type": "string"},
                            "shelter_date": {"type": "string"},
                            "location": {"type": "string"},
                            "phone": {"type": "string"},
                            "image_urls": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "features": {"type": "string"},
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
                },
            },
            "required": ["animals"],
        },
    },
}


class GroqProvider(LlmProvider):
    """Groq API (OpenAI互換) を使った構造化抽出の実装"""

    def __init__(
        self,
        model: str = "llama-3.3-70b-versatile",
        api_key: str | None = None,
        max_retries: int = 3,
    ) -> None:
        self.model_name = model
        self.max_retries = max_retries
        self._api_key = api_key or os.environ.get("GROQ_API_KEY")
        self._client = None

    @property
    def client(self):
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(
                api_key=self._api_key,
                base_url="https://api.groq.com/openai/v1",
            )
        return self._client

    def extract_animal_data(
        self,
        html_content: str,
        source_url: str,
        category: str,
    ) -> ExtractionResult:
        prompt = (
            f"以下のHTMLから保護動物の情報を抽出してください。\n"
            f"出典URL: {source_url}\n"
            f"カテゴリ: {category}\n\n"
            f"```html\n{html_content}\n```"
        )
        fields, usage = self._call_with_tool(
            system=EXTRACTION_SYSTEM_PROMPT,
            prompt=prompt,
            tool=ANIMAL_EXTRACTION_TOOL,
            function_name="extract_animal_data",
        )
        return ExtractionResult(
            fields=fields,
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
        )

    def extract_multiple_animals(
        self,
        content: str,
        source_url: str,
        category: str,
        hint_species: str = "",
    ) -> MultiExtractionResult:
        species_hint = (
            f"\nヒント: このPDFに含まれる動物はすべて「{hint_species}」です。"
            if hint_species
            else ""
        )
        prompt = (
            f"以下のPDFテキストから、記載されている全ての動物情報を抽出してください。\n"
            f"出典URL: {source_url}\n"
            f"カテゴリ: {category}{species_hint}\n\n"
            f"{content}"
        )
        args, usage = self._call_with_tool(
            system=MULTI_ANIMAL_SYSTEM_PROMPT,
            prompt=prompt,
            tool=MULTI_ANIMAL_EXTRACTION_TOOL,
            function_name="extract_multiple_animals",
        )
        return MultiExtractionResult(
            animals=args.get("animals", []),
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
        )

    def extract_detail_links(
        self,
        html_content: str,
        base_url: str,
    ) -> list[str]:
        prompt = (
            f"以下の一覧ページHTMLから、動物の詳細ページへのリンクを抽出してください。\n"
            f"ベースURL: {base_url}\n\n"
            f"```html\n{html_content}\n```"
        )
        args, _ = self._call_with_tool(
            system=LINK_EXTRACTION_SYSTEM_PROMPT,
            prompt=prompt,
            tool=LINK_EXTRACTION_TOOL,
            function_name="extract_detail_links",
        )
        return args.get("links", [])

    def _call_with_tool(
        self,
        system: str,
        prompt: str,
        tool: dict[str, Any],
        function_name: str,
    ) -> tuple[dict[str, Any], dict[str, int]]:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ]
        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=messages,
                    tools=[tool],
                    tool_choice={"type": "function", "function": {"name": function_name}},
                )
                tool_calls = response.choices[0].message.tool_calls
                args = json.loads(tool_calls[0].function.arguments) if tool_calls else {}
                usage = {
                    "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                    "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                }
                return args, usage
            except Exception as e:
                last_error = e
                error_str = str(e).lower()
                # tool_use_failed: モデルが function call の JSON を不正に生成する
                # 既知の Groq の非決定的バグ。非決定性のためリトライで成功することが多い。
                is_transient = any(
                    k in error_str
                    for k in ["quota", "rate", "429", "500", "503", "tool_use_failed"]
                )
                if is_transient:
                    if attempt < self.max_retries - 1:
                        wait = 2**attempt
                        logger.warning(
                            f"Groq API呼び出し失敗 (attempt {attempt + 1}/{self.max_retries}): "
                            f"{e}. {wait}秒後にリトライ..."
                        )
                        time.sleep(wait)
                    else:
                        logger.error(f"Groq API呼び出し失敗（最大リトライ到達）: {e}")
                else:
                    raise
        raise last_error  # type: ignore[misc]
