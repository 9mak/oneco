"""一般財団法人 滋賀県動物保護管理協会 (sapca.jp) 用 rule-based adapter

対象ドメイン: https://www.sapca.jp/lost (迷い犬・猫)

特徴:
- list ページ (`/lost`) は `<ul class="list">` 配下に各動物カード
  (`<li>` + `<a href="/lost/{id}.html">`) が並ぶ典型的な list+detail 構造。
- 個別 detail ページ (`/lost/{id}.html`) には WordPress 系の
  `<table><th>項目名</th><td>値</td></table>` または `<dl><dt>...<dd>...` で
  動物の属性が掲載されている (種類/性別/毛色/収容日/連絡先 など)。
- list ページ HTML 内で同一 detail URL は 1 度しか出現しない
  (画像 + ラベルが同じ `<a>` で囲まれているため) ので、
  `WordPressListAdapter` の seen 集合による重複除去で十分。
- 既に飼い主に戻った/譲渡完了したカードには `class="sumi"` が付くが、
  list_url から見える時点では運用上「掲載中」として扱い、ここでは
  特別なフィルタは行わない (在庫 0 件も許容される)。
"""

from __future__ import annotations

from ..registry import SiteAdapterRegistry
from ..wordpress_list import FieldSpec, WordPressListAdapter


class SapcaAdapter(WordPressListAdapter):
    """滋賀県動物保護管理協会 (sapca.jp) 用 list+detail アダプター"""

    # `<ul class="list"> > <li> > <a href="/lost/{id}.html">` のリンクのみ抽出。
    # サイドバーやヘッダ側の `/lost` 自体へのリンクを取り込まないよう、
    # 末尾が `.html` で終わるパターンに限定する (sites.yaml と同等)。
    LIST_LINK_SELECTOR = "ul.list a[href*='/lost/'][href$='.html']"

    # detail ページの定義リスト/テーブル見出しに対応するラベル。
    # WordPressListAdapter._extract_by_label が <dt>/<th> のいずれにも対応する。
    FIELD_SELECTORS = {
        "species": FieldSpec(label="種類"),
        "sex": FieldSpec(label="性別"),
        "age": FieldSpec(label="年齢"),
        "color": FieldSpec(label="毛色"),
        "size": FieldSpec(label="体格"),
        "shelter_date": FieldSpec(label="保護日"),
        "location": FieldSpec(label="保護場所"),
        "phone": FieldSpec(label="連絡先"),
    }

    # 動物写真は WordPress uploads 配下に置かれる。サイドバーの装飾画像 (themes 配下)
    # は基底の `_filter_image_urls` の uploads フィルタで除外される。
    IMAGE_SELECTOR = "img"


# ─────────────────── サイト登録 ───────────────────
SiteAdapterRegistry.register("滋賀県動物保護管理センター（迷い犬猫）", SapcaAdapter)
