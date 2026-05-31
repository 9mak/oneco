"""柏市動物愛護ふれあいセンター rule-based adapter

対象ドメイン: https://www.city.kashiwa.lg.jp/dobutsuaigo/

特徴:
- 同一テンプレート上で 2 サイトが運用されている:
    - .../mainmenu/dobutsu/hogo/hogo.html   (柏市（保護動物）)
    - .../mainmenu/dobutsu/hogo/satoya.html (柏市（譲渡対象動物）)
- 1 ページに複数動物がカード形式 (`div.col2_sp2_wrap`) で並ぶ single_page 形式。
  個別 detail ページは存在しないため一覧から直接抽出する。
- 各動物カードの内部構造:
    <h3>{犬|猫}</h3>          ← 直前の見出しで species を表現
    <div class="col2_sp2_wrap">
      <div class="col2">
        <div class="col2L">      ← 写真 (or 「写真なし」)
          <p><img src="..."></p>
          ...
        </div>
        <div class="col2R">      ← 属性
          <p>番号：051101</p>
          <p>種類：雑種</p>
          <p>毛色：茶トラ</p>
          <p>収容：5月11日</p>
          <p>性別：メス</p>
          <p>場所：豊四季台</p>
          <p>特徴：...</p>
        </div>
      </div>
    </div>
- テーブル形式ではなく `<p>ラベル：値</p>` の並びで構造化されているため、
  `SinglePageTableAdapter` の `td/th` ベース既定実装ではなく
  `extract_animal_details` をオーバーライドして属性を取得する。
- species は HTML の「種類：雑種」のような具体名ではなく、カードの直前に
  ある `<h3>犬</h3>` `<h3>猫</h3>` の見出しから推定する
  (見出しが取れない場合は「種類」値や「その他」にフォールバック)。
- 動物が 0 件のとき (告知のみのページ) は ParsingError ではなく空リストを
  返す (CityMachidaAdapter と同様の方針)。
"""

from __future__ import annotations

import re
from typing import ClassVar

from bs4 import Tag

from ....domain.models import RawAnimalData
from ...municipality_adapter import ParsingError
from ..registry import SiteAdapterRegistry
from ..single_page_table import SinglePageTableAdapter


