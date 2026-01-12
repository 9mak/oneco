"""
データ正規化ロジック

自治体サイトから抽出した生データ (RawAnimalData) を統一スキーマ (AnimalData) に変換します。
動物種別、性別、年齢、日付、電話番号などの正規化ルールを提供します。
"""

import re
from typing import Optional
from datetime import datetime

from .models import RawAnimalData, AnimalData


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

        # 正規化処理
        return AnimalData(
            species=DataNormalizer._normalize_species(raw_data.species),
            sex=DataNormalizer._normalize_sex(raw_data.sex),
            age_months=DataNormalizer._normalize_age(raw_data.age),
            color=raw_data.color if raw_data.color else None,
            size=raw_data.size if raw_data.size else None,
            shelter_date=datetime.strptime(
                DataNormalizer._normalize_date(raw_data.shelter_date), "%Y-%m-%d"
            ).date(),
            location=raw_data.location if raw_data.location else None,
            phone=DataNormalizer._normalize_phone(raw_data.phone),
            image_urls=image_urls_raw,
            source_url=raw_data.source_url
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
    def _normalize_age(raw_age: str) -> Optional[int]:
        """
        年齢を月単位の数値に変換

        対応形式:
        - "N歳" → N * 12
        - "Nヶ月", "Nか月", "Nカ月", "Nケ月" → N
        - "N年" → N * 12
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

        # "N歳" のパターン
        match = re.search(r'(\d+)\s*歳', age_str)
        if match:
            years = int(match.group(1))
            return years * 12

        # "Nヶ月", "Nか月", "Nカ月", "Nケ月" のパターン
        match = re.search(r'(\d+)\s*[ヶかカケ]月', age_str)
        if match:
            months = int(match.group(1))
            return months

        # "N年" のパターン
        match = re.search(r'(\d+)\s*年', age_str)
        if match:
            years = int(match.group(1))
            return years * 12

        # マッチしない場合は None
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
        if re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
            # 妥当性チェック
            datetime.strptime(date_str, "%Y-%m-%d")
            return date_str

        # 令和N年M月D日 のパターン
        match = re.search(r'令和(\d+)年(\d+)月(\d+)日', date_str)
        if match:
            reiwa_year = int(match.group(1))
            month = int(match.group(2))
            day = int(match.group(3))

            # 令和元年 = 2019年5月1日開始
            # 令和N年 = 2018 + N (簡易計算: 令和1年 = 2019年)
            year = 2018 + reiwa_year

            # 日付の妥当性チェック
            date_obj = datetime(year, month, day).date()
            return date_obj.strftime("%Y-%m-%d")

        # RN.M/D のパターン（例: R3.11/16 → 2021-11-16, R8.1/9 → 2026-01-09）
        match = re.search(r'R(\d{1,2})\.(\d{1,2})/(\d{1,2})', date_str)
        if match:
            reiwa_year = int(match.group(1))
            month = int(match.group(2))
            day = int(match.group(3))

            # 令和N年 = 2018 + N
            year = 2018 + reiwa_year

            # 日付の妥当性チェック
            date_obj = datetime(year, month, day).date()
            return date_obj.strftime("%Y-%m-%d")

        # YYYY/MM/DD のパターン
        match = re.search(r'(\d{4})/(\d{1,2})/(\d{1,2})', date_str)
        if match:
            year = int(match.group(1))
            month = int(match.group(2))
            day = int(match.group(3))

            # 日付の妥当性チェック
            date_obj = datetime(year, month, day).date()
            return date_obj.strftime("%Y-%m-%d")

        # YYYY年M月D日 のパターン
        match = re.search(r'(\d{4})年(\d{1,2})月(\d{1,2})日', date_str)
        if match:
            year = int(match.group(1))
            month = int(match.group(2))
            day = int(match.group(3))

            # 日付の妥当性チェック
            date_obj = datetime(year, month, day).date()
            return date_obj.strftime("%Y-%m-%d")

        # マッチしない場合はエラー
        raise ValueError(f"無効な日付形式: {raw_date}")

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
            digits = re.sub(r'\D', '', phone_str)
        else:
            # 数字のみを抽出
            digits = re.sub(r'\D', '', phone_str)

        # 10桁の場合: 市外局番に応じて分割
        if len(digits) == 10:
            # 2桁市外局番 (03, 04, 05, 06 など)
            if digits[0:2] in ['03', '04', '05', '06']:
                return f"{digits[0:2]}-{digits[2:6]}-{digits[6:10]}"
            # 3桁市外局番 (088, 090 など)
            else:
                return f"{digits[0:3]}-{digits[3:6]}-{digits[6:10]}"

        # 11桁の場合: 0XX-XXXX-XXXX
        if len(digits) == 11:
            return f"{digits[0:3]}-{digits[3:7]}-{digits[7:11]}"

        # 無効な桁数の場合は数字のみを返す (元のphone_strではなくdigits)
        return digits if digits else phone_str
