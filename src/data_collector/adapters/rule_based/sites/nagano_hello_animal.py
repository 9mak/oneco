"""長野県動物愛護センター（ハローアニマル）譲渡情報 rule-based adapter

対象ドメイン: https://www.pref.nagano.lg.jp/dobutsuaigo/joto/inu-neko/inu.html

実構造 (2026-05-29 確認):
- single_page 形式。1ページに譲渡希望の犬 (or 猫) が複数掲載される
- 動物ブロック:
  - 「飼い主募集中の犬の情報」/「飼い主募集中の猫の情報」 h2 配下
  - 1動物 = `<div class="section">` (h3 で動物名 + フリーテキストで属性)
- 動物属性のフォーマット:
  - 種類：ミックス（薄茶）  ← 括弧内が毛色
  - 性別：オス（去勢済み）
  - 生年月：2021年5月頃生まれ ← 生年月から DataNormalizer が月数推定
  - 備考：体重16kg前後で中型犬...
- 「県内保健所（保健福祉事務所）の情報」h2 以降は別セクションなので除外
  (各保健所ページへのリンク集で、個別動物データは含まない)

47都道府県カバー完成のための新規追加 (2026-05-29)。
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup, NavigableString, Tag

from ....domain.models import AnimalData, RawAnimalData
from ...municipality_adapter import ParsingError
from ..base import RuleBasedAdapter
from ..registry import SiteAdapterRegistry

# 動物ブロックの開始 h2 (犬: 「…の情報」/ 猫: 「…の詳細」と表記揺れあり)
_ACTIVE_HEADING_RE = re.compile(r"飼い主募集中の(?:犬|猫|動物)")
# 動物ブロックの終端 h2 (この見出し以降は別セクション)
_END_HEADING_RE = re.compile(r"県内保健所|保健福祉事務所")

# 各動物ブロック内のラベル抽出パターン
_FIELD_PATTERNS: dict[str, re.Pattern[str]] = {
    # 種類：ミックス（薄茶）→ 「ミックス（薄茶）」全体を species 候補に
    # (DataNormalizer は「犬/猫」キーワードで判定するため、ここでは
    # 補助情報として保持し、species 本体は site name 推定で確実に犬/猫を入れる)
    "species_label": re.compile(r"種類[：:]\s*([^\n]+)"),
    "sex": re.compile(r"性別[：:]\s*([^\n]+)"),
    # 生年月：2021年5月頃生まれ → DataNormalizer の生年月パース対象
    "age": re.compile(r"生年月[：:]\s*([^\n]+)"),
    # 備考から体格を緩く拾う（「中型犬」「小型犬」「大型犬」を含むかどうか）
    "size_hint": re.compile(r"備考[：:][^\n]*?(小型犬|中型犬|大型犬)"),
}

# 種類フィールド内の「（…）」毛色情報を抽出 (例: ミックス（薄茶） → 薄茶)
_COLOR_IN_SPECIES_RE = re.compile(r"[（(]([^）)]+)[）)]")
# 種類フィールド内の括弧前のテキスト (品種名相当、normalizer の species 判定材料)
_BREED_BEFORE_PAREN_RE = re.compile(r"^([^（(]+)")


class NaganoHelloAnimalAdapter(RuleBasedAdapter):
    """長野県動物愛護センター（ハローアニマル）譲渡情報 single_page adapter

    /inu-neko/inu.html (譲渡犬) と /inu-neko/neko.html (譲渡猫) を扱う。
    「飼い主募集中の犬／猫の情報」h2 配下の `<div class="section">` を
    1動物として抽出。各ブロックの h3 が動物名、後続テキストが属性。
    """

    # 全動物カード共通の連絡先電話番号 (2026-06 観測)。
    # ページ末尾に「電話番号：0267-24-5071」とのみ記載され、動物単位の
    # 個別電話番号は無いため、長野県動物愛護センター代表電話を共通注入する。
    _CENTER_TEL = "0267-24-5071"

    def __init__(self, site_config: Any) -> None:
        super().__init__(site_config)
        self._html_cache: str | None = None
        self._blocks_cache: list[dict[str, Any]] | None = None

    # ─────────────────── オーバーライド ───────────────────

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        """list_url HTML から `<div class="section">` 動物ブロックを抽出し
        `#row=N` URL を返す"""
        blocks = self._load_blocks()
        category = self.site_config.category
        base = self.site_config.list_url
        return [(f"{base}#row={i}", category) for i in range(len(blocks))]

    def extract_animal_details(self, virtual_url: str, category: str = "adoption") -> RawAnimalData:
        """#row=N から対応する動物ブロックを取り出し RawAnimalData を構築"""
        blocks = self._load_blocks()
        idx = self._parse_row_index(virtual_url)
        if idx >= len(blocks):
            raise ParsingError(
                f"row index {idx} out of range (total {len(blocks)})",
                url=virtual_url,
            )
        block = blocks[idx]

        # species はサイト名で確実に「犬」or「猫」に倒す
        # (種類フィールドの値は normalizer の判定基準 (犬/猫) を満たさない
        # ことが多い: 「ミックス」「ポメラニアン」など)
        species = self._infer_species_from_site_name(self.site_config.name) or "犬"

        # age は「2021年5月頃生まれ」のような生年月表記。`_normalize_age` の
        # `_parse_birth_date` は YYYY年M月D日 を要求するため、日付を補完して
        # 渡すと月数換算できる。
        age_raw = block.get("age", "")
        age = self._normalize_birth_month_for_age(age_raw)

        try:
            return RawAnimalData(
                species=species,
                sex=block.get("sex", ""),
                age=age,
                color=block.get("color", ""),
                size=block.get("size", ""),
                shelter_date="",  # 譲渡待ちページは収容日相当の情報が無い
                # 大分市と同じく施設名を location に入れる (location 不明回避)
                location="長野県動物愛護センター（ハローアニマル）",
                phone=self._CENTER_TEL,
                image_urls=block.get("image_urls", []) or [],
                source_url=virtual_url,
                category=category,
            )
        except Exception as e:
            raise ParsingError(f"RawAnimalData バリデーション失敗: {e}", url=virtual_url) from e

    def normalize(self, raw_data: RawAnimalData) -> AnimalData:
        """基底の `_default_normalize` (DataNormalizer ベース) に委譲"""
        return self._default_normalize(raw_data)

    # ─────────────────── ブロック抽出 ───────────────────

    def _load_blocks(self) -> list[dict[str, Any]]:
        """list_url HTML から「飼い主募集中」配下の動物ブロックを抽出

        構造のバリエーション:
        - 犬ページ: <div class="section"> 1 つ = 1 動物 (h3=動物名)
        - 猫ページ: <div class="section"> 1 つに複数 h3 (= 複数動物がまとまっている)

        両方に対応するため **h3 ベース** で動物を切り出す。
        「飼い主募集中」h2 → 次の h2 (= 別セクション) までの DOM 範囲内で、
        全ての h3 を 1 動物の起点とし、次の h3 (or 範囲終端) までのテキストを
        1 動物のテキストとして field 抽出する。

        各 block には属性辞書に加えて、h3 ～ 次 h3 までの DOM 範囲に含まれる
        `<img src=...>` を絶対 URL 化した `image_urls` リストを格納する。
        """
        if self._blocks_cache is not None:
            return self._blocks_cache
        if self._html_cache is None:
            self._html_cache = self._http_get(self.site_config.list_url)

        soup = BeautifulSoup(self._html_cache, "html.parser")
        main = soup.select_one("#tmp_contents") or soup

        # 「飼い主募集中…」h2 を起点
        start_h2: Tag | None = None
        for h2 in main.find_all("h2"):
            if _ACTIVE_HEADING_RE.search(h2.get_text(strip=True)):
                start_h2 = h2
                break

        blocks: list[dict[str, Any]] = []
        if start_h2 is None:
            self._blocks_cache = blocks
            return blocks

        # start_h2 以降の最初の h2 を範囲終端 (boundary) とする
        boundary: Tag | None = None
        curr = start_h2
        while True:
            nxt = curr.find_next("h2")
            if nxt is None:
                break
            boundary = nxt
            break

        # DOM 順で start_h2 から boundary までの h3 を集める
        h3_anchors: list[Tag] = []
        elem: Tag | NavigableString | None = start_h2
        while elem is not None:
            elem = elem.find_next(["h2", "h3"]) if isinstance(elem, Tag) else None
            if elem is None or elem is boundary:
                break
            if isinstance(elem, Tag) and elem.name == "h2":
                break
            if isinstance(elem, Tag) and elem.name == "h3":
                h3_anchors.append(elem)

        # 各 h3 → 次の h3 (or boundary) までのテキスト/画像を 1 動物として抽出
        for i, h3 in enumerate(h3_anchors):
            next_anchor: Tag | None = h3_anchors[i + 1] if i + 1 < len(h3_anchors) else boundary
            block_text = self._collect_text_between(h3, next_anchor)
            block: dict[str, Any] = dict(self._extract_block_fields_from_text(block_text))
            if not block:
                continue
            block["image_urls"] = self._collect_images_between(h3, next_anchor)
            blocks.append(block)

        self._blocks_cache = blocks
        return blocks

    def _collect_images_between(self, start: Tag, end: Tag | None) -> list[str]:
        """start (含む) から end (除く) までの `<img src=...>` を絶対 URL で集める

        ハローアニマルの動物ブロックには各動物の写真が <img> で配置される。
        DOM 順にスキャンし、相対 URL は list_url を base にして絶対化する。
        重複は除外する (順序は保持)。
        """
        urls: list[str] = []
        seen: set[str] = set()
        base = self.site_config.list_url
        elem: Tag | NavigableString | None = start
        while elem is not None and elem is not end:
            if isinstance(elem, Tag) and elem.name == "img":
                src = elem.get("src")
                if isinstance(src, str) and src.strip():
                    absolute = urljoin(base, src.strip())
                    if absolute not in seen:
                        seen.add(absolute)
                        urls.append(absolute)
            elem = elem.next_element if hasattr(elem, "next_element") else None
        return urls

    @staticmethod
    def _normalize_birth_month_for_age(age_raw: str) -> str:
        """「2021年5月頃生まれ」を normalizer が解釈可能な形に整形する

        `DataNormalizer._parse_birth_date` の「YYYY年M月D日」パターンに合わせて
        日付 (1日) を補完する。元の文字列に既に「日」が含まれている場合は
        そのまま返す (フォーマット重複を避ける)。
        """
        if not age_raw:
            return ""
        # 既に YYYY年M月D日 が含まれているなら追加処理は不要
        if re.search(r"\d{4}年\d{1,2}月\d{1,2}日", age_raw):
            return age_raw
        m = re.search(r"(\d{4})年(\d{1,2})月", age_raw)
        if not m:
            return age_raw
        return f"{m.group(1)}年{m.group(2)}月1日"

    @staticmethod
    def _collect_text_between(start: Tag, end: Tag | None) -> str:
        """start (含む) から end (除く) までの DOM 順 NavigableString を結合"""
        parts: list[str] = []
        elem: Tag | NavigableString | None = start
        while elem is not None and elem is not end:
            if isinstance(elem, NavigableString):
                t = str(elem).strip()
                if t:
                    parts.append(t)
            elem = elem.next_element if hasattr(elem, "next_element") else None
        return "\n".join(parts)

    @staticmethod
    def _extract_block_fields_from_text(text: str) -> dict[str, str]:
        """1 動物分のテキストから動物属性を抽出 (大分市と同じ正規表現アプローチ)"""
        fields: dict[str, str] = {}
        for fld, pat in _FIELD_PATTERNS.items():
            m = pat.search(text)
            if not m:
                continue
            value = m.group(1).strip()
            if fld == "species_label":
                # 「ミックス（薄茶）」の括弧内を color として取る
                color_m = _COLOR_IN_SPECIES_RE.search(value)
                if color_m and "color" not in fields:
                    fields["color"] = color_m.group(1).strip()
            elif fld == "size_hint":
                fields["size"] = value
            else:
                fields[fld] = value
        return fields

    @staticmethod
    def _parse_row_index(url: str) -> int:
        if "#row=" not in url:
            return 0
        try:
            return int(url.rsplit("#row=", 1)[-1])
        except ValueError:
            return 0

    # ─────────────────── 種別推定 ───────────────────

    @staticmethod
    def _infer_species_from_site_name(name: str) -> str:
        """サイト名から動物種別を推定"""
        if "犬" in name and "猫" in name:
            return "その他"
        if "犬" in name:
            return "犬"
        if "猫" in name:
            return "猫"
        return ""


# ─────────────────── サイト登録 ───────────────────
for _site_name in (
    "長野県動物愛護センター（譲渡犬）",
    "長野県動物愛護センター（譲渡猫）",
):
    if SiteAdapterRegistry.get(_site_name) is None:
        SiteAdapterRegistry.register(_site_name, NaganoHelloAnimalAdapter)
