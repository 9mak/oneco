"""都道府県マッピングユーティリティ

source_url から都道府県を推定する。データ収集時の prefecture カラム自動設定と
DB バックフィルで同じロジックを共有する。
"""

from urllib.parse import urlparse


PREFECTURE_DOMAIN_MAP: tuple[tuple[str, str], ...] = (
    ("kochi-apc.com", "高知県"),
    ("douai-tokushima.com", "徳島県"),
    ("kagawa", "香川県"),
    ("ehime", "愛媛県"),
)


def infer_prefecture_from_url(url: str | None) -> str | None:
    """URL から都道府県名を推定する。

    Args:
        url: 元ページの URL

    Returns:
        都道府県名 (例: "高知県")。判定不能な場合は None。
    """
    if not url:
        return None
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if not host:
        return None
    for needle, prefecture in PREFECTURE_DOMAIN_MAP:
        if needle in host:
            return prefecture
    return None
