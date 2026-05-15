"""松山市 はぴまるの丘（松山市動物愛護センター） rule-based adapter

対象ドメイン: https://www.city.matsuyama.ehime.jp/kurashi/kurashi/aigo/index.html

特徴:
- single_page 形式の 1 サイトで犬・猫を同一ページに掲載する。
- 個別 detail ページは存在せず、トップ HTML 内のスライダー UI に
  動物 1 頭ずつが ``<li>`` として並ぶ:

    <div class="aigo_sec05 aigo_wp_over">  ← 犬セクション
      <ul class="slider02" id="slick02">
        <li>
          <span class="movie_slider_img">
            <img src="index.images/inu.R7No.310ver3.jpg" alt="R7No.310">
          </span>
          <span class="movie_slider_text">新しい飼い主募集中</span>
        </li>
        ...
      </ul>
    </div>

    <div class="aigo_sec06 aigo_wp_over">  ← 猫セクション
      <ul class="slider03" id="slick03">
        <li> ... </li>
      </ul>
    </div>

- HTML には収容日・性別・毛色・体格などは記載されておらず、
  画像 alt の収容番号 (例: ``R7No.310`` / ``R8.No.29-30``) と
  ``movie_slider_text`` の状態 (例: ``新しい飼い主募集中`` /
  ``マッチング予約不可``) のみが取得できる。
- 詳細問い合わせ用の電話番号 ``089-923-9435`` は HTML 本文に固定で記載
  されているため、phone はサイト共通定数として埋める。
- 種別 (犬/猫) は ``<li>`` の祖先 ``div.aigo_sec05`` / ``div.aigo_sec06``
  で判別する。
- 0 件状態 (スライダー ``<li>`` が無い) は ``fetch_animal_list`` から
  空リストを返す (``ParsingError`` は出さない)。
"""

from __future__ import annotations

from typing import ClassVar

from bs4 import Tag

from ....domain.models import RawAnimalData
from ...municipality_adapter import ParsingError
from ..registry import SiteAdapterRegistry
from ..single_page_table import SinglePageTableAdapter

# 松山市動物愛護センター（はぴまるの丘）共通の問い合わせ先
_MATSUYAMA_CENTER_PHONE: str = "089-923-9435"


class CityMatsuyamaAdapter(SinglePageTableAdapter):
    """松山市 はぴまるの丘（収容中）用 rule-based adapter

    1 ページ内の犬セクション (``aigo_sec05``) と猫セクション (``aigo_sec06``)
    の両方からスライダー ``<li>`` を抽出する single_page 形式。
    """

    # 犬と猫の両セクションのスライダー <li> を順に拾う。
    # CSS セレクタの並び (犬→猫) が ``fetch_animal_list`` の出力順序になる。
    ROW_SELECTOR: ClassVar[str] = "div.aigo_sec05 ul#slick02 > li, div.aigo_sec06 ul#slick03 > li"
    # スライダー <li> はヘッダ行を含まないので除外しない
    SKIP_FIRST_ROW: ClassVar[bool] = False
    # td/th ベースの既定実装は使わない (extract_animal_details で完全 override)
    COLUMN_FIELDS: ClassVar[dict[int, str]] = {}
    LOCATION_COLUMN: ClassVar[int | None] = None
    SHELTER_DATE_DEFAULT: ClassVar[str] = ""

    # ─────────────────── MunicipalityAdapter 実装 ───────────────────

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        """スライダー <li> を仮想 URL に変換する

        セクション (犬/猫) が両方とも 0 件の場合は空リストを返す。
        ``aigo_sec05`` / ``aigo_sec06`` セクション自体が存在しないなど
        構造が想定外な場合は ``ParsingError`` を伝播させる (基底実装の
        挙動: 行が無い時に raise) のではなく、本サイトでは 0 件扱いに
        統一して空リストを返す。
        """
        rows = self._load_rows()
        category = self.site_config.category
        return [(f"{self.site_config.list_url}#row={i}", category) for i in range(len(rows))]

    def extract_animal_details(self, virtual_url: str, category: str = "adoption") -> RawAnimalData:
        """スライダー <li> から RawAnimalData を構築する

        - species: 祖先 ``div.aigo_sec05`` (犬) / ``div.aigo_sec06`` (猫) で判別
        - location: 画像 alt の収容番号 (例: ``R7No.310``) + 状態テキストを連結
        - phone: ``_MATSUYAMA_CENTER_PHONE`` を埋め込む
        - shelter_date / sex / color / age / size: HTML に存在しないため空文字
        """
        rows = self._load_rows()
        idx = self._parse_row_index(virtual_url)
        if idx >= len(rows):
            raise ParsingError(
                f"row index {idx} out of range (total {len(rows)})",
                url=virtual_url,
            )
        item = rows[idx]

        species = self._infer_species_from_section(item)

        # 画像 alt = 収容番号 (例: "R7No.310")
        img = item.find("img")
        animal_id = ""
        if isinstance(img, Tag):
            alt = img.get("alt")
            if isinstance(alt, str):
                animal_id = alt.strip()

        # ステータス (例: "新しい飼い主募集中" / "マッチング予約不可")
        status_span = item.select_one("span.movie_slider_text")
        status = status_span.get_text(strip=True) if isinstance(status_span, Tag) else ""

        # location 列に相当する情報が無いため、収容番号 + 状態を埋める。
        # どちらも空ならカード由来のテキスト全体を fallback として使う。
        location_parts = [p for p in (animal_id, status) if p]
        if location_parts:
            location = " ".join(location_parts)
        else:
            location = item.get_text(separator=" ", strip=True)

        try:
            return RawAnimalData(
                species=species,
                sex="",
                age="",
                color="",
                size="",
                shelter_date=self.SHELTER_DATE_DEFAULT,
                location=location,
                phone=self._normalize_phone(_MATSUYAMA_CENTER_PHONE),
                image_urls=self._extract_row_images(item, virtual_url),
                source_url=virtual_url,
                category=category,
            )
        except Exception as e:
            raise ParsingError(f"RawAnimalData バリデーション失敗: {e}", url=virtual_url) from e

    # ─────────────────── ヘルパー ───────────────────

    @staticmethod
    def _infer_species_from_section(item: Tag) -> str:
        """祖先要素の class から species を推定する

        - ``div.aigo_sec05`` 配下 → 犬
        - ``div.aigo_sec06`` 配下 → 猫
        - いずれにも属さない場合 → "その他"
        """
        # find_parent でクラス指定。BeautifulSoup の class_ は完全マッチではなく
        # クラス属性中に該当トークンがあれば真。
        if item.find_parent("div", class_="aigo_sec05") is not None:
            return "犬"
        if item.find_parent("div", class_="aigo_sec06") is not None:
            return "猫"
        return "その他"


# ─────────────────── サイト登録 ───────────────────
# sites.yaml の name と一致させる必要がある (1 サイトのみ)。
SiteAdapterRegistry.register("松山市 はぴまるの丘（収容中）", CityMatsuyamaAdapter)
