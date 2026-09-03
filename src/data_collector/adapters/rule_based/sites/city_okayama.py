"""岡山市保護動物情報サイト rule-based adapter

対象ドメイン: https://www.city.okayama.jp/kurashi/category/1-15-1-0-0-0-0-0-0-0.html

特徴:
- 岡山市公式 CMS のカテゴリページに、保護犬・保護猫の個別記事リンクが
  日付付きで列挙されている list + detail 構造。
- 一覧ページ本文の `<ul class="category_end">` 配下の `<li>` 各要素が
  1 件 = 1 動物 (もしくは 1 件のお知らせ記事) を表し、
  `<a href="./../0000067714.html">1D2026023保護犬個別情報</a>` のように
  10 桁数字 + `.html` の記事 URL がリンクされている。
- サイドメニュー (`aside.page_right`) や「同じ階層の情報」リスト、
  パンくず・グローバルナビにも `/kurashi/...` のリンクが多数あるため、
  本文エリアの `ul.category_end` に絞ることでサイドリンクの混入を防ぐ。
- お知らせ記事 (例: 「保護犬の人馴れ訓練プロジェクト」「岡山市保護猫情報」
  「保護犬情報一覧」) も同じ `<ul>` に並ぶため、URL からの完全な動物/
  お知らせ判定はできない。本 adapter は detail URL を一覧として返し、
  detail ページ抽出時に 1 フィールドも取れない場合 (お知らせ記事等) は
  `ParsingError` を出す既定動作に任せる。
- 詳細ページの実 HTML は当初本リポジトリ内に fixture として入手できて
  いなかったため、自治体 CMS 共通で多用される `<th>項目名</th><td>値</td>`
  のテーブル、または `<dt>項目名</dt><dd>値</dd>` の定義リストいずれかで
  各フィールドが並ぶ前提で `WordPressListAdapter` の既定実装に乗せていた。
  さらに `<th>` を持たない 2 カラムテーブル
  (`<td>label</td><td>value</td>`) にもフォールバックする。
- T125 (2026-09-03) で実サイト (`0000077577.html` 等) を実機取得し、
  以下の差異を確認・修正した:
  - shelter_date / location の実ラベルは「収容日」「収容場所」ではなく
    「保護日」「保護場所」(旧ラベルも後方互換で残す)。誤ラベルのまま
    だと常に空文字となり、location は DataNormalizer 側で「不明」に
    フォールバックしていた (致命8フィールドの1つが常時欠落)。
  - 電話番号はテーブル/定義リストではなく、本文末尾の
    `<section class="kiji_aside ...">` 内の自由文
    (`<p>電話: 086-803-1259　ファクス: ...</p>`) にのみ存在する。
    ラベル抽出 (dt/dd, th/td) では原理的に拾えないため、当該セクション
    のテキストを正規表現で正規化する専用抽出を追加した。
    フッタの市代表電話 (例: 086-803-1000) と混同しないよう、
    `kiji_aside` セクション内に限定して探す。
  - 個体識別用の管理番号 (例: "1D2026049") はタイトル/h1 先頭に
    `<ID>保護犬個別情報` / `<ID>保護猫個別情報` の形で現れるため、
    先頭部分を management_number として抽出する。
  - 写真取得時に `/module/access_log.cgi` `/module/get_trend.cgi` の
    アクセス解析用トラッキングピクセルが img として混入するため除外する。
- 動物種別 (species) はラベル抽出を優先し、空のときは記事タイトル
  (例: "1D2026023保護犬個別情報") またはサイト名から「犬/猫」を推定する。
- 在庫 0 件 (記事リンク 0 件) のときは ParsingError ではなく空リストを返す。
"""

from __future__ import annotations

import re
from typing import ClassVar

from bs4 import BeautifulSoup, Tag

from ....domain.models import RawAnimalData
from ...municipality_adapter import ParsingError
from ..registry import SiteAdapterRegistry
from ..wordpress_list import FieldSpec, WordPressListAdapter


