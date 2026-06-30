"""LLM-assisted adapter 自動修復ワーカー (自己修復ループ Phase 2)

検知シグナル (フィールド欠損率急増 / detail_error 連続 / 件数低下) を受けた
1 サイトについて、Groq API で adapter コードのパッチを生成し、
二重ガード (ユニットテスト + live test 改善定量確認) を通過したら
fix/auto-* ブランチで PR を作成する。失敗時は Issue を作成する。

Usage:
    python scripts/auto_fix_adapter.py --site-name "サイト名"
    python scripts/auto_fix_adapter.py --site-name "..." --dry-run

設計方針 (project_self_healing.md, project_extraction_strategy.md):
- 運用は rule-based 100% 維持。LLM は adapter のコード修正にだけ使う
- LLM は **Groq** を使う（既存 GROQ_API_KEY 流用、コスト最小化）
- 自動マージは二重ガード通過時のみ。ガード未通過は Issue 化して人間判断
"""

from __future__ import annotations

import argparse
import importlib
import inspect
import json
import os
import pkgutil
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import yaml  # noqa: E402

# adapter registry を populate（auto-discoverable）
import data_collector.adapters.rule_based.sites as _sites_pkg  # noqa: E402

for _, _name, _ in pkgutil.iter_modules(_sites_pkg.__path__):
    try:
        importlib.import_module(f"data_collector.adapters.rule_based.sites.{_name}")
    except Exception:
        pass

from data_collector.adapters.rule_based.registry import SiteAdapterRegistry  # noqa: E402
from data_collector.domain.normalizer import DataNormalizer  # noqa: E402
from data_collector.domain.quality_metrics import compute_missing_rates  # noqa: E402
from data_collector.llm.config import SiteConfig  # noqa: E402

DEFAULT_MODEL = "llama-3.3-70b-versatile"  # Groq (既存 GroqProvider と揃える)
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
MAX_HTML_CHARS = 6000  # 圧縮後の list/detail HTML 各上限 (Groq 無料枠 TPM 12000 に収める)
DETAIL_SAMPLE_COUNT = 5
# max_tokens は Groq の "Requested" トークンに 1:1 で効く (実出力長と無関係)。
# セレクタ/ラベル修正の unified diff は短いので 2048 で足り、無料枠超過を防ぐ。
MAX_OUTPUT_TOKENS = 2048
# 並列 dispatch (山梨県 犬/猫/他ペット 等) で org 全体の TPM/min を食い合った際の
# 待機リトライ。単発リクエストを縮小しても、同一分内に複数走ると 429 になりうるため。
RATE_LIMIT_MAX_RETRIES = 4
RATE_LIMIT_DEFAULT_WAIT_SEC = 60


_SCRIPT_STYLE_RE = re.compile(
    r"<(script|style|noscript)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL
)
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_WHITESPACE_RE = re.compile(r"\s+")


def _compress_html(html: str) -> str:
    """LLM プロンプト用に HTML を圧縮する。

    script/style/noscript ブロック・HTML コメント・連続空白を除去し、
    タグ構造とラベルテキスト (セレクタ修復に必要な情報) は保ったまま
    トークン量を削る。Groq 無料枠 TPM 12000 に単発リクエストを収めるため。
    """
    html = _SCRIPT_STYLE_RE.sub("", html)
    html = _HTML_COMMENT_RE.sub("", html)
    html = _WHITESPACE_RE.sub(" ", html)
    return html.strip()


def _retry_after_seconds(err: Exception) -> float | None:
    """RateLimitError の Retry-After ヘッダ (秒) を読む。無ければ None。"""
    response = getattr(err, "response", None)
    headers = getattr(response, "headers", None)
    if not headers:
        return None
    value = headers.get("retry-after")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@dataclass
class Metrics:
    """1 サイトの adapter 動作メトリクス (before / after で比較)"""

    status: str  # "ok" / "empty" / "list_error" / "detail_error" / "skipped_js" / "no_adapter"
    list_count: int = 0
    detail_errors: int = 0
    missing_rates: dict[str, float] | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "list_count": self.list_count,
            "detail_errors": self.detail_errors,
            "missing_rates": self.missing_rates or {},
            "error": self.error,
        }


