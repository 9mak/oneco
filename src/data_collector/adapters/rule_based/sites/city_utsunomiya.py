"""宇都宮市動物愛護センター rule-based adapter

対象ドメイン: https://www.city.utsunomiya.lg.jp/kurashi/pet/pet/

特徴:
- 1 ページ (1005584.html) に「迷子犬」「負傷猫」等の動物が並ぶ single_page
  サイト。個別 detail ページは存在しないため、一覧ページから直接抽出する。
- 各動物は `div#voice` 配下で次のような並びで表現される:
    <h2>迷子犬（掲載期限　令和8年5月27日）</h2>
    <p class="imageright"><img src="..." alt="..."></p>
    <p>収容日　　令和8年5月13日</p>
    <p>収容場所　五代2丁目</p>
    <p>種類　　　ダックス系</p>
    <p>毛色　　　黒茶</p>
    <p>性別　　　メス</p>
    <p>体格　　　小</p>
    <p>装着物　　紫とピンクのチェック柄首輪</p>
- 同じ `<h2>` でも本文先頭のセクション見出しや末尾の案内 (栃木県警察 等) が
  並ぶため、`（掲載期限` を含む `<h2>` のみを「動物カード」とみなす。
- ラベルと値は全角コロンではなく**全角スペース (`　`)** で区切られる
  (千葉市の `ラベル：値<br>` 形式とは異なる)。最初の連続する全角/半角
  空白を区切りとして 2 分割する。
- 種別は HTML 側の「種類」(ダックス系/雑種等) は具体名のため使わず、
  `<h2>` テキストの「迷子犬」「負傷猫」等から (犬/猫/その他) を推定する。
- 0 件状態 (動物 `<h2>` が一件も無い) は ParsingError ではなく
  空リストとして扱う (実運用で在庫 0 が頻発するため)。
"""

from __future__ import annotations

import re
from typing import ClassVar

from bs4 import BeautifulSoup, Tag

from ....domain.models import RawAnimalData
from ...municipality_adapter import ParsingError
from ..registry import SiteAdapterRegistry
from ..single_page_table import SinglePageTableAdapter


# 動物カード `<h2>` の見分けキー (掲載期限の表記)
_ANIMAL_HEADING_RE = re.compile(r"（掲載期限")
# 連続する空白 (全角 　 / 半角) を区切りとして使うパターン
_LABEL_VALUE_SEP_RE = re.compile(r"[　 \t]+")


