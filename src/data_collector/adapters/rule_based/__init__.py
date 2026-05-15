"""rule-based 抽出アダプター群

LLM に依存せず、サイト個別の HTML 構造を CSS セレクタ等で抽出する
adapter 階層。`RuleBasedAdapter` を共通基底とし、4 種類の base class
（WordPressList / SinglePageTable / Playwright / PdfTable）が派生する。
サイト個別アダプターはこれらの 4 base から派生する。
"""

from .base import RuleBasedAdapter
from .pdf_table import PdfTableAdapter
from .playwright import PlaywrightFetchMixin
from .registry import SiteAdapterRegistry
from .single_page_table import SinglePageTableAdapter
from .wordpress_list import FieldSpec, WordPressListAdapter

__all__ = [
    "FieldSpec",
    "PdfTableAdapter",
    "PlaywrightFetchMixin",
    "RuleBasedAdapter",
    "SinglePageTableAdapter",
    "SiteAdapterRegistry",
    "WordPressListAdapter",
]
