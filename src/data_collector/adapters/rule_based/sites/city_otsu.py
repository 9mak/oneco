"""大津市動物愛護センター rule-based adapter

対象ドメイン: https://www.city.otsu.lg.jp/soshiki/021/1442/g/pet/mayoi/

特徴:
- 1 サイト ("大津市動物愛護センター（迷い犬猫）") のみ運用される
  single_page 形式。1 ページに迷い犬・迷い猫の情報が `<table>` でまとまる。
- テーブル構造 (1 行 = 1 頭):
    <table>
      <caption>迷い犬猫情報</caption>
      <thead><tr>
        <th>種類</th><th>毛色</th><th>体格</th><th>性別</th>
        <th>保護場所</th><th>保護日時</th><th>備考</th>
      </tr></thead>
      <tbody>
        <tr>
          <td>{種類}</td><td>{毛色}</td><td>{体格}</td><td>{性別}</td>
          <td>{保護場所}</td><td>{保護日時}</td><td>{備考}</td>
        </tr>
      </tbody>
    </table>
- 在庫 0 件の場合 (本フィクスチャがこのケース):
    - 本文上部に `<h3>現在収容している犬猫の情報はありません。</h3>` が出る
    - テーブルは存在するが `<tbody>` に空セル (`&nbsp;`) のみのプレースホルダ
      行が 1 つだけ入り、保護日時列にはテンプレ文字 ("月　日"/"時　分") が残る
  この状態は ParsingError ではなく "0 件" として扱い、
  `fetch_animal_list` は空リストを返す。
- 動物種別 (犬/猫) は HTML の「種類」列の値が具体名 (柴犬等) のため
  サイト名 ("迷い犬猫") から推定する。「犬猫」併用サイトのため "その他"
  扱い (越谷市の "個人保護犬猫" と同じ方針)。
- 大津市ページは fixture 化される際に二重 UTF-8 mojibake
  (本来 UTF-8 のバイト列を Latin-1 として解釈してから再度 UTF-8 として
  保存) になるため、HTML キャッシュ取得時に逆変換を試みる。
- category は sites.yaml で "lost" (迷い動物) と指定される。
"""

from __future__ import annotations

import re
from typing import ClassVar

from bs4 import BeautifulSoup, Tag

from ....domain.models import RawAnimalData
from ...municipality_adapter import ParsingError
from ..registry import SiteAdapterRegistry
from ..single_page_table import SinglePageTableAdapter

# 「現在収容している犬猫の情報はありません。」等の 0 件告知パターン。
# 「現在」+ 「(収容|情報)」+ 「ありません」程度の表記揺れを緩く吸収する。
_EMPTY_STATE_PATTERN = re.compile(r"現在[^。]*?(?:収容|情報)[^。]*?ありません")

# プレースホルダ行の保護日時列に残る固定文言 (本フィクスチャでは
# "月　日" / "時　分" のように数字が空の状態で出る)
_DATE_PLACEHOLDER_TOKENS = ("月　日", "時　分", "月 日", "時 分")


