"""茨城県 PDF 系 rule-based adapter

対象ドメイン: https://www.pref.ibaraki.jp/

茨城県は以下 2 サイトで日次に PDF を公表している:
- 「収容中の動物たち」 (sheltered)
- 「迷い犬・猫情報」 (lost)

いずれも一覧 HTML から PDF リンクを抽出し、各 PDF に複数頭の動物情報が
表または箇条書き形式で記載される。

実装方針:
- `PdfTableAdapter` を継承し、`PDF_LINK_SELECTOR` と `_parse_pdf_text` を実装
- PDF テキストは行ごとに走査し「収容日」が現れた行を新ブロック開始とみなす
- 同一行内に複数フィールドが含まれていても正規表現で個別抽出
- 2 サイトとも同一テンプレート想定のため単一 adapter で Registry 登録

T066 (2026-08-29 実PDF確認): 実際の PDF (`documents/inu0827.pdf` 等) は
先頭に「22-3543」のような管理番号が付き、これが 1 頭分のブロック開始になる
(香川県の「個体管理番号」と同型)。ブロック開始の検出をこの番号にも対応させ、
`source_url` の安定化 (management_number 優先) に使う。

T117 (2026-08-29 実PDF確認): 実 PDF は 1 ページに動物情報が左右 2 列で
並ぶ2段組みレイアウト。基底クラス (`PdfTableAdapter`) の既定実装
(`page.extract_text()` をページ丸ごと呼ぶ) だと、pdfplumber が座標順に
文字列を連結する際に左列と右列の行が交互に混ざり、1 物理行に2頭分の
フィールド (管理番号や収容日が2つ等。例:
`22-3543 市町村名 鉾田市田崎 23-3799 市町村名 茨城町小幡`) が同居して
しまう。本 adapter の正規表現はいずれも `.search()` で行内の最初の一致
だけを拾う実装のため、右列 (2頭目) が丸ごと欠落していた (実測: 143頭中
72頭のみ抽出)。T066時点ではこれを「2段組みテーブル抽出の別バグ・スコープ
外」としていたが、`_extract_pdf_text` をオーバーライドし、ページを左右
半分に `crop()` してから個別に `extract_text()` することで列を分離して
解消した。列分離後のテキストは1段組みと同じ構造になるため
`_parse_pdf_text` 側は変更不要 (T066 の管理番号優先ブロック検出もそのまま
両列に効く)。
"""

from __future__ import annotations

import io
import re
from typing import ClassVar

from ...municipality_adapter import NetworkError, ParsingError
from ..pdf_table import PdfTableAdapter
from ..registry import SiteAdapterRegistry

try:
    import pdfplumber
except ImportError:  # pragma: no cover
    pdfplumber = None  # type: ignore[assignment]

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
    # sites.yaml の pdf_link_pattern と同一。
    #
    # 旧セレクタ `a[href*='kouhyou'][href$='.pdf']` は実サイトの現在の
    # ファイル名 (`documents/inu0827.pdf` / `documents/neko0827.pdf`) と
    # 一致せず、`data/site_baselines.yaml` 上で
    # 「茨城県（収容中の動物たち）」「茨城県（迷い犬・猫情報）」がいずれも
    # consecutive_zero_runs=64 (収集のたび PDF リンク 0 件) になっていた
    # ことを実測で確認した (T117 調査時点)。犬猫別ファイル名の "inu"/"neko"
    # は日付部分 (MMDD) が変わっても残る安定した部分文字列のため、これを
    # 基準にする。年間集計 PDF (`r7syuuyousuu.pdf` 等) は対象外にしたいため
    # `kouhyou` 同様に部分文字列マッチを使う。
    PDF_LINK_SELECTOR: ClassVar[str] = (
        "a[href*='documents/inu'][href$='.pdf'], a[href*='documents/neko'][href$='.pdf']"
    )

    # ─────────────────── _extract_pdf_text 実装 (2段組み対応) ───────────────────

    def _extract_pdf_text(self, pdf_bytes: bytes) -> str:
        """PDF テキストを列ごとに分割してから抽出する

        実 PDF は1ページに動物情報が左右2列で並ぶ2段組みレイアウト。
        ページ中央 (`page.width / 2`) で左右に `crop()` してからそれぞれ
        `extract_text()` することで列を分離する (実測で列間に十分な余白が
        あり、単語がまたがって欠けることは無いことを確認済み)。
        列を分離した状態で連結するため、基底クラスと違い1ページにつき
        テキストブロックが2つ (左列・右列) 生成される。
        """
        if pdfplumber is None:  # pragma: no cover
            raise NetworkError("pdfplumber が利用不可")
        try:
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                blocks: list[str] = []
                for page in pdf.pages:
                    mid_x = page.width / 2
                    left = page.crop((0, 0, mid_x, page.height))
                    right = page.crop((mid_x, 0, page.width, page.height))
                    for column in (left, right):
                        text = column.extract_text()
                        if text:
                            blocks.append(text)
                return "\n\n".join(blocks)
        except Exception as e:
            raise ParsingError(f"PDF テキスト抽出失敗: {e}") from e

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
        ため、取得できていればこちらを優先する。T117 で2段組み PDF の
        右列 (2頭目) も左列と同様に正しく管理番号を取得できるようになった
        ため、取得できない個体は基本的に管理番号の無い旧レイアウトのみに
        限られる。それでも取得できない場合は `_pdf_filename_source_url`
        の (ファイル名+row) にフォールバックする
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
