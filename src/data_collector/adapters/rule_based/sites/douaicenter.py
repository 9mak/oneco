"""旭川市あにまある (douaicenter.jp) 用 rule-based adapter

同一ドメイン上の 8 サイト (譲渡犬/猫/他、収容犬/猫/他、市民保護犬/猫) が
同じテンプレートを共有しているため、1 つの adapter クラスで全サイトを賄う。

list ページ:
    - 各動物カードは `<div class="animal-list-img-box">` で囲まれ、
      内部の `<a href="/animal/{id}">` (または `/other-animal/{id}`) が
      detail ページへのリンク。
    - 同一 detail URL が画像リンク + テキストリンクで重複出現するが、
      WordPressListAdapter 側の seen 集合で重複除去される。

detail ページ:
    - WordPress 系の典型構造で、`<dl><dt>性別</dt><dd>...</dd></dl>` または
      `<table><th>性別</th><td>...</td></table>` のいずれかでフィールドを表現する。
      WordPressListAdapter._extract_by_label が両方対応するためそのまま乗る。
"""

from __future__ import annotations

from ..registry import SiteAdapterRegistry
from ..wordpress_list import FieldSpec, WordPressListAdapter


class DouaicenterAdapter(WordPressListAdapter):
    """旭川市あにまある 共通アダプター

    list / detail 両方のテンプレートが 8 サイト共通なので、サイト名ごとに
    クラスを分けず、registry に複数の site_name を 1 クラスで束ねる。
    """

    # /animal/{id} と /other-animal/{id} の両方の detail を抽出。
    # animal-list-img-box 内のリンクのみ対象にすることで、ヘッダ/メニュー側の
    # `/animal/list/...` のような一覧ページ自体へのリンクを排除する。
    LIST_LINK_SELECTOR = (
        ".animal-list-img-box a[href*='/animal/'],"
        " .animal-list-img-box a[href*='/other-animal/']"
    )

    # detail ページの定義リスト/テーブル見出しに対応するラベル
    FIELD_SELECTORS = {
        "species": FieldSpec(label="種類"),
        "sex": FieldSpec(label="性別"),
        "age": FieldSpec(label="年齢"),
        "color": FieldSpec(label="毛色"),
        "size": FieldSpec(label="体格"),
        "shelter_date": FieldSpec(label="収容日"),
        "location": FieldSpec(label="収容場所"),
        "phone": FieldSpec(label="連絡先"),
    }

    # detail ページ本体の動物写真は WordPress uploads 配下に配置される。
    # サイドバー/ヘッダの装飾画像は `_filter_image_urls` の uploads フィルタで除外される。
    IMAGE_SELECTOR = "img"


# ─────────────────── レジストリ登録 ───────────────────
# sites.yaml の 8 件を 1 つの adapter クラスで束ねる
_SITE_NAMES = (
    "旭川市あにまある（譲渡犬）",
    "旭川市あにまある（譲渡猫）",
    "旭川市あにまある（譲渡その他）",
    "旭川市あにまある（収容犬）",
    "旭川市あにまある（収容猫）",
    "旭川市あにまある（収容その他）",
    "旭川市あにまある（市民保護犬）",
    "旭川市あにまある（市民保護猫）",
)

for _name in _SITE_NAMES:
    SiteAdapterRegistry.register(_name, DouaicenterAdapter)
