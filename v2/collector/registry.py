"""台帳（registry/sources.yaml）の読み込み。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
REGISTRY_PATH = ROOT / "registry" / "sources.yaml"


@dataclass
class Source:
    slug: str
    name: str
    municipality: str
    prefecture: str
    url: str
    kind: str                  # adoption（里親募集）| sheltered（保護中）| stray（迷子＝飼い主不明のまま保護）| lost（探してます＝飼い主が探している迷子。2026-10-02 追加）
    species: str = "mixed"     # dog | cat | mixed
    phone: str | None = None
    address: str | None = None
    mode: str = "recipe"       # recipe | link_only
    recipe: str | None = None
    enabled: bool = True
    legacy: dict[str, Any] = field(default_factory=dict)

    @property
    def recipe_path(self) -> Path:
        return ROOT / (self.recipe or f"recipes/{self.slug}.yaml")


def load_sources(path: Path = REGISTRY_PATH) -> list[Source]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    out = []
    for raw in data["sources"]:
        known = {k: v for k, v in raw.items() if k in Source.__dataclass_fields__}
        out.append(Source(**known))
    return out


def select(sources: list[Source], prefix: str | None) -> list[Source]:
    if not prefix:
        return sources
    return [s for s in sources if s.slug == prefix or s.slug.startswith(prefix)]
