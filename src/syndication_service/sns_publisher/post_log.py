"""SNS 投稿履歴の YAML 永続化

design.md 5.2 step 5: 投稿結果 (動物 ID, 投稿時刻, プラットフォーム, URL, 成否) を記録。
重複投稿防止のため candidate_selector が posted_urls を参照する。

ストレージは YAML ファイル (SiteBaselineTracker と同じ思想)。DB スキーマ変更を
避けてリリース速度を確保する。本格運用で件数が増えたら DB テーブルに移行。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import yaml

if TYPE_CHECKING:
    from data_collector.domain.models import AnimalData

logger = logging.getLogger(__name__)

# 「写真なし」プレースホルダ画像の名前パターン。これを照合キーに使うと
# 写真の無い別個体同士が同一と誤判定されるため除外する (山梨 noimage01.jpg)。
_PLACEHOLDER_IMAGE_MARKERS = ("noimage", "no-image", "no_image", "nophoto", "no-photo")


def identity_of(animal: AnimalData) -> dict[str, str]:
    """投稿記録に残す個体アイデンティティ (T058)。

    source_url の形式変更 (T026 山梨の実例) で URL 照合をすり抜けても、
    個体の特徴で「投稿済み」を判定するための材料。値はすべて文字列で
    YAML にそのまま永続化できる形にする。
    """
    first_image = ""
    if animal.image_urls:
        first_image = Path(urlparse(str(animal.image_urls[0])).path).name
    return {
        "species": animal.species or "",
        "sex": animal.sex or "",
        "color": (animal.color or "").strip(),
        "shelter_date": animal.shelter_date.isoformat() if animal.shelter_date else "",
        "image_name": first_image,
    }


def identity_keys_from_fields(identity: dict[str, Any]) -> set[str]:
    """identity 辞書から照合キー集合を作る。

    2 種類のキーを返す:
      - ``img:<画像ファイル名>``: 個体写真は一意性が高く単独で照合できる。
        プレースホルダ画像 (noimage 等) は別個体同士を誤同一視するため除外。
      - ``prof:<種別>|<性別>|<毛色>|<初出日>``: 写真が無い個体向け。毛色だけでは
        衝突する (キジトラ雄など) ため初出日まで含めて絞る。いずれかの要素が
        欠けるキーは作らない (空要素入りキーは誤ヒットの温床になる)。
    """
    keys: set[str] = set()
    image_name = str(identity.get("image_name") or "").strip().lower()
    if image_name and not any(m in image_name for m in _PLACEHOLDER_IMAGE_MARKERS):
        keys.add(f"img:{image_name}")
    species = str(identity.get("species") or "").strip()
    sex = str(identity.get("sex") or "").strip()
    color = str(identity.get("color") or "").strip()
    shelter_date = str(identity.get("shelter_date") or "").strip()
    if species and sex and color and shelter_date:
        keys.add(f"prof:{species}|{sex}|{color}|{shelter_date}")
    return keys


def identity_keys_of(animal: AnimalData) -> set[str]:
    """AnimalData から直接照合キー集合を作る (candidate_selector 用)。"""
    return identity_keys_from_fields(identity_of(animal))


class PostLog:
    """投稿履歴を YAML で永続化する。

    URL を主キーとし、再記録は上書き (= 重複投稿防止のための観点では「投稿済み」
    という事実だけが必要)。
    """

    def __init__(self, *, path: Path) -> None:
        self._path = path
        self._records: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            raw = yaml.safe_load(self._path.read_text(encoding="utf-8"))
        except Exception as exc:  # YAML 破損は黙って空扱い (collection を止めない)
            logger.warning("PostLog: failed to load %s (%s); treating as empty", self._path, exc)
            return
        if not isinstance(raw, dict):
            return
        posts = raw.get("posts")
        if not isinstance(posts, list):
            return
        for entry in posts:
            if not isinstance(entry, dict):
                continue
            url = entry.get("url")
            if isinstance(url, str) and url:
                self._records[url] = entry

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"posts": list(self._records.values())}
        self._path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False))

    def posted_urls(self) -> set[str]:
        return set(self._records.keys())

    def posted_identity_keys(self) -> set[str]:
        """記録済み identity から照合キー集合を返す。

        source_url の形式変更 (T026 山梨の実例) で URL 照合をすり抜けても、
        個体そのものの特徴で「投稿済み」を判定できるようにする (T058)。
        identity を持たない旧エントリは空集合に寄与するだけで壊れない。
        """
        keys: set[str] = set()
        for entry in self._records.values():
            identity = entry.get("identity")
            if isinstance(identity, dict):
                keys |= identity_keys_from_fields(identity)
        return keys

    def record(
        self,
        *,
        url: str,
        platform: str,
        text: str,
        dry_run: bool,
        identity: dict[str, str] | None = None,
    ) -> None:
        if not url:
            raise ValueError("url must be non-empty")
        if not platform:
            raise ValueError("platform must be non-empty")
        entry: dict[str, Any] = {
            "url": url,
            "platform": platform,
            "text": text,
            "dry_run": dry_run,
        }
        if identity:
            entry["identity"] = identity
        self._records[url] = entry
        self._save()
