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
from .google_provider import (
    EXTRACTION_SYSTEM_PROMPT,
    LINK_EXTRACTION_SYSTEM_PROMPT,
    MULTI_ANIMAL_SYSTEM_PROMPT,
)

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
                if any(k in error_str for k in ["quota", "rate", "429", "500", "503"]):
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
