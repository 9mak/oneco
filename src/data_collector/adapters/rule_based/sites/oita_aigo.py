"""おおいた動物愛護センター rule-based adapter

対象ドメイン: https://oita-aigo.com/

特徴:
- 同一ドメイン上で 3 サイト (迷子情報メイン / 譲渡犬 / 譲渡猫) が
  共通テンプレートを使用しているため 1 つの adapter で全サイトを賄う:
    - https://oita-aigo.com/lostchild/                       (迷子情報, sheltered)
    - https://oita-aigo.com/information_doglist/anytimedog/  (譲渡犬,   adoption)
    - https://oita-aigo.com/information_catlist/anytimecat/  (譲渡猫,   adoption)
- 1 ページに複数動物が `<div class="information_box">` カード形式で
  並ぶ single_page サイト。詳細ページへのリンクは存在するが、
  一覧ページに必要な情報 (保護地域 / 推定年齢 / 性別 / 体重 / 写真) が
  全て掲載されているため一覧から抽出する。
- 各カード内部は `<dl><dt>項目名</dt><dd>値</dd></dl>` の定義リスト + 先頭の
  `<dd class="lostchild_ttl">` (例: 令和8年5月1日) と末尾の
  `<div class="information_day"><time>更新日：YYYY.MM.DD</time></div>` で
  構成される。テーブルではなく label 一致で抽出するため、基底の
  `td/th` ベース既定 `extract_animal_details` をオーバーライドする。
- 動物種別 (犬/猫) は譲渡サイトでは URL/サイト名から決まるが、
  迷子情報メインは犬猫が混在し HTML 上にも明示が無いため、
  サイト名から推定し不明な場合は空文字とする。
"""

from __future__ import annotations

from typing import ClassVar

from bs4 import Tag

from ....domain.models import RawAnimalData
from ...municipality_adapter import ParsingError
from ..registry import SiteAdapterRegistry
from ..single_page_table import SinglePageTableAdapter


class OitaAigoAdapter(SinglePageTableAdapter):
    """おおいた動物愛護センター用 rule-based adapter

    迷子情報メイン / 譲渡犬 / 譲渡猫 の 3 サイトで共通テンプレート。
    各動物は `div.information_box` カードで表現される single_page 形式。
    """

    # 各動物カード
    ROW_SELECTOR: ClassVar[str] = "div.information_box"
    # ヘッダ相当の行は無いので除外しない
    SKIP_FIRST_ROW: ClassVar[bool] = False
    # `<dl><dt>...</dt><dd>...</dd></dl>` から label 一致で抽出するため、
    # 基底の col_index ベース実装は使わない。契約として空辞書を宣言する。
    COLUMN_FIELDS: ClassVar[dict[int, str]] = {}
    LOCATION_COLUMN: ClassVar[int | None] = None
    # 収容日はカード上の「令和YYYY年M月D日」表記をそのまま採用するため
    # 既定値は不要 (空文字 = 不明扱い)。
    SHELTER_DATE_DEFAULT: ClassVar[str] = ""

    # 定義リストの dt ラベル -> RawAnimalData フィールド名
    LABEL_FIELDS: ClassVar[dict[str, str]] = {
        "保護地域": "location",
        "推定年齢": "age",
        "性別": "sex",
        "体重": "size",
        "毛色": "color",
    }

    # ─────────────────── オーバーライド ───────────────────

    def extract_animal_details(self, virtual_url: str, category: str = "adoption") -> RawAnimalData:
        """`<div class="information_box">` カードから RawAnimalData を構築する

        基底の `td/th` ベース実装ではなく、`<dl><dt>label</dt><dd>value</dd></dl>`
        の並びを LABEL_FIELDS のラベル一致で取り出す。
        """
        rows = self._load_rows()
        idx = self._parse_row_index(virtual_url)
        if idx >= len(rows):
            raise ParsingError(
                f"row index {idx} out of range (total {len(rows)})",
                url=virtual_url,
            )
        card = rows[idx]

        fields = self._extract_dl_fields(card)

        # 収容日: `<dd class="lostchild_ttl">` (例: "令和8年5月1日") を採用。
        # 無い場合は SHELTER_DATE_DEFAULT (空文字) で不明扱い。
        shelter_date = ""
        ttl = card.select_one("dd.lostchild_ttl")
        if isinstance(ttl, Tag):
            shelter_date = ttl.get_text(strip=True)
        if not shelter_date:
            shelter_date = self.SHELTER_DATE_DEFAULT

        # 動物種別はサイト名/URL から推定 (HTML には明示されない)。
        species = self._infer_species(self.site_config.name, self.site_config.list_url)

        try:
            return RawAnimalData(
                species=species,
                sex=fields.get("sex", ""),
                age=fields.get("age", ""),
                color=fields.get("color", ""),
                size=fields.get("size", ""),
                shelter_date=shelter_date,
                location=fields.get("location", ""),
                phone="",
                image_urls=self._extract_row_images(card, virtual_url),
                source_url=virtual_url,
                category=category,
            )
        except Exception as e:
            raise ParsingError(f"RawAnimalData バリデーション失敗: {e}", url=virtual_url) from e

    # ─────────────────── ヘルパー ───────────────────

    def _extract_dl_fields(self, card: Tag) -> dict[str, str]:
        """カード配下の `<dl><dt>label</dt><dd>value</dd></dl>` を辞書化する

        同一 dl 内に dt が無く dd のみのもの (タイトル用 `lostchild_ttl`) は
        `LABEL_FIELDS` に登録されないため自然にスキップされる。
        """
        result: dict[str, str] = {}
        for dl in card.find_all("dl"):
            if not isinstance(dl, Tag):
                continue
            dt = dl.find("dt")
            dd = dl.find("dd")
            if not isinstance(dt, Tag) or not isinstance(dd, Tag):
                continue
            label = dt.get_text(strip=True)
            value = dd.get_text(strip=True)
            field = self.LABEL_FIELDS.get(label)
            if field and field not in result:
                result[field] = value
        return result

    @staticmethod
    def _infer_species(name: str, list_url: str) -> str:
        """サイト名 / URL から動物種別 (犬/猫) を推定する

        - 譲渡犬サイト: name に "犬" / URL に "doglist" を含む
        - 譲渡猫サイト: name に "猫" / URL に "catlist" を含む
        - 迷子情報メイン: 犬猫混在のため空文字 (不明) を返す
        """
        haystack = f"{name} {list_url}"
        if "doglist" in list_url or ("犬" in name and "猫" not in name):
            return "犬"
        if "catlist" in list_url or ("猫" in name and "犬" not in name):
            return "猫"
        # 迷子情報など犬猫混在のケースは空文字 (不明)
        del haystack
        return ""


# ─────────────────── サイト登録 ───────────────────
# 同一テンプレート上で運用される 3 サイトを同一 adapter にマップする。
_SITE_NAMES = (
    "おおいた動物愛護センター（迷子情報メイン）",
    "おおいた動物愛護センター（譲渡犬）",
    "おおいた動物愛護センター（譲渡猫）",
)

for _name in _SITE_NAMES:
    SiteAdapterRegistry.register(_name, OitaAigoAdapter)
