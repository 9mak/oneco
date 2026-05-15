"""青森県動物愛護センター (aomori-animal.jp) rule-based adapter

対象サイト:
- 青森県動物愛護センター（収容情報）
  http://www.aomori-animal.jp/01_MAIGO/Shuyo.html

特徴:
- 1 ページ 1 テーブル ・ 個別 detail ページなし (single_page 形式)
- ページ自体は Shift_JIS で配信される (`<meta charset="Shift_JIS">`)
- リポジトリ内の fixture は Shift_JIS バイト列を Latin-1 として読み、
  さらに UTF-8 でファイル保存された二重エンコード状態のため
  `_load_rows` で一度だけ逆変換を試みる (千葉県/愛媛県 adapter と同方針)。
- HTML が極めて素朴で、各データ行の最初の `<td>` が閉じタグを欠落しており、
  BeautifulSoup でパースすると「先頭 td に後続 td が入れ子」される。
  幸い `find_all(['td','th'])` で平坦化すれば 10 個のセルが順序通りに
  取得できる:

      [0] No. + 種別 (`<p>1</p><p>犬</p>` の 2 行) ← 種別はここから抽出
      [1] 見つかった日 (YYYY/MM/DD)
      [2] 見つかった場所
      [3] 種類 (品種: 雑種 等)  ← species ではなく breed なので未使用
      [4] 毛色
      [5] 性別 (雄/雌)
      [6] 体格 (中型 等)
      [7] 特徴 (空のことが多い)
      [8] 画像 (`<img src="Shuyoimg/...">`)
      [9] 連絡先 (`動物愛護センター...<br>TEL: 0176-23-9511`)

- 画像 URL は `Shuyoimg/YYYYMMDD_NNN.jpg` の相対パスで、
  `/wp-content/uploads/` 規約に依拠する基底の `_filter_image_urls`
  をそのまま使うとフェイルセーフで全件保持されるが、サイト固有の
  パス判定を持たせて意図を明示する。
- 在庫 0 件 (データ行が無い) のページでも ParsingError を出さず空リストを返す。
"""

from __future__ import annotations

from typing import ClassVar

from bs4 import BeautifulSoup, Tag

from ....domain.models import RawAnimalData
from ...municipality_adapter import ParsingError
from ..registry import SiteAdapterRegistry
from ..single_page_table import SinglePageTableAdapter


