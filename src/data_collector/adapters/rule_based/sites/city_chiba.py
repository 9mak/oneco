"""千葉市動物保護指導センター rule-based adapter

対象ドメイン: https://www.city.chiba.jp/hokenfukushi/iryoeisei/seikatsueisei/dobutsuhogo/

特徴:
- 同一テンプレート上で 6 サイト (迷子: 犬/猫/その他、市民保護: 犬/猫/その他)
  を運用しており、URL パターンのみが異なる:
    - .../dobutsuhogo/lost_dog.html             (迷子犬)
    - .../dobutsuhogo/lost_cat.html             (迷子猫)
    - .../dobutsuhogo/lost_another_animal.html  (迷子その他動物)
    - .../dobutsuhogo/hogo_dog.html             (市民保護犬)
    - .../dobutsuhogo/hogo_cat.html             (市民保護猫)
    - .../dobutsuhogo/lost_others.html          (市民保護その他)
- 1 ページに複数動物がブロック形式で並ぶ single_page サイト。個別 detail
  ページは存在しないため一覧ページから直接抽出する。
- 各動物は `#contents_editable` 内で次のような並びで表現される:
    <h4>{管理番号}</h4>
    <p><img alt="..." src="..."></p>
    <p>収容日：令和8年5月7日<br>
       告示（掲載）期限：令和8年5月12日<br>
       収容場所：稲毛区小仲台<br>
       種類：柴犬<br>
       毛色：茶<br>
       性別：メス<br>
       体格：中<br>
       特徴：</p>
- ROW_SELECTOR には `<h4>` を採用し、各 `<h4>` の後に続く同一階層の
  `<p>` 群 (画像段落 + 属性段落) を 1 件の動物カードとして扱う。
- テーブル形式ではないので基底 `SinglePageTableAdapter` の `td/th` ベース
  既定実装は使えず、`extract_animal_details` をオーバーライドする。
- 画像は属性 `<p>` の直前にある `<p><img></p>` から抽出する。
"""

from __future__ import annotations

from typing import ClassVar

from bs4 import Tag

from ....domain.models import RawAnimalData
from ...municipality_adapter import ParsingError
from ..registry import SiteAdapterRegistry
from ..single_page_table import SinglePageTableAdapter