def load_site(site_name: str) -> tuple[SiteConfig, type, Path]:
    """sites.yaml と registry から site_config / adapter_cls / adapter_file_path を取得"""
    cfg = yaml.safe_load(
        (ROOT / "src/data_collector/config/sites.yaml").read_text(encoding="utf-8")
    )
    raw = next((s for s in cfg["sites"] if s["name"] == site_name), None)
    if not raw:
        raise SystemExit(f"site not found in sites.yaml: {site_name}")
    sc = SiteConfig(
        name=raw["name"],
        prefecture=raw.get("prefecture", ""),
        prefecture_code=raw.get("prefecture_code", "00"),
        list_url=raw["list_url"],
        category=raw.get("category", "sheltered"),
        requires_js=raw.get("requires_js", False),
        single_page=raw.get("single_page", False),
        list_link_pattern=raw.get("list_link_pattern"),
        pdf_link_pattern=raw.get("pdf_link_pattern"),
        pdf_multi_animal=raw.get("pdf_multi_animal", False),
        timeout_sec=raw.get("timeout_sec"),
        fallback_to_llm=raw.get("fallback_to_llm", False),
    )
    cls = SiteAdapterRegistry.get(site_name)
    if cls is None:
        raise SystemExit(f"adapter not registered: {site_name}")
    adapter_file = Path(inspect.getfile(cls))
    return sc, cls, adapter_file


def measure(adapter) -> Metrics:
    """現状 adapter での収集結果のメトリクスを採取 (最大 DETAIL_SAMPLE_COUNT 件)"""
    try:
        urls = adapter.fetch_animal_list()
    except Exception as e:
        return Metrics(status="list_error", error=f"{type(e).__name__}: {str(e)[:160]}")
    if not urls:
        return Metrics(status="empty", list_count=0)
    raws = []
    detail_errors = 0
    for url, cat in urls[:DETAIL_SAMPLE_COUNT]:
        try:
            raws.append(adapter.extract_animal_details(url, cat))
        except Exception:
            detail_errors += 1
    if not raws:
        return Metrics(status="detail_error", list_count=len(urls), detail_errors=detail_errors)
    animals = [DataNormalizer.normalize(r) for r in raws]
    return Metrics(
        status="ok",
        list_count=len(urls),
        detail_errors=detail_errors,
        missing_rates=compute_missing_rates(animals),
    )


def fetch_html_samples(site_config: SiteConfig, adapter_cls: type) -> dict[str, str]:
    """list HTML と detail HTML サンプルを取得 (LLM プロンプト用)"""
    adapter = adapter_cls(site_config)
    samples: dict[str, str] = {}
    try:
        list_html = adapter._http_get(site_config.list_url)
        samples["list_html"] = _compress_html(list_html)[:MAX_HTML_CHARS]
    except Exception as e:
        samples["list_html"] = f"<error: {e}>"
        return samples
    try:
        urls = adapter.fetch_animal_list()
        if urls:
            detail_url = urls[0][0]
            detail_html = adapter._http_get(detail_url)
            samples["detail_url"] = detail_url
            samples["detail_html"] = _compress_html(detail_html)[:MAX_HTML_CHARS]
    except Exception as e:
        samples["detail_html"] = f"<error: {e}>"
    return samples


def build_prompt(
    adapter_code: str,
    adapter_file_rel: str,
    site_config: SiteConfig,
    before: Metrics,
    samples: dict[str, str],
) -> tuple[str, str]:
    """system_msg, user_msg を組み立てる (テストから差し替え可能にするため分離)"""
    schema_doc = (
        "RawAnimalData フィールド:\n"
        "- species: str (犬/猫/その他)\n"
        "- sex: str (オス/メス/不明)\n"
        '- age: str (例 "成犬", "2歳", "推定3歳", "")\n'
        "- color: str (毛色)\n"
        '- size: str (例 "小型"/"中型"/"大型"/"")\n'
        '- shelter_date: str (例 "2026-05-15" or "")\n'
        '- location: str (収容場所、施設名+住所等。なければ "")\n'
        '- phone: str (電話番号、なければ "")\n'
        "- image_urls: list[str] (動物の写真URL)\n"
        "- source_url: str (detail URL)\n"
        '- category: str ("sheltered"/"adoption"/"lost" 等)'
    )
    system_msg = (
        "あなたは Python 製の rule-based HTML スクレイピング adapter を修復する AI です。"
        "対象 adapter は壊れている兆候があります (フィールド欠損率急増 or detail_error)。"
        "実 HTML を読み取り、ラベル/セレクタの不一致を直す unified diff を生成してください。"
    )
    user_msg = f"""## 対象サイト
- 名前: {site_config.name}
- list_url: {site_config.list_url}
- adapter ファイル: {adapter_file_rel}

## 現状の症状 (baseline metrics)
{json.dumps(before.to_dict(), ensure_ascii=False, indent=2)}

## 期待スキーマ (RawAnimalData)
{schema_doc}

## 現在の adapter コード
```python
{adapter_code}
```

## 実HTML (list URL)
```html
{samples.get("list_html", "<not fetched>")}
```

## 実HTML (detail URL: {samples.get("detail_url", "N/A")})
```html
{samples.get("detail_html", "<not fetched>")}
```

## 修正タスク
adapter のラベル/セレクタを実HTML に合わせて修正してください。

制約:
- 修正対象は `{adapter_file_rel}` **のみ**。基底クラス・テスト・他ファイル変更禁止
- 既存クラス名・メソッド名は保持
- 出力は unified diff 形式のみ (説明文・前置き禁止)
- diff のヘッダは `--- a/<path>` `+++ b/<path>` 形式

## 出力フォーマット
```diff
--- a/{adapter_file_rel}
+++ b/{adapter_file_rel}
@@ ... @@
 ...変更内容...
```
"""
    return system_msg, user_msg


