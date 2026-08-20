"""ワンニャピアあきた (wannyapia.akita.jp) rule-based adapter

かつては JavaScript による動的描画で静的 HTML から動物データを取得できず、
常に空リストを返す実装だった。2026-08-19 の T046 監査で、現行サイトは
静的 HTML に一覧リンク・詳細フィールドとも出力されている (SSR) ことを
確認したため、WordPressListAdapter ベースの通常抽出へ書き換えた。
旧実装の「常に空」は 10 頭のサイレント掲載漏れを生んでいた。

list ページ (例: /pages/protective-cats):
    - 各動物カードに `<a href="/pages/animals/p{id}">` の詳細リンク。

detail ページ (例: /pages/animals/p2085):
    - `div.page-header h1` に仮名 (例: むつ)。
    - `<table>` に th/td ペアで「状態 / 個体管理ナンバー / 種類 / 性別 /
      年齢 / 体重 / 毛色 / 首輪の色 / 備考 / 連絡先」。
    - 「種類」は「雑種（ミックス）」等で犬猫を判別できないため、
      list_url (protective-dogs / protective-cats) から species を補完する。
    - 「連絡先」は「秋田県動物愛護センター」という施設名のみで電話番号を
      含まないため、フッタ固定の代表電話をフォールバック注入する。
    - 収容日・収容場所に相当するフィールドは存在しない。location は
      センター名を注入する (譲渡対象はセンター収容個体のため)。
    - 動物写真は `/uploads/contents/animals_.../` 配下。

カバーサイト (2):
- ワンニャピアあきた（譲渡犬）
- ワンニャピアあきた（譲渡猫）
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from ..registry import SiteAdapterRegistry
from ..wordpress_list import FieldSpec, WordPressListAdapter

# 秋田県動物愛護センター ワンニャピアあきた 代表電話 (サイトフッタ固定)
_CENTER_PHONE = "018-827-5051"
_CENTER_NAME = "秋田県動物愛護センター"


class WannyapiaAkitaAdapter(WordPressListAdapter):
    """ワンニャピアあきた adapter (譲渡犬 / 譲渡猫 共通)"""

    LIST_LINK_SELECTOR = "a[href*='/pages/animals/']"

    FIELD_SELECTORS = {
        "species": FieldSpec(label="種類"),
        "breed": FieldSpec(label="種類"),
        "sex": FieldSpec(label="性別"),
        "age": FieldSpec(label="年齢"),
        "color": FieldSpec(label="毛色"),
        # 体格フィールドは無く体重のみ。DataNormalizer._cap_size は体格語の
        # 無い純粋な体重表記を None に捨てるため、adapter 側で体格語へ変換する
        # (_postprocess_fields。oita_aigo / city_kashiwa と同じ 5kg/15kg 境界)。
        "size": FieldSpec(label="体重"),
        "description": FieldSpec(label="備考"),
        "management_number": FieldSpec(label="個体管理ナンバー"),
        "phone": FieldSpec(label="連絡先"),
        "name": FieldSpec(selector="div.page-header h1"),
    }

    # 動物写真は /uploads/contents/animals_... 配下のみ。サイト装飾画像は
    # ここで除外する (基底 _filter_image_urls は wp-content 前提のため、
    # セレクタ側で絞らないとフェイルセーフで装飾画像が素通りする)。
    IMAGE_SELECTOR = "img[src*='/uploads/contents/animals']"

    def _postprocess_fields(
        self, fields: dict[str, str], detail_url: str, soup: BeautifulSoup
    ) -> None:
        """species / size / phone / location の不足分を補完する。

        - species: 「雑種（ミックス）」等で犬猫判定できないため、
          list_url の protective-dogs / protective-cats から補完する。
        - size: 「体重」しか無く、DataNormalizer._cap_size は体格語の無い
          体重表記を None に捨てるため、ここで体格語へ変換する。
        - phone: 「連絡先」は施設名のみで番号を含まないため、電話番号らしい
          桁数 (6桁以上) が無ければ代表電話を注入する。
        - location: 相当フィールドが無いためセンター名を注入する
          (譲渡対象はセンター管理個体。yokosuka_doubutu と同型の補完)。
        """
        species = fields.get("species", "")
        if not any(kw in species for kw in ("犬", "猫", "いぬ", "ねこ", "イヌ", "ネコ")):
            list_url = (self.site_config.list_url or "").lower()
            if "protective-dogs" in list_url:
                fields["species"] = "犬"
            elif "protective-cats" in list_url:
                fields["species"] = "猫"

        fields["size"] = self._weight_to_size(fields.get("size", ""))

        if len(re.findall(r"\d", fields.get("phone", ""))) < 6:
            fields["phone"] = _CENTER_PHONE

        if not fields.get("location"):
            fields["location"] = _CENTER_NAME

    @staticmethod
    def _weight_to_size(size_text: str) -> str:
        """「約2.7㎏」のような体重表記を体格語 (小型/中型/大型) に変換する。

        oita_aigo / city_kashiwa と同じ境界: 5kg 未満=小型 / 15kg 未満=中型 /
        それ以上=大型。既に体格語を含む場合はそのまま温存し、数値が拾えない
        場合は空文字 (DataNormalizer 側で None 扱い)。
        """
        if not size_text:
            return ""
        if any(kw in size_text for kw in ("小型", "中型", "大型", "超小")):
            return size_text
        m = re.search(r"(\d+(?:[.．]\d+)?)", size_text)
        if not m:
            return ""
        try:
            kg = float(m.group(1).replace("．", "."))
        except ValueError:
            return ""
        if kg < 5.0:
            return "小型"
        if kg < 15.0:
            return "中型"
        return "大型"


SiteAdapterRegistry.register("ワンニャピアあきた（譲渡犬）", WannyapiaAkitaAdapter)
SiteAdapterRegistry.register("ワンニャピアあきた（譲渡猫）", WannyapiaAkitaAdapter)
