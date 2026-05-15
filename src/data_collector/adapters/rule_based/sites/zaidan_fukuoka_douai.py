"""福岡県動物愛護センター (公益財団法人福岡県動物愛護協会) rule-based adapter

対象ドメイン: https://www.zaidan-fukuoka-douai.or.jp/

特徴:
- 同一ドメイン上で 8 サイト (保健所収容/一般保護/センター譲渡/団体譲渡 × 犬/猫)
  が共通テンプレートを使用しているため 1 つの adapter で全サイトを賄う。
- 一覧ページ (`/animals/protections/{dog,cat}`,
  `/personal-animals/hogo/{dog,cat}`, `/animals/centers/{dog,cat}`,
  `/animals/groups/{dog,cat}`) では
  `<div class="thumb-list ... animals-list"><ul><li><a href="..."></a></li></ul></div>`
  形式で詳細ページへのリンクを並べる。
- 詳細ページの URL は `/animals/protection-detail/{uuid}` 等の
  「-detail/{uuid}」を末尾に持つパスで、4 系統 (protection / personal-hogo /
  center / group) で接頭辞のみ異なる。`animals-list` 配下の `<a>` のみを
  対象にすることで、ヘッダ/フッタ側のカテゴリ遷移リンクを排除する。
- 詳細ページは `<dl><dt>項目名</dt><dd>値</dd></dl>` の定義リストで
  各フィールドを表現する。`WordPressListAdapter._extract_by_label` が
  そのまま乗る構造。
"""

from __future__ import annotations

from typing import ClassVar

from ..registry import SiteAdapterRegistry
from ..wordpress_list import FieldSpec, WordPressListAdapter


class ZaidanFukuokaDouaiAdapter(WordPressListAdapter):
    """福岡県動物愛護協会 共通アダプター

    list / detail テンプレートが 8 サイト共通なので、サイト名ごとに
    クラスを分けず、registry に複数の site_name を 1 クラスで束ねる。
    """

    # `animals-list` (一覧ブロック) 配下の `<a>` のみを対象にする。
    # これによりヘッダ/フッタの `/animals/protections/dog` のような
    # カテゴリ遷移リンクや、ページ下部の「他カテゴリへ」ボタン
    # (`.transfer-menu` 内) を確実に排除できる。
    LIST_LINK_SELECTOR: ClassVar[str] = "div.animals-list a[href*='-detail/']"

    # detail ページの定義リスト見出しに対応するラベル。
    # 一覧時の inline data (個体管理ナンバー / 収容日 / 保護した場所 / 収容先)
    # 相当のフィールドに加え、詳細ページにある品種・性別・毛色・特徴等を
    # ラベル一致で拾う。同じセマンティクスの label 候補が複数ある場合は
    # `_extract_by_label` の最初にヒットしたものが採用される。
    FIELD_SELECTORS: ClassVar[dict[str, FieldSpec]] = {
        # 種類/品種 (例: "雑種", "ミックス")
        "species": FieldSpec(label="品種"),
        # 性別 (例: "オス", "メス", "不明")
        "sex": FieldSpec(label="性別"),
        # 年齢 (推定年齢として記載されることが多い)
        "age": FieldSpec(label="年齢"),
        # 毛色
        "color": FieldSpec(label="毛色"),
        # 大きさ (体格)
        "size": FieldSpec(label="大きさ"),
        # 収容日
        "shelter_date": FieldSpec(label="収容日"),
        # 収容先 (保健福祉環境事務所など)
        "location": FieldSpec(label="収容先"),
        # 連絡先 (電話番号)
        "phone": FieldSpec(label="連絡先"),
    }

    # 動物写真は `/files/download/Animals/<uuid>/image_XX/...` 配下に配置される。
    # 親 WordPressListAdapter._filter_image_urls は `/wp-content/uploads/` を
    # 期待するが、本サイトでは該当パスが存在しないためフェイルセーフで
    # 元リストがそのまま返る挙動に依存する。装飾画像 (アイコン等) を排除
    # するため、`<figure class="list-pht">` や本文 `figure` 配下の `img` のみを
    # 拾うセレクタにしぼる。
    IMAGE_SELECTOR: ClassVar[str] = "figure img"


# ─────────────────── サイト登録 ───────────────────
# 同一テンプレート上で運用される 8 サイトを同一 adapter にマップする。
_SITE_NAMES = (
    "福岡県動物愛護協会（保健所収容犬）",
    "福岡県動物愛護協会（保健所収容猫）",
    "福岡県動物愛護協会（一般保護犬）",
    "福岡県動物愛護協会（一般保護猫）",
    "福岡県動物愛護協会（センター譲渡犬）",
    "福岡県動物愛護協会（センター譲渡猫）",
    "福岡県動物愛護協会（団体譲渡犬）",
    "福岡県動物愛護協会（団体譲渡猫）",
)

for _name in _SITE_NAMES:
    SiteAdapterRegistry.register(_name, ZaidanFukuokaDouaiAdapter)