def ask_llm_for_patch(
    adapter_code: str,
    adapter_file: Path,
    site_config: SiteConfig,
    before: Metrics,
    samples: dict[str, str],
    model: str = DEFAULT_MODEL,
) -> str:
    """Groq API (OpenAI 互換) に修正パッチを依頼。unified diff を返す。

    既存 GroqProvider と同じ openai SDK + Groq エンドポイント経由。
    `GROQ_API_KEY` 環境変数が必須。
    """
    from openai import OpenAI, RateLimitError  # 遅延 import (テストで mock しやすくするため)

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY 環境変数が未設定です")
    client = OpenAI(api_key=api_key, base_url=GROQ_BASE_URL)
    system_msg, user_msg = build_prompt(
        adapter_code,
        str(adapter_file.relative_to(ROOT)),
        site_config,
        before,
        samples,
    )
    # 並列 dispatch で org 全体の TPM/min を食い合うと 429 (rate_limit) になる。
    # 単発が無料枠内なら、待てば次の分でリセットされるので backoff リトライする。
    # (413 = 単発がサイズ超過は待っても無駄なので、そちらは縮小側で対処済み。)
    for attempt in range(RATE_LIMIT_MAX_RETRIES):
        try:
            response = client.chat.completions.create(
                model=model,
                max_tokens=MAX_OUTPUT_TOKENS,
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": user_msg},
                ],
            )
            break
        except RateLimitError as e:
            if attempt == RATE_LIMIT_MAX_RETRIES - 1:
                raise
            wait = _retry_after_seconds(e) or RATE_LIMIT_DEFAULT_WAIT_SEC
            print(
                f"  rate_limit (attempt {attempt + 1}/{RATE_LIMIT_MAX_RETRIES}): "
                f"{wait}s 待って再試行",
                file=sys.stderr,
            )
            time.sleep(wait)
    text = response.choices[0].message.content or ""
    return extract_diff(text)


def extract_diff(text: str) -> str:
    """LLM 応答から ```diff ... ``` 部分を取り出す。なければ生テキストを返す。"""
    if "```diff" in text:
        return text.split("```diff", 1)[1].split("```", 1)[0].strip()
    if "```" in text:
        # 最初のコードブロックを試す
        parts = text.split("```", 2)
        if len(parts) >= 3:
            chunk = parts[1]
            # 言語指定 'diff' が先頭にあれば除く (lstrip('diff') は文字単位
            # strip になり誤動作するので literal prefix で除去)
            if chunk.startswith("diff"):
                chunk = chunk[4:]
            return chunk.strip()
    return text.strip()


_DIFF_PLUS_RE = re.compile(r"^\+\+\+ (?:b/)?(.+?)\s*$", re.MULTILINE)
_DIFF_MINUS_RE = re.compile(r"^--- (?:a/)?(.+?)\s*$", re.MULTILINE)


