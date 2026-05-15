"""鹿児島市保健所 rule-based adapter

対象ドメイン: https://www.city.kagoshima.lg.jp/.../joho/{inu|neko}.html

特徴:
- 同一テンプレート上で 2 サイト (保護犬 / 保護猫) を運用しており、
  URL パターンのみが異なる:
    - .../joho/inu.html  (保護犬)
    - .../joho/neko.html (保護猫)
- 1 ページに `<h2>No.XXX</h2>` + 直後の `<p>` 群が 1 頭分という構造で
  並ぶ single_page サイト。個別 detail ページは存在しない。
- 各動物ブロックの構造 (例):
    <h2>No.260009</h2>
    <p><img alt="..." src="..."/>保護日：令和8年4月30日（木曜日）</p>
    <p>保護期限：令和8年5月13日（水曜日）</p>
    <p>保護場所：光山二丁目</p>
    <p>種類：雑種</p>
    <p>性別：雄</p>
    <p>体格：小</p>
    <p>推定年齢：10歳</p>
    <p>首輪他：青色首輪、青リード付</p>
- h2 タイトル自体が「（飼い主の元に戻りました。）」のような注記を含む場合は
  既に返還済みであり、現役の保護動物としては扱わない (除外)。
- 在庫 0 件 (該当 h2 が無い) の場合は `fetch_animal_list` から空リストを
  返し、ParsingError は出さない (`<h1>` のみのテンプレート表示状態を
  正常な 0 件として許容)。
- 動物種別 (犬/猫) はサイト名から推定する (HTML の「種類」列は犬種等の
  具体名のため species への直接利用は不適切)。
"""

from __future__ import annotations

import re
from typing import ClassVar

from bs4 import BeautifulSoup, Tag

from ....domain.models import RawAnimalData
from ...municipality_adapter import ParsingError
from ..registry import SiteAdapterRegistry
from ..single_page_table import SinglePageTableAdapter

# 「No.XXXXXX」を含む h2 のみを動物ブロックの先頭とみなすパターン。
# 「お問い合わせ」等のセクション見出しを誤検出しないためのガード。
_ANIMAL_H2_RE = re.compile(r"No\.?\s*\d+", re.IGNORECASE)

# h2 タイトルに含まれる「飼い主の元に戻りました」(返還済み) を検出するパターン。
# 半角/全角括弧の揺れに耐える形にする。
_RETURNED_RE = re.compile(r"飼い主.*戻り")


