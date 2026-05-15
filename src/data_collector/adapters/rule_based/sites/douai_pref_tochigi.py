"""栃木県動物愛護指導センター rule-based adapter

対象ドメイン: https://www.douai.pref.tochigi.lg.jp/

特徴:
- WordPress テーマ `serum_tcd096` (TCD 系) で構築された自治体サイト。
- 同一ドメイン上で 3 サイト (保護動物 / 譲渡動物 / 迷子動物) が
  共通テンプレートを使用しているため、1 つの adapter で全サイトを賄う。
- 一覧ページのレイアウトはタクソノミー (`/work_category/custody/` 等) と
  固定ページ (`/jyouto/`, `/work/custody-lostanimal/`) で混在しており、
  実データ (詳細記事) は `/news/<slug>/` 形式の WordPress 投稿として
  公開される運用になっている。一覧ページのテンプレートには
  `#treatment_list .post_list .item a` でサブセクション (＝親カテゴリ
  ページ等) のカードが並ぶことがあり、これらも『一覧 → 詳細』の
  入口として WordPressListAdapter にそのまま乗せる。
- 詳細ページ (実データ側) は WordPress 投稿 `/news/<slug>/` で、
  `<dl><dt>項目名</dt><dd>値</dd></dl>` または
  `<table><th>項目名</th><td>値</td></table>` の典型構造で
  各フィールドを表現するため、`WordPressListAdapter._extract_by_label`
  がそのまま機能する。
- 動物写真は `/wp/wp-content/uploads/...` 配下に置かれるため、
  基底の `_filter_image_urls` (uploads 配下のみ採用) がそのまま機能する。
"""

from __future__ import annotations

from typing import ClassVar

from ..registry import SiteAdapterRegistry
from ..wordpress_list import FieldSpec, WordPressListAdapter


class DouaiPrefTochigiAdapter(WordPressListAdapter):
    """栃木県動物愛護指導センター 共通アダプター

    保護動物 / 譲渡動物 / 迷子動物 の 3 サイトで共通テンプレートを
    使用するため、サイト名ごとにクラスを分けず registry に複数の
    site_name を 1 クラスで束ねる。
    """

    # 一覧ページの detail link 候補:
    # - `/news/<slug>/`     : 個別記事 (主要な動物データの公開先)
    # - `#treatment_list .post_list .item a` :
    #     カテゴリ親ページ等のカード (`/work/...` 系)。
    #     `/news/` 投稿が無い期間でも一覧ページとして空にならない。
    # 同じ URL は WordPressListAdapter 側の seen 集合で重複除去される。
    LIST_LINK_SELECTOR: ClassVar[str] = "a[href*='/news/'], #treatment_list .post_list .item a"

    # detail ページの定義リスト/テーブル見出しに対応するラベル。
    # 同種のラベルが複数候補ある場合は、`_extract_by_label` で
    # 最初にヒットしたものが採用される (本サイトでは 1 種のみ)。
    FIELD_SELECTORS: ClassVar[dict[str, FieldSpec]] = {
        # 種類 / 品種 (例: "雑種", "柴犬")
        "species": FieldSpec(label="種類"),
        # 性別 (例: "オス", "メス")
        "sex": FieldSpec(label="性別"),
        # 年齢 (例: "成犬", "推定2歳")
        "age": FieldSpec(label="年齢"),
        # 毛色
        "color": FieldSpec(label="毛色"),
        # 体格 / 大きさ
        "size": FieldSpec(label="大きさ"),
        # 収容日
        "shelter_date": FieldSpec(label="収容日"),
        # 収容場所 (保健所名等)
        "location": FieldSpec(label="収容場所"),
        # 連絡先 (電話番号)
        "phone": FieldSpec(label="連絡先"),
    }

    # 動物写真は `/wp/wp-content/uploads/YYYY/MM/...` 配下に置かれる。
    # ヘッダ等のロゴ画像 (`/wp-content/themes/serum_tcd096/...`) は
    # 基底 `_filter_image_urls` の uploads フィルタで自動排除される。
    IMAGE_SELECTOR: ClassVar[str] = "img"


# ─────────────────── サイト登録 ───────────────────
# 同一テンプレート上で運用される 3 サイトを同一 adapter にマップする。
_SITE_NAMES = (
    "栃木県動物愛護指導センター（保護動物）",
    "栃木県動物愛護指導センター（譲渡動物）",
    "栃木県動物愛護指導センター（迷子動物）",
)

for _name in _SITE_NAMES:
    SiteAdapterRegistry.register(_name, DouaiPrefTochigiAdapter)
