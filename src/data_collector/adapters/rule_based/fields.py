"""rule_based adapter 共通のフィールド変換ヘルパー

96 サイト個別モジュールに散在していた「体重→size語彙」「性別正規化」
「和暦/日付パース」「サイト名/URLからの種別推定」「ラベル：値 の自由テキスト
パース」を集約する。各サイト adapter は DOM から生テキストを取り出す部分
(サイト固有) だけを持ち、変換ロジックはここに委譲する。

種別 (犬/猫) のパターンリストは `DataNormalizer._SPECIES_DOG_PATTERNS` /
`_SPECIES_CAT_PATTERNS` を単一のソースオブトゥルースとして再利用し、ここでは
重複定義しない。
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping

from ...domain.normalizer import DataNormalizer

# ─────────────────── weight_to_size ───────────────────

# 96 サイト中の全ての _weight_to_size 系実装が共通で使う境界値。
# 5kg 未満: 小 / 5kg 以上 15kg 未満: 中 / 15kg 以上: 大
_SIZE_BOUNDARY_SMALL_KG = 5.0
_SIZE_BOUNDARY_LARGE_KG = 15.0

# 「体重4kg」「体重：4.9kg」「体重 3〜4キログラム」等から数値を拾う。
# kg 表記を要求しない緩いパターン (city_machida 系) と、kg 表記を要求する
# 厳格パターン (douai_tokushima 系) の両方の呼び出し元があるため、
# `require_kg` で切り替えられるようにする。
_WEIGHT_NUMBER_RE = re.compile(r"(\d+(?:\.\d+)?)")
_WEIGHT_NUMBER_KG_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:kg|ｋｇ|キロ|キログラム)", re.IGNORECASE)


def weight_to_size(text: str, *, require_kg: bool = False) -> str:
    """体重を表す自由テキストから size 語彙 (小/中/大) を推定する。

    範囲表記 ("3〜4kg" 等) は正規表現が最初にマッチした数値 (= 最小値) を採用する。
    数値が拾えない/空文字の場合は "" を返す (呼び出し元は size 不明として扱う)。

    Args:
        text: 体重を含む可能性のある自由テキスト (例: "体重：4.9kg")
        require_kg: True の場合 kg/キロ 等の単位が付いた数値のみを拾う
            (単位なしの数値を誤って体重扱いしないための防御。douai_tokushima 系)。
    """
    if not text:
        return ""
    norm = unicodedata.normalize("NFKC", text).replace("．", ".")
    pattern = _WEIGHT_NUMBER_KG_RE if require_kg else _WEIGHT_NUMBER_RE
    m = pattern.search(norm)
    if not m:
        return ""
    try:
        kg = float(m.group(1))
    except ValueError:
        return ""
    if kg < _SIZE_BOUNDARY_SMALL_KG:
        return "小"
    if kg < _SIZE_BOUNDARY_LARGE_KG:
        return "中"
    return "大"


# ─────────────────── normalize_sex ───────────────────

# 「雄/雌」等の旧字体表記を「オス/メス」に寄せる (city_kagoshima 等 8 サイトの
# _normalize_sex がこの語彙で一致していた)。マッチしない値は素通しし、最終的な
# 「男の子/女の子/不明」正規化は DataNormalizer.normalize に一元化する
# (adapter 側で早期に丸めてしまうと DataNormalizer の広いパターン網羅を迂回するため)。
_SEX_MAP: Mapping[str, str] = {
    "雄": "オス",
    "雌": "メス",
}


def normalize_sex(raw_sex: str) -> str:
    """「雄/雌」を「オス/メス」に寄せる。それ以外はそのまま返す。"""
    if not raw_sex:
        return ""
    for src, dst in _SEX_MAP.items():
        if src in raw_sex:
            return dst
    return raw_sex


# ─────────────────── parse_jp_date ───────────────────


def parse_jp_date(raw_date: str) -> str:
    """和暦/西暦混在の日付表記を ISO 8601 (YYYY-MM-DD) に変換する。

    対応形式は `DataNormalizer._normalize_date` に委譲する (令和N年M月D日 /
    R{N}.M.D / YYYY-MM-DD / YYYY/MM/DD / YYYY年M月D日 / M月D日 / M/D 等)。
    パターンリストの二重管理を避けるため、ここでは独自パースを行わない。

    Returns:
        ISO 8601 形式の日付文字列。パース不能な場合は "" (adapter は空文字を
        RawAnimalData.shelter_date に渡せば DataNormalizer が収集日へ
        フォールバックする)。
    """
    if not raw_date:
        return ""
    try:
        return DataNormalizer._normalize_date(raw_date)
    except ValueError:
        return ""


# ─────────────────── infer_species ───────────────────

_DOG_PATTERNS = tuple(p.lower() for p in DataNormalizer._SPECIES_DOG_PATTERNS)
_CAT_PATTERNS = tuple(p.lower() for p in DataNormalizer._SPECIES_CAT_PATTERNS)


def infer_species(text: str) -> str:
    """サイト名 / URL / 見出し等の自由テキストから動物種別 (犬/猫/その他) を推定する。

    `DataNormalizer._SPECIES_DOG_PATTERNS` / `_SPECIES_CAT_PATTERNS` を
    唯一のパターン定義として使う (重複定義しない)。
    """
    if not text:
        return "その他"
    text_lower = text.lower()
    if any(p in text_lower for p in _DOG_PATTERNS):
        return "犬"
    if any(p in text_lower for p in _CAT_PATTERNS):
        return "猫"
    return "その他"


# ─────────────────── parse_label_value_pairs ───────────────────


def parse_label_value_pairs(
    texts: Iterable[str],
    label_to_field: Mapping[str, str],
    *,
    valid_values: Mapping[str, frozenset[str]] | None = None,
) -> dict[str, str]:
    """「ラベル：値」形式の自由テキスト行群から RawAnimalData フィールド値を抽出する。

    21 の single_page 系 adapter (city_chiba / city_amagasaki / city_hirakata /
    city_kagoshima / city_kawasaki / city_kashiwa / city_koshigaya_kojin /
    city_nagoya / city_machida / city_saitama / city_miyazaki / city_nara /
    city_utsunomiya / city_sendai / city_osaka / city_takatsuki /
    city_yokohama / hama_aikyou / pref_gunma / pref_chiba / pref_osaka) が
    それぞれ手書きしていた「全角/半角コロンで最初に分割 → label_to_field で
    引く → 既出フィールドは上書きしない」ループを共通化したもの。

    DOM から「どのテキスト断片群をラベル行とみなすか」(h4 の後続 <p> / テーブル
    セル / カード内の <p> 等) はサイトごとに構造が異なるため、この関数は
    "テキスト行の並び" を受け取るだけで DOM 走査には関与しない。

    Args:
        texts: ラベル：値 を含みうるテキスト片のイテラブル (改行区切り済みの行、
            もしくは要素ごとの `get_text()` 結果)。各要素はさらに改行で分割される。
        label_to_field: ラベル文字列 -> RawAnimalData フィールド名。
        valid_values: フィールド名 -> 許容値集合 (任意)。指定されたフィールドは
            値がホワイトリストに無ければ採用しない (city_chiba の size 防御等)。

    Returns:
        フィールド名 -> 値 の辞書。同じフィールドに複数ラベルがヒットした場合は
        最初にヒットした値を採用する (既出フィールドは上書きしない)。
    """
    fields: dict[str, str] = {}
    for chunk in texts:
        if not chunk:
            continue
        for raw_line in chunk.split("\n"):
            line = raw_line.strip()
            if not line:
                continue
            for sep in ("：", ":"):
                if sep not in line:
                    continue
                label, value = line.split(sep, 1)
                label = label.strip()
                value = value.strip()
                field = label_to_field.get(label)
                if field and value and field not in fields:
                    allowed = valid_values.get(field) if valid_values else None
                    if allowed is not None and value not in allowed:
                        break
                    fields[field] = value
                break
    return fields
