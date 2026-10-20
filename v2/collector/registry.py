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
    verified_at: str | None = None   # 電話・所在地が元ページに載っていると確認した日（YYYY-MM-DD。ops/verify_registry.py が書く。施設との対応までは見ていない）
    verified_phone_url: str | None = None    # 電話が載っていたページ
    verified_address_url: str | None = None  # 所在地が載っていたページ（台帳に address が無い entry は None）
    contact_scope: str = "facility"  # facility（phone / address は収容先そのもの）| operator（県のまとめページ等。掲載元の運営元の連絡先で、収容先は別のことがある。個体ページでは「問い合わせ先」と出す）
    mode: str = "recipe"       # recipe | link_only
    recipe: str | None = None
    enabled: bool = True
    photo: str = "ok"          # ok | pending（写真表示の許諾を自治体に申請中。返事が来るまで写真を出さない）| no（不可の返事）。T630
    legacy: dict[str, Any] = field(default_factory=dict)

    @property
    def recipe_path(self) -> Path:
        return ROOT / (self.recipe or f"recipes/{self.slug}.yaml")


def load_sources(path: Path = REGISTRY_PATH) -> list[Source]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    out = []
    for raw in data["sources"]:
        known = {k: v for k, v in raw.items() if k in Source.__dataclass_fields__}
        if known.get("verified_at") is not None:
            known["verified_at"] = str(known["verified_at"])  # 引用なしの日付は YAML が date にする
        out.append(Source(**known))
    return out


def select(sources: list[Source], prefix: str | None) -> list[Source]:
    if not prefix:
        return sources
    return [s for s in sources if s.slug == prefix or s.slug.startswith(prefix)]
