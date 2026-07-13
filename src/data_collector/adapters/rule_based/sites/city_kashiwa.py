"""柏市動物愛護ふれあいセンター rule-based adapter

対象ドメイン: https://www.city.kashiwa.lg.jp/dobutsuaigo/

特徴:
- 同一テンプレート上で 2 サイトが運用されているが、2026-06 時点で
  **2 つの異なる HTML フォーマット**が混在する:

  (A) ラベル形式 — 主に hogo.html (柏市（保護動物）)
    <h3>{犬|猫}</h3>          ← 直前の見出しで species を表現
    <div class="col2_sp2_wrap">
      <div class="col2">
        <div class="col2L"><p><img src="..."></p></div>  ← 写真
        <div class="col2R">      ← 属性 (ラベル：値)
          <p>番号：051101</p><p>種類：雑種</p><p>毛色：茶トラ</p>
          <p>収容：5月11日</p><p>性別：メス</p><p>場所：豊四季台</p>
        </div>
      </div>
    </div>

  (B) 自由テキスト形式 — 主に satoya.html (柏市（譲渡対象動物）)
    <h3>{犬|猫}</h3>
    <div class="col2_sp2_wrap"> ...写真と名前キャプションのみ... </div>
    <p>コッタ （031001）</p>                            ← 名前（番号）
    <p>オス(去勢手術済み)　R6.9月生(推定)　ワクチン...</p>  ← 性別・年齢・医療
    <p>...性格・特徴の自由文...</p>
    <hr>                                              ← 個体の区切り
  (属性が col2R 内のラベルではなく、カード直後の兄弟 <p> に自由文で並ぶ。
   年齢は「N才(推定)」「R6.9月生(推定)」「H28.4月生(推定)」の 3 形式。)

実装方針:
- いずれの形式でも `div.col2_sp2_wrap` をカード起点 (ROW_SELECTOR) とする。
- カードが (A) ラベル付き col2R を持てばラベル形式でパース、無ければ
  カード直後の兄弟 <p> 群 (B) から性別・年齢を抽出する dual-mode。
- species はカード直前の `<h3>犬</h3>`/`<h3>猫</h3>` 見出しから推定する。
- 動物が 0 件のとき (告知のみのページ) は ParsingError ではなく空リストを返す。
- 写真と名前キャプションだけで属性 (ラベルも兄弟 <p> 性別も) を持たない
  装飾カードは除外する。
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

    # 「現在、保護動物はおりません」「収容動物はいません」
    # 「譲渡対象の動物はおりません」「譲渡対象の犬はおりません」等の 0 件告知。
    # 「譲渡対象(の)動物」のように助詞「の」が挟まる表記も許容する。
    _EMPTY_STATE_PATTERN: ClassVar[re.Pattern[str]] = re.compile(
        r"(?:収容|保護|譲渡(?:対象)?)(?:の)?(?:動物|犬|猫)[^。]*?"
        r"(?:おりません|ありません|いません)"
    )

    # 在庫 0 でカード自体が省略されるページ (2026-07 観測) の判定に使う。
    # <h3>犬</h3> / <h3>猫</h3> の種別見出しが残っていればテンプレートは
    # 生きている (= 構造変化ではなく空在庫) と見なす。
    _SPECIES_HEADING_PATTERN: ClassVar[re.Pattern[str]] = re.compile(
        r"<h3[^>]*>\s*(?:犬|猫)\s*</h3>"
    )

    # ── 自由テキスト形式 (B / satoya.html) 用 ──
    # 性別マーカー。「オス(去勢手術済み)」「メス(不妊手術済み)」等の自由文から拾う。
    _SEX_RE: ClassVar[re.Pattern[str]] = re.compile(r"(オス|メス)")
    # 元号略記の生年月 (R6.9月生 / H28.4月生 / S60.1月生)。日の記載は無い。
    _ERA_BIRTH_RE: ClassVar[re.Pattern[str]] = re.compile(r"([RHS])\s*(\d+)\s*\.\s*(\d+)\s*月")
    # 元号略記 → 西暦元年。year = base + N (例: R6 → 2018 + 6 = 2024)。
    _ERA_BASE_YEAR: ClassVar[dict[str, int]] = {
        "R": 2018,  # 令和元年 = 2019
        "H": 1988,  # 平成元年 = 1989
        "S": 1925,  # 昭和元年 = 1926
    }
    # 「1才(推定)」「2歳」「6ヶ月」等の直接年齢表記
    _DIRECT_AGE_RE: ClassVar[re.Pattern[str]] = re.compile(r"(\d+)\s*(?:才|歳|[ヶかカケヵ]月)")

    # ─────────────────── オーバーライド ───────────────────

    def _load_rows(self) -> list[Tag]:
        """ROW_SELECTOR で取得した行から「動物データを持つカード」のみを残す

        柏市には、写真と名前キャプションだけで属性 (ラベルも兄弟 <p> 性別も)
        を持たない装飾カードが混在する。それらを取り込むと species/age/color
        がすべて空の無意味なレコードが snapshot に並ぶため除外する。

        カードを採用する条件 (いずれか):
        - (A) col2R に「種類：」「毛色：」等のラベル付きフィールドがある
        - (B) カード直後の兄弟 <p> 群に性別マーカー (オス/メス) がある
        """
        if self._rows_cache is not None:
            return self._rows_cache

        # 親実装で取得 → 親が _rows_cache に保存するので上書きする
        raw_rows = super()._load_rows()
        valid = [r for r in raw_rows if self._has_labeled_field(r) or self._has_following_attr(r)]
        self._rows_cache = valid
        return valid

    @classmethod
    def _is_cardless_inventory(cls, html: str) -> bool:
        """在庫 0 でカードが丸ごと省略されたページかを判定する

        テンプレートの種別見出し (<h3>犬</h3>/<h3>猫</h3>) が残っており、
        かつカード要素 (col2_sp2_wrap) が 1 つも無ければ、構造変化ではなく
        「掲載動物なし」の正常状態と見なす。
        """
        return "col2_sp2_wrap" not in html and bool(cls._SPECIES_HEADING_PATTERN.search(html))

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

    @classmethod
    def _collect_following_attr_paragraphs(cls, card: Tag) -> list[str]:
        """カード直後の兄弟 <p> テキストを <hr> / 次カードまで収集する (形式 B)

        satoya.html では属性がカード内ではなく、カードの後続兄弟 <p> に
        自由文で並ぶ。区切りは <hr> または次の col2_sp2_wrap カード。
        """
        paragraphs: list[str] = []
        sib = card
        while True:
            sib = sib.find_next_sibling()
            if sib is None or not isinstance(sib, Tag):
                if sib is None:
                    break
                continue
            if sib.name == "hr":
                break
            cls_list = sib.get("class") or []
            if sib.name == "div" and "col2_sp2_wrap" in cls_list:
                break
            if sib.name == "p":
                text = sib.get_text(separator=" ", strip=True)
                if text:
                    paragraphs.append(text)
        return paragraphs

    @classmethod
    def _has_following_attr(cls, card: Tag) -> bool:
        """カード直後の兄弟 <p> 群に性別マーカー (オス/メス) があれば True (形式 B)"""
        joined = " ".join(cls._collect_following_attr_paragraphs(card))
        return bool(cls._SEX_RE.search(joined))

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        """一覧ページから動物の仮想 URL を返す

        基底実装は行が 0 件のとき `ParsingError` を投げるが、柏市の
        テンプレートでは 0 件が正常状態として発生し得る:

        - 「現在、保護動物はおりません」等の告知テキストがあるページ
        - 告知すら無く、<h3>犬</h3>/<h3>猫</h3> の種別見出しだけ残して
          カードが丸ごと省略されるページ (2026-07 観測。旧実装はこれを
          ParsingError にして連続失敗 → broken 扱いになっていた)

        いずれかを検出した場合は空リストを返し、それ以外で行が
        見つからなかった場合のみ `ParsingError` を伝播する。
        カード構造の変化で偽の 0 件になるリスクは、収集側の件数低下検知
        (前回 N 件 → 今回 0 件の warning) で補足する運用。
        """
        rows = self._load_rows()
        if not rows:
            if self._html_cache and (
                self._EMPTY_STATE_PATTERN.search(self._html_cache)
                or self._is_cardless_inventory(self._html_cache)
            ):
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

        # 形式 A (ラベル) を優先。col2R にラベルが無ければ形式 B (自由テキスト)。
        if self._has_labeled_field(card):
            fields = self._parse_labeled_card(card)
        else:
            fields = self._parse_freetext_card(card)

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
                # 「種類」(雑種/柴犬/三毛猫等)は species 本体ではなく犬種=breed。
                # fields["species"] に抽出済みだが未伝搬で欠損していた。
                breed=fields.get("species", ""),
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
                # 「特徴」自由文を性格・特徴(description)として保存（年齢/体重補完だけに
                # 使い捨てていたものを識別情報として残す。PII伏字は normalizer 側で実施）
                description=features,
            )
        except Exception as e:
            raise ParsingError(f"RawAnimalData バリデーション失敗: {e}", url=virtual_url) from e

    def _parse_labeled_card(self, card: Tag) -> dict[str, str]:
        """形式 A: col2R 内の「ラベル：値」<p> 群をパースする (hogo.html)"""
        col2r = card.select_one("div.col2R")
        fields: dict[str, str] = {}
        if not isinstance(col2r, Tag):
            return fields
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
        return fields

    def _parse_freetext_card(self, card: Tag) -> dict[str, str]:
        """形式 B: カード直後の兄弟 <p> 群 (自由文) から属性を抽出する (satoya.html)

        例: "オス(去勢手術済み)　R6.9月生(推定)　ワクチン接種済み、FeLV(-)、FIV(-)"
        - sex:  オス / メス を拾う
        - age:  「N才」「R6.9月生」「H28.4月生」を normalizer 可読形式に変換
        - color/location/shelter_date は本形式に存在しないため空 (= 不明扱い)
        - 全 <p> を連結したものを _features として保持し、後段で size/age 補完に使う
        """
        paragraphs = self._collect_following_attr_paragraphs(card)
        joined = " ".join(paragraphs)
        fields: dict[str, str] = {}

        sex_match = self._SEX_RE.search(joined)
        if sex_match:
            fields["sex"] = sex_match.group(1)

        age = self._extract_age_from_freetext(joined)
        if age:
            fields["age"] = age

        # 自由文全体を特徴として残す (size 推定の体重ヒント等に使う)
        if joined:
            fields["_features"] = joined
        return fields

    @classmethod
    def _extract_age_from_freetext(cls, text: str) -> str:
        """自由文から normalizer が解釈できる年齢文字列を抽出する (形式 B)

        - "R6.9月生(推定)"  → "2024年9月" (令和6年 = 2024)
        - "H28.4月生(推定)" → "2016年4月" (平成28年 = 2016)
        - "1才(推定)"       → "1才"
        いずれも DataNormalizer 側で月数換算される (才→歳 / YYYY年M月 対応済)。
        生年月の表記を直接年齢表記より優先する (より正確なため)。
        """
        if not text:
            return ""
        # 元号略記の生年月 (R6.9月生 等) を西暦 "YYYY年M月" に変換
        era = cls._ERA_BIRTH_RE.search(text)
        if era:
            prefix, year_n, month = era.group(1), int(era.group(2)), int(era.group(3))
            base = cls._ERA_BASE_YEAR.get(prefix)
            if base is not None and 1 <= month <= 12:
                return f"{base + year_n}年{month}月"
        # 直接年齢表記 (1才 / 2歳 / 6ヶ月)
        direct = cls._DIRECT_AGE_RE.search(text)
        if direct:
            return direct.group(0)
        return ""

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
