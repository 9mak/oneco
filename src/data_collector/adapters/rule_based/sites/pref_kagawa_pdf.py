"""香川県保健福祉事務所 PDF 系 rule-based adapter

対象ドメイン: https://www.pref.kagawa.lg.jp/

香川県は 4 つの保健福祉事務所 (東讃 / 中讃 / 西讃 / 小豆) が
それぞれ独立した静的 HTML ページに収容動物情報 PDF を掲載している。
PDF は数頭分の動物情報を表形式または箇条書きで記載しており、
1 PDF から複数の動物 dict を抽出する必要がある。

実装方針:
- 一覧 HTML から `a[href$='.pdf']` 系セレクタで PDF リンクを抽出
- 各 PDF を `_download_pdf` でダウンロードし pdfplumber でテキスト抽出
- `_parse_pdf_text` でテキストを行ごとに走査し、動物 1 頭分の情報が
  揃ったブロックを dict として収集する
- 4 サイト全て同じテンプレート想定のため単一 adapter で Registry 登録
"""

from __future__ import annotations

import re
from typing import ClassVar

from ..pdf_table import PdfTableAdapter
from ..registry import SiteAdapterRegistry

# ─────────────────── パース用パターン ───────────────────

# 「収容日: 2026年5月12日」「収容日 2026/5/12」「収容日時 2026年5月12日 13:40」など
# (「収容日時」も拾えるよう、ラベル直後の任意文字を許容する)
_SHELTER_DATE_RE = re.compile(
    r"収容日(?:時)?\s*[:：]?\s*"
    r"(\d{4})\s*[年/\-\.]\s*(\d{1,2})\s*[月/\-\.]\s*(\d{1,2})\s*日?"
)

# 実 PDF は和暦表記:「収容日時 令和8年7月31日 13:40」
# 元号は現行の令和のみ扱う (平成以前の収容情報は掲載期間 7 日の運用上ありえない)。
_SHELTER_DATE_WAREKI_RE = re.compile(
    r"収容日(?:時)?\s*[:：]?\s*令和\s*(\d{1,2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日"
)
# 令和元年 = 1<<西暦 2019 年。令和 N 年 = 2018 + N。
_REIWA_EPOCH = 2018

# 「個体管理番号 2630166」— 実 PDF ではこれが 1 頭分のブロック開始になる。
_MGMT_NUMBER_RE = re.compile(r"個体管理番号\s*[:：]?\s*([A-Za-z0-9\-]+)")
# 「動物の種類 犬 種類 雑種 2～3週齢」の「種類 雑種」部分 (品種)。
# 「動物の種類」に先に食われないよう、直前が「物の」でないことを要求する。
_BREED_RE = re.compile(r"(?<!動物の)種類\s*[:：]?\s*([^\s　]+)")
# 「2～3週齢」「6～12か月齢」「推定3歳」など単位付きの年月齢。
_AGE_UNIT_RE = re.compile(r"(\d+\s*[～~\-]?\s*\d*\s*(?:週齢|か月齢|ヶ月齢|カ月齢|歳|才))")
# 「引取り場所 丸亀市 中津町」(実 PDF の場所ラベル)
_PICKUP_LOCATION_RE = re.compile(r"引取り?場所\s*[:：]?\s*([^\n]+?)(?:\s{2,}|$)")
# 「種類: 犬」「種別 猫」など (「収容場所」の "所" と衝突しないよう「種類/種別」のみ)
_SPECIES_RE = re.compile(r"(?:種類|種別)\s*[:：]?\s*(犬|猫|その他|[^\s]+)")
# 「性別: オス」
_SEX_RE = re.compile(r"性別\s*[:：]?\s*([^\s　]+)")
# 「年齢: 推定3歳」「年齢 成犬」など
_AGE_RE = re.compile(r"年齢\s*[:：]?\s*([^\s　]+)")
# 「毛色: 白黒」
_COLOR_RE = re.compile(r"毛色\s*[:：]?\s*([^\s　]+)")
# 「体格: 中」「大きさ: 中型」
_SIZE_RE = re.compile(r"(?:体格|大きさ)\s*[:：]?\s*([^\s　]+)")
# 「収容場所: ○○市△△町」
_LOCATION_RE = re.compile(r"収容場所\s*[:：]?\s*([^\n]+?)(?:\s{2,}|$)")


