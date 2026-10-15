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
MAX_GENERATION_BYTES = 10 * 1024 * 1024   # 1 世代（1 slug）の合計。follow_all の slug が数百文書を抱えないように
MAX_DOCS = 60                              # 1 世代の文書数
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


def cleanup_last_ok(root: Path) -> None:
    """前回の保存が途中で落ちた残骸を片付ける（run の開始時）。.tmp-* は捨てる。
    .old-<slug> は <slug> が無ければ（dest を退避した直後に落ちた）戻し、あれば（置換は済んでいた）捨てる。"""
    try:
        entries = list(root.iterdir()) if root.is_dir() else []
    except OSError:
        return
    for p in entries:
        try:
            if p.name.startswith(".tmp-"):
                shutil.rmtree(p, ignore_errors=True)
            elif p.name.startswith(".old-"):
                dest = root / p.name.removeprefix(".old-")
                if dest.exists():
                    shutil.rmtree(p, ignore_errors=True)
                else:
                    os.replace(p, dest)
        except OSError as e:
            log.warning("last_ok の残骸を片付けられない %s: %s", p, e)


def save_last_ok(root: Path, slug: str, date: str, rec: RecordingFetcher, count: int | None = None) -> bool:
    """保存したら True。保存しない場合（render・文書なし・サイズ/文書数超過・保存失敗）は前回の世代を残して False。
    count はその日の頭数（d の基準。state の last_ok_count より優先する）。"""
    if not _SAFE_SLUG.fullmatch(slug) or rec.rendered or not rec.pages:
        return False
    pages = list(rec.pages.values())
    sizes = [len(getattr(p, "content", b"") or b"") for p in pages]
    if len(pages) > MAX_DOCS or any(n > MAX_DOC_BYTES for n in sizes) or sum(sizes) > MAX_GENERATION_BYTES:
        log.info("%s: 文書が多すぎる・大きすぎるので last_ok を保存しない（%d 文書・%d バイト）", slug, len(pages), sum(sizes))
        return False
    tmp = root / f".tmp-{slug}-{os.getpid()}"
    old = root / f".old-{slug}"
    dest = root / slug
    moved = False
    try:
        shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir(parents=True)
        docs = []
        for i, p in enumerate(pages):
            (tmp / f"{i}.bin").write_bytes(p.content)
            docs.append({"url": p.url, "final_url": p.final_url, "file": f"{i}.bin"})
        (tmp / "index.json").write_text(json.dumps({"date": date, "count": count, "docs": docs}, ensure_ascii=False),
                                        encoding="utf-8")
        # 原子的な置換: 前世代を .old へ退避 → 新世代を置く → .old を消す。途中で落ちたら前世代を戻す
        shutil.rmtree(old, ignore_errors=True)
        if dest.exists():
            os.replace(dest, old)
            moved = True
        os.replace(tmp, dest)
    except (OSError, AttributeError, TypeError) as e:
        log.warning("%s: last_ok を保存できない: %s", slug, e)
        if moved and not dest.exists():
            try:
                os.replace(old, dest)
            except OSError as e2:
                log.warning("%s: 前世代を戻せない（次の run の開始時に戻す）: %s", slug, e2)
        shutil.rmtree(tmp, ignore_errors=True)
        return False
    shutil.rmtree(old, ignore_errors=True)
    return True


def load_count(root: Path, slug: str) -> int | None:
    """保存した日の頭数（無ければ None）。"""
    if not _SAFE_SLUG.fullmatch(slug):
        return None
    try:
        n = json.loads((root / slug / "index.json").read_text(encoding="utf-8")).get("count")
    except (OSError, ValueError, AttributeError):
        return None
    return n if isinstance(n, int) and not isinstance(n, bool) else None


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
