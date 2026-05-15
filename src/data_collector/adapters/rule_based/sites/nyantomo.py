"""函館どうなん動物愛護センター rule-based adapter

対象ドメイン: https://nyantomo.jp/donanhakodate/

特徴:
- WordPress + Elementor + JetEngine の動的リスト構造で、1 ページに
  複数の里親募集中の猫がカード (`div.jet-listing-grid__item`) で並ぶ
  single_page 形式。個別 detail ページは別途存在するが、必要な情報
  (名前/年齢/性別/施設名/写真) は一覧カードに含まれているため、
  一覧から直接抽出する。
- カード内部は Elementor ウィジェットの並びで、ラベル(`<p
  class="elementor-heading-title">名前</p>` 等) の直後に値ウィジェット
  (`.jet-listing-dynamic-field__content` または `.elementor-shortcode`)
  が並ぶ「ラベル -> 値」のフラットな構造。
- 画像は lazyload (`<img class="lazyload" src="data:..." data-src="..."`)
  だが、`<noscript>` フォールバック内に通常の `src` を持つ `<img>` が
  含まれるため、既定の `_extract_row_images` (src のみを見る実装) で
  正しい URL を取得できる。`/wp-content/uploads/` フィルタもそのまま機能。
- このサイトは猫の保護団体「ニャン友ねっとわーく北海道」運営のため、
  species は常に「猫」。
- 在庫 0 件のページ (掲示板に募集中の猫がいない状態) でも例外を投げず
  空リストを返す方針 (CityKashiwaAdapter と同様)。
"""

from __future__ import annotations

from typing import ClassVar

from bs4 import Tag

from ....domain.models import RawAnimalData
from ...municipality_adapter import ParsingError
from ..registry import SiteAdapterRegistry
from ..single_page_table import SinglePageTableAdapter


