"""横須賀市動物愛護センター rule-based adapter

対象ドメイン: https://www.yokosuka-doubutu.com/

特徴:
- WordPress (Toolset Views) で構築された自治体サイト。
- 同一テンプレートで 6 サイト (保護: 犬/猫/その他、譲渡: 犬/猫/その他)
  を運用しており、URL のみが異なるため 1 つのアダプタで全て扱える。
- 一覧ページ (`/protected-animals-XXX/`, `/jouto-animals-XXX/`) では
  `<ul id="animals-list"><li><div class="list-box"><a href="...">` 形式で
  詳細ページへのリンクを並べる。
- 詳細ページ (`/protected-animals/<番号>/` 等) は `<th>` を持たない
  2 列テーブル `<td>項目名</td><td>値</td>` で各フィールドを表現する。
  そのため `WordPressListAdapter` の `_extract_by_label` を拡張して
  `<td>/<td>` ペアからも値を取れるようにオーバーライドしている。
- 電話番号は詳細ページ本文には無く、フッタの `#footer-text-2` に
  "TEL : 046-869-0040" の形で記載されている。
- 動物写真は `<div id="photos"><ul><li><img></li>...</ul></div>` 配下。
"""

from __future__ import annotations

import re
from typing import ClassVar

from bs4 import BeautifulSoup, Tag

from ..registry import SiteAdapterRegistry
from ..wordpress_list import FieldSpec, WordPressListAdapter


