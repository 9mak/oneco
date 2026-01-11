"""
自治体アダプター抽象基底クラス

自治体ごとの HTML 構造差異を吸収するための抽象インターフェースを定義します。
新規自治体追加時は、このクラスを継承して具象アダプターを実装します。
"""

from abc import ABC, abstractmethod
from typing import List, Optional

from ..domain.models import RawAnimalData, AnimalData


class NetworkError(Exception):
    """
    ネットワークエラー例外

    HTTP エラー、接続タイムアウト、DNS 解決失敗などのネットワーク関連エラーを表します。
    """

    def __init__(
        self,
        message: str,
        url: Optional[str] = None,
        status_code: Optional[int] = None,
    ):
        """
        Args:
            message: エラーメッセージ
            url: エラーが発生した URL
            status_code: HTTP ステータスコード（該当する場合）
        """
        super().__init__(message)
        self.url = url
        self.status_code = status_code


class ParsingError(Exception):
    """
    パースエラー例外

    HTML 構造が想定と異なる場合、必要な要素が見つからない場合などを表します。
    ページ構造変更の検知に使用されます。
    """

    def __init__(
        self,
        message: str,
        selector: Optional[str] = None,
        url: Optional[str] = None,
    ):
        """
        Args:
            message: エラーメッセージ
            selector: 見つからなかった CSS セレクター
            url: エラーが発生したページの URL
        """
        super().__init__(message)
        self.selector = selector
        self.url = url


class MunicipalityAdapter(ABC):
    """
    自治体別スクレイピングアダプター抽象基底クラス

    自治体ごとに異なる HTML 構造を吸収し、統一的なインターフェースで
    保護動物情報を取得するための抽象クラスです。
    """

    def __init__(self, prefecture_code: str, municipality_name: str):
        """
        Args:
            prefecture_code: 都道府県コード（2桁数字文字列、例: "39"）
            municipality_name: 自治体名（例: "高知県"）

        Preconditions:
            prefecture_code は2桁数字文字列
            municipality_name は非空文字列
        """
        self.prefecture_code = prefecture_code
        self.municipality_name = municipality_name

    @abstractmethod
    def fetch_animal_list(self) -> List[str]:
        """
        一覧ページから個体詳細ページの URL リストを取得

        Returns:
            List[str]: 個体詳細ページの絶対 URL リスト

        Raises:
            NetworkError: HTTP エラー発生時
            ParsingError: HTML 構造が想定と異なる時
        """
        pass

    @abstractmethod
    def extract_animal_details(self, detail_url: str) -> RawAnimalData:
        """
        個体詳細ページから動物情報を抽出

        Args:
            detail_url: 個体詳細ページの URL

        Returns:
            RawAnimalData: 抽出した生データ

        Raises:
            NetworkError: HTTP エラー発生時
            ParsingError: HTML 構造が想定と異なる時
            ValidationError: 必須フィールド欠損時
        """
        pass

    @abstractmethod
    def normalize(self, raw_data: RawAnimalData) -> AnimalData:
        """
        生データを統一スキーマに正規化

        Args:
            raw_data: 自治体サイトから抽出した生データ

        Returns:
            AnimalData: 正規化済みデータ（Pydantic モデル）

        Raises:
            ValidationError: 正規化失敗時
        """
        pass