class CityKashiwaAdapter(SinglePageTableAdapter):
    """柏市動物愛護ふれあいセンター用 rule-based adapter

    保護動物 (hogo.html) / 譲渡対象動物 (satoya.html) の 2 サイトで
    共通テンプレートを使用する single_page 形式。
    各動物は `div.col2_sp2_wrap` カードで表現される。
    """

    # 各動物カードの起点
    ROW_SELECTOR: ClassVar[str] = "div.col2_sp2_wrap"
    SKIP_FIRST_ROW: ClassVar[bool] = False
    # `<p>ラベル：値</p>` 並びを直接スキャンするため
    # `COLUMN_FIELDS` は基底契約の充足のためだけに宣言する。
    COLUMN_FIELDS: ClassVar[dict[int, str]] = {
        0: "id",
        1: "species",
        2: "color",
        3: "shelter_date",
        4: "sex",
        5: "location",
    }
    LOCATION_COLUMN: ClassVar[int | None] = 5
    SHELTER_DATE_DEFAULT: ClassVar[str] = ""

    # 動物カードに個別電話番号が無いため、柏市動物愛護ふれあいセンター代表電話を
    # 全動物カード共通で割り当てる (2026-05 観測)。
    _CENTER_TEL: ClassVar[str] = "04-7190-2828"

    # 「番号：051101」のようなラベル → RawAnimalData フィールド名のマッピング
    _LABEL_TO_FIELD: ClassVar[dict[str, str]] = {
        "種類": "species",
        "毛色": "color",
        "性別": "sex",
        "場所": "location",
        "収容": "shelter_date",
        "収容日": "shelter_date",
        "保護日": "shelter_date",
        "年齢": "age",
        "推定年齢": "age",
        "体格": "size",
        "大きさ": "size",
        # 「特徴」は自由テキスト。年齢/体重ヒントを後段で正規表現で抽出する。
        "特徴": "_features",
    }

    # 「特徴」自由テキストから「推定1～2歳」「推定1歳」「N歳」「Nヶ月」等を拾う。
    # 「推定」プレフィクスを許容し、範囲表現 (N～M歳) は下限値を採用 (normalizer 側の
    #  「N歳」マッチが先頭の数字を取るため、下限値を含む文字列を渡せば月数換算できる)。
    _AGE_HINT_PATTERN: ClassVar[re.Pattern[str]] = re.compile(
        r"(?:推定)?\s*(\d+(?:\s*[～~〜-]\s*\d+)?\s*(?:歳|才|[ヶかカケヵ]月))"
    )

    # 体重 → size 推定の境界 (kg)。oita_aigo / kumamoto_doubutuaigo と同基準。
    # 柏市は保護対象が猫が主体のため、~5kg を「小」、~15kg を「中」とする。
    _SIZE_BOUNDARY_SMALL_KG: ClassVar[float] = 5.0
    _SIZE_BOUNDARY_LARGE_KG: ClassVar[float] = 15.0
    # 「体重4.7kg」「体重2.9kg」のような自由テキストから体重数値を拾う
    _WEIGHT_HINT_PATTERN: ClassVar[re.Pattern[str]] = re.compile(
        r"体重\s*[:：]?\s*約?\s*(\d+(?:\.\d+)?)\s*[kK][gG]"
    )

    # 「現在、保護動物はおりません」「収容動物はいません」等の 0 件告知
    _EMPTY_STATE_PATTERN: ClassVar[re.Pattern[str]] = re.compile(
        r"(?:収容|保護|譲渡(?:対象)?)(?:動物|犬|猫)[^。]*?"
        r"(?:おりません|ありません|いません)"
    )

    # ─────────────────── オーバーライド ───────────────────

    def _load_rows(self) -> list[Tag]:
        """ROW_SELECTOR で取得した行から「ラベル付きカード」のみを残す

        柏市の譲渡対象動物ページ (satoya.html) には、写真と名前テキストだけで
        「種類：xxx」「毛色：xxx」のような構造化情報を持たないカードが
        混在する。それらを動物データとして取り込むと species/age/color/size が
        すべて空の無意味なレコードが snapshot に並ぶため、ラベル付きの
        カードだけを採用するようフィルタする。
        """
        if self._rows_cache is not None:
            return self._rows_cache

        # 親実装で取得 → 親が _rows_cache に保存するので上書きする
        raw_rows = super()._load_rows()
        valid = [r for r in raw_rows if self._has_labeled_field(r)]
        self._rows_cache = valid
        return valid

    @classmethod
    def _has_labeled_field(cls, card: Tag) -> bool:
        """カードに「種類:xxx」「毛色:xxx」等の構造化ラベルが1つ以上あれば True"""
        col2r = card.select_one("div.col2R")
        if not isinstance(col2r, Tag):
            return False
        for p in col2r.find_all("p"):
            text = p.get_text(separator=" ", strip=True)
            if not text:
                continue
            for sep in ("：", ":"):
                if sep in text:
                    label = text.split(sep, 1)[0].strip()
                    if label in cls._LABEL_TO_FIELD:
                        return True
                    break
        return False

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        """一覧ページから動物の仮想 URL を返す

        基底実装は行が 0 件のとき `ParsingError` を投げるが、柏市の
        テンプレートでは「現在、保護動物はおりません」等の告知ページが
        正常状態として発生し得る。empty state テキストを検出した場合は
        空リストを返し、それ以外で行が見つからなかった場合のみ
        `ParsingError` を伝播する。
        """
        rows = self._load_rows()
        if not rows:
            if self._html_cache and self._EMPTY_STATE_PATTERN.search(self._html_cache):
                return []
            raise ParsingError(
                "行要素が見つかりません",
                selector=self.ROW_SELECTOR,
                url=self.site_config.list_url,
            )
        category = self.site_config.category
        return [(f"{self.site_config.list_url}#row={i}", category) for i in range(len(rows))]

    def extract_animal_details(
        self, virtual_url: str, category: str = "sheltered"
    ) -> RawAnimalData:
        """1 個の `div.col2_sp2_wrap` カードから RawAnimalData を構築する

        基底の `td/th` ベース実装は使わず、`div.col2R > p` 配下の
        「ラベル：値」テキストを順次パースする。
        species は直前の `<h3>` 見出し (犬/猫) を優先し、無ければ
        「種類」値、それも無ければサイト名から推定する。
        """
        rows = self._load_rows()
        idx = self._parse_row_index(virtual_url)
        if idx >= len(rows):
            raise ParsingError(
                f"row index {idx} out of range (total {len(rows)})",
                url=virtual_url,
            )
        card = rows[idx]

        # 属性ブロック col2R 内の <p> をスキャン
        col2r = card.select_one("div.col2R")
        fields: dict[str, str] = {}
        if isinstance(col2r, Tag):
            for p in col2r.find_all("p"):
                if not isinstance(p, Tag):
                    continue
                text = p.get_text(separator=" ", strip=True)
                if not text:
                    continue
                # 全角コロン「：」または半角「:」の最初の出現で 2 分割
                for sep in ("：", ":"):
                    if sep in text:
                        label, value = text.split(sep, 1)
                        label = label.strip()
                        value = value.strip()
                        field = self._LABEL_TO_FIELD.get(label)
                        if field and value and field not in fields:
                            fields[field] = value
                        break

        # species: 直前の <h3>犬</h3>/<h3>猫</h3> を最優先
        species = self._infer_species_from_heading(card)
        if not species:
            # 「種類：雑種」「種類：柴犬」のような具体名から推定
            species = self._infer_species_from_breed(fields.get("species", ""))
        if not species:
            species = self._infer_species_from_site_name(self.site_config.name)

        # 「特徴」自由テキストから age / size を best-effort で補完。
        # age は専用ラベル (年齢/推定年齢) が無いため特徴欄から「推定N歳」等を拾う。
        # size は「体重Nkg」から oita_aigo と同じ境界で小/中/大に換算する。
        features = fields.get("_features", "")
        age = fields.get("age") or self._extract_age_from_features(features)
        size = fields.get("size") or self._weight_to_size(features)

        try:
            return RawAnimalData(
                species=species,
                sex=fields.get("sex", ""),
                age=age,
                color=fields.get("color", ""),
                size=size,
                shelter_date=fields.get("shelter_date", self.SHELTER_DATE_DEFAULT),
                location=fields.get("location", ""),
                phone=self._CENTER_TEL,
                image_urls=self._extract_row_images(card, virtual_url),
                source_url=virtual_url,
                category=category,
            )
        except Exception as e:
            raise ParsingError(f"RawAnimalData バリデーション失敗: {e}", url=virtual_url) from e

    # ─────────────────── ヘルパー ───────────────────

    @staticmethod
    def _infer_species_from_heading(card: Tag) -> str:
        """カード直前の `<h3>` 見出しから動物種別を推定する

        柏市テンプレートでは `<h2>保護収容動物情報</h2>` の下に
        `<h3>犬</h3>` または `<h3>猫</h3>` の見出しがあり、その後に
        該当種別の `div.col2_sp2_wrap` が並ぶ。直前の `<h3>` を
        後方に辿って最初に見つかったものを採用する。
        """
        for prev in card.find_all_previous(["h3", "h2"]):
            if not isinstance(prev, Tag):
                continue
            if prev.name != "h3":
                # h2 まで遡っても h3 が無ければ打ち切り
                continue
            text = prev.get_text(strip=True)
            if "犬" in text:
                return "犬"
            if "猫" in text:
                return "猫"
            # 他の <h3> (例: 「目次」等) はスキップして更に遡る
        return ""

    @staticmethod
    def _infer_species_from_breed(breed: str) -> str:
        """「種類」値 (柴犬/雑種/三毛猫等) から動物種別を推定する"""
        if not breed:
            return ""
        if "犬" in breed:
            return "犬"
        if "猫" in breed:
            return "猫"
        return ""

    @classmethod
    def _extract_age_from_features(cls, features: str) -> str:
        """「特徴」自由テキストから age 文字列を best-effort で抽出する

        柏市カードには専用の「年齢」フィールドが無く、「特徴」欄に
        「推定1～2歳」「推定1歳」「年齢若め」のような自由表現で記載される。
        normalizer が解釈できる「N歳」「Nヶ月」を含む部分を取り出して
        そのまま raw_data.age に渡す (後段で `_normalize_age` が月数化する)。

        - 「推定1～2歳」  → "1歳" (下限値) を返す
        - 「推定1歳」    → "1歳"
        - 「6ヶ月」      → "6ヶ月"
        - 「年齢若め」 (数値なし)  → "" (DataNormalizer は数値が無いと None)

        normalizer は範囲表記の下限を拾えないため、ここで明示的に下限値を
        含む文字列に整形して返す。
        """
        if not features:
            return ""
        m = cls._AGE_HINT_PATTERN.search(features)
        if not m:
            return ""
        snippet = m.group(1)
        # 「1～2歳」のような範囲表記は下限値だけ残す ("1歳" → normalizer が "歳" を拾う)
        range_m = re.search(r"(\d+)\s*[～~〜-]\s*\d+\s*(歳|才|[ヶかカケヵ]月)", snippet)
        if range_m:
            return f"{range_m.group(1)}{range_m.group(2)}"
        return snippet.strip()

    @classmethod
    def _weight_to_size(cls, features: str) -> str:
        """「特徴」自由テキスト中の「体重Nkg」から size 語彙 (小/中/大) を推定する

        - 5kg 未満: 小
        - 5kg 以上 15kg 未満: 中
        - 15kg 以上: 大
        - 体重表記が拾えない場合: 空文字 (size 不明)
        """
        if not features:
            return ""
        m = cls._WEIGHT_HINT_PATTERN.search(features)
        if not m:
            return ""
        try:
            kg = float(m.group(1))
        except ValueError:
            return ""
        if kg < cls._SIZE_BOUNDARY_SMALL_KG:
            return "小"
        if kg < cls._SIZE_BOUNDARY_LARGE_KG:
            return "中"
        return "大"

    @staticmethod
    def _infer_species_from_site_name(name: str) -> str:
        """サイト名から動物種別を推定する (フォールバック)

        柏市の 2 サイト名 (「柏市（保護動物）」「柏市（譲渡対象動物）」) は
        いずれも犬/猫の明示が無いため、通常は空文字を返す。
        """
        if "犬" in name:
            return "犬"
        if "猫" in name:
            return "猫"
        return ""


# ─────────────────── サイト登録 ───────────────────
# 同一テンプレート上で運用される 2 サイトを同一 adapter にマップする。
# `sites.yaml` の `prefecture: 千葉県` かつ `city.kashiwa.lg.jp` ドメイン。
for _site_name in (
    "柏市（保護動物）",
    "柏市（譲渡対象動物）",
):
    if SiteAdapterRegistry.get(_site_name) is None:
        SiteAdapterRegistry.register(_site_name, CityKashiwaAdapter)
