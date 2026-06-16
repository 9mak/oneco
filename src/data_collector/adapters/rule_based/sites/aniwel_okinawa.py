"""沖縄県動物愛護管理センター (aniwel-pref.okinawa) rule-based adapter

対象ドメイン: https://www.aniwel-pref.okinawa/

カバーサイト (6):
- 沖縄県動物愛護管理センター（収容犬）  /animals/accommodate/dogs
- 沖縄県動物愛護管理センター（収容猫）  /animals/accommodate/cats
- 沖縄県動物愛護管理センター（行方不明犬）/animals/missing/dogs
- 沖縄県動物愛護管理センター（行方不明猫）/animals/missing/cats
- 沖縄県動物愛護管理センター（迷い込み保護犬）/animals/protection/dogs
- 沖縄県動物愛護管理センター（迷い込み保護猫）/animals/protection/cats

特徴:
- JavaScript で動物 DB を動的描画するため `PlaywrightFetchMixin` を併用する。
- 一覧ページから個別詳細ページへのリンクは
  `/animals/{accommodate,missing,protection}_view/{ID}` の共通パターン。
  3 系統の prefix を 1 つの LIST_LINK_SELECTOR (`a[href*='_view/']`) で拾う。
- 詳細ページは `<dl><dt>項目名</dt><dd>値</dd></dl>` 形式の定義リスト
  (または `<table><th><td>` 形式) でフィールドを表現する想定。
  `WordPressListAdapter._extract_by_label` がそのまま乗る。
- 種別 (犬/猫) は URL/サイト名から判別可能なため、サイト固有の
  species_hint をサイト名から推定して `species` が空のとき補完する。
"""

from __future__ import annotations

import re
from typing import ClassVar

from ....domain.models import AnimalData, RawAnimalData
from ..playwright import PlaywrightFetchMixin
from ..registry import SiteAdapterRegistry
from ..wordpress_list import FieldSpec, WordPressListAdapter

# 「12」のような数値のみの年齢を「N歳」へ補完するためのパターン。
# 半角/全角数字、小数 (例: 「2.5」) を許容。
_NUMERIC_ONLY_AGE = re.compile(r"^[\d０-９]+(?:[.．][\d０-９]+)?$")

# 動物画像と装飾画像 (ロゴ・アイコン・サイドバー等) を区別するための URL パターン。
# 沖縄県動愛サイトは `/files/animal/image/{ID}/` 配下に動物写真を置いている。
_ANIMAL_IMAGE_PATH = "/files/animal/image/"
_DECORATION_PATH_PATTERNS = (
    "/images/header/",
    "/images/sidebar/",
    "/images/top/",
    "/images/animals/pdf_icon",
    "/images/animals/icon_",
)

# 沖縄県動物愛護管理センター本所 (南城市大里) 代表電話。
# 2026-06 観測: https://www.aniwel-pref.okinawa/ のお問い合わせに記載。
# 本所 / ハピアニおきなわ (譲渡推進棟) ともに同じ代表電話を使うため、
# 6 サイト (収容/行方不明/迷い込み × 犬/猫) 全件で共通の連絡先として
# 注入する。詳細ページ自体に phone 欄が無く、snapshots では 91 件全件で
# phone=null だったので空のときだけ補完する (将来 detail に番号が
# 書かれるようになった場合に上書きしないため)。
_DEFAULT_PHONE = "098-945-3043"


