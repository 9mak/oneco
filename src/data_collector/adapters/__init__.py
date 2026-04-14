"""
アダプター層

自治体ごとの HTML スクレイピング・データ抽出ロジックを提供します。
"""

from .kochi_adapter import KochiAdapter
from .municipality_adapter import MunicipalityAdapter, NetworkError, ParsingError

__all__ = ["KochiAdapter", "MunicipalityAdapter", "NetworkError", "ParsingError"]
