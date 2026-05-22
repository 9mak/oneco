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
    }

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

        # location が空なら「地区」を fallback として使う
        if not fields.get("location") and extras.get("_location_fallback"):
            fields["location"] = extras["_location_fallback"]

        # 連絡先テキスト or 本文の「連絡先 0920-...」パターンから電話番号を抽出
        if not fields.get("phone"):
            phone_text = extras.get("_phone_source", "") or soup.get_text(" ", strip=True)
            m = re.search(r"(\d{2,4}-\d{2,4}-\d{3,4})", phone_text)
            if m:
                fields["phone"] = m.group(1)

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
