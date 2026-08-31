"""栃木県動物愛護指導センター「迷子動物収容情報」 rule-based adapter

対象ドメイン: https://douai.sakura.ne.jp/wp/maigo/html/stray/

背景 (T121 調査, 2026-08-31):
- 本体サイト (douai.pref.tochigi.lg.jp) の旧登録 URL
  (`/work/custody-lostanimal/`) はテーマ改修で案内リンク集ページ化しており、
  実データを一切含まない。ページ内で唯一実質的な導線は
  「迷子のペットを探している方へ」リンクで、その先は全く別ドメインの
  静的サイト `douai.sakura.ne.jp`（自治体が別途運用しているレガシー
  システムと見られる）に置かれた「迷子動物収容情報」ページである。
- このドメインは WordPress ではなく素朴な静的 HTML だが、一覧
  (`stray/{dog,cat}/list.html`) + 詳細 (`<管理番号>.html`) という
  典型的な list+detail 構造で、詳細ページは `<table><th>項目名</th>
  <td>値</td></table>` 形式のため、`WordPressListAdapter` の
  `_extract_by_label` (th/td 対応) をそのまま流用できる。
- 一覧ページの本文中の `<a href="....html">` は個体詳細へのリンクのみ
  (グローバルナビ等の装飾が無い素の HTML) のため、
  `a[href$='.html']` で十分に絞り込める。
- 詳細ページには「動物種別」(犬/猫) と「種類」(雑種/柴犬等の品種) が
  別項目として存在する。本体サイトの旧 WordPress adapter
  (`douai_pref_tochigi.py`) では "種類" を species として扱っていたが
  (旧 detail ページには動物種別が無かったため)、このサイトでは
  正しく species=動物種別 / breed=種類 に分離する。
- 画像は `../../image/<ファイル名>.JPG` のような相対パスで、
  `/wp-content/uploads/` を前提とする基底の `_filter_image_urls` は
  一致せずフェイルセーフで無フィルタになる。写真未登録の個体は
  `../../image/` (ファイル名無し) のダミー `<img>` を持つため、
  末尾が `/` で終わる URL を明示的に除外する。
"""

from __future__ import annotations

from typing import ClassVar

from ..registry import SiteAdapterRegistry
from ..wordpress_list import FieldSpec, WordPressListAdapter


class DouaiPrefTochigiStrayAdapter(WordPressListAdapter):
    """栃木県動物愛護指導センター「迷子動物収容情報」(douai.sakura.ne.jp) 用アダプター

    犬 / 猫の 2 サイトで共通テンプレートを使用するため、1 クラスで束ねる。
    """

    # 一覧ページ内の `<a href="....html">` は個体詳細リンクのみ。
    LIST_LINK_SELECTOR: ClassVar[str] = "a[href$='.html']"

    FIELD_SELECTORS: ClassVar[dict[str, FieldSpec]] = {
        "management_number": FieldSpec(label="管理番号"),
        "shelter_date": FieldSpec(label="収容日"),
        "location": FieldSpec(label="収容場所"),
        # 「動物種別」(犬/猫) が本当の species。「種類」(雑種/柴犬等) は breed。
        "species": FieldSpec(label="動物種別"),
        "breed": FieldSpec(label="種類"),
        "sex": FieldSpec(label="性別"),
        "age": FieldSpec(label="年齢"),
        "color": FieldSpec(label="毛色"),
        "size": FieldSpec(label="大きさ"),
    }

    IMAGE_SELECTOR: ClassVar[str] = "#gazou img"

    def _filter_image_urls(self, urls: list[str], base_url: str) -> list[str]:
        """写真未登録の `../../image/` (ファイル名無し) ダミー画像を除外する

        基底実装は `/wp-content/uploads/` 前提のため本サイトでは無効化され、
        無フィルタで返ってしまう。ここではファイル名を持つ URL のみ残す。
        """
        return [u for u in urls if u and not u.endswith("/")]


# ─────────────────── サイト登録 ───────────────────
_SITE_NAMES = (
    "栃木県動物愛護指導センター（迷子動物・犬）",
    "栃木県動物愛護指導センター（迷子動物・猫）",
)

for _name in _SITE_NAMES:
    SiteAdapterRegistry.register(_name, DouaiPrefTochigiStrayAdapter)
