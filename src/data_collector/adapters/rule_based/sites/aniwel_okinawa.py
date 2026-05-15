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

from typing import ClassVar

from ....domain.models import AnimalData, RawAnimalData
from ...municipality_adapter import ParsingError
from ..playwright import PlaywrightFetchMixin
from ..registry import SiteAdapterRegistry
from ..wordpress_list import FieldSpec, WordPressListAdapter


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

    # 詳細ページの定義リスト (または table) 見出しに対応するラベル。
    # 公開仕様書が無いため一般的な日本語ラベルを網羅的に並べる。
    FIELD_SELECTORS: ClassVar[dict[str, FieldSpec]] = {
        "species": FieldSpec(label="種類"),
        "sex": FieldSpec(label="性別"),
        "age": FieldSpec(label="年齢"),
        "color": FieldSpec(label="毛色"),
        "size": FieldSpec(label="大きさ"),
        "shelter_date": FieldSpec(label="収容日"),
        "location": FieldSpec(label="収容場所"),
        "phone": FieldSpec(label="連絡先"),
    }

    # 動物画像。サイトが独自 CMS のため `/wp-content/uploads/` パスは無く、
    # `_filter_image_urls` のフェイルセーフで全画像が返る挙動に依存する。
    # 装飾画像 (ヘッダロゴ等) を排除するため、`<figure>` または
    # 詳細本体らしい要素配下の `<img>` のみに限定する。
    IMAGE_SELECTOR: ClassVar[str] = "figure img, .animal-photo img, main img"

    # ─────────────────── オーバーライド ───────────────────

    def extract_animal_details(
        self, detail_url: str, category: str = "adoption"
    ) -> RawAnimalData:
        """詳細ページ抽出。species が空ならサイト名から補完する。"""
        raw = super().extract_animal_details(detail_url, category=category)
        if not raw.species:
            hint = self._infer_species_from_site_name()
            if hint:
                raw = raw.model_copy(update={"species": hint})
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
