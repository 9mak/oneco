"""環境省「収容動物の情報を掲載している自治体リンク先一覧」と台帳の差分。

https://www.env.go.jp/nature/dobutsu/aigo/shuyo/link.html に約 130 主体のリンクがある。
これを読み、台帳に無いドメイン（new）と、台帳にあってリンク集に無いドメイン（gone）を出す。

確認済みの差分は registry/discover_known.yaml にドメインごとに持つ（pending = 台帳への追加待ち、
excluded = 対象外、covered = 別ドメインの slug で載せている）。`--notify` では一覧に無い差分だけを
Discord に 1 通送る（同じ差分を毎週繰り返し送らない）。実行時の状態は持たない。
ops/collect.sh が毎週月曜にだけ `discover --notify` を走らせる（2026-10-05 T518）。
"""

from __future__ import annotations

import json
import os
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import httpx
import yaml
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

from .fetch import FetchError, Fetcher
from .registry import ROOT, Source, load_sources

ENV_URL = "https://www.env.go.jp/nature/dobutsu/aigo/shuyo/link.html"
KNOWN_PATH = ROOT / "registry" / "discover_known.yaml"
STATUSES = ("pending", "excluded", "covered")
# リンク集のドメイン数がこれを下回ったら「ページの形が変わった」とみなし、差分は出さない
# （2026-10-05 は 132。全部「消えた」と誤報しないため）
MIN_DOMAINS = 80
REQUEST = "セッションで「差分を台帳に足して」と依頼してください"


class DiscoverError(Exception):
    """リンク集が取れない・形が変わった。"""


@dataclass
class Known:
    status: str                       # pending | excluded | covered
    name: str = ""                    # 自治体名（リンク集の表記）
    note: str = ""                    # 理由・補足
    slugs: list[str] = field(default_factory=list)   # covered: 載せている slug
    task: str = ""                    # pending: 受け持つタスク（例 T519）


