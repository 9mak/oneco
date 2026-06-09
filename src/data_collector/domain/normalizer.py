"""
データ正規化ロジック

自治体サイトから抽出した生データ (RawAnimalData) を統一スキーマ (AnimalData) に変換します。
動物種別、性別、年齢、日付、電話番号などの正規化ルールを提供します。
"""

import logging
import re
from datetime import date, datetime

from ..utils.prefecture import infer_prefecture_from_url
from .models import AnimalData, RawAnimalData

logger = logging.getLogger(__name__)


class DataNormalizer:
    """
    データ正規化クラス

    自治体ごとに異なる形式のデータを統一スキーマに正規化する静的メソッドを提供します。
    """

    # 正規化パターン定義
    _SPECIES_DOG_PATTERNS = ["犬", "いぬ", "イヌ", "inu", "dog"]
    _SPECIES_CAT_PATTERNS = ["猫", "ねこ", "ネコ", "neko", "cat"]

    # 牡 / 牝 は一部自治体の旧表記。取りこぼすと sex 全件「不明」になりフィルタが死ぬ。
    _SEX_MALE_PATTERNS = ["男の子", "オトコノコ", "オス", "おす", "雄", "牡", "♂", "male"]
    _SEX_FEMALE_PATTERNS = ["女の子", "オンナノコ", "メス", "めす", "雌", "牝", "♀", "female"]

    _UNKNOWN_PATTERNS = ["不明", "?", "？", "unknown", ""]

    # 定性的年齢表記 → 代表月数 (環境省ガイドライン目安)。
    # koshigaya 等の譲渡動物表で「中齢」「若齢」のような独自分類が出現する。
    # 範囲の中央値を採用し、誤差は許容 (ID 等の誤抽出ではないので保持を優先)。
    _AGE_CLASS_MONTHS: dict[str, int] = {
        "幼齢": 3,  # 〜半年
        "若齢": 12,  # 0.5〜2歳
        "中齢": 60,  # 2〜7歳
        "高齢": 120,  # 7歳〜
    }

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
        # AnimalData.image_urls は HttpUrl 制約のため、data:/javascript:/相対パス等が
        # 1 件でも混入すると Pydantic の ValidationError で動物レコードごと欠落する。
        # http(s) のみに濾過してレコード全損を防ぐ。
        image_urls_raw = DataNormalizer._filter_valid_image_urls(raw_data.image_urls)

        # shelter_date は不明 / 解析不能な場合「データ取得日」をフォールバックに使う。
        # 譲渡カテゴリページや未対応フォーマットの日付表記でも AnimalData 化失敗で
        # 全件落ちることを防ぐためのセーフネット。
        # ただし「静かに丸めて誤データを混入」する盲点を避けるため、
        # フォールバック発生時は WARNING ログを出して可視化する。
        today = DataNormalizer._today()
        raw_shelter = (raw_data.shelter_date or "").strip()
        shelter_date_str = ""
        if raw_shelter:
            try:
                shelter_date_str = DataNormalizer._normalize_date(raw_shelter)
            except ValueError:
                shelter_date_str = ""
        if not shelter_date_str:
            if raw_shelter:
                # 入力はあるが解析失敗 — adapter のフォーマット対応不足の可能性
                logger.warning(
                    "shelter_date parse failed, falling back to today",
                    extra={
                        "raw_shelter_date": raw_shelter,
                        "source_url": raw_data.source_url,
                    },
                )
            shelter_date_str = today.strftime("%Y-%m-%d")
        else:
            # 収容日/「いなくなった日時」が未来日になるのは物理的に不正
            # (長崎 animal-net の実例)。収集日 (今日) にフォールバックして
            # アーカイブの時系列整合性を守る。
            parsed_shelter = datetime.strptime(shelter_date_str, "%Y-%m-%d").date()
            if parsed_shelter > today:
                logger.warning(
                    "shelter_date is in future, clamping to today",
                    extra={
                        "raw_shelter_date": raw_shelter,
                        "parsed_shelter_date": shelter_date_str,
                        "source_url": raw_data.source_url,
                    },
                )
                shelter_date_str = today.strftime("%Y-%m-%d")

        # 所在地: 迷子(lost)は飼い主の生活圏を番地まで晒さないよう粗粒度化する。
        location = raw_data.location if raw_data.location else "不明"
        if raw_data.category == "lost":
            location = DataNormalizer._coarsen_location(location)

        # 正規化処理
        return AnimalData(
            species=DataNormalizer._normalize_species(raw_data.species),
            sex=DataNormalizer._normalize_sex(raw_data.sex),
            age_months=DataNormalizer._normalize_age(raw_data.age),
            color=DataNormalizer._cap_color(raw_data.color),
            size=DataNormalizer._cap_size(raw_data.size),
            shelter_date=datetime.strptime(shelter_date_str, "%Y-%m-%d").date(),
            location=location,
            prefecture=infer_prefecture_from_url(raw_data.source_url),
            # 携帯/IP 番号(発見者の個人電話)は公開 phone に載せない
            phone=DataNormalizer._sanitize_public_phone(
                DataNormalizer._normalize_phone(raw_data.phone)
            )
            or None,
            image_urls=image_urls_raw,
            source_url=raw_data.source_url,
            category=raw_data.category,
            # 個体識別: 品種 (Slice 1)。トリム+長さ丸めのみ (PII 非適用の構造化値)。
            breed=DataNormalizer._cap_text(raw_data.breed, DataNormalizer._BREED_MAX_LEN),
            # 個体識別: 性格・特徴 (Slice 2)。自由文のため電話/メールを伏字化 + 長さ丸め。
            description=DataNormalizer._normalize_description(raw_data.description),
        )

    @staticmethod
    def _filter_valid_image_urls(urls: list[str] | None) -> list[str]:
        """http(s) スキームの画像 URL のみを残し、重複を順序保ち除去する。

        AnimalData.image_urls は HttpUrl 制約。data:/javascript:/相対パス等を
        Pydantic に渡すと ValidationError でレコードごと欠落するため、ここで
        防御する (全アダプター共通)。
        """
        if not urls:
            return []
        seen: set[str] = set()
        valid: list[str] = []
        for u in urls:
            if not isinstance(u, str):
                continue
            candidate = u.strip()
            if not (candidate.startswith("http://") or candidate.startswith("https://")):
                continue
            if candidate in seen:
                continue
            seen.add(candidate)
            valid.append(candidate)
        return valid

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

    # 個体識別フィールドの長さ上限。ORM の VARCHAR と厳密一致させること
    # (不一致は丸めをすり抜けて INSERT 失敗 → 1 サイト全損)。
    # animals.breed VARCHAR(50) / name VARCHAR(100) / management_number VARCHAR(50)
    _BREED_MAX_LEN: int = 50
    _NAME_MAX_LEN: int = 100
    _MANAGEMENT_NUMBER_MAX_LEN: int = 50
    # description は Text 列だが、自由文の暴走防止に上限を設ける
    _DESCRIPTION_MAX_LEN: int = 2000

    # PII (個人情報) 検出パターン。自治体サイトの「特徴」「コメント」自由記述に
    # 飼い主や保護者の個人連絡先が混入するケースがあり、公開リスクとなる。
    # color など自由テキスト由来のフィールドで以下を ███ に置換する:
    # - 電話番号 (半角/全角ハイフン、ハイフン無し 10/11 桁含む)
    # - メールアドレス
    _PII_PHONE_RE = re.compile(
        r"(?:\d|[０-９]){2,4}\s*[-－‐ー]\s*(?:\d|[０-９]){2,4}\s*[-－‐ー]\s*(?:\d|[０-９]){3,4}"
        r"|0[5789]0\d{8}"  # ハイフン無し携帯/IP 11桁
        r"|0\d{9}"  # ハイフン無し固定電話 10桁
    )
    _PII_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
    _PII_REPLACEMENT = "███"

    @staticmethod
    def _redact_pii(text: str) -> str:
        """テキストから電話番号・メールアドレスを ███ に置換する"""
        text = DataNormalizer._PII_PHONE_RE.sub(DataNormalizer._PII_REPLACEMENT, text)
        text = DataNormalizer._PII_EMAIL_RE.sub(DataNormalizer._PII_REPLACEMENT, text)
        return text

    @staticmethod
    def _cap_text(raw: str | None, max_len: int) -> str | None:
        """自由値フィールドをトリムし、空は None、上限超過は丸めて返す（PII 非適用）。

        breed / name / management_number 等の短い識別値に使う
        （_cap_color から PII 伏字行を除いた汎用版）。
        """
        if not raw:
            return None
        text = raw.strip()
        if not text:
            return None
        if len(text) > max_len:
            return text[:max_len]
        return text

    @staticmethod
    def _normalize_description(raw: str | None) -> str | None:
        """性格・特徴の自由記述を正規化する。

        空は None、電話番号/メールを _redact_pii で伏字化し、上限超過は丸める。
        氏名(人名)は伏字対象外（形態素解析を要するため本仕様の非対象）。
        伏字を丸めの前に行い、伏字後の文字数で上限判定する。
        """
        if not raw:
            return None
        text = raw.strip()
        if not text:
            return None
        text = DataNormalizer._redact_pii(text)
        if len(text) > DataNormalizer._DESCRIPTION_MAX_LEN:
            return text[: DataNormalizer._DESCRIPTION_MAX_LEN]
        return text

    @staticmethod
    def _cap_color(raw_color: str | None) -> str | None:
        """color を DB 制約に収まる長さで返し、PII を除去する。空/長さ 0 は None。"""
        if not raw_color:
            return None
        text = raw_color.strip()
        if not text:
            return None
        # PII (電話番号・メール) を ███ に置換
        text = DataNormalizer._redact_pii(text)
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
        - "N歳M[ヶかヵ]月" → N * 12 + M
        - "N歳" / "N才" → N * 12 ("才" は歳の代用字。"くらい/以上/前後/半"
          等の付随表現や "2~3才" の範囲表記があっても数値を拾う)
        - "Nヶ月", "Nか月", "Nカ月", "Nケ月", "Nヵ月" → N
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

        # 全角数字を半角に正規化 (推定６週齢, ２歳 等)
        age_str = age_str.translate(str.maketrans("０１２３４５６７８９", "0123456789"))

        # "才" は "歳" の代用字 (長崎・和歌山・旭川あにまある 等で多用)。
        # 歳に正規化して以降の年齢パターンに乗せる。"13才くらい"/"１０才以上"
        # のような付随表現は re.search が数値+歳を拾うため自然に無視される。
        age_str = age_str.replace("才", "歳")

        # 各パスは月数を months に代入し、末尾で妥当域チェックを一括適用する。
        months: int | None = None

        today = DataNormalizer._today()

        # 1. 明示的な年齢表記 (N歳M月 / N歳 / Nヶ月 / N週齢 / 定性表記) を最優先する。
        #    収容日・掲載日 (例: "3歳 2026-05-01収容") が併記されていても、
        #    その日付を生年月日と誤認して月齢を再計算しない (旧実装の age 化けバグ)。
        if match := re.search(r"(\d+)\s*歳\s*(\d+)\s*[ヶかカケヵ]月", age_str):
            months = int(match.group(1)) * 12 + int(match.group(2))
        elif match := re.search(r"(\d+)\s*歳", age_str):
            months = int(match.group(1)) * 12
        elif match := re.search(r"(\d+)\s*[ヶかカケヵ]月", age_str):
            months = int(match.group(1))
        # 2. "N週齢" / "推定N週齢" (koshigaya 等の譲渡動物表)
        #    1ヶ月 ≈ 4週として整数除算 (端数切り捨て)
        elif match := re.search(r"(\d+)\s*週齢", age_str):
            months = int(match.group(1)) // 4
        # 3. 定性的年齢表記 (幼齢/若齢/中齢/高齢) — 環境省ガイドライン目安
        elif months_qualitative := DataNormalizer._AGE_CLASS_MONTHS.get(age_str):
            months = months_qualitative
        else:
            # 4. 明示年齢が無い場合のみ生年月日から月齢を計算する。
            #    "令和N年M月D日" の "N年" を Nヶ月と誤マッチさせない。
            birth = DataNormalizer._parse_birth_date(age_str)
            if birth is not None:
                months = DataNormalizer._months_between(birth, today)
            # 5. "YYYY年M月" / "YYYY年M月頃[生まれ]" (日なし) — 日を 1 仮定
            elif match := re.search(r"(\d{4})年(\d{1,2})月", age_str):
                try:
                    birth_year_month = date(int(match.group(1)), int(match.group(2)), 1)
                except ValueError:
                    pass
                else:
                    if birth_year_month <= today:
                        months = DataNormalizer._months_between(birth_year_month, today)
            # 6. "令和N年M月" (日なし、頃つき可) も日 1 仮定
            elif match := re.search(r"令和(\d+)年(\d{1,2})月", age_str):
                try:
                    year = 2018 + int(match.group(1))
                    birth_reiwa_month = date(year, int(match.group(2)), 1)
                except ValueError:
                    pass
                else:
                    if birth_reiwa_month <= today:
                        months = DataNormalizer._months_between(birth_reiwa_month, today)
            # 7. "YYYY年" のみ (4桁年号、月日なし) — 1月1日仮定で月数化
            #    kitakyushu 譲渡犬テーブルが「2017年」のみで日が無いケースの救済。
            elif match := re.search(r"(\d{4})年", age_str):
                try:
                    birth_year_only = date(int(match.group(1)), 1, 1)
                except ValueError:
                    pass
                else:
                    if birth_year_only <= today:
                        months = DataNormalizer._months_between(birth_year_only, today)
            # 8. "N年" のパターン (4桁年号 "YYYY年" や "令和N年" を除外)
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
        - 全角数字・全角ハイフン・括弧 → 半角に正規化
        - 「内線」「ext.」「(代表)」等の付帯情報は除去（13桁化を防ぐ）

        桁数が想定外（9桁未満や12桁以上）の場合は空文字を返す。旧実装は部分文字列を
        返していたが、内線数字が混入した「088-826-2364内線123」が「08882623641」のような
        不正データになる原因だったため、安全側に倒す。

        Args:
            raw_phone: 正規化前の電話番号

        Returns:
            str: ハイフン付き電話番号、または空文字列
        """
        phone_str = raw_phone.strip()

        # 全角数字 → 半角数字
        phone_str = phone_str.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
        # 全角・各種ハイフン → ASCII ハイフン（ー(長音)、－、―、‐、−、–、—）
        phone_str = re.sub(r"[ー－―‐−–—]", "-", phone_str)
        # 全角・半角括弧を削除
        phone_str = re.sub(r"[()（）]", "", phone_str)

        # 内線・付帯情報以降を切り捨て（混入数字が桁数を狂わせるのを防ぐ）
        for kw in ("内線", "ext.", "ext", "EXT", "Ext", "代表", "（", "(", "／", "/"):
            idx = phone_str.find(kw)
            if idx > 0:
                phone_str = phone_str[:idx]
                break

        # 数字のみを抽出
        digits = re.sub(r"\D", "", phone_str)

        # 桁数が想定外 (9桁以下や12桁以上) は空文字。
        # 旧実装は digits[:20] で部分文字列を返していたが、これは内線混入時の
        # 13桁化等の不正データの原因。Codex リリースレビュー I-10 で指摘。
        if len(digits) not in (10, 11):
            return ""

        # 入力が既に妥当な区切りでハイフン済みなら、剥がして再分割せず温存する。
        # 実データの多くは正しくハイフン済み ('045-211-2000')。数字に潰して市外局番
        # 長を推定し直すと 04x の 2桁(柏 04-7190)/3桁(横浜 045) の区別がつかず誤番号に
        # なる。各部が数字・先頭 0・連結が digits と一致する 3 分割は原本の区切りを信頼する。
        hyphen_parts = phone_str.split("-")
        if (
            len(hyphen_parts) == 3
            and all(p.isdigit() for p in hyphen_parts)
            and hyphen_parts[0].startswith("0")
            and "".join(hyphen_parts) == digits
        ):
            return "-".join(hyphen_parts)

        # ハイフン無し / 不正な区切り → 桁数と市外局番から分割を推定する。
        if len(digits) == 10:
            # 実際の 2桁市外局番は 03(東京23区)・06(大阪市) のみ。04x/05x で始まる
            # 川崎044・横浜045・さいたま048・名古屋052 等は 3桁市外局番なので、
            # ここで 2桁扱いしてはいけない（旧実装はこれらを誤分割していた）。
            if digits[0:2] in ("03", "06"):
                return f"{digits[0:2]}-{digits[2:6]}-{digits[6:10]}"
            # それ以外の10桁固定電話は3桁市外局番として分割 (0XX-XXX-XXXX)
            return f"{digits[0:3]}-{digits[3:6]}-{digits[6:10]}"

        # 11桁 (携帯/IP/一部固定): 0XX-XXXX-XXXX
        return f"{digits[0:3]}-{digits[3:7]}-{digits[7:11]}"

    # 公開ポータルに載せない携帯/IP 電話の市外局番プレフィックス
    _PERSONAL_PHONE_PREFIXES = ("070", "080", "090", "050")

    @staticmethod
    def _sanitize_public_phone(phone: str) -> str:
        """公開ポータルに載せない個人電話を除去する。

        070/080/090(携帯)・050(IP) は個人の番号である可能性が高く、発見者・市民の
        個人情報を晒すため公開しない（空文字で落とす）。施設の連絡先は固定電話であり、
        元ページへのリンクは別途残るので連絡手段が完全に失われるわけではない。
        """
        digits = re.sub(r"\D", "", phone)
        if len(digits) == 11 and digits[:3] in DataNormalizer._PERSONAL_PHONE_PREFIXES:
            return ""
        return phone

    # 住所のブロックレベル(丁目以下・付近等)を検出する正規表現
    _CHOME_RE = re.compile(r"[0-9０-９一二三四五六七八九十]+\s*丁目")
    _LANDMARK_RE = re.compile(r"付近|周辺|地内|交差点|住宅街")

    @staticmethod
    def _coarsen_location(location: str) -> str:
        """所在地を町名レベルに粗粒度化し、丁目以下・付近/交差点等のブロックレベル
        詳細を除去する。迷子(lost)の所在地が飼い主の生活圏を番地まで晒すのを防ぐ。

        住所マーカー(丁目/付近等)が無い値（管理番号・施設名・市区町村のみ）は壊さずに
        そのまま返す（lost の location に管理番号が混入する実データがあるため）。
        """
        cuts = []
        m = DataNormalizer._CHOME_RE.search(location)
        if m:
            cuts.append(m.start())
        m = DataNormalizer._LANDMARK_RE.search(location)
        if m:
            cuts.append(m.start())
        if not cuts:
            return location
        coarse = location[: min(cuts)].rstrip(" 　-－・,、")
        return coarse.strip() or location
