"""台帳（registry/sources.yaml）の電話・所在地を元ページで全件突合し、provenance（verified_at・verified_url）を付ける監査ツール（W006 T616）。

  python ops/verify_registry.py --dry-run --out data/verify-registry-YYYY-MM-DD.json
  python ops/verify_registry.py --only city_yokkaichi --dry-run
  python ops/verify_registry.py --write      # 全項目が元ページで確認できた entry にだけ verified_at / verified_url を書く

自治体サーバーへの配慮: 同時 4・同一ホストは 1 秒以上あける・タイムアウト 20 秒・1 URL 1 回。
不一致があっても exit 0（監査ツール）。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import time
import unicodedata
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlsplit

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from collector.registry import REGISTRY_PATH, Source, load_sources, select  # noqa: E402

UA = "Mozilla/5.0 (compatible; oneco-linkcheck/1.0; +https://github.com/9mak/oneco)"
TIMEOUT = 20
HOST_INTERVAL = 1.0
MAX_FOLLOW = 3
LINK_KEYWORDS = re.compile(r"お問い合わせ|お問合せ|問合せ|問い合わせ|連絡先|アクセス|施設案内|センター|about|contact|access", re.I)
SKIP_EXT = re.compile(r"\.(pdf|jpe?g|png|gif|zip|xlsx?|docx?|pptx?)(\?|$)", re.I)


@dataclass
class Fetched:
    url: str
    html: str | None
    error: str | None


Fetch = Callable[[str], Fetched]


# --- 正規化 ---

_KANJI = {"〇": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_KANJI_RUN = re.compile(r"[〇一二三四五六七八九十百]+(?=丁目|丁|番地|番(?!町)|号)")
_HYPHENS = "‐‑‒–—―−ーｰ"
_DIGIT_JOINER = re.compile(rf"(?<=\d)[{_HYPHENS}の](?=\d)")
_PREF = re.compile(r"^(?:北海道|東京都|京都府|大阪府|.{2,3}県)")


def _kanji_to_int(s: str) -> int:
    total, cur = 0, 0
    for ch in s:
        if ch == "百":
            total += (cur or 1) * 100
            cur = 0
        elif ch == "十":
            total += (cur or 1) * 10
            cur = 0
        else:
            cur = cur * 10 + _KANJI[ch]
    return total + cur


def digits(s: str) -> str:
    """数字だけ残す（全角・各種ハイフン・括弧・スペースは落ちる）。"""
    return re.sub(r"\D", "", unicodedata.normalize("NFKC", s))


def normalize_text(s: str, sep: str = "") -> str:
    """所在地照合用: NFKC・漢数字→算用数字・丁目/番/号→ハイフン区切り・空白除去（sep を渡すと空白をその文字に置き換える）。"""
    s = unicodedata.normalize("NFKC", s)
    s = _KANJI_RUN.sub(lambda m: str(_kanji_to_int(m.group())), s)
    s = re.sub(r"\s+", sep, s)
    s = _DIGIT_JOINER.sub("-", s)
    s = re.sub(r"(\d+)丁目", r"\1-", s)
    s = re.sub(r"(\d+)番地?(?!町)", r"\1-", s)
    s = re.sub(r"(\d+)号", r"\1", s)
    s = re.sub(r"-の(?=\d)", "-", s)
    return re.sub(r"-{2,}", "-", s)


def address_head(address: str) -> str:
    """台帳の所在地から照合キー（都道府県・括弧書き・郵便番号を除き、番地の先頭＝丁目・番まで）を作る。"""
    a = re.sub(r"[（(][^）)]*[）)]", "", unicodedata.normalize("NFKC", address))
    a = re.sub(r"^〒?\s*\d{3}-?\d{4}\s*", "", a)
    a = normalize_text(a)
    a = _PREF.sub("", a)
    m = re.match(r"^(\D*\d+(?:-\d+)?)", a)
    return (m.group(1) if m else a).rstrip("-")


def town_key(head: str) -> str | None:
    """head から先頭の「○○市／町／村／郡」を外した町名＋番地。短すぎる・番地が無いものは使わない。"""
    t = re.sub(r"^.+?[市町村郡]+", "", head, count=1)
    return t if len(t) >= 4 and re.search(r"\d", t) else None


def contains_town(text: str, town: str) -> bool:
    """市名なしの町名＋番地が、別の町名・数字の途中でなく単独で現れるか（郵便番号の直後は許す）。"""
    t = normalize_text(text, sep="|")
    t = re.sub(r"〒?(?<!\d)\d{3}-\d{4}(?!\d)", "|", t)
    return re.search(r"(?<!\w)" + re.escape(town) + r"(?!\d)", t) is not None


def contains_address(text_norm: str, head: str) -> bool:
    return re.search(re.escape(head) + r"(?!\d)", text_norm) is not None


# --- HTML ---

def parse_html(html: str, base_url: str) -> tuple[str, list[tuple[str, str]]]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    links = [(a.get_text(" ", strip=True), urldefrag(urljoin(base_url, a["href"]))[0])
             for a in soup.find_all("a", href=True)]
    for t in soup(["script", "style", "noscript"]):
        t.decompose()
    return soup.get_text(" "), links


def pick_links(links: list[tuple[str, str]], base_url: str) -> list[str]:
    host = urlsplit(base_url).netloc
    seen = {urldefrag(base_url)[0]}
    out: list[str] = []
    for label, u in links:
        sp = urlsplit(u)
        if sp.scheme not in ("http", "https") or sp.netloc != host or u in seen or SKIP_EXT.search(u):
            continue
        if LINK_KEYWORDS.search(label) or LINK_KEYWORDS.search(u):
            seen.add(u)
            out.append(u)
            if len(out) == MAX_FOLLOW:
                break
    return out


# 電話番号の形に切り出す。左右に数字（や「-数字」の続き）があるものは別の数字列の一部なので拾わない
_PHONE_RE = re.compile(r"(?<![\d-])0\d{1,4}[-(（)）\s]*\d{1,4}[-)）\s]*\d{3,4}(?!\d)(?!-\d)")


def phone_candidates(text: str) -> list[str]:
    t = unicodedata.normalize("NFKC", text)
    t = re.sub(f"[{_HYPHENS}]", "-", t)
    return [m.group() for m in _PHONE_RE.finditer(t)]


FOOTER_CHARS = 1500


def phone_only_in_footer(html: str, want_digits: str) -> bool:
    """番号がページ末尾（<footer> 内、無ければ最後の 1,500 文字）にしか出ないか。県庁・市役所の代表番号を拾った疑いの目印。"""
    from bs4 import BeautifulSoup

    def has(t: str) -> bool:
        return want_digits in {digits(c) for c in phone_candidates(t)}

    soup = BeautifulSoup(html, "lxml")
    for t in soup(["script", "style", "noscript"]):
        t.decompose()
    footers = soup.find_all("footer")
    if footers:
        foot = " ".join(f.get_text(" ") for f in footers)
        for f in footers:
            f.decompose()
        rest = soup.get_text(" ")
        if has(foot) and not has(rest):
            return True
        if has(rest):
            return False
    text = soup.get_text(" ") if not footers else foot + " " + rest
    text = re.sub(r"\s+", " ", text)
    return has(text[-FOOTER_CHARS:]) and not has(text[:-FOOTER_CHARS])


def nearby_phones(text: str, want: str, limit: int = 3) -> list[str]:
    want_d = digits(want)
    found: list[str] = []
    for raw in phone_candidates(text):
        v = re.sub(r"[()\s]+", "-", raw).strip("-")
        if digits(v) != want_d and v not in found:
            found.append(v)
    found.sort(key=lambda v: (digits(v)[:3] != want_d[:3], digits(v)[-4:] != want_d[-4:]))
    return found[:limit]


def nearby_addresses(text_norm: str, head: str, limit: int = 3) -> list[str]:
    m = re.match(r"^(\D+)", head)
    if not m or len(m.group(1)) < 3:
        return []
    out: list[str] = []
    for x in re.finditer(re.escape(m.group(1)) + r"\d+(?:-\d+)*", text_norm):
        if x.group() not in out:
            out.append(x.group())
    return out[:limit]


# --- 判定 ---

@dataclass
class GroupResult:
    phone_found: bool | None
    address_found: bool | None
    evidence_url: str | None
    phone_url: str | None
    address_url: str | None
    fetched_at: str
    reason: str
    phone_footer_only: bool | None = None  # 番号が見つかったページで、フッターにしか出ないか
    address_match: str | None = None  # "full"=市区町村名＋番地 / "town"=市名を省いた町名＋番地
    pages: list[str] = field(default_factory=list)
    nearby_phones: list[str] = field(default_factory=list)
    nearby_addresses: list[str] = field(default_factory=list)


def verify_group(fetch: Fetch, url: str, phone: str | None, address: str | None) -> GroupResult:
    want_phone = digits(phone) if phone else None
    head = address_head(address) if address else None
    r = GroupResult(
        phone_found=False if want_phone else None,
        address_found=False if head else None,
        evidence_url=None, phone_url=None, address_url=None,
        fetched_at=datetime.now().astimezone().isoformat(timespec="seconds"), reason="",
    )
    if not want_phone and not head:
        r.reason = "台帳に電話も所在地も無い"
        return r
    town = town_key(head) if head else None
    errors: list[str] = []
    texts: list[str] = []

    def check(u: str) -> list[tuple[str, str]] | None:
        f = fetch(u)
        if f.html is None:
            errors.append(f"{u}: {f.error}")
            return None
        try:
            text, links = parse_html(f.html, u)
        except Exception as e:
            errors.append(f"{u}: 解析失敗 {type(e).__name__}: {str(e)[:100]}")
            return None
        r.pages.append(u)
        texts.append(text)
        if want_phone and not r.phone_found and want_phone in {digits(c) for c in phone_candidates(text)}:
            r.phone_found, r.phone_url = True, u
            r.phone_footer_only = phone_only_in_footer(f.html, want_phone)
        if head and not r.address_found:
            tn = normalize_text(text)
            if contains_address(tn, head):
                r.address_found, r.address_url, r.address_match = True, u, "full"
            elif town and contains_town(text, town):
                # ページが市名を省いて「風早2-4-3」とだけ書く場合。町名＋番地で一致扱いにし、明細に "town" と残す
                r.address_found, r.address_url, r.address_match = True, u, "town"
        return links

    def done() -> bool:
        return r.phone_found is not False and r.address_found is not False

    links = check(url)
    if links is not None and not done():
        for u in pick_links(links, url):
            check(u)
            if done():
                break
    r.evidence_url = r.phone_url or r.address_url
    if not r.pages:
        r.reason = "取得不能: " + "; ".join(errors)
    elif done():
        r.reason = "全項目を元ページで確認"
    else:
        miss = [n for n, v in (("電話", r.phone_found), ("所在地", r.address_found)) if v is False]
        r.reason = "ページ内に無い: " + "・".join(miss) + f"（見たページ {len(r.pages)} 件）"
        alltext = " ".join(texts)
        if r.phone_found is False and phone:
            r.nearby_phones = nearby_phones(alltext, phone)
        if r.address_found is False and head:
            r.nearby_addresses = nearby_addresses(normalize_text(alltext), head)
    if errors and r.pages:
        r.reason += "（辿り先の取得失敗: " + "; ".join(errors) + "）"
    return r


def verified_urls(r: GroupResult) -> tuple[str | None, str | None] | None:
    """書き戻せる根拠 (電話のページ, 所在地のページ)。台帳にある項目がすべて確認でき、所在地は市名つきの full 一致だけ。台帳に無い項目は None。"""
    if r.phone_found is None and r.address_found is None:
        return None
    if r.phone_found is False or r.address_found is False:
        return None
    if r.address_found and r.address_match != "full":
        return None
    return r.phone_url, r.address_url


def classify(r: GroupResult) -> str:
    if r.phone_found is None and r.address_found is None:
        return "no_data"
    if not r.pages:
        return "unfetchable"
    vals = [v for v in (r.phone_found, r.address_found) if v is not None]
    if all(vals):
        return "match"
    return "partial" if any(vals) else "mismatch"


# --- 全件実行 ---

def run(sources: list[Source], fetch: Fetch, workers: int = 4, today: str = "") -> dict[str, GroupResult]:
    """(municipality, phone, address) の組ごとに 1 回だけ取得し、結果を組の全 slug で共有する。"""
    groups: dict[tuple[str, str | None, str | None], list[Source]] = {}
    for s in sources:
        groups.setdefault((s.municipality, s.phone, s.address), []).append(s)

    def work(item):
        (_, phone, address), members = item
        return members, verify_group(fetch, members[0].url, phone, address)

    results: dict[str, GroupResult] = {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for members, res in ex.map(work, list(groups.items())):
            for m in members:
                results[m.slug] = res
    return {s.slug: results[s.slug] for s in sources}


def summarize(results: dict[str, GroupResult]) -> dict[str, int]:
    out = {"total": len(results), "match": 0, "partial": 0, "mismatch": 0, "unfetchable": 0, "no_data": 0}
    for r in results.values():
        out[classify(r)] += 1
    return out


# --- 実フェッチ ---

class _Throttle:
    """同一ホストへは直列＋最低 interval 秒あける。"""

    def __init__(self, interval: float) -> None:
        self.interval = interval
        self._last: dict[str, float] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    def wait(self, host: str) -> threading.Lock:
        with self._guard:
            lock = self._locks.setdefault(host, threading.Lock())
        lock.acquire()
        gap = self._last.get(host, 0) + self.interval - time.monotonic()
        if gap > 0:
            time.sleep(gap)
        return lock

    def done(self, host: str, lock: threading.Lock) -> None:
        self._last[host] = time.monotonic()
        lock.release()


def make_http_fetch() -> Fetch:
    import httpx
    from bs4 import UnicodeDammit

    throttle = _Throttle(HOST_INTERVAL)
    client = httpx.Client(follow_redirects=True, timeout=TIMEOUT, headers={"User-Agent": UA})

    def fetch(url: str) -> Fetched:
        host = urlsplit(url).netloc
        lock = throttle.wait(host)
        try:
            resp = client.get(url)
        except Exception as e:
            return Fetched(url, None, f"{type(e).__name__}: {str(e)[:120]}")
        finally:
            throttle.done(host, lock)
        if resp.status_code >= 400:
            return Fetched(url, None, f"HTTP {resp.status_code}")
        ct = resp.headers.get("content-type", "")
        if "pdf" in ct or resp.content[:4] == b"%PDF":
            return Fetched(url, None, "PDF（本文を読まない）")
        enc = resp.charset_encoding
        dammit = UnicodeDammit(resp.content, [enc] if enc else [], is_html=True)
        return Fetched(url, dammit.unicode_markup or resp.text, None)

    return fetch


# --- 書き戻し ---

def write_back(path: Path, results: dict[str, GroupResult], today: str) -> int:
    """verified_urls が返す entry の url 行の直後に verified_at / verified_phone_url / verified_address_url を置く（既存行は置換）。コメント・並びは触らない。"""
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    out: list[str] = []
    n = 0
    i = 0
    while i < len(lines):
        m = re.match(r"^- slug: (\S+)\s*$", lines[i])
        if not m:
            out.append(lines[i])
            i += 1
            continue
        j = i + 1
        while j < len(lines) and not lines[j].startswith("- slug:"):
            j += 1
        block = lines[i:j]
        res = results.get(m.group(1))
        urls = verified_urls(res) if res is not None else None
        if urls is not None:
            block = [ln for ln in block if not re.match(r"^  verified_(at|url|phone_url|address_url):", ln)]
            k = next((x for x, ln in enumerate(block) if ln.startswith("  url:")), None)
            if k is not None:
                new = [f"  verified_at: '{today}'\n"]
                if urls[0]:
                    new.append(f"  verified_phone_url: {json.dumps(urls[0])}\n")
                if urls[1]:
                    new.append(f"  verified_address_url: {json.dumps(urls[1])}\n")
                block[k + 1:k + 1] = new
                n += 1
        out.extend(block)
        i = j
    path.write_text("".join(out), encoding="utf-8")
    return n


# --- CLI ---

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--registry", default=str(REGISTRY_PATH))
    ap.add_argument("--only", help="slug 前方一致")
    ap.add_argument("--dry-run", action="store_true", help="台帳に書き戻さない（--write が無ければ元から書かない）")
    ap.add_argument("--out", help="結果の明細 JSON")
    ap.add_argument("--write", action="store_true", help="確認できた entry に verified_at / verified_url を書き戻す")
    ap.add_argument("--footer-only", action="store_true", help="電話番号がページ末尾（フッター）にしか出ない entry の一覧も出す")
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args(argv)
    import warnings

    from bs4 import XMLParsedAsHTMLWarning

    warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

    path = Path(a.registry)
    srcs = select(load_sources(path), a.only)
    today = datetime.now().date().isoformat()
    t0 = time.monotonic()
    groups = len({(s.municipality, s.phone, s.address) for s in srcs})
    print(f"{len(srcs)} 件（取得単位 {groups} 組）を突合します", flush=True)
    results = run(srcs, make_http_fetch(), workers=min(a.workers, 4), today=today)
    secs = time.monotonic() - t0
    summ = summarize(results)
    print(f"所要 {secs:.0f} 秒 / 全 {summ['total']} 件: 全項目一致 {summ['match']}・片方のみ {summ['partial']}・"
          f"不一致 {summ['mismatch']}・取得不能 {summ['unfetchable']}・台帳に値なし {summ['no_data']}")
    town_only = sum(1 for r in results.values() if r.address_match == "town")
    writable = sum(1 for r in results.values() if verified_urls(r) is not None)
    print(f"（所在地が市名なしの町名＋番地で一致したもの {town_only} 件を含む。--write の対象は {writable} 件）")
    by_slug = {s.slug: s for s in srcs}
    for title, kinds in (("不一致・片方のみ", ("mismatch", "partial")), ("取得不能", ("unfetchable",))):
        rows = [(sl, r) for sl, r in results.items() if classify(r) in kinds]
        if rows:
            print(f"\n[{title}] {len(rows)} 件")
            for sl, r in rows:
                s = by_slug[sl]
                print(f"- {sl} ({classify(r)}) 電話={s.phone} 所在地={s.address}\n    {r.reason}"
                      + (f"\n    近い電話: {r.nearby_phones}" if r.nearby_phones else "")
                      + (f"\n    近い所在地: {r.nearby_addresses}" if r.nearby_addresses else ""))
    if a.footer_only:
        rows = [(sl, r) for sl, r in results.items() if r.phone_footer_only]
        print(f"\n[電話がフッターにしか出ない] {len(rows)} 件")
        for sl, r in rows:
            print(f"- {sl} 電話={by_slug[sl].phone} {r.phone_url}")
    if a.out:
        detail: dict = {"generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                        "elapsed_sec": round(secs), "summary": summ, "results": {}}
        for sl, r in results.items():
            s = by_slug[sl]
            detail["results"][sl] = {"status": classify(r), "municipality": s.municipality, "url": s.url,
                                     "ledger_phone": s.phone, "ledger_address": s.address, **asdict(r)}
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(detail, ensure_ascii=False, indent=2), encoding="utf-8")
    if a.write and not a.dry_run:
        print(f"\n台帳に書き戻し: {write_back(path, results, today)} 件")
    return 0


if __name__ == "__main__":
    sys.exit(main())
