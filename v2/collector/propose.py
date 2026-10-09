"""data/proposals/*.yaml（AI が書いたレシピ案）を draft PR にする（W006 T619）。

本番 clone には書かない。作業用 clone（ONECO_REPAIR_CLONE、既定 <v2>/../.repair-clone）で
origin/main から repair/<slug>（日付なし。同じ slug は常に同じブランチ）を切り、案を v2/recipes/<slug>.yaml に置いて push → gh pr create --draft。
PR の merge はしない（オーナーが差分を見て merge したときだけ翌日の収集から本番に入る。採らないなら close）。
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import yaml

from .ai_repair import _SAFE_SLUG, PROPOSALS_DIR
from .registry import ROOT, load_sources

MAX_PR_PER_RUN = 5
JST = timezone(timedelta(hours=9))


class StepError(Exception):
    pass


def _run(cmd: list[str], cwd: Path | None = None) -> str:
    p = subprocess.run(cmd, check=False, cwd=cwd, capture_output=True, text=True, timeout=300)
    if p.returncode != 0:
        raise StepError(f"{' '.join(cmd[:3])} が失敗 (exit {p.returncode}): {(p.stderr or p.stdout).strip()[:300]}")
    return p.stdout


def clone_dir() -> Path:
    return Path(os.environ.get("ONECO_REPAIR_CLONE") or ROOT.parent / ".repair-clone")


def _ensure_clone(clone: Path) -> None:
    if (clone / ".git").exists():
        return
    origin = _run(["git", "-C", str(ROOT), "remote", "get-url", "origin"]).strip()
    _run(["git", "clone", "--quiet", origin, str(clone)])


def _differs(proposal: Path, recipe: Path) -> bool:
    """コメントを除いた YAML の中身が違うか。本番レシピが無ければ違う。"""
    if not recipe.exists():
        return True
    try:
        return yaml.safe_load(proposal.read_text(encoding="utf-8")) != yaml.safe_load(recipe.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return True


def _header_info(text: str) -> tuple[str, str, str]:
    """案の先頭コメントから (元の失敗理由, 頭数, agy の note) を取る。"""
    why = re.search(r"元の失敗理由 (.*?)・取れた頭数 (\d+)", text)
    note = re.search(r"^# agy note: (.*)$", text, re.M)
    return (why.group(1) if why else "不明", why.group(2) if why else "?", note.group(1) if note else "")


def _pr_body(slug: str, name: str, why: str, count: str, note: str) -> str:
    return (
        f"slug: {slug}\n自治体: {name}\n元の失敗理由: {why}\n新レシピで取れた頭数: {count}\n\n"
        "merge すれば翌日の収集から本番に入る。採らないなら close。\n"
        "（案の先頭の `# proposal:` コメントは手がかり。差分を見て判断する）\n\n"
        f"agy の note: {note or '(なし)'}\n"
    )


def _notify(msg: str) -> None:
    url = os.environ.get("DISCORD_WEBHOOK_URL")
    print(msg)
    if not url:
        return
    try:
        httpx.post(url, json={"content": msg}, timeout=15).raise_for_status()
    except httpx.HTTPError as e:
        print(f"-- Discord に送れなかった: {e}")


def propose(dry_run: bool = False, proposals_dir: Path | None = None, today: str | None = None) -> int:
    """案を 1 件ずつ PR にする。作った PR の数ではなく、失敗が 1 件でもあれば 1 を返す。"""
    pdir = proposals_dir or PROPOSALS_DIR
    day = today or datetime.now(JST).strftime("%Y%m%d")
    files = sorted(pdir.glob("*.yaml")) if pdir.exists() else []
    names = {s.slug: s.name for s in load_sources()}
    clone = clone_dir()
    made = 0
    failed = 0
    for f in files:
        slug = f.stem
        if not _SAFE_SLUG.fullmatch(slug):
            print(f"{slug}: slug が使えないので飛ばす")
            continue
        if not _differs(f, ROOT / "recipes" / f"{slug}.yaml"):
            print(f"{slug}: 本番レシピと同じ内容なので飛ばす")
            continue
        if made >= MAX_PR_PER_RUN:
            print(f"{slug}: 1 回の PR は最大 {MAX_PR_PER_RUN} 件。残りは次回")
            continue
        branch = f"repair/{slug}"   # 日付を付けない: 同じ slug の open PR は 1 つだけ（reviewer F-01）。close 済みなら同名ブランチを上書きして作り直す
        name = names.get(slug, slug)
        text = f.read_text(encoding="utf-8")
        why, count, note = _header_info(text)
        if dry_run:
            print(f"{slug}: PR を作る予定（{branch}・{count} 頭）")
            made += 1
            continue
        try:
            _ensure_clone(clone)
            if _run(["gh", "pr", "list", "--head", branch, "--state", "open", "--json", "url", "-q", ".[].url"], cwd=clone).strip():
                print(f"{slug}: open な PR が既にある。飛ばす")
                continue
            c = str(clone)
            _run(["git", "-C", c, "fetch", "origin"])
            _run(["git", "-C", c, "checkout", "-B", branch, "origin/main"])
            dest = clone / "v2" / "recipes" / f"{slug}.yaml"
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(f, dest)
            _run(["git", "-C", c, "add", f"v2/recipes/{slug}.yaml"])
            _run(["git", "-C", c, "commit", "-m", f"v2 repair: {slug} のレシピ案（agy・{count} 頭）"])
            _run(["git", "-C", c, "push", "--force-with-lease", "-u", "origin", branch])   # 前回（close 済み）の同名ブランチを上書き
            out = _run(["gh", "pr", "create", "--draft", "--title", f"v2 repair: {name}（{slug}）のレシピ案",
                        "--body", _pr_body(slug, name, why, count, note)], cwd=clone)
        except (StepError, OSError, subprocess.TimeoutExpired) as e:
            print(f"{slug}: PR を作れなかった。飛ばす: {e}")
            failed += 1
            continue
        made += 1
        url = out.strip().splitlines()[-1] if out.strip() else "(URL 不明)"
        done = pdir / "done"
        done.mkdir(parents=True, exist_ok=True)
        shutil.move(str(f), str(done / f"{slug}-{day}.yaml"))
        _notify(f"レシピ案 PR: {url}（{name}）")
    print(f"propose: PR {made} 件" + (f"・失敗 {failed} 件" if failed else ""))
    return 1 if failed else 0
