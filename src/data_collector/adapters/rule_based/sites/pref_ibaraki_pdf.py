"""茨城県 PDF 系 rule-based adapter

対象ドメイン: https://www.pref.ibaraki.jp/

茨城県は以下 2 サイトで日次に PDF を公表している:
- 「収容中の動物たち」 (sheltered)
- 「迷い犬・猫情報」 (lost)

いずれも一覧 HTML から `a[href*='kouhyou'][href$='.pdf']` で PDF リンクを
抽出し、各 PDF に複数頭の動物情報が表または箇条書き形式で記載される。

実装方針:
- `PdfTableAdapter` を継承し、`PDF_LINK_SELECTOR` と `_parse_pdf_text` を実装
- PDF テキストは行ごとに走査し「収容日」が現れた行を新ブロック開始とみなす
- 同一行内に複数フィールドが含まれていても正規表現で個別抽出
- 2 サイトとも同一テンプレート想定のため単一 adapter で Registry 登録

T066 (2026-08-29 実PDF確認): 実際の PDF (`documents/inu0827.pdf` 等) は
先頭に「22-3543」のような管理番号が付き、これが 1 頭分のブロック開始になる
(香川県の「個体管理番号」と同型)。ブロック開始の検出をこの番号にも対応させ、
`source_url` の安定化 (management_number 優先) に使う。
実 PDF は 2 段組みで、同じ物理行に 2 頭分のフィールドが横並びで入っている
(例: `22-3543 市町村名 鉾田市田崎 23-3799 市町村名 茨城町小幡`)。
本 adapter の正規表現はいずれも `.search()` で行内の最初の一致だけを拾う
実装のため、右列 (2 頭目) のデータはブロックとして起票されず欠落する
既知の別問題がある (2026-08-29 実 PDF 検証で 143 頭中 72 頭のみ抽出を確認)。
これは 2 段組みテーブル抽出の別バグであり T066 のスコープ外
(source_url 安定化) のため本修正では着手しない。
"""

from __future__ import annotations

import re
from typing import ClassVar

from ..pdf_table import PdfTableAdapter
from ..registry import SiteAdapterRegistry

# ─────────────────── パース用パターン ───────────────────

# 「収容日: 2026年5月12日」「収容年月日 2026/5/12」など
_SHELTER_DATE_RE = re.compile(
    r"収容(?:年月)?日\s*[:：]?\s*"
    r"(\d{4})\s*[年/\-\.]\s*(\d{1,2})\s*[月/\-\.]\s*(\d{1,2})\s*日?"
)
# 「種類: 犬」「種別 猫」「動物種 犬」など
_SPECIES_RE = re.compile(r"(?:種類|種別|動物種)\s*[:：]?\s*(犬|猫|その他|[^\s　]+)")
# 「性別: オス」
_SEX_RE = re.compile(r"性別\s*[:：]?\s*([^\s　]+)")
# 「年齢: 推定3歳」「年齢 成犬」など
_AGE_RE = re.compile(r"年齢\s*[:：]?\s*([^\s　]+)")
# 「毛色: 白黒」「色: 茶」
_COLOR_RE = re.compile(r"(?:毛色|色)\s*[:：]?\s*([^\s　]+)")
# 「体格: 中」「大きさ: 中型」「体重: 5kg」
_SIZE_RE = re.compile(r"(?:体格|大きさ|体重)\s*[:：]?\s*([^\s　]+)")
# 「収容場所: ○○市△△町」「発見場所: ○○市」
_LOCATION_RE = re.compile(r"(?:収容場所|発見場所|保護場所)\s*[:：]?\s*([^\n]+?)(?:\s{2,}|$)")
# 「22-3543 市町村名 鉾田市田崎」— 実 PDF (T066 確認) ではこれが 1 頭分の
# ブロック開始になる。「市町村名」の直前という文脈で固定し、本文中の他の
# 数字 (収容日の年など) を誤って拾わないようにする。
_MGMT_NUMBER_RE = re.compile(r"(\d{2}-\d{3,6})(?=\s*市町村名)")


