"""仙台市動物管理センター (アニパル仙台) rule-based adapter

対象ドメイン: https://www.city.sendai.jp/dobutsu/kurashi/shizen/petto/hogodobutsu/joho/

特徴:
- 同一テンプレート上で 3 サイト (譲渡犬/譲渡猫/譲渡子猫) を運用しており、
  URL パターンのみが異なる:
    - .../joho/inu.html     (譲渡犬)
    - .../joho/neko.html    (譲渡猫)
    - .../joho/koneko.html  (譲渡子猫)
- 1 ページに複数動物が掲載される single_page サイト。
  各動物は次のような繰り返し構造で記述される:
    <h3>...管理番号 XXX（愛称：YYY）...</h3>
    <table>  ← 基本情報テーブル (1 行 2 列)
      <tr>
        <td><img src="..."></td>
        <td>
          <p>基本情報</p>
          <p>　種類：柴犬</p>
          <p>　性別：去勢雄</p>
          <p>　年齢：10歳</p>
          <p>　体重：約16kg</p>
          <p>　毛色：茶</p>
        </td>
      </tr>
    </table>
    <table>...</table>  ← 健康/性格情報テーブル (任意)
- ページ上部にも他テーブル (案内文書等) が混在し得るが、本サイトでは
  「管理番号 ＋ 愛称」を含む `<h3>` の直後の最初のテーブルのみを
  動物情報テーブルとみなして抽出する。
- 在庫 0 件のときは「管理番号」を含む `<h3>` が 1 つも現れないため、
  fetch_animal_list は空リストを返す (ParsingError は出さない)。
- 動物種別 (犬/猫/その他) はサイト名から推定する。
- 収容日と問い合わせ電話番号はページ全体の固定値 (ヘッダ「譲渡犬情報
  (令和X年Y月Z日更新)」と末尾の問い合わせ欄) として共有される。
  電話番号はページ全体から `_normalize_phone` で抽出する。
"""

from __future__ import annotations

import re
from typing import ClassVar

from bs4 import BeautifulSoup, Tag

from ....domain.models import RawAnimalData
from ...municipality_adapter import ParsingError
from ..registry import SiteAdapterRegistry
from ..single_page_table import SinglePageTableAdapter

# 「管理番号 D24018（愛称：平助）」のような h3 内テキストを判定するパターン。
# 全角/半角スペース・括弧揺れを許容する。
_KANRI_BANGO_RE = re.compile(r"管理番号")

# 基本情報テーブルセル内の "種類：柴犬" のようなラベル行を分割するパターン。
# 行頭の全角スペース等は事前に strip しておく。
_FIELD_LABEL_RE = re.compile(r"^[\s　]*([^：:]+?)[：:]\s*(.*)$")

# ラベル → RawAnimalData フィールド名 のマッピング。
_LABEL_TO_FIELD: dict[str, str] = {
    "種類": "species",
    "性別": "sex",
    "年齢": "age",
    "体重": "size",
    "毛色": "color",
}


