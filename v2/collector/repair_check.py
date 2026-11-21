"""エージェントの仕事を、PR にする前に固定の基準で検査する（W006 T645）。エージェントの自己申告は信じない。

作業用 worktree（repair/<slug>。origin/main から切ったもの）の状態を見る:
  1 差分が触ってよいパスだけ（レシピ・自分の試験・自分の fixture）。台帳・コード・ほかの slug・.github は落とす
  2 strict schema（recipe_schema）
  3 今日のページ（エージェントが保存した fixture）でその slug を読む: 1 頭以上（採用条件 a・b・c・v1・v2 つき）か、雛形でない 0 頭の根拠
  4 過去の fixture（その slug のもの）で、直す前のレシピが読めていたものは頭数と ID が変わらない
  5 差分に個人の連絡先（携帯・メール）が無い
  6 追加した試験は直す前のレシピでは落ちる（Red）→ 直したレシピで通る（Green）→ v2 全体の pytest → ruff
1〜5 は安く、6 は遅い。1〜5 で落ちたら 6 は動かさない。
"""

from __future__ import annotations

import html
import os
import re
import subprocess
import sys
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .ai_repair import (
    MAX_FIXTURE_SAMPLES,
    _fixture_name_pattern,
    _try_recipe,
    check_adoption,
    heading_in_values,
)
from .extract import Result
from .fetch import FakeFetcher
from .recipe import Recipe
from .recipe_schema import validate_recipe_dict
from .registry import load_sources
from .repair_agent import agent_env

TARGETED_TIMEOUT_S = 900
FULL_TIMEOUT_S = 1800
RUFF_TIMEOUT_S = 300
# 0 頭の根拠として認める種類（extract.empty_hits の kind）。all_excluded は「全行を除外しただけ」で、雛形・案内文の行を落としているだけのことがある
REAL_EMPTY_EVIDENCE = frozenset({"empty_selector", "empty_absent", "empty_text", "empty_text_all", "empty_text_entries"})
_SAFE_SLUG = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")
# tests/test_fixtures_pii_guard.py と同じ判定（伏せ字 0X0-0000-0000・example / mihon.jp / *.lg.jp / *.go.jp のメールは許す）
_MOBILE = re.compile(r"(?<![0-9])0[5789]0[-‐‑–—−\s.]?[0-9]{4}[-‐‑–—−\s.]?[0-9]{4}(?![0-9])")
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]{2,}\s*(?:@|\(a\)|\[at\]|\(at\))\s*([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)", re.I)
_OK_EMAIL_DOMAIN = ("example", "mihon.jp", ".lg.jp", ".go.jp")

ExecFn = Callable[[list[str], Path, dict[str, str] | None, int], tuple[int, str]]


@dataclass
class CheckResult:
    ok: bool
    problems: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)


def default_exec(cmd: list[str], cwd: Path, env: dict[str, str] | None, timeout: int) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, check=False, timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, f"時間切れ（{timeout} 秒）"
    except OSError as e:
        return 127, f"{type(e).__name__}: {e}"
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def _git(wt: Path, *args: str) -> str:
    p = subprocess.run(["git", "-C", str(wt), *args], capture_output=True, text=True, check=False)
    if p.returncode != 0:
        raise RuntimeError(f"git {' '.join(args[:2])} が失敗: {(p.stderr or p.stdout).strip()[:200]}")
    return p.stdout


def changed_files(wt: Path) -> list[str]:
    """origin/main との差分のファイル（commit 済み・未 commit・未追跡のぜんぶ）。"""
    tracked = _git(wt, "diff", "--name-only", "origin/main").splitlines()
    untracked = _git(wt, "ls-files", "--others", "--exclude-standard").splitlines()
    return sorted({f for f in tracked + untracked if f})


def allowed_patterns(slug: str) -> list[re.Pattern[str]]:
    s = re.escape(slug)
    return [re.compile(p) for p in (
        rf"v2/recipes/{s}\.yaml",
        rf"v2/tests/test_repair_{s}_\d{{8}}\.py",
        rf"v2/tests/fixtures/repair_{s}_\d{{8}}[A-Za-z0-9_.-]*\.(?:html|json)",
    )]


def _origin_recipe(wt: Path, slug: str) -> str | None:
    try:
        return _git(wt, "show", f"origin/main:v2/recipes/{slug}.yaml")
    except RuntimeError:
        return None


def _added_text(wt: Path, files: list[str]) -> str:
    """差分で足された行（追跡中のファイルの + 行と、未追跡のファイルの全文）。"""
    diff = _git(wt, "diff", "-U0", "origin/main")
    lines = [ln[1:] for ln in diff.splitlines() if ln.startswith("+") and not ln.startswith("+++")]
    untracked = set(_git(wt, "ls-files", "--others", "--exclude-standard").splitlines())
    for f in files:
        if f in untracked:
            try:
                lines.append((wt / f).read_text(encoding="utf-8", errors="replace"))
            except OSError:
                pass
    return "\n".join(lines)


