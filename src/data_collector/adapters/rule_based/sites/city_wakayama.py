"""和歌山市動物愛護管理センター（譲渡候補）rule-based adapter

対象ドメイン: https://www.city.wakayama.wakayama.jp/kurashi/kenko_iryo/1009125/1035775/1002096.html

特徴:
- 和歌山市役所の独自 CMS (HiNT 系) で運用される single_page サイト。
  個別 detail ページは存在せず、1 ページに譲渡候補の犬・猫が並ぶ。
- 本文は `<article id="content">` 配下に
  `<h3>飼い主さんを募集中の猫</h3>` と `<h3>飼い主さんを募集中の犬</h3>` の
  2 セクションがあり、各セクション内で `<div class="img3lows">` の中に
  `<div class="imglows">` カードが 1 頭ずつ並ぶ。
- 各カード `<div class="imglows">` の構造:
    <div class="imglows">
      <p class="imagecenter"><img src="..."></p>
      <p>仮名：○○<br>
         種類：雑種<br>
         年齢（推定）：1歳<br>
         性別：オス（手術済）<br>
         検査等：FIV／FeLV陰性<br>
         性格等：…</p>
    </div>
  - 各フィールドは `ラベル：値` (全角コロン) で 1 行ごとに `<br>` 区切り。
  - `年齢（推定）` のように括弧付きラベルがあるため、ラベル一致は前方一致で扱う。
  - 検査等・性格等は本サイト固有の付加情報なので RawAnimalData には含めない。
- 動物種別 (犬/猫) はカード単独では判定しづらいため、所属 `<h3>` セクションの
  見出しテキストから推定する (見出しに「犬」が含まれれば犬、それ以外で
  「猫」が含まれれば猫)。
- `imagecenter` 内の `<img>` から画像 URL を取得し、`_absolute_url` で
  list_url を基準に絶対化する。
- 在庫 0 件 (どのカードも無い) の場合は空リストを返す。本文の主要見出し
  (`<h1>譲渡可能動物情報</h1>` 等の `article#content`) すら無い場合のみ
  テンプレート崩壊として `ParsingError` を出す。
"""

from __future__ import annotations

import re
from typing import ClassVar

from bs4 import BeautifulSoup, Tag

from ....domain.models import RawAnimalData
from ...municipality_adapter import ParsingError
from ..registry import SiteAdapterRegistry
from ..single_page_table import SinglePageTableAdapter

# 全角/半角コロン
_COLON = r"[:：]"


def _extract_field(text: str, label: str) -> str:
    """`text` から「{label}{コロン}{値}」の値部分を抽出する

    値は次の改行 / 文字列終端まで。マッチしない場合は空文字を返す。
    ラベルに括弧 (例: `年齢（推定）`) が含まれるためエスケープする。
    """
    pattern = re.escape(label) + _COLON + r"(.*?)(?=\n|$)"
    m = re.search(pattern, text)
    if not m:
        return ""
    return m.group(1).strip(" 　\t\r\n")


def _strip_paren_suffix(value: str) -> str:
    """`オス（手術済）` → `オス` のように末尾の括弧注釈を除去する

    全角・半角の括弧の両方に対応する。性別カラムをドメインの
    `male/female` に正規化する後段処理 (DataNormalizer) で
    括弧付きの値を扱えないケースに備えるための整形ヘルパー。
    """
    return re.sub(r"\s*[（(].*?[)）]\s*$", "", value).strip()


