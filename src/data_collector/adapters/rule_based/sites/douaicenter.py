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

from bs4 import BeautifulSoup

from ..registry import SiteAdapterRegistry
from ..wordpress_list import FieldSpec, WordPressListAdapter


class DouaicenterAdapter(WordPressListAdapter):
    """旭川市あにまある 共通アダプター

    list / detail 両方のテンプレートが 8 サイト共通なので、サイト名ごとに
    クラスを分けず、registry に複数の site_name を 1 クラスで束ねる。

    detail テンプレートは 2 系統あり、それぞれラベルが異なる:
    - `/animal/{id}` (センター収容/譲渡): 「保護日」「保護場所」「種類」「性別」…
    - `/other-animal/{id}` (市民保護): 「不明日」「不明場所」「連絡先」…
    そのため FieldSpec の label を複数候補 tuple にして両方を吸収する。

    phone について:
    - `/animal/` 配下のテンプレートには「連絡先」フィールド自体が無く、
      実運用上はすべて旭川市動物愛護センター宛 (0166-25-5271) で問い合わせる。
    - `/other-animal/` (市民保護) には個別連絡先が入る場合があるが、
      省略されている個体も多い。
    どちらも phone が空のときは代表電話をフォールバックとして注入する。
    """

    # 旭川市動物愛護センター あにまある 代表電話
    # サイト全ページのヘッダ/フッタに `<a href="tel:0166255271">` で固定埋め込み。
    _CENTER_PHONE = "0166-25-5271"

    # /animal/{id} と /other-animal/{id} の両方の detail を抽出。
    # animal-list-img-box 内のリンクのみ対象にすることで、ヘッダ/メニュー側の
    # `/animal/list/...` のような一覧ページ自体へのリンクを排除する。
    LIST_LINK_SELECTOR = (
        ".animal-list-img-box a[href*='/animal/'], .animal-list-img-box a[href*='/other-animal/']"
    )

    # detail ページの定義リスト/テーブル見出しに対応するラベル
    FIELD_SELECTORS = {
        "species": FieldSpec(label="種類"),
        "sex": FieldSpec(label="性別"),
        "age": FieldSpec(label="年齢"),
        "color": FieldSpec(label="毛色"),
        "size": FieldSpec(label="体格"),
        "shelter_date": FieldSpec(label=("保護日", "不明日", "収容日")),
        "location": FieldSpec(label=("保護場所", "不明場所", "収容場所")),
        "phone": FieldSpec(label="連絡先"),
    }

    # detail ページ本体の動物写真は WordPress uploads 配下に配置される。
    # サイドバー/ヘッダの装飾画像は `_filter_image_urls` の uploads フィルタで除外される。
    IMAGE_SELECTOR = "img"

    def _postprocess_fields(
        self, fields: dict[str, str], detail_url: str, soup: BeautifulSoup
    ) -> None:
        """species と phone の不足分を補完する。

        - species: 「雑種」等で犬猫判定できない場合、list_url で補正する。
        - phone: 「連絡先」フィールドが無いか空の場合、旭川市動物愛護センター
          代表電話を注入する。`/animal/` 配下は「連絡先」フィールド自体が
          存在しないため必ず注入され、`/other-animal/` 配下は個別連絡先が
          優先され、無い場合のみ注入される。
        """
        species = fields.get("species", "")
        # 「犬」「猫」が明示されていればそのまま、それ以外は URL hint で上書き
        if not any(kw in species for kw in ("犬", "猫", "いぬ", "ねこ", "イヌ", "ネコ")):
            hint = self._infer_species_from_url()
            if hint:
                fields["species"] = hint

        # phone フォールバック: 空 (またはキー未設定) のとき代表電話を入れる
        if not fields.get("phone"):
            fields["phone"] = self._CENTER_PHONE


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
