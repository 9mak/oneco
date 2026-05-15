"""広島市 (city.hiroshima.lg.jp) rule-based adapter

対象ドメイン: https://www.city.hiroshima.lg.jp/living/pet-doubutsu/

特徴:
- 同一テンプレート上で 2 サイトが運用されている (URL の末尾ページ番号のみ異なる):
    - .../1021301/1026245/1037461.html  飼い主不明犬 (迷子犬)
    - .../1021301/1026245/1039097.html  飼い主不明猫 (迷子猫)
- 1 ページに動物 1 件のみ。`<div id="voice">` 配下の `<dl>` に
  「収容月日 / 種類 / 推定年齢 / 毛色 / 性別 / 首輪等 / 拾得等の場所 / 備考」
  が `<dt>/<dd>` で並ぶ。`<dl>` の直前の `<h2>` に整理番号、
  `<p class="imagecenter">` に動物写真が並ぶ構造。
- `<table>` ベースではないため `SinglePageTableAdapter` の既定 `td/th`
  実装ではなく、`extract_animal_details` をオーバーライドし dt/dd と
  サイト名から RawAnimalData を構築する。
- 動物種別 (犬/猫) はサイト名から推定する。
"""

from __future__ import annotations

from typing import ClassVar

from bs4 import Tag

from ....domain.models import RawAnimalData
from ...municipality_adapter import ParsingError
from ..registry import SiteAdapterRegistry
from ..single_page_table import SinglePageTableAdapter


class CityHiroshimaAdapter(SinglePageTableAdapter):
    """広島市 飼い主不明犬・猫一覧用 rule-based adapter

    1 ページ 1 動物の single_page 形式。`<div id="voice"> <dl>` を
    単一の「行」として扱い、`<dt>` ラベルを正規化キーにマッピングする。
    """

    # 動物 1 件 = 本文 dl 1 つ。`<div id="voice">` 配下を限定対象にして
    # 関連リンクなど別 dl が紛れた将来変更にも追従しやすくする。
    ROW_SELECTOR: ClassVar[str] = "div#voice dl"
    # ヘッダ行に相当する dl は無いので除外しない
    SKIP_FIRST_ROW: ClassVar[bool] = False
    # 基底の td/th ベース既定実装は使わないため空辞書を明示
    COLUMN_FIELDS: ClassVar[dict[int, str]] = {}
    LOCATION_COLUMN: ClassVar[int | None] = None
    # 収容日は dt "収容月日" から取得するためデフォルトは空
    SHELTER_DATE_DEFAULT: ClassVar[str] = ""

    # `<dt>` テキスト -> RawAnimalData フィールド名 のマッピング。
    # 表記揺れに備えキー側でゆるくマッチさせる。
    _DT_LABEL_MAP: ClassVar[dict[str, str]] = {
        "収容月日": "shelter_date",
        "収容日": "shelter_date",
        "種類": "species_breed",  # 犬種 / 猫種 (species 本体ではない)
        "犬種": "species_breed",
        "猫種": "species_breed",
        "推定年齢": "age",
        "年齢": "age",
        "毛色": "color",
        "色": "color",
        "性別": "sex",
        "拾得等の場所": "location",
        "保護等の場所": "location",
        "発見場所": "location",
        "場所": "location",
    }

    # ─────────────────── オーバーライド ───────────────────

    def extract_animal_details(
        self, virtual_url: str, category: str = "lost"
    ) -> RawAnimalData:
        """`<dl>` (= 動物 1 件) から RawAnimalData を構築する"""
        rows = self._load_rows()
        idx = self._parse_row_index(virtual_url)
        if idx >= len(rows):
            raise ParsingError(
                f"row index {idx} out of range (total {len(rows)})",
                url=virtual_url,
            )
        dl = rows[idx]

        # <dt> / <dd> をペアで走査
        fields: dict[str, str] = {}
        dts = dl.find_all("dt", recursive=False)
        dds = dl.find_all("dd", recursive=False)
        # recursive=False でも構造によっては 0 件になることがあるためフォールバック
        if not dts:
            dts = dl.find_all("dt")
            dds = dl.find_all("dd")
        for dt, dd in zip(dts, dds):
            label = dt.get_text(strip=True)
            value = dd.get_text(separator=" ", strip=True)
            key = self._DT_LABEL_MAP.get(label)
            if key:
                fields[key] = value

        # サイト名から動物種別 (犬/猫) を推定。dt "種類" 等は犬種扱い。
        species = self._infer_species_from_site_name(self.site_config.name)

        try:
            return RawAnimalData(
                species=species,
                sex=fields.get("sex", ""),
                age=fields.get("age", ""),
                color=fields.get("color", ""),
                size="",
                shelter_date=fields.get("shelter_date", self.SHELTER_DATE_DEFAULT),
                location=fields.get("location", ""),
                phone="",
                image_urls=self._extract_animal_images(dl, virtual_url),
                source_url=virtual_url,
                category=category,
            )
        except Exception as e:
            raise ParsingError(
                f"RawAnimalData バリデーション失敗: {e}", url=virtual_url
            ) from e

    # ─────────────────── ヘルパー ───────────────────

    def _extract_animal_images(self, dl: Tag, base_url: str) -> list[str]:
        """動物写真用 img の URL を抽出する

        広島市テンプレートでは動物写真は `<dl>` の直前に
        `<p class="imagecenter"><img .../></p>` として並ぶため、
        `dl` 自身ではなく親 (`<div id="voice">`) の `p.imagecenter` 内
        img を対象にする。SNS / 新規ウィンドウアイコンなどの装飾は
        この CSS クラスに含まれないため安全に除外できる。
        """
        urls: list[str] = []
        parent = dl.parent
        if parent is not None:
            for img in parent.select("p.imagecenter img"):
                src = img.get("src")
                if src and isinstance(src, str):
                    urls.append(self._absolute_url(src, base=base_url))
        # `_filter_image_urls` は wp-content/uploads パターン前提で
        # 広島市では一致しないため、ここでは生リストを返す。
        return urls

    @staticmethod
    def _infer_species_from_site_name(name: str) -> str:
        """サイト名から動物種別 (犬/猫) を推定する"""
        if "犬" in name:
            return "犬"
        if "猫" in name:
            return "猫"
        return "その他"


# ─────────────────── サイト登録 ───────────────────
# 同一テンプレート上で運用される 2 サイトを同一 adapter にマップする。
for _site_name in (
    "広島市（迷子犬）",
    "広島市（迷子猫）",
):
    SiteAdapterRegistry.register(_site_name, CityHiroshimaAdapter)
