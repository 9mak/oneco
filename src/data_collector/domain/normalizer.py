"""
データ正規化ロジック

自治体サイトから抽出した生データ (RawAnimalData) を統一スキーマ (AnimalData) に変換します。
動物種別、性別、年齢、日付、電話番号などの正規化ルールを提供します。
"""

import re
from datetime import date, datetime

from ..utils.prefecture import infer_prefecture_from_url
from .models import AnimalData, RawAnimalData


class DataNormalizer:
    """
    データ正規化クラス

    自治体ごとに異なる形式のデータを統一スキーマに正規化する静的メソッドを提供します。
    """

    # 正規化パターン定義
    _SPECIES_DOG_PATTERNS = ["犬", "いぬ", "イヌ", "inu", "dog"]
    _SPECIES_CAT_PATTERNS = ["猫", "ねこ", "ネコ", "neko", "cat"]

    _SEX_MALE_PATTERNS = ["男の子", "オトコノコ", "オス", "おす", "雄", "♂", "male"]
    _SEX_FEMALE_PATTERNS = ["女の子", "オンナノコ", "メス", "めす", "雌", "♀", "female"]

    _UNKNOWN_PATTERNS = ["不明", "?", "？", "unknown", ""]

    @staticmethod
    def normalize(raw_data: RawAnimalData) -> AnimalData:
        """
        生データを統一スキーマに正規化

        Args:
            raw_data: 自治体サイトから抽出した生データ

        Returns:
            AnimalData: 正規化済みデータ

        Raises:
            ValidationError: 必須フィールド欠損または不正な値の場合
        """
        # 画像URLの処理 (文字列リストをそのまま渡す)
        # AnimalData の image_urls は HttpUrl のリストなので、Pydantic が自動変換する
        image_urls_raw = raw_data.image_urls if raw_data.image_urls else []

        # shelter_date は不明 / 解析不能な場合「データ取得日」をフォールバックに使う。
        # 譲渡カテゴリページや未対応フォーマットの日付表記でも AnimalData 化失敗で
        # 全件落ちることを防ぐためのセーフネット。
        today = DataNormalizer._today()
        raw_shelter = (raw_data.shelter_date or "").strip()
        shelter_date_str = ""
        if raw_shelter:
            try:
                shelter_date_str = DataNormalizer._normalize_date(raw_shelter)
            except ValueError:
                shelter_date_str = ""
        if not shelter_date_str:
            shelter_date_str = today.strftime("%Y-%m-%d")
        else:
            # 収容日/「いなくなった日時」が未来日になるのは物理的に不正
            # (長崎 animal-net の実例)。収集日 (今日) にフォールバックして
            # アーカイブの時系列整合性を守る。
            parsed_shelter = datetime.strptime(shelter_date_str, "%Y-%m-%d").date()
            if parsed_shelter > today:
                shelter_date_str = today.strftime("%Y-%m-%d")

        # 正規化処理
        return AnimalData(
            species=DataNormalizer._normalize_species(raw_data.species),
            sex=DataNormalizer._normalize_sex(raw_data.sex),
            age_months=DataNormalizer._normalize_age(raw_data.age),
            color=DataNormalizer._cap_color(raw_data.color),
            size=DataNormalizer._cap_size(raw_data.size),
            shelter_date=datetime.strptime(shelter_date_str, "%Y-%m-%d").date(),
            location=raw_data.location if raw_data.location else "不明",
            prefecture=infer_prefecture_from_url(raw_data.source_url),
            phone=DataNormalizer._normalize_phone(raw_data.phone) or None,
            image_urls=image_urls_raw,
            source_url=raw_data.source_url,
            category=raw_data.category,
        )

    @staticmethod
    def _normalize_species(raw_species: str) -> str:
        """
        動物種別を '犬', '猫', 'その他' に正規化

        Args:
            raw_species: 正規化前の動物種別

        Returns:
            str: '犬', '猫', 'その他' のいずれか
        """
        species_lower = raw_species.lower().strip()

        # 犬のパターンマッチング
        for pattern in DataNormalizer._SPECIES_DOG_PATTERNS:
            if pattern.lower() in species_lower:
                return "犬"

        # 猫のパターンマッチング
        for pattern in DataNormalizer._SPECIES_CAT_PATTERNS:
            if pattern.lower() in species_lower:
                return "猫"

        # その他
        return "その他"

    @staticmethod
    def _normalize_sex(raw_sex: str) -> str:
        """
        性別を '男の子', '女の子', '不明' に正規化

        Args:
            raw_sex: 正規化前の性別

        Returns:
            str: '男の子', '女の子', '不明' のいずれか
        """
        sex_lower = raw_sex.lower().strip()

        # 女の子のパターンマッチング (male が female に含まれるため、先にチェック)
        for pattern in DataNormalizer._SEX_FEMALE_PATTERNS:
            if pattern.lower() in sex_lower:
                return "女の子"

        # 男の子のパターンマッチング
        for pattern in DataNormalizer._SEX_MALE_PATTERNS:
            if pattern.lower() in sex_lower:
                return "男の子"

        # 不明
        return "不明"

    @staticmethod
    def _today() -> date:
        """テストで時刻固定するためのフック（生年月日からの月数計算用）"""
        return date.today()

    @staticmethod
    def _months_between(birth: date, today: date) -> int | None:
        """birth から today までの経過月数を返す。未来日付なら None。"""
        if birth > today:
            return None
        months = (today.year - birth.year) * 12 + (today.month - birth.month)
        if today.day < birth.day:
            months -= 1
        return max(months, 0)

    # 犬猫の寿命上限の余裕を持った値 (30歳 = 360ヶ月)。これを超える年齢は
    # 個体識別番号や年号の誤抽出 (例: 沖縄 missing の 82歳=984ヶ月) なので
    # 不明扱い (None) にする。長寿猫の 22歳(264ヶ月) 等は保持できる。
    _MAX_PLAUSIBLE_AGE_MONTHS: int = 360

    @staticmethod
    def _reject_implausible_age(months: int) -> int | None:
        """生物学的に有り得ない高齢は誤パースとして None を返す。"""
        if months > DataNormalizer._MAX_PLAUSIBLE_AGE_MONTHS:
            return None
        return months

    # DB の animals.color が VARCHAR(100) のため、これを超える文字列が
    # 流入すると INSERT 失敗 → トランザクション全体 rollback で 1 サイト分が
    # 全滅する。adapter 側のフィールド誤割当 (例: 横須賀の「特徴」欄に
    # 長文説明が入るケース) のセーフネットとしてこの長さで切り捨てる。
    _COLOR_MAX_LEN: int = 100
    # animals.size VARCHAR(50)
    _SIZE_MAX_LEN: int = 50
    # animals.phone VARCHAR(20)
    _PHONE_MAX_LEN: int = 20

    @staticmethod
    def _cap_color(raw_color: str | None) -> str | None:
        """color を DB 制約に収まる長さで返す。空/長さ 0 は None。"""
        if not raw_color:
            return None
        text = raw_color.strip()
        if not text:
            return None
        if len(text) > DataNormalizer._COLOR_MAX_LEN:
            return text[: DataNormalizer._COLOR_MAX_LEN]
        return text

    @staticmethod
    def _cap_size(raw_size: str | None) -> str | None:
        """size を体格の正規形 (小型/中型/大型) に揃えつつ DB 制約に収める。

        実データには (a) 単漢字 小/中/大、(b) 体重・タブ混入
        ("小型\\t\\t（7.7kg）")、(c) 体重情報のみ ("0.3kg",
        "(現在の体重：…Kg)") が混在する。UI のフィルタを統一するため:

        1. 空白 (タブ/全角含む) を畳んで体格語を抽出 → 小型/中型/大型 に正規化
        2. 体格語が無く体重情報のみなら size ではないので None
        3. それ以外の未知表記は長さ制限のみ掛けて温存 (データ消失防止)
        """
        if not raw_size:
            return None
        text = re.sub(r"\s+", " ", raw_size).strip()
        if not text:
            return None

        # 括弧 (全角/半角・入れ子) を繰り返し除去して体重等の付随情報を落とす
        core = text
        prev = None
        while prev != core:
            prev = core
            core = re.sub(r"[（(][^（()）]*[）)]", "", core)
        core = re.sub(r"\s+", "", core)

        # 体格語の正規化 (小/中/大 は単独でも可)。互いに排他なので順に判定。
        if "大型" in core or "大きめ" in core or core == "大":
            return "大型"
        if "中型" in core or core == "中":
            return "中型"
        if "小型" in core or "超小" in core or core == "小":
            return "小型"

        # 体格語が無く体重情報のみ → size ではないので捨てる
        if "体重" in text or re.search(r"\d+(?:[.．]\d+)?\s*(?:kg|㎏|キロ)", text, re.IGNORECASE):
            return None

        # 未知表記は温存 (長さ制限のみ)
        if len(text) > DataNormalizer._SIZE_MAX_LEN:
            return text[: DataNormalizer._SIZE_MAX_LEN]
        return text

    @staticmethod
    def _normalize_age(raw_age: str) -> int | None:
        """
        年齢を月単位の数値に変換

        対応形式:
        - "N歳M[ヶか]月" → N * 12 + M
        - "N歳" → N * 12
        - "Nヶ月", "Nか月", "Nカ月", "Nケ月" → N
        - "N年" → N * 12
        - 生年月日 (YYYY-MM-DD, YYYY/MM/DD, YYYY年M月D日, R{N}.M.D, 令和N年M月D日)
          → 今日との差分を月単位で返す
        - 不明・無効な値 → None

        Args:
            raw_age: 正規化前の年齢

        Returns:
            Optional[int]: 月単位の年齢、不明の場合は None
        """
        age_str = raw_age.strip()

        # 不明パターンのチェック
        if age_str in DataNormalizer._UNKNOWN_PATTERNS:
            return None

        # 各パスは月数を months に代入し、末尾で妥当域チェックを一括適用する。
        months: int | None = None

        # 1. 生年月日パターンを最初にチェック（"令和N年M月D日" の "N年" が
        #    "N年=Nヶ月*12" として誤マッチするのを避けるため）
        today = DataNormalizer._today()
        birth = DataNormalizer._parse_birth_date(age_str)
        if birth is not None:
            months = DataNormalizer._months_between(birth, today)
        # 2. "N歳M[ヶかカケ]月" の組み合わせ（年/月の合計）
        elif match := re.search(r"(\d+)\s*歳\s*(\d+)\s*[ヶかカケ]月", age_str):
            months = int(match.group(1)) * 12 + int(match.group(2))
        # 3. "N歳" のパターン
        elif match := re.search(r"(\d+)\s*歳", age_str):
            months = int(match.group(1)) * 12
        # 4. "Nヶ月", "Nか月", "Nカ月", "Nケ月" のパターン
        elif match := re.search(r"(\d+)\s*[ヶかカケ]月", age_str):
            months = int(match.group(1))
        # 5. "N年" のパターン (4桁年号 "YYYY年" や "令和N年" を除外)
        elif not re.search(r"\d{4}年|令和\d+年", age_str):
            if match := re.search(r"(\d+)\s*年", age_str):
                months = int(match.group(1)) * 12

        if months is None:
            return None
        return DataNormalizer._reject_implausible_age(months)

    @staticmethod
    def _parse_birth_date(text: str) -> date | None:
        """生年月日表記をパースして date を返す。失敗したら None。

        対応形式: YYYY-MM-DD / YYYY/MM/DD / YYYY年M月D日 / R{N}.M.D / 令和N年M月D日
        """
        # YYYY-MM-DD
        match = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", text)
        if match:
            try:
                return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
            except ValueError:
                return None

        # YYYY/MM/DD
        match = re.search(r"(\d{4})/(\d{1,2})/(\d{1,2})", text)
        if match:
            try:
                return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
            except ValueError:
                return None

        # YYYY年M月D日
        match = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", text)
        if match:
            try:
                return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
            except ValueError:
                return None

        # 令和N年M月D日
        match = re.search(r"令和(\d+)年(\d{1,2})月(\d{1,2})日", text)
        if match:
            try:
                year = 2018 + int(match.group(1))
                return date(year, int(match.group(2)), int(match.group(3)))
            except ValueError:
                return None

        # R{N}.M.D（R5.11.30 等）
        match = re.search(r"R(\d{1,2})[.\s　](\d{1,2})[./](\d{1,2})", text)
        if match:
            try:
                year = 2018 + int(match.group(1))
                return date(year, int(match.group(2)), int(match.group(3)))
            except ValueError:
                return None

        return None

    @staticmethod
    def _normalize_date(raw_date: str) -> str:
        """
        日付を ISO 8601 形式 (YYYY-MM-DD) に変換

        対応形式:
        - "令和N年M月D日" → 西暦変換 → YYYY-MM-DD
        - "YYYY/MM/DD" → YYYY-MM-DD
        - "YYYY-MM-DD" → そのまま
        - "YYYY年M月D日" → YYYY-MM-DD

        Args:
            raw_date: 正規化前の日付

        Returns:
            str: ISO 8601 形式の日付 (YYYY-MM-DD)

        Raises:
            ValueError: 無効な日付形式の場合
        """
        date_str = raw_date.strip()

        if not date_str:
            raise ValueError("日付が空です")

        # すでに ISO 8601 形式の場合
        if re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
            # 妥当性チェック
            datetime.strptime(date_str, "%Y-%m-%d")
            return date_str

        # 令和N年M月D日 のパターン
        match = re.search(r"令和(\d+)年(\d+)月(\d+)日", date_str)
        if match:
            reiwa_year = int(match.group(1))
            month = int(match.group(2))
            day = int(match.group(3))

            # 令和元年 = 2019年5月1日開始。「令和0年」は存在しないので拒否
            # (旧実装は 2018 年に変換していたが、これは元号開始前のため不正)
            if reiwa_year < 1:
                raise ValueError(f"令和0年は存在しません: {raw_date}")

            # 令和N年 = 2018 + N (令和1年 = 2019年)
            year = 2018 + reiwa_year

            # 日付の妥当性チェック
            date_obj = datetime(year, month, day).date()
            return date_obj.strftime("%Y-%m-%d")

        # RN.M/D または RN　M/D または RN M/D のパターン
        # （例: R3.11/16, R6　9/27, R6 9/27, R7　8/27　午前10時頃）
        match = re.search(r"R(\d{1,2})[.\s\u3000](\d{1,2})/(\d{1,2})", date_str)
        if match:
            reiwa_year = int(match.group(1))
            month = int(match.group(2))
            day = int(match.group(3))

            if reiwa_year < 1:
                raise ValueError(f"令和0年は存在しません: {raw_date}")

            # 令和N年 = 2018 + N
            year = 2018 + reiwa_year

            # 日付の妥当性チェック
            date_obj = datetime(year, month, day).date()
            return date_obj.strftime("%Y-%m-%d")

        # RN.M.D のパターン (例: R8.5.14（木曜日）, R6.10.21)
        # 横須賀市 doubutu サイト等で使われる
        match = re.search(r"R(\d{1,2})\.(\d{1,2})\.(\d{1,2})", date_str)
        if match:
            reiwa_year = int(match.group(1))
            month = int(match.group(2))
            day = int(match.group(3))
            if reiwa_year < 1:
                raise ValueError(f"令和0年は存在しません: {raw_date}")
            year = 2018 + reiwa_year
            date_obj = datetime(year, month, day).date()
            return date_obj.strftime("%Y-%m-%d")

        # M月D日 のパターン（年なし、当年を補完）。京都市ペットラブ等で使われる。
        # 全角数字を含む場合は半角に正規化してから判定する。
        normalized = date_str.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
        match = re.search(r"^(\d{1,2})月(\d{1,2})日", normalized)
        if match:
            month = int(match.group(1))
            day = int(match.group(2))
            try:
                date_obj = DataNormalizer._infer_yearless_date(month, day)
                return date_obj.strftime("%Y-%m-%d")
            except ValueError:
                pass

        # YYYY/MM/DD のパターン
        match = re.search(r"(\d{4})/(\d{1,2})/(\d{1,2})", date_str)
        if match:
            year = int(match.group(1))
            month = int(match.group(2))
            day = int(match.group(3))

            # 日付の妥当性チェック
            date_obj = datetime(year, month, day).date()
            return date_obj.strftime("%Y-%m-%d")

        # YYYY年M月D日 のパターン
        match = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", date_str)
        if match:
            year = int(match.group(1))
            month = int(match.group(2))
            day = int(match.group(3))

            # 日付の妥当性チェック
            date_obj = datetime(year, month, day).date()
            return date_obj.strftime("%Y-%m-%d")

        # M/D のパターン（年なし、当年を補完）
        # （例: 4/30, 6/17, 1/31　午前10時頃）
        match = re.search(r"^(\d{1,2})/(\d{1,2})", date_str)
        if match:
            month = int(match.group(1))
            day = int(match.group(2))
            date_obj = DataNormalizer._infer_yearless_date(month, day)
            return date_obj.strftime("%Y-%m-%d")

        # マッチしない場合はエラー
        raise ValueError(f"無効な日付形式: {raw_date}")

    @staticmethod
    def _infer_yearless_date(month: int, day: int) -> date:
        """年なし表記 (M月D日 / M/D) から date を構築する。

        単純に `datetime.now().year` で補完すると、12月末収集時にサイト上の
        翌1月日付が「今年1月」(過去) として保存されてしまい、アーカイブの
        時系列整合性が崩れる (Codex 監査 MEDIUM #6)。

        補完日付が今日から見て遠い未来 (30日超) なら、それは「前年の同月日」
        と解釈するのが自然 (保護動物サイトは通常「最近の収容情報」を出す)。

        Args:
            month: 1-12
            day: 1-31

        Returns:
            date: 補完済み日付

        Raises:
            ValueError: 不正な月日 (例: 2/30, 13月)
        """
        today = DataNormalizer._today()
        year = today.year
        candidate = date(year, month, day)
        # 保護動物の収容日は通常「過去〜現在」。今日より大きく未来 (30日超) の
        # 場合は前年補完が正解 (例: 5月収集時に "12/1" は今年 12/1 ではなく
        # 去年 12/1 を指すのが自然)。
        if (candidate - today).days > 30:
            candidate = date(year - 1, month, day)
        return candidate

    @staticmethod
    def _normalize_phone(raw_phone: str) -> str:
        """
        電話番号をハイフン含む標準形式に正規化

        対応形式:
        - 10桁 (0XXXXXXXXX) → 市外局番に応じて適切に分割
          - 03, 06 など2桁市外局番 → 0X-XXXX-XXXX
          - 088 など3桁市外局番 → 0XX-XXX-XXXX
        - 11桁 (0XXXXXXXXXXX) → 0XX-XXXX-XXXX
        - すでにハイフン付き → 括弧を削除して返す
        - 括弧付き (0XX)XXX-XXXX → 0XX-XXX-XXXX

        Args:
            raw_phone: 正規化前の電話番号

        Returns:
            str: ハイフン付き電話番号
        """
        phone_str = raw_phone.strip()

        # 括弧を削除
        phone_str = phone_str.replace("(", "").replace(")", "")

        # すでにハイフンが含まれている場合
        if "-" in phone_str:
            # 数字のみを抽出して再フォーマット
            digits = re.sub(r"\D", "", phone_str)
        else:
            # 数字のみを抽出
            digits = re.sub(r"\D", "", phone_str)

        # 10桁の場合: 市外局番に応じて分割
        if len(digits) == 10:
            # 2桁市外局番 (03, 04, 05, 06 など)
            if digits[0:2] in ["03", "04", "05", "06"]:
                return f"{digits[0:2]}-{digits[2:6]}-{digits[6:10]}"
            # 3桁市外局番 (088, 090 など)
            else:
                return f"{digits[0:3]}-{digits[3:6]}-{digits[6:10]}"

        # 11桁の場合: 0XX-XXXX-XXXX
        if len(digits) == 11:
            return f"{digits[0:3]}-{digits[3:7]}-{digits[7:11]}"

        # 無効な桁数の場合は数字のみを返す。
        # 数字が 0 桁 (例: 「お問い合わせフォームから」「https://...」が phone セルに
        # 流入したケース) の場合に元の長文 phone_str を返すと、DB の phone VARCHAR(20)
        # を超過して INSERT 失敗 → トランザクション全体 rollback でサイト全滅する。
        # 数字無しは空文字 (= 後段で None に変換される) を返す。
        if not digits:
            return ""
        return digits[: DataNormalizer._PHONE_MAX_LEN]