def pii_hits(text: str) -> list[str]:
    plain = unicodedata.normalize("NFKC", html.unescape(text))
    plain = re.sub(r"<[^>]+>", " ", plain)
    hits = []
    for m in _MOBILE.finditer(plain):
        digits = re.sub(r"[^0-9]", "", m.group(0))
        if not (digits[3:] == "00000000" or digits == "0000000000"):
            hits.append("携帯・IP 電話の形")
    for m in _EMAIL.finditer(plain):
        if not any(k in m.group(1).lower() for k in _OK_EMAIL_DOMAIN):
            hits.append("私人のメールの形")
    return sorted(set(hits))


def _passed(out: str) -> int:
    m = re.search(r"(\d+) passed", out)
    return int(m.group(1)) if m else 0


def _ids(res: Result) -> list[str]:
    return sorted(str(a.get("id")) for a in res.animals)


def _today_fixture(wt: Path, slug: str) -> tuple[Path | None, str | None]:
    """エージェントが保存した今日の入口ページ repair_<slug>_<YYYYMMDD>.html（日付が最新のもの）。"""
    pat = re.compile(rf"repair_{re.escape(slug)}_(\d{{8}})\.html")
    found = sorted(((m.group(1), p) for p in (wt / "v2/tests/fixtures").glob("*.html") if (m := pat.fullmatch(p.name))), key=lambda t: t[0])
    return (found[-1][1], found[-1][0]) if found else (None, None)


def _pages(wt: Path, slug: str, ymd: str, url: str, entry: Path) -> dict[str, str]:
    pages = {url: entry.read_text(encoding="utf-8")}
    meta = wt / f"v2/tests/fixtures/repair_{slug}_{ymd}_pages.json"
    if meta.exists():
        import json

        data = json.loads(meta.read_text(encoding="utf-8"))
        for u, name in data.items():
            pages[u] = (wt / "v2/tests/fixtures" / Path(name).name).read_text(encoding="utf-8")
    return pages


def check(slug: str, wt: Path, exec_fn: ExecFn = default_exec, run_full: bool = True) -> CheckResult:
    problems: list[str] = []
    d: dict[str, Any] = {}
    if not _SAFE_SLUG.fullmatch(slug):
        return CheckResult(False, [f"slug がファイル名に使えない: {slug!r}"], d)

    # 1 触ってよいパス
    files = changed_files(wt)
    d["changed_files"] = files
    pats = allowed_patterns(slug)
    outside = [f for f in files if not any(p.fullmatch(f) for p in pats)]
    if outside:
        problems.append("触ってよいパス以外を変えている: " + "・".join(outside[:8]))
    recipe_rel = f"v2/recipes/{slug}.yaml"
    new_tests = [f for f in files if re.fullmatch(rf"v2/tests/test_repair_{re.escape(slug)}_\d{{8}}\.py", f)]
    if recipe_rel not in files:
        problems.append("レシピが変わっていない")
    if not new_tests:
        problems.append(f"試験 v2/tests/test_repair_{slug}_<日付>.py が無い（直す前に落ちる試験を先に書く決まり）")

    sources = {s.slug: s for s in load_sources(wt / "v2/registry/sources.yaml")}
    source = sources.get(slug)
    if source is None:
        return CheckResult(False, problems + [f"台帳に無い slug: {slug}"], d)

    # 2 schema
    new_text = (wt / recipe_rel).read_text(encoding="utf-8") if (wt / recipe_rel).exists() else ""
    old_text = _origin_recipe(wt, slug)
    new_recipe: Recipe | None = None
    try:
        raw = yaml.safe_load(new_text)
    except yaml.YAMLError as e:
        raw = None
        problems.append(f"レシピが YAML として読めない: {e}")
    if isinstance(raw, dict):
        violations = validate_recipe_dict(raw, source.url)
        if violations:
            problems.append("レシピが schema 検査に通らない: " + " / ".join(violations))
        else:
            new_recipe = Recipe.from_dict(raw)
    elif raw is not None or not problems:
        problems.append("レシピが YAML のマッピングでない")

    # 3 今日のページ
    entry, ymd = _today_fixture(wt, slug)
    if entry is None or ymd is None:
        problems.append(f"今日のページの保存 v2/tests/fixtures/repair_{slug}_<日付>.html が無い")
    elif new_recipe is not None:
        _check_today(wt, slug, source, entry, ymd, new_recipe, old_text, problems, d)

    # 4 過去の fixture
    if new_recipe is not None and old_text:
        _check_regression(wt, slug, source, new_recipe, old_text, set(files), problems, d)

    # 5 個人の連絡先
    hits = pii_hits(_added_text(wt, files))
    if hits:
        problems.append("差分に個人の連絡先らしい文字列がある（" + "・".join(hits) + "。伏せ字 0X0-0000-0000・masked@example.jp にする）")

    if problems:
        return CheckResult(False, problems, d)

    # 6 Red → Green → 全体 → ruff
    env = {**agent_env("agy", os.environ, python_dir=str(Path(sys.executable).parent)), "PYTHONPATH": str(wt / "v2")}
    py = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"]
    if old_text is not None:
        recipe_path = wt / recipe_rel
        recipe_path.write_text(old_text, encoding="utf-8")
        try:
            code, _out = exec_fn([*py, *new_tests], wt, env, TARGETED_TIMEOUT_S)
        finally:
            recipe_path.write_text(new_text, encoding="utf-8")
        if code == 0:
            problems.append("追加した試験は直す前のレシピでも通る（今の崩れを再現していない）")
    mention = sorted(p.relative_to(wt).as_posix() for p in (wt / "v2/tests").glob("test_*.py")
                     if not p.name.startswith(f"test_repair_{slug}_") and slug in p.read_text(encoding="utf-8", errors="replace"))
    code, out = exec_fn([*py, *new_tests, *mention], wt, env, TARGETED_TIMEOUT_S)
    d["tests_added"] = _passed(out)
    if code != 0:
        problems.append(f"追加した試験・この slug の既存の試験が通らない: {out.strip()[-200:]}")
    elif run_full:
        code, out = exec_fn([*py, "v2"], wt, env, FULL_TIMEOUT_S)
        d["tests_total"] = _passed(out)
        if code != 0:
            problems.append(f"v2 全体の pytest が通らない: {out.strip()[-200:]}")
    code, out = exec_fn([sys.executable, "-m", "ruff", "check", "--config", "ruff.toml", "v2"], wt, env, RUFF_TIMEOUT_S)
    d["ruff"] = "ok" if code == 0 else out.strip()[-200:]
    if code != 0:
        problems.append(f"ruff が通らない: {out.strip()[-200:]}")
    return CheckResult(not problems, problems, d)