def validate_patch_scope(patch_text: str, allowed_files: list[str]) -> tuple[bool, str]:
    """unified diff が `allowed_files` (repo 相対パスのリスト) のみを変更する
    ことを検証する gate。

    LLM が prompt 内の「テスト・他ファイル変更禁止」制約を無視するケースを
    apply_patch の前で reject する。これが無いと、LLM が tests/ を緩めて
    ガード1 (unit test) を欺き、garbage な adapter が auto-merge される
    最悪パスが残る (過去 6 回サイレントドロップを踏んだ領域)。

    Returns:
        (ok, reason). ok=True なら allowed のみ変更。False なら理由付き reject。
    """
    plus_files = set(_DIFF_PLUS_RE.findall(patch_text))
    minus_files = set(_DIFF_MINUS_RE.findall(patch_text))

    if not plus_files and not minus_files:
        return False, "patch contains no file headers (no '--- '/'+++ ' lines)"

    # /dev/null = 新規ファイル作成 (--- /dev/null) / 削除 (+++ /dev/null)
    # adapter 修復のスコープ外。明確に reject。
    if "/dev/null" in plus_files:
        return False, "patch contains file deletion ('+++ /dev/null') — not allowed"
    if "/dev/null" in minus_files:
        return False, "patch contains new file creation ('--- /dev/null') — not allowed"

    all_files = plus_files | minus_files
    allowed_set = set(allowed_files)
    forbidden = sorted(all_files - allowed_set)
    if forbidden:
        return False, f"patch touches files outside allowed scope: {forbidden}"

    return True, "ok"


def apply_patch(
    patch_text: str,
    cwd: Path = ROOT,
    allowed_files: list[str] | None = None,
) -> bool:
    """unified diff を `git apply` で当てる。成功なら True。

    `allowed_files` が指定されている場合、validate_patch_scope で「指定 file
    以外を触らない」ことを apply 前に確認する。違反したら apply せず False を返す。
    """
    if allowed_files is not None:
        ok, reason = validate_patch_scope(patch_text, allowed_files)
        if not ok:
            print(f"patch scope gate failed: {reason}", file=sys.stderr)
            return False
    with tempfile.NamedTemporaryFile("w", suffix=".patch", delete=False, encoding="utf-8") as f:
        f.write(patch_text)
        if not patch_text.endswith("\n"):
            f.write("\n")
        patch_path = f.name
    try:
        # --recount: ハンクヘッダ (@@ -1,5 +1,5 @@) の行数を無視し、実際の行から
        # 再カウントする。LLM (llama) は unified diff の行数を誤りやすく、宣言行数と
        # 実ハンク行数がズレて "corrupt patch" になるのを救う (実測で山梨県の patch が
        # これで当たるようになった)。当たった後はガードテストが内容の妥当性を検証する。
        result = subprocess.run(
            ["git", "apply", "--recount", patch_path],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            print(f"git apply failed: {result.stderr}", file=sys.stderr)
            return False
        return True
    finally:
        os.unlink(patch_path)


def rollback(adapter_file: Path, cwd: Path = ROOT) -> None:
    """git checkout で adapter ファイルをロールバック"""
    subprocess.run(
        ["git", "checkout", "--", str(adapter_file.relative_to(cwd))],
        cwd=cwd,
        capture_output=True,
        check=False,
    )


def run_unit_tests(cwd: Path = ROOT) -> bool:
    """rule_based 配下と normalizer のテストを走らせる。pass なら True。

    validate_patch_scope で「adapter ファイル以外を触らないパッチ」のみ apply
    される保証があるため、normalize() を含む既存テストは確実に変更されていない。
    本テスト pass = adapter の正しさ + normalize 規約 + 既存サイトの非回帰。
    """
    cmd = [
        str(cwd / ".venv/bin/python"),
        "-m",
        "pytest",
        "tests/adapters/rule_based/",
        "tests/domain/test_normalizer.py",
        "-q",
        "--no-header",
    ]
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)
    print((result.stdout or "")[-1500:])
    if result.returncode != 0:
        print((result.stderr or "")[-800:], file=sys.stderr)
    return result.returncode == 0


