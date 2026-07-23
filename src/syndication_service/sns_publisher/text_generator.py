"""SNS 投稿文生成 (Groq 優先、フォールバックテンプレあり)

design.md 5.3 のプロンプト準拠。LLM 失敗時もテンプレで投稿を継続できるよう
build_fallback_text を独立公開する。

Threads/X 共通テキスト (180 字以内)。プラットフォーム別の文字上限切詰めは
moderator.py が担当 (二重防御)。
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse, urlunparse

from data_collector.domain.models import AnimalData

logger = logging.getLogger(__name__)

# 47 都道府県 (location 文字列からのフォールバック抽出用)
_PREFECTURES: tuple[str, ...] = (
    "北海道",
    "青森県",
    "岩手県",
    "宮城県",
    "秋田県",
    "山形県",
    "福島県",
    "茨城県",
    "栃木県",
    "群馬県",
    "埼玉県",
    "千葉県",
    "東京都",
    "神奈川県",
    "新潟県",
    "富山県",
    "石川県",
    "福井県",
    "山梨県",
    "長野県",
    "岐阜県",
    "静岡県",
    "愛知県",
    "三重県",
    "滋賀県",
    "京都府",
    "大阪府",
    "兵庫県",
    "奈良県",
    "和歌山県",
    "鳥取県",
    "島根県",
    "岡山県",
    "広島県",
    "山口県",
    "徳島県",
    "香川県",
    "愛媛県",
    "高知県",
    "福岡県",
    "佐賀県",
    "長崎県",
    "熊本県",
    "大分県",
    "宮崎県",
    "鹿児島県",
    "沖縄県",
)

_VALID_PLATFORMS: frozenset[str] = frozenset({"threads", "x"})

# Threads/X 共通の安全余裕 (moderator で更に切詰める)
_TARGET_LEN = 180

_SYSTEM_PROMPT = (
    "あなたは保護動物情報サイト oneco の SNS 運用担当です。"
    "公開された動物情報を、客観的・事実中心で簡潔に伝える投稿文を作成してください。"
    "主観的形容詞 (可愛い・優しい等) は使わず、自治体公式情報の要約に徹してください。"
    "投稿文は 180 字以内とし、末尾に「詳細・問い合わせは自治体公式へ」のニュアンスを必ず含めてください。"
)


def _extract_prefecture(animal: AnimalData) -> str | None:
    if animal.prefecture:
        return animal.prefecture
    if animal.location:
        for pref in _PREFECTURES:
            if animal.location.startswith(pref):
                return pref
    return None


def _species_hashtag(species: str) -> str | None:
    if species == "犬":
        return "#保護犬"
    if species == "猫":
        return "#保護猫"
    return None


def _ensure_utm(url: str, platform: str) -> str:
    """既存 URL に utm_source={platform} を付与する。既に同じ値があれば変更しない。"""
    parts = urlparse(url)
    query = parts.query
    if "utm_source=" in query:
        return url
    new_query = f"utm_source={platform}" if not query else f"{query}&utm_source={platform}"
    return urlunparse(parts._replace(query=new_query))


def _append_oneco_url(text: str, oneco_url: str | None) -> str:
    """oneco 側の動物詳細ページへの導線を末尾に足す (未指定なら何もしない)。

    自治体公式リンク・「自治体公式へ」の必須要素はそのまま維持し、
    oneco は追加の発見導線として最後に添えるだけに留める
    (oneco が一次情報源であるかのような誤解を避けるため)。
    """
    if not oneco_url:
        return text
    return f"{text}\n🔍 oneco でも公開中: {oneco_url}"


def build_fallback_text(animal: AnimalData, *, platform: str, oneco_url: str | None = None) -> str:
    """LLM 不要のテンプレ生成。常に出力できる。

    180 字以内 (oneco_url 付与時はこの限りではなく moderator の上限に委ねる)、
    必須要素 (種別/地域/URL/「自治体公式へ」/ハッシュタグ) を含む。
    主観的表現 (description) は持ち込まない。
    """
    if platform not in _VALID_PLATFORMS:
        raise ValueError(f"unknown platform: {platform!r}")

    pref = _extract_prefecture(animal)
    species_tag = _species_hashtag(animal.species)
    url = _ensure_utm(str(animal.source_url), platform)

    parts: list[str] = []
    parts.append(f"{pref or animal.location}で{animal.species}の里親を募集中です。")
    if animal.management_number:
        parts.append(f"管理番号: {animal.management_number}。")
    parts.append("詳細・問い合わせは自治体公式へ。")
    parts.append(url)

    hashtags = ["#里親募集"]
    if species_tag:
        hashtags.insert(0, species_tag)
    if pref:
        hashtags.append(f"#{pref}")
    parts.append(" ".join(hashtags))

    text = "\n".join(parts)

    if len(text) > _TARGET_LEN:
        # 管理番号行から落とす
        text = "\n".join(p for p in parts if not p.startswith("管理番号:"))
    if len(text) > _TARGET_LEN:
        text = text[: _TARGET_LEN - 1].rstrip() + "…"
    return _append_oneco_url(text, oneco_url)


class TextGenerator:
    """Groq (OpenAI 互換) で投稿文を生成する。失敗時はフォールバックテンプレ。"""

    def __init__(
        self,
        *,
        client: Any | None = None,
        model: str = "llama-3.3-70b-versatile",
        timeout: float = 10.0,
    ) -> None:
        self._client = client
        self._model = model
        self._timeout = timeout

    def generate(self, animal: AnimalData, *, platform: str, oneco_url: str | None = None) -> str:
        if platform not in _VALID_PLATFORMS:
            raise ValueError(f"unknown platform: {platform!r}")

        if self._client is None:
            return build_fallback_text(animal, platform=platform, oneco_url=oneco_url)

        try:
            text = self._call_llm(animal, platform=platform)
        except Exception as exc:
            # LLM の up-stream 障害 (network/rate-limit/timeout) は全部 fallback へ
            logger.warning("Groq generation failed (%s); using fallback", exc)
            return build_fallback_text(animal, platform=platform, oneco_url=oneco_url)

        if not text or not text.strip():
            logger.warning("Groq returned empty text; using fallback")
            return build_fallback_text(animal, platform=platform, oneco_url=oneco_url)

        return self._post_process(text.strip(), animal, platform=platform, oneco_url=oneco_url)

    def _call_llm(self, animal: AnimalData, *, platform: str) -> str:
        user_prompt = self._build_user_prompt(animal, platform=platform)
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
            max_tokens=400,
            timeout=self._timeout,
        )
        content = resp.choices[0].message.content
        return content or ""

    def _build_user_prompt(self, animal: AnimalData, *, platform: str) -> str:
        pref = _extract_prefecture(animal) or animal.location or "不明"
        species_tag = _species_hashtag(animal.species) or "#里親募集"
        url = _ensure_utm(str(animal.source_url), platform)
        lines = [
            f"プラットフォーム: {platform}",
            f"種別: {animal.species}",
            f"性別: {animal.sex}",
            f"所在地: {animal.location} (都道府県: {pref})",
        ]
        if animal.breed:
            lines.append(f"品種: {animal.breed}")
        if animal.name:
            lines.append(f"仮名: {animal.name}")
        if animal.management_number:
            lines.append(f"管理番号: {animal.management_number}")
        lines.append(f"自治体公式URL: {url}")
        lines.append("")
        lines.append("制約:")
        lines.append("- 主観的形容詞は使わない")
        lines.append("- 180 字以内")
        lines.append(f"- ハッシュタグ {species_tag} #里親募集 #{pref} を含める")
        lines.append("- 末尾に自治体公式 URL をそのまま貼る (utm_source 付き)")
        lines.append("- 「詳細・問い合わせは自治体公式へ」を含める")
        return "\n".join(lines)

    def _post_process(
        self, text: str, animal: AnimalData, *, platform: str, oneco_url: str | None = None
    ) -> str:
        """LLM 出力に URL/utm が含まれていなければ付加する。重複は作らない。

        oneco_url は LLM が触れていないので、常に (未付加なら) 追加する。
        """
        url = _ensure_utm(str(animal.source_url), platform)
        if str(animal.source_url) not in text and "utm_source=" not in text:
            text = f"{text}\n{url}"
        if oneco_url and oneco_url not in text:
            text = _append_oneco_url(text, oneco_url)
        return text
