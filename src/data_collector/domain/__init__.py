"""
ドメイン層

データ正規化・差分検知・バリデーションロジックを提供します。
"""

from .diff_detector import DiffDetector, DiffResult
from .models import AnimalData, RawAnimalData
from .normalizer import DataNormalizer

__all__ = [
    "AnimalData",
    "DataNormalizer",
    "DiffDetector",
    "DiffResult",
    "RawAnimalData",
]