class CitySendaiAdapter(SinglePageTableAdapter):
    """仙台市動物管理センター用 rule-based adapter

    譲渡犬/譲渡猫/譲渡子猫 の 3 サイトで共通テンプレートを使用する。
    `<h3>管理番号 ...</h3>` を動物カードのアンカーとし、その直後の
    最初の `<table>` から基本情報を抽出する single_page 形式。
    """

    # 基底契約 (`__init_subclass__` の検査) を満たすため定義するが、
    # 本サイトでは `_load_rows` をオーバーライドして h3 ベースで動物グループを
    # 構築するため、この CSS セレクタ自体は内部では使用しない。
    ROW_SELECTOR: ClassVar[str] = "h3"
    SKIP_FIRST_ROW: ClassVar[bool] = False
    # `<p>` ベースの抽出を独自に行うため、列 index ベースの既定マッピングは使用しない。
    COLUMN_FIELDS: ClassVar[dict[int, str]] = {}
    LOCATION_COLUMN: ClassVar[int | None] = None
    # 仙台市のページには動物個別の収容日表記は無い。
    SHELTER_DATE_DEFAULT: ClassVar[str] = ""

    def __init__(self, site_config) -> None:
        super().__init__(site_config)
        # ページ全体で共通の問い合わせ電話番号 (1 ページに 1 度だけパース)。
        self._page_phone_cache: str | None = None

    # ─────────────────── fetch_animal_list オーバーライド ───────────────────

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        """動物カード相当のテーブルを仮想 URL に変換する

        在庫 0 件 (「管理番号」を含む `<h3>` が 1 つも無い) のケースでは
        空リストを返す (ParsingError は出さない)。
        """
        rows = self._load_rows()
        category = self.site_config.category
        return [(f"{self.site_config.list_url}#row={i}", category) for i in range(len(rows))]

    # ─────────────────── _load_rows オーバーライド ───────────────────

    def _load_rows(self) -> list[Tag]:
        """ページ HTML を 1 度だけ取得し、動物カード相当の `<table>` を返す

        各 `<h3>` のうち「管理番号」を含むものを動物アンカーとし、
        その後ろに最初に出現する `<table>` を 1 頭分の情報テーブルと
        みなして集める。テーブルが存在しない h3 は無視する。
        """
        if self._rows_cache is not None:
            return self._rows_cache

        if self._html_cache is None:
            self._html_cache = self._http_get(self.site_config.list_url)

        soup = BeautifulSoup(self._html_cache, "html.parser")

        rows: list[Tag] = []
        for h3 in soup.find_all("h3"):
            if not isinstance(h3, Tag):
                continue
            text = h3.get_text(separator=" ", strip=True)
            if not _KANRI_BANGO_RE.search(text):
                continue
            table = h3.find_next("table")
            if isinstance(table, Tag):
                rows.append(table)

        # ページ全体から問い合わせ電話番号を 1 度だけ抽出してキャッシュ。
        self._page_phone_cache = self._normalize_phone(soup.get_text(" ", strip=True))

        self._rows_cache = rows
        return rows

    # ─────────────────── extract_animal_details オーバーライド ───────────────────

    def extract_animal_details(self, virtual_url: str, category: str = "adoption") -> RawAnimalData:
        """1 頭分の `<table>` から RawAnimalData を構築する"""
        rows = self._load_rows()
        idx = self._parse_row_index(virtual_url)
        if idx >= len(rows):
            raise ParsingError(
                f"row index {idx} out of range (total {len(rows)})",
                url=virtual_url,
            )
        table = rows[idx]

        # `<p>` ベースで「ラベル：値」形式を集める。
        # セル内の `<br>` で分かれた行、複数の `<p>` のいずれにも対応するため、
        # テーブル全体からテキストを行ごとに取り出してパースする。
        fields: dict[str, str] = {}
        text_lines = self._extract_text_lines(table)
        for line in text_lines:
            m = _FIELD_LABEL_RE.match(line)
            if not m:
                continue
            label = m.group(1).strip().strip("　")
            value = m.group(2).strip().strip("　")
            field_name = _LABEL_TO_FIELD.get(label)
            if field_name and field_name not in fields:
                fields[field_name] = value

        # 動物種別: 「種類」フィールドではなくサイト名から推定する。
        # (HTML の「種類」列は犬種名など具体名のため、犬/猫/その他の判別には不向き。)
        species = self._infer_species_from_site_name(self.site_config.name)

        try:
            return RawAnimalData(
                species=species,
                sex=fields.get("sex", ""),
                age=fields.get("age", ""),
                color=fields.get("color", ""),
                size=fields.get("size", ""),
                shelter_date=self.SHELTER_DATE_DEFAULT,
                location="",
                phone=self._page_phone_cache or "",
                image_urls=self._extract_row_images(table, virtual_url),
                source_url=virtual_url,
                category=category,
            )
        except Exception as e:
            raise ParsingError(f"RawAnimalData バリデーション失敗: {e}", url=virtual_url) from e

    # ─────────────────── ヘルパー ───────────────────

    @staticmethod
    def _extract_text_lines(table: Tag) -> list[str]:
        """テーブル内テキストを論理行のリストとして取り出す

        `<p>` の境界・`<br>` の境界をいずれも改行に揃えてから
        空白行を除外して返す。
        """
        # `<br>` を改行に変換するため separator='\n' を使う
        # ただし `<p>` 同士はそのままでは隣接して結合されないので、
        # 各 `<p>` を個別に走査して連結する。
        lines: list[str] = []
        # `<p>` を優先的に行単位として扱う
        ps = table.find_all("p")
        if ps:
            for p in ps:
                if not isinstance(p, Tag):
                    continue
                txt = p.get_text(separator="\n", strip=False)
                for ln in txt.split("\n"):
                    ln = ln.strip()
                    if ln:
                        lines.append(ln)
        else:
            # `<p>` が無い場合はセル全体から行を分割
            txt = table.get_text(separator="\n", strip=False)
            for ln in txt.split("\n"):
                ln = ln.strip()
                if ln:
                    lines.append(ln)
        return lines

    @staticmethod
    def _infer_species_from_site_name(name: str) -> str:
        """サイト名から動物種別 (犬/猫/その他) を推定する

        「子猫」も「猫」と判定する (順序: 子猫より先に犬を判定)。
        """
        if "犬" in name:
            return "犬"
        if "猫" in name:
            return "猫"
        return "その他"


# ─────────────────── サイト登録 ───────────────────
# 同一テンプレート上で運用される 3 サイトを同一 adapter にマップする。
for _site_name in (
    "仙台市アニパル（譲渡犬）",
    "仙台市アニパル（譲渡猫）",
    "仙台市アニパル（譲渡子猫）",
):
    SiteAdapterRegistry.register(_site_name, CitySendaiAdapter)
