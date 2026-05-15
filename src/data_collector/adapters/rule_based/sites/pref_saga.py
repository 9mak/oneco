"""佐賀県保護動物 rule-based adapter

対象ドメイン: https://www.pref.saga.lg.jp/

特徴:
- 同一ドメイン (`/kijiNNNNNNN/index.html`) 上で 6 サイトが運用されており、
  地域別保護犬猫 5 サイトと全県譲渡犬猫 1 サイトすべてが同一テンプレートを
  共有する。サイトごとに URL (kiji 番号) のみが異なる:
    - /kiji00349237/index.html : 佐賀市・多久・小城・神埼
    - /kiji00334357/index.html : 鳥栖・三養基郡
    - /kiji00365042/index.html : 唐津・東松浦郡
    - /kiji00334505/index.html : 伊万里・西松浦郡
    - /kiji00334341/index.html : 武雄・鹿島・嬉野・杵島・藤津
    - /kiji00314888/index.html : 全県譲渡犬猫
- 1 ページ内に「保護犬情報」「保護猫情報」「その他の保護動物情報」の
  3 セクションが並び、各セクションは `table.__wys_table` 1 つに対応する
  (= 1 動物 = 1 テーブル)。`SinglePageTableAdapter` の "テーブルの 1 行 =
  1 動物" モデルとは異なり、本サイトでは "テーブル全体 = 1 動物" となる
  ため、`ROW_SELECTOR` をテーブル自身に設定し、`extract_animal_details`
  をオーバーライドして縦並び (項目名 / 値) のセルから値を取り出す。
- 各テーブルの構造 (代表例):

    <h3 class="title">保護犬情報</h3>
    <table class="__wys_table">
      <tr><td>保護犬（番号）</td><td colspan="2">保護した場所</td><td>{場所}</td></tr>
      <tr><td rowspan="8">{備考}</td>
          <td rowspan="6">犬の特徴</td>
          <td>種類</td><td>{種類}</td></tr>
      <tr><td>毛色</td><td>{毛色}</td></tr>
      <tr><td>性別</td><td>{性別}</td></tr>
      <tr><td>体格</td><td>{体格}</td></tr>
      <tr><td>推定年齢</td><td>{年齢}</td></tr>
      <tr><td>その他</td><td>{その他}</td></tr>
      <tr><td colspan="2">収容日</td><td>{収容日}</td></tr>
      <tr><td colspan="2">ホームページ掲載期限</td><td>{掲載期限}</td></tr>
    </table>

  値セルが空の場合、当該セクションに収容中の動物がいないことを意味する
  (本文に「現在保護中の◯はいません」と記載されることがある)。
  実運用では空テーブルもパース対象としつつ、値が空文字のままで
  RawAnimalData を構築する (Pydantic は空文字を許容する仕様のため)。
- 動物種別はテーブル直前の `<h3 class="title">` から推定する
  (保護犬情報 → 犬 / 保護猫情報 → 猫 / その他… → その他)。
  「全県譲渡犬猫」サイトも同じ h3 ラベルを使用するため、サイト名ではなく
  ページ内見出しを正としている。
"""

from __future__ import annotations

from typing import ClassVar

from bs4 import Tag

from ....domain.models import RawAnimalData
from ...municipality_adapter import ParsingError
from ..registry import SiteAdapterRegistry
from ..single_page_table import SinglePageTableAdapter