class CityUtsunomiyaAdapter(SinglePageTableAdapter):
    """宇都宮市動物愛護センター用 rule-based adapter

    1 ページに「迷子犬」「負傷猫」等の動物 `<h2>` ブロックが並ぶ
    single_page 形式。各 `<h2>` の後ろに画像 `<p>` と属性 `<p>` 群が続く。
    """

    # `div#voice` 配下の `<h2>` を起点とする (サイドナビ等の他 `<h2>` を拾わない)。
    # ただし「収容している動物の情報」「栃木県警察」等の案内見出しも同階層に
    # 並ぶため、後段で「（掲載期限」を含む見出しのみに絞り込む。
    ROW_SELECTOR: ClassVar[str] = "div#voice h2"
    SKIP_FIRST_ROW: ClassVar[bool] = False
    # 値の取り出しはオーバーライドした `extract_animal_details` が
    # ラベル/値の縦並びレイアウトを直接スキャンするため
    # `COLUMN_FIELDS` は宣言のみ (基底契約の充足)。
    COLUMN_FIELDS: ClassVar[dict[int, str]] = {
        0: "shelter_date",  # 収容日
        1: "location",      # 収容場所
        2: "species",       # 種類 (HTML 上の値、実際の出力には使わない)
        3: "color",         # 毛色
        4: "sex",           # 性別
        5: "size",          # 体格
    }
    LOCATION_COLUMN: ClassVar[int | None] = 1
    SHELTER_DATE_DEFAULT: ClassVar[str] = ""

    # 属性 `<p>` 内のラベル → RawAnimalData フィールド名
    _LABEL_TO_FIELD: ClassVar[dict[str, str]] = {
        "収容日": "shelter_date",
        "収容場所": "location",
        "種類": "species_local",  # HTML 値は使わないため別名で保持
        "毛色": "color",
        "性別": "sex",
        "体格": "size",
        "装着物": "features",
        "その他": "features",
    }

    # ─────────────────── オーバーライド ───────────────────

    def _load_rows(self) -> list[Tag]:
        """`div#voice h2` のうち動物カード見出しのみに絞り込む

        基底実装は ROW_SELECTOR で取得した全要素を返すため、本サイトの
        ように「動物 `<h2>`」と「案内 `<h2>`」が同階層に混在するときに
        案内まで動物として扱われてしまう。`（掲載期限` を含む見出しに
        限定することで誤検出を防ぐ。
        """
        if self._rows_cache is not None:
            return self._rows_cache

        if self._html_cache is None:
            self._html_cache = self._http_get(self.site_config.list_url)

        soup = BeautifulSoup(self._html_cache, "html.parser")
        candidates = soup.select(self.ROW_SELECTOR)
        rows = [
            r for r in candidates
            if isinstance(r, Tag)
            and _ANIMAL_HEADING_RE.search(r.get_text(strip=False))
        ]
        if self.SKIP_FIRST_ROW and rows:
            rows = rows[1:]
        self._rows_cache = rows
        return rows

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        """一覧ページから動物の仮想 URL を返す

        基底 `SinglePageTableAdapter.fetch_animal_list` は行が 0 件のとき
        `ParsingError` を投げるが、宇都宮市サイトでは在庫 0 件 (動物
        `<h2>` が一件も無い) が正常状態として頻発するため、
        その場合は空リストを返す。
        """
        rows = self._load_rows()
        if not rows:
            return []
        category = self.site_config.category
        return [
            (f"{self.site_config.list_url}#row={i}", category)
            for i in range(len(rows))
        ]

    def extract_animal_details(
        self, virtual_url: str, category: str = "adoption"
    ) -> RawAnimalData:
        """`<h2>` を起点とした動物ブロックから RawAnimalData を構築する"""
        rows = self._load_rows()
        idx = self._parse_row_index(virtual_url)
        if idx >= len(rows):
            raise ParsingError(
                f"row index {idx} out of range (total {len(rows)})",
                url=virtual_url,
            )
        h2 = rows[idx]

        # 同一階層で `<h2>` の後ろに続く `<p>` を、次の `<h2>`/`<h3>`/`<hr>`/
        # `<ul>`/`<div>` に到達するまで集める。
        siblings: list[Tag] = []
        for sib in h2.find_next_siblings():
            if not isinstance(sib, Tag):
                continue
            name = sib.name
            if name in ("h1", "h2", "h3", "h4", "hr", "ul", "ol", "div"):
                break
            if name == "p":
                siblings.append(sib)

        # 画像 `<p>` (class="imageright" 等) と属性 `<p>` を分離
        image_paragraphs = [p for p in siblings if p.find("img") is not None]
        attr_paragraphs = [p for p in siblings if p.find("img") is None]

        fields: dict[str, str] = {}
        for p in attr_paragraphs:
            text = p.get_text(separator="\n", strip=False)
            for line in text.split("\n"):
                line = line.strip()
                if not line:
                    continue
                # 全角スペース or 半角空白の連続で「ラベル」と「値」に 2 分割
                m = _LABEL_VALUE_SEP_RE.search(line)
                if not m:
                    # 区切りが無い行は単独ラベル ("その他" 等) として無視
                    continue
                label = line[: m.start()].strip()
                value = line[m.end():].strip()
                field = self._LABEL_TO_FIELD.get(label)
                if field and value and field not in fields:
                    fields[field] = value

        # 画像 URL を集める
        image_urls: list[str] = []
        for p in image_paragraphs:
            for img in p.find_all("img"):
                src = img.get("src")
                if src and isinstance(src, str):
                    image_urls.append(self._absolute_url(src, base=virtual_url))
        image_urls = self._filter_image_urls(image_urls, virtual_url)

        # 動物種別: HTML の「種類」(ダックス系/雑種等) は具体名のため
        # `<h2>` テキスト「迷子犬」「負傷猫」等から (犬/猫/その他) を推定する。
        species = self._infer_species_from_heading(h2.get_text(strip=True))

        try:
            return RawAnimalData(
                species=species,
                sex=fields.get("sex", ""),
                age="",
                color=fields.get("color", ""),
                size=fields.get("size", ""),
                shelter_date=fields.get("shelter_date", self.SHELTER_DATE_DEFAULT),
                location=fields.get("location", ""),
                phone="",
                image_urls=image_urls,
                source_url=virtual_url,
                category=category,
            )
        except Exception as e:
            raise ParsingError(
                f"RawAnimalData バリデーション失敗: {e}", url=virtual_url
            ) from e

    # ─────────────────── ヘルパー ───────────────────

    @staticmethod
    def _infer_species_from_heading(heading_text: str) -> str:
        """`<h2>` テキストから動物種別 (犬/猫/その他) を推定する

        例:
            "迷子犬（掲載期限　令和8年5月27日）"  -> "犬"
            "負傷猫（掲載期限　令和8年5月22日）"  -> "猫"
        """
        if "犬" in heading_text:
            return "犬"
        if "猫" in heading_text:
            return "猫"
        return "その他"


# ─────────────────── サイト登録 ───────────────────
SiteAdapterRegistry.register("宇都宮市（迷子犬・負傷猫）", CityUtsunomiyaAdapter)
