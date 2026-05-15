"""新潟県動物愛護センター rule-based adapter

対象ドメイン: https://www.pref.niigata.lg.jp/sec/seikatueisei/...

特徴:
- 1 ページに犬/猫の保護動物が `<div class="detail_free">` ブロックで
  並ぶ single_page 形式。個別 detail ページは存在しない。
- 各動物ブロックの先頭は `<h3>犬</h3>` または `<h3>猫</h3>` の見出しで
  始まる (種別判定はこの見出しから行う)。
  「返還の際に必要な物」「関連情報」など他の見出しを持つ
  `detail_free` ブロックは動物データではないので除外する。
- ブロック内の段落構成 (典型例):
    <p><img ...><img ...></p>                  ← 画像（複数）
    <p><strong>26長MC007</strong></p>           ← 管理番号
    <p>5月13日 長岡市乙吉地内で保護</p>          ← 収容日 + 場所
    <p>MIX、オス(未去勢)、白茶、しま模様の尻尾、体重3.6Kg、装着物なし</p>
                                                 ← 属性（種類/性別/毛色 等を「、」区切り）
    <p>4月28日から長岡市乙吉地内を徘徊していました...</p>
                                                 ← 補足説明（無視）
- 収容日表記は "M月D日" のみで年が省略される。fixture / 実運用とも
  「現在年に最も近い過去の月日」を採用する単純なヒューリスティクスで
  ISO 化する (将来またぐ場合は前年扱い)。
- 電話番号はページフッタの `<span class="sf_tel">Tel：0258-21-5501</span>`
  から抽出する (各動物ブロックには記載なし)。
- 新潟県の HTML は fixture 上で UTF-8 バイト列を Latin-1 と誤認して
  再 UTF-8 化された二重エンコーディング (mojibake) になっているケースが
  ある。`_load_rows` で「新潟県」が含まれていないときに限り逆変換を試みる。
- 在庫 0 件 (動物ブロック無し) でも ParsingError を出さず空リストを返す。
"""

from __future__ import annotations

import datetime as _dt
import re
from typing import ClassVar

from bs4 import BeautifulSoup, Tag

from ....domain.models import RawAnimalData
from ...municipality_adapter import ParsingError
from ..registry import SiteAdapterRegistry
from ..single_page_table import SinglePageTableAdapter

# 「M月D日」(全角/半角どちらでも) を抽出する正規表現
_DATE_RE = re.compile(r"(\d{1,2})\s*月\s*(\d{1,2})\s*日")
# 「で保護」「で収容」「を保護」等の場所抽出用
_LOCATION_RE = re.compile(r"\d{1,2}\s*月\s*\d{1,2}\s*日\s*(.+?)(?:で保護|で収容|を保護|を収容)")
# フッタ電話番号 ("Tel:0258-21-5501" / "Tel：0258-21-5501")
_PHONE_RE = re.compile(r"Tel\s*[：:]\s*(\d{2,4}-\d{1,4}-\d{4})")

# 動物見出しと種別の対応
_SPECIES_HEADINGS: dict[str, str] = {
    "犬": "犬",
    "猫": "猫",
}


