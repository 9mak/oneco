"""
アダプター層

自治体ごとの HTML スクレイピング・データ抽出ロジックを提供します。
"""

from .municipality_adapter import MunicipalityAdapter, NetworkError, ParsingError
from .kochi_adapter import KochiAdapter

__all__ = ["MunicipalityAdapter", "NetworkError", "ParsingError", "KochiAdapter"]
