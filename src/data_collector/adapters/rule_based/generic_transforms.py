"""GenericAdapter の `postprocess:` から名前で参照される小さな変換関数群 (T405)

各関数のシグネチャは `(fields: dict[str, str], adapter: RuleBasedAdapter) -> None`
(in-place 変更)。spec.yaml の `postprocess:` は文字列のリストで、`weight_to_size`
のように引数無しの名前、または `phone_fallback:028-684-5458` のように `:` 区切りで
引数を渡す名前のどちらも受け付ける。

移行元の 9 モジュールに散在していた `_postprocess_fields` の個別実装を、
再利用可能な名前付き変換として集約する。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from .fields import weight_to_size as _weight_to_size_common

if TYPE_CHECKING:
    from .base import RuleBasedAdapter

# transform シグネチャ: (fields, adapter, *args) -> None
_TransformFn = Callable[[dict[str, str], "RuleBasedAdapter", list[str]], None]

_SPECIES_KEYWORDS = ("犬", "猫", "いぬ", "ねこ", "イヌ", "ネコ")


def _species_from_list_url_dog_cat(
    fields: dict[str, str], adapter: RuleBasedAdapter, args: list[str]
) -> None:
    """species が犬/猫キーワードを含まない場合、list_url の dog/cat 系ヒントで補完する

    douaicenter (`_infer_species_from_url` の "/dog"/"/cat" 判定) と、
    wannyapia_akita (`protective-dogs`/`protective-cats` クエリ) の両方の
    語彙を吸収する。args にカスタムのキーワードペアを
    `dog=/dog,cat=/cat` のように渡せる。デフォルトは両サイトの語彙を含む。
    """
    species = fields.get("species", "")
    if any(kw in species for kw in _SPECIES_KEYWORDS):
        return
    list_url = (getattr(getattr(adapter, "site_config", None), "list_url", "") or "").lower()

    dog_hints = ["/dog", "/inu", "protective-dogs"]
    cat_hints = ["/cat", "/neko", "protective-cats"]
    for arg in args:
        if "=" not in arg:
            continue
        key, value = arg.split("=", 1)
        if key == "dog":
            dog_hints.extend(value.split(","))
        elif key == "cat":
            cat_hints.extend(value.split(","))

    if any(hint in list_url for hint in dog_hints):
        fields["species"] = "犬"
    elif any(hint in list_url for hint in cat_hints):
        fields["species"] = "猫"


def _weight_to_size_transform(
    fields: dict[str, str], adapter: RuleBasedAdapter, args: list[str]
) -> None:
    """`size` フィールドの体重表記 (例: "約2.7kg") を体格語 (小型/中型/大型) に変換する

    5kg 未満=小型 / 15kg 未満=中型 / それ以上=大型 (oita_aigo / city_kashiwa /
    wannyapia_akita 共通の境界)。既に体格語を含む場合はそのまま温存する。
    """
    size_text = fields.get("size", "")
    if not size_text:
        return
    if any(kw in size_text for kw in ("小型", "中型", "大型", "超小")):
        return
    size = _weight_to_size_common(size_text, require_kg=False)
    # weight_to_size は「小/中/大」を返すため、既存 adapter の語彙
    # (「小型/中型/大型」) に寄せる。数値が拾えない場合は元の adapter 実装と
    # 同様に空文字へ落とす (「不明」等の非数値表記を size として残さない)。
    fields["size"] = {"小": "小型", "中": "中型", "大": "大型"}.get(size, size)


def _phone_fallback(fields: dict[str, str], adapter: RuleBasedAdapter, args: list[str]) -> None:
    """phone が空 (未抽出) のとき、args[0] の代表電話を注入する

    正規化 (`_normalize_phone`) は WordPressListAdapter.extract_animal_details /
    SinglePageTableAdapter.extract_animal_details が RawAnimalData 構築時に
    必ず一度だけ通すため、ここでは生テキストの有無だけを見る (douaicenter /
    wannyapia_akita の元実装と同じ挙動)。
    """
    if not args:
        return
    if not fields.get("phone", "").strip():
        fields["phone"] = args[0]


def _phone_fallback_if_invalid(
    fields: dict[str, str], adapter: RuleBasedAdapter, args: list[str]
) -> None:
    """phone を正規化し、有効な番号 (10-11桁) が取れない場合のみ代表電話を注入する

    wannyapia_akita の元実装と同じ挙動: 「連絡先」欄に施設名のみが入っていて
    番号を含まない場合も救済する (`_phone_fallback` の素の空文字チェックより広い)。
    """
    if not args:
        return
    normalized = adapter._normalize_phone(fields.get("phone", ""))
    fields["phone"] = normalized or args[0]


def _location_fallback(fields: dict[str, str], adapter: RuleBasedAdapter, args: list[str]) -> None:
    """location が空のとき、args[0] の施設名を注入する"""
    if not args:
        return
    if not fields.get("location"):
        fields["location"] = args[0]


_TRANSFORMS: dict[str, _TransformFn] = {
    "species_from_list_url_dog_cat": _species_from_list_url_dog_cat,
    "weight_to_size": _weight_to_size_transform,
    "phone_fallback": _phone_fallback,
    "phone_fallback_if_invalid": _phone_fallback_if_invalid,
    "location_fallback": _location_fallback,
}


def apply_postprocess(names: list[str], fields: dict[str, str], adapter: RuleBasedAdapter) -> None:
    """spec.yaml の `postprocess:` リストを順番に適用する

    各要素は `name` または `name:arg1:arg2` の形式。未知の名前は ValueError
    (spec の記述ミスをテストで即座に検出するため、黙って無視しない)。
    """
    for entry in names:
        name, *args = entry.split(":")
        fn = _TRANSFORMS.get(name)
        if fn is None:
            raise ValueError(f"未知の postprocess 変換名: {name!r} (spec の記述ミス)")
        fn(fields, adapter, args)
