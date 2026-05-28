"""フィールド欠損率の計算 (自己修復ループの検知層)

各サイト×フィールドについて「missing」を統一基準で判定し、欠損率を
集計するための純関数群。`FieldQualityTracker` と `_send_run_summary_alert`
から利用され、前回比 +閾値 以上の急増を adapter 破損のシグナルとする。

判定基準は `DataNormalizer` の挙動に揃える:
- location/sex は欠損時に "不明" が入る (str required) → "不明" を欠損扱い
- age_months/size/color/phone は None が許容 → None を欠損扱い
- image_urls は空リストを欠損扱い
"""

from __future__ import annotations

from collections.abc import Iterable

from .models import AnimalData

# 自己修復の検知対象フィールド。これらの欠損率が前回比 +20% 以上急増
# すると adapter のラベル/セレクタ不一致を疑うシグナルとして扱う。
MONITORED_FIELDS: tuple[str, ...] = (
    "location",
    "age_months",
    "size",
    "sex",
    "phone",
    "image_urls",
)

# 「不明扱い」とみなす文字列 (DataNormalizer の location="不明"/sex="不明"
# フォールバック、および adapter が "-" "なし" 等を入れるケースに対応)
_UNKNOWN_STRINGS: tuple[str, ...] = ("", "不明", "-", "－", "なし", "?", "？")


def is_missing(animal: AnimalData, field: str) -> bool:
    """指定フィールドが欠損しているかを返す。

    None / "不明" 等のプレースホルダ文字列 / 空リスト を欠損とみなす。
    """
    v = getattr(animal, field, None)
    if v is None:
        return True
    if isinstance(v, str):
        return v.strip() in _UNKNOWN_STRINGS
    if isinstance(v, list):
        return len(v) == 0
    return False


def compute_missing_rates(
    animals: list[AnimalData],
    fields: Iterable[str] = MONITORED_FIELDS,
) -> dict[str, float]:
    """各フィールドの欠損率 (0.0-1.0) を返す。animals 空なら全 0.0。"""
    fields_tuple = tuple(fields)
    if not animals:
        return dict.fromkeys(fields_tuple, 0.0)
    n = len(animals)
    return {f: sum(1 for a in animals if is_missing(a, f)) / n for f in fields_tuple}


def group_animals_by_site(
    animals: list[AnimalData],
    site_list_urls: dict[str, str],
) -> dict[str, list[AnimalData]]:
    """`source_url` が site の `list_url` の prefix と一致する動物をグルーピング。

    どの site にも一致しなかった動物は結果に含めず、また 1 件も該当しない
    site は結果のキーから除外する (空配列は返さない)。
    """
    if not animals or not site_list_urls:
        return {}
    groups: dict[str, list[AnimalData]] = {name: [] for name in site_list_urls}
    for a in animals:
        src = str(a.source_url)
        for name, list_url in site_list_urls.items():
            if src.startswith(list_url):
                groups[name].append(a)
                break
    return {name: lst for name, lst in groups.items() if lst}
