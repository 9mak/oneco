#!/usr/bin/env python3
"""PoC: LLM-generated CSS selectors for rule-based animal data extraction.

Validates the hypothesis that Groq can generate reusable CSS selectors
from a sample HTML page, which can then be cached and applied for
maintenance-free rule-based extraction (LLM only re-runs when selectors break).

Target: 高知県動物愛護センター (kochi-apc.com)
- 既存 KochiAdapter (798 lines, hand-written) との突合用
- jouto (譲渡) ページで selector 生成 → 詳細1件で適用テスト

Usage:
    source .envrc  # GROQ_API_KEY required
    python3 scripts/poc_selector_gen.py
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
import yaml
from bs4 import BeautifulSoup

# ─────────────────────────── Config ───────────────────────────
PRESETS = {
    "kochi": {
        "label": "高知県動物愛護センター",
        "list_url": "https://kochi-apc.com/jouto/",
        "anchor": "/center-data/",  # used to find a representative window
    },
    "takamatsu-dog": {
        "label": "高松市 わんにゃん高松（収容中犬）",
        "list_url": "https://www.city.takamatsu.kagawa.jp/udanimo/ani_infolist1.html?infotype=1&animaltype=1",
        "anchor": "ani_infodetail",
    },
    "ehime-shelter": {
        "label": "愛媛県動物愛護センター（収容中, single_page）",
        "list_url": "https://www.pref.ehime.jp/page/16976.html",
        "anchor": None,  # single_page: no detail link
        "single_page": True,
    },
}

GROQ_MODEL = "llama-3.3-70b-versatile"
GROQ_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
HTML_MAX_CHARS = 12_000  # ≈ 3k tokens, safe for Groq free-tier TPM limits
CACHE_DIR = Path(__file__).parent / "poc_selectors"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36 "
    "(oneco PoC selector generator)"
)
HTTP_HEADERS = {"User-Agent": USER_AGENT}


# ─────────────────────────── Prompts ───────────────────────────
LIST_PROMPT = """あなたはWebスクレイピングの専門家です。
以下は保護動物の一覧ページHTMLです。各動物カードを抽出するためのCSSセレクタを設計してください。

# 出力フォーマット (JSON)
```json
{
  "card_selector": "個別の動物カードを囲む要素のCSSセレクタ",
  "fields": {
    "detail_url": {"selector": "card内の詳細ページリンク", "attr": "href"},
    "image_url":  {"selector": "card内の画像", "attr": "src"},
    "title":      {"selector": "card内のタイトル/名前", "attr": "text"}
  },
  "notes": "判断理由や注意点"
}
```

# 制約
- selector は BeautifulSoup の .select() で動くCSS構文で
- 取得不能な場合は selector を null
- card_selector で .select() した後、各 field selector はカード内で .select_one() される前提

# HTML
"""

DETAIL_PROMPT = """あなたはWebスクレイピングの専門家です。
以下は保護動物の詳細ページHTMLです。各フィールドを抽出するためのCSSセレクタを設計してください。

# 出力フォーマット (JSON)
```json
{
  "fields": {
    "species":      {"selector": "...", "attr": "text", "regex_extract": "(犬|猫)"},
    "sex":          {"selector": "...", "attr": "text"},
    "age":          {"selector": "...", "attr": "text"},
    "color":        {"selector": "...", "attr": "text"},
    "size":         {"selector": "...", "attr": "text"},
    "shelter_date": {"selector": "...", "attr": "text"},
    "location":     {"selector": "...", "attr": "text"},
    "phone":        {"selector": "...", "attr": "text"},
    "image_urls":   {"selector": "...", "attr": "src", "multi": true}
  },
  "notes": "判断理由や注意点"
}
```

# 制約
- 定義リスト (<dt>項目名</dt><dd>値</dd>) パターンが頻出
- テーブル (<th>項目名</th><td>値</td>) パターンも頻出
- 取得不能な場合は selector を null
- 値だけを取れるセレクタを優先 (項目名を含めない)
- regex_extract が指定されたら text からその正規表現でグループ1を抽出