class PrefKagawaPdfAdapter(PdfTableAdapter):
    """香川県保健福祉事務所 (4 所) PDF 用 rule-based adapter"""

    # 一覧ページから PDF リンクを抽出するセレクタ
    # 4 事務所いずれも `a[href$='.pdf']` で網羅できる構造
    PDF_LINK_SELECTOR: ClassVar[str] = "a[href$='.pdf']"

    # ─────────────────── _parse_pdf_text 実装 ───────────────────

    def _parse_pdf_text(self, pdf_text: str) -> list[dict]:
        """PDF テキストから動物 dict のリストを抽出する

        ・収容日が現れた行を新しい動物ブロックの開始とみなす
        ・以降の行から ラベル付きフィールド (種類/性別/年齢/毛色/体格/収容場所)
          を正規表現で取り出す
        ・次の収容日が現れた時点で前のブロックを確定して dict 化する
        """
        if not pdf_text:
            return []

        records: list[dict] = []
        current: dict | None = None

        # PDF の連続改行を整理して 1 行ずつ処理
        lines = [ln.strip() for ln in pdf_text.splitlines() if ln.strip()]

        for line in lines:
            # 実 PDF は「個体管理番号」が 1 頭分の先頭に来る。
            # 収容日より前に現れるため、こちらを優先してブロックを切る。
            mgmt_match = _MGMT_NUMBER_RE.search(line)
            if mgmt_match:
                if current is not None and self._is_record_valid(current):
                    records.append(current)
                current = self._new_record()
                current["management_number"] = mgmt_match.group(1)
                continue

            shelter_match = _SHELTER_DATE_RE.search(line)
            wareki_match = None if shelter_match else _SHELTER_DATE_WAREKI_RE.search(line)
            if shelter_match or wareki_match:
                if shelter_match:
                    y, mo, d = (int(g) for g in shelter_match.groups())
                else:
                    era_year, mo, d = (int(g) for g in wareki_match.groups())  # type: ignore[union-attr]
                    y = _REIWA_EPOCH + era_year
                iso_date = f"{y:04d}-{mo:02d}-{d:02d}"

                if current is not None and not current.get("shelter_date"):
                    # 個体管理番号で開始済みのブロックに収容日を足す
                    current["shelter_date"] = iso_date
                else:
                    # 管理番号を持たない旧レイアウト: 収容日がブロック開始
                    if current is not None and self._is_record_valid(current):
                        records.append(current)
                    current = self._new_record()
                    current["shelter_date"] = iso_date
                # 同一行に他フィールドが含まれている場合も後続パターンで拾う
                # (continue せずに下記の各種マッチへフォールスルー)

            if current is None:
                # 収容日 / 管理番号より前の見出し行などはスキップ。
                # 「掲載開始： 令和8年8月1日」等はここで捨てられる。
                continue

            self._extract_field(line, current)

        # ループ後に残った最後のブロックを確定
        if current is not None and self._is_record_valid(current):
            records.append(current)

        return records

    @staticmethod
    def _new_record() -> dict:
        """空の動物レコードを作る"""
        return {
            "species": "",
            "sex": "",
            "age": "",
            "color": "",
            "size": "",
            "shelter_date": "",
            "location": "",
            "breed": "",
            "management_number": "",
        }

    # ─────────────────── ヘルパー ───────────────────

    @staticmethod
    def _extract_field(line: str, record: dict) -> None:
        """1 行から各属性を抽出し record を埋める (空欄のみ上書き)

        実 PDF は「動物の種類 犬 種類 雑種 2～3週齢」のように 1 行へ複数の
        フィールドが並ぶため、各パターンを同じ行に対して順に当てる。
        """
        for key, pattern in (
            ("species", _SPECIES_RE),
            ("breed", _BREED_RE),
            ("sex", _SEX_RE),
            # ラベル付き (「年齢: 推定3歳」) を優先し、ラベルが無い実 PDF の
            # 「2～3週齢」のみ単位パターンで拾う。逆順にすると「推定」が落ちる。
            ("age", _AGE_RE),
            ("age", _AGE_UNIT_RE),
            ("color", _COLOR_RE),
            ("size", _SIZE_RE),
            ("location", _PICKUP_LOCATION_RE),
            ("location", _LOCATION_RE),
        ):
            if record.get(key):
                continue
            m = pattern.search(line)
            if m:
                record[key] = m.group(1).strip()

    @staticmethod
    def _is_record_valid(record: dict) -> bool:
        """少なくとも収容日と他 1 つ以上のフィールドが埋まっていれば有効"""
        if not record.get("shelter_date"):
            return False
        return any(record.get(k) for k in ("species", "sex", "age", "color", "size", "location"))


# ─────────────────── サイト登録 ───────────────────
# 4 つの香川県保健福祉事務所 PDF サイトを同一 adapter にマップ
for _site_name in (
    "東讃保健福祉事務所（収容動物）",
    "中讃保健福祉事務所（収容動物）",
    "西讃保健福祉事務所（収容動物）",
    "小豆保健所（収容動物）",
):
    SiteAdapterRegistry.register(_site_name, PrefKagawaPdfAdapter)