class CityOtsuAdapter(SinglePageTableAdapter):
    """大津市動物愛護センター用 rule-based adapter

    迷い犬猫の単一サイト。`<table>` 内 `<tbody><tr>` を 1 動物として扱う
    single_page 形式。在庫 0 件は告知 `<h3>` + 空プレースホルダ行で表現
    されるため、`fetch_animal_list` 側で 0 件状態を正常終了として扱う。
    """

    # 本文の `div.wysiwyg` 配下のテーブル `<tbody><tr>` のみを候補とする。
    # ページ内に他テーブルが追加された場合に備えてスコープを限定する。
    ROW_SELECTOR: ClassVar[str] = "div.wysiwyg table tbody tr"
    # `<tbody>` 内のため、ヘッダ (`<thead><tr>`) は最初から含まれない
    SKIP_FIRST_ROW: ClassVar[bool] = False
    # 列インデックス → RawAnimalData フィールド名 のマッピング。
    # 値の取り出しは `extract_animal_details` のオーバーライドが行うが、
    # 契約として明示する。
    COLUMN_FIELDS: ClassVar[dict[int, str]] = {
        0: "species_detail",  # 種類 (柴犬等の具体名 / サイト名から推定するため未使用)
        1: "color",  # 毛色
        2: "size",  # 体格
        3: "sex",  # 性別
        4: "location",  # 保護場所
        5: "shelter_date",  # 保護日時
        6: "features",  # 備考
    }
    LOCATION_COLUMN: ClassVar[int | None] = 4
    SHELTER_DATE_DEFAULT: ClassVar[str] = ""

    # ─────────────────── オーバーライド ───────────────────

    def _load_rows(self) -> list[Tag]:
        """list_url の HTML を取得し、二重 UTF-8 mojibake を補正してから行を抽出"""
        if self._rows_cache is not None:
            return self._rows_cache

        if self._html_cache is None:
            self._html_cache = self._http_get(self.site_config.list_url)

        html = self._html_cache
        # mojibake 検出: ページに「大津」が含まれない場合は
        # latin-1 → utf-8 の逆変換を試みる。失敗したら元のまま。
        if "大津" not in html:
            try:
                html = html.encode("latin-1").decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass

        # 復元後の HTML をキャッシュに反映 (extract_animal_details で
        # 同じ HTML を再利用できるようにするため)
        self._html_cache = html

        soup = BeautifulSoup(html, "html.parser")
        rows = soup.select(self.ROW_SELECTOR)
        rows = [r for r in rows if isinstance(r, Tag)]
        if self.SKIP_FIRST_ROW and rows:
            rows = rows[1:]
        self._rows_cache = rows
        return rows

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        """テーブル行を仮想 URL に変換する

        0 件状態 (告知見出し + 空プレースホルダ行) は空リストを返す。
        テーブル自体が存在しない場合のみ ParsingError。
        """
        rows = self._load_rows()
        if not rows:
            # `<tbody>` の `<tr>` が一切無い = テーブル不在。
            # 「情報はありません」告知だけはあってテーブル丸ごと無いケース
            # も 0 件として許容する。
            if self._html_cache and (
                _EMPTY_STATE_PATTERN.search(self._html_cache)
                or "情報はありません" in self._html_cache
            ):
                return []
            raise ParsingError(
                "行要素が見つかりません",
                selector=self.ROW_SELECTOR,
                url=self.site_config.list_url,
            )

        # プレースホルダ行を除外したものが実データ行
        data_rows = [r for r in rows if not self._is_empty_placeholder(r)]
        category = self.site_config.category
        return [(f"{self.site_config.list_url}#row={i}", category) for i in range(len(data_rows))]

    def extract_animal_details(self, virtual_url: str, category: str = "lost") -> RawAnimalData:
        """テーブル行から RawAnimalData を構築する

        基底のセルベース既定実装に対し、`<p>` で複数行に分かれている
        セル (保護日時等) のテキスト整形と species のサイト名推定を加える。
        """
        rows = [r for r in self._load_rows() if not self._is_empty_placeholder(r)]
        idx = self._parse_row_index(virtual_url)
        if idx >= len(rows):
            raise ParsingError(
                f"row index {idx} out of range (total {len(rows)})",
                url=virtual_url,
            )
        row = rows[idx]
        cells = [c for c in row.find_all(["td", "th"]) if isinstance(c, Tag)]

        def _cell_text(i: int) -> str:
            if i >= len(cells):
                return ""
            text = cells[i].get_text(separator=" ", strip=True)
            # `&nbsp;` ( ) や全半角スペースのみは空扱い
            if not text.replace(" ", "").strip():
                return ""
            # 連続スペース/全角スペースを 1 つに正規化
            return re.sub(r"[  　]+", " ", text).strip()

        color = _cell_text(1)
        size = _cell_text(2)
        sex = _cell_text(3)
        location = _cell_text(4)
        shelter_date = _cell_text(5) or self.SHELTER_DATE_DEFAULT

        # 動物種別: HTML の「種類」(柴犬等) は具体名のためサイト名から推定。
        # サイト名は "大津市動物愛護センター（迷い犬猫）" で犬猫いずれもありうる
        # ため "その他" 扱い (越谷市 "個人保護犬猫" と同じ方針)。
        species = self._infer_species_from_site_name(self.site_config.name)

        try:
            return RawAnimalData(
                species=species,
                sex=sex,
                age="",
                color=color,
                size=size,
                shelter_date=shelter_date,
                location=location,
                phone="",
                image_urls=self._extract_row_images(row, virtual_url),
                source_url=virtual_url,
                category=category,
            )
        except Exception as e:
            raise ParsingError(f"RawAnimalData バリデーション失敗: {e}", url=virtual_url) from e

    # ─────────────────── ヘルパー ───────────────────

    @staticmethod
    def _is_empty_placeholder(row: Tag) -> bool:
        """0 件時のプレースホルダ行 (全セル空 + 日時テンプレ文字のみ) かを判定

        - データセル (種類/毛色/体格/性別/保護場所/備考) がすべて空白扱い
        - 保護日時列も "月　日"/"時　分" 等のテンプレ文字のみ
        の場合に True を返す。1 つでも実データを含むセルがあれば False。
        """
        cells = [c for c in row.find_all(["td", "th"]) if isinstance(c, Tag)]
        if not cells:
            return True
        for c in cells:
            text = c.get_text(separator="", strip=True).replace(" ", "").strip()
            if not text:
                continue
            # 日時列のテンプレ文字 ("月　日" 等) は空扱い
            normalized = text.replace("　", "").replace(" ", "")
            placeholder_only = all(ch in "月日時分" for ch in normalized) and normalized != ""
            if placeholder_only:
                continue
            # ここに到達した = 実データを含むセルがある
            return False
        return True

    @staticmethod
    def _infer_species_from_site_name(name: str) -> str:
        """サイト名から動物種別 (犬/猫/その他) を推定する

        - "犬猫" を含む → "その他" (犬猫いずれもありうる)
        - "犬" のみ → "犬"
        - "猫" のみ → "猫"
        - いずれにも該当しない → "" (空文字)
        """
        if "犬猫" in name:
            return "その他"
        if "犬" in name:
            return "犬"
        if "猫" in name:
            return "猫"
        return ""


# ─────────────────── サイト登録 ───────────────────
# sites.yaml で定義される 1 サイトを登録する。
if SiteAdapterRegistry.get("大津市動物愛護センター（迷い犬猫）") is None:
    SiteAdapterRegistry.register("大津市動物愛護センター（迷い犬猫）", CityOtsuAdapter)