class CityWakayamaAdapter(SinglePageTableAdapter):
    """和歌山市動物愛護管理センター（譲渡候補）用 rule-based adapter

    `<div class="imglows">` 1 つを 1 頭分のカードとして抽出する single_page 形式。
    基底のセルベース既定実装は使わず、`extract_animal_details` を
    オーバーライドしてカード内 `<p>` のテキストからフィールドを切り出す。
    また species は所属 `<h3>` 見出しから推定するため、`fetch_animal_list`
    で `(card, species)` のペアを内部キャッシュに保持する。
    """

    ROW_SELECTOR: ClassVar[str] = "div.imglows"
    SKIP_FIRST_ROW: ClassVar[bool] = False
    # 基底のセルベース既定実装は使わないが契約として明示的に空指定する。
    COLUMN_FIELDS: ClassVar[dict[int, str]] = {}
    LOCATION_COLUMN: ClassVar[int | None] = None
    # 収容日 (公開日) はページに明示されないため空のまま (DataNormalizer 側の
    # フォールバックに委ねる)
    SHELTER_DATE_DEFAULT: ClassVar[str] = ""
    # ページ右上の「お問い合わせ」ブロック内テキスト (動物愛護管理センター)
    DEFAULT_LOCATION: ClassVar[str] = "和歌山県和歌山市"

    def __init__(self, site_config) -> None:
        super().__init__(site_config)
        # カード index -> 推定 species ('犬' / '猫' / 'その他')
        self._species_by_index: dict[int, str] = {}

    # ─────────────────── オーバーライド ───────────────────

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        """カードを走査し index と species のペアを構築する

        本文コンテナ (`article#content` または `div#voice`) すら無い場合のみ
        テンプレート崩壊として例外化する。
        """
        if self._html_cache is None:
            self._html_cache = self._http_get(self.site_config.list_url)

        soup = BeautifulSoup(self._html_cache, "html.parser")
        if soup.select_one("article#content") is None and soup.select_one("div#voice") is None:
            raise ParsingError(
                "本文コンテナ (article#content / div#voice) が見つかりません",
                selector="article#content",
                url=self.site_config.list_url,
            )

        rows = self._load_rows()
        # 各カードの species を所属 <h3> から推定して格納
        self._species_by_index = {
            i: self._infer_species_from_section(card) for i, card in enumerate(rows)
        }

        category = self.site_config.category
        return [(f"{self.site_config.list_url}#row={i}", category) for i in range(len(rows))]

    def extract_animal_details(self, virtual_url: str, category: str = "adoption") -> RawAnimalData:
        """`<div class="imglows">` カードから RawAnimalData を構築する"""
        rows = self._load_rows()
        idx = self._parse_row_index(virtual_url)
        if idx >= len(rows):
            raise ParsingError(
                f"row index {idx} out of range (total {len(rows)})",
                url=virtual_url,
            )
        card = rows[idx]

        # カード内 <p> (画像用 imagecenter は除外) のテキストを <br> を改行に
        # 置換して取得
        paragraph_texts: list[str] = []
        for p in card.find_all("p"):
            if not isinstance(p, Tag):
                continue
            classes = p.get("class") or []
            if isinstance(classes, list) and "imagecenter" in classes:
                continue
            paragraph_texts.append(p.get_text(separator="\n", strip=True))
        full_text = "\n".join(paragraph_texts)

        # species は事前にセクション見出しから推定済 (キャッシュ)。
        # 未登録のときは本文テキストから推定。
        species = self._species_by_index.get(idx) or self._infer_species_from_text(full_text)

        sex = _strip_paren_suffix(_extract_field(full_text, "性別"))
        # 種類カラム (例: 雑種) は AnimalData の color/size とは別概念のため、
        # ドメイン側で扱える値だけマッピングする。
        breed = _extract_field(full_text, "種類")
        age = _extract_field(full_text, "年齢（推定）") or _extract_field(full_text, "年齢")

        try:
            return RawAnimalData(
                species=species,
                sex=sex,
                age=age,
                # 毛色・体格は本サイト掲載項目に無いため空欄
                color="",
                size="",
                shelter_date=self.SHELTER_DATE_DEFAULT,
                location=self.DEFAULT_LOCATION,
                phone="",
                image_urls=self._extract_row_images(card, virtual_url),
                source_url=virtual_url,
                category=category,
            )
        except Exception as e:
            raise ParsingError(
                f"RawAnimalData バリデーション失敗: {e} (breed={breed!r})",
                url=virtual_url,
            ) from e

    # ─────────────────── 画像 URL 抽出 (オーバーライド) ───────────────────

    def _filter_image_urls(self, urls: list[str], base_url: str) -> list[str]:
        """和歌山市 CMS は `_res/projects/.../_page_/...` 配下に動物写真を置く

        WordPress 系の `/wp-content/uploads/` 想定の基底実装では本サイトの
        画像が全てフィルタアウトされてしまうため、本サイト用の許可パスで
        判定する。ロゴやアイコン等のテンプレート画像は `_template_/` 配下に
        集約されているため、これを除外するだけで概ね動物写真のみが残る。
        """
        filtered = [u for u in urls if "/_template_/" not in u]
        return filtered if filtered else urls

    # ─────────────────── ヘルパー ───────────────────

    @staticmethod
    def _infer_species_from_section(card: Tag) -> str:
        """カードが属する直前の `<h3>` 見出しから動物種別を推定する

        本サイトでは「飼い主さんを募集中の猫」「飼い主さんを募集中の犬」の
        ような見出しの下に各カード群が並ぶ。
        """
        for prev in card.find_all_previous(["h2", "h3"]):
            if not isinstance(prev, Tag):
                continue
            heading = prev.get_text(strip=True)
            if "犬" in heading:
                return "犬"
            if "猫" in heading:
                return "猫"
        return "その他"

    @staticmethod
    def _infer_species_from_text(text: str) -> str:
        """カード本文テキストから動物種別 (犬/猫/その他) を推定する (フォールバック)"""
        if "犬" in text:
            return "犬"
        if "猫" in text:
            return "猫"
        return "その他"


# ─────────────────── サイト登録 ───────────────────
# 他テストが registry を clear する場合に備え、未登録時のみ登録する。
_SITE_NAME = "和歌山市動物愛護管理センター（譲渡候補）"
if SiteAdapterRegistry.get(_SITE_NAME) is None:
    SiteAdapterRegistry.register(_SITE_NAME, CityWakayamaAdapter)