def _check_today(wt: Path, slug: str, source: Any, entry: Path, ymd: str, new_recipe: Recipe, old_text: str | None,
                 problems: list[str], d: dict[str, Any]) -> None:
    try:
        pages = _pages(wt, slug, ymd, source.url, entry)
    except (OSError, ValueError) as e:
        problems.append(f"今日のページの保存（_pages.json）が読めない: {e}")
        return
    d["before_count"] = None
    if old_text:
        try:
            old_raw = yaml.safe_load(old_text)
            d["before_count"] = len(_try_recipe(source, Recipe.from_dict(old_raw), FakeFetcher(pages)).animals)
        except Exception:
            d["before_count"] = 0
    try:
        res = _try_recipe(source, new_recipe, FakeFetcher(pages))
    except Exception as e:
        problems.append(f"今日のページで新レシピが動かない: {type(e).__name__}: {e}。辿る先のページがあるなら "
                        f"repair_{slug}_{ymd}_pages.json に URL とファイル名を並べる")
        return
    d["after_count"] = len(res.animals)
    d["empty_evidence"] = res.empty_evidence
    if res.animals:
        bad = check_adoption(res)
        if bad:
            problems.append("今日のページの結果が採用条件を満たさない: " + " / ".join(bad))
        d["headings"] = heading_in_values(res.animals)
    elif not (res.empty_confirmed and res.empty_evidence in REAL_EMPTY_EVIDENCE):
        problems.append("今日のページで 0 頭で、0 頭の根拠（empty_selector・empty_absent・empty_text）が無い"
                        "（雛形の行を除外しただけ・読めていないだけの可能性）")


def _check_regression(wt: Path, slug: str, source: Any, new_recipe: Recipe, old_text: str, changed: set[str],
                      problems: list[str], d: dict[str, Any]) -> None:
    try:
        old_recipe = Recipe.from_dict(yaml.safe_load(old_text))
    except (TypeError, ValueError, yaml.YAMLError):
        d["regression_compared"] = 0
        return
    pat = _fixture_name_pattern(slug)
    fx = wt / "v2/tests/fixtures"
    past = [p for p in sorted(fx.glob("*.html")) if pat.search(p.name) and f"v2/tests/fixtures/{p.name}" not in changed]
    compared = 0
    for p in past[:MAX_FIXTURE_SAMPLES]:
        text = p.read_text(encoding="utf-8", errors="replace")
        try:
            old_res = _try_recipe(source, old_recipe, FakeFetcher({source.url: text}))
        except Exception:
            continue    # 直す前のレシピが読めない保存ページは基準にならない
        if not old_res.animals or heading_in_values(old_res.animals):
            continue
        compared += 1
        try:
            new_res = _try_recipe(source, new_recipe, FakeFetcher({source.url: text}))
        except Exception as e:
            problems.append(f"退行: 過去の fixture {p.name} で新レシピが動かない（{type(e).__name__}）")
            continue
        if len(new_res.animals) != len(old_res.animals) or _ids(new_res) != _ids(old_res):
            problems.append(f"退行: 過去の fixture {p.name} で頭数 {len(old_res.animals)}→{len(new_res.animals)}"
                            + ("・ID が変わる" if _ids(new_res) != _ids(old_res) else ""))
    d["regression_compared"] = compared
