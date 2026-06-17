"""山梨県動物愛護指導センター rule-based adapter

対象ドメイン: https://www.pref.yamanashi.jp/doubutsu/

特徴:
- 同一テンプレート上で 6 サイト (探している/保護されている × 犬/猫/その他)
  を運用しており、URL パターンのみが異なる:
    - https://www.pref.yamanashi.jp/doubutsu/m_dog/index.html (探している犬)
    - https://www.pref.yamanashi.jp/doubutsu/m_cat/index.html (探している猫)
    - https://www.pref.yamanashi.jp/doubutsu/m_other/index.html (探している他)
    - https://www.pref.yamanashi.jp/doubutsu/p_dog/index.html (保護されている犬)
    - https://www.pref.yamanashi.jp/doubutsu/p_cat/index.html (保護されている猫)
    - https://www.pref.yamanashi.jp/doubutsu/p_other/index.html (保護されている他)
- 1 ページに複数動物がカード形式で並ぶ single_page サイト。
  個別 detail ページは存在するが、一覧ページに必要な情報
  (場所/性別/毛色/写真) が全て掲載されているためここでは一覧から抽出する。
- 各動物カードは `<div class="menu_item">` で表現され、内部構造は:
    <div class="menu_item">
      <div class="menu_item_img"><span class="img"><img ... /></span></div>
      <div class="menu_item_cnt">
        <div class="item_link_ttl">
          <p class="txt"><a href="...">{場所}</a></p>
          <p>{性別}</p>
          <p>{毛色}</p>
        </div>
      </div>
    </div>
- テーブル形式ではなく `<p>` の並びで構造化されているため、
  `SinglePageTableAdapter` の `td/th` ベース既定実装ではなく
  `extract_animal_details` をオーバーライドして `<p>` から値を取得する。
- 種別 (犬/猫/その他) と収容/迷子の別は site_config 名と URL から決まり、
  ページ HTML には明示されないため adapter のクラス変数とサイト名から推定する。
- 収容日もページに掲載されないため、`SHELTER_DATE_DEFAULT` を空文字としつつ
  実運用では shelter_date 不明として扱う (RawAnimalData は文字列なので空可)。
"""

from __future__ import annotations

import logging
import re
from typing import ClassVar

from bs4 import BeautifulSoup, Tag

from ....domain.models import RawAnimalData
from ...municipality_adapter import ParsingError
from ..registry import SiteAdapterRegistry
from ..single_page_table import SinglePageTableAdapter

_logger = logging.getLogger(__name__)

# 「種類・体格」「性別」「毛色」「管轄保健所の連絡先」等の見出し直後の
# `<p>` から値を拾うための h2 ラベル → フィールド名マッピング。
# phone は「管轄保健所の連絡先」が正式系統だが、古い detail テンプレート
# (例: `/doubutsu/p_cat/{id}.html`) には存在せず「現在の収容場所及び連絡先」
# のみが phone を持つケースがあり、後者をフォールバックとして許容する。
_DETAIL_H2_LABELS: dict[str, str] = {
    "種類・体格": "_kind_size",
    "管轄保健所の連絡先": "phone",
    "現在の収容場所及び連絡先": "phone_fallback",
    "その他の情報": "_other_info",
}
# 体格表記の正規化用パターン。
# 「猫（雑種）大型」「猫（雑種）・中型」のように全角括弧/中点が token を
# 分割不能にするため、文字列全体から search() で体格語を探す。
# 旧 token 完全一致 + prefix match 戦略では拾えなかった。
# 長い表記 (中型/小型/大型) を先頭、短い表記 (大/中/小) を後尾にして
# 「中」が「中型」を横取りしないように sort 済み。
_SIZE_SEARCH_PATTERN = re.compile(r"(超大型|超小型|大型|中型|小型|その他|[小中大])")
# 体重 → size 推定 (oita_aigo / kumamoto_doubutuaigo と同基準)
# 「3kgくらい」「体重約4kg」のような体重表記から size 推定。
# 「12kg」「12.5kg」「12.5キロ」「キログラム」「U+339F ㎏」「全角ｋｇ」も拾う。
# 山梨「その他の情報」に「体重６ｋｇ」「大型5㎏くらい」のような全角・記号表記が混在。
_WEIGHT_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*(?:kg|キロ|キログラム|㎏)")
# 全角 → 半角の数字・kg 変換テーブル (size 抽出前に正規化)
_FULLWIDTH_NORMALIZE = str.maketrans(
    "０１２３４５６７８９ｋｇＫＧ．",
    "0123456789kgKG.",
)
_WEIGHT_SIZE_SMALL_KG = 5.0
_WEIGHT_SIZE_LARGE_KG = 15.0
# 「子猫」「子犬」は size=「小」、「成犬」「成猫」は推定不可で空のまま
_AGE_KEYWORD_TO_SIZE = {"子猫": "小", "子犬": "小"}
# 「峡東保健所TEL:0553-20-2751」のような「保健所名 + TEL/電話 + 番号」表記。
# サイトには ASCII ハイフン `-` 以外に、全角ハイフン類が混在する:
#   - `ｰ` (U+FF70 HALFWIDTH KATAKANA-HIRAGANA PROLONGED SOUND MARK)
#   - `ー` (U+30FC KATAKANA-HIRAGANA PROLONGED SOUND MARK)
#   - `－` (U+FF0D FULLWIDTH HYPHEN-MINUS)
#   - `‐` (U+2010 HYPHEN)
# これらを区切り文字として受け付ける (内部正規化で ASCII ハイフンへ統一)。
_PHONE_HYPHEN_CLASS = r"[-ｰー－‐]"
_PHONE_PATTERN = re.compile(
    rf"(\d{{2,4}}{_PHONE_HYPHEN_CLASS}\d{{2,4}}{_PHONE_HYPHEN_CLASS}\d{{3,4}})"
)
_PHONE_HYPHEN_NORMALIZE_RE = re.compile(_PHONE_HYPHEN_CLASS)
# 「その他の情報」自由記述から年齢表現を best-effort 抽出する。
# 構造化欄が無いため、ヒット率は限定的だが取れるものは取る。
# 例: "年齢：3才", "推定2歳", "6ヶ月", "5か月くらい"
_AGE_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*(才|歳|ヶ月|か月|カ月|ヵ月)")