class PrefIbarakiPdfAdapter(PdfTableAdapter):
    """茨城県 (収容中の動物たち / 迷い犬・猫情報) PDF 用 rule-based adapter"""

    # 一覧ページから PDF リンクを抽出するセレクタ
    # sites.yaml の pdf_link_pattern と同一: kouhyou を含む .pdf リンク
    PDF_LINK_SELECTOR: ClassVar[str] = "a[href*='kouhyou'][href$='.pdf']"

    # ─────────────────── _parse_pdf_text 実装 ───────────────────

    def _parse_pdf_text(self, pdf_text: str) -> list[dict]:
        """PDF テキストから動物 dict のリストを抽出する

        ・管理番号 (例: 「22-3543」) が現れた行を新しい動物ブロックの開始と
          みなす。管理番号が無い旧レイアウトでは収容日をブロック開始とする
          (香川県 adapter と同じ二段構え。T066)
        ・以降の行から ラベル付きフィールド (種類/性別/年齢/毛色/体格/収容場所)
          を正規表現で取り出す
        ・次の管理番号 (または収容日) が現れた時点で前のブロックを確定する
        """
        if not pdf_text:
            return []

        records: list[dict] = []
        current: dict | None = None

        # PDF の連続改行を整理して 1 行ずつ処理
        lines = [ln.strip() for ln in pdf_text.splitlines() if ln.strip()]

        for line in lines:
            # 実 PDF は管理番号が 1 頭分の先頭に来る (収容日より前)。
            # こちらを優先してブロックを切る。
            mgmt_match = _MGMT_NUMBER_RE.search(line)
            if mgmt_match:
                if current is not None and self._is_record_valid(current):
                    records.append(current)
                current = self._new_record()
                current["management_number"] = mgmt_match.group(1)
                continue

            shelter_match = _SHELTER_DATE_RE.search(line)
            if shelter_match:
                y, mo, d = (
                    shelter_match.group(1),
                    shelter_match.group(2),
                    shelter_match.group(3),
                )
                iso_date = f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
                if current is not None and not current.get("shelter_date"):
                    # 管理番号で開始済みのブロックに収容日を足す
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
                # 収容日/管理番号より前の見出し行などはスキップ
                continue

            self._extract_field(line, current)

        # ループ後に残った最後のブロックを確定
        if current is not None and self._is_record_valid(current):
            records.append(current)

        return records

    # ─────────────────── ヘルパー ───────────────────

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
            "management_number": "",
        }

    @staticmethod
    def _extract_field(line: str, record: dict) -> None:
        """1 行から各属性を抽出し record を埋める (空欄のみ上書き)"""
        for key, pattern in (
            ("species", _SPECIES_RE),
            ("sex", _SEX_RE),
            ("age", _AGE_RE),
            ("color", _COLOR_RE),
            ("size", _SIZE_RE),
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

    # ─────────────────── source_url (T066) ───────────────────

    def _public_source_url(self, pdf_url: str, idx: int) -> str:
        """管理番号があれば安定キーとして source_url に使う

        茨城県の PDF ファイル名も自治体側の日次差し替えで毎日変わる
        (例: `inu0827.pdf` → `inu0828.pdf`)。管理番号 (例: `22-3543`) は
        自治体が個体ごとに割り振る一意 ID で PDF 差し替えの影響を受けない
        ため、取得できていればこちらを優先する。取得できない個体 (管理番号
        の無い旧レイアウトや、2 段組み PDF の右列など) は
        `_pdf_filename_source_url` の (ファイル名+row) にフォールバックする
        (このフォールバックはこれまで通り不安定)。
        """
        records = self._pdf_cache.get(pdf_url) or []
        management_number = records[idx].get("management_number", "") if idx < len(records) else ""
        if management_number:
            return f"{self.site_config.list_url}#animal={management_number}"
        return self._pdf_filename_source_url(pdf_url, idx)


# ─────────────────── サイト登録 ───────────────────
# 茨城県の 2 サイトを同一 adapter にマップ
for _site_name in (
    "茨城県（収容中の動物たち）",
    "茨城県（迷い犬・猫情報）",
):
    SiteAdapterRegistry.register(_site_name, PrefIbarakiPdfAdapter)