class CityChibaAdapter(SinglePageTableAdapter):
    """千葉市動物保護指導センター用 rule-based adapter

    迷子 (lost_*) / 市民保護 (hogo_*, lost_others) × 犬/猫/その他 の
    6 サイトで共通テンプレートを使用する。
    各動物は `#contents_editable` 内の `<h4>` を起点としたブロックで表現される
    single_page 形式。
    """

    # 各動物の起点となる `<h4>` (管理番号)。`#contents_editable` 配下に限定して、
    # サイドナビ等の他の `<h4>` を拾わないようにする。
    ROW_SELECTOR: ClassVar[str] = "div#contents_editable h4"
    SKIP_FIRST_ROW: ClassVar[bool] = False
    # 属性 `<p>` 内のラベル → RawAnimalData フィールド名 マッピング。
    # 基底の cells ベース既定実装は使わないが、契約として明示する。
    COLUMN_FIELDS: ClassVar[dict[int, str]] = {
        0: "shelter_date",  # 収容日
        1: "location",  # 収容場所
        2: "species",  # 種類
        3: "color",  # 毛色
        4: "sex",  # 性別
        5: "size",  # 体格
    }
    LOCATION_COLUMN: ClassVar[int | None] = 1
    SHELTER_DATE_DEFAULT: ClassVar[str] = ""

    # 属性ブロック (`<p>収容日：...<br>...`) 内のラベル → フィールド名
    _LABEL_TO_FIELD: ClassVar[dict[str, str]] = {
        "収容日": "shelter_date",
        "収容場所": "location",
        "種類": "species",
        "毛色": "color",
        "性別": "sex",
        "体格": "size",
        "特徴": "features",
    }

    # ─────────────────── オーバーライド ───────────────────

    def extract_animal_details(self, virtual_url: str, category: str = "adoption") -> RawAnimalData:
        """`<h4>` を起点とした動物ブロックから RawAnimalData を構築する

        基底の `td/th` ベース実装ではなく、`<h4>` の次に続く同階層の
        `<p>` 群から「画像 `<p>`」と「`ラベル：値<br>` の並びの属性 `<p>`」を
        順次取得する。
        """
        rows = self._load_rows()
        idx = self._parse_row_index(virtual_url)
        if idx >= len(rows):
            raise ParsingError(
                f"row index {idx} out of range (total {len(rows)})",
                url=virtual_url,
            )
        h4 = rows[idx]

        # 同一階層で `<h4>` の後ろに続く `<p>` を、次の `<h4>`/`<h2>`/`<hr>`/`<ul>`
        # に到達するまで集める。Chiba のテンプレートでは各動物ブロックの末尾は
        # 次の動物の `<h4>`、または共通の `<p><span class="txt_big">...` リンクや
        # `<h2>このページのご利用について</h2>` 等で区切られる。
        siblings: list[Tag] = []
        for sib in h4.find_next_siblings():
            if not isinstance(sib, Tag):
                continue
            name = sib.name
            if name in ("h1", "h2", "h3", "h4", "hr", "ul"):
                break
            if name == "p":
                # 案内リンク (<p><span class="txt_big"><a>...</a></span></p>) は除外
                if sib.find("span", class_="txt_big") is not None:
                    break
                siblings.append(sib)

        # 画像 `<p>` と属性 `<p>` を分離する
        image_paragraphs = [p for p in siblings if p.find("img") is not None]
        attr_paragraphs = [p for p in siblings if p.find("img") is None]

        fields: dict[str, str] = {}
        for p in attr_paragraphs:
            # `<br>` を改行として取り出し、行ごとに「ラベル：値」をパース
            text = p.get_text(separator="\n", strip=False)
            for line in text.split("\n"):
                line = line.strip()
                if not line:
                    continue
                # 全角コロン「：」または半角「:」の最初の出現で 2 分割
                for sep in ("：", ":"):
                    if sep in line:
                        label, value = line.split(sep, 1)
                        label = label.strip()
                        value = value.strip()
                        field = self._LABEL_TO_FIELD.get(label)
                        if field and value and field not in fields:
                            fields[field] = value
                        break

        # 画像 URL を集める
        image_urls: list[str] = []
        for p in image_paragraphs:
            for img in p.find_all("img"):
                src = img.get("src")
                if src and isinstance(src, str):
                    image_urls.append(self._absolute_url(src, base=virtual_url))
        image_urls = self._filter_image_urls(image_urls, virtual_url)

        # 動物種別: HTML の「種類」(柴犬/雑種等) は具体名のためサイト名から推定する
        species = self._infer_species_from_site_name(self.site_config.name)

        try:
            return RawAnimalData(
                species=species,
                sex=fields.get("sex", ""),
                age="",
                color=fields.get("color", ""),
                size=fields.get("size", ""),
                shelter_date=fields.get("shelter_date", self.SHELTER_DATE_DEFAULT),
                location=fields.get("location", ""),
                phone="",
                image_urls=image_urls,
                source_url=virtual_url,
                category=category,
            )
        except Exception as e:
            raise ParsingError(f"RawAnimalData バリデーション失敗: {e}", url=virtual_url) from e

    # ─────────────────── ヘルパー ───────────────────

    @staticmethod
    def _infer_species_from_site_name(name: str) -> str:
        """サイト名から動物種別 (犬/猫/その他) を推定する"""
        if "犬" in name:
            return "犬"
        if "猫" in name:
            return "猫"
        return "その他"


# ─────────────────── サイト登録 ───────────────────
# 同一テンプレート上で運用される 6 サイトを同一 adapter にマップする。
for _site_name in (
    "千葉市（迷子犬）",
    "千葉市（迷子猫）",
    "千葉市（迷子その他動物）",
    "千葉市（市民保護犬）",
    "千葉市（市民保護猫）",
    "千葉市（市民保護その他）",
):
    SiteAdapterRegistry.register(_site_name, CityChibaAdapter)