class PrefNiigataAdapter(SinglePageTableAdapter):
    """新潟県動物保護管理センター用 rule-based adapter

    1 ページ内の `<div class="detail_free">` ブロックのうち、先頭の
    `<h3>` が「犬」または「猫」のものだけを動物データとして扱う。
    """

    # 行候補は detail_free ブロック (動物見出し判定は _load_rows で実施)
    ROW_SELECTOR: ClassVar[str] = "div.detail_free"
    SKIP_FIRST_ROW: ClassVar[bool] = False
    # 基底の cells ベース既定実装は使わない (<p> ベース解析のため宣言だけ)
    COLUMN_FIELDS: ClassVar[dict[int, str]] = {}
    LOCATION_COLUMN: ClassVar[int | None] = None
    SHELTER_DATE_DEFAULT: ClassVar[str] = ""

    # ─────────────────── オーバーライド ───────────────────

    def _load_rows(self) -> list[Tag]:
        """list_url の HTML を取得し、動物 detail_free ブロックをキャッシュ

        - 二重 UTF-8 mojibake (latin-1 解釈 → utf-8 再エンコード) を補正
        - 先頭 `<h3>` テキストが「犬」「猫」と一致するブロックのみ採用
        """
        if self._rows_cache is not None:
            return self._rows_cache

        if self._html_cache is None:
            self._html_cache = self._http_get(self.site_config.list_url)

        html = self._html_cache
        # mojibake 検出: ページに「新潟県」が含まれない場合のみ逆変換を試みる
        if "新潟県" not in html:
            try:
                html = html.encode("latin-1").decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass

        # 補正後の HTML をフッタ電話番号抽出にも使うため保持
        self._decoded_html: str = html

        soup = BeautifulSoup(html, "html.parser")
        rows: list[Tag] = []
        for block in soup.select(self.ROW_SELECTOR):
            if not isinstance(block, Tag):
                continue
            h3 = block.find("h3")
            if not isinstance(h3, Tag):
                continue
            heading = h3.get_text(strip=True).replace("\xa0", "").strip()
            if heading in _SPECIES_HEADINGS:
                rows.append(block)

        self._rows_cache = rows
        return rows

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        """動物リスト取得 (在庫 0 件でも ParsingError を出さない)

        新潟県のサイトは保護動物が居ない期間でもページ自体は存在するため、
        空リストを返す挙動を許容する。
        """
        rows = self._load_rows()
        category = self.site_config.category
        return [(f"{self.site_config.list_url}#row={i}", category) for i in range(len(rows))]

    def extract_animal_details(
        self, virtual_url: str, category: str = "sheltered"
    ) -> RawAnimalData:
        """`<div class="detail_free">` ブロックから RawAnimalData を構築する"""
        rows = self._load_rows()
        idx = self._parse_row_index(virtual_url)
        if idx >= len(rows):
            raise ParsingError(
                f"row index {idx} out of range (total {len(rows)})",
                url=virtual_url,
            )
        block = rows[idx]

        # 種別 (犬/猫) は h3 見出しから決定
        h3 = block.find("h3")
        heading = ""
        if isinstance(h3, Tag):
            heading = h3.get_text(strip=True).replace("\xa0", "").strip()
        species = _SPECIES_HEADINGS.get(heading, "その他")

        # ブロック内の <p> を順に処理
        paragraphs = [p for p in block.find_all("p", recursive=False) if isinstance(p, Tag)]

        image_urls: list[str] = []
        management_number = ""
        shelter_date = ""
        location = ""
        sex = ""
        color = ""
        size = ""
        age = ""

        for p in paragraphs:
            # (1) 画像段落
            imgs = p.find_all("img")
            if imgs:
                for img in imgs:
                    src = img.get("src")
                    if src and isinstance(src, str):
                        image_urls.append(self._absolute_url(src, base=virtual_url))
                continue

            text = p.get_text(separator="", strip=True)
            if not text:
                continue

            # (2) 管理番号段落: <strong> を含み、年号や場所キーワードを含まない
            if not management_number and p.find("strong") is not None and not _DATE_RE.search(text):
                strong = p.find("strong")
                if isinstance(strong, Tag):
                    management_number = strong.get_text(strip=True)
                continue

            # (3) 日付 + 場所段落: "5月13日 長岡市乙吉地内で保護"
            if not shelter_date and _DATE_RE.search(text) and ("保護" in text or "収容" in text):
                shelter_date = self._parse_shelter_date(text)
                loc_match = _LOCATION_RE.search(text)
                if loc_match:
                    location = loc_match.group(1).strip()
                continue

            # (4) 属性段落: 「、」区切りで種類/性別/毛色/補足が並ぶ
            #     例: "MIX、オス(未去勢)、白茶、しま模様の尻尾、体重3.6Kg、装着物なし"
            if not sex and "、" in text and self._looks_like_attribute_line(text):
                sex_v, color_v, size_v, age_v = self._parse_attribute_line(text)
                sex = sex_v
                color = color_v
                size = size_v
                age = age_v
                continue

            # (5) それ以外 (補足説明) は無視

        # 場所が空の場合は「新潟県」をフォールバックとして付与
        # (location は normalizer 側で都道府県名最低限要求のため)
        if not location:
            location = self.site_config.prefecture or ""

        phone = self._extract_footer_phone()

        try:
            return RawAnimalData(
                species=species,
                sex=sex,
                age=age,
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

    # ─────────────────── ヘルパー ───────────────────

    @staticmethod
    def _parse_shelter_date(text: str) -> str:
        """「5月13日」を含む文字列から ISO 形式 "YYYY-MM-DD" を返す

        年は HTML に明記されないので、`今日の日付` を起点として、
        その月日が今日より未来になる場合は「前年」とみなす単純な
        ヒューリスティクスを採用する (収容日が未来になることはないため)。
        """
        m = _DATE_RE.search(text)
        if not m:
            return ""
        month, day = int(m.group(1)), int(m.group(2))
        today = _dt.date.today()
        year = today.year
        try:
            candidate = _dt.date(year, month, day)
        except ValueError:
            return ""
        if candidate > today:
            try:
                candidate = _dt.date(year - 1, month, day)
            except ValueError:
                return ""
        return candidate.isoformat()

    @staticmethod
    def _looks_like_attribute_line(text: str) -> bool:
        """その行が属性行 (種類/性別/毛色...) っぽいかを判定

        「で保護」「を保護」など日付段落の特徴を含むものは除外。
        性別キーワードまたは「kg」「キロ」「体重」など属性らしい
        トークンを含むものを採用。
        """
        if "保護" in text or "収容" in text:
            return False
        for kw in (
            "オス",
            "メス",
            "雄",
            "雌",
            "性別",
            "体重",
            "Kg",
            "kg",
            "キロ",
            "MIX",
            "雑種",
            "毛色",
            "首輪",
            "装着",
        ):
            if kw in text:
                return True
        return False

    @staticmethod
    def _parse_attribute_line(text: str) -> tuple[str, str, str, str]:
        """属性行から (sex, color, size, age) を抽出する

        例: "MIX、オス(未去勢)、白茶、しま模様の尻尾、体重3.6Kg、装着物なし"
            -> sex="オス(未去勢)", color="白茶", size="3.6Kg", age=""
        色は性別の次のトークンを採用する単純ルール。要素数が足りない
        場合は空文字で埋める。
        """
        parts = [s.strip() for s in text.split("、") if s.strip()]
        sex = ""
        color = ""
        size = ""
        age = ""
        sex_idx = -1
        for i, part in enumerate(parts):
            if any(kw in part for kw in ("オス", "メス", "雄", "雌")):
                sex = part
                sex_idx = i
                break
        if sex_idx >= 0 and sex_idx + 1 < len(parts):
            color = parts[sex_idx + 1]
        # 体重表記から size 候補を取り出す (例: "体重3.6Kg")
        for part in parts:
            m = re.search(r"(?:体重\s*)?(\d+(?:\.\d+)?)\s*[kK][gG]", part)
            if m:
                size = f"{m.group(1)}Kg"
                break
        return sex, color, size, age

    def _extract_footer_phone(self) -> str:
        """フッタの "Tel：0258-21-5501" から電話番号を抽出"""
        html = getattr(self, "_decoded_html", None) or self._html_cache or ""
        if not html:
            return ""
        m = _PHONE_RE.search(html)
        if not m:
            return ""
        return self._normalize_phone(m.group(1))


# ─────────────────── サイト登録 ───────────────────
SiteAdapterRegistry.register("新潟県動物愛護センター（保護動物）", PrefNiigataAdapter)