# HTML
"""


# ─────────────────────────── HTTP / LLM ───────────────────────────
def fetch(url: str) -> str:
    resp = requests.get(url, headers=HTTP_HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.text


def clean_html(html: str) -> str:
    """Strip noise + reduce attribute clutter, return only <body> contents.

    Note: do NOT decompose <head> — some WordPress themes have malformed HTML
    where decomposing head also strips body content (parser treats them as
    siblings). Instead, extract body separately and operate on that.
    """
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "iframe", "svg"]):
        tag.decompose()

    body = soup.find("body")
    if body is None:
        body = soup  # fallback

    keep_attrs = {"class", "id", "href", "src", "alt", "title"}
    for el in body.find_all(True):
        el.attrs = {k: v for k, v in el.attrs.items() if k in keep_attrs}

    text = str(body)
    text = re.sub(r"\n\s*\n", "\n", text)
    return text


def extract_sample(html: str, anchor: str, window: int = 5000) -> str:
    """Take a window of HTML around the first occurrence of `anchor`.

    Used to give the LLM a representative sample without sending the whole page.
    """
    idx = html.find(anchor)
    if idx < 0:
        return html[:window]
    start = max(0, idx - window // 2)
    end = min(len(html), idx + window // 2)
    return html[start:end]


def call_groq(prompt: str, html: str) -> tuple[dict[str, Any], dict[str, int]]:
    """Send prompt+html to Groq, return parsed JSON and token usage."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY not set. Run `source .envrc` or check Keychain entry."
        )

    truncated = html[:HTML_MAX_CHARS]
    body = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "user", "content": prompt + "\n```html\n" + truncated + "\n```"}
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.1,
    }
    resp = requests.post(
        GROQ_ENDPOINT,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=body,
        timeout=120,
    )
    if not resp.ok:
        print(f"\n!! Groq API error {resp.status_code}: {resp.text[:500]}")
        resp.raise_for_status()
    payload = resp.json()
    content = payload["choices"][0]["message"]["content"]
    usage = payload.get("usage", {})
    return json.loads(content), usage


# ─────────────────────────── Selector application ───────────────────────────
def apply_list_selectors(html: str, selectors: dict[str, Any]) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    card_sel = selectors.get("card_selector")
    if not card_sel:
        return []
    cards = soup.select(card_sel)
    out = []
    for card in cards:
        item: dict[str, Any] = {}
        for name, spec in (selectors.get("fields") or {}).items():
            sel = spec.get("selector")
            if not sel:
                item[name] = None
                continue
            el = card.select_one(sel)
            if el is None:
                item[name] = None
                continue
            attr = spec.get("attr", "text")
            item[name] = el.get_text(strip=True) if attr == "text" else el.get(attr)
        out.append(item)
    return out


def apply_detail_selectors(html: str, selectors: dict[str, Any]) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    out: dict[str, Any] = {}
    for name, spec in (selectors.get("fields") or {}).items():
        sel = spec.get("selector")
        if not sel:
            out[name] = None
            continue
        attr = spec.get("attr", "text")
        if spec.get("multi"):
            els = soup.select(sel)
            out[name] = [
                (e.get_text(strip=True) if attr == "text" else e.get(attr)) for e in els
            ]
            continue
        el = soup.select_one(sel)
        if el is None:
            out[name] = None
            continue
        val = el.get_text(strip=True) if attr == "text" else el.get(attr)
        if regex := spec.get("regex_extract"):
            m = re.search(regex, val or "")
            val = m.group(1) if m else None
        out[name] = val
    return out


