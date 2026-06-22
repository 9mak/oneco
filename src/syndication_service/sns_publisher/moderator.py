"""投稿前モデレーション (PII 再 grep / status / 文字数 二重防御)

design.md 5.8 の安全網。

- PII: normalizer の伏字を経たうえで「念のため」再 grep。検出時は HARD reject。
  既存 PII regex (DataNormalizer._PII_PHONE_RE / _PII_EMAIL_RE) を再利用するため
  パターン乖離が起きない。
  **スコープの限界**: 電話・メールのみ検査する。住所 (番地等) は対象外。
  adoption の location は normalizer の _coarsen_location が適用されない
  (lost のみ粗粒度化対象) ため、上流 (adapter / normalizer 側) で adoption
  location に PII が無いことが前提。Threads 投稿前にもう一段の住所 PII チェック
  を追加するかは別 issue で検討。
- status: sheltered / None のみ通す。adopted / deceased / returned は拒否
  (新規里親募集のための SNS なので)。
- 文字数: プラットフォーム別に切詰め (Threads 500 / X 280)。
  末尾に URL がある場合は URL を優先保持して本文を削る。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from data_collector.domain.models import AnimalData, AnimalStatus
from data_collector.domain.normalizer import DataNormalizer

# プラットフォーム別文字上限
# Threads: 500 字 (Meta 公式仕様 2026 時点)
# X: 280 字 (Free / Basic tier)
_CHAR_LIMITS: dict[str, int] = {
    "threads": 500,
    "x": 280,
}

# 末尾 URL 検出 (改行前後 / 文末)。 https? のみ対象。
_URL_TAIL_RE = re.compile(r"(https?://\S+)\s*$", re.MULTILINE)


@dataclass(frozen=True)
class ModerationResult:
    """モデレーション結果。

    Attributes:
        ok: 投稿可否
        text: モデレーション後の最終テキスト (ok=False のときも入力をそのまま返す)
        reasons: 拒否理由 (ok=True なら空、ok=False なら 1 件以上)
    """

    ok: bool
    text: str
    reasons: list[str] = field(default_factory=list)


def _contains_pii(text: str) -> list[str]:
    """テキストに PII (電話・メール) が残っていれば理由を返す。空なら ok。"""
    reasons: list[str] = []
    if DataNormalizer._PII_PHONE_RE.search(text):
        reasons.append("pii_phone_detected")
    if DataNormalizer._PII_EMAIL_RE.search(text):
        reasons.append("pii_email_detected")
    return reasons


def _check_status(animal: AnimalData) -> str | None:
    """status が投稿対象外なら理由を返す。投稿可なら None。"""
    if animal.status is None:
        # 旧データ / status カラム未対応サイト。defensive に通す。
        # deceased 混入は collection 側で防御済み (DataNormalizer)。
        return None
    if animal.status == AnimalStatus.SHELTERED:
        return None
    if animal.status == AnimalStatus.DECEASED:
        return "status_deceased"
    if animal.status == AnimalStatus.ADOPTED:
        return "status_adopted"
    if animal.status == AnimalStatus.RETURNED:
        return "status_returned"
    return f"status_unknown:{animal.status}"


def _truncate(text: str, limit: int) -> tuple[str, bool]:
    """文字数上限まで切詰める。末尾 URL があれば URL を保持して本文を削る。

    Returns:
        (truncated_text, was_truncated)
    """
    if len(text) <= limit:
        return text, False

    m = _URL_TAIL_RE.search(text)
    if m:
        url = m.group(1)
        # URL 部 (改行含めた区切りも含む) を除いた本文
        body = text[: m.start()].rstrip()
        # 区切り 1 字 (改行) + URL は必ず残す
        keep_for_url = len(url) + 1
        body_budget = max(0, limit - keep_for_url - 1)  # 末尾「…」分を 1 字確保
        if len(body) > body_budget:
            body = body[:body_budget].rstrip() + "…"
        return f"{body}\n{url}", True

    # URL 無し: 末尾「…」を入れて素朴に切る
    return text[: limit - 1].rstrip() + "…", True


def moderate_post(
    text: str,
    animal: AnimalData,
    *,
    platform: str,
) -> ModerationResult:
    """投稿テキスト + 動物データをモデレーションする。

    Args:
        text: LLM 等で生成された投稿候補
        animal: 投稿対象の動物 (status 確認に使う)
        platform: "threads" or "x"

    Returns:
        ModerationResult (ok / text / reasons)

    Raises:
        ValueError: platform が未知の場合
    """
    if platform not in _CHAR_LIMITS:
        raise ValueError(f"unknown platform: {platform!r}")

    reasons: list[str] = []

    # status: deceased / adopted / returned は HARD reject
    status_reason = _check_status(animal)
    if status_reason is not None:
        reasons.append(status_reason)

    # PII: 残留があれば HARD reject (text/description 両方を念のため確認)
    reasons.extend(_contains_pii(text))
    if animal.description:
        reasons.extend(f"description_{r}" for r in _contains_pii(animal.description))

    if reasons:
        return ModerationResult(ok=False, text=text, reasons=reasons)

    # 文字数: 切詰めて soft-pass (info)
    limit = _CHAR_LIMITS[platform]
    truncated_text, was_truncated = _truncate(text, limit)
    if was_truncated:
        return ModerationResult(ok=True, text=truncated_text, reasons=["truncated"])

    return ModerationResult(ok=True, text=text, reasons=[])