class AomoriAnimalAdapter(SinglePageTableAdapter):
    """青森県動物愛護センター adapter (single_page 形式)"""

    # 表は body 直下に 1 つだけある実データテーブルで、
    # `<table border='1' ...>` という属性で識別できる
    # (ヘッダ用の caption-only テーブルは border 属性を持たない)。
    ROW_SELECTOR: ClassVar[str] = "table[border] tbody tr"
    # 1 行目はヘッダ (`<th>` のみ)。データ行とは分かれているがフィルタする。
    SKIP_FIRST_ROW: ClassVar[bool] = True
    # 基底の cells ベース既定実装は使わず extract_animal_details を独自実装する。
    # 契約として COLUMN_FIELDS は宣言しておく。
    COLUMN_FIELDS: ClassVar[dict[int, str]] = {
        1: "shelter_date",
        2: "location",
        4: "color",
        5: "sex",
        6: "size",
        9: "phone",
    }
    LOCATION_COLUMN: ClassVar[int | None] = 2
    SHELTER_DATE_DEFAULT: ClassVar[str] = ""

    # ─────────────────── オーバーライド ───────────────────

    def _load_rows(self) -> list[Tag]:
        """list_url の HTML を取得し、データ行をキャッシュ

        - 二重 UTF-8 mojibake (latin-1 解釈 → utf-8 再エンコード) を補正
        - ヘッダ専用 caption-only テーブルを除外し、`<table border='1'>` の
          tbody 内 tr のみを対象にする
        - データ行のうち `<td>` を 1 つ以上持つ行だけを返す
          (ヘッダ行は `<th>` のみで構成されるため自動的に除外される)
        """
        if self._rows_cache is not None:
            return self._rows_cache

        if self._html_cache is None:
            self._html_cache = self._http_get(self.site_config.list_url)

        html = self._html_cache
        # mojibake 検出: 本文に「青森」も「動物」も含まれない場合のみ
        # latin-1 → shift_jis 復元を試みる (UTF-8 保存された SJIS バイト列)。
        if "青森" not in html and "動物" not in html:
            for codec in ("shift_jis", "cp932"):
                try:
                    html = self._html_cache.encode("latin-1").decode(codec)
                    break
                except (UnicodeEncodeError, UnicodeDecodeError):
                    continue
        # 補正後の HTML を再キャッシュ (画像 URL 正規化等で再利用)
        self._html_cache = html

        soup = BeautifulSoup(html, "html.parser")
        rows: list[Tag] = []
        for tr in soup.select(self.ROW_SELECTOR):
            if not isinstance(tr, Tag):
                continue
            # ヘッダ行 (`<th>` のみで `<td>` を持たない) は除外
            if tr.find("td") is None:
                continue
            rows.append(tr)
        self._rows_cache = rows
        return rows

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        """動物リスト取得 (在庫 0 件でも ParsingError を出さない)"""
        rows = self._load_rows()
        category = self.site_config.category
        return [(f"{self.site_config.list_url}#row={i}", category) for i in range(len(rows))]

    def extract_animal_details(
        self, virtual_url: str, category: str = "sheltered"
    ) -> RawAnimalData:
        """1 行の `<tr>` から RawAnimalData を構築する

        セル順序は本モジュール冒頭のドキュメント参照。
        """
        rows = self._load_rows()
        idx = self._parse_row_index(virtual_url)
        if idx >= len(rows):
            raise ParsingError(
                f"row index {idx} out of range (total {len(rows)})",
                url=virtual_url,
            )
        row = rows[idx]
        cells = [c for c in row.find_all(["td", "th"]) if isinstance(c, Tag)]

        species = self._extract_species(cells)
        shelter_date = self._cell_text(cells, 1)
        location = self._cell_text(cells, 2, separator=" ")
        color = self._cell_text(cells, 4)
        sex = self._normalize_sex(self._cell_text(cells, 5))
        size = self._cell_text(cells, 6)
        phone_raw = self._cell_text(cells, 9, separator=" ")
        phone = self._normalize_phone(phone_raw)
        image_urls = self._extract_row_images(row, virtual_url)

        try:
            return RawAnimalData(
                species=species,
                sex=sex,
                age="",
                color=color,
                size=size,
                shelter_date=shelter_date or self.SHELTER_DATE_DEFAULT,
                location=location,
                phone=phone,
                image_urls=image_urls,
                source_url=virtual_url,
                category=category,
            )
        except Exception as e:
            raise ParsingError(f"RawAnimalData バリデーション失敗: {e}", url=virtual_url) from e

    def _filter_image_urls(self, urls: list[str], base_url: str) -> list[str]:
        """`Shuyoimg/` 配下の画像のみを残す (基底の uploads 規約は使わない)"""
        filtered = [u for u in urls if "/Shuyoimg/" in u or "Shuyoimg/" in u]
        return filtered if filtered else urls

    # ─────────────────── ヘルパー ───────────────────

    @staticmethod
    def _cell_text(cells: list[Tag], idx: int, *, separator: str = "") -> str:
        """指定インデックスのセルからテキストを取り出す (範囲外は空文字)

        セル内に子要素として後続 td/p/br がぶら下がるケースがあるため、
        直接の子テキストノードのみを連結する。これにより先頭 td が
        閉じタグ欠落で後続セルを内包していても、自身の `<p>` タグ群だけが
        対象になる。
        """
        if idx >= len(cells):
            return ""
        cell = cells[idx]
        # 直接の子テキスト + 直下の `<p>` のみを拾う。
        # 入れ子された後続 td (パーサが補完したもの) は除外する。
        parts: list[str] = []
        for child in cell.children:
            if isinstance(child, Tag):
                if child.name == "td":
                    # 入れ子された後続セル (閉じタグ欠落の副作用) は無視
                    continue
                if child.name in ("p", "span", "br", "a", "strong", "em", "div"):
                    text = child.get_text(separator=separator, strip=True)
                    if text:
                        parts.append(text)
            else:
                text = str(child).strip()
                if text:
                    parts.append(text)
        joined = separator.join(parts) if separator else "".join(parts)
        return joined.replace("　", " ").strip()

    @staticmethod
    def _extract_species(cells: list[Tag]) -> str:
        """先頭セル `<p>1</p><p>犬</p>` から動物種別を抽出する

        値は通常「犬」または「ねこ」(=「猫」)。判定不能時は「その他」。
        """
        if not cells:
            return "その他"
        head = cells[0]
        # 先頭 td の直下にある全 `<p>` の文字列を集める
        # (閉じタグ欠落で後続 td が入れ子されているため `recursive=True` は危険)
        texts: list[str] = []
        for p in head.find_all("p", recursive=False):
            t = p.get_text(strip=True)
            if t:
                texts.append(t)
        joined = " ".join(texts)
        if "犬" in joined:
            return "犬"
        if "猫" in joined or "ねこ" in joined or "ネコ" in joined:
            return "猫"
        return "その他"

    @staticmethod
    def _normalize_sex(raw: str) -> str:
        """雄/雌 (および 男/女・オス/メス) を一貫した表記に揃える

        正規化処理は normalizer 側でも行うが、生データが「雄」のような
        漢字一文字の場合に下流が混乱しないよう adapter 段階でも揃える。
        """
        if not raw:
            return ""
        s = raw.strip()
        if s in ("雄", "オス", "♂", "男", "おす"):
            return "オス"
        if s in ("雌", "メス", "♀", "女", "めす"):
            return "メス"
        return s

    def _extract_row_images(self, row: Tag, base_url: str) -> list[str]:
        """行内の `<img>` から `src` を絶対 URL のリストに変換する

        `Shuyoimg/...` の相対パスを `list_url` 起点の絶対 URL にする。
        """
        urls: list[str] = []
        seen: set[str] = set()
        for img in row.find_all("img"):
            src = img.get("src")
            if not src or not isinstance(src, str):
                continue
            absolute = self._absolute_url(src, base=self.site_config.list_url)
            if absolute in seen:
                continue
            seen.add(absolute)
            urls.append(absolute)
        return self._filter_image_urls(urls, base_url)


# ─────────────────── サイト登録 ───────────────────
SiteAdapterRegistry.register("青森県動物愛護センター（収容情報）", AomoriAnimalAdapter)
