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
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from ....domain.models import RawAnimalData
from ...municipality_adapter import ParsingError
from ..registry import SiteAdapterRegistry
from ..single_page_table import SinglePageTableAdapter

# 「管理番号 D24018（愛称：平助）」のような h3 内テキストを判定するパターン。
# 全角/半角スペース・括弧揺れを許容する。
_KANRI_BANGO_RE = re.compile(r"管理番号")

# h3 から管理番号 (例: D24018) を抽出するパターン。英数字・ハイフン類を許容。
_MGMT_NUMBER_RE = re.compile(r"管理番号[\s　]*([A-Za-z0-9\-―ー‐]+)")
# h3 の「（愛称：平助）」から仮名 (愛称) を抽出するパターン。
# 値は閉じ括弧 / 全角空白 / 文字列終端の手前まで。
_NICKNAME_RE = re.compile(r"愛称[：:\s　]*([^）)　]+)")

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

# ─── 2026-08 リニューアル後の一覧表レイアウト用 ───
# 譲渡猫 / 譲渡子猫ページは `<table class="datatable">` の
# 「ヘッダ行 + 1 頭 = 1 行」形式に変更された。列構成はページごとに異なる
# (猫: 管理番号/猫の種類/性別/体格/毛色/その他、
#  子猫: 管理番号/写真/性別/毛色/コメント) ため、列 index は固定せず
# ヘッダのラベル名から解決する。
_DATATABLE_HEADER_TO_FIELD: dict[str, str] = {
    "管理番号": "management_number",
    "猫の種類": "breed",
    "犬の種類": "breed",
    "種類": "breed",
    "性別": "sex",
    "体格": "size",
    "体重": "size",
    "毛色": "color",
    "年齢": "age",
    "その他": "description",
    "コメント": "description",
}
# 一覧表と判定するために必要なヘッダ (これが無い表は案内文などの別テーブル)。
_DATATABLE_REQUIRED_HEADER = "管理番号"


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
        # ページ全体の「（令和X年Y月Z日更新）」を shelter_date フォールバックに使う。
        self._page_update_date_cache: str = ""
        # 各動物テーブルに対応する h3 テキスト (管理番号・愛称の抽出元)。
        # `_load_rows` で rows と同じ順序・件数で構築する。
        self._h3_text_by_row: list[str] = []
        # レイアウト種別: "legacy" (h3 + テーブル) / "datatable" (一覧表)。
        # `_load_rows` が実 HTML を見て決定する。
        self._layout: str = "legacy"
        # datatable レイアウトの {フィールド名: 列 index}。
        self._datatable_fields: dict[str, int] = {}
        # datatable レイアウトの {管理番号: 画像 URL 一覧}。
        # 猫ページは写真が別テーブル (管理番号/写真1/写真2) に分離されている
        # ため、管理番号をキーに突き合わせる。
        self._images_by_mgmt: dict[str, list[str]] = {}

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
        h3_texts: list[str] = []
        for h3 in soup.find_all("h3"):
            if not isinstance(h3, Tag):
                continue
            text = h3.get_text(separator=" ", strip=True)
            if not _KANRI_BANGO_RE.search(text):
                continue
            table = h3.find_next("table")
            if isinstance(table, Tag):
                rows.append(table)
                # 管理番号・愛称の抽出元として h3 テキストを行と同順で保持する
                h3_texts.append(text)
        self._h3_text_by_row = h3_texts

        # 旧レイアウトで 1 頭も取れない場合は 2026-08 リニューアル後の
        # 一覧表レイアウトを試す。譲渡犬ページは旧のままなので、
        # 「旧を優先し、空なら新」の順で両対応する。
        if not rows:
            rows = self._load_datatable_rows(soup)

        # ページ全体から問い合わせ電話番号と「更新日」を 1 度だけ抽出してキャッシュ。
        page_text = soup.get_text(" ", strip=True)
        self._page_phone_cache = self._normalize_phone(page_text)
        # 「（令和8年5月15日更新）」の更新日を shelter_date のフォールバックに使う
        m = re.search(r"(令和\d+年\d+月\d+日|\d{4}年\d+月\d+日)", page_text)
        self._page_update_date_cache = m.group(1) if m else ""

        self._rows_cache = rows
        return rows

    # ─────────────────── datatable レイアウト ───────────────────

    def _load_datatable_rows(self, soup: BeautifulSoup) -> list[Tag]:
        """`table.datatable` の一覧表から 1 頭 = 1 行の `<tr>` を集める

        ヘッダ行に「管理番号」を含むテーブルだけを動物一覧とみなす。
        列 index はヘッダのラベル名から解決して `_datatable_fields` に持つ。
        写真専用テーブル (管理番号 + 写真N のみ) は動物一覧ではなく
        画像ソースとして `_images_by_mgmt` に取り込む。
        """
        animal_rows: list[Tag] = []
        for table in soup.find_all("table"):
            if not isinstance(table, Tag):
                continue
            trs = table.find_all("tr")
            if len(trs) < 2:
                continue
            headers = [c.get_text(" ", strip=True) for c in trs[0].find_all(["th", "td"])]
            if _DATATABLE_REQUIRED_HEADER not in headers:
                continue

            fields = {
                _DATATABLE_HEADER_TO_FIELD[h]: i
                for i, h in enumerate(headers)
                if h in _DATATABLE_HEADER_TO_FIELD
            }
            mgmt_idx = fields.get("management_number")
            if mgmt_idx is None:
                continue

            # 「管理番号」以外に実データ列を持たない表 = 写真テーブル。
            # 動物一覧としては扱わず、画像だけ管理番号に紐付けて回収する。
            is_photo_table = set(fields) <= {"management_number"}
            for tr in trs[1:]:
                cells = tr.find_all(["th", "td"])
                if mgmt_idx >= len(cells):
                    continue
                mgmt = cells[mgmt_idx].get_text(" ", strip=True)
                if not mgmt:
                    continue
                imgs = self._collect_row_image_urls(tr)
                if imgs:
                    self._images_by_mgmt.setdefault(mgmt, []).extend(imgs)
                if not is_photo_table:
                    animal_rows.append(tr)

            if not is_photo_table and fields:
                self._datatable_fields = fields

        if animal_rows:
            self._layout = "datatable"
        return animal_rows

    def _collect_row_image_urls(self, row: Tag) -> list[str]:
        """行内の `<img>` から絶対 URL を組み立てて返す"""
        urls: list[str] = []
        for img in row.find_all("img"):
            if not isinstance(img, Tag):
                continue
            src = img.get("src") or ""
            if not src:
                continue
            urls.append(urljoin(self.site_config.list_url, str(src)))
        return urls

    def _extract_from_datatable_row(self, row: Tag, virtual_url: str, category: str):
        """一覧表の 1 行から RawAnimalData を構築する"""
        cells = row.find_all(["th", "td"])

        def cell(field: str) -> str:
            i = self._datatable_fields.get(field)
            if i is None or i >= len(cells):
                return ""
            return cells[i].get_text(" ", strip=True)

        management_number = cell("management_number")
        images = self._images_by_mgmt.get(management_number, [])
        if not images:
            images = self._collect_row_image_urls(row)

        return RawAnimalData(
            species=self._infer_species_from_site_name(self.site_config.name),
            breed=cell("breed"),
            name="",
            management_number=management_number,
            sex=cell("sex"),
            age=cell("age"),
            color=cell("color"),
            size=cell("size"),
            description=cell("description"),
            shelter_date=self._page_update_date_cache or self.SHELTER_DATE_DEFAULT,
            location="仙台市動物管理センター（アニパル仙台）",
            phone=self._page_phone_cache or "",
            image_urls=images,
            source_url=virtual_url,
            category=category,
        )

    # ─────────────────── extract_animal_details オーバーライド ───────────────────

    def extract_animal_details(self, virtual_url: str, category: str = "adoption") -> RawAnimalData:
        """1 頭分の `<table>` (旧) または `<tr>` (一覧表) から RawAnimalData を構築する"""
        rows = self._load_rows()
        idx = self._parse_row_index(virtual_url)
        if idx >= len(rows):
            raise ParsingError(
                f"row index {idx} out of range (total {len(rows)})",
                url=virtual_url,
            )
        table = rows[idx]

        if self._layout == "datatable":
            try:
                return self._extract_from_datatable_row(table, virtual_url, category)
            except Exception as e:
                raise ParsingError(f"RawAnimalData バリデーション失敗: {e}", url=virtual_url) from e

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

        # 管理番号・仮名(愛称) は h3「管理番号 D24018（愛称：平助）」から抽出する。
        # 「種類：柴犬」は犬種名のため品種(breed)として保存する。
        h3_text = self._h3_text_by_row[idx] if idx < len(self._h3_text_by_row) else ""
        mgmt_match = _MGMT_NUMBER_RE.search(h3_text)
        management_number = mgmt_match.group(1) if mgmt_match else ""
        name_match = _NICKNAME_RE.search(h3_text)
        name = name_match.group(1).strip().strip("　") if name_match else ""
        breed = fields.get("species", "")

        # 仙台市のページには動物個別の収容日表記が無いため、ページの「更新日」を
        # shelter_date のフォールバックに使う (掲載が始まった日として最も近い情報)。
        shelter_date = self._page_update_date_cache or self.SHELTER_DATE_DEFAULT
        try:
            return RawAnimalData(
                species=species,
                breed=breed,
                name=name,
                management_number=management_number,
                sex=fields.get("sex", ""),
                age=fields.get("age", ""),
                color=fields.get("color", ""),
                size=fields.get("size", ""),
                shelter_date=shelter_date,
                location="仙台市動物管理センター（アニパル仙台）",
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
