"""
高知県アダプター

高知県自治体サイトから保護動物情報をスクレイピングするアダプターです。
"""

from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from ..domain.models import AnimalData, RawAnimalData
from ..domain.normalizer import DataNormalizer
from .municipality_adapter import MunicipalityAdapter, NetworkError, ParsingError


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

    # カテゴリ定数
    CATEGORY_ADOPTION = "adoption"
    CATEGORY_LOST = "lost"

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

    # 【高知県特別ルール】一覧ページのカテゴリリンクから犬/猫を判定するためのパターン
    _SPECIES_URL_PATTERNS = {
        "_inu": "犬",
        "_neko": "猫",
    }

    # 【高知県特別ルール】年齢テキストから推定月齢へのマッピング
    # 正規化共通ロジック (DataNormalizer) では "N歳", "Nヶ月" 等の数値パターンのみ対応
    # 高知県サイト固有の日本語テキスト年齢表記に対応
    _KOCHI_AGE_ESTIMATES = {
        "高齢": 120,  # 10歳相当
        "老齢": 120,  # 10歳相当
        "老犬": 120,  # 10歳相当
        "老猫": 120,  # 10歳相当
        "成犬": 36,  # 3歳相当
        "成猫": 36,  # 3歳相当
        "成熟": 36,  # 3歳相当
        "中齢": 60,  # 5歳相当
        "若犬": 18,  # 1.5歳相当
        "若猫": 18,  # 1.5歳相当
        "若齢": 18,  # 1.5歳相当
        "仔犬": 3,  # 3ヶ月相当
        "子犬": 3,  # 3ヶ月相当
        "仔猫": 3,  # 3ヶ月相当
        "子猫": 3,  # 3ヶ月相当
        "幼齢": 3,  # 3ヶ月相当
        "乳飲み子": 1,  # 1ヶ月相当
    }

    def __init__(self):
        """高知県アダプターを初期化"""
        super().__init__(prefecture_code="39", municipality_name="高知県")
        # 【高知県特別ルール】一覧ページから取得した犬/猫種別情報を保持
        # key: detail_url, value: "犬" or "猫"
        self._species_from_list: dict = {}

    def fetch_animal_list(self) -> list[tuple[str, str]]:
        """
        高知県の一覧ページから個体詳細 URL とカテゴリのリストを抽出

        譲渡情報と迷子情報の両方から動物の詳細ページURLとカテゴリを収集します。
        各動物のカテゴリリンクから犬/猫の種別も判定し、URLにメタデータとして付与します。

        Returns:
            List[Tuple[str, str]]: (個体詳細ページURL, category) のタプルリスト
                category: 'adoption' (譲渡対象) または 'lost' (迷子)

        Raises:
            NetworkError: HTTP エラー発生時
            ParsingError: HTML 構造が想定と異なる時
        """
        all_urls = []

        # 譲渡情報と迷子情報の両方から収集
        for page_url, page_type, category in [
            (self.JOUTO_URL, "譲渡情報", self.CATEGORY_ADOPTION),
            (self.MAIGO_URL, "迷子情報", self.CATEGORY_LOST),
        ]:
            try:
                urls_with_species = self._fetch_from_page(page_url, page_type)
                # 各URLにカテゴリを付与（species情報はインスタンス変数で保持）
                all_urls.extend([(url, category) for url, _species in urls_with_species])
            except (NetworkError, ParsingError):
                # 片方のページでエラーが発生しても、もう片方は処理を続行
                # エラーは上位でログ出力される想定
                raise

        # 重複を削除（同じ動物が両方のページに掲載される可能性は低いが念のため）
        return list(set(all_urls))

    def _fetch_from_page(self, page_url: str, page_type: str) -> list[tuple[str, str]]:
        """
        指定されたページから動物詳細URLと犬猫種別を抽出

        Args:
            page_url: 一覧ページのURL
            page_type: ページ種別（ログ用）

        Returns:
            List[Tuple[str, str]]: (詳細ページURL, 種別) のタプルリスト
                種別: "犬", "猫", "" (判定不能)

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

        # 【高知県特別ルール】カテゴリリンクから犬猫種別マップを構築
        # 各動物カードのカテゴリリンク（maigojouto_cat=center_jouto_inu 等）を解析
        self._build_species_map_from_list_page(soup)

        # リンク抽出: /center-data/ へのリンクを探す
        # 「詳細はこちら」リンクを取得
        results = []
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
                species = self._species_from_list.get(absolute_url, "")
                results.append((absolute_url, species))

        return results

    def _build_species_map_from_list_page(self, soup: BeautifulSoup) -> None:
        """
        【高知県特別ルール】一覧ページのカードからURL→犬猫種別のマップを構築

        高知県サイトでは、各動物カードにカテゴリリンク（例:
        maigojouto_cat=center_jouto_inu）が含まれており、そこから犬猫を判定できる。
        詳細ページの「品種」フィールドは「雑種」等の品種名で、犬猫の区別がつかないため、
        一覧ページの情報を使う。

        Args:
            soup: 一覧ページのBeautifulSoupオブジェクト
        """
        # カテゴリリンク（maigojouto_catパラメータ含む）を持つ全てのaタグを取得
        category_links = soup.select("a[href*='maigojouto_cat=']")
        for cat_link in category_links:
            cat_href = cat_link.get("href", "")

            # カテゴリURLから犬猫を判定
            detected_species = ""
            for pattern, species in self._SPECIES_URL_PATTERNS.items():
                if pattern in cat_href:
                    detected_species = species
                    break

            if not detected_species:
                continue

            # 同じカード内の詳細リンクを探す（共通の親要素を辿る）
            parent = cat_link.parent
            detail_link = None
            # 最大5階層上まで探索
            for _ in range(5):
                if parent is None:
                    break
                detail_link = parent.select_one("a[href*='/center-data/']")
                if detail_link:
                    break
                parent = parent.parent

            if detail_link:
                detail_href = detail_link.get("href", "")
                detail_url = urljoin(self.BASE_URL, detail_href).rstrip("/")
                self._species_from_list[detail_url] = detected_species

    def extract_animal_details(self, detail_url: str, category: str = "adoption") -> RawAnimalData:
        """
        高知県の詳細ページから動物情報を抽出

        WordPress投稿ページから以下の情報を抽出：
        - 管理番号、仮名、種類、性別、年齢、毛色、体格
        - 収容日、収容場所、電話番号、画像URL、カテゴリ

        Args:
            detail_url: 個体詳細ページの URL
            category: カテゴリ ('adoption' または 'lost')、デフォルトは 'adoption'

        Returns:
            RawAnimalData: 抽出した生データ（category を含む）

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
        # 【高知県特別ルール】品種フィールドは「雑種」等の品種名を返すため、
        # 一覧ページで判定した犬猫種別を優先使用し、品種名はフォールバック
        breed = self._extract_from_structured_data(entry_content, ["品種", "種類", "しゅるい"])
        species = self._species_from_list.get(detail_url, "")
        if not species:
            # フォールバック: 品種名に犬/猫が含まれているか、ページ内テキストから推定
            species = self._detect_species_from_content(entry_content, breed)
        sex = self._extract_from_structured_data(entry_content, ["性別", "せいべつ"])
        age = self._extract_from_structured_data(
            entry_content, ["年齢", "推定年齢", "ねんれい", "月齢"]
        )
        color = self._extract_from_structured_data(entry_content, ["毛色", "色", "けいろ"])
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
            category=category,
        )

    def normalize(self, raw_data: RawAnimalData) -> AnimalData:
        """
        生データを統一スキーマに正規化

        KochiAdapter固有のフォールバック処理を行い、
        DataNormalizer に処理を委譲します。

        【高知県特別ルール】
        - locationが空の場合は「高知県」をフォールバック値として設定
        - 画像URLからテンプレート画像を除外
        - 年齢テキストの推定変換（「高齢」→120ヶ月等）
        - 未来日付の補正

        Args:
            raw_data: 自治体サイトから抽出した生データ

        Returns:
            AnimalData: 正規化済みデータ
        """
        # 【高知県特別ルール】画像URLからテンプレート画像を除外
        filtered_images = self._filter_kochi_image_urls(raw_data.image_urls or [])

        # 【高知県特別ルール】年齢テキストの推定変換
        age = raw_data.age
        age = self._estimate_kochi_age(age)

        # 【高知県特別ルール】未来日付の補正 & 空日付のフォールバック
        shelter_date = self._validate_kochi_date(raw_data.shelter_date)
        if not shelter_date or not shelter_date.strip():
            # 日付が空の場合、本日の日付をフォールバックとして使用
            from datetime import date

            shelter_date = date.today().strftime("%Y-%m-%d")

        # locationが空の場合は「高知県」をフォールバック値として設定
        raw_data = RawAnimalData(
            species=raw_data.species,
            sex=raw_data.sex,
            age=age,
            color=raw_data.color,
            size=raw_data.size,
            shelter_date=shelter_date,
            location=raw_data.location if raw_data.location else "高知県",
            phone=raw_data.phone,
            image_urls=filtered_images,
            source_url=raw_data.source_url,
            category=raw_data.category,
        )
        return DataNormalizer.normalize(raw_data)

    def _validate_page_structure(self, soup: BeautifulSoup, expected_selectors: list[str]) -> bool:
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

    def _extract_from_structured_data(self, content, field_names: list[str]) -> str:
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

    def _extract_from_definition_list(self, content, field_names: list[str]) -> str:
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

    def _extract_from_table(self, content, field_names: list[str]) -> str:
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

    def _extract_field_from_text(self, content_text: str, field_names: list[str]) -> str:
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

    def _extract_image_urls_from_content(self, entry_content, base_url: str) -> list[str]:
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

    # =========================================================================
    # 【高知県特別ルール】以下は高知県サイト固有のデータ品質改善メソッド
    # 他の都道府県アダプターでは不要な可能性があります。
    # 共通ロジック (DataNormalizer) は変更せず、アダプター層で対応します。
    # =========================================================================

    def _detect_species_from_content(self, content, breed: str) -> str:
        """
        【高知県特別ルール】ページ内容から犬猫種別を推定

        一覧ページのカテゴリリンクで判定できなかった場合のフォールバック。
        品種名やページ内テキストから犬/猫を判定する。

        Args:
            content: BeautifulSoup要素（詳細ページ本文）
            breed: 品種フィールドの値

        Returns:
            str: "犬", "猫", または品種名そのまま
        """
        # 品種名に犬/猫が含まれていればそのまま使う（normalizer が処理可能）
        dog_keywords = ["犬", "いぬ", "イヌ"]
        cat_keywords = ["猫", "ねこ", "ネコ"]

        for kw in dog_keywords:
            if kw in breed:
                return breed
        for kw in cat_keywords:
            if kw in breed:
                return breed

        # ページのタイトルやURLから推定
        page_text = content.get_text(separator=" ", strip=True)
        # 「保護犬」「保護猫」等のキーワードを探す
        if any(kw in page_text for kw in ["保護犬", "譲渡犬", "迷い犬"]):
            return "犬"
        if any(kw in page_text for kw in ["保護猫", "譲渡猫", "迷い猫", "負傷猫"]):
            return "猫"

        # 判定不能の場合はbreedをそのまま返す（normalizerが「その他」にする）
        return breed

    @staticmethod
    def _filter_kochi_image_urls(image_urls: list[str]) -> list[str]:
        """
        【高知県特別ルール】テンプレート画像を除外

        高知県サイトはWordPressテーマで、body全体からimg取得すると
        /wp-content/themes/ 配下のテンプレート画像が大量に混入する。
        実際の動物写真は /wp-content/uploads/ 配下にある。

        Args:
            image_urls: フィルタリング前の画像URLリスト

        Returns:
            List[str]: テンプレート画像を除外した画像URLリスト
        """
        filtered = [url for url in image_urls if "/wp-content/uploads/" in url]
        # uploads画像が1枚もない場合は元のリストを返す（データ消失防止）
        return filtered if filtered else image_urls

    def _estimate_kochi_age(self, raw_age: str) -> str:
        """
        【高知県特別ルール】日本語テキスト年齢を推定数値に変換

        DataNormalizerは "N歳", "Nヶ月" 等の数値パターンのみ対応。
        高知県サイトでは「高齢」「成犬」「子猫」等のテキスト表記が使われるため、
        アダプター層で推定月齢に変換してからnormalizerに渡す。

        Args:
            raw_age: 年齢テキスト（例: "高齢", "成犬", "3歳"）

        Returns:
            str: normalizerが処理可能な形式（例: "10歳", "3歳", "3ヶ月"）
                 数値パターンの場合はそのまま返す
        """
        if not raw_age:
            return raw_age

        import re
        from datetime import date

        age_stripped = raw_age.strip()

        # 既に数値パターンを含む場合はそのまま返す
        if re.search(r"\d+\s*[歳年]", age_stripped) or re.search(
            r"\d+\s*[ヶかカケ]月", age_stripped
        ):
            return raw_age

        # 【高知県特別ルール】生年月日から年齢を計算
        # パターン: "生年月日：2018.8/2", "生年月日2023.5.12", "誕生日：R8.2/10"
        birthday = self._parse_kochi_birthday(age_stripped)
        if birthday:
            today = date.today()
            age_months = (today.year - birthday.year) * 12 + (today.month - birthday.month)
            age_months = max(age_months, 0)
            if age_months >= 12:
                return f"{age_months // 12}歳"
            else:
                return f"{age_months}ヶ月"

        # 【高知県特別ルール】"推定N歳" や "N-M歳" の範囲パターン
        range_match = re.search(r"(\d+)\s*[-~〜]\s*(\d+)\s*歳", age_stripped)
        if range_match:
            low = int(range_match.group(1))
            high = int(range_match.group(2))
            avg = (low + high) // 2
            return f"{avg}歳"

        # テキスト年齢を推定月齢に変換
        for keyword, months in self._KOCHI_AGE_ESTIMATES.items():
            if keyword in age_stripped:
                if months >= 12:
                    return f"{months // 12}歳"
                else:
                    return f"{months}ヶ月"

        # マッチしない場合はそのまま返す（normalizerがNoneにする）
        return raw_age

    @staticmethod
    def _parse_kochi_birthday(age_text: str) -> "date | None":
        """
        【高知県特別ルール】生年月日テキストからdateオブジェクトを解析

        対応パターン:
        - "生年月日：2018.8/2" → 2018-08-02
        - "生年月日2023.5.12" → 2023-05-12
        - "誕生日：R8.2/10" → 令和8年2月10日
        - "生年月日：H30.7/11" → 平成30年7月11日
        - "生年月日：R1.5/19" → 令和1年5月19日

        Args:
            age_text: 年齢テキスト

        Returns:
            date or None: 解析できた場合はdateオブジェクト
        """
        import re
        from datetime import date

        # 生年月日/誕生日キーワードがない場合はスキップ
        if not any(kw in age_text for kw in ["生年月日", "誕生日"]):
            return None

        # 西暦パターン: 2018.8/2 or 2023.5.12
        match = re.search(r"(\d{4})[./](\d{1,2})[./](\d{1,2})", age_text)
        if match:
            try:
                return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
            except ValueError:
                pass

        # 令和パターン: R8.2/10, R1.5/19
        match = re.search(r"R(\d{1,2})[./](\d{1,2})[./](\d{1,2})", age_text)
        if match:
            try:
                year = 2018 + int(match.group(1))
                return date(year, int(match.group(2)), int(match.group(3)))
            except ValueError:
                pass

        # 平成パターン: H30.7/11
        match = re.search(r"H(\d{1,2})[./](\d{1,2})[./](\d{1,2})", age_text)
        if match:
            try:
                year = 1988 + int(match.group(1))
                return date(year, int(match.group(2)), int(match.group(3)))
            except ValueError:
                pass

        return None

    @staticmethod
    def _validate_kochi_date(raw_date: str) -> str:
        """
        【高知県特別ルール】未来日付を補正

        令和年号の変換で未来日付が生成される場合がある。
        アダプター層で検出し、日付文字列を補正する。

        Args:
            raw_date: 日付テキスト

        Returns:
            str: 補正済み日付テキスト（未来日付の場合は前年に補正）
        """
        if not raw_date:
            return raw_date

        import re
        from datetime import date

        # RN.M/D パターン（"R5　9/26　夕方" 等の付加テキストにも対応）
        match = re.search(r"R(\d{1,2})[.\s\u3000]+(\d{1,2})/(\d{1,2})", raw_date)
        if match:
            reiwa_year = int(match.group(1))
            month = int(match.group(2))
            day = int(match.group(3))
            year = 2018 + reiwa_year
            try:
                parsed = date(year, month, day)
                if parsed > date.today():
                    # 未来日付: 令和年号を1年下げて再試行
                    corrected_year = year - 1
                    corrected = date(corrected_year, month, day)
                    return corrected.strftime("%Y-%m-%d")
                # 正常な日付: ISO形式に変換して返す（normalizerが直接処理可能に）
                return parsed.strftime("%Y-%m-%d")
            except ValueError:
                pass

        # 年なし日付パターン: "6/17", "12/22　午後5時頃" 等
        # normalizerが今年を補完すると未来日付になる場合があるため、前年に補正
        match = re.search(r"^(\d{1,2})/(\d{1,2})", raw_date.strip())
        if match:
            month = int(match.group(1))
            day = int(match.group(2))
            today = date.today()
            try:
                parsed = date(today.year, month, day)
                if parsed > today:
                    parsed = date(today.year - 1, month, day)
                return parsed.strftime("%Y-%m-%d")
            except ValueError:
                pass

        # 令和N年M月D日パターンも同様にチェック・変換
        match = re.search(r"令和(\d+)年(\d+)月(\d+)日", raw_date)
        if match:
            reiwa_year = int(match.group(1))
            month = int(match.group(2))
            day = int(match.group(3))
            year = 2018 + reiwa_year
            try:
                parsed = date(year, month, day)
                if parsed > date.today():
                    corrected_year = year - 1
                    corrected = date(corrected_year, month, day)
                    return corrected.strftime("%Y-%m-%d")
            except ValueError:
                pass

        return raw_date