# ─────────────────────────── Main flow ───────────────────────────
def run_one(preset_key: str) -> dict[str, Any]:
    """Run the PoC against a single preset and return a result summary."""
    preset = PRESETS[preset_key]
    list_url = preset["list_url"]
    anchor = preset.get("anchor")
    single_page = preset.get("single_page", False)

    print("\n" + "=" * 70)
    print(f"PRESET: {preset_key} — {preset['label']}")
    print(f"URL:    {list_url}")
    if single_page:
        print("MODE:   single_page (no detail step)")
    print("=" * 70)

    summary: dict[str, Any] = {
        "preset": preset_key,
        "label": preset["label"],
        "list_url": list_url,
        "tokens": 0,
    }

    # ── Step 1: List page ──
    print(f"\n[1] Fetching list page...")
    t0 = time.time()
    try:
        list_html = fetch(list_url)
    except Exception as e:
        print(f"      FETCH FAILED: {e}")
        summary["error"] = f"fetch: {e}"
        return summary
    print(f"      raw: {len(list_html):,} chars ({time.time() - t0:.1f}s)")
    list_clean = clean_html(list_html)
    print(f"      cleaned: {len(list_clean):,} chars")

    # ── Step 2: Generate list selectors ──
    if anchor:
        list_sample = extract_sample(list_clean, anchor, window=8000)
        print(f"      sample: {len(list_sample):,} chars (window around '{anchor}')")
    else:
        list_sample = list_clean[:HTML_MAX_CHARS]
        print(f"      sample: {len(list_sample):,} chars (truncated to {HTML_MAX_CHARS})")

    print("\n[2] Generating list-page selectors via Groq...")
    t0 = time.time()
    try:
        list_selectors, list_usage = call_groq(LIST_PROMPT, list_sample)
    except Exception as e:
        print(f"      LLM FAILED: {e}")
        summary["error"] = f"llm-list: {e}"
        return summary
    summary["tokens"] += list_usage.get("total_tokens", 0)
    print(f"      response in {time.time() - t0:.1f}s, tokens={list_usage.get('total_tokens')}")
    print(f"      selectors: {json.dumps(list_selectors, ensure_ascii=False)}")

    # ── Step 3: Apply ──
    cards = apply_list_selectors(list_html, list_selectors)
    summary["cards_extracted"] = len(cards)
    summary["list_selectors"] = list_selectors
    print(f"\n[3] Extracted {len(cards)} cards")
    for i, card in enumerate(cards[:3]):
        # truncate long values for readability
        printable = {k: (v[:60] + "..." if isinstance(v, str) and len(v) > 60 else v) for k, v in card.items()}
        print(f"      [{i}] {printable}")
    if len(cards) > 3:
        print(f"      ... +{len(cards) - 3} more")

    if single_page:
        summary["mode"] = "single_page"
        return summary

    # ── Step 4: Detail page sample ──
    detail_url = None
    for c in cards:
        u = c.get("detail_url")
        if u and isinstance(u, str):
            detail_url = urljoin(list_url, u)
            break
    if not detail_url:
        print("\n[4] No detail_url found — skipping detail step.")
        summary["detail_skipped"] = "no detail_url"
        return summary

    print(f"\n[4] Detail page sample: {detail_url}")
    try:
        detail_html = fetch(detail_url)
    except Exception as e:
        print(f"      FETCH FAILED: {e}")
        summary["detail_error"] = str(e)
        return summary
    detail_clean = clean_html(detail_html)
    detail_sample = detail_clean[:HTML_MAX_CHARS]
    print(f"      cleaned: {len(detail_clean):,} chars, sample: {len(detail_sample):,}")

    print("      generating detail-page selectors...")
    t0 = time.time()
    try:
        detail_selectors, detail_usage = call_groq(DETAIL_PROMPT, detail_sample)
    except Exception as e:
        print(f"      LLM FAILED: {e}")
        summary["detail_error"] = str(e)
        return summary
    summary["tokens"] += detail_usage.get("total_tokens", 0)
    print(f"      response in {time.time() - t0:.1f}s, tokens={detail_usage.get('total_tokens')}")

    detail_data = apply_detail_selectors(detail_html, detail_selectors)
    summary["detail_data"] = detail_data
    summary["detail_selectors"] = detail_selectors
    summary["detail_url"] = detail_url
    print("      extracted detail:")
    for k, v in detail_data.items():
        v_print = v if not isinstance(v, list) else f"[{len(v)} items]"
        print(f"        {k}: {v_print}")

    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="PoC: LLM-generated selectors")
    parser.add_argument(
        "presets",
        nargs="*",
        default=["kochi"],
        help=f"preset keys to run (one or more). Available: {', '.join(PRESETS)}",
    )
    args = parser.parse_args()

    invalid = [p for p in args.presets if p not in PRESETS]
    if invalid:
        print(f"Unknown presets: {invalid}. Available: {list(PRESETS)}")
        return 2

    CACHE_DIR.mkdir(exist_ok=True)
    results = []
    for key in args.presets:
        try:
            r = run_one(key)
        except Exception as e:
            r = {"preset": key, "error": f"unhandled: {e}"}
        results.append(r)
        # save individual result
        out = CACHE_DIR / f"{key}.yaml"
        out.write_text(yaml.safe_dump(r, allow_unicode=True, sort_keys=False, default_flow_style=False))
        print(f"\n  saved → {out}")
        time.sleep(2)  # rate-limit kindness

    # ── Cross-site summary ──
    print("\n\n" + "=" * 70)
    print("CROSS-SITE SUMMARY")
    print("=" * 70)
    total_tokens = sum(r.get("tokens", 0) for r in results)
    print(f"{'Preset':<20} {'Cards':>8} {'Tokens':>10} {'Status':<20}")
    print("-" * 70)
    for r in results:
        status = r.get("error") or r.get("detail_error") or r.get("mode", "OK")
        cards = r.get("cards_extracted", "-")
        print(f"{r['preset']:<20} {cards:>8} {r.get('tokens', 0):>10,} {str(status)[:20]:<20}")
    print("-" * 70)
    print(f"Total tokens: {total_tokens:,} ({total_tokens / 1000:.1f}k)")
    print(f"Groq free tier remaining today: ~{(100_000 - total_tokens) / 1000:.0f}k tokens")

    return 0


if __name__ == "__main__":
    sys.exit(main())
