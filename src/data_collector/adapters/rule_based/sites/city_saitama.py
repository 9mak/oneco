"""さいたま市動物愛護ふれあいセンター rule-based adapter

対象ドメイン: https://www.city.saitama.lg.jp/008/004/003/004/

特徴:
- 同一テンプレート上で 2 サイト (保護犬 / 保護猫・その他) を運用しており、
  URL のページ番号のみが異なる:
    - .../p003138.html  (保護犬)
    - .../p019971.html  (保護猫・その他)
- 1 ページに `div.wysiwyg_area > div` 形式で動物カードが並ぶ single_page サイト。
  個別 detail ページは存在しないため一覧ページから直接抽出する。
- 各動物カードは `div.wysiwyg_area > div` 配下で次のような並びで表現される:
    <div>
      <p>管理番号 R07-XXX</p>
      <p><img src="..."><br />写真の無断転載はご遠慮ください。</p>
      <ul>
        <li><strong>収容日： </strong>令和8年5月10日</li>
        <li><strong>公示（掲載）期限： </strong>令和8年5月15日</li>
        <li><strong>収容場所： </strong>さいたま市浦和区...</li>
        <li><strong>種類： </strong>柴犬</li>
        <li><strong>毛色： </strong>茶</li>
        <li><strong>性別： </strong>オス</li>
        <li><strong>体格： </strong>中</li>
        <li><strong>推定年齢： </strong>3歳</li>
        <li><strong>首輪： </strong>あり</li>
        <li><strong>備考：</strong></li>
      </ul>
    </div>
- 在庫 0 件のときも 1 つだけ「テンプレート (空欄) のカード」が残る運用なので、
  全フィールドが空のカードは在庫 0 件のプレースホルダとして除外する。
- 動物種別はサイト名から推定する (HTML 中の「種類」は具体的な犬種・猫種が入る)。
"""

from __future__ import annotations

from typing import ClassVar

from bs4 import Tag

from ....domain.models import RawAnimalData
from ...municipality_adapter import ParsingError
from ..registry import SiteAdapterRegistry
from ..single_page_table import SinglePageTableAdapter


