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


def is_missing_value(value: object) -> bool:
    """値そのものが欠損かを返す。

    None / "不明" 等のプレースホルダ文字列 / 空リスト を欠損とみなす。
    AnimalData を持たない呼び出し元 (公開 API の dict を扱う監査スクリプト等) が
    欠損の定義をコピーして食い違わせないよう、値ベースの判定として切り出す。
    """
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() in _UNKNOWN_STRINGS
    if isinstance(value, list):
        return len(value) == 0
    return False


def is_missing(animal: AnimalData, field: str) -> bool:
    """指定フィールドが欠損しているかを返す。

    None / "不明" 等のプレースホルダ文字列 / 空リスト を欠損とみなす。
    """
    return is_missing_value(getattr(animal, field, None))


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
    source_urls_by_site: dict[str, list[str]],
) -> dict[str, list[AnimalData]]:
    """収集時に判明した `source_url` の対応で動物をサイト別にまとめる。

    Args:
        animals: 今 run の全動物。
        source_urls_by_site: `{site_name: [収集した source_url, ...]}`。
            収集ループが実際に取得した URL をそのまま渡す。

    Returns:
        `{site_name: [AnimalData, ...]}`。どの site にも紐付かなかった動物は
        結果に含めず、1 件も該当しない site はキーごと落とす (空配列は返さない)。

    以前は `{site_name: list_url}` を受け取り `source_url.startswith(list_url)`
    で振り分けていたが、1 頭ごとに独立した詳細ページ URL を持つサイト
    (長崎犬猫ネット `/animal/no-N/` 等) では前方一致が成立せず、実測で
    211 サイト中 70 サイトが「実データがあるのに品質監視の対象外」だった。
    加えて同一ドメインに複数サイトを持つ自治体 (旭川市 8 / 福岡県 8 など) は
    source_url だけでは原理的に site を特定できないため、収集時の対応を正とする。
    """
    if not animals or not source_urls_by_site:
        return {}

    # source_url → site_name の逆引き。同じ URL が複数サイトに現れた場合は
    # 先に登録されたサイトを優先する (収集順 = sites.yaml の定義順)。
    site_by_url: dict[str, str] = {}
    for name, urls in source_urls_by_site.items():
        for url in urls:
            site_by_url.setdefault(str(url), name)

    groups: dict[str, list[AnimalData]] = {name: [] for name in source_urls_by_site}
    for a in animals:
        name = site_by_url.get(str(a.source_url))
        if name is not None:
            groups[name].append(a)
    return {name: lst for name, lst in groups.items() if lst}
