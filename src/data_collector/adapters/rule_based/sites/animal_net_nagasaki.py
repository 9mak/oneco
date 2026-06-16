"""ながさき犬猫ネット rule-based adapter

対象ドメイン: https://animal-net.pref.nagasaki.jp/

特徴:
- WordPress (テーマ `ngk-animal`) で構築された自治体サイト。
- 同一ドメイン上で 4 サイト (募集中:保健所収容/その他譲渡、行方不明、保護)
  が共通テンプレートを使用しているため、1 つの adapter で全サイトを賄う。
- 一覧ページ (`/syuuyou`, `/jyouto`, `/maigo`, `/hogo`) では
  `<div class="list-area"><ul><li><a href="/animal/no-XXXXX/">...</a></li></ul></div>`
  形式で詳細ページへのリンクを並べる。`list-area` 配下に絞ることで
  ヘッダ / フッタ / 検索パネルの遷移リンクや、ページャ等を確実に排除する。
- 詳細ページは `<dl>` 配下の `<div class="list-box">` でラップされた
  `<dt>項目名</dt><dd>値</dd>` の定義リストで各フィールドを表現する。
  bs4 の `find_next_sibling` は同一親内の兄弟関係で `<dt>`/`<dd>` を
  拾えるため、`WordPressListAdapter._extract_by_label` がそのまま乗る。
- 動物写真は `/wp/wp-content/uploads/...` 配下に配置されるため、
  基底の `_filter_image_urls` (uploads 配下のみ採用) がそのまま機能する。
"""

from __future__ import annotations

import re
from typing import ClassVar

from bs4 import BeautifulSoup

from ..registry import SiteAdapterRegistry
from ..wordpress_list import FieldSpec, WordPressListAdapter


