"""環境省「収容動物の情報を掲載している自治体リンク先一覧」と台帳の差分。

https://www.env.go.jp/nature/dobutsu/aigo/shuyo/link.html に約 130 主体のリンクがある。
月 1 回これを読み、台帳に無いドメインと、台帳にあってリンク集から消えたドメインを出す。
"""

from __future__ import annotations

import json
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from .fetch import Fetcher
from .registry import load_sources

ENV_URL = "https://www.env.go.jp/nature/dobutsu/aigo/shuyo/link.html"


def _domain(url: str) -> str:
    host = urlsplit(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def discover(json_out: bool = False) -> int:
    page = Fetcher().get(ENV_URL)
    soup = BeautifulSoup(page.html or "", "lxml")
    env_links: dict[str, list[tuple[str, str]]] = {}
    for a in soup.select("a[href]"):
        href = urljoin(ENV_URL, a["href"])
        if "env.go.jp" in href:
            continue
        env_links.setdefault(_domain(href), []).append((href, a.get_text(" ", strip=True)))
    reg = load_sources()
    reg_domains = {_domain(s.url) for s in reg}
    new = {d: v for d, v in env_links.items() if d not in reg_domains}
    gone = sorted(d for d in reg_domains if d not in env_links)
    if json_out:
        print(json.dumps({"new": new, "gone": gone}, ensure_ascii=False, indent=1))
        return 0
    print(f"環境省リンク集: {len(env_links)} ドメイン / 台帳: {len(reg_domains)} ドメイン")
    print(f"\n台帳に無いドメイン {len(new)} 件（候補。人が見て台帳に足す）:")
    for d, v in sorted(new.items()):
        print(f"- {d}: {v[0][1]}  {v[0][0]}")
    print(f"\n台帳にあるがリンク集に無いドメイン {len(gone)} 件（リンク集の網羅漏れか、自治体が掲載をやめた）:")
    for d in gone:
        print(f"- {d}")
    return 0