class YokosukaDoubutuAdapter(WordPressListAdapter):
    """横須賀市動物愛護センター用 rule-based adapter

    保護収容/譲渡 × 犬/猫/その他 の 6 サイトで共通テンプレートを使用する。
    """

    LIST_LINK_SELECTOR: ClassVar[str] = "ul#animals-list li a"

    FIELD_SELECTORS: ClassVar[dict[str, FieldSpec]] = {
        # 種類（ブリード相当。例: "豆柴", "雑種", "MIX"）
        # 注: 「種類」セルは犬種/猫種を含むためそのままでは species (犬/猫/その他)
        # にならない。_postprocess_fields で「分類」セル ("猫(保護収容)" 等) を
        # 優先採用し、無いときはサイト名から推定する。
        "species": FieldSpec(label="種類"),
        # 分類（species 推定の主ソース。例: "猫(保護収容)", "犬(譲渡)"）
        # _postprocess_fields でここから「犬/猫/その他」を取り出し species に格納する。
        "category_label": FieldSpec(label="分類"),
        # 性別（例: "メス", "オス"）
        "sex": FieldSpec(label="性別"),
        # 年齢: 詳細ページに専用フィールドが無い
        "age": FieldSpec(label="年齢"),
        # 特徴（毛色を含むことが多い。例: "黒白"）
        # 注: 譲渡カテゴリでは長文の説明が入るため _postprocess_fields で
        # 30 文字超は color から外し description として扱う。
        "color": FieldSpec(label="特徴"),
        # 大きさ: 専用フィールドが無いことが多い (譲渡犬の一部のみ)
        "size": FieldSpec(label="大きさ"),
        # 体重 (size 推定の補助ソース。例: "29Kg", "9.6Kg")
        # 詳細ページの 2 列テーブルに <td>体重</td><td>値</td> として存在することが
        # ある。size が空のときに「小/中/大」へ変換する。
        "weight": FieldSpec(label="体重"),
        # 収容日（例: "R8.5.14（木曜日）"）
        "shelter_date": FieldSpec(label="収容日"),
        # 収容場所（例: "池田町"）
        "location": FieldSpec(label="収容場所"),
        # 電話番号: 本文には無くフッタからの抽出
        "phone": FieldSpec(selector="#footer-text-2"),
    }

    # 「特徴」を color として扱える長さの上限。これを超える場合は
    # 毛色ではなく譲渡対象動物の説明文と判定し color フィールドから外す。
    _COLOR_MAX_LEN: ClassVar[int] = 30

    # 「種類」セル併記の毛色 (例: "黒白", "ブラウンマッカレルタビー") として
    # 採用する最大長。実観測の最長 "ブラウンマッカレルタビー" は 12 文字
    # なので 15 を上限としておく (これを超えるものは説明文混入と判定)。
    _BREED_COLOR_MAX_LEN: ClassVar[int] = 15

    # 「特徴」セル内に混在する年齢表記を取り出す正規表現 (2026-05 観測)。
    # 例: 「キジ白、推定1歳」「茶トラ、約3か月」「黒、子猫」「成犬」
    # 抽出後は color テキストから該当部分を除去する。
    _AGE_IN_FEATURE_RE: ClassVar[str] = (
        r"(?:(?:推定|約)?\s*\d+\s*(?:歳|才|か月|ヶ月|ヵ月|カ月|ケ月)(?:\s*\d+\s*(?:か月|ヶ月|ヵ月|カ月|ケ月))?"
        r"|子犬|子猫|成犬|成猫|幼犬|幼猫|老犬|老猫)"
    )

    # 体重 → size 推定の境界 (kg)。oita_aigo / kumamoto_doubutuaigo と同基準。
    _SIZE_BOUNDARY_SMALL_KG: ClassVar[float] = 5.0
    _SIZE_BOUNDARY_LARGE_KG: ClassVar[float] = 15.0

    # 譲渡カテゴリ (`/adopted-animals/`) の詳細ページは「収容場所」セルを
    # 持たないため location が空になり normalizer で "不明" になる。
    # 譲渡対象動物は施設で会うため、施設名を location に代入する
    # (zaidan_fukuoka_douai._CENTER_FACILITY_NAME と同じ運用)。
    _CENTER_FACILITY_NAME: ClassVar[str] = "横須賀市動物愛護センター"

    # 動物写真は `#photos` ブロック配下に集約されている
    IMAGE_SELECTOR: ClassVar[str] = "div#photos img"

    # ─────────────────── 拡張 ───────────────────

    def _postprocess_fields(
        self, fields: dict[str, str], detail_url: str, soup: BeautifulSoup
    ) -> None:
        """species の正規化、size 推定、color/age 分離を行う

        species:
          - 「種類」セルは犬種/猫種が入るため species (犬/猫/その他) にならない。
            「分類」セル ("猫(保護収容)" 等) を優先して上書きし、無い場合は
            サイト名 (横須賀市（保護猫） 等) から推定する。

        size:
          - 詳細ページに「大きさ」セルが無く、譲渡犬の一部だけ「体重」セル
            (例: "29Kg") が存在する。size が空のときは体重から「小/中/大」を
            推定する (kumamoto_doubutuaigo._weight_to_size と同基準)。

        color/age (既存ロジック):
          - 「キジ白、推定1歳」のように color と age が同セルに混在するため
            年齢を分離する。長文 (`_COLOR_MAX_LEN` 超) は color から除外する。

        color (種類セル併記、2026-06 追加):
          - 譲渡カテゴリでは「種類」セルにブリードと毛色が「、」区切りで
            併記される (例: "MIX、黒白", "スコティッシュフォールド、ホワイト")。
            「特徴」セルから color が取れない場合のみ、後半部分を color に
            採用する (区切りなし/後半が長文の場合はスキップ)。
          - species 正規化で「種類」セルが上書きされる前に処理する。

        location (譲渡カテゴリのデフォルト、2026-06 追加):
          - 譲渡 (`/adopted-animals/`) は「収容場所」セルを持たないため
            location が空 → normalizer で "不明" になる。譲渡対象動物は
            施設で会うため、施設名を location に充てる。
        """
        # 「種類」セルから毛色を抽出 (species 上書き前に実施)
        breed_color = self._extract_color_from_breed_cell(fields.get("species", ""))
        if breed_color and not fields.get("color"):
            fields["color"] = breed_color

        # species: 「分類」セル → サイト名の順で正規化
        # 注: 基底実装は _postprocess_fields の **後** に
        # `any(fields.values())` で空ページを検出して ParsingError を投げる。
        # サイト名からの推定で species を埋めると空ページが検出できなくなるため、
        # 元 fields に 1 つでも値がある場合のみサイト名フォールバックを行う。
        had_any_value = any(
            v for k, v in fields.items() if k not in {"species", "category_label"}
        ) or bool(fields.get("species") or fields.get("category_label"))
        species_from_category = self._species_from_category_label(fields.get("category_label", ""))
        if species_from_category:
            fields["species"] = species_from_category
        elif had_any_value and (
            not fields.get("species") or self._looks_like_breed(fields.get("species", ""))
        ):
            # 「種類」セルが空、または犬種/猫種そのもの (e.g. "MIX", "豆柴") で
            # species (犬/猫) として使えない場合はサイト名から推定する。
            inferred = self._infer_species_from_site_name(self.site_config.name)
            if inferred:
                fields["species"] = inferred

        color = fields.get("color", "")
        if color:
            m = re.search(self._AGE_IN_FEATURE_RE, color)
            if m:
                age_token = m.group(0).strip()
                if not fields.get("age"):
                    fields["age"] = age_token
                # color から年齢部分を除去 (区切り文字も整理)
                color = re.sub(self._AGE_IN_FEATURE_RE, "", color)
                color = re.sub(r"[、,。\s]{2,}", "、", color).strip("、 ,")
                fields["color"] = color

        # 長文判定 (説明文相当) は color から除外
        if fields.get("color") and len(fields["color"]) > self._COLOR_MAX_LEN:
            fields["color"] = ""

        # size: 「大きさ」セル優先、なければ体重から推定
        if not fields.get("size"):
            fields["size"] = self._weight_to_size(fields.get("weight", ""))

        # location: 譲渡カテゴリで空なら施設名を充てる
        if not fields.get("location") and "/adopted-animals/" in detail_url:
            fields["location"] = self._CENTER_FACILITY_NAME

    @classmethod
    def _extract_color_from_breed_cell(cls, breed_cell: str) -> str:
        """「種類」セル ("MIX、黒白" 等) の区切り後ろから毛色候補を取り出す

        - 区切りは「、」/「,」/「，」(全角カンマ) を受け付ける
        - 最後の区切り以降の文字列を毛色候補とする
        - 候補が空 / 長すぎる (`_COLOR_MAX_LEN` 超) 場合は採用しない
        - 候補が species 語彙 ("犬"/"猫"/"その他") そのものなら毛色ではない

        例:
        - "MIX、黒白" → "黒白"
        - "スコティッシュフォールド、ブラウンマッカレルタビー" → "ブラウンマッカレルタビー"
        - "ミヌエット、レッド＆ホワイト" → "レッド＆ホワイト"
        - "フレンチブルドッグ" → "" (区切りなし)
        - "MIX、とても可愛い毛並みの…" → "" (長文)
        """
        if not breed_cell:
            return ""
        parts = re.split(r"[、,，]", breed_cell)
        if len(parts) < 2:
            return ""
        candidate = parts[-1].strip()
        if not candidate:
            return ""
        if len(candidate) > cls._BREED_COLOR_MAX_LEN:
            return ""
        if candidate in {"犬", "猫", "その他"}:
            return ""
        return candidate

    @classmethod
    def _species_from_category_label(cls, label: str) -> str:
        """「分類」セル ("猫(保護収容)", "犬(譲渡)") から「犬/猫/その他」を抽出

        - "犬" を含む → "犬"
        - "猫" を含む → "猫"
        - それ以外 (空含む) → ""
        """
        if not label:
            return ""
        if "犬" in label:
            return "犬"
        if "猫" in label:
            return "猫"
        return ""

    @staticmethod
    def _infer_species_from_site_name(name: str) -> str:
        """サイト名 ("横須賀市（保護犬）" 等) から動物種別を推定する

        - "犬" と "猫" 両方含む (想定なし) → "その他"
        - "犬" のみ → "犬"
        - "猫" のみ → "猫"
        - "その他" を含む → "その他"
        - それ以外 → ""
        """
        has_dog = "犬" in name
        has_cat = "猫" in name
        if has_dog and has_cat:
            return "その他"
        if has_dog:
            return "犬"
        if has_cat:
            return "猫"
        if "その他" in name:
            return "その他"
        return ""

    # 「種類」セルが犬種/猫種そのもの (species ではなくブリード) と判定するための
    # ヒューリスティック。横須賀観測の値: "豆柴", "雑種", "MIX", "ラブラドルレトリバー",
    # "スコティッシュフォールド、ブラウンマッカレルタビー" など。
    # 値が「犬」「猫」「その他」そのものなら species として扱える。
    @staticmethod
    def _looks_like_breed(value: str) -> bool:
        if not value:
            return False
        # 値そのものが species 語彙 (1〜3文字) なら breed ではない
        return value not in {"犬", "猫", "その他"}

    @classmethod
    def _weight_to_size(cls, weight_text: str) -> str:
        """「29Kg」「9.6kg」のような体重テキストを「小/中/大」に変換

        - 5kg 未満: 小
        - 5kg 以上 15kg 未満: 中
        - 15kg 以上: 大
        - 数値が拾えない場合 ("不明" / 空): 空文字

        oita_aigo / kumamoto_doubutuaigo._weight_to_size と同じ境界。
        """
        if not weight_text:
            return ""
        m = re.search(r"(\d+(?:\.\d+)?)", weight_text)
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

    def _extract_by_label(self, soup: BeautifulSoup, label: str) -> str:
        """基底の `<dt>/<dd>`, `<th>/<td>` に加えて `<td>/<td>` パターンも探す

        本サイトの詳細ページは `<th>` を使わず、2 列テーブルの
        最初の `<td>` を見出し、次の `<td>` を値として並べる構造。
        基底実装で見つからなかった場合のフォールバックとして
        同じ `<tr>` 内で「ラベルセル -> 次の兄弟 td」のペアを探す。
        """
        # まず基底の dl / th-td パターンを試す
        value = super()._extract_by_label(soup, label)
        if value:
            return value

        # フォールバック: <td>label</td><td>value</td> の 2 列テーブル
        for td in soup.find_all("td"):
            if not isinstance(td, Tag):
                continue
            # ネストした要素を含めずにテキスト一致を見たいので strip 比較
            cell_text = td.get_text(strip=True)
            if not cell_text or label not in cell_text:
                continue
            # 同一 tr の中で次の td を値として採用
            sibling = td.find_next_sibling("td")
            if sibling is None:
                continue
            sibling_text = sibling.get_text(strip=True)
            if sibling_text:
                return sibling_text
        return ""


# ─────────────────── サイト登録 ───────────────────
# 同一テンプレート上で運用される 6 サイトを同一 adapter にマップする。
for _site_name in (
    "横須賀市（保護犬）",
    "横須賀市（保護猫）",
    "横須賀市（保護その他）",
    "横須賀市（譲渡犬）",
    "横須賀市（譲渡猫）",
    "横須賀市（譲渡その他）",
):
    SiteAdapterRegistry.register(_site_name, YokosukaDoubutuAdapter)