class AnimalNetNagasakiAdapter(WordPressListAdapter):
    """ながさき犬猫ネット 共通アダプター

    list / detail テンプレートが 4 サイト共通なので、サイト名ごとに
    クラスを分けず、registry に複数の site_name を 1 クラスで束ねる。

    detail ページは `<li><p>品種</p><p>ミックス（雑種）</p></li>` のような
    `<li>` 内に 2 つの `<p>` を並べる構造。`WordPressListAdapter._extract_by_label`
    が前提とする `<dt>/<dd>` `<th>/<td>` には載らないため、
    `_postprocess_fields` で独自パースする。
    """

    # `list-area` (一覧ブロック) 配下の `/animal/no-...` 形式の `<a>` のみを
    # 対象にする。これによりヘッダ/フッタの `/syuuyou` 等のカテゴリ遷移リンクや、
    # 検索パネル内のリンク等の混入を防ぐ。
    LIST_LINK_SELECTOR: ClassVar[str] = "div.list-area a[href*='/animal/no-']"

    # detail は `<li><p>label</p><p>value</p></li>` 構造のため
    # 通常のラベル抽出は効かない。FIELD_SELECTORS は空にして
    # `_postprocess_fields` 側で全フィールドを埋める。
    FIELD_SELECTORS: ClassVar[dict[str, FieldSpec]] = {
        "species": FieldSpec(label="品種"),
        "sex": FieldSpec(label="性別"),
        "age": FieldSpec(label="年齢"),
        "color": FieldSpec(label="毛色"),
        "size": FieldSpec(label="大きさ"),
        "shelter_date": FieldSpec(label="収容日"),
        "location": FieldSpec(label="収容場所"),
        "phone": FieldSpec(label="連絡先"),
    }

    # 動物写真は `/wp/wp-content/uploads/YYYY/MM/...jpg` 配下に置かれる。
    # ヘッダ等のロゴ画像 (`/wp-content/themes/ngk-animal/...`) は
    # 基底 `_filter_image_urls` の uploads フィルタで自動排除される。
    IMAGE_SELECTOR: ClassVar[str] = "img"

    # `<li><p>label</p><p>value</p></li>` 構造のラベル → フィールド名対応表。
    # カテゴリ (syuuyou/jyouto/maigo/hogo) によって使うラベル名が変わるため候補を網羅する。
    _LI_LABEL_MAP: ClassVar[dict[str, str]] = {
        "品種": "species",
        "性別": "sex",
        "年齢": "age",
        "毛色": "color",
        "大きさ": "size",
        "体格": "size",
        # 収容日相当
        "収容日": "shelter_date",
        "保護日": "shelter_date",
        "いなくなった日時": "shelter_date",
        "登録日": "shelter_date",
        "公開日": "shelter_date",
        # 場所相当
        "収容場所": "location",
        "保護場所": "location",
        "いなくなった場所": "location",
        "地区": "_location_fallback",  # 詳細場所が無い時の代替
        # 電話番号抽出元
        "問い合わせ先": "_phone_source",
        "連絡先": "_phone_source",
        # species 補正用: 模様(柄)。三毛/サビ/キジ/トラ は猫固有のため種別確定に使う。
        # live HTML の実ラベルは「模様・柄」(中黒・柄付き)。PR #204 は「模様」のみ
        # 登録し exact-match で外れ不発だったため両表記を登録する。
        "模様": "_pattern",
        "模様・柄": "_pattern",
    }
    # 猫固有の柄 (三毛・サビは遺伝的に猫のみ、キジトラ/茶トラは猫の慣用)。
    _CAT_ONLY_PATTERNS: ClassVar[tuple[str, ...]] = ("三毛", "サビ", "キジ", "トラ")

    # `/animal/no-12345/` から個体番号 (12345) を取り出す。
    _NO_RE: ClassVar[re.Pattern[str]] = re.compile(r"/animal/no-(\d+)")

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        """一覧を取得すると同時に、ソース自身の犬猫分類を権威ソースとして取り込む。

        detail ページは品種「ミックス（雑種）」のみで犬猫を持たず、サイト名にも
        犬猫両方が含まれるため species が その他 化していた (全その他191件の最大
        要因=長崎98件)。ソースは list_url に `?animal-type=dog` / `?animal-type=cat`
        を付けると犬/猫で完全分割するため、これを取得して `{個体番号: 犬|猫}` を
        構築し _postprocess_fields で上書きする (色推測ではなくソース権威分類)。
        """
        urls = super().fetch_animal_list()
        # 動物が 0 件の種別では分類取得を省略 (無駄なリクエストを避ける)。
        self._species_by_no: dict[str, str] = self._build_species_by_no() if urls else {}
        return urls

    def _typed_list_url(self, animal_type: str) -> str:
        """list_url に `?animal-type=...` を付与する (既存クエリがあれば `&`)。"""
        base = self.site_config.list_url
        sep = "&" if "?" in base else "?"
        return f"{base}{sep}animal-type={animal_type}"

    def _build_species_by_no(self) -> dict[str, str]:
        """`?animal-type=dog|cat` 一覧から `{個体番号: 犬|猫}` を構築する。"""
        mapping: dict[str, str] = {}
        for animal_type, species in (("dog", "犬"), ("cat", "猫")):
            try:
                html = self._http_get(self._typed_list_url(animal_type))
            except Exception:
                # 分類ソース取得失敗時は通常フロー (品種/模様/サイト名補正) に委ねる。
                continue
            soup = BeautifulSoup(html, "html.parser")
            for link in soup.select(self.LIST_LINK_SELECTOR):
                href = link.get("href")
                if not href or not isinstance(href, str):
                    continue
                if m := self._NO_RE.search(href):
                    mapping[m.group(1)] = species
        return mapping

    def _postprocess_fields(
        self, fields: dict[str, str], detail_url: str, soup: BeautifulSoup
    ) -> None:
        """`<li><p>label</p><p>value</p></li>` 構造から残フィールドを補完する。

        既にラベル抽出で値が埋まっているフィールドは尊重し、空の場合のみ上書きする。
        """
        extras: dict[str, str] = {}
        for li in soup.select("li"):
            ps = li.find_all("p", recursive=False)
            if len(ps) < 2:
                continue
            label = ps[0].get_text(strip=True)
            value = ps[1].get_text(strip=True)
            field = self._LI_LABEL_MAP.get(label)
            if field is None:
                continue
            if field.startswith("_"):
                extras[field] = value
            elif not fields.get(field):
                fields[field] = value

        # ソース自身の犬猫分類 (?animal-type=dog|cat) を最優先の権威ソースとして
        # 適用する。fetch_animal_list 経由で構築済みの場合のみ作動し、detail を
        # 直接呼ぶ既存経路では未設定 → 従来どおり品種/模様/サイト名補正に委ねる。
        species_by_no = getattr(self, "_species_by_no", None)
        if species_by_no and (m := self._NO_RE.search(detail_url)):
            if authoritative := species_by_no.get(m.group(1)):
                fields["species"] = authoritative

        # location が空なら「地区」を fallback として使う
        if not fields.get("location") and extras.get("_location_fallback"):
            fields["location"] = extras["_location_fallback"]

        # 連絡先テキスト or 本文の「連絡先 0920-...」パターンから電話番号を抽出
        if not fields.get("phone"):
            phone_text = extras.get("_phone_source", "") or soup.get_text(" ", strip=True)
            m = re.search(r"(\d{2,4}-\d{2,4}-\d{3,4})", phone_text)
            if m:
                fields["phone"] = m.group(1)

        # species が犬猫判定不能でも、模様(柄)が猫固有(三毛/サビ/キジ/トラ)なら
        # 猫と確定する。長崎犬猫ネットは品種が「ミックス（雑種）」かつサイト名に
        # 犬猫両方を含むため下のサイト名補正が効かず、その他化していた
        # (2026-06-16, 全その他191件の最大要因=長崎98件のうち25件を救済)。
        species = fields.get("species", "")
        if not any(kw in species for kw in ("犬", "猫", "いぬ", "ねこ", "イヌ", "ネコ")):
            pattern = extras.get("_pattern", "")
            if any(p in pattern for p in self._CAT_ONLY_PATTERNS):
                fields["species"] = "猫"

        # species が「ミックス（雑種）」など犬猫判定不能でもサイト名で補正できる場合のみ。
        # サイト名に「犬」「猫」が片方だけ含まれる場合に限定（両方含まれるサイト名
        # 例「長崎犬猫ネット（譲渡）」では補正せず元値のまま DataNormalizer に委ねる）。
        species = fields.get("species", "")
        if not any(kw in species for kw in ("犬", "猫", "いぬ", "ねこ", "イヌ", "ネコ")):
            site_name = getattr(self.site_config, "name", "")
            has_dog = "犬" in site_name
            has_cat = "猫" in site_name
            if has_dog and not has_cat:
                fields["species"] = "犬"
            elif has_cat and not has_dog:
                fields["species"] = "猫"

        # 譲渡カテゴリ等で shelter_date が取れない場合は DataNormalizer 側で
        # 「データ取得日」にフォールバックされる（全 adapter 共通のセーフネット）。


# ─────────────────── サイト登録 ───────────────────
# 同一テンプレート上で運用される 4 サイトを同一 adapter にマップする。
_SITE_NAMES = (
    "長崎犬猫ネット（保健所収容）",
    "長崎犬猫ネット（譲渡）",
    "長崎犬猫ネット（迷子）",
    "長崎犬猫ネット（保護）",
)

for _name in _SITE_NAMES:
    SiteAdapterRegistry.register(_name, AnimalNetNagasakiAdapter)