@dataclass
class Diff:
    env_count: int                                  # リンク集のドメイン数
    reg_count: int                                  # 台帳のドメイン数
    new: dict[str, list[tuple[str, str]]]           # 台帳に無いリンク集のドメイン → [(URL, 自治体名)]
    gone: list[str]                                 # 台帳にあってリンク集に無いドメイン
    known: dict[str, Known]
    reg_by_domain: dict[str, list[Source]]

    @property
    def unknown_new(self) -> dict[str, list[tuple[str, str]]]:
        return {d: v for d, v in self.new.items() if d not in self.known}

    @property
    def unknown_gone(self) -> list[str]:
        return [d for d in self.gone if d not in self.known]

    @property
    def stale(self) -> list[str]:
        """確認済み一覧にあるが今の差分に無いドメイン（台帳に入った・リンク集から消えた）。一覧から外してよい。"""
        current = set(self.new) | set(self.gone)
        return sorted(d for d in self.known if d not in current)

    def by_status(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for d in sorted(set(self.new) | set(self.gone)):
            if d in self.known:
                out.setdefault(self.known[d].status, []).append(d)
        return out


def _domain(url: str) -> str:
    host = urlsplit(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def load_known(path: Path = KNOWN_PATH) -> dict[str, Known]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out: dict[str, Known] = {}
    for domain, raw in (data.get("domains") or {}).items():
        raw = raw or {}
        status = raw.get("status")
        if status not in STATUSES:
            raise ValueError(f"{path.name}: {domain} の status が不正: {status}（{' / '.join(STATUSES)}）")
        out[domain] = Known(status=status, name=str(raw.get("name") or ""), note=str(raw.get("note") or ""),
                            slugs=list(raw.get("slugs") or []), task=str(raw.get("task") or ""))
    return out


def env_links(html: str) -> dict[str, list[tuple[str, str]]]:
    """リンク集の HTML → 外部ドメイン → [(URL, リンク文字列)]。環境省内のリンクは除く。"""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", XMLParsedAsHTMLWarning)   # リンク集は XHTML（<?xml …?> 付き）
        soup = BeautifulSoup(html, "lxml")
    links: dict[str, list[tuple[str, str]]] = {}
    for a in soup.select("a[href]"):
        href = urljoin(ENV_URL, a["href"])
        if "env.go.jp" in href:
            continue
        links.setdefault(_domain(href), []).append((href, a.get_text(" ", strip=True)))
    return links


def compute(links: dict[str, list[tuple[str, str]]], sources: list[Source], known: dict[str, Known]) -> Diff:
    reg: dict[str, list[Source]] = {}
    for s in sources:
        reg.setdefault(_domain(s.url), []).append(s)
    new = {d: v for d, v in sorted(links.items()) if d not in reg}
    gone = sorted(d for d in reg if d not in links)
    return Diff(len(links), len(reg), new, gone, known, reg)


def _gone_label(diff: Diff, domain: str) -> str:
    srcs = diff.reg_by_domain.get(domain, [])
    return f"{domain}（" + "・".join(f"{s.slug} {s.name}" for s in srcs[:3]) + (" ほか" if len(srcs) > 3 else "") + "）"


def message(diff: Diff) -> str | None:
    """一覧に無い差分の通知文。無ければ None（送らない）。"""
    new, gone = diff.unknown_new, diff.unknown_gone
    if not new and not gone:
        return None
    lines: list[str] = []
    if new:
        lines.append(f"環境省リンク集に新しい自治体 {len(new)} 件（{REQUEST}）")
        for v in new.values():
            url, name = v[0]
            lines.append(f"- {name or '(名前なし)'} {url}")
    if gone:
        lines.append(f"リンク集から消えた {len(gone)} 件（台帳にあるがリンク集に無い。掲載をやめたか移転した可能性。{REQUEST}）")
        for d in gone:
            lines.append(f"- {_gone_label(diff, d)}")
    lines.append("（確認済みにしたら v2/registry/discover_known.yaml に足す）")
    return "\n".join(lines)[:1900]


def failure_message(error: str) -> str:
    return (f"環境省リンク集を読めなかった: {error}\n"
            f"（{ENV_URL} 。日次収集とは無関係で、サイトはふだんどおり。来週も同じなら collector/discover.py を直す）")


def _send(msg: str) -> int:
    url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not url:
        print("DISCORD_WEBHOOK_URL が無いので送らない（表示だけ）")
        return 0
    try:
        httpx.post(url, json={"content": msg}, timeout=15).raise_for_status()
    except httpx.HTTPError as e:
        print(f"Discord に送れなかった: {type(e).__name__}: {e}")
        return 1
    print("Discord に送った")
    return 0


def _fetch_links(fetcher: Fetcher) -> dict[str, list[tuple[str, str]]]:
    try:
        page = fetcher.get(ENV_URL)
    except FetchError as e:
        raise DiscoverError(str(e)) from e
    links = env_links(page.html or "")
    if len(links) < MIN_DOMAINS:
        raise DiscoverError(f"リンクが {len(links)} ドメインしかない（ふだんは 130 前後。{MIN_DOMAINS} 未満）。ページの形が変わった可能性")
    return links


def _print(diff: Diff) -> None:
    print(f"環境省リンク集: {diff.env_count} ドメイン / 台帳: {diff.reg_count} ドメイン")
    print(f"\n台帳に無いドメイン {len(diff.new)} 件:")
    for d, v in diff.new.items():
        k = diff.known.get(d)
        mark = f"[{k.status}]" if k else "[未確認]"
        print(f"- {mark} {d}: {v[0][1]}  {v[0][0]}")
    print(f"\n台帳にあるがリンク集に無いドメイン {len(diff.gone)} 件:")
    for d in diff.gone:
        k = diff.known.get(d)
        print(f"- {'[' + k.status + ']' if k else '[未確認]'} {_gone_label(diff, d)}")
    counts = {s: len(v) for s, v in diff.by_status().items()}
    print(f"\n確認済み（registry/discover_known.yaml）: {counts}")
    print(f"通知すべき差分（未確認）: 新しい {len(diff.unknown_new)} 件・消えた {len(diff.unknown_gone)} 件")
    if diff.stale:
        print(f"確認済み一覧にあるが今の差分に無い {len(diff.stale)} 件（台帳に入った・リンク集から消えた。一覧から外してよい）:")
        for d in diff.stale:
            print(f"- {d}")


def discover(json_out: bool = False, notify: bool = False, *, fetcher: Fetcher | None = None,
             sources: list[Source] | None = None, known_path: Path = KNOWN_PATH) -> int:
    """0 = 差分を出せた（通知の有無は問わない）、1 = リンク集が読めない・形が変わった・送れなかった。"""
    try:
        links = _fetch_links(fetcher or Fetcher())
    except DiscoverError as e:
        msg = failure_message(str(e))
        print(msg)
        if notify:
            _send(msg)
        return 1
    diff = compute(links, load_sources() if sources is None else sources, load_known(known_path))
    if json_out:
        print(json.dumps({"new": diff.new, "gone": diff.gone, "unknown_new": diff.unknown_new,
                          "unknown_gone": diff.unknown_gone, "known": diff.by_status(), "stale": diff.stale},
                         ensure_ascii=False, indent=1))
    else:
        _print(diff)
    if not notify:
        return 0
    msg = message(diff)
    if msg is None:
        print("通知すべき差分なし。送らない")
        return 0
    print("\n---- 通知文 ----\n" + msg)
    return _send(msg)
