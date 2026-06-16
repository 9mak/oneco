"""船橋市動物愛護指導センター rule-based adapter

対象ドメイン: https://www.city.funabashi.lg.jp/kurashi/doubutsu/003/

特徴:
- 同一テンプレート上で 2 サイト (収容犬猫 / 譲渡可能犬猫) を運用しており、
  URL パターンのみが異なる:
    - .../003/p013242.html      (収容犬猫)
    - .../003/joutoindex.html   (譲渡可能犬猫)
- 1 ページに `<table>` 形式で動物情報が並ぶ single_page サイト。
  個別 detail ページは存在しない。
- テーブル構造 (1 行 = 1 頭, ヘッダ行 + データ行 N 件):
    <table style="width: 800; height: 96;">
      <caption>公示内容 ...</caption>
      <tbody>
        <tr> (ヘッダ)
          <th>番号</th><th>収容年月日</th><th>公示満了日</th>
          <th>収容場所</th><th>動物種</th><th>種類</th>
          <th>毛色</th><th>性別</th><th>体格</th><th>備考</th>
          <th>写真</th>
        </tr>
        <tr> (データ行 N 件)
          <td>{番号}</td><td>{収容年月日}</td><td>{公示満了日}</td>
          <td>{収容場所}</td><td>{動物種=犬|猫}</td><td>{種類}</td>
          <td>{毛色}</td><td>{性別}</td><td>{体格}</td><td>{備考}</td>
          <td><img src="..."></td>
        </tr>
      </tbody>
    </table>
- 収容数 0 件のときはテーブルにヘッダ行のみが残る。本 adapter は
  `SKIP_FIRST_ROW=True` でヘッダを除外し、結果として `fetch_animal_list` が
  空リストを返す (ParsingError は出さない)。
- 動物種別は HTML の「動物種」列に明示されている (犬 / 猫) ので、
  サイト名推定に頼らずそのまま使う。
"""

from __future__ import annotations

from typing import ClassVar

from bs4 import BeautifulSoup
from bs4.element import Tag

from ....domain.models import RawAnimalData
from ...municipality_adapter import ParsingError
from ..registry import SiteAdapterRegistry
from ..single_page_table import SinglePageTableAdapter


