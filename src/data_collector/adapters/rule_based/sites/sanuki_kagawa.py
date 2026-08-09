"""さぬき動物愛護センター (pref.kagawa.lg.jp) rule-based adapter

対象 URL: https://www.pref.kagawa.lg.jp/s-doubutuaigo/sanukidouaicenter/jyouto/s04u6e190311095146.html

特徴:
- 香川県さぬき動物愛護センターの「譲渡犬猫」情報ページ。本文中に PDF への
  リンク (`/documents/6103/0805dog.pdf` 等) が並び、各 PDF が一覧表形式で
  複数頭の譲渡候補動物を掲載する。
- 一覧ページ自体が JS で DOM を組み立てるため Playwright で取得する
  (`PlaywrightFetchMixin` を `PdfTableAdapter` と多重継承)。
- PDF は罫線のある表なので `extract_tables()` で読み、管理番号を持つ行を
  1 頭として展開する。列位置はヘッダ行から動的に決める (犬は「大きさ」列が
  あり猫は代わりに「FeLV/FIV」列がある、といった差があるため)。

2026-08-06 の仕様変更 (W001/T032):
  それまでは「PDF 1 本 = 1 頭」として登録しており、犬40頭・猫26頭が載って
  いる PDF が犬1件・猫1件に潰れていた。しかも登録内容は species と施設情報
  以外すべて空で、里親の判断材料になっていなかった。さらに動物ではない
  マイクロチップ登録の案内チラシ (`micro.pdf`) まで1頭として公開していた。
  表を行単位で読む方式に改め、管理番号を持たない PDF は 0 件を返す。

重ね書きへの対処:
  猫 PDF は「譲渡希望者と交渉中です。」が既存セルの上に重ねて描画されており、
  pdfplumber が文字を x 座標順に並べると「譲雑渡種希」のように 1 文字ずつ
  交互に混ざる。フォント名・サイズ・色がすべて同一で属性による分離ができない
  ため、既知の語を含む場合だけ採用し、混線した値は捨てる (誤情報を公開する
  くらいなら空欄にする)。

カバーサイト (1):
- さぬき動物愛護センター（譲渡犬猫）
"""

from __future__ import annotations

import io
import logging
import re
import unicodedata
from typing import ClassVar

from ..pdf_table import PdfTableAdapter
from ..playwright import PlaywrightFetchMixin
from ..registry import SiteAdapterRegistry

logger = logging.getLogger(__name__)

try:
    import pdfplumber
except ImportError:  # pragma: no cover
    pdfplumber = None  # type: ignore[assignment]

# 施設情報 (sites.yaml に記載が無い固定値。香川県公式サイトより)
_CENTER_NAME = "さぬき動物愛護センター"
_CENTER_PHONE = "087-815-2255"

# センター管理番号: 「8中‐D0155」「5西-D0564」「8高-C0017」等。
# 全角ハイフン・全角数字の表記ゆれが実 PDF に混在する。
_MGMT_NUMBER_RE = re.compile(r"[\d０-９]+[中西高東]\s*[-‐−–ー]\s*[DC][\d０-９]{4}")

# 推定生年月日: 「H31.4.1」「R5.11.30」
_BIRTH_RE = re.compile(r"[HRhr]\s*[\d０-９]{1,2}\s*\.\s*[\d０-９]{1,2}\s*\.\s*[\d０-９]{1,2}")

# 掲載日: 「2026年8月5日」
_PUBLISHED_RE = re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")

# 性別。重ね書きで「中でオすス。」のように分解された値を弾くため、
# 「オス」「メス」が連続して現れる場合だけ採用する。
_SEX_RE = re.compile(r"(オス|メス|雄|雌)")

# 品種。同じ理由で既知語を含む場合だけ採用する。
_BREED_WORDS: tuple[str, ...] = ("雑種", "ミックス", "日本猫", "柴", "秋田", "洋猫")

# 大きさ: 「約12ｋｇ」「約1９㎏」。実 PDF は半角 kg・全角 ｋｇ・合字 ㎏ が混在する。
_SIZE_RE = re.compile(r"約\s*[\d０-９]+\s*(?:[kKｋＫ][gGｇＧ]|㎏|キロ)")

# 体重 → 体格の境界 (kg)。他サイトの adapter (福岡・町田・大分・徳島・横須賀・
# 熊本・柏) と同じ 5 / 15 kg を使い、UI の体格フィルタで横断比較できるようにする。
_SIZE_BOUNDARY_SMALL_KG = 5.0
_SIZE_BOUNDARY_LARGE_KG = 15.0

# 毛色として妥当と見なす上限。重ね書きの混線は長い文字列になりやすい。
_COLOR_MAX_LEN = 12

# ヘッダ行の見出しと record キーの対応
_HEADER_MAP: tuple[tuple[str, str], ...] = (
    ("品種", "breed"),
    ("毛色", "color"),
    ("性別", "sex"),
    ("大きさ", "size"),
    ("特徴", "description"),
)


