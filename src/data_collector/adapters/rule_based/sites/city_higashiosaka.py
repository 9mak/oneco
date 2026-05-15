"""東大阪市保護収容動物情報 rule-based adapter

対象ドメイン: https://www.city.higashiosaka.lg.jp/0000005910.html

特徴:
- 東大阪市役所動物指導センター運用の独自 CMS (`mol_*` クラス) ページ。
- 1 ページに動物情報が並ぶ single_page サイト。個別 detail ページは無い。
- 本文は `#mol_contents` (ページ内では id 無しの `div.mol_contents`) 配下に
  `<div class="mol_imageblock ...">` が「1 件 = 1 ブロック」として並ぶ
  テンプレート構造になっている。各カードは:
    <div class="mol_imageblock clearfix block_index_NN">
      <div class="mol_imageblock_imgfloatleft">
        <div class="mol_imageblock_w_long ...">
          <div class="mol_imageblock_img"><img src="..." ></div>
          <p>個体番号:NN　収容年月日:令和X年Y月Z日<br>
             種類:○○　性別:オス／メス<br>
             毛色:○○　体格:○　体長○cm　体高○cm<br>
             推定年齢:○○　収容地域:○○<br>
             備考:</p>
        </div>
      </div>
    </div>
  という形式で、<p> 内に <br> 区切りで複数フィールドが詰め込まれる。
- 在庫 0 件のときは別途 `<b>現在、保護収容動物情報はありません。</b>` の
  メッセージが本文中の `mol_xhtmlblock` に表示され、`mol_imageblock` 自体は
  ページ HTML 上ではコメント (`<!-- ... -->`) で囲まれて出現する
  (CMS 側で雛形を残しつつ表示を抑制している)。BeautifulSoup の標準パーサは
  HTML コメントを Tag として解析しないため、`div.mol_imageblock` の
  CSS セレクタは何もマッチせず空リストが返る — 本 adapter ではこれを
  ParsingError ではなく「在庫 0 件」として扱う。
- 動物種別 (犬/猫) はカード内 `種類:` の値だけでは犬種等が混じり判定が
  難しいケースもあるため、テキストから「犬」「猫」を直接探して推定する
  (見つからなければ「その他」)。
- `<p>` 内テキストは「ラベル:値　ラベル:値」 (全角/半角コロン + 全角空白
  または `<br>`) で区切られているため、正規表現で各フィールドを抽出する。
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
# フィールド区切り (全角/半角空白、改行、または <br> 由来の空白)
_SEP = r"[\s　]"


def _extract_field(text: str, label: str) -> str:
    """`text` から「{label}{コロン}{値}」の値部分を抽出する

    値は「次の既知ラベル+コロン」「全角空白」「改行」「文字列終端」の
    いずれか直前まで。マッチしない場合は空文字を返す。
    全角空白を区切りに含めるのは、本サイトが
    `毛色:茶白　体格:中　体長50cm　体高40cm` のように
    1 行に複数項目を全角空白で並べるテンプレートだから。
    """
    # 既知ラベル一覧 (本文中で値の終端マーカーになる)
    other_labels = [
        "個体番号",
        "収容年月日",
        "種類",
        "性別",
        "毛色",
        "体格",
        "体長",
        "体高",
        "推定年齢",
        "収容地域",
        "備考",
    ]
    # ラベル自身は除外
    others = [lbl for lbl in other_labels if lbl != label]
    label_alt = "|".join(re.escape(lbl) + _COLON for lbl in others)
    # 終端: 次の既知ラベル / 全角空白 / 改行 / 文字列終端
    next_lookahead = r"(?=" + label_alt + r"|　|\n|$)"
    pattern = re.escape(label) + _COLON + r"(.*?)" + next_lookahead
    m = re.search(pattern, text, flags=re.DOTALL)
    if not m:
        return ""
    return m.group(1).strip(" 　\t\r\n")


class CityHigashiosakaAdapter(SinglePageTableAdapter):
    """東大阪市保護収容動物情報用 rule-based adapter

    `<div class="mol_imageblock ...">` 1 つを 1 頭分のカードとして抽出する
    single_page 形式。基底の `td/th` セルベース既定実装は使わず、
    `extract_animal_details` をオーバーライドしてカード内 `<p>` のテキストから
    フィールドを切り出す。
    """

    ROW_SELECTOR: ClassVar[str] = "div.mol_imageblock"
    SKIP_FIRST_ROW: ClassVar[bool] = False
    # 基底のセルベース既定実装は使わないが契約として明示的に空指定する。
    COLUMN_FIELDS: ClassVar[dict[int, str]] = {}
    LOCATION_COLUMN: ClassVar[int | None] = None
    # 収容年月日はカード内テキストから取得するためデフォルトは空
    SHELTER_DATE_DEFAULT: ClassVar[str] = ""

    # ─────────────────── オーバーライド ───────────────────

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        """データブロックが見つからない (在庫 0 件) ときは空リストを返す

        東大阪市は保護動物が居ない期間も同 URL で平常運用される。本文コンテナ
        (`div.mol_contents`) すら無い場合のみテンプレート崩壊として例外化する。
        """
        if self._html_cache is None:
            self._html_cache = self._http_get(self.site_config.list_url)

        soup = BeautifulSoup(self._html_cache, "html.parser")
        if soup.select_one("div.mol_contents") is None:
            raise ParsingError(
                "本文コンテナ (div.mol_contents) が見つかりません",
                selector="div.mol_contents",
                url=self.site_config.list_url,
            )

        rows = self._load_rows()
        category = self.site_config.category
        return [(f"{self.site_config.list_url}#row={i}", category) for i in range(len(rows))]

    def extract_animal_details(
        self, virtual_url: str, category: str = "sheltered"
    ) -> RawAnimalData:
        """`<div class="mol_imageblock">` カードから RawAnimalData を構築する"""
        rows = self._load_rows()
        idx = self._parse_row_index(virtual_url)
        if idx >= len(rows):
            raise ParsingError(
                f"row index {idx} out of range (total {len(rows)})",
                url=virtual_url,
            )
        card = rows[idx]

        # カード内 <p> のテキストを <br> を改行に置換して取得
        paragraph_texts: list[str] = []
        for p in card.find_all("p"):
            if isinstance(p, Tag):
                paragraph_texts.append(p.get_text(separator="\n", strip=True))
        full_text = "\n".join(paragraph_texts)

        species = self._infer_species_from_text(full_text)
        sex = _extract_field(full_text, "性別")
        color = _extract_field(full_text, "毛色")
        size = _extract_field(full_text, "体格")
        age = _extract_field(full_text, "推定年齢")
        shelter_date = _extract_field(full_text, "収容年月日")
        location = _extract_field(full_text, "収容地域")

        try:
            return RawAnimalData(
                species=species,
                sex=sex,
                age=age,
                color=color,
                size=size,
                shelter_date=shelter_date or self.SHELTER_DATE_DEFAULT,
                location=location,
                phone="",
                image_urls=self._extract_row_images(card, virtual_url),
                source_url=virtual_url,
                category=category,
            )
        except Exception as e:
            raise ParsingError(f"RawAnimalData バリデーション失敗: {e}", url=virtual_url) from e

    # ─────────────────── ヘルパー ───────────────────

    @staticmethod
    def _infer_species_from_text(text: str) -> str:
        """カード本文テキストから動物種別 (犬/猫/その他) を推定する

        `種類:` ラベルの直後だけでなく、本文全体に「犬」「猫」が含まれているか
        で判定する (例: 種類欄に犬種名のみ書かれているケースに備える)。
        """
        if "犬" in text:
            return "犬"
        if "猫" in text:
            return "猫"
        return "その他"


# ─────────────────── サイト登録 ───────────────────
# 他テストが registry を clear する場合に備え、未登録時のみ登録する。
_SITE_NAME = "東大阪市（保護収容動物）"
if SiteAdapterRegistry.get(_SITE_NAME) is None:
    SiteAdapterRegistry.register(_SITE_NAME, CityHigashiosakaAdapter)
