"""アニウェル北海道（猫の里親募集） rule-based adapter

対象ドメイン: https://aniwel.jp/cats/

特徴:
- 非営利型一般社団法人アニウェル北海道が運営する WordPress (Lightning テーマ)
  の里親募集ページ。1 ページに `flexitem2 width160 base` クラスのカードが
  並ぶ single_page 形式で、各カードに名前 / 性別 / 年齢 / 写真 / 詳細ページ
  リンクが含まれる。`single_page: true` 設定のため詳細ページは取得せず
  カードから直接抽出する。
- カードの典型的な内部構造:
    <div class="flexitem2 width160 base">
      <div class="full">
        <img src="...uploads/.../xxx-150x150.jpg" alt="..." />
        <div class="name">うらら</div>
        <div class="sex">メス</div>
        <div class="age">約4歳</div>
        <section class="Satooya">
          <a href="https://aniwel.jp/cats/.../" class="btn_09">...</a>
        </section>
      </div>
    </div>
- カード内には毛色・収容日・場所などの情報が無いため、それらは空文字とする。
  species は URL とサイト名から「猫」固定で扱う。
- 動物カードの並ぶ親領域 (`#main` の `.postList`) 以外にもサイドバーや
  フッターに同名クラスが現れる可能性は低いが、念のため `ROW_SELECTOR` は
  カード固有のクラス組合せ `div.flexitem2.base` を使用する。
- 0 件状態 (募集中の猫がいない) の場合はカードが出力されないため、
  ParsingError ではなく空リストを返す。
"""

from __future__ import annotations

from typing import ClassVar

from bs4 import Tag

from ....domain.models import RawAnimalData
from ...municipality_adapter import ParsingError
from ..registry import SiteAdapterRegistry
from ..single_page_table import SinglePageTableAdapter


class AniwelAdapter(SinglePageTableAdapter):
    """アニウェル北海道（猫の里親募集）用 rule-based adapter

    一覧ページ (https://aniwel.jp/cats/) に並ぶ
    `div.flexitem2.base` カードを 1 頭分として扱う single_page 形式。
    """

    # 各動物カードの起点 (CSS class 組合せでサイドバー等の誤抽出を避ける)
    ROW_SELECTOR: ClassVar[str] = "div.flexitem2.base"
    SKIP_FIRST_ROW: ClassVar[bool] = False
    # `<div class="name|sex|age">値</div>` 並びを直接スキャンするため
    # `COLUMN_FIELDS` は基底契約の充足のためだけに宣言する。
    COLUMN_FIELDS: ClassVar[dict[int, str]] = {
        0: "sex",
        1: "age",
    }
    LOCATION_COLUMN: ClassVar[int | None] = None
    SHELTER_DATE_DEFAULT: ClassVar[str] = ""

    # カード内の `<div class="...">値</div>` の class → RawAnimalData フィールド名。
    # `name` は RawAnimalData に対応フィールドが無いため意図的に取得しない。
    _CLASS_TO_FIELD: ClassVar[dict[str, str]] = {
        "sex": "sex",
        "age": "age",
    }

    # ─────────────────── オーバーライド ───────────────────

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        """一覧ページから動物の仮想 URL を返す

        基底実装は行が 0 件のとき `ParsingError` を投げるが、本サイトでは
        募集中の猫が居ないとカードが一切出力されない正常状態が起き得るため、
        `<body class="post-type-archive-cats">` (一覧ページの本体) を検出した
        場合は空リストを返し、それ以外で行が見つからなかった場合のみ
        `ParsingError` を伝播する。
        """
        rows = self._load_rows()
        if not rows:
            if self._html_cache and self._is_archive_page(self._html_cache):
                return []
            raise ParsingError(
                "行要素が見つかりません",
                selector=self.ROW_SELECTOR,
                url=self.site_config.list_url,
            )
        category = self.site_config.category
        return [(f"{self.site_config.list_url}#row={i}", category) for i in range(len(rows))]

    def extract_animal_details(self, virtual_url: str, category: str = "adoption") -> RawAnimalData:
        """1 個の `div.flexitem2.base` カードから RawAnimalData を構築する

        基底の `td/th` ベース実装は使わず、カード内の
        `<div class="name|sex|age">値</div>` を class 名で直接抽出する。
        species はサイトが猫専用ページのため「猫」固定。
        """
        rows = self._load_rows()
        idx = self._parse_row_index(virtual_url)
        if idx >= len(rows):
            raise ParsingError(
                f"row index {idx} out of range (total {len(rows)})",
                url=virtual_url,
            )
        card = rows[idx]

        fields: dict[str, str] = {}
        for class_name, field_name in self._CLASS_TO_FIELD.items():
            el = card.find("div", class_=class_name)
            if isinstance(el, Tag):
                value = el.get_text(strip=True)
                if value:
                    fields[field_name] = value

        species = self._infer_species()

        try:
            return RawAnimalData(
                species=species,
                sex=fields.get("sex", ""),
                age=fields.get("age", ""),
                color="",
                size="",
                shelter_date=self.SHELTER_DATE_DEFAULT,
                location="",
                phone="",
                image_urls=self._extract_row_images(card, virtual_url),
                source_url=virtual_url,
                category=category,
            )
        except Exception as e:
            raise ParsingError(f"RawAnimalData バリデーション失敗: {e}", url=virtual_url) from e

    # ─────────────────── ヘルパー ───────────────────

    @staticmethod
    def _is_archive_page(html: str) -> bool:
        """`/cats/` の archive ページであることを示す signal を含むか判定する

        WordPress の post type archive は body に
        `post-type-archive-cats` クラスが付与される。これを見ることで、
        ネットワークエラー等で来た想定外の HTML を空リスト扱いに
        誤って吸収するリスクを下げる。
        """
        return "post-type-archive-cats" in html or "post-type-cats" in html

    @staticmethod
    def _infer_species() -> str:
        """サイトは猫専用ページのため species は「猫」固定"""
        return "猫"


# ─────────────────── サイト登録 ───────────────────
_SITE_NAME = "アニウェル北海道（猫の里親募集）"
if SiteAdapterRegistry.get(_SITE_NAME) is None:
    SiteAdapterRegistry.register(_SITE_NAME, AniwelAdapter)