class NyantomoAdapter(SinglePageTableAdapter):
    """函館どうなん動物愛護センター用 rule-based adapter

    一覧ページ (https://nyantomo.jp/donanhakodate/) 内の
    `div.jet-listing-grid__item` 各カードから 1 匹の猫情報を抽出する。
    """

    # 各動物カード
    ROW_SELECTOR: ClassVar[str] = "div.jet-listing-grid__item"
    SKIP_FIRST_ROW: ClassVar[bool] = False
    # 「ラベル -> 値」のフラットなウィジェット並びを直接スキャンするため、
    # COLUMN_FIELDS は基底契約の充足のためだけに最低限の宣言を行う。
    COLUMN_FIELDS: ClassVar[dict[int, str]] = {
        0: "name",
        1: "age",
        2: "sex",
    }
    LOCATION_COLUMN: ClassVar[int | None] = None
    SHELTER_DATE_DEFAULT: ClassVar[str] = ""

    # ヘッダ (`<p class="elementor-heading-title">`) のテキスト ->
    # RawAnimalData 上の論理フィールド名
    _HEADING_TO_FIELD: ClassVar[dict[str, str]] = {
        "名前": "name",
        "年齢": "age",
        "性別": "sex",
    }

    # ─────────────────── オーバーライド ───────────────────

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        """一覧ページから動物カードの仮想 URL を返す

        基底実装は行 0 件で `ParsingError` を投げるが、本サイトは
        募集中の猫が一時的に 0 件になり得るため、その場合は空リストを
        返す方針を取る。HTML が取得できているのに `jet-listing-grid__item`
        が 1 件も無いケースは「募集 0 件」と解釈する。
        """
        rows = self._load_rows()
        if not rows:
            # HTML 自体は取得できているので 0 件状態として空リスト返却
            if self._html_cache:
                return []
            raise ParsingError(
                "行要素が見つかりません",
                selector=self.ROW_SELECTOR,
                url=self.site_config.list_url,
            )
        category = self.site_config.category
        return [
            (f"{self.site_config.list_url}#row={i}", category)
            for i in range(len(rows))
        ]

    def extract_animal_details(
        self, virtual_url: str, category: str = "adoption"
    ) -> RawAnimalData:
        """1 個の `jet-listing-grid__item` カードから RawAnimalData を構築する

        Elementor ウィジェットがフラットに並ぶため、`<p
        class="elementor-heading-title">名前/年齢/性別</p>` を見つけたら
        その直後の値ウィジェット
        (`.jet-listing-dynamic-field__content` または
        `.elementor-shortcode`) を値として採用する。
        """
        rows = self._load_rows()
        idx = self._parse_row_index(virtual_url)
        if idx >= len(rows):
            raise ParsingError(
                f"row index {idx} out of range (total {len(rows)})",
                url=virtual_url,
            )
        card = rows[idx]

        fields = self._extract_labeled_fields(card)
        location = self._extract_location(card)

        try:
            return RawAnimalData(
                # ニャン友ねっとわーくは猫の保護団体。
                species="猫",
                sex=fields.get("sex", ""),
                age=fields.get("age", ""),
                color="",
                size="",
                shelter_date=self.SHELTER_DATE_DEFAULT,
                # 「道南愛護センター」「函館市愛護センター」等の施設名。
                # 名前 (例: 「道南 ふわ」) と組み合わせるとより文脈が
                # 残るが、location は施設名を優先する。
                location=location or fields.get("name", ""),
                phone="",
                image_urls=self._extract_row_images(card, virtual_url),
                source_url=virtual_url,
                category=category,
            )
        except Exception as e:
            raise ParsingError(
                f"RawAnimalData バリデーション失敗: {e}", url=virtual_url
            ) from e

    # ─────────────────── ヘルパー ───────────────────

    def _extract_labeled_fields(self, card: Tag) -> dict[str, str]:
        """カード内の「ラベル -> 値」並びをスキャンしてフィールド辞書を返す

        Elementor の構造では heading ウィジェット
        (`<p class="elementor-heading-title">名前</p>`) と
        値ウィジェット (`.jet-listing-dynamic-field__content` または
        `.elementor-shortcode`) が DOM 上で前後する。ラベルのテキストを
        `_HEADING_TO_FIELD` で論理フィールド名に変換し、直後の最初の
        値ウィジェットを値として採用する。
        """
        fields: dict[str, str] = {}
        for heading in card.select("p.elementor-heading-title"):
            if not isinstance(heading, Tag):
                continue
            label = heading.get_text(strip=True)
            field = self._HEADING_TO_FIELD.get(label)
            if not field or field in fields:
                continue
            value = self._find_value_after(heading)
            if value:
                fields[field] = value
        return fields

    @staticmethod
    def _find_value_after(heading: Tag) -> str:
        """heading 要素より後の DOM 順で最初に出現する値ウィジェットを返す

        値ウィジェットは下記いずれかの class を持つ:
        - `.jet-listing-dynamic-field__content` (動的フィールド)
        - `.elementor-shortcode` (ショートコード経由の動的値)
        """
        # 同じ heading の祖先 element 配下から探す方が安全だが、
        # Elementor では heading と値が兄弟ウィジェットとして並ぶため、
        # heading の後続要素を DOM 順で辿る。
        for el in heading.find_all_next(
            class_=["jet-listing-dynamic-field__content", "elementor-shortcode"]
        ):
            if not isinstance(el, Tag):
                continue
            text = el.get_text(strip=True)
            if not text:
                continue
            return text
        return ""

    @staticmethod
    def _extract_location(card: Tag) -> str:
        """カード上部の施設名ラベル (例: 「道南愛護センター」) を取り出す

        Elementor のショートコードで「里親募集中<br/>道南愛護センター」
        のように 2 行で出力されているため、`.elementor-shortcode .centering`
        を取得し改行で分解して施設名行 (「センター」を含む行) を選ぶ。
        """
        for el in card.select(".elementor-shortcode .centering"):
            if not isinstance(el, Tag):
                continue
            # `<br/>` を改行で分けて行ごとに評価
            text = el.get_text("\n", strip=True)
            for line in text.split("\n"):
                line = line.strip()
                if not line:
                    continue
                # 「里親募集中」等のラベル行はスキップ
                if "募集" in line:
                    continue
                if "センター" in line or "愛護" in line:
                    return line
        return ""


# ─────────────────── サイト登録 ───────────────────
# sites.yaml の `name: "函館どうなん動物愛護センター（里親募集）"` に対応。
if SiteAdapterRegistry.get("函館どうなん動物愛護センター（里親募集）") is None:
    SiteAdapterRegistry.register(
        "函館どうなん動物愛護センター（里親募集）", NyantomoAdapter
    )
