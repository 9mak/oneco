"""直近の正常日の入口 HTML（と follow した文書）を slug ごとに 1 世代だけ残す（W006 T618・設計監査 B2）。

AI 修復の案を「今日の HTML」だけで検証すると循環検証になる。ok だった日の HTML に新レシピを当て、
頭数が前回 ok の頭数から大きく外れないことを採用条件にするための素材。data/last_ok/<slug>/ に置く（data/ は git 管理外）。
  index.json  {"date", "docs": [{"url", "final_url", "file"}]}
  0.bin 1.bin …  取得したバイト列そのまま（PDF も）
render（Playwright）を使った run は描画後の状態を再現できないので保存しない。
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
from pathlib import Path
from typing import Any

from .fetch import FakeFetcher
from .registry import ROOT

log = logging.getLogger("collector")
LAST_OK_DIR = ROOT / "data" / "last_ok"
MAX_DOC_BYTES = 2 * 1024 * 1024   # 1 文書あたり。超えたら世代ごと保存しない
_SAFE_SLUG = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")


class RecordingFetcher:
    """fetcher を包み、get した文書を覚える。Executor が使う get / render 以外は中身へ委譲する。"""

    def __init__(self, inner: Any) -> None:
        self.inner = inner
        self.pages: dict[str, Any] = {}
        self.rendered = False

    def get(self, url: str, *args: Any, **kw: Any) -> Any:
        page = self.inner.get(url, *args, **kw)
        self.pages[url] = page
        return page

    def render(self, *args: Any, **kw: Any) -> Any:
        self.rendered = True
        return self.inner.render(*args, **kw)

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)


def save_last_ok(root: Path, slug: str, date: str, rec: RecordingFetcher) -> bool:
    """保存したら True。保存しない場合（render・文書なし・サイズ超過・保存失敗）は前回の世代を残して False。"""
    if not _SAFE_SLUG.fullmatch(slug) or rec.rendered or not rec.pages:
        return False
    pages = list(rec.pages.values())
    if any(len(getattr(p, "content", b"") or b"") > MAX_DOC_BYTES for p in pages):
        log.info("%s: 文書が %d バイトを超えるので last_ok を保存しない", slug, MAX_DOC_BYTES)
        return False
    tmp = root / f".tmp-{slug}-{os.getpid()}"
    dest = root / slug
    try:
        shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir(parents=True)
        docs = []
        for i, p in enumerate(pages):
            (tmp / f"{i}.bin").write_bytes(p.content)
            docs.append({"url": p.url, "final_url": p.final_url, "file": f"{i}.bin"})
        (tmp / "index.json").write_text(json.dumps({"date": date, "docs": docs}, ensure_ascii=False), encoding="utf-8")
        shutil.rmtree(dest, ignore_errors=True)
        os.replace(tmp, dest)
    except (OSError, AttributeError, TypeError) as e:
        log.warning("%s: last_ok を保存できない: %s", slug, e)
        shutil.rmtree(tmp, ignore_errors=True)
        return False
    return True


def load_replay(root: Path, slug: str) -> FakeFetcher | None:
    """保存済みの文書だけを返す Fetcher（オフライン）。無ければ None。"""
    if not _SAFE_SLUG.fullmatch(slug):
        return None
    d = root / slug
    try:
        idx = json.loads((d / "index.json").read_text(encoding="utf-8"))
        pages: dict[str, str | bytes] = {}
        redirects: dict[str, str] = {}
        for doc in idx["docs"]:
            pages[doc["url"]] = (d / doc["file"]).read_bytes()
            if doc.get("final_url") and doc["final_url"] != doc["url"]:
                redirects[doc["url"]] = doc["final_url"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return FakeFetcher(pages, redirects) if pages else None
