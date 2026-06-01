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

from bs4 import BeautifulSoup

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

    # detail ページのテーブル見出しに対応するラベル。
    # `<table><tr><th>項目名</th><td>値</td></tr>` 形式で、`_extract_by_label`
    # が th も対応する。同じセマンティクスの label 候補が複数ある場合は
    # 最初にヒットしたものが採用される。
    FIELD_SELECTORS: ClassVar[dict[str, FieldSpec]] = {
        # 種類/品種 (実 HTML には項目なし。URL から _postprocess_fields で補完)
        "species": FieldSpec(label="品種"),
        # 性別 (例: "オス", "メス", "不明")
        "sex": FieldSpec(label="性別"),
        # 年齢 ("推定年齢（推定生年月日）" にもラベル部分一致でマッチ)
        "age": FieldSpec(label="年齢"),
        # 毛色
        "color": FieldSpec(label="毛色"),
        # 大きさ (体格)
        "size": FieldSpec(label="大きさ"),
        # 保護した日 (=収容日相当)
        "shelter_date": FieldSpec(label="保護した日"),
        # 保護した場所 (=収容先相当)
        "location": FieldSpec(label="保護した場所"),
        # 連絡先 (実 HTML に該当 th なし。_postprocess_fields で別 selector を試す)
        "phone": FieldSpec(label="連絡先"),
    }

    # 動物写真は `/files/download/<Bucket>/<uuid>/image_XX/...` 配下に配置される。
    # 2026-05/06 観測: 詳細ページのカテゴリで bucket 名が違う。
    #   - `protection-detail` (保健所収容)   → `/files/download/Animals/`
    #   - `hogo-detail`       (一般保護)     → `/files/download/PersonalAnimals/`
    #   - `center-detail`     (センター譲渡) → `/files/download/AnimalCompletes/`
    #   - `group-detail`      (団体譲渡)     → `/files/download/AnimalCompletes/`
    # 旧 selector は `Animals` だけしか拾えず、`personal-animals/hogo-detail/...`
    # と `animals/{center,group}-detail/...` の 33/36 件で image_urls が空欠損。
    # 3 系統すべてを拾うため、CSS attribute selector を 3 つ列挙する。
    # 装飾画像 (`/img/common/...`) は src パスから外れるため自動除外。
    # スライダ構造はメイン画像とサムネで同一 src が複数回出るため、
    # adapter 側で順序保持の重複排除を行う (`<figure>` も将来対応のため残す)。
    IMAGE_SELECTOR: ClassVar[str] = (
        "figure img,"
        " img[src*='/files/download/Animals/'],"
        " img[src*='/files/download/PersonalAnimals/'],"
        " img[src*='/files/download/AnimalCompletes/']"
    )

    # 動物写真として採用するパス prefix の集合。`_filter_image_urls` で参照。
    _ANIMAL_IMAGE_PATH_PREFIXES: ClassVar[tuple[str, ...]] = (
        "/files/download/Animals/",
        "/files/download/PersonalAnimals/",
        "/files/download/AnimalCompletes/",
    )

    # 譲渡カテゴリの詳細ページ (`/animals/center-detail/`, `/animals/group-detail/`)
    # は「保護した場所」欄を持たないため、location が空になったまま snapshot に
    # 出ると「不明」表示になる。譲渡対象動物は施設で会うことになるので、
    # 施設名 (= 福岡県動物愛護センター) を location に代入する。
    _CENTER_FACILITY_NAME: ClassVar[str] = "福岡県動物愛護センター"

    def _filter_image_urls(self, urls: list[str], base_url: str) -> list[str]:
        """動物画像 bucket 配下のみを採用し順序保持で重複排除する

        IMAGE_SELECTOR で attribute selector を使って既に動物画像のみを
        拾っているが、スライダ構造でメイン画像とサムネが同一 src を 2 回
        以上返すため、ここで dedupe する。`<figure img>` フォールバックも
        引き続き同じ重複排除を通す。

        bucket は カテゴリにより `Animals` / `PersonalAnimals` / `AnimalCompletes`
        の 3 種があるため、いずれかの prefix を含むもののみ残す。
        """
        cleaned: list[str] = []
        seen: set[str] = set()
        for u in urls:
            if not any(prefix in u for prefix in self._ANIMAL_IMAGE_PATH_PREFIXES):
                continue
            if u in seen:
                continue
            seen.add(u)
            cleaned.append(u)
        return cleaned

    def _postprocess_fields(
        self, fields: dict[str, str], detail_url: str, soup: BeautifulSoup
    ) -> None:
        """detail HTML に「品種」「連絡先」 列が無いため、URL とフォールバックで補う。

        - species: list_url の `/dog` `/cat` から推測
        - phone: 動物情報 table の外にある問い合わせ先 box から拾えれば拾う
        - location: 譲渡カテゴリ (`center-detail` / `group-detail`) では
          「保護した場所」欄が無いため施設名をフォールバックとして代入する
        """
        species = fields.get("species", "")
        if not any(kw in species for kw in ("犬", "猫", "いぬ", "ねこ", "イヌ", "ネコ")):
            hint = self._infer_species_from_url()
            if hint:
                fields["species"] = hint
        if not fields.get("phone"):
            # ページ末尾の「お問い合わせ」block に電話番号がある場合、最初の TEL: パターンを採用
            import re

            text = soup.get_text(" ", strip=True)
            m = re.search(r"(\d{2,4}-\d{2,4}-\d{3,4})", text)
            if m:
                fields["phone"] = m.group(1)
        if not fields.get("location") and (
            "/center-detail/" in detail_url or "/group-detail/" in detail_url
        ):
            fields["location"] = self._CENTER_FACILITY_NAME


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
