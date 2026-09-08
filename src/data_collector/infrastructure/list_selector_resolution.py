"""一覧ページの detail link / row セレクタを adapter 実装から解決する共通ロジック (T141)。

scripts/site_count_audit.py (T105) の掲載数比較と scripts/full_publication_audit.py の
count_audit_blind_hosts (T140) の両方が「このサイトは掲載数を比較できるか」を判定する際に
一覧ページのセレクタを必要とする。以前は両方とも sites.yaml の list_link_pattern だけを見て
いたが、これは adapter が実際に使うセレクタとは独立に手入力された値であり、adapter の
LIST_LINK_SELECTOR / ROW_SELECTOR と一致する保証がない (実質的なトートロジー)。213サイト中
178サイトが list_link_pattern を持たず構造的に判定不能だった (T133)。

解決優先順位 (T141):
    1. SiteAdapterRegistry 経由で引いた adapter class の LIST_LINK_SELECTOR
    2. 同 adapter class の ROW_SELECTOR (SinglePageTableAdapter 系)
    3. sites.yaml の list_link_pattern (adapter 未登録サイトの既存フォールバック)
    4. sites.yaml の pdf_link_pattern (PDF はリンク先内の頭数を数えられないため
       is_pdf=True を立てて比較不能扱いにする)

registry.get() は class を返すだけで adapter を instantiate しない (HTTP/DB を発生させない)。
二重実装すると片方だけ直して判定がズレるため、両スクリプトはここへ必ず集約する。
"""

from __future__ import annotations

from typing import Any

from ..adapters.rule_based.registry import SiteAdapterRegistry


def resolve_list_selector(site_name: str, raw_cfg: dict[str, Any]) -> tuple[str, str, bool]:
    """(selector, selector_source, is_pdf) を返す。selector が空文字なら解決不可。

    selector_source: "registry_list_link" | "registry_row" | "sites_yaml_list_link"
    | "sites_yaml_pdf" | "none"
    """
    adapter_cls = SiteAdapterRegistry.get(site_name)
    if adapter_cls is not None:
        list_selector = getattr(adapter_cls, "LIST_LINK_SELECTOR", "") or ""
        if list_selector:
            return list_selector, "registry_list_link", False
        row_selector = getattr(adapter_cls, "ROW_SELECTOR", "") or ""
        if row_selector:
            return row_selector, "registry_row", False

    list_pattern = raw_cfg.get("list_link_pattern")
    if list_pattern:
        return list_pattern, "sites_yaml_list_link", False

    pdf_pattern = raw_cfg.get("pdf_link_pattern")
    if pdf_pattern:
        return pdf_pattern, "sites_yaml_pdf", True

    return "", "none", False


def resolve_pagination(site_name: str) -> tuple[str, int]:
    """(NEXT_PAGE_SELECTOR, MAX_LIST_PAGES) を返す。

    NEXT_PAGE_SELECTOR が空、または adapter 未登録の場合はページ送りを辿らない
    ("" , 1) を返す。WordPressListAdapter (src/data_collector/adapters/rule_based/
    wordpress_list.py) 派生の adapter だけが NEXT_PAGE_SELECTOR / MAX_LIST_PAGES を持つ。
    """
    adapter_cls = SiteAdapterRegistry.get(site_name)
    if adapter_cls is None:
        return "", 1
    next_selector = getattr(adapter_cls, "NEXT_PAGE_SELECTOR", "") or ""
    if not next_selector:
        return "", 1
    max_pages = getattr(adapter_cls, "MAX_LIST_PAGES", 10)
    return next_selector, max_pages