def verify_no_unexpected_changes(allowed_files: list[str], cwd: Path = ROOT) -> tuple[bool, str]:
    """`git status --porcelain` で allowed_files 以外に変更が無いことを再確認する。

    apply_patch の validate_patch_scope が機能している限り redundant な防御層だが、
    diff parse の取りこぼし (新形式 git diff・rename・mode 変更) や、テスト中に
    他ファイルを副作用で書き換える adapter ロジック (例: ファイル出力) を捕まえる
    最後の砦。

    Returns:
        (ok, reason). ok=True なら allowed のみ dirty。
    """
    # `-uall` を付けて untracked directory を 1 行で集約せず各ファイル単位で
    # 展開する。default だと "tests/" のように dir 単位で集約され、
    # tests/test_x.py の改ざんを path 名で identify できない。
    result = subprocess.run(
        ["git", "status", "--porcelain", "-z", "-uall"],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return False, f"git status failed: {result.stderr}"

    allowed_set = set(allowed_files)
    forbidden: list[str] = []
    # `-z` は NUL 区切り。各エントリは "XY <path>\0" の形式。
    entries = [e for e in result.stdout.split("\0") if e]
    for entry in entries:
        # XY (2 文字 status) + space + path
        if len(entry) < 4:
            continue
        path = entry[3:]
        # rename ("R") の場合は "old\0new" になるが、簡略化のため new だけ見る
        if path not in allowed_set:
            forbidden.append(path)
    if forbidden:
        return False, f"unexpected dirty files: {sorted(forbidden)}"
    return True, "ok"


def evaluate_improvement(before: Metrics, after: Metrics) -> tuple[bool, str]:
    """before/after を比較し、改善があれば (True, reason) を返す。"""
    # status 改善
    if before.status in ("list_error", "detail_error") and after.status == "ok":
        return True, f"status: {before.status} → ok ({after.list_count}件)"
    # 0件 → 取得復活
    if before.status == "empty" and after.status == "ok" and after.list_count > 0:
        return True, f"empty → ok ({after.list_count} 件)"
    # 欠損率の改善 (5%以上の低下)
    if before.missing_rates and after.missing_rates:
        improved = []
        for f, b_rate in before.missing_rates.items():
            a_rate = after.missing_rates.get(f, 1.0)
            if a_rate < b_rate - 0.05:
                improved.append(f"{f}: {b_rate:.0%}→{a_rate:.0%}")
        if improved:
            return True, "improved: " + "; ".join(improved)
    return False, "no improvement detected"


def _slugify(name: str) -> str:
    """サイト名から英数 slug を生成 (ブランチ名用)"""
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", name.lower()).strip("-")
    return slug[:40] or "site"


def create_pr(site_name: str, adapter_file: Path, reason: str, cwd: Path = ROOT) -> str | None:
    """fix/auto-* ブランチで commit + push + PR 作成。PR URL を返す。"""
    slug = _slugify(site_name)
    branch = f"fix/auto-{slug}"
    commit_msg_main = f"fix(auto-{slug}): adapter自動修復"
    pr_title = f"fix(auto): {site_name} adapter自動修復"
    pr_body = (
        "## 自動修復\n\n"
        f"対象サイト: `{site_name}`\n\n"
        "## 改善内容\n"
        f"{reason}\n\n"
        "二重ガード通過済み:\n"
        "- [x] 既存ユニットテスト全件パス\n"
        "- [x] live test で改善定量確認\n\n"
        "🤖 Generated by `scripts/auto_fix_adapter.py`"
    )
    sequence = [
        ["git", "checkout", "-b", branch],
        ["git", "add", str(adapter_file.relative_to(cwd))],
        [
            "git",
            "commit",
            "-m",
            commit_msg_main,
            "-m",
            reason,
            "-m",
            "Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>",
        ],
        ["git", "push", "-u", "origin", branch],
        [
            "gh",
            "pr",
            "create",
            "--base",
            "main",
            "--head",
            branch,
            "--title",
            pr_title,
            "--body",
            pr_body,
            "--label",
            "auto-fix",
        ],
    ]
    last_stdout = ""
    for cmd in sequence:
        result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            print(f"command failed: {' '.join(cmd)}\n{result.stderr}", file=sys.stderr)
            return None
        last_stdout = (result.stdout or "").strip()
    # gh pr create の最後の出力が PR URL
    return last_stdout.splitlines()[-1] if last_stdout else None


def create_issue(site_name: str, reason: str, cwd: Path = ROOT) -> str | None:
    """auto-fix 失敗時に Issue を作成"""
    title = f"adapter 自動修復失敗: {site_name}"
    body = (
        "## 自動修復が失敗しました\n\n"
        f"対象サイト: `{site_name}`\n\n"
        "理由:\n```\n"
        f"{reason}\n```\n\n"
        "手動で adapter の修正が必要です。"
    )
    result = subprocess.run(
        [
            "gh",
            "issue",
            "create",
            "--title",
            title,
            "--body",
            body,
            "--label",
            "adapter-broken",
        ],
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return (result.stdout or "").strip()
    print(f"issue create failed: {result.stderr}", file=sys.stderr)
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="LLM-assisted adapter 自動修復")
    parser.add_argument("--site-name", required=True, help="sites.yaml の name と完全一致")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--dry-run", action="store_true", help="パッチ適用までして PR は作らない")
    args = parser.parse_args()

    print(f"=== auto-fix-adapter: {args.site_name} ===")
    site_config, adapter_cls, adapter_file = load_site(args.site_name)
    print(f"adapter: {adapter_cls.__name__} @ {adapter_file.relative_to(ROOT)}")

    # 1. baseline metrics
    print("\n[1/6] baseline metrics...")
    before = measure(adapter_cls(site_config))
    print(json.dumps(before.to_dict(), ensure_ascii=False, indent=2))

    # 2. HTML サンプル取得
    print("\n[2/6] fetching HTML samples...")
    samples = fetch_html_samples(site_config, adapter_cls)

    # 3. LLM パッチ依頼
    print("\n[3/6] requesting patch from LLM...")
    adapter_code = adapter_file.read_text(encoding="utf-8")
    try:
        patch = ask_llm_for_patch(
            adapter_code, adapter_file, site_config, before, samples, model=args.model
        )
    except Exception as e:
        msg = f"LLM 呼び出し失敗: {e}"
        print(msg, file=sys.stderr)
        if not args.dry_run:
            create_issue(args.site_name, msg)
        return 2
    print(f"patch length: {len(patch)} chars")
    print(patch[:600] + ("..." if len(patch) > 600 else ""))

    # 4. パッチ適用 (adapter ファイル本体のみ変更を許可する gate 付き)
    print("\n[4/6] applying patch...")
    adapter_file_rel = str(adapter_file.relative_to(ROOT))
    if not apply_patch(patch, allowed_files=[adapter_file_rel]):
        msg = (
            "LLM 生成パッチが当たらなかった or 許可スコープ外 "
            f"({adapter_file_rel} 以外のファイル変更を含む可能性)"
        )
        print(msg, file=sys.stderr)
        if not args.dry_run:
            create_issue(args.site_name, msg)
        return 3

    # 5. ガード1: ユニットテスト + 「adapter ファイル外が dirty でない」再確認
    print("\n[5/6] guard 1: unit tests + git status...")
    ok, reason = verify_no_unexpected_changes([adapter_file_rel])
    if not ok:
        print(f"想定外のファイル変更 → ロールバック ({reason})", file=sys.stderr)
        rollback(adapter_file)
        if not args.dry_run:
            create_issue(args.site_name, f"想定外のファイル変更: {reason}")
        return 4
    if not run_unit_tests():
        print("ユニットテスト失敗 → ロールバック", file=sys.stderr)
        rollback(adapter_file)
        if not args.dry_run:
            create_issue(args.site_name, "修正後のユニットテストが失敗しました")
        return 4

    # 6. ガード2: live test の改善定量確認
    print("\n[6/6] guard 2: live test improvement...")
    module = importlib.import_module(adapter_cls.__module__)
    importlib.reload(module)
    new_cls = SiteAdapterRegistry.get(args.site_name) or adapter_cls
    after = measure(new_cls(site_config))
    print("after:", json.dumps(after.to_dict(), ensure_ascii=False, indent=2))
    improved, reason = evaluate_improvement(before, after)
    if not improved:
        print(f"改善なし → ロールバック ({reason})", file=sys.stderr)
        rollback(adapter_file)
        if not args.dry_run:
            create_issue(
                args.site_name,
                f"改善が検出されませんでした: {reason}\n\nbefore:\n{json.dumps(before.to_dict(), ensure_ascii=False, indent=2)}\n\nafter:\n{json.dumps(after.to_dict(), ensure_ascii=False, indent=2)}",
            )
        return 5
    print(f"✓ improvement: {reason}")

    if args.dry_run:
        print("\n[dry-run] PR 作成スキップ。変更はワーキングツリーに残されます。")
        return 0

    # 7. PR 作成
    print("\n[7/7] creating PR...")
    pr_url = create_pr(args.site_name, adapter_file, reason)
    if not pr_url:
        rollback(adapter_file)
        create_issue(args.site_name, "PR 作成失敗 (git push or gh pr create 失敗)")
        return 6
    print(f"PR: {pr_url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