class PrefYamanashiAdapter(SinglePageTableAdapter):
    """山梨県動物愛護指導センター用 rule-based adapter

    迷子 (m_*) / 保護 (p_*) × 犬/猫/その他 の 6 サイトで共通テンプレート。
    各動物は `div.menu_item` カードで表現される single_page 形式。
    """

    # 各動物カード
    ROW_SELECTOR: ClassVar[str] = "div.menu_item"
    # ヘッダ相当の行は無いので除外しない
    SKIP_FIRST_ROW: ClassVar[bool] = False
    # `.item_link_ttl > p` の位置に対するフィールドマッピング。
    # extract_animal_details オーバーライドから参照される (基底の cells ベース
    # 既定実装は本サイトでは使わないが、契約として明示的に宣言する)。
    COLUMN_FIELDS: ClassVar[dict[int, str]] = {
        0: "location",  # <p class="txt"><a>{市町村名}</a></p>
        1: "sex",  # <p>{オス|メス|不明}</p>
        2: "color",  # <p>{毛色}</p>
    }
    # location 列のインデックス (上の COLUMN_FIELDS と整合)
    LOCATION_COLUMN: ClassVar[int | None] = 0
    # 山梨県のサイトには収容日表記が無いため空文字で初期化 (不明扱い)
    SHELTER_DATE_DEFAULT: ClassVar[str] = ""

    # ─────────────────── オーバーライド ───────────────────

    def extract_animal_details(self, virtual_url: str, category: str = "adoption") -> RawAnimalData:
        """`<div class="menu_item">` カードから RawAnimalData を構築する

        基底の `td/th` ベース実装ではなく、`.item_link_ttl > p` の並びを
        `COLUMN_FIELDS` のインデックスに従って取り出す。
        """
        rows = self._load_rows()
        idx = self._parse_row_index(virtual_url)
        if idx >= len(rows):
            raise ParsingError(
                f"row index {idx} out of range (total {len(rows)})",
                url=virtual_url,
            )
        card = rows[idx]

        # `.item_link_ttl` 配下の直下 <p> を順序通りに取得
        title_block = card.select_one("div.item_link_ttl")
        paragraphs: list[Tag] = []
        if isinstance(title_block, Tag):
            paragraphs = [
                p for p in title_block.find_all("p", recursive=False) if isinstance(p, Tag)
            ]

        fields: dict[str, str] = {}
        for col_idx, field_name in self.COLUMN_FIELDS.items():
            if col_idx < len(paragraphs):
                # <br> を含む場合があるので separator で結合
                text = paragraphs[col_idx].get_text(separator=" ", strip=True)
                fields[field_name] = text

        location = fields.get("location", "")

        # 動物種別はサイト名から推定 (URL パスでも可だが name の方が確実)
        species = self._infer_species_from_site_name(self.site_config.name)

        # 詳細ページ (`/doubutsu/kt/{section}/{id}.html`) を辿って
        # 一覧カードには無い phone / size / age を補完する。失敗時は空のまま。
        phone, size, age, breed = self._fetch_phone_size_age_from_detail(card, virtual_url)

        try:
            return RawAnimalData(
                species=species,
                sex=fields.get("sex", ""),
                age=age,
                color=fields.get("color", ""),
                size=size,
                # 個体識別: 犬種/品種。「種類・体格」欄から体格語を除いた残り。
                # 旧実装は size のみ抽出し犬種を捨てていた (222 件 breed 欠損)。
                breed=breed,
                shelter_date=self.SHELTER_DATE_DEFAULT,
                location=location,
                phone=phone,
                image_urls=self._extract_row_images(card, virtual_url),
                source_url=virtual_url,
                category=category,
            )
        except Exception as e:
            raise ParsingError(f"RawAnimalData バリデーション失敗: {e}", url=virtual_url) from e

    # ─────────────────── detail 補完 ───────────────────

    def _fetch_phone_size_age_from_detail(
        self, card: Tag, base_url: str
    ) -> tuple[str, str, str, str]:
        """カードの詳細リンクを辿って phone / size / age / breed を抽出する

        実サイト構造 (2026-05 観測):
            <h2>種類・体格</h2><p>{犬種} {体格}</p>
            <h2>管轄保健所の連絡先</h2><p>{保健所名}TEL:{番号}</p>
            <h2>その他の情報</h2><p>... 年齢：3才 ...</p>  ← 記載は任意

        age は構造化欄が無いため「その他の情報」自由記述から
        正規表現で best-effort 抽出する (記載がないカードでは空文字)。
        breed は「種類・体格」欄から体格語を除いた残りを採用する。

        ネットワーク失敗・HTML 構造変化等は致命的でないため、例外は
        握り潰して空文字を返す。
        """
        link = card.select_one("div.item_link_ttl p.txt a")
        if not isinstance(link, Tag):
            return "", "", "", ""
        href = link.get("href")
        if not isinstance(href, str) or not href:
            return "", "", "", ""
        detail_url = self._absolute_url(href, base=base_url)
        try:
            html = self._http_get(detail_url)
        except Exception as e:
            _logger.debug("yamanashi detail fetch failed %s: %s", detail_url, e)
            return "", "", "", ""

        soup = BeautifulSoup(html, "html.parser")
        phone = ""
        phone_fallback = ""
        size = ""
        age = ""
        breed = ""
        for h2 in soup.find_all("h2"):
            if not isinstance(h2, Tag):
                continue
            label = h2.get_text(strip=True)
            target = next(
                (key for key in _DETAIL_H2_LABELS if key in label),
                None,
            )
            if target is None:
                continue
            nxt = h2.find_next_sibling()
            if not isinstance(nxt, Tag):
                continue
            value = nxt.get_text(" ", strip=True)
            if not value:
                continue
            kind = _DETAIL_H2_LABELS[target]
            if kind == "phone":
                extracted = self._extract_phone(value)
                if extracted:
                    phone = extracted
            elif kind == "phone_fallback":
                extracted = self._extract_phone(value)
                if extracted:
                    phone_fallback = extracted
            elif kind == "_kind_size":
                size = self._extract_size_from_kind_size(value)
                breed = self._extract_breed_from_kind_size(value)
            elif kind == "_other_info":
                m = _AGE_PATTERN.search(value)
                if m:
                    age = f"{m.group(1)}{m.group(2)}"
                # 種類・体格 で size が取れなかった場合のみ
                # その他の情報の自由記述から best-effort で抽出
                if not size:
                    size = self._extract_size_from_kind_size(value)
        # 「管轄保健所の連絡先」を優先、無ければ「現在の収容場所及び連絡先」で補完
        return phone or phone_fallback, size, age, breed

    @staticmethod
    def _extract_phone(value: str) -> str:
        """phone 文字列から電話番号を抽出して ASCII ハイフン区切りで返す

        サイト内には ASCII `-` 以外に全角ハイフン (ｰ ー － ‐) が混在するため、
        どちらでマッチした場合も内部で ASCII `-` に統一する。
        マッチしない場合は空文字。
        """
        m = _PHONE_PATTERN.search(value)
        if not m:
            return ""
        return _PHONE_HYPHEN_NORMALIZE_RE.sub("-", m.group(1))

    @classmethod
    def _extract_size_from_kind_size(cls, value: str) -> str:
        """「種類・体格」欄のテキストから size を 3 段階で推定する

        実サイトに見られる多様な表記をカバー (2026-06 調査):
            "トイプードル 中型"           → "中型"  (素直)
            "雑種 小型（3.5kg）"          → "小型"  (注記付き)
            "猫（雑種）大型"               → "大型"  (全角括弧で token 分離不能)
            "猫（雑種）・中型"             → "中型"  (中点区切り)
            "雑種、体重約4kg"             → "小"    (体重 → size 推定)
            "3kgくらい"                    → "小"    (体重単独)
            "子猫"                          → "小"    (年齢キーワード)
            "雑種"                          → ""     (体格情報なし、構造的不可能)
            "柴犬"                          → ""     (犬種のみ)

        優先順位:
        1. 体格語の直接検出 (`_SIZE_SEARCH_PATTERN`)
        2. 体重 → size 推定 (`_WEIGHT_PATTERN` + 5kg/15kg 境界)
        3. 年齢キーワード (子犬/子猫 → "小")
        4. 該当なし → 空文字
        """
        # 全角数字・全角 kg・U+339F ㎏ を半角に正規化してから検索
        value = value.translate(_FULLWIDTH_NORMALIZE)
        m = _SIZE_SEARCH_PATTERN.search(value)
        if m:
            return m.group(1)
        m = _WEIGHT_PATTERN.search(value)
        if m:
            try:
                kg = float(m.group(1))
            except ValueError:
                kg = 0.0
            if kg > 0:
                if kg < _WEIGHT_SIZE_SMALL_KG:
                    return "小"
                if kg < _WEIGHT_SIZE_LARGE_KG:
                    return "中"
                return "大"
        for keyword, size in _AGE_KEYWORD_TO_SIZE.items():
            if keyword in value:
                return size
        return ""

    @classmethod
    def _extract_breed_from_kind_size(cls, value: str) -> str:
        """「種類・体格」欄 (`{犬種} {体格}`) から犬種/品種を抽出する。

        体格語・体重・修飾語を除いた残りを breed とみなす。括弧内に品種が入る
        変種「猫（雑種）大型」は括弧内 (体格/体重でなければ) を採用する。
        品種が判定できない場合は空文字を返す (誤った breed を作らない)。

            "トイプードル 中型"   → "トイプードル"
            "雑種 小型（3.5kg）"  → "雑種"
            "猫（雑種）大型"       → "雑種"
            "雑種、体重約4kg"     → "雑種"
            "柴犬"                → "柴犬"
            "雑種"                → "雑種"
            "3kgくらい" / "子猫"   → ""   (品種情報なし)
        """
        if not value:
            return ""
        text = value.translate(_FULLWIDTH_NORMALIZE)
        text = _WEIGHT_PATTERN.sub("", text)
        for noise in ("体重", "約", "くらい", "ぐらい", "程度"):
            text = text.replace(noise, "")
        candidate = text
        # 括弧内に品種が入る変種を優先 (中身が体格/体重でなければ)
        paren = re.search(r"[（(]\s*([^（）()]+?)\s*[）)]", text)
        if paren:
            inner = paren.group(1).strip()
            if (
                inner
                and not _SIZE_SEARCH_PATTERN.fullmatch(inner)
                and not _WEIGHT_PATTERN.search(inner)
            ):
                candidate = inner
        # 体格語の除去: 長い形は全体から、短い形 (大中小) は末尾のみ
        candidate = re.sub(r"(超大型|超小型|大型|中型|小型|その他)", "", candidate)
        candidate = re.sub(r"[大中小]$", "", candidate)
        # 残存する数値・kg・区切り・空白・括弧を除去
        candidate = re.sub(r"\d+(?:\.\d+)?\s*(?:kg|キロ|キログラム|㎏)?", "", candidate)
        candidate = re.sub(r"[、。・,\s（）()]", "", candidate)
        # 先頭の species 語 (犬/猫/その他) を除去 (例「猫雑種」→「雑種」)。
        # 「柴犬」は 柴 で始まるため影響を受けない。
        candidate = re.sub(r"^(その他|犬|猫)", "", candidate).strip()
        # 年齢キーワードや空は品種ではない
        if not candidate or candidate in ("子犬", "子猫", "成犬", "成猫"):
            return ""
        return candidate

    # ─────────────────── ヘルパー ───────────────────

    @staticmethod
    def _infer_species_from_site_name(name: str) -> str:
        """サイト名から動物種別 (犬/猫/その他) を推定する"""
        if "犬" in name:
            return "犬"
        if "猫" in name:
            return "猫"
        return "その他"


# ─────────────────── サイト登録 ───────────────────
# 同一テンプレート上で運用される 6 サイトを同一 adapter にマップする。
for _site_name in (
    "山梨県（探している犬）",
    "山梨県（探している猫）",
    "山梨県（探している他のペット）",
    "山梨県（保護されている犬）",
    "山梨県（保護されている猫）",
    "山梨県（保護されている他のペット）",
):
    SiteAdapterRegistry.register(_site_name, PrefYamanashiAdapter)
