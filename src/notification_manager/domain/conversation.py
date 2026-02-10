"""
notification-manager 対話機能

このモジュールはLINEでの対話フロー制御を提供します:
- ConversationHandler: コマンド解析、状態管理、入力処理
- ConversationState: 対話状態の定義
- Command: 認識可能なコマンドの定義

Requirements: 1.2, 1.5, 1.6, 1.7
"""

import re
import logging
from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from src.notification_manager.domain.models import NotificationPreferenceInput

logger = logging.getLogger(__name__)

# 都道府県リスト（バリデーション用）
PREFECTURES = [
    "北海道", "青森県", "岩手県", "宮城県", "秋田県", "山形県", "福島県",
    "茨城県", "栃木県", "群馬県", "埼玉県", "千葉県", "東京都", "神奈川県",
    "新潟県", "富山県", "石川県", "福井県", "山梨県", "長野県",
    "岐阜県", "静岡県", "愛知県", "三重県",
    "滋賀県", "京都府", "大阪府", "兵庫県", "奈良県", "和歌山県",
    "鳥取県", "島根県", "岡山県", "広島県", "山口県",
    "徳島県", "香川県", "愛媛県", "高知県",
    "福岡県", "佐賀県", "長崎県", "熊本県", "大分県", "宮崎県", "鹿児島県", "沖縄県",
]


class Command(Enum):
    """認識可能なコマンド"""

    SETTINGS = auto()  # 設定開始
    CHANGE = auto()    # 条件変更
    STOP = auto()      # 通知停止
    RESUME = auto()    # 通知再開
    STATUS = auto()    # 現在の設定確認
    HELP = auto()      # ヘルプ


class ConversationState(Enum):
    """対話状態"""

    IDLE = auto()                 # 待機中
    AWAITING_SPECIES = auto()     # 種別待ち
    AWAITING_PREFECTURES = auto() # 都道府県待ち
    AWAITING_AGE = auto()         # 年齢待ち
    AWAITING_SIZE = auto()        # サイズ待ち
    AWAITING_SEX = auto()         # 性別待ち


@dataclass
class ValidationResult:
    """バリデーション結果"""

    is_valid: bool
    value: any = None
    error_message: Optional[str] = None
    min_months: Optional[int] = None
    max_months: Optional[int] = None


@dataclass
class UserConversation:
    """ユーザー対話状態"""

    state: ConversationState = ConversationState.IDLE
    species: Optional[str] = None
    prefectures: Optional[List[str]] = None
    age_min_months: Optional[int] = None
    age_max_months: Optional[int] = None
    size: Optional[str] = None
    sex: Optional[str] = None


