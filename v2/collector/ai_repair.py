"""読めなくなったページのレシピを Claude に書き直させる。

流れ: ページを取る → 現行レシピ・docs/RECIPE.md・ページ本文（script/style を除いた HTML、60,000 文字まで）を
Claude に渡す → 返った YAML をその場で実行 → 1 頭以上取れたときだけ recipes/<slug>.yaml を上書きする。
取れなければファイルは触らない（元のまま）。

環境変数: ANTHROPIC_API_KEY（無ければ status "no_key"）、ONECO_AI_MODEL（既定 claude-sonnet-5）。
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import Callable

import yaml
from bs4 import BeautifulSoup

from .extract import Result, build
from .fetch import FetchError, Fetcher
from .recipe import Executor, Recipe, RecipeError
from .registry import ROOT, Source

log = logging.getLogger("collector.repair")

DEFAULT_MODEL = "claude-sonnet-5"
MAX_BODY_CHARS = 60_000
RECIPE_DOC = ROOT / "docs" / "RECIPE.md"

SYSTEM_PROMPT = """あなたは日本の自治体サイトから保護犬猫の一覧を読む「レシピ」（YAML）を書く担当です。
レシピの仕様は与える docs/RECIPE.md の通りで、実行エンジンは固定です（新しい機能は使えません）。
出力は YAML 本文だけにしてください。前置き・説明・コードフェンス（```）は書かないでください。
YAML の先頭に # コメントで「どの要素を 1 頭とみなしたか」を 1〜3 行書いてください。

守ること:
- 1 頭 = rows のセレクタに合う要素 1 つ。見出し・案内文・雛形の行は row_filter で落とす
- 動物とみなされる条件は「写真がある」か「management_no または shelter_date が取れる」。どちらも取れないと全部捨てられる
- 電話・所在地・都道府県・区分はレシピに書かない（台帳の固定値）
- ページに動物が 0 頭なら、その旨の文言を empty_text に入れる
- 台帳の species が mixed のときだけ species を書く（heading / field / text）
- 見えているのは入口ページだけ。steps で別ページへ辿る場合は、リンク先の構造は推測になるので、
  入口ページに一覧があるならそれを直接読む方を優先する
- 現行レシピは壊れているので、そのまま返してはいけない。ページの現状に合わせて直す"""


class RepairError(Exception):
    pass


@dataclass
class RepairResult:
    slug: str
    status: str                  # ok | failed | no_key
    count: int = 0
    error: str | None = None
    recipe_text: str | None = None   # Claude が返した YAML（失敗時も残す）
    saved: bool = False


# --- 入力を作る ---------------------------------------------------------------
def strip_html(html: str, limit: int = MAX_BODY_CHARS) -> str:
    """script / style / noscript / svg / コメントを除いた HTML を limit 文字まで。"""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "svg", "link", "meta"]):
        tag.decompose()
    text = str(soup)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text[:limit]


def build_user_prompt(source: Source, current: str | None, doc: str, body: str, error: str | None) -> str:
    parts = [
        "## 台帳のエントリ",
        f"slug: {source.slug}\nname: {source.name}\nurl: {source.url}\nkind: {source.kind}\nspecies: {source.species}",
        "## 昨日までの失敗理由",
        error or "(不明)",
        "## 現行レシピ（壊れている）",
        current or "(まだ無い。新規に書く)",
        "## レシピの書き方（docs/RECIPE.md）",
        doc,
        f"## ページ本文（script/style 除去済み、先頭 {MAX_BODY_CHARS:,} 文字まで）",
        body,
        "## 指示",
        "このページから今日いる動物を全部読める新しいレシピを YAML だけで返してください。",
    ]
    return "\n\n".join(parts)


def extract_yaml(text: str) -> str:
    """Claude の返答から YAML 本文を取り出す（フェンスが付いていれば剥がす）。"""
    m = re.search(r"```(?:ya?ml)?\s*\n(.*?)```", text, re.S)
    body = m.group(1) if m else text
    return body.strip() + "\n"


# --- Claude 呼び出し（テストではここを差し替える） ------------------------------
def ask_claude(system: str, user: str, model: str) -> str:
    """Claude に問い合わせ、返答テキストを返す。"""
    import anthropic

    client = anthropic.Anthropic()
    try:
        with client.messages.stream(
            model=model,
            max_tokens=16000,
            system=system,
            thinking={"type": "adaptive"},
            messages=[{"role": "user", "content": user}],
        ) as stream:
            msg = stream.get_final_message()
    except anthropic.AuthenticationError as e:
        raise RepairError(f"ANTHROPIC_API_KEY が無効: {e}") from e
    except anthropic.RateLimitError as e:
        raise RepairError(f"レート制限: {e}") from e
    except anthropic.APIStatusError as e:
        raise RepairError(f"API エラー HTTP {e.status_code}: {e}") from e
    except anthropic.APIConnectionError as e:
        raise RepairError(f"API に接続できない: {e}") from e
    if msg.stop_reason == "refusal":
        raise RepairError("Claude が回答を拒否した")
    if msg.stop_reason == "max_tokens":
        raise RepairError("返答が長すぎて途中で切れた")
    text = "".join(b.text for b in msg.content if b.type == "text")
    if not text.strip():
        raise RepairError("Claude の返答が空")
    return text


# --- 実行 -------------------------------------------------------------------
def _try_recipe(source: Source, recipe: Recipe, fetcher: Fetcher) -> Result:
    ex = Executor(fetcher, recipe)
    docs = ex.resolve(source.url)
    return build(source, recipe, docs, getattr(ex, "visited", None))


def repair(
    source: Source,
    fetcher: Fetcher | None = None,
    model: str | None = None,
    error: str | None = None,
    ask: Callable[[str, str, str], str] | None = None,
    save: bool = True,
) -> RepairResult:
    """1 回だけ Claude にレシピを書かせ、1 頭以上取れたら保存する。"""
    slug = source.slug
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return RepairResult(slug, "no_key", error="ANTHROPIC_API_KEY 未設定")
    if source.mode != "recipe":
        return RepairResult(slug, "failed", error=f"mode={source.mode} は修復対象外")
    fetcher = fetcher or Fetcher()
    model = model or os.environ.get("ONECO_AI_MODEL") or DEFAULT_MODEL
    ask = ask or ask_claude

    # 1. ページ本文
    try:
        page = fetcher.get(source.url)
    except FetchError as e:
        return RepairResult(slug, "failed", error=f"ページが取れないので修復できない: {e}")
    if page.html is None:
        body = "(入口 URL が PDF などテキストでない文書。PDF 方式のレシピが必要)"
    else:
        body = strip_html(page.html)

    # 2. 入力
    path = source.recipe_path
    original = path.read_text(encoding="utf-8") if path.exists() else None
    doc = RECIPE_DOC.read_text(encoding="utf-8") if RECIPE_DOC.exists() else "(docs/RECIPE.md が無い)"
    user = build_user_prompt(source, original, doc, body, error)

    # 3. Claude
    try:
        answer = ask(SYSTEM_PROMPT, user, model)
    except RepairError as e:
        return RepairResult(slug, "failed", error=str(e))
    recipe_text = extract_yaml(answer)

    # 4. 保存前に実行して確かめる
    try:
        raw = yaml.safe_load(recipe_text)
        if not isinstance(raw, dict):
            raise RepairError("返答が YAML のマッピングでない")
        recipe = Recipe.from_dict(raw)
        res = _try_recipe(source, recipe, fetcher)
    except (yaml.YAMLError, RecipeError, FetchError, RepairError, TypeError, ValueError) as e:
        return RepairResult(slug, "failed", error=f"新レシピが動かない: {type(e).__name__}: {e}", recipe_text=recipe_text)
    except Exception as e:  # noqa: BLE001 — 生成されたレシピが何を起こすか分からない
        log.exception("%s: 新レシピの実行で例外", slug)
        return RepairResult(slug, "failed", error=f"新レシピが動かない: {type(e).__name__}: {e}", recipe_text=recipe_text)
    if not res.animals:
        why = f"新レシピでも 0 頭（行 {res.rows}・捨てた {len(res.dropped)}" + ("・empty_text あり" if res.empty_confirmed else "") + "）"
        return RepairResult(slug, "failed", error=why, recipe_text=recipe_text)

    # 5. 1 頭以上取れたときだけ上書き
    if save:
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            path.write_text(recipe_text, encoding="utf-8")
            Recipe.load(path)   # 書いたものが読み直せることを確認
        except Exception as e:  # noqa: BLE001
            if original is None:
                path.unlink(missing_ok=True)
            else:
                path.write_text(original, encoding="utf-8")
            return RepairResult(slug, "failed", error=f"保存に失敗したので元に戻した: {e}", recipe_text=recipe_text)
    return RepairResult(slug, "ok", count=len(res.animals), recipe_text=recipe_text, saved=save)