class CityKagoshimaAdapter(SinglePageTableAdapter):
    """鹿児島市保健所 (生活衛生課) 用 rule-based adapter

    保護犬 / 保護猫 の 2 サイトで共通テンプレートを使用する。
    `<h2>No.XXX</h2>` + 直後の `<p>` 群を 1 頭分のブロックとして抽出する
    single_page 形式。
    """

    # 動物ブロックの先頭となる h2 をセレクタとして指定。
    # 実際のグルーピング (h2 + 直後 p 群) は `_load_rows` を完全置換する
    # 形で実現する (基底の cells ベース既定実装は使わない)。
    ROW_SELECTOR: ClassVar[str] = "h2"
    # h2 自体は「No.XXX」かどうかでフィルタするため SKIP_FIRST_ROW は不要。
    SKIP_FIRST_ROW: ClassVar[bool] = False
    # COLUMN_FIELDS は `<p>` ラベル方式で抽出するため空 (既定実装は使わない)。
    COLUMN_FIELDS: ClassVar[dict[int, str]] = {}
    LOCATION_COLUMN: ClassVar[int | None] = None
    SHELTER_DATE_DEFAULT: ClassVar[str] = ""

    # `<p>` ラベルから RawAnimalData フィールドへのマッピング。
    # 鹿児島市は「ラベル：値」形式で全角コロン区切りで記載されている。
    # キーは label の prefix 一致 (substring) で判定する。
    _LABEL_TO_FIELD: ClassVar[dict[str, str]] = {
        "保護日": "shelter_date",
        "保護場所": "location",
        # 「種類」は犬種名なので species ではなく size 等とは無関係。
        # RawAnimalData の species はサイト名から推定するため、
        # 「種類」ラベルは抽出しても使わない (将来 detail 拡張用)。
        "性別": "sex",
        "体格": "size",
        "推定年齢": "age",
    }

    # 性別表記の正規化マップ (鹿児島市は「雄/雌」表記)。
    _SEX_MAP: ClassVar[dict[str, str]] = {
        "雄": "オス",
        "雌": "メス",
    }

    # ─────────────────── オーバーライド ───────────────────

    def _load_rows(self) -> list[Tag]:
        """`<h2>No.XXX</h2>` で始まる動物ブロックの h2 だけをキャッシュする

        基底実装は `select(ROW_SELECTOR)` の結果を返すが、本サイトでは
        以下の追加フィルタが必要:
        - h2 のうち「No.XXX」を含むものだけを動物ブロックの起点とみなす
        - h2 タイトルが「飼い主の元に戻りました」を含む (返還済み) は除外
        """
        if self._rows_cache is not None:
            return self._rows_cache

        if self._html_cache is None:
            self._html_cache = self._http_get(self.site_config.list_url)

        soup = BeautifulSoup(self._html_cache, "html.parser")
        # 本文コンテナに限定 (フッタ/サイドバーの h2 を除外)。
        # `#tmp_contents` が無いケースに備えて document 全体にもフォールバック。
        scope = soup.select_one("#tmp_contents") or soup
        rows: list[Tag] = []
        for h2 in scope.find_all("h2"):
            if not isinstance(h2, Tag):
                continue
            title = h2.get_text(separator=" ", strip=True)
            if not _ANIMAL_H2_RE.search(title):
                continue
            if _RETURNED_RE.search(title):
                # 返還済みは「現役の保護動物」ではないので除外
                continue
            rows.append(h2)
        self._rows_cache = rows
        return rows

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        """h2 (No.XXX) をベースに仮想 URL リストを返す

        在庫 0 件 (該当 h2 が無い) の場合は空リストを返し、ParsingError は
        出さない。実サイトでは保護動物が居ない期間も平常運用される。
        """
        rows = self._load_rows()
        category = self.site_config.category
        return [(f"{self.site_config.list_url}#row={i}", category) for i in range(len(rows))]

    def extract_animal_details(
        self, virtual_url: str, category: str = "sheltered"
    ) -> RawAnimalData:
        """1 動物ブロック (h2 + 直後 p 群) から RawAnimalData を構築する"""
        rows = self._load_rows()
        idx = self._parse_row_index(virtual_url)
        if idx >= len(rows):
            raise ParsingError(
                f"row index {idx} out of range (total {len(rows)})",
                url=virtual_url,
            )
        h2 = rows[idx]
        block_paragraphs = self._collect_block_paragraphs(h2)

        fields: dict[str, str] = {}
        image_urls: list[str] = []
        for p in block_paragraphs:
            # ブロック内の画像も一緒に拾う
            for img in p.find_all("img"):
                src = img.get("src")
                if src and isinstance(src, str):
                    image_urls.append(self._absolute_url(src, base=virtual_url))
            text = p.get_text(separator=" ", strip=True)
            if not text:
                continue
            label, value = self._split_label_value(text)
            if not label:
                continue
            field_name = self._LABEL_TO_FIELD.get(label)
            if field_name and field_name not in fields:
                fields[field_name] = value

        # 動物種別 (犬/猫) はサイト名から推定 (HTML の「種類」は犬種名)
        species = self._infer_species_from_site_name(self.site_config.name)

        sex = self._normalize_sex(fields.get("sex", ""))

        try:
            return RawAnimalData(
                species=species,
                sex=sex,
                age=fields.get("age", ""),
                color="",  # 鹿児島市の HTML には毛色項目が無い
                size=fields.get("size", ""),
                shelter_date=fields.get("shelter_date", self.SHELTER_DATE_DEFAULT),
                location=fields.get("location", ""),
                phone="",
                image_urls=self._filter_image_urls(image_urls, virtual_url),
                source_url=virtual_url,
                category=category,
            )
        except Exception as e:
            raise ParsingError(f"RawAnimalData バリデーション失敗: {e}", url=virtual_url) from e

    # ─────────────────── ヘルパー ───────────────────

    @staticmethod
    def _collect_block_paragraphs(h2: Tag) -> list[Tag]:
        """`<h2>` の直後から次の `<h2>` までの `<p>` を集める

        鹿児島市の本文は `<h2>` を区切り文字として「動物ブロック」が並ぶ
        フラットな構造になっている (子要素ではなく兄弟関係)。
        """
        paragraphs: list[Tag] = []
        for sibling in h2.find_next_siblings():
            if not isinstance(sibling, Tag):
                continue
            if sibling.name == "h2":
                break
            if sibling.name == "p":
                paragraphs.append(sibling)
            else:
                # `<div>` や `<ul>` 配下に潜る p も拾う (将来のレイアウト変更耐性)
                for nested in sibling.find_all("p"):
                    if isinstance(nested, Tag):
                        paragraphs.append(nested)
        return paragraphs

    @staticmethod
    def _split_label_value(text: str) -> tuple[str, str]:
        """「ラベル：値」「ラベル:値」形式を (label, value) に分割

        鹿児島市は全角コロン (U+FF1A) が標準だが、半角コロンにも対応する。
        ラベル区切りが見つからない場合は ("", text) を返す。
        """
        for sep in ("：", ":"):
            if sep in text:
                label, value = text.split(sep, 1)
                return label.strip(), value.strip()
        return "", text.strip()

    @classmethod
    def _normalize_sex(cls, raw_sex: str) -> str:
        """「雄/雌」→ 「オス/メス」、それ以外は元の値をそのまま返す"""
        if not raw_sex:
            return ""
        for src, dst in cls._SEX_MAP.items():
            if src in raw_sex:
                return dst
        return raw_sex

    @staticmethod
    def _infer_species_from_site_name(name: str) -> str:
        """サイト名 ("鹿児島市（保護犬）" 等) から動物種別を推定する"""
        if "犬" in name:
            return "犬"
        if "猫" in name:
            return "猫"
        return "その他"


# ─────────────────── サイト登録 ───────────────────
# 同一テンプレート上で運用される 2 サイトを同一 adapter にマップする。
for _site_name in (
    "鹿児島市（保護犬）",
    "鹿児島市（保護猫）",
):
    if SiteAdapterRegistry.get(_site_name) is None:
        SiteAdapterRegistry.register(_site_name, CityKagoshimaAdapter)