class SanukiKagawaAdapter(PlaywrightFetchMixin, PdfTableAdapter):
    """さぬき動物愛護センター（譲渡犬猫） rule-based adapter

    一覧ページから PDF リンクを抽出し、各 PDF の表を 1 行 = 1 頭に展開する。
    """

    # ─────────────────── Playwright 設定 ───────────────────
    # 実ページは jQuery で本文ブロックを差し込むため、
    # 該当パスのアンカーが現れるまで待機する。
    WAIT_SELECTOR: ClassVar[str | None] = "a[href*='/documents/6103/']"

    # ─────────────────── PdfTable 設定 ───────────────────
    # 別部署の PDF を拾わないよう `/documents/6103/` に限定する。
    PDF_LINK_SELECTOR: ClassVar[str] = "a[href*='/documents/6103/'][href$='.pdf']"

    # ─────────────────── PDF テキスト化 ───────────────────

    def _extract_pdf_text(self, pdf_bytes: bytes) -> str:
        """表を「1 セル = タブ区切り / 1 行 = 改行区切り」の文字列にする

        基底の `extract_text()` は列の区切りを失い、犬の「品種 毛色 性別
        大きさ」が 1 行に連なって復元できなくなる。罫線のある表なので
        `extract_tables()` を使い、列位置を保ったまま `_parse_pdf_text`
        へ渡す。
        """
        if pdfplumber is None:  # pragma: no cover - 環境依存
            return ""

        lines: list[str] = []
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                for table in page.extract_tables():
                    for row in table:
                        cells = [(c or "").replace("\n", " ").strip() for c in row]
                        if any(cells):
                            lines.append("\t".join(cells))
        return "\n".join(lines)

    # ─────────────────── _parse_pdf_text 実装 ───────────────────

    def _parse_pdf_text(self, pdf_text: str) -> list[dict]:
        """表テキストから動物 dict のリストを返す

        ・ヘッダ行 (「管理番号」を含む行) が現れるたびに列位置を取り直す。
          実 PDF はページごとに空列の数が変わり (0805dog.pdf は 10/9/11/10 列)、
          1 ページ目のヘッダを使い回すと 2 ページ目以降の値がずれる
        ・管理番号を持つ行だけを 1 頭として採用する
        ・案内チラシのように管理番号が 1 件も無い PDF は空リストを返す
        """
        if not pdf_text:
            return []

        rows = [line.split("\t") for line in pdf_text.splitlines() if line.strip()]
        species = self._infer_species(pdf_text)
        published = self._extract_published_date(rows)

        records: list[dict] = []
        columns: dict[str, int] = {}
        header_count = 0
        for cells in rows:
            header = self._header_columns(cells)
            if header:
                columns = header
                header_count += 1
                continue
            mgmt = self._find_management_number(cells)
            if mgmt is None:
                continue
            records.append(self._build_record(cells, columns, mgmt, species, published))

        # 本番でのみ size が落ちる事象 (2026-08-07・犬42件中7件) の切り分け用。
        # ヘッダを何回検出したかと最終的な列位置が分かれば、ページごとの
        # 取り直しが効いているかをログだけで判定できる。
        logger.info(
            "[sanuki] PDF パース完了: species=%s rows=%d headers=%d records=%d "
            "last_columns=%s size_filled=%d",
            species or "不明",
            len(rows),
            header_count,
            len(records),
            columns,
            sum(1 for r in records if r.get("size")),
        )
        return records

    # ─────────────────── ヘルパー ───────────────────

    @staticmethod
    def _infer_species(pdf_text: str) -> str:
        """PDF 本文とヘッダから種別を推定する

        本文の「掲載されている犬／猫について」を第一に見る。文言が変わった
        場合に備え、犬にしか無い「フィラリア」列と猫にしか無い「FeLV」列でも
        判定する。
        """
        if "掲載されている犬" in pdf_text or "フィラリア" in pdf_text:
            return "犬"
        if "掲載されている猫" in pdf_text or "FeLV" in pdf_text or "FIV" in pdf_text:
            return "猫"
        return ""

    @staticmethod
    def _extract_published_date(rows: list[list[str]]) -> str:
        """「掲載日： 2026年8月5日」を ISO 形式で返す"""
        for cells in rows[:3]:
            joined = " ".join(cells)
            if "掲載日" not in joined:
                continue
            m = _PUBLISHED_RE.search(joined)
            if m:
                y, mo, d = (int(g) for g in m.groups())
                return f"{y:04d}-{mo:02d}-{d:02d}"
        return ""

    @staticmethod
    def _header_columns(cells: list[str]) -> dict[str, int] | None:
        """ヘッダ行なら「record キー → 列インデックス」を返す

        犬は「大きさ」列を持ち猫は持たない、ページによって空列の数が違う、
        といった差があるため固定インデックスにはしない。ヘッダでなければ
        None を返す。
        """
        if "管理番号" not in "".join(cells):
            return None
        columns: dict[str, int] = {}
        for idx, cell in enumerate(cells):
            for label, key in _HEADER_MAP:
                if label in cell and key not in columns:
                    columns[key] = idx
        return columns or None

    @staticmethod
    def _find_management_number(cells: list[str]) -> str | None:
        """行の先頭寄りのセルから管理番号を取り出す

        「NEW 8中‐D0155」のように前置きが付くことがあるため部分一致で拾う。
        ヘッダ行の「センター 管理番号」は数字を含まないのでマッチしない。
        """
        for cell in cells[:2]:
            m = _MGMT_NUMBER_RE.search(cell)
            if m:
                return m.group(0).replace(" ", "")
        return None

    def _build_record(
        self,
        cells: list[str],
        columns: dict[str, int],
        mgmt: str,
        species: str,
        published: str,
    ) -> dict:
        """1 行ぶんの record dict を作る"""

        def cell(key: str) -> str:
            idx = columns.get(key)
            if idx is None or idx >= len(cells):
                return ""
            return cells[idx].strip()

        description_parts: list[str] = []
        birth = _BIRTH_RE.search(" ".join(cells))
        if birth:
            description_parts.append(f"推定生年月日: {birth.group(0).replace(' ', '')}")
        feature = cell("description")
        if feature:
            description_parts.append(feature)

        size = self._clean_size(cell("size"))
        if not size:
            # 列を特定できなかった / 列位置がずれた場合の保険。「約N kg」は体重に
            # しか現れない形なので、行全体から拾い直しても他の値と紛れない
            # (sex / color / breed は他列の値と紛れうるので同じことはしない)。
            size = self._clean_size(" ".join(cells))
            if size:
                logger.warning(
                    "[sanuki] size を列(index=%s)から取得できず行全体から復元しました: "
                    "mgmt=%s size=%s columns=%s cells=%s",
                    columns.get("size"),
                    mgmt,
                    size,
                    columns,
                    cells,
                )

        return {
            "species": species,
            "sex": self._clean_sex(cell("sex")),
            "age": "",
            "color": self._clean_color(cell("color")),
            "size": size,
            "shelter_date": published,
            "location": _CENTER_NAME,
            "phone": _CENTER_PHONE,
            "breed": self._clean_breed(cell("breed")),
            "management_number": mgmt,
            "description": " ".join(description_parts),
            "image_urls": [],
        }

    @staticmethod
    def _clean_sex(value: str) -> str:
        """「オス 去勢済」→「オス」。重ね書きで分解された値は空にする"""
        m = _SEX_RE.search(value)
        return m.group(1) if m else ""

    @staticmethod
    def _clean_breed(value: str) -> str:
        """既知の品種語を含む場合だけ採用する

        重ね書きの「譲雑渡種希」は「雑種」が連続部分文字列として現れない
        ため、この判定で自然に落ちる。
        """
        for word in _BREED_WORDS:
            if word in value:
                return word
        return ""

    @staticmethod
    def _clean_color(value: str) -> str:
        """毛色として妥当な長さのものだけ採用する"""
        value = value.strip()
        if not value or len(value) > _COLOR_MAX_LEN:
            return ""
        # 重ね書きの混線は句読点を巻き込むことが多い
        if any(ch in value for ch in "。、！"):
            return ""
        return value

    @staticmethod
    def _clean_size(value: str) -> str:
        """「約12ｋｇ」等の体重表記を体格 (小型/中型/大型) に変換する

        生の体重をそのまま返してはいけない。`DataNormalizer._cap_size` は
        「体格語が無く体重情報のみなら size ではない」として捨てる仕様で、
        判定正規表現が半角 kg にしか当たらないため、そのまま返すと
        「約16kg」(半角) は None になり「約3ｋｇ」(全角) だけが素通りする、
        という表記ゆれ依存の歯抜けになる。

        2026-08-07 の本番データがまさにそれで、犬42件のうち DB に size が
        入っていたのは全角表記の7件だけだった。adapter 段では 42/42 取れて
        いたため「本番でのみ落ちる原因不明の問題」と誤認したが、実際は
        normalize 段の仕様どおりの挙動だった (テストを RawAnimalData だけで
        アサートしていて `normalize()` を通していなかったのが原因)。

        体格の境界は他サイトの adapter と揃える。5kg 未満は小型、5〜15kg 未満は
        中型、15kg 以上は大型。全角数字・全角 kg・合字 ㎏ は NFKC で吸収する。
        """
        m = _SIZE_RE.search(value)
        if not m:
            return ""
        normalized = unicodedata.normalize("NFKC", m.group(0))
        num = re.search(r"(\d+(?:\.\d+)?)", normalized)
        if not num:
            return ""
        try:
            kg = float(num.group(1))
        except ValueError:  # pragma: no cover - 正規表現が数値を保証する
            return ""
        if kg < _SIZE_BOUNDARY_SMALL_KG:
            return "小型"
        if kg < _SIZE_BOUNDARY_LARGE_KG:
            return "中型"
        return "大型"


# ─────────────────── サイト登録 ───────────────────
SiteAdapterRegistry.register("さぬき動物愛護センター（譲渡犬猫）", SanukiKagawaAdapter)