class PrefSagaAdapter(SinglePageTableAdapter):
    """佐賀県保護動物用 rule-based adapter

    地域別 5 + 全県譲渡 1 の計 6 サイトで共通テンプレートを使用する。
    1 ページ内の `table.__wys_table` 各 1 個が 1 動物に対応する縦並び形式。
    """

    # 各動物セクションは 1 つの `table.__wys_table` で表現される
    ROW_SELECTOR: ClassVar[str] = "table.__wys_table"
    # ヘッダ行という概念はなくテーブル自身が 1 件分のため除外しない
    SKIP_FIRST_ROW: ClassVar[bool] = False
    # 値の取り出しはオーバーライドした `extract_animal_details` が
    # 縦並びレイアウトを直接スキャンするため `COLUMN_FIELDS` は宣言のみ。
    # 各キーは `RawAnimalData` のフィールド名と整合する。
    COLUMN_FIELDS: ClassVar[dict[int, str]] = {
        0: "species",
        1: "color",
        2: "sex",
        3: "size",
        4: "age",
        5: "shelter_date",
    }
    LOCATION_COLUMN: ClassVar[int | None] = None
    # 収容日が「令和 8 年(2026年） 月  日」のように未確定で記載される
    # ことがあるため、デフォルト値は空文字としておく (不明扱い)。
    SHELTER_DATE_DEFAULT: ClassVar[str] = ""

    # ─────────────────── オーバーライド ───────────────────

    def extract_animal_details(
        self, virtual_url: str, category: str = "adoption"
    ) -> RawAnimalData:
        """1 つの `table.__wys_table` から RawAnimalData を構築する

        基底の "セル位置 → フィールド" マッピングではなく、
        各行の左側ラベル (種類 / 毛色 / 性別 / …) と右端の値セルを
        ペアで読み取る縦並び抽出を行う。
        """
        rows = self._load_rows()
        idx = self._parse_row_index(virtual_url)
        if idx >= len(rows):
            raise ParsingError(
                f"row index {idx} out of range (total {len(rows)})",
                url=virtual_url,
            )
        table = rows[idx]
        trs = [tr for tr in table.find_all("tr") if isinstance(tr, Tag)]

        # 1 行目の最後のセルが「保護した場所」の値
        location = ""
        if trs:
            tr0_cells = trs[0].find_all(["td", "th"])
            if tr0_cells:
                location = tr0_cells[-1].get_text(separator=" ", strip=True)

        # 2 行目以降からラベル → 値を抽出。ラベル候補と
        # `RawAnimalData` フィールド名のマッピング。
        label_to_field = {
            "種類": "species",
            "毛色": "color",
            "性別": "sex",
            "体格": "size",
            "推定年齢": "age",
            "収容日": "shelter_date",
        }
        fields: dict[str, str] = {}
        for tr in trs[1:]:
            cells = [c for c in tr.find_all(["td", "th"]) if isinstance(c, Tag)]
            if len(cells) < 2:
                continue
            # 行末のセルを値、それ以前のいずれかにラベルが含まれているはず
            value_cell = cells[-1]
            value_text = value_cell.get_text(separator=" ", strip=True)
            for label_cell in cells[:-1]:
                label_text = label_cell.get_text(separator=" ", strip=True)
                # ラベルセルは短いテキストのため部分一致でマッチング
                for label, field in label_to_field.items():
                    if field in fields:
                        continue
                    if label in label_text:
                        fields[field] = value_text
                        break

        # 動物種別は先行する h3.title から推定 (サイト名より確実)
        species_from_heading = self._infer_species_from_heading(table)
        species = species_from_heading or fields.get("species", "")

        try:
            return RawAnimalData(
                species=species,
                sex=fields.get("sex", ""),
                age=fields.get("age", ""),
                color=fields.get("color", ""),
                size=fields.get("size", ""),
                shelter_date=fields.get(
                    "shelter_date", self.SHELTER_DATE_DEFAULT
                ),
                location=location,
                phone="",
                image_urls=self._extract_row_images(table, virtual_url),
                source_url=virtual_url,
                category=category,
            )
        except Exception as e:
            raise ParsingError(
                f"RawAnimalData バリデーション失敗: {e}", url=virtual_url
            ) from e

    # ─────────────────── ヘルパー ───────────────────

    @staticmethod
    def _infer_species_from_heading(table: Tag) -> str:
        """テーブル直前の `<h3 class="title">` から動物種別を推定する

        想定見出し:
        - "保護犬情報" / "譲渡犬情報" → "犬"
        - "保護猫情報" / "譲渡猫情報" → "猫"
        - "その他の保護動物情報" 等 → "その他"

        見出しが見つからない場合は空文字を返し、呼出側で
        テーブル内 "種類" セルの値にフォールバックさせる。
        """
        # `find_previous` でテーブルより前に出現する最初の h3 を探す
        h3 = table.find_previous("h3")
        if not isinstance(h3, Tag):
            return ""
        text = h3.get_text(strip=True)
        if "犬" in text:
            return "犬"
        if "猫" in text:
            return "猫"
        if text:
            return "その他"
        return ""


# ─────────────────── サイト登録 ───────────────────
# 同一テンプレート上で運用される 6 サイトを同一 adapter にマップする。
for _site_name in (
    "佐賀県（佐賀市・多久・小城・神埼）保護犬猫",
    "佐賀県（鳥栖・三養基郡）保護犬猫",
    "佐賀県（唐津・東松浦郡）保護犬猫",
    "佐賀県（伊万里・西松浦郡）保護犬猫",
    "佐賀県（武雄・鹿島・嬉野・杵島・藤津）保護犬猫",
    "佐賀県（全県）譲渡犬猫",
):
    if SiteAdapterRegistry.get(_site_name) is None:
        SiteAdapterRegistry.register(_site_name, PrefSagaAdapter)
