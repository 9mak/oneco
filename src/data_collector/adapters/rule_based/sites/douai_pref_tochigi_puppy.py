"""栃木県動物愛護指導センター 子犬/子猫 譲渡ページ rule-based adapter

対象ページ:
  - https://www.douai.pref.tochigi.lg.jp/work/puppy/  (愛護館で活躍中の子犬たち)
  - https://www.douai.pref.tochigi.lg.jp/work/kitten/ (愛護館で活躍中の猫たち)

背景 (T121 調査, 2026-08-31):
- 本体サイトの旧登録 URL `/jyouto/` (動物の譲渡) はテーマ改修で案内リンク
  集ページ化しており実データを持たない。実データは上記 2 つの固定ページに
  1 ページ完結型のテーブルとして掲載されている (詳細ページは存在しない)。
- HTML 構造が既存の `SinglePageTableAdapter` (1 行 = 1 個体) とは異なり、
  WordPress Gutenberg のテーブルブロック (`table.has-fixed-layout`) 内で
  「1 列 = 1 個体、1 行 = 1 項目」という転置レイアウトになっている。
  例 (子犬譲渡会枠、5 頭):
    <tr><td colspan=5>５枠</td></tr>                       ← 枠見出し (スキップ)
    <tr><td>番号：希望表配布時に付番します</td>×5</tr>       ← 個体別 (N セル)
    <tr><td>性別：オス</td>×5</tr>                          ← 個体別 (N セル)
    <tr><td><img></td>×5</tr>                              ← 個体別 (N セル)
  随時譲渡枠 (3 頭ずつ) では、上記に加えて「性質/体特徴」行 (個体別) と
  末尾に 1 セル (colspan=3) の共通注記行 ("4月生まれ　ワクチン2回接種済"
  等、全頭共通のため全列に適用) が続く。行の並び順・行数はテーブルごとに
  異なる (子猫ページは 番号→写真→性別 の順で子犬ページと逆)。
  そのため「行の位置」ではなく「セル数」で個体別行 (N セル) か
  全列共通行 (1 セル) かを判定し、各セルのテキストを
  `ラベル：値` の正規表現で読み取る方式にした。
- 「番号：希望表配布時に付番します」は「希望表配布時にならないと管理番号が
  決まらない」という意味で、個体自体は現在公開・閲覧可能なため除外しない
  (management_number は空文字にする)。
- 「番号：１ 飼い主さん決まりました」のように、番号セルに直接
  ステータス文言が連結されるケースがある。これは既に譲渡先が決定し
  募集対象外になった個体を意味するため、一覧から除外する。
- shelter_date (収容日) はこのページには記載が無いため空文字のまま返す。
  DataNormalizer 側の「データ取得日」フォールバック (全 adapter 共通の
  セーフネット) に委ねる。
- location (収容場所) は明示的な記載が無いが、ページ自体が「愛護館で
  活躍中の...」(=施設内で展示中) という文脈のため、施設名を既定値とする。
- 動物種別・年齢区分 (子犬/子猫) はこのページ自体に明示フィールドが無いため
  site_config.name (例: "栃木県動物愛護指導センター（子犬譲渡）") から推定する
  (`PrefChibaAdapter._infer_species_from_site_name` と同種の手法)。
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup, Tag

from ....domain.models import AnimalData, RawAnimalData
from ...municipality_adapter import ParsingError
from ..base import RuleBasedAdapter
from ..registry import SiteAdapterRegistry

# セル内の「ラベル：値」を 1 つ以上抽出する。1 セルに複数ラベルが連結される
# ケース (例: "体特徴：両前足白ソックス 性質：やや怖がり、音に敏感") に対応する
# ため、次のラベルの直前までを非貪欲マッチで値とする。
_LABEL_VALUE_RE = re.compile(r"([^\s：]{1,8})：([^：]*?)(?=[^\s：]{1,8}：|$)")

# 番号欄に連結され得る「既に譲渡先決定済み」を示す文言。
_UNAVAILABLE_MARKERS: tuple[str, ...] = ("決まりました", "終了しました", "マッチング済")

# 「番号：希望表配布時に付番します」= 管理番号は未確定だが個体自体は公開中。
_PENDING_NUMBER_TEXT = "希望表配布時に付番します"

_LOCATION_DEFAULT = "栃木県動物愛護指導センター"


def _apply_cell_text(column: dict[str, Any], text: str) -> None:
    """1 セルのテキストを解析し、column (個体別の蓄積辞書) に反映する"""
    text = text.strip()
    if not text:
        return
    matches = _LABEL_VALUE_RE.findall(text)
    if not matches:
        column["notes"].append(text)
        return
    for label, raw_value in matches:
        value = raw_value.strip()
        if label == "番号":
            if any(marker in value for marker in _UNAVAILABLE_MARKERS):
                column["unavailable"] = True
            if _PENDING_NUMBER_TEXT in value:
                column["management_number"] = ""
            else:
                # 実番号にステータス文言が連結される場合があるため先頭トークンのみ採用
                tokens = value.split()
                column["management_number"] = tokens[0] if tokens else ""
        elif label == "性別":
            column["sex"] = value
        elif value:
            column["notes"].append(f"{label}：{value}")


def _parse_table_columns(table: Tag) -> list[dict[str, Any]]:
    """1 テーブル (1 枠) から個体別データを列単位で抽出する

    先頭行は枠見出し ("５枠"/"Aケージ" 等の colspan 1 セル) のためスキップし、
    以降の行はセル数で「個体別行 (N セル)」か「全列共通の注記行 (1 セル)」かを
    判定する。
    """
    rows = [tr for tr in table.find_all("tr") if isinstance(tr, Tag)]
    if not rows:
        return []
    cell_lists = [tr.find_all(["td", "th"]) for tr in rows]
    n = max((len(cells) for cells in cell_lists), default=0)
    if n == 0:
        return []

    columns: list[dict[str, Any]] = [
        {"notes": [], "image_urls": [], "sex": "", "management_number": ""} for _ in range(n)
    ]

    for row_idx, cells in enumerate(cell_lists):
        if row_idx == 0:
            continue  # 枠見出し行 (個体データではない)
        if len(cells) == n:
            for i, cell in enumerate(cells):
                img = cell.find("img")
                if img is not None:
                    src = img.get("src")
                    if isinstance(src, str) and src:
                        columns[i]["image_urls"].append(src)
                    continue
                _apply_cell_text(columns[i], cell.get_text(" ", strip=True))
        elif len(cells) == 1:
            # 全頭共通の注記 (例: "4月生まれ　ワクチン2回接種済")
            text = cells[0].get_text(" ", strip=True)
            if text:
                for column in columns:
                    column["notes"].append(text)
        # それ以外のセル数 (壊れた行) は個体との対応が付かないため無視する

    return columns


class DouaiPrefTochigiPuppyAdapter(RuleBasedAdapter):
    """栃木県動物愛護指導センター 子犬/子猫譲渡ページ用アダプター

    詳細ページを持たない 1 ページ完結型のため、`<list_url>#animal=N` の
    仮想 URL で個体を識別する (`SinglePageTableAdapter` と同様の方式)。
    """

    def __init__(self, site_config) -> None:
        super().__init__(site_config)
        self._html_cache: str | None = None
        self._columns_cache: list[dict[str, Any]] | None = None

    # ─────────────────── MunicipalityAdapter 実装 ───────────────────

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        columns = self._load_available_columns()
        if not columns:
            return []
        category = self.site_config.category
        return [(f"{self.site_config.list_url}#animal={i}", category) for i in range(len(columns))]

    def extract_animal_details(self, virtual_url: str, category: str = "adoption") -> RawAnimalData:
        columns = self._load_available_columns()
        idx = self._parse_index(virtual_url)
        if idx >= len(columns):
            raise ParsingError(
                f"animal index {idx} out of range (total {len(columns)})",
                url=virtual_url,
            )
        column = columns[idx]

        image_urls = self._filter_image_urls(
            [
                self._absolute_url(src, base=self.site_config.list_url)
                for src in column["image_urls"]
            ],
            self.site_config.list_url,
        )
        # notes の重複を除きつつ順序を保って description へ連結
        description = "、".join(dict.fromkeys(column.get("notes", [])))

        try:
            return RawAnimalData(
                species=self._infer_species(),
                sex=column.get("sex", ""),
                age=self._infer_age_label(),
                color="",
                size="",
                shelter_date="",
                location=_LOCATION_DEFAULT,
                phone="",
                image_urls=image_urls,
                source_url=virtual_url,
                category=category,
                description=description,
                management_number=column.get("management_number", ""),
            )
        except Exception as e:
            raise ParsingError(f"RawAnimalData バリデーション失敗: {e}", url=virtual_url) from e

    def normalize(self, raw_data: RawAnimalData) -> AnimalData:
        return self._default_normalize(raw_data)

    # ─────────────────── ヘルパー ───────────────────

    def _load_available_columns(self) -> list[dict[str, Any]]:
        """列 (個体) データを 1 回だけ抽出してキャッシュし、募集対象外を除外する

        行 0 件は「現在譲渡対象の子犬/子猫がいない」真ゼロとして扱う。
        """
        if self._columns_cache is not None:
            return self._columns_cache

        if self._html_cache is None:
            self._html_cache = self._http_get(self.site_config.list_url)

        soup = BeautifulSoup(self._html_cache, "html.parser")
        columns: list[dict[str, Any]] = []
        for table in soup.select("table.has-fixed-layout"):
            columns.extend(_parse_table_columns(table))

        # 「決まりました」等ですでに譲渡先が決定した個体は募集対象外のため除外
        available = [c for c in columns if not c.get("unavailable")]
        self._columns_cache = available
        return available

    @staticmethod
    def _parse_index(virtual_url: str) -> int:
        """`<list_url>#animal=N` から N を取り出す"""
        fragment = urlparse(virtual_url).fragment
        if not fragment.startswith("animal="):
            raise ParsingError(f"無効な仮想 URL: {virtual_url} (#animal=N 形式が必要)")
        return int(fragment.split("=", 1)[1])

    def _infer_species(self) -> str:
        """site_config.name から動物種別 (犬/猫) を推定する"""
        return "猫" if "猫" in self.site_config.name else "犬"

    def _infer_age_label(self) -> str:
        """site_config.name から年齢区分 (子犬/子猫) を推定する"""
        name = self.site_config.name
        if "子猫" in name:
            return "子猫"
        if "子犬" in name:
            return "子犬"
        return ""


# ─────────────────── サイト登録 ───────────────────
_SITE_NAMES = (
    "栃木県動物愛護指導センター（子犬譲渡）",
    "栃木県動物愛護指導センター（子猫譲渡）",
)

for _name in _SITE_NAMES:
    SiteAdapterRegistry.register(_name, DouaiPrefTochigiPuppyAdapter)