class CityFunabashiAdapter(SinglePageTableAdapter):
    """船橋市動物愛護指導センター用 rule-based adapter

    収容犬猫 / 譲渡可能犬猫 の 2 サイトで共通テンプレートを使用する。
    `<table>` ヘッダ行 + データ行 N 件の single_page 形式。
    """

    # `boxEntryFreeform` 配下のテーブルの行のみを対象とする。
    # ページ内に他テーブルが追加された場合に備えてスコープを限定する。
    ROW_SELECTOR: ClassVar[str] = "div.boxEntryFreeform table tr"
    # 1 行目はヘッダ (`<th>`) なので除外
    SKIP_FIRST_ROW: ClassVar[bool] = True
    # 収容公示テーブルの列数。譲渡サイトには 4 列の「譲渡情報」テーブルや
    # 3 列の「譲渡団体一覧」テーブルが混在するため、ヘッダ行の列数がこの値に
    # 一致するテーブルのみをデータソースとして扱う。
    TABLE_SELECTOR: ClassVar[str] = "div.boxEntryFreeform table"
    EXPECTED_COLUMN_COUNT: ClassVar[int] = 11
    # 列インデックス → RawAnimalData フィールド名 のマッピング。
    # 列 0 (番号), 列 2 (公示満了日), 列 9 (備考), 列 10 (写真) は
    # RawAnimalData に対応するフィールドが無いため除外する。
    COLUMN_FIELDS: ClassVar[dict[int, str]] = {
        1: "shelter_date",  # 収容年月日
        3: "location",  # 収容場所
        4: "species",  # 動物種 (犬 / 猫)
        6: "color",  # 毛色
        7: "sex",  # 性別
        8: "size",  # 体格
    }
    LOCATION_COLUMN: ClassVar[int | None] = 3
    SHELTER_DATE_DEFAULT: ClassVar[str] = ""

    # ─────────────────── 譲渡 (adoption) ページ設定 ───────────────────
    # 譲渡ページ (joutoindex.html) は収容の 11 列とは別構造で、犬/猫 譲渡情報が
    # それぞれ 4 列テーブル ([No., 種類/毛色, 備考, 画像]) で並ぶ。3 列の譲渡
    # ボランティア一覧テーブルも混在するため、ヘッダ 4 列のテーブルのみを採用する。
    _ADOPTION_COLUMN_COUNT: ClassVar[int] = 4
    # 備考に含まれると「掲載中だが既に家族が決まった」= 譲渡済を示す語。
    # 募集中の個体のみ掲載するためスキップする。
    _ADOPTED_MARKERS: ClassVar[tuple[str, ...]] = (
        "見つかりました",
        "決まりました",
        "決定しました",
    )
    # 譲渡テーブルには所在地列が無いため、収容先としてセンター名を充てる。
    _ADOPTION_LOCATION: ClassVar[str] = "船橋市動物愛護指導センター"

    # ─────────────────── オーバーライド ───────────────────

    def _load_rows(self) -> list[Tag]:
        """カテゴリに応じて収容 (11列) / 譲渡 (4列) のデータ行を抽出する

        収容ページ (sheltered) と譲渡ページ (adoption) は同一テンプレート上の
        別構造のため、`site_config.category` で経路を分ける。収容の 11 列パスは
        既存挙動を一切変えない (回帰防止)。
        """
        if self._rows_cache is not None:
            return self._rows_cache

        if self._html_cache is None:
            self._html_cache = self._http_get(self.site_config.list_url)

        soup = BeautifulSoup(self._html_cache, "html.parser")
        if self.site_config.category == "adoption":
            self._rows_cache = self._load_adoption_rows(soup)
        else:
            self._rows_cache = self._load_sheltered_rows(soup)
        return self._rows_cache

    def _load_sheltered_rows(self, soup: BeautifulSoup) -> list[Tag]:
        """収容ページ: ヘッダ列数が `EXPECTED_COLUMN_COUNT` (11) のテーブルのみ採用

        譲渡サイト由来の 4 列 / 3 列テーブルを誤取り込みしないよう、各テーブル単位で
        ヘッダ列数を確認し、収容公示と同じ 11 列のものだけをデータソースとする。
        """
        matched: list[Tag] = []
        for table in soup.select(self.TABLE_SELECTOR):
            rows = [r for r in table.find_all("tr") if isinstance(r, Tag)]
            if not rows:
                continue
            header_cells = rows[0].find_all(["th", "td"])
            if len(header_cells) != self.EXPECTED_COLUMN_COUNT:
                continue
            if self.SKIP_FIRST_ROW:
                rows = rows[1:]
            matched.extend(rows)
        return matched

    def _load_adoption_rows(self, soup: BeautifulSoup) -> list[Tag]:
        """譲渡ページ: 4 列の犬/猫譲渡テーブルから募集中の個体行のみ抽出する

        - ヘッダ 4 列のテーブルのみ採用 (3 列の団体一覧・11 列の収容を除外)。
        - テーブルごとに species を文脈 (caption/直前見出し/種類列) から確定し、
          抽出した各行と同じインデックスで `_adoption_species_by_index` に保持する。
        - colspan 導入文ブロック (ncells=1)、空 placeholder 行 (No.も備考も空)、
          譲渡済 (備考に「見つかりました」等) はスキップする。
        """
        matched: list[Tag] = []
        species_by_index: list[str] = []
        for table in soup.select(self.TABLE_SELECTOR):
            rows = [r for r in table.find_all("tr") if isinstance(r, Tag)]
            if not rows:
                continue
            header_cells = rows[0].find_all(["th", "td"])
            if len(header_cells) != self._ADOPTION_COLUMN_COUNT:
                continue
            species = self._adoption_table_species(table)
            for tr in rows[1:]:
                cells = [c for c in tr.find_all(["td", "th"]) if isinstance(c, Tag)]
                if len(cells) != self._ADOPTION_COLUMN_COUNT:
                    continue  # colspan 導入文 (ncells=1) 等
                no_text = cells[0].get_text(strip=True)
                note_text = cells[2].get_text(" ", strip=True)
                if not no_text and not note_text:
                    continue  # 犬テーブルの placeholder 空行
                if any(marker in note_text for marker in self._ADOPTED_MARKERS):
                    continue  # 譲渡済は掲載しない (募集中のみ)
                matched.append(tr)
                species_by_index.append(species)
        self._adoption_species_by_index: list[str] = species_by_index
        return matched

    def _adoption_table_species(self, table: Tag) -> str:
        """譲渡テーブルの犬/猫を caption → 直前見出し → 種類列 の順で確定する

        `_infer_species_from_site_name` はサイト名「船橋市（譲渡可能犬猫）」に対し
        「犬猫」→「犬」を返し全頭を犬に誤分類するため、譲渡経路では使わない。
        犬テーブルの caption は「現在紹介できる犬は…」、猫テーブルは caption が空で
        直前見出し「猫がいます！」や種類列「子猫」で猫が取れる。判定不能なら空文字。
        """
        candidates: list[str] = []
        caption = table.find("caption")
        if isinstance(caption, Tag):
            candidates.append(caption.get_text(" ", strip=True))
        heading = table.find_previous(["h2", "h3"])
        if isinstance(heading, Tag):
            candidates.append(heading.get_text(" ", strip=True))
        for tr in table.find_all("tr")[1:]:
            cells = [c for c in tr.find_all(["td", "th"]) if isinstance(c, Tag)]
            if len(cells) >= 2:
                candidates.append(cells[1].get_text(" ", strip=True))
                break
        for text in candidates:
            has_dog = "犬" in text
            has_cat = "猫" in text
            if has_dog and not has_cat:
                return "犬"
            if has_cat and not has_dog:
                return "猫"
        return ""

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        """テーブル行を仮想 URL に変換する

        収容数 0 件の場合 (ヘッダ行のみ) は空リストを返す。
        テーブル自体が存在しない場合は ParsingError。
        """
        # テーブルそのものが存在しない場合は明示的にエラー。
        # (rows のみで判断すると「ヘッダ行のみ」と区別できない)
        if self._html_cache is None:
            self._html_cache = self._http_get(self.site_config.list_url)
        soup = BeautifulSoup(self._html_cache, "html.parser")
        if soup.select_one("div.boxEntryFreeform table") is None:
            raise ParsingError(
                "テーブルが見つかりません",
                selector="div.boxEntryFreeform table",
                url=self.site_config.list_url,
            )

        rows = self._load_rows()
        # _load_rows は SKIP_FIRST_ROW=True によりヘッダ行を除外済み。
        # 結果が空 = データ行 0 件 (= 在庫 0 件) として正常扱いする。
        if not rows:
            return []
        category = self.site_config.category
        return [(f"{self.site_config.list_url}#row={i}", category) for i in range(len(rows))]

    def extract_animal_details(self, virtual_url: str, category: str = "adoption") -> RawAnimalData:
        """テーブル行から RawAnimalData を構築する

        基底のセルベース既定実装に加え、画像列 (列 10) の絶対 URL 化と、
        動物種列 (列 4) を species にそのまま使う処理を行う。
        """
        rows = self._load_rows()
        idx = self._parse_row_index(virtual_url)
        if idx >= len(rows):
            raise ParsingError(
                f"row index {idx} out of range (total {len(rows)})",
                url=virtual_url,
            )
        row = rows[idx]

        if self.site_config.category == "adoption":
            return self._extract_adoption_animal(row, idx, virtual_url, category)

        cells = row.find_all(["td", "th"])

        fields: dict[str, str] = {}
        for col_idx, field_name in self.COLUMN_FIELDS.items():
            if col_idx < len(cells):
                fields[field_name] = cells[col_idx].get_text(separator=" ", strip=True)

        location = fields.get("location", "")
        # 「動物種」列はサイトによっては空欄や記号があり得るので、
        # 空のときはサイト名から推定する (フォールバック)。
        species = fields.get("species", "").strip()
        if not species:
            species = self._infer_species_from_site_name(self.site_config.name)

        try:
            return RawAnimalData(
                species=species,
                sex=fields.get("sex", ""),
                age="",
                color=fields.get("color", ""),
                size=fields.get("size", ""),
                shelter_date=fields.get("shelter_date", self.SHELTER_DATE_DEFAULT),
                location=location,
                phone="",
                image_urls=self._extract_row_images(row, virtual_url),
                source_url=virtual_url,
                category=category,
            )
        except Exception as e:
            raise ParsingError(f"RawAnimalData バリデーション失敗: {e}", url=virtual_url) from e

    def _extract_adoption_animal(
        self, row: Tag, idx: int, virtual_url: str, category: str
    ) -> RawAnimalData:
        """譲渡 4 列テーブルの行から RawAnimalData を構築する

        列構成: [No., 種類(=breed), 備考(=description), 画像]。毛色/年齢/性別は
        備考の自由文に埋まっており構造化が難しいため、description に原文を保持して
        silent-drop を避ける (breed と description は CLAUDE.md 必須保持項目)。
        species は `_load_adoption_rows` がテーブル文脈から確定済みの値を使い、
        取れない場合は種類列 (breed="子猫") を normalizer に委ねる。
        """
        cells = row.find_all(["td", "th"])
        breed = cells[1].get_text(" ", strip=True) if len(cells) > 1 else ""
        description = cells[2].get_text(" ", strip=True) if len(cells) > 2 else ""
        species_by_index = getattr(self, "_adoption_species_by_index", [])
        species = species_by_index[idx] if idx < len(species_by_index) else ""

        try:
            return RawAnimalData(
                species=species or breed,
                sex="",
                age="",
                color="",
                size="",
                shelter_date="",
                location=self._ADOPTION_LOCATION,
                phone="",
                image_urls=self._extract_row_images(row, virtual_url),
                source_url=virtual_url,
                category=category,
                breed=breed,
                description=description,
            )
        except Exception as e:
            raise ParsingError(f"RawAnimalData バリデーション失敗: {e}", url=virtual_url) from e

    # ─────────────────── ヘルパー ───────────────────

    @staticmethod
    def _infer_species_from_site_name(name: str) -> str:
        """サイト名から動物種別 (犬/猫/その他) を推定する

        船橋市の 2 サイトはどちらも「犬猫」を含むので確定はできないが、
        HTML の動物種列が空のときの最終フォールバックとして "犬" を返す。
        """
        if "犬猫" in name:
            return "犬"
        if "犬" in name:
            return "犬"
        if "猫" in name:
            return "猫"
        return "その他"


# ─────────────────── サイト登録 ───────────────────
# 同一テンプレート上で運用される 2 サイトを同一 adapter にマップする。
for _site_name in (
    "船橋市（収容犬猫）",
    "船橋市（譲渡可能犬猫）",
):
    SiteAdapterRegistry.register(_site_name, CityFunabashiAdapter)
