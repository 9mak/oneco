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

from typing import ClassVar

from ..registry import SiteAdapterRegistry
from ..wordpress_list import FieldSpec, WordPressListAdapter


class AnimalNetNagasakiAdapter(WordPressListAdapter):
    """ながさき犬猫ネット 共通アダプター

    list / detail テンプレートが 4 サイト共通なので、サイト名ごとに
    クラスを分けず、registry に複数の site_name を 1 クラスで束ねる。
    """

    # `list-area` (一覧ブロック) 配下の `/animal/no-...` 形式の `<a>` のみを
    # 対象にする。これによりヘッダ/フッタの `/syuuyou` 等のカテゴリ遷移リンクや、
    # 検索パネル内のリンク等の混入を防ぐ。
    LIST_LINK_SELECTOR: ClassVar[str] = "div.list-area a[href*='/animal/no-']"

    # detail ページの定義リスト見出しに対応するラベル。
    # 一覧時の inline data (品種 / 性別 / 年齢 / 公開日) 相当に加え、
    # 詳細ページで一般的に提供される毛色・大きさ・収容日・収容場所・連絡先を
    # ラベル一致で拾う。同じセマンティクスの label 候補が複数ある場合は
    # `_extract_by_label` の最初にヒットしたものが採用される。
    FIELD_SELECTORS: ClassVar[dict[str, FieldSpec]] = {
        # 種類/品種 (例: "ミックス（雑種）")
        "species": FieldSpec(label="品種"),
        # 性別 (例: "オス", "メス", "不明")
        "sex": FieldSpec(label="性別"),
        # 年齢 (例: "約４ヶ月", "不明")
        "age": FieldSpec(label="年齢"),
        # 毛色
        "color": FieldSpec(label="毛色"),
        # 大きさ (体格)
        "size": FieldSpec(label="大きさ"),
        # 収容日 / 公開日 (詳細ページ側で「収容日」が無い場合は空)
        "shelter_date": FieldSpec(label="収容日"),
        # 収容場所 (保健所名等)
        "location": FieldSpec(label="収容場所"),
        # 連絡先 (電話番号)
        "phone": FieldSpec(label="連絡先"),
    }

    # 動物写真は `/wp/wp-content/uploads/YYYY/MM/...jpg` 配下に置かれる。
    # ヘッダ等のロゴ画像 (`/wp-content/themes/ngk-animal/...`) は
    # 基底 `_filter_image_urls` の uploads フィルタで自動排除される。
    IMAGE_SELECTOR: ClassVar[str] = "img"


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