class CityOkayamaAdapter(WordPressListAdapter):
    """岡山市保護動物情報 rule-based adapter

    list_url 本文の `ul.category_end` 配下から detail URL を抽出し、
    各 detail ページの定義リスト/テーブルから RawAnimalData を構築する。
    """

    # 一覧ページ本文の記事リスト `<ul class="category_end">` 配下の
    # `<a>` のみを拾う。サイドメニュー (`aside.page_right`) やパンくず・
    # グローバルナビの同種リンクは `ul.category_end` 配下ではないため
    # 自然に除外される。
    LIST_LINK_SELECTOR: ClassVar[str] = "ul.category_end li a"

    # detail ページのラベル。T125 (2026-09-03) で実サイトを実機取得し、
    # shelter_date/location は実ラベル (保護日/保護場所) を優先しつつ
    # 旧想定ラベル (収容日/収容場所) も後方互換で残す。size は実サイトの
    # 詳細ページに対応する項目が無いため、他の自治体 CMS で見られる
    # 一般的な見出しのまま残す (該当が無ければ空文字のまま無害)。
    FIELD_SELECTORS: ClassVar[dict[str, FieldSpec]] = {
        # 種類 / 品種 (例: "雑種", "柴犬", "三毛")
        "species": FieldSpec(label="種類"),
        # 性別 (例: "オス", "メス", "不明")
        "sex": FieldSpec(label="性別"),
        # 年齢 (例: "成犬", "子犬", "推定3歳")
        "age": FieldSpec(label="年齢"),
        # 毛色
        "color": FieldSpec(label="毛色"),
        # 大きさ (体格)
        "size": FieldSpec(label="大きさ"),
        # 保護日 (実ラベル) / 収容日 (旧想定ラベル、後方互換)
        "shelter_date": FieldSpec(label=("保護日", "収容日")),
        # 保護場所 (実ラベル) / 収容場所 (旧想定ラベル、後方互換)
        "location": FieldSpec(label=("保護場所", "収容場所")),
        # 連絡先 (電話番号)。実サイトはテーブルにこのラベルを持たず
        # `section.kiji_aside` の自由文にのみ電話番号があるため、
        # ここで空だった場合は extract_animal_details 内で
        # _extract_phone_from_contact_section によるフォールバック抽出を行う。
        "phone": FieldSpec(label="連絡先"),
    }

    # detail ページ本文末尾の「お問い合わせ」欄。電話番号がテーブル化されて
    # おらず自由文でしか取得できないため、専用抽出のスコープをこのクラスに限定する
    # (フッタの市代表電話と混同しないため)。
    CONTACT_SECTION_CLASS: ClassVar[str] = "kiji_aside"

    # タイトル/h1 先頭の管理番号。例: "1D2026049保護犬個別情報" → "1D2026049"
    _MANAGEMENT_NUMBER_RE: ClassVar[re.Pattern[str]] = re.compile(
        r"^([0-9A-Za-z]{3,20})(?=保護[犬猫]個別情報)"
    )

    # 動物写真は detail ページ内 `<img>` から拾い、テンプレート由来
    # (/css/img/, /design_img/, /images/, favicon 等) を除外する。
    IMAGE_SELECTOR: ClassVar[str] = "img"

    # 詳細記事 URL の典型パターン: 10 桁数字 + `.html`
    # 例: "/kurashi/0000067714.html", "./../0000067714.html"
    _ARTICLE_HREF_RE: ClassVar[re.Pattern[str]] = re.compile(r"/?\d{10}\.html$")

    # ─────────────────── オーバーライド ───────────────────

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        """一覧ページから detail URL を抽出する (0 件は正常系として許容)

        基底 `WordPressListAdapter.fetch_animal_list` は detail link が
        1 件も見つからない場合に `ParsingError` を投げるが、本サイトは
        在庫 0 件 (お知らせ記事も無い) の状態も想定し得るため、link が
        0 件の場合は空リストを返す。
        """
        html = self._http_get(self.site_config.list_url)
        soup = BeautifulSoup(html, "html.parser")

        links = soup.select(self.LIST_LINK_SELECTOR)
        if not links:
            return []

        urls: list[tuple[str, str]] = []
        seen: set[str] = set()
        category = self.site_config.category
        for link in links:
            href = link.get("href")
            if not href or not isinstance(href, str):
                continue
            # 念のため、10 桁数字 + .html の記事リンクのみ採用する。
            # `category/...` のカテゴリトップへのリンクが混入することを防ぐ。
            if not self._ARTICLE_HREF_RE.search(href):
                continue
            absolute = self._absolute_url(href)
            if absolute in seen:
                continue
            seen.add(absolute)
            urls.append((absolute, category))
        return urls

    def extract_animal_details(self, detail_url: str, category: str = "adoption") -> RawAnimalData:
        """detail ページから RawAnimalData を構築する

        基底実装に加え、以下の岡山市固有処理を行う:
        - species (動物種別) はラベル抽出を優先し、空のときは
          ページタイトル ("1D2026023保護犬個別情報" 等) または
          site_config.name から「犬/猫」を推定する。
        - 1 フィールドも抽出できなかった場合は ParsingError。
        """
        html = self._http_get(detail_url)
        soup = BeautifulSoup(html, "html.parser")

        fields: dict[str, str] = {}
        for name, spec in self.FIELD_SELECTORS.items():
            value = self._extract_field(soup, spec)
            fields[name] = value

        # 電話番号はテーブル/定義リストに存在せず、本文末尾の
        # `section.kiji_aside` 内の自由文にのみ書かれているサイトがある
        # (T125)。ラベル抽出で拾えなかった場合のみフォールバックする。
        if not fields.get("phone"):
            contact_text = self._extract_contact_section_text(soup)
            if contact_text:
                fields["phone"] = contact_text

        if not any(fields.values()):
            raise ParsingError(
                "detail ページから 1 フィールドも抽出できませんでした",
                url=detail_url,
            )

        # 「種類」(品種: 雑種/柴犬等)は species 本体ではなく犬種=breed。品種をそのまま
        # species にすると normalizer で「雑種」が「その他」に誤分類され breed も欠落する
        # (二重バグ・mie_dakc 同型)。species はタイトル/h1/site 名から犬/猫を推定し、
        # 品種は breed として保存する。推定不能なら従来どおり品種テキストを species に残す。
        breed = fields.get("species", "")
        title_only_text = ""
        title_el = soup.find("title")
        if isinstance(title_el, Tag):
            title_only_text = title_el.get_text(strip=True)
        h1_text = ""
        h1_el = soup.find("h1")
        if isinstance(h1_el, Tag):
            h1_text = h1_el.get_text(strip=True)
        title_text = f"{title_only_text} {h1_text}"
        species = (
            self._infer_species_from_text(title_text)
            or self._infer_species_from_text(self.site_config.name)
            or breed
        )

        # 個体識別用の管理番号。タイトル/h1 先頭に
        # "<ID>保護犬個別情報" / "<ID>保護猫個別情報" の形で現れる (T125)。
        management_number = self._extract_management_number(
            title_only_text
        ) or self._extract_management_number(h1_text)

        image_urls = self._extract_images(soup, detail_url)

        try:
            return RawAnimalData(
                species=species,
                breed=breed,
                sex=fields.get("sex", ""),
                age=fields.get("age", ""),
                color=fields.get("color", ""),
                size=fields.get("size", ""),
                shelter_date=fields.get("shelter_date", ""),
                location=fields.get("location", ""),
                phone=self._normalize_phone(fields.get("phone", "")),
                image_urls=image_urls,
                source_url=detail_url,
                category=category,
                management_number=management_number,
            )
        except Exception as e:
            raise ParsingError(f"RawAnimalData バリデーション失敗: {e}", url=detail_url) from e

    # ─────────────────── 抽出ヘルパー拡張 ───────────────────

    def _extract_contact_section_text(self, soup: BeautifulSoup) -> str:
        """本文末尾の「お問い合わせ」欄 (`section.kiji_aside`) のテキストを返す

        電話番号がテーブル/定義リスト化されておらず自由文
        (`<p>電話: 086-803-1259　ファクス: ...</p>`) でしか書かれていない
        サイトがあるため (T125)、ラベル抽出では拾えない。`_normalize_phone`
        に渡す前提でテキストをそのまま返す (正規表現抽出は呼び出し側で行う)。
        フッタの市代表電話 (例: 086-803-1000) と混同しないよう、
        `kiji_aside` セクション内に限定して探す。
        """
        for section in soup.find_all("section"):
            if not isinstance(section, Tag):
                continue
            classes = section.get("class") or []
            if self.CONTACT_SECTION_CLASS not in classes:
                continue
            text = section.get_text(" ", strip=True)
            if "電話" in text:
                return text
        return ""

    def _extract_management_number(self, text: str) -> str:
        """タイトル/h1 先頭の管理番号を抽出する

        例: "1D2026049保護犬個別情報" → "1D2026049"
        """
        if not text:
            return ""
        m = self._MANAGEMENT_NUMBER_RE.match(text)
        return m.group(1) if m else ""

    def _extract_by_label(self, soup: BeautifulSoup, label: str | tuple[str, ...]) -> str:
        """基底の `<dt>/<dd>`, `<th>/<td>` に加えて `<td>/<td>` パターンも探す

        本サイトの詳細ページは実 HTML が入手できていないが、自治体 CMS では
        `<th>` を持たない 2 列テーブル (左 td: ラベル, 右 td: 値) も
        頻出するため、フォールバックとして対応する
        (city_oita / city_kumamoto と同等の方針)。

        `label` は基底クラスと同様、単一ラベルの str または複数候補の
        tuple/list を OR 検索として受け取れる (T125: 実ラベル/旧想定ラベル
        の後方互換のため shelter_date/location で tuple を使用する)。
        """
        # まず基底の dl / th-td パターンを試す
        value = super()._extract_by_label(soup, label)
        if value:
            return value

        # フォールバック: <td>label</td><td>value</td> の 2 列テーブル
        labels = (label,) if isinstance(label, str) else tuple(label)
        for td in soup.find_all("td"):
            if not isinstance(td, Tag):
                continue
            cell_text = td.get_text(strip=True)
            if not cell_text or not any(lbl in cell_text for lbl in labels):
                continue
            sibling = td.find_next_sibling("td")
            if sibling is None:
                continue
            sibling_text = sibling.get_text(strip=True)
            if sibling_text:
                return sibling_text
        return ""

    def _filter_image_urls(self, urls: list[str], base_url: str) -> list[str]:
        """テンプレート装飾画像・トラッキングピクセルを除外する

        岡山市 CMS は `/css/img/`, `/design_img/`, `/images/` 配下に
        ロゴ・装飾画像を置いているため、これらを除外したリストを返す。
        また `/module/access_log.cgi` `/module/get_trend.cgi` はアクセス
        解析用トラッキングピクセル (実画像ではない) として img タグに
        埋め込まれているため、`/module/` 配下も除外する (T125)。
        除外後に 0 件になった場合は元リストを返す (フェイルセーフ)。
        """
        filtered = [
            u
            for u in urls
            if "/css/img/" not in u
            and "/css/" not in u
            and "/design_img/" not in u
            and "/images/clearspacer" not in u
            and "/module/" not in u
            and not u.endswith(".ico")
            and not u.endswith(".gif")
        ]
        return filtered if filtered else urls

    # ─────────────────── 種別推定 ───────────────────

    @staticmethod
    def _infer_species_from_text(text: str) -> str:
        """テキスト ("...保護犬..." / "保護猫..." / "岡山市（保護動物情報）" 等)
        から動物種別を推定する

        - "犬" を含み "猫" を含まない → "犬"
        - "猫" を含み "犬" を含まない → "猫"
        - 両方含む / どちらも含まない → ""
        """
        if not text:
            return ""
        has_dog = bool(re.search(r"犬", text))
        has_cat = bool(re.search(r"猫", text))
        if has_dog and not has_cat:
            return "犬"
        if has_cat and not has_dog:
            return "猫"
        return ""


# ─────────────────── サイト登録 ───────────────────
# `sites.yaml` の `name` フィールドと完全一致するサイト名で登録する。
for _site_name in ("岡山市（保護動物情報）",):
    if SiteAdapterRegistry.get(_site_name) is None:
        SiteAdapterRegistry.register(_site_name, CityOkayamaAdapter)