class CitySaitamaAdapter(SinglePageTableAdapter):
    """さいたま市動物愛護ふれあいセンター用 rule-based adapter

    保護犬 / 保護猫・その他 の 2 サイトで共通テンプレートを使用する。
    各動物は `div.wysiwyg_area > div` カード (管理番号 + 画像 + ラベル付き
    `<ul>`) で表現される single_page 形式。
    """

    # 動物カード候補となる `<div>` 群。`div.wysiwyg_area` の直下にある
    # `<div>` のみを対象とし、`<ul>` を内包するもの (= 属性リストを持つ)
    # を `_load_rows` でさらに絞り込む。
    ROW_SELECTOR: ClassVar[str] = "div.wysiwyg_area > div"
    SKIP_FIRST_ROW: ClassVar[bool] = False
    # 属性 `<ul>` 内のラベル → RawAnimalData フィールド名 マッピング。
    # 基底の cells ベース既定実装は使わないが、契約として明示する。
    COLUMN_FIELDS: ClassVar[dict[int, str]] = {
        0: "shelter_date",  # 収容日
        1: "location",      # 収容場所 (公示期限を挟むため位置は参考値)
        2: "species",       # 種類
        3: "color",          # 毛色
        4: "sex",            # 性別
        5: "size",           # 体格
        6: "age",            # 推定年齢
    }
    LOCATION_COLUMN: ClassVar[int | None] = 1
    SHELTER_DATE_DEFAULT: ClassVar[str] = ""

    # `<li><strong>ラベル：</strong>値</li>` のラベル → フィールド名
    _LABEL_TO_FIELD: ClassVar[dict[str, str]] = {
        "収容日": "shelter_date",
        "収容場所": "location",
        "種類": "species",
        "毛色": "color",
        "性別": "sex",
        "体格": "size",
        "推定年齢": "age",
        "首輪": "collar",
        "備考": "remarks",
        "公示（掲載）期限": "notice_deadline",
    }

    # ─────────────────── オーバーライド ───────────────────

    def _load_rows(self) -> list[Tag]:
        """`div.wysiwyg_area > div` のうち、属性 `<ul>` を持つカードに限定する

        基底実装が拾う `<div>` には地図情報ブロックや関連リンクブロック等の
        無関係な要素も含まれるため、ここで「`管理番号` を含む `<p>` と
        `<ul>` の双方を持つ」要素のみを動物カードとして残す。
        さらに、全フィールドが空欄のテンプレート (= 在庫 0 件) は除外する。
        """
        if self._rows_cache is not None:
            return self._rows_cache

        rows = super()._load_rows()
        animal_cards: list[Tag] = []
        for row in rows:
            if not isinstance(row, Tag):
                continue
            if not self._is_animal_card(row):
                continue
            if self._is_empty_template(row):
                continue
            animal_cards.append(row)
        self._rows_cache = animal_cards
        return animal_cards

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        """テンプレートのみ (在庫 0 件) のときは空リストを返す

        基底実装は「行が 0 = ParsingError」だが、本サイトでは在庫 0 件でも
        テンプレート的なカードが 1 つ残るため、`_load_rows` のフィルタ後に
        0 件であれば例外なく空リストを返す。テンプレート自体が消失した
        (`<div class="wysiwyg_area">` が無い) 場合も空リスト扱いとする。
        """
        return [
            (f"{self.site_config.list_url}#row={i}", self.site_config.category)
            for i in range(len(self._load_rows()))
        ]

    def extract_animal_details(
        self, virtual_url: str, category: str = "adoption"
    ) -> RawAnimalData:
        """動物カード `<div>` から RawAnimalData を構築する

        基底の `td/th` ベース実装ではなく、内部 `<ul>` の各 `<li>` を
        「ラベル：値」としてパースする。
        """
        rows = self._load_rows()
        idx = self._parse_row_index(virtual_url)
        if idx >= len(rows):
            raise ParsingError(
                f"row index {idx} out of range (total {len(rows)})",
                url=virtual_url,
            )
        card = rows[idx]

        fields = self._parse_card_fields(card)

        # 動物種別は HTML の「種類」(柴犬/雑種等) ではなくサイト名から推定する
        species = self._infer_species_from_site_name(self.site_config.name)

        try:
            return RawAnimalData(
                species=species,
                sex=fields.get("sex", ""),
                age=fields.get("age", ""),
                color=fields.get("color", ""),
                size=fields.get("size", ""),
                shelter_date=fields.get("shelter_date", self.SHELTER_DATE_DEFAULT),
                location=fields.get("location", ""),
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

    @staticmethod
    def _is_animal_card(div: Tag) -> bool:
        """動物カード相当の `<div>` かを判定 (管理番号 `<p>` と `<ul>` を持つ)"""
        if div.find("ul") is None:
            return False
        for p in div.find_all("p"):
            if "管理番号" in p.get_text(strip=True):
                return True
        return False

    @classmethod
    def _is_empty_template(cls, div: Tag) -> bool:
        """全フィールドが空のテンプレートカードかを判定 (= 在庫 0 件)

        管理番号値 (R07- に続く番号) が空、かつ属性 `<ul>` の全 `<li>` の値部
        (ラベル「：」より右側) が空のとき True。
        """
        # 管理番号値の空判定
        kanri_value = ""
        for p in div.find_all("p"):
            text = p.get_text(strip=True)
            if "管理番号" in text:
                # "管理番号 R07-XXX" → "R07-XXX" の後ろ部分を抽出
                _, _, rest = text.partition("管理番号")
                rest = rest.strip()
                # ハイフンの後に続く番号があるか
                if "-" in rest:
                    _, _, after_hyphen = rest.rpartition("-")
                    kanri_value = after_hyphen.strip()
                else:
                    kanri_value = rest.strip()
                break
        if kanri_value:
            return False

        # 属性 <ul> の値部すべてが空か
        ul = div.find("ul")
        if ul is None:
            return True
        for li in ul.find_all("li"):
            value = cls._extract_li_value(li)
            if value:
                return False
        return True

    @staticmethod
    def _extract_li_value(li: Tag) -> str:
        """`<li><strong>ラベル： </strong>値</li>` の値部を取り出す"""
        # `<strong>` を除いた残りのテキストが値
        # get_text 全体からラベル＋区切り文字を取り除く戦略を採用する
        full_text = li.get_text(separator=" ", strip=True)
        strong = li.find("strong")
        label_text = strong.get_text(strip=True) if isinstance(strong, Tag) else ""
        if label_text and full_text.startswith(label_text):
            value = full_text[len(label_text):].strip()
        else:
            value = full_text
        # ラベル末尾の「：」「:」が値の先頭に残った場合を除去
        for sep in ("：", ":"):
            if value.startswith(sep):
                value = value[len(sep):].strip()
        return value

    @classmethod
    def _parse_card_fields(cls, card: Tag) -> dict[str, str]:
        """カード内 `<ul>` から `{field_name: value}` を構築"""
        fields: dict[str, str] = {}
        ul = card.find("ul")
        if ul is None:
            return fields
        for li in ul.find_all("li"):
            strong = li.find("strong")
            if not isinstance(strong, Tag):
                continue
            label_raw = strong.get_text(strip=True)
            # ラベル末尾の「：」「:」を取り除く
            label = label_raw
            for sep in ("：", ":"):
                if label.endswith(sep):
                    label = label[: -len(sep)].strip()
                    break
            field = cls._LABEL_TO_FIELD.get(label)
            if not field:
                continue
            value = cls._extract_li_value(li)
            if value and field not in fields:
                fields[field] = value
        return fields

    @staticmethod
    def _infer_species_from_site_name(name: str) -> str:
        """サイト名から動物種別 (犬/猫/その他) を推定する"""
        if "犬" in name:
            return "犬"
        if "猫" in name:
            return "猫"
        return "その他"


# ─────────────────── サイト登録 ───────────────────
# 同一テンプレート上で運用される 2 サイトを同一 adapter にマップする。
for _site_name in (
    "さいたま市（保護犬）",
    "さいたま市（保護猫・その他）",
):
    SiteAdapterRegistry.register(_site_name, CitySaitamaAdapter)
