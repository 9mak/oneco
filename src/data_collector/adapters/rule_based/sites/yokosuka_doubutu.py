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
        # 種類（例: "豆柴", "雑種"）
        "species": FieldSpec(label="種類"),
        # 性別（例: "メス", "オス"）
        "sex": FieldSpec(label="性別"),
        # 年齢: 詳細ページに専用フィールドが無い
        "age": FieldSpec(label="年齢"),
        # 特徴（毛色を含むことが多い。例: "黒白"）
        "color": FieldSpec(label="特徴"),
        # 大きさ: 専用フィールドが無いことが多い
        "size": FieldSpec(label="大きさ"),
        # 収容日（例: "R8.5.14（木曜日）"）
        "shelter_date": FieldSpec(label="収容日"),
        # 収容場所（例: "池田町"）
        "location": FieldSpec(label="収容場所"),
        # 電話番号: 本文には無くフッタからの抽出
        "phone": FieldSpec(selector="#footer-text-2"),
    }

    # 動物写真は `#photos` ブロック配下に集約されている
    IMAGE_SELECTOR: ClassVar[str] = "div#photos img"

    # ─────────────────── 拡張 ───────────────────

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
