"""content_anomaly の純関数テスト

FieldQualityTracker は欠損率(missing rate)のドリフトしか検知できず、
「値はあるが内容が不正」なケース(2026-07-24 発見: 山梨県 breed に体格比較
説明文が混入、高知県 name に運営告知文が混入)を検知できなかった。
本テストはその内容不正パターンを恒久的に検知できることを保証する。
"""

from __future__ import annotations

from datetime import date

from src.data_collector.domain.content_anomaly import (
    ContentAnomaly,
    detect_content_anomalies,
)
from src.data_collector.domain.models import AnimalData


def _make(
    *,
    breed: str | None = None,
    name: str | None = None,
    color: str | None = None,
    description: str | None = None,
    source_url: str = "https://example.lg.jp/animals/detail/1",
) -> AnimalData:
    return AnimalData(
        species="犬",
        shelter_date=date(2026, 5, 1),
        location="高知県",
        sex="男の子",
        breed=breed,
        name=name,
        color=color,
        description=description,
        image_urls=["https://example.lg.jp/img/1.jpg"],
        source_url=source_url,
        category="adoption",
    )


def test_no_anomalies_for_clean_data():
    """正常なデータは検知されない"""
    animals = [_make(breed="柴犬", name="ポチ", color="茶")]
    assert detect_content_anomalies(animals) == []


def test_detects_breed_with_comparison_word():
    """breed に体格比較の説明文が混入している疑いを検知する (山梨県 id=1949 相当)"""
    animals = [_make(breed="柴犬よりやや大きめ", source_url="https://pref.example/dog/1")]
    findings = detect_content_anomalies(animals)
    assert len(findings) == 1
    assert findings[0] == ContentAnomaly(
        source_url="https://pref.example/dog/1",
        field="breed",
        value="柴犬よりやや大きめ",
        reason="品種名ではなく体格比較の説明文が混入している疑い",
    )


def test_detects_name_with_notice_marker():
    """name に運営告知(※...)が混入している疑いを検知する (高知県相当)"""
    animals = [
        _make(
            name="せつなちゃん※譲渡手続き中です。",
            source_url="https://kochi-apc.com/center-data/1",
        )
    ]
    findings = detect_content_anomalies(animals)
    assert len(findings) == 1
    assert findings[0].field == "name"
    assert findings[0].reason == "仮名に運営告知(※...)が混入している疑い"


def test_detects_html_tag_leak_in_text_fields():
    """breed/name/color/description に HTML タグが残留している疑いを検知する"""
    animals = [_make(description="人懐っこい性格<br>です")]
    findings = detect_content_anomalies(animals)
    assert any(f.field == "description" and "HTMLタグ" in f.reason for f in findings)


def test_detects_html_entity_leak_in_text_fields():
    """breed/name/color/description に HTML エンティティが残留している疑いを検知する"""
    animals = [_make(color="白&amp;茶")]
    findings = detect_content_anomalies(animals)
    assert any(f.field == "color" and "HTMLエンティティ" in f.reason for f in findings)


def test_none_fields_are_skipped():
    """breed/name/color/description が None のときは何も検知しない"""
    animals = [_make()]
    assert detect_content_anomalies(animals) == []


def test_multiple_animals_aggregate_findings():
    """複数動物にまたがる検知結果を全て集約する"""
    animals = [
        _make(breed="柴犬よりやや大きめ", source_url="https://a.example/1"),
        _make(name="ポチ※収容中です", source_url="https://a.example/2"),
        _make(breed="柴犬", name="タマ", source_url="https://a.example/3"),
    ]
    findings = detect_content_anomalies(animals)
    assert len(findings) == 2
    assert {f.source_url for f in findings} == {"https://a.example/1", "https://a.example/2"}
