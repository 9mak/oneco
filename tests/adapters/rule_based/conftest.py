"""rule-based adapter テスト共通フィクスチャ

各サイト adapter テストで使う HTML フィクスチャ読み込み + HTTP モック helper。
"""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURE_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixture_html():
    """HTML フィクスチャを slug 名で読み込むファクトリ

    Usage:
        def test_x(fixture_html):
            html = fixture_html("yokosuka_doubutu__dog")
    """

    def _load(slug: str) -> str:
        path = FIXTURE_DIR / f"{slug}.html"
        if not path.exists():
            raise FileNotFoundError(f"fixture not found: {path}")
        return path.read_text(encoding="utf-8")

    return _load


@pytest.fixture
def assert_raw_animal():
    """RawAnimalData 検証 helper

    Usage:
        def test_x(assert_raw_animal):
            assert_raw_animal(raw, species="犬", sex="オス", ...)
    """

    def _assert(raw, **expected):
        for key, value in expected.items():
            actual = getattr(raw, key, None)
            assert actual == value, f"{key}: expected {value!r}, got {actual!r}"

    return _assert
