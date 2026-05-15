"""宮崎市保護動物サイト rule-based adapter

対象ドメイン: https://www.city.miyazaki.miyazaki.jp/life/pet/protection/

特徴:
- 同一テンプレート上で 4 サイトを運用しており、URL の記事 ID のみが異なる:
    - 411118.html (直近保護犬)
    - 411116.html (直近保護猫)
    - 109676.html (センター保護犬・飼い主募集)
    - 339718.html (センター保護猫・飼い主募集)
- 1 ページにつき動物 1 頭の "single_page" 形式 (一覧ページが存在しないため、
  detail URL 自体を 1 行のテーブルと見立てる)。
- 本文は `<article class="body">` 配下に `<h3>{ラベル}</h3><p>{値}</p>` の
  繰り返しで表現される。`<th>/<td>` ベースの基底既定実装ではなく、
  `extract_animal_details` をオーバーライドして h3-p ペアから抽出する。
- 動物種別 (犬/猫) はページ本文の "犬の種類" / "猫の種類" 見出しから判定する
  (見つからない場合は <title> や h1 の【犬・…】/【猫・…】表記から推定)。
- 電話番号は `<footer class="contact">` 内の `<dl class="tel">` から取得する。
- 画像は `<article class="body">` 配下の `<img>` を絶対 URL に変換して返す。
"""

from __future__ import annotations

from typing import ClassVar

from bs4 import BeautifulSoup, Tag

from ....domain.models import RawAnimalData
from ...municipality_adapter import ParsingError
from ..registry import SiteAdapterRegistry
from ..single_page_table import SinglePageTableAdapter