class AniwelOkinawaAdapter(PlaywrightFetchMixin, WordPressListAdapter):
    """沖縄県動物愛護管理センター 共通アダプター

    list / detail テンプレートが 6 サイト共通なので、サイト名ごとに
    クラスを分けず、registry に複数の site_name を 1 クラスで束ねる。
    """

    # JS 描画完了を待つセレクタ。動物カードリスト/詳細表本体が
    # 描画されるまで待機する。一覧/詳細どちらでも `_view/` を含む
    # `<a>` または `<dl>` が現れるため、緩めに `body` のうち
    # 主要コンテナを待つ。
    WAIT_SELECTOR: ClassVar[str | None] = "main, #app, .animal-list, dl, a[href*='_view/']"

    # 一覧ページから詳細ページへのリンク。
    # accommodate / missing / protection の 3 prefix を共通で拾う。
    LIST_LINK_SELECTOR: ClassVar[str] = "a[href*='_view/']"

    # 詳細ページ `<table><th><td>` の実見出しラベル (2026-05 ブラウザ実査)。
    # 収容(accommodate)/行方不明(missing)/迷い込み(protection) の 3 系統で
    # ラベルが異なるため、`_extract_by_label` の部分一致 (label ⊂ th文字列) と
    # tuple OR 検索で全系統を 1 アダプターに束ねる。
    #   - location: 場所 / 行方不明場所 / 迷い込んだ場所 → 共通部分文字列 "場所"
    #   - size    : 体格 (旧 "大きさ" は実在せず location が 100% 不明だった)
    #   - 日付    : 収容日 / 保護日 / 行方不明日 (受付月日より保護日を優先)
    #   - age     : "年齢" は "推定年齢" にも部分一致する
    #   - species : "種類"/"品種" は値が "雑種(ミケネコ)" 等で誤分類しやすいため
    #               抽出せずサイト名から犬/猫を補完する (extract_animal_details)
    FIELD_SELECTORS: ClassVar[dict[str, FieldSpec]] = {
        "species": FieldSpec(label="種類"),
        "sex": FieldSpec(label="性別"),
        "age": FieldSpec(label="年齢"),
        "color": FieldSpec(label="毛色"),
        "size": FieldSpec(label=("体格", "大きさ")),
        "shelter_date": FieldSpec(label=("収容日", "保護日", "行方不明日")),
        "location": FieldSpec(label="場所"),
        "phone": FieldSpec(label="連絡先"),
        # 個体識別: 管理番号。収容=「記号」(例 R8-4)、行方不明/迷い込み=「受付番号」。
        # base が management_number を RawAnimalData に配線済みのためラベル登録で開通。
        "management_number": FieldSpec(label=("記号", "受付番号")),
    }

    # 動物画像。実サイトは `<td class="photo"><ul class="slick-main">...<img></ul></td>`
    # 構造で表示している (slick-main は実画像、slick-nav はサムネだが同一 src)。
    # `figure img` / `.animal-photo img` も将来対応のため残す。
    IMAGE_SELECTOR: ClassVar[str] = "td.photo img, .slick-main img, figure img, .animal-photo img"

    # ─────────────────── オーバーライド ───────────────────

    def extract_animal_details(self, detail_url: str, category: str = "adoption") -> RawAnimalData:
        """詳細ページ抽出。species/age/phone を補完し、装飾画像を除外する。

        - species が空ならサイト名から犬/猫を補完
        - age が「12」「2.5」のような数値単独表記なら「12歳」に補完
          (normalizer は単位付きしか解釈できないため)
        - image_urls から `/images/header/` `/images/sidebar/` などの
          装飾画像を除外し、重複 (slick-main と slick-nav の同一 src) を排除
        - phone が空なら沖縄県動物愛護管理センター本所代表電話を注入
          (detail ページ自体に連絡先欄が無いため。将来 detail に番号が
          書かれた場合は上書きしない)
        """
        raw = super().extract_animal_details(detail_url, category=category)
        updates: dict[str, object] = {}
        if not raw.species:
            hint = self._infer_species_from_site_name()
            if hint:
                updates["species"] = hint
        age = self._normalize_numeric_age(raw.age)
        if age != raw.age:
            updates["age"] = age
        cleaned_images = self._filter_decoration_images(raw.image_urls)
        if cleaned_images != raw.image_urls:
            updates["image_urls"] = cleaned_images
        if not raw.phone:
            updates["phone"] = self._normalize_phone(_DEFAULT_PHONE)
        if updates:
            raw = raw.model_copy(update=updates)
        return raw

    def normalize(self, raw_data: RawAnimalData) -> AnimalData:
        return self._default_normalize(raw_data)

    # ─────────────────── ヘルパー ───────────────────

    def _infer_species_from_site_name(self) -> str:
        """サイト名 (例: 「…（収容犬）」) から犬/猫を推定する"""
        name = self.site_config.name
        if "犬" in name:
            return "犬"
        if "猫" in name:
            return "猫"
        return ""

    @staticmethod
    def _normalize_numeric_age(age: str) -> str:
        """「12」のような数値単独の年齢を「N歳」へ補完する

        normalizer._normalize_age が「3歳」「6ヶ月」のように単位付きの
        フォーマットしか解釈できないため、adapter 段階で単位を補う。
        """
        if not age:
            return age
        stripped = age.strip()
        if _NUMERIC_ONLY_AGE.match(stripped):
            return f"{stripped}歳"
        return age

    @staticmethod
    def _filter_decoration_images(urls: list[str]) -> list[str]:
        """装飾画像 (ヘッダ/サイドバー/PDF アイコン等) を除外し重複を排除

        実サイトの動物写真は `/files/animal/image/{ID}/...` 配下にのみ置かれる。
        IMAGE_SELECTOR で td.photo を指定しているが、念のため URL ベースの
        二重防御を入れる。slick-main と slick-nav が同じ画像を 2 回返すので
        順序を保ったまま重複も除去する。
        """
        cleaned: list[str] = []
        seen: set[str] = set()
        for u in urls:
            if any(p in u for p in _DECORATION_PATH_PATTERNS):
                continue
            if u in seen:
                continue
            seen.add(u)
            cleaned.append(u)
        return cleaned


# ─────────────────── サイト登録 ───────────────────
# 同一テンプレート上で運用される 6 サイトを同一 adapter にマップする。
_SITE_NAMES = (
    "沖縄県動物愛護管理センター（収容犬）",
    "沖縄県動物愛護管理センター（収容猫）",
    "沖縄県動物愛護管理センター（行方不明犬）",
    "沖縄県動物愛護管理センター（行方不明猫）",
    "沖縄県動物愛護管理センター（迷い込み保護犬）",
    "沖縄県動物愛護管理センター（迷い込み保護猫）",
)

for _name in _SITE_NAMES:
    if SiteAdapterRegistry.get(_name) is None:
        SiteAdapterRegistry.register(_name, AniwelOkinawaAdapter)
