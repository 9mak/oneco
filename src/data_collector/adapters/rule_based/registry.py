"""SiteAdapterRegistry - サイト名と rule-based adapter class のマッピング

各 rule-based 派生クラスは `register()` で site_name を登録する。
`__main__.py` の `run_rule_based_sites` が、sites.yaml の各 site に対して
このレジストリから adapter クラスを引いて instantiate する。

未登録サイトは `get()` が None を返し、呼出側で LLM 経路にフォールバックする。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import RuleBasedAdapter


class SiteAdapterRegistry:
    """サイト名 → rule-based adapter class の静的レジストリ"""

    _registry: dict[str, type[RuleBasedAdapter]] = {}

    @classmethod
    def register(cls, site_name: str, adapter_cls: type[RuleBasedAdapter]) -> None:
        """site_name と adapter_cls を関連付ける

        Args:
            site_name: sites.yaml の `name` フィールドと完全一致する名前
            adapter_cls: RuleBasedAdapter のサブクラス

        Raises:
            ValueError: 同じ site_name が既に登録されている場合
        """
        if site_name in cls._registry:
            existing = cls._registry[site_name].__name__
            raise ValueError(f"site '{site_name}' is already registered by {existing}")
        cls._registry[site_name] = adapter_cls

    @classmethod
    def get(cls, site_name: str) -> type[RuleBasedAdapter] | None:
        """site_name に対応する adapter class を返す（未登録時は None）"""
        return cls._registry.get(site_name)

    @classmethod
    def all_registered(cls) -> list[str]:
        """登録済みの site_name 一覧"""
        return list(cls._registry.keys())

    @classmethod
    def coverage_stats(cls, all_site_names: list[str]) -> dict[str, int]:
        """全サイトの中で何件が rule-based 化されているかの統計

        Args:
            all_site_names: sites.yaml に存在する全 site_name

        Returns:
            {"total": int, "rule_based": int, "llm_only": int}
        """
        rule_based_count = sum(1 for n in all_site_names if n in cls._registry)
        return {
            "total": len(all_site_names),
            "rule_based": rule_based_count,
            "llm_only": len(all_site_names) - rule_based_count,
        }
