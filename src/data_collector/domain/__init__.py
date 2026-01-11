"""
ドメイン層

データ正規化・差分検知・バリデーションロジックを提供します。
"""

from .models import RawAnimalData, AnimalData
from .normalizer import DataNormalizer
from .diff_detector import DiffDetector, DiffResult

__all__ = [
    "RawAnimalData",
    "AnimalData",
    "DataNormalizer",
    "DiffDetector",
    "DiffResult",
]