class CityMiyazakiAdapter(SinglePageTableAdapter):
    """宮崎市 (city.miyazaki.miyazaki.jp) 用 rule-based adapter

    1 ページ 1 頭の detail ページを 1 行のテーブルと見立て、
    `<article class="body">` 配下の h3-p ペアから RawAnimalData を構築する。
    """

    # ページ本文。動物 1 頭分が 1 行に対応する想定。
    ROW_SELECTOR: ClassVar[str] = "article.body"
    SKIP_FIRST_ROW: ClassVar[bool] = False
    # h3 ラベル → RawAnimalData フィールド名。基底の cells ベース実装は
    # 使わないが、契約として明示的に宣言する。
    COLUMN_FIELDS: ClassVar[dict[int, str]] = {}
    # 収容日表記が無い場合のデフォルト (空文字 = 不明)
    SHELTER_DATE_DEFAULT: ClassVar[str] = ""

    # h3 のテキスト (前後空白除去後) と RawAnimalData のフィールド名の対応
    _LABEL_TO_FIELD: ClassVar[dict[str, str]] = {
        "保護場所": "location",
        "毛色": "color",
        "性別": "sex",
        "推定年齢": "age",
        "体格": "size",
        "保護日時": "shelter_date",
    }

    # ─────────────────── オーバーライド ───────────────────

    def extract_animal_details(
        self, virtual_url: str, category: str = "adoption"
    ) -> RawAnimalData:
        """`<article class="body">` から RawAnimalData を構築する

        基底の `td/th` ベース実装ではなく、`<h3>{ラベル}</h3><p>{値}</p>` の
        並びを `_LABEL_TO_FIELD` のマッピングに従って取り出す。
        """
        rows = self._load_rows()
        idx = self._parse_row_index(virtual_url)
        if idx >= len(rows):
            raise ParsingError(
                f"row index {idx} out of range (total {len(rows)})",
                url=virtual_url,
            )
        article = rows[idx]

        # h3-p ペアを抽出。h3 直後の同階層 <p> を値として採用する。
        # 一部のラベル (保護場所など) では <p> が複数続くことがあるため、
        # 次の h3 までに現れた最初の非空 <p> のテキストを使う。
        fields: dict[str, str] = {}
        species = ""
        for h3 in article.find_all("h3"):
            label = h3.get_text(strip=True)
            value = self._collect_value_after(h3)
            if not value:
                continue
            if label in ("犬の種類", "猫の種類"):
                # 種別はページ本文の見出しから直接判定
                species = "犬" if label.startswith("犬") else "猫"
                # 種類詳細 (柴系雑種など) は現状 RawAnimalData に対応フィールドが
                # ないため species 推定にのみ利用する。
                continue
            field = self._LABEL_TO_FIELD.get(label)
            if field:
                fields[field] = value

        # ページ見出しからのフォールバック (本文に種類見出しが無いケース)
        if not species:
            species = self._infer_species_from_title(article)

        # 電話番号は本文外 (footer) にあるためページ全体から探す
        phone = self._extract_phone_from_page(article)

        try:
            return RawAnimalData(
                species=species,
                sex=fields.get("sex", ""),
                age=fields.get("age", ""),
                color=fields.get("color", ""),
                size=fields.get("size", ""),
                shelter_date=fields.get(
                    "shelter_date", self.SHELTER_DATE_DEFAULT
                ),
                location=fields.get("location", ""),
                phone=phone,
                image_urls=self._extract_row_images(article, virtual_url),
                source_url=virtual_url,
                category=category,
            )
        except Exception as e:
            raise ParsingError(
                f"RawAnimalData バリデーション失敗: {e}", url=virtual_url
            ) from e

    # ─────────────────── 画像 URL フィルタ ───────────────────

    def _filter_image_urls(self, urls: list[str], base_url: str) -> list[str]:
        """宮崎市 CMS 上の動物画像のみを残す

        `/fs/` 配下にアップロードされたファイルが本文画像であり、
        `/img/` `/assets/` 配下のロゴ・装飾類は除外したい。
        フィルタ後 0 件になる場合は元リストを返す (フェイルセーフ)。
        """
        filtered = [u for u in urls if "/fs/" in u]
        return filtered if filtered else urls

    # ─────────────────── ヘルパー ───────────────────

    @staticmethod
    def _collect_value_after(h3: Tag) -> str:
        """`<h3>` の次の兄弟要素を順に走査し、最初の非空 `<p>` テキストを返す

        次の `<h3>` (または別ブロック見出し) に到達したら打ち切る。
        """
        for sibling in h3.next_siblings:
            if not isinstance(sibling, Tag):
                continue
            name = sibling.name or ""
            if name in ("h2", "h3", "h4"):
                break
            if name == "p":
                text = sibling.get_text(separator=" ", strip=True)
                # NBSP のみのプレースホルダは無視
                if text and text.replace("\xa0", "").strip():
                    return text
        return ""

    def _infer_species_from_title(self, article: Tag) -> str:
        """ページ見出し (h1) から種別を推定する

        宮崎市の記事タイトルは "令和8年5月6日保護分【犬・柴系】" のように
        【犬・…】【猫・…】を含む。article 内に h1 が無ければ
        ドキュメント全体を遡って探す。
        """
        # まず article 自身、続いて親ドキュメントから h1/title を探索
        h1: Tag | None = None
        if article and article.find("h1"):
            h1 = article.find("h1")
        else:
            doc = article.find_parent() if article else None
            while doc is not None and h1 is None:
                h1 = doc.find("h1")
                doc = doc.find_parent()
        if h1 is not None:
            text = h1.get_text(strip=True)
            if "犬" in text:
                return "犬"
            if "猫" in text:
                return "猫"

        # サイト名からのフォールバック
        name = self.site_config.name or ""
        if "犬" in name:
            return "犬"
        if "猫" in name:
            return "猫"
        return "その他"

    def _extract_phone_from_page(self, article: Tag) -> str:
        """ページ全体の `<dl class="tel">` から電話番号を取得する

        article 内には掲載されないため、document 全体を遡って探す。
        """
        # 親をたどってドキュメントルートを取得
        doc: Tag | None = article
        parent = article.find_parent()
        while parent is not None:
            doc = parent
            parent = parent.find_parent()
        if doc is None:
            return ""
        candidate = ""
        tel_dl = doc.select_one("dl.tel")
        if tel_dl is not None:
            candidate = tel_dl.get_text(separator=" ", strip=True)
        return self._normalize_phone(candidate)

    # 基底の _load_rows は html.parser 既定でも問題ないが、
    # 行が 0 件のときの ParsingError メッセージ整備のためここでは触らない。

    # 画像抽出は基底 _extract_row_images をそのまま利用 (article 内 img 全件 →
    # _filter_image_urls で /fs/ 配下のみ残す)。
    # `_load_rows` の BeautifulSoup parser 引数:
    #   基底既定の "html.parser" で本サイトの構造は問題なく解析できる。

    # ─────────────────── parser 上書き不要のため省略 ───────────────────


# ─────────────────── サイト登録 ───────────────────
# 同一テンプレート上で運用される 4 サイトを同一 adapter にマップする。
_SITE_NAMES = (
    "宮崎市（直近保護犬）",
    "宮崎市（直近保護猫）",
    "宮崎市（センター保護犬・飼い主募集）",
    "宮崎市（センター保護猫・飼い主募集）",
)
for _name in _SITE_NAMES:
    SiteAdapterRegistry.register(_name, CityMiyazakiAdapter)
