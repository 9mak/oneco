"""ContentAnomaly - 収集データの内容不正検知 (欠損ではなく「値はあるが誤り」)

`FieldQualityTracker` / `quality_metrics.compute_missing_rates` は欠損率
(missing rate) のドリフトしか検知できない。値が存在しつつ内容が不正な
ケース(2026-07-24 発見: 山梨県アダプタの breed に体格比較の説明文
「柴犬よりやや大きめ」が混入、高知県アダプタの name に運営告知文
「※譲渡手続き中です」が混入)は欠損率には現れないため別枠で検知する。

ドリフト検知と異なり履歴を必要としないため、毎 run の収集結果に対して
直接チェックできる純関数として実装する。
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from .models import AnimalData

# breed に品種名ではなく体格の比較・補足説明が混入している疑いを示す語。
# 例: 「柴犬よりやや大きめ」「大きめ」「より大きめ」「前後」
# (pref_yamanashi.py の `_SIZE_COMPARISON_KEYWORDS` と同じ考え方の横断チェック)
_BREED_COMPARISON_WORDS = ("より", "くらい", "ぐらい", "程度", "大きめ", "小さめ", "前後")

# name に運営告知(※...)が同一フィールドに混入している疑いを示すマーカー。
# 例: 「せつなちゃん※譲渡手続き中です。」(高知県アダプタで確認)
_NOTICE_MARKER = "※"

_HTML_TAG_RE = re.compile(r"<[a-zA-Z/][^>]*>")
_HTML_ENTITY_RE = re.compile(r"&[a-z]+;|&#\d+;")

# HTML タグ/エンティティ残留チェックの対象フィールド (自由記述・識別情報系)
_TEXT_FIELDS: tuple[str, ...] = ("breed", "name", "color", "description")


@dataclass(frozen=True)
class ContentAnomaly:
    """内容不正の疑いがあるフィールドの検知結果"""

    source_url: str
    field: str
    value: str
    reason: str


def detect_content_anomalies(animals: Iterable[AnimalData]) -> list[ContentAnomaly]:
    """AnimalData 群から既知の内容不正パターンを検知する

    adapter 個別のバグ修正は行わない (検知のみ)。ここで見つかったパターンは
    Discord 通知経由で可視化し、該当 adapter の追加修正を判断する材料とする。
    """
    findings: list[ContentAnomaly] = []
    for animal in animals:
        source_url = str(animal.source_url)

        breed = animal.breed or ""
        if breed and any(w in breed for w in _BREED_COMPARISON_WORDS):
            findings.append(
                ContentAnomaly(
                    source_url=source_url,
                    field="breed",
                    value=breed,
                    reason="品種名ではなく体格比較の説明文が混入している疑い",
                )
            )

        name = animal.name or ""
        if name and _NOTICE_MARKER in name:
            findings.append(
                ContentAnomaly(
                    source_url=source_url,
                    field="name",
                    value=name,
                    reason="仮名に運営告知(※...)が混入している疑い",
                )
            )

        for field in _TEXT_FIELDS:
            value = getattr(animal, field) or ""
            if not value:
                continue
            if _HTML_TAG_RE.search(value):
                findings.append(
                    ContentAnomaly(
                        source_url=source_url,
                        field=field,
                        value=value[:80],
                        reason="HTMLタグの混入疑い",
                    )
                )
            if _HTML_ENTITY_RE.search(value):
                findings.append(
                    ContentAnomaly(
                        source_url=source_url,
                        field=field,
                        value=value[:80],
                        reason="HTMLエンティティの混入疑い",
                    )
                )
    return findings
