"""投稿前モデレーション (PII / deceased / 文字数) の二重防御テスト

design.md 5.8 の安全網。LLM 出力は信頼せず、必ずこのモデレーションを通す。
- PII (電話・メール) が残っていたら HARD reject
- status=deceased の動物は HARD reject (repository 側で除外済みだが二重防御)
- 文字数オーバーは自動切詰め (Threads 500 / X 280)
"""

from __future__ import annotations

from datetime import date

import pytest

from data_collector.domain.models import AnimalData, AnimalStatus
from syndication_service.sns_publisher.moderator import (
    ModerationResult,
    moderate_post,
)


def _animal(
    *,
    status: AnimalStatus | None = AnimalStatus.SHELTERED,
    description: str | None = None,
) -> AnimalData:
    return AnimalData(
        species="犬",
        shelter_date=date(2026, 6, 1),
        location="高知県",
        source_url="https://example.jp/animals/1",
        category="adoption",
        description=description,
        status=status,
    )


class TestPII:
    def test_clean_text_passes(self):
        result = moderate_post(
            "全国の保護犬を一緒に応援しよう #保護犬",
            _animal(),
            platform="threads",
        )
        assert result.ok is True
        assert result.text == "全国の保護犬を一緒に応援しよう #保護犬"
        assert result.reasons == []

    def test_phone_in_post_text_rejected(self):
        result = moderate_post(
            "問い合わせは 090-1234-5678 まで",
            _animal(),
            platform="threads",
        )
        assert result.ok is False
        assert any("phone" in r.lower() or "pii" in r.lower() for r in result.reasons)

    def test_email_in_post_text_rejected(self):
        result = moderate_post(
            "メールは contact@example.jp に送ってください",
            _animal(),
            platform="threads",
        )
        assert result.ok is False
        assert any("email" in r.lower() or "pii" in r.lower() for r in result.reasons)

    def test_partial_pii_marker_passes(self):
        """既存 normalizer は伏字後に '███' を残す。これは PII ではないので通す。"""
        result = moderate_post(
            "保護されました。連絡先 ███ → 詳細は自治体公式へ",
            _animal(),
            platform="threads",
        )
        assert result.ok is True


class TestDeceased:
    def test_deceased_status_rejected(self):
        result = moderate_post(
            "里親募集中",
            _animal(status=AnimalStatus.DECEASED),
            platform="threads",
        )
        assert result.ok is False
        assert any("deceased" in r.lower() or "死亡" in r for r in result.reasons)

    def test_adopted_status_rejected(self):
        """adopted も投稿対象外 (新規里親募集のための SNS なので)。"""
        result = moderate_post(
            "里親募集中",
            _animal(status=AnimalStatus.ADOPTED),
            platform="threads",
        )
        assert result.ok is False
        assert any("status" in r.lower() or "adopted" in r.lower() for r in result.reasons)

    def test_sheltered_status_passes(self):
        result = moderate_post(
            "里親募集中",
            _animal(status=AnimalStatus.SHELTERED),
            platform="threads",
        )
        assert result.ok is True

    def test_none_status_passes(self):
        """status=None (旧データ・status カラム未対応サイト) は防御的に通す。
        deceased が混入しないことは collection 側で保証 (DataNormalizer)。"""
        result = moderate_post(
            "里親募集中",
            _animal(status=None),
            platform="threads",
        )
        assert result.ok is True


class TestCharLimits:
    def test_under_limit_passes_as_is(self):
        text = "あ" * 100
        result = moderate_post(text, _animal(), platform="threads")
        assert result.ok is True
        assert result.text == text

    def test_threads_500_limit_truncated(self):
        text = "あ" * 501
        result = moderate_post(text, _animal(), platform="threads")
        assert result.ok is True
        assert len(result.text) <= 500
        assert "truncated" in [r.lower() for r in result.reasons] or any(
            "truncat" in r.lower() for r in result.reasons
        )

    def test_x_280_limit_truncated(self):
        text = "あ" * 281
        result = moderate_post(text, _animal(), platform="x")
        assert result.ok is True
        assert len(result.text) <= 280

    def test_truncation_preserves_url_tail(self):
        """末尾に URL がある場合、URL を残して本文側を削る。"""
        body = "あ" * 280
        url = "https://example.jp/a/1"
        text = f"{body}\n{url}"
        result = moderate_post(text, _animal(), platform="x")
        assert result.ok is True
        assert url in result.text
        assert len(result.text) <= 280


class TestUnknownPlatform:
    def test_unknown_platform_raises(self):
        with pytest.raises(ValueError):
            moderate_post("hi", _animal(), platform="myspace")


class TestModerationResult:
    def test_result_is_dataclass_like(self):
        result = moderate_post("ok", _animal(), platform="threads")
        assert isinstance(result, ModerationResult)
        assert hasattr(result, "ok")
        assert hasattr(result, "text")
        assert hasattr(result, "reasons")