class ConversationHandler:
    """
    対話ハンドラー

    LINEでの条件設定対話フローを制御する。

    Requirements: 1.2, 1.5, 1.6, 1.7
    """

    # コマンドパターン
    COMMAND_PATTERNS = {
        Command.SETTINGS: [r"^設定$", r"^条件設定$", r"^新規設定$"],
        Command.CHANGE: [r"^条件変更$", r"^変更$"],
        Command.STOP: [r"^停止$", r"^通知停止$", r"^ストップ$"],
        Command.RESUME: [r"^再開$", r"^通知再開$"],
        Command.STATUS: [r"^確認$", r"^現在の設定$", r"^ステータス$"],
        Command.HELP: [r"^ヘルプ$", r"^help$", r"^\?$"],
    }

    def __init__(self, user_service=None, line_adapter=None):
        """
        ConversationHandler を初期化

        Args:
            user_service: ユーザーサービス
            line_adapter: LINEアダプター
        """
        self._user_service = user_service
        self._line_adapter = line_adapter
        self._conversations: Dict[str, UserConversation] = {}

    def parse_command(self, text: str) -> Optional[Command]:
        """
        テキストからコマンドを解析

        Args:
            text: 入力テキスト

        Returns:
            Optional[Command]: 認識されたコマンド、または None
        """
        text = text.strip()
        for command, patterns in self.COMMAND_PATTERNS.items():
            for pattern in patterns:
                if re.match(pattern, text, re.IGNORECASE):
                    return command
        return None

    def get_state(self, user_id: str) -> ConversationState:
        """
        ユーザーの対話状態を取得

        Args:
            user_id: ユーザーID

        Returns:
            ConversationState: 現在の対話状態
        """
        conv = self._conversations.get(user_id)
        return conv.state if conv else ConversationState.IDLE

    def start_settings_flow(self, user_id: str):
        """
        設定フローを開始

        Args:
            user_id: ユーザーID
        """
        self._conversations[user_id] = UserConversation(
            state=ConversationState.AWAITING_SPECIES
        )
        logger.info(f"Started settings flow for user {user_id[:8]}...")

    def process_input(self, user_id: str, text: str) -> Optional[str]:
        """
        ユーザー入力を処理

        Args:
            user_id: ユーザーID
            text: 入力テキスト

        Returns:
            Optional[str]: 応答メッセージ
        """
        text = text.strip()

        # キャンセル処理
        if text in ["キャンセル", "やめる", "中止"]:
            self._conversations.pop(user_id, None)
            return "設定をキャンセルしました。"

        conv = self._conversations.get(user_id)
        if not conv:
            return None

        state = conv.state

        if state == ConversationState.AWAITING_SPECIES:
            result = self.validate_species(text)
            if result.is_valid:
                conv.species = result.value
                conv.state = ConversationState.AWAITING_PREFECTURES
                return self.get_prompt_message(ConversationState.AWAITING_PREFECTURES)
            return result.error_message

        elif state == ConversationState.AWAITING_PREFECTURES:
            result = self.validate_prefectures(text)
            if result.is_valid:
                conv.prefectures = result.value
                conv.state = ConversationState.AWAITING_AGE
                return self.get_prompt_message(ConversationState.AWAITING_AGE)
            return result.error_message

        elif state == ConversationState.AWAITING_AGE:
            result = self.validate_age(text)
            if result.is_valid:
                conv.age_min_months = result.min_months
                conv.age_max_months = result.max_months
                conv.state = ConversationState.AWAITING_SIZE
                return self.get_prompt_message(ConversationState.AWAITING_SIZE)
            return result.error_message

        elif state == ConversationState.AWAITING_SIZE:
            result = self.validate_size(text)
            if result.is_valid:
                conv.size = result.value
                conv.state = ConversationState.AWAITING_SEX
                return self.get_prompt_message(ConversationState.AWAITING_SEX)
            return result.error_message

        elif state == ConversationState.AWAITING_SEX:
            result = self.validate_sex(text)
            if result.is_valid:
                conv.sex = result.value
                conv.state = ConversationState.IDLE
                prefs = self.get_collected_preferences(user_id)
                self._conversations.pop(user_id, None)
                return self.get_completion_message(prefs)
            return result.error_message

        return None

    def get_collected_preferences(self, user_id: str) -> NotificationPreferenceInput:
        """
        収集された条件を取得

        Args:
            user_id: ユーザーID

        Returns:
            NotificationPreferenceInput: 収集された条件
        """
        conv = self._conversations.get(user_id)
        if not conv:
            return NotificationPreferenceInput()

        return NotificationPreferenceInput(
            species=conv.species,
            prefectures=conv.prefectures,
            age_min_months=conv.age_min_months,
            age_max_months=conv.age_max_months,
            size=conv.size,
            sex=conv.sex,
        )

    def validate_species(self, text: str) -> ValidationResult:
        """
        種別入力をバリデーション

        Args:
            text: 入力テキスト

        Returns:
            ValidationResult: バリデーション結果
        """
        text = text.strip()
        if text in ["犬", "いぬ", "イヌ"]:
            return ValidationResult(is_valid=True, value="犬")
        if text in ["猫", "ねこ", "ネコ"]:
            return ValidationResult(is_valid=True, value="猫")
        if text in ["どちらでも", "両方", "指定なし"]:
            return ValidationResult(is_valid=True, value=None)

        return ValidationResult(
            is_valid=False,
            error_message="「犬」「猫」「どちらでも」のいずれかを選択してください。"
        )

    def validate_prefectures(self, text: str) -> ValidationResult:
        """
        都道府県入力をバリデーション

        Args:
            text: 入力テキスト（カンマ区切りで複数可）

        Returns:
            ValidationResult: バリデーション結果
        """
        text = text.strip()
        if text in ["指定なし", "全国", "すべて"]:
            return ValidationResult(is_valid=True, value=None)

        # カンマ、読点、スペースで分割
        parts = re.split(r"[,、\s]+", text)
        valid_prefs = []

        for part in parts:
            part = part.strip()
            if not part:
                continue

            # 都道府県名の正規化
            normalized = self._normalize_prefecture(part)
            if normalized in PREFECTURES:
                valid_prefs.append(normalized)
            else:
                return ValidationResult(
                    is_valid=False,
                    error_message=f"「{part}」は有効な都道府県名ではありません。"
                )

        if not valid_prefs:
            return ValidationResult(
                is_valid=False,
                error_message="都道府県名を入力するか、「指定なし」を選択してください。"
            )

        return ValidationResult(is_valid=True, value=valid_prefs)

    def _normalize_prefecture(self, text: str) -> str:
        """都道府県名を正規化"""
        # 「県」「府」「都」「道」が抜けている場合の補完
        if text in ["東京"]:
            return "東京都"
        if text in ["大阪"]:
            return "大阪府"
        if text in ["京都"]:
            return "京都府"
        if text in ["北海道"]:
            return "北海道"

        # 県が抜けている場合
        if text not in PREFECTURES and not text.endswith(("県", "府", "都", "道")):
            if text + "県" in PREFECTURES:
                return text + "県"

        return text

    def validate_age(self, text: str) -> ValidationResult:
        """
        年齢入力をバリデーション

        Args:
            text: 入力テキスト

        Returns:
            ValidationResult: バリデーション結果
        """
        text = text.strip()

        if text in ["指定なし", "すべて", "不問"]:
            return ValidationResult(is_valid=True, min_months=None, max_months=None)

        # パターンマッチング
        # "1歳以上", "1才以上", "12ヶ月以上"
        min_match = re.match(r"(\d+)\s*(歳|才|ヶ月|か月)?\s*(以上|〜)", text)
        if min_match:
            num = int(min_match.group(1))
            unit = min_match.group(2) or "歳"
            months = num * 12 if unit in ["歳", "才"] else num
            return ValidationResult(is_valid=True, min_months=months, max_months=None)

        # "3歳以下", "36ヶ月以下"
        max_match = re.match(r"(\d+)\s*(歳|才|ヶ月|か月)?\s*(以下|まで)", text)
        if max_match:
            num = int(max_match.group(1))
            unit = max_match.group(2) or "歳"
            months = num * 12 if unit in ["歳", "才"] else num
            return ValidationResult(is_valid=True, min_months=None, max_months=months)

        # "1歳から3歳", "1〜3歳"
        range_match = re.match(
            r"(\d+)\s*(歳|才)?\s*(から|〜|-)\s*(\d+)\s*(歳|才)?", text
        )
        if range_match:
            min_num = int(range_match.group(1))
            max_num = int(range_match.group(4))
            return ValidationResult(
                is_valid=True,
                min_months=min_num * 12,
                max_months=max_num * 12,
            )

        return ValidationResult(
            is_valid=False,
            error_message=(
                "年齢は「1歳以上」「3歳以下」「1〜3歳」「指定なし」などの形式で入力してください。"
            )
        )

    def validate_size(self, text: str) -> ValidationResult:
        """
        サイズ入力をバリデーション

        Args:
            text: 入力テキスト

        Returns:
            ValidationResult: バリデーション結果
        """
        text = text.strip()

        if text in ["指定なし", "すべて", "不問"]:
            return ValidationResult(is_valid=True, value=None)

        if text in ["小型", "小"]:
            return ValidationResult(is_valid=True, value="小型")
        if text in ["中型", "中"]:
            return ValidationResult(is_valid=True, value="中型")
        if text in ["大型", "大"]:
            return ValidationResult(is_valid=True, value="大型")

        return ValidationResult(
            is_valid=False,
            error_message="「小型」「中型」「大型」「指定なし」のいずれかを選択してください。"
        )

    def validate_sex(self, text: str) -> ValidationResult:
        """
        性別入力をバリデーション

        Args:
            text: 入力テキスト

        Returns:
            ValidationResult: バリデーション結果
        """
        text = text.strip()

        if text in ["指定なし", "どちらでも", "不問"]:
            return ValidationResult(is_valid=True, value=None)

        if text in ["男の子", "オス", "おす", "♂"]:
            return ValidationResult(is_valid=True, value="男の子")
        if text in ["女の子", "メス", "めす", "♀"]:
            return ValidationResult(is_valid=True, value="女の子")

        return ValidationResult(
            is_valid=False,
            error_message="「男の子」「女の子」「指定なし」のいずれかを選択してください。"
        )

    def get_prompt_message(self, state: ConversationState) -> str:
        """
        状態に応じたプロンプトメッセージを取得

        Args:
            state: 対話状態

        Returns:
            str: プロンプトメッセージ
        """
        prompts = {
            ConversationState.AWAITING_SPECIES: (
                "動物の種別を選択してください。\n"
                "・犬\n"
                "・猫\n"
                "・どちらでも"
            ),
            ConversationState.AWAITING_PREFECTURES: (
                "希望する都道府県を入力してください。\n"
                "複数ある場合はカンマ(,)で区切ってください。\n"
                "例: 高知県,愛媛県\n"
                "全国の場合は「指定なし」と入力してください。"
            ),
            ConversationState.AWAITING_AGE: (
                "希望する年齢範囲を入力してください。\n"
                "例: 1歳以上、3歳以下、1〜3歳\n"
                "指定しない場合は「指定なし」と入力してください。"
            ),
            ConversationState.AWAITING_SIZE: (
                "希望するサイズを選択してください。\n"
                "・小型\n"
                "・中型\n"
                "・大型\n"
                "・指定なし"
            ),
            ConversationState.AWAITING_SEX: (
                "希望する性別を選択してください。\n"
                "・男の子\n"
                "・女の子\n"
                "・指定なし"
            ),
        }
        return prompts.get(state, "")

    def get_completion_message(self, prefs: NotificationPreferenceInput) -> str:
        """
        設定完了メッセージを生成

        Args:
            prefs: 設定された条件

        Returns:
            str: 完了メッセージ
        """
        lines = ["通知条件の設定が完了しました！\n", "【設定内容】"]

        lines.append(f"種別: {prefs.species or 'すべて'}")

        if prefs.prefectures:
            lines.append(f"都道府県: {', '.join(prefs.prefectures)}")
        else:
            lines.append("都道府県: 全国")

        if prefs.age_min_months is not None or prefs.age_max_months is not None:
            age_parts = []
            if prefs.age_min_months:
                age_parts.append(f"{prefs.age_min_months // 12}歳以上")
            if prefs.age_max_months:
                age_parts.append(f"{prefs.age_max_months // 12}歳以下")
            lines.append(f"年齢: {' '.join(age_parts)}")
        else:
            lines.append("年齢: 指定なし")

        lines.append(f"サイズ: {prefs.size or '指定なし'}")
        lines.append(f"性別: {prefs.sex or '指定なし'}")

        lines.append("\n条件に合う動物が見つかり次第、お知らせします！")

        return "\n".join(lines)

    def get_help_message(self) -> str:
        """
        ヘルプメッセージを取得

        Returns:
            str: ヘルプメッセージ
        """
        return (
            "【使い方】\n"
            "・「設定」- 通知条件を新規設定\n"
            "・「条件変更」- 現在の条件を変更\n"
            "・「停止」- 通知を一時停止\n"
            "・「再開」- 通知を再開\n"
            "・「確認」- 現在の設定を確認\n"
            "\n"
            "設定中は「キャンセル」で中断できます。"
        )
