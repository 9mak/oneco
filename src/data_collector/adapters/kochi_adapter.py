"""
高知県アダプター

高知県自治体サイトから保護動物情報をスクレイピングするアダプターです。
"""

from typing import List
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .municipality_adapter import MunicipalityAdapter, NetworkError, ParsingError
from ..domain.models import RawAnimalData, AnimalData
from ..domain.normalizer import DataNormalizer


class KochiAdapter(MunicipalityAdapter):
    """
    高知県自治体サイト向けスクレイピング実装

    高知県の保護動物情報サイトから犬猫の情報を収集し、
    統一スキーマに変換します。
    """

    # 高知県中央・中村小動物管理センター
    BASE_URL = "https://kochi-apc.com"

    # 譲渡情報ページ（譲渡対象動物）
    JOUTO_URL = f"{BASE_URL}/jouto/"

    # 迷子情報ページ（飼い主の迎えを待つ動物）
    MAIGO_URL = f"{BASE_URL}/maigo/"

    # HTTP リクエストヘッダー
    HEADERS = {
        "User-Agent": "PetRescueApp/1.0 (Data Collection Bot for Animal Rescue)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ja,en;q=0.5",
    }

    # リクエストタイムアウト（秒）
    TIMEOUT = 30

    # 一覧ページの期待される構造（WordPress + VK Filter Search Pro）
    # 動物カードはfigureまたはdiv内に配置され、「詳細はこちら」リンクを含む
    LIST_PAGE_SELECTORS = ["a[href*='/center-data/']"]

    # 詳細ページの期待される構造（定義リストまたはテーブル）
    DETAIL_PAGE_SELECTORS = ["dl", "dt", "dd", "table", "body"]

    def __init__(self):
        """高知県アダプターを初期化"""
        super().__init__(prefecture_code="39", municipality_name="高知県")

    def fetch_animal_list(self) -> List[str]:
        """
        高知県の一覧ページから個体詳細 URL リストを抽出

        譲渡情報と迷子情報の両方から動物の詳細ページURLを収集します。

        Returns:
            List[str]: 個体詳細ページの絶対 URL リスト

        Raises:
            NetworkError: HTTP エラー発生時
            ParsingError: HTML 構造が想定と異なる時
        """
        all_urls = []

        # 譲渡情報と迷子情報の両方から収集
        for page_url, page_type in [
            (self.JOUTO_URL, "譲渡情報"),
            (self.MAIGO_URL, "迷子情報"),
        ]:
            try:
                urls = self._fetch_from_page(page_url, page_type)
                all_urls.extend(urls)
            except (NetworkError, ParsingError) as e:
                # 片方のページでエラーが発生しても、もう片方は処理を続行
                # エラーは上位でログ出力される想定
                raise

        # 重複を削除（同じ動物が両方のページに掲載される可能性は低いが念のため）
        return list(set(all_urls))

    def _fetch_from_page(self, page_url: str, page_type: str) -> List[str]:
        """
        指定されたページから動物詳細URLを抽出

        Args:
            page_url: 一覧ページのURL
            page_type: ページ種別（ログ用）

        Returns:
            List[str]: 詳細ページのURLリスト

        Raises:
            NetworkError: HTTP エラー発生時
            ParsingError: HTML 構造が想定と異なる時
        """
        try:
            response = requests.get(
                page_url,
                headers=self.HEADERS,
                timeout=self.TIMEOUT,
            )
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            raise NetworkError(
                f"HTTP エラー ({page_type}): {e}",
                url=page_url,
                status_code=response.status_code if response else None,
            )
        except requests.exceptions.RequestException as e:
            raise NetworkError(
                f"ネットワークエラー ({page_type}): {e}",
                url=page_url,
            )

        soup = BeautifulSoup(response.text, "html.parser")

        # リンク抽出: /center-data/ へのリンクを探す
        # 「詳細はこちら」リンクを取得
        urls = []
        detail_links = soup.select("a[href*='/center-data/']")

        if not detail_links:
            raise ParsingError(
                f"{page_type}ページに動物詳細リンクが見つかりません",
                selector="a[href*='/center-data/']",
                url=page_url,
            )

        for link in detail_links:
            href = link.get("href")
            if href:
                # 相対パスを絶対 URL に変換
                absolute_url = urljoin(self.BASE_URL, href)
                # 重複を避けるため、最後の "/" を削除して正規化
                absolute_url = absolute_url.rstrip("/")
                urls.append(absolute_url)

        return urls

    def extract_animal_details(self, detail_url: str) -> RawAnimalData:
        """
        高知県の詳細ページから動物情報を抽出

        WordPress投稿ページから以下の情報を抽出：
        - 管理番号、仮名、種類、性別、年齢、毛色、体格
        - 収容日、収容場所、電話番号、画像URL

        Args:
            detail_url: 個体詳細ページの URL

        Returns:
            RawAnimalData: 抽出した生データ

        Raises:
            NetworkError: HTTP エラー発生時
            ParsingError: HTML 構造が想定と異なる時
        """
        try:
            response = requests.get(
                detail_url,
                headers=self.HEADERS,
                timeout=self.TIMEOUT,
            )
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            raise NetworkError(
                f"HTTP エラー: {e}",
                url=detail_url,
                status_code=response.status_code if response else None,
            )
        except requests.exceptions.RequestException as e:
            raise NetworkError(
                f"ネットワークエラー: {e}",
                url=detail_url,
            )

        soup = BeautifulSoup(response.text, "html.parser")

        # ページ構造検証（WordPress投稿ページの基本構造）
        if not self._validate_page_structure(soup, self.DETAIL_PAGE_SELECTORS):
            raise ParsingError(
                "詳細ページの構造が変更されています",
                selector=", ".join(self.DETAIL_PAGE_SELECTORS),
                url=detail_url,
            )

        # ページ本文を取得（body全体）
        entry_content = soup.select_one("body")
        if not entry_content:
            raise ParsingError(
                "body要素が見つかりません",
                selector="body",
                url=detail_url,
            )

        # 定義リストまたはテーブルから情報を抽出
        species = self._extract_from_structured_data(
            entry_content, ["品種", "種類", "しゅるい"]
        )
        sex = self._extract_from_structured_data(entry_content, ["性別", "せいべつ"])
        age = self._extract_from_structured_data(
            entry_content, ["年齢", "推定年齢", "ねんれい", "月齢"]
        )
        color = self._extract_from_structured_data(
            entry_content, ["毛色", "色", "けいろ"]
        )
        size = self._extract_from_structured_data(
            entry_content, ["体格", "大きさ", "サイズ", "たいかく"]
        )
        shelter_date = self._extract_from_structured_data(
            entry_content, ["保護した日時", "保護日時", "収容日", "保護日", "しゅうようび"]
        )
        location = self._extract_from_structured_data(
            entry_content, ["保護した場所", "保護場所", "収容場所", "場所", "ばしょ"]
        )
        # 電話番号は管轄保健所の情報に含まれている
        phone = self._extract_from_structured_data(
            entry_content,
            ["管轄保健所", "電話", "連絡先", "でんわ", "TEL", "問い合わせ先"],
        )

        # 画像 URL 抽出
        image_urls = self._extract_image_urls_from_content(entry_content, detail_url)

        return RawAnimalData(
            species=species,
            sex=sex,
            age=age,
            color=color,
            size=size,
            shelter_date=shelter_date,
            location=location,
            phone=phone,
            image_urls=image_urls,
            source_url=detail_url,
        )

    def normalize(self, raw_data: RawAnimalData) -> AnimalData:
        """
        生データを統一スキーマに正規化

        DataNormalizer に処理を委譲します。

        Args:
            raw_data: 自治体サイトから抽出した生データ

        Returns:
            AnimalData: 正規化済みデータ
        """
        return DataNormalizer.normalize(raw_data)

    def _validate_page_structure(
        self, soup: BeautifulSoup, expected_selectors: List[str]
    ) -> bool:
        """
        ページ構造が想定通りか検証

        Args:
            soup: BeautifulSoup オブジェクト
            expected_selectors: 期待される CSS セレクターリスト

        Returns:
            bool: いずれかのセレクターが存在すれば True（ORロジック）
        """
        for selector in expected_selectors:
            if soup.select_one(selector):
                return True
        return False

    def _extract_from_structured_data(self, content, field_names: List[str]) -> str:
        """
        構造化データ（定義リストまたはテーブル）から特定のフィールド値を抽出

        Args:
            content: BeautifulSoup要素
            field_names: フィールド名の候補リスト

        Returns:
            str: 抽出された値（見つからない場合は空文字列）
        """
        # 定義リスト（dl/dt/dd）から抽出を試みる
        value = self._extract_from_definition_list(content, field_names)
        if value:
            return value

        # テーブル（table/tr/td）から抽出を試みる
        value = self._extract_from_table(content, field_names)
        if value:
            return value

        # フォールバック: テキストベースの抽出
        return self._extract_field_from_text(
            content.get_text(separator="\n", strip=True), field_names
        )

    def _extract_from_definition_list(
        self, content, field_names: List[str]
    ) -> str:
        """
        定義リスト（dl/dt/dd）から特定のフィールド値を抽出

        Args:
            content: BeautifulSoup要素
            field_names: フィールド名の候補リスト

        Returns:
            str: 抽出された値（見つからない場合は空文字列）
        """
        # すべてのdtとddのペアを取得
        dt_elements = content.select("dt")
        for dt in dt_elements:
            label = dt.get_text(strip=True)

            # フィールド名と一致するか確認
            for field_name in field_names:
                if field_name in label:
                    # 次のdd要素を取得
                    dd = dt.find_next_sibling("dd")
                    if dd:
                        return dd.get_text(strip=True)

        return ""

    def _extract_from_table(self, content, field_names: List[str]) -> str:
        """
        テーブル構造から特定のフィールド値を抽出

        テーブルの行（tr）から、ラベル（th/td）に一致する値（td）を抽出します。
        例: <tr><th>品種</th><td>柴犬</td></tr> → "柴犬"
        例: <tr><td>品種</td><td>柴犬</td></tr> → "柴犬"

        Args:
            content: BeautifulSoup要素
            field_names: フィールド名の候補リスト

        Returns:
            str: 抽出された値（見つからない場合は空文字列）
        """
        # テーブル内のすべてのtrを取得
        rows = content.select("tr")
        for row in rows:
            # th + td のパターンを試す
            ths = row.select("th")
            tds = row.select("td")

            if len(ths) >= 1 and len(tds) >= 1:
                # th（ラベル）とtd（値）のペア
                label = ths[0].get_text(strip=True)
                value = tds[0].get_text(strip=True)

                # フィールド名と一致するか確認
                for field_name in field_names:
                    if field_name in label:
                        return value

            elif len(tds) >= 2:
                # td + td のパターン（古い実装との互換性）
                label = tds[0].get_text(strip=True)
                value = tds[1].get_text(strip=True)

                # フィールド名と一致するか確認
                for field_name in field_names:
                    if field_name in label:
                        return value

        # テーブルで見つからない場合、テキストベースのフォールバック
        return self._extract_field_from_text(
            content.get_text(separator="\n", strip=True), field_names
        )

    def _extract_field_from_text(self, content_text: str, field_names: List[str]) -> str:
        """
        テキストから特定のフィールド値を抽出（フォールバック用）

        フィールド名に続く値を抽出します（例: "種類：ミックス" → "ミックス"）

        Args:
            content_text: 投稿本文のテキスト
            field_names: フィールド名の候補リスト

        Returns:
            str: 抽出された値（見つからない場合は空文字列）
        """
        import re

        lines = content_text.split("\n")
        for line in lines:
            for field_name in field_names:
                # "フィールド名：値"、"フィールド名:値"、"フィールド名　値" のパターンに対応
                pattern = rf"{field_name}[\s：:]*(.+)"
                match = re.search(pattern, line, re.IGNORECASE)
                if match:
                    value = match.group(1).strip()
                    # 括弧やその他の余分な記号を削除
                    value = re.sub(r"[\(\)（）\[\]【】]", "", value).strip()
                    if value:
                        return value
        return ""

    def _extract_image_urls_from_content(
        self, entry_content, base_url: str
    ) -> List[str]:
        """
        投稿本文から画像 URL を抽出し、絶対 URL に変換

        Args:
            entry_content: BeautifulSoup 投稿本文要素
            base_url: ベース URL（相対パス変換用）

        Returns:
            List[str]: 画像の絶対 URL リスト
        """
        image_urls = []
        # 投稿本文内のすべてのimg要素を取得
        images = entry_content.select("img")
        for img in images:
            src = img.get("src")
            if src:
                # 相対パスを絶対 URL に変換
                absolute_url = urljoin(base_url, src)
                # 画像URLの妥当性を簡易チェック
                if absolute_url.startswith(("http://", "https://")):
                    image_urls.append(absolute_url)
        return image_urls
