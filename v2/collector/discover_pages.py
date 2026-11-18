"""台帳に無い「同じ自治体の別ページ」（譲渡・保護中・迷子）を見つける（`collector discover --pages`。W006 T641）。

`collector discover`（discover.py）は環境省リンク集と台帳をドメイン単位でしか比べないので、ドメインが台帳にある自治体の
別ページの掲載漏れは差分に出ない（2026-11-17 の手作業の棚卸しで 19 自治体。projects/oneco/outputs/t640 の gap_*.py）。
その調査を固定スクリプトにしたもの。LLM・有料 API は使わない。台帳は変えず、候補を知らせるだけ。

1. 起点 = 台帳の全エントリの URL（enabled・recipe / link_only を問わない）・その親ディレクトリ・環境省リンク集のリンク先
2. 候補 = 起点のページのリンクのうち、リンク文字が KW に当たり NG に当たらないもの（depth 2 なら候補ページからもう 1 段）。
   台帳・data/latest.json の source_url・レシピ本文・discover_known.yaml の pages: にあるものは除く
3. 採点 = 候補を開いて性別の語・日付の語・写真・0 頭の文を数える。性別の語が SEX_MIN 以上で、個体ページでなければ通知の対象
4. ついでに、台帳の URL が HTTP 404・410 か別ホストへの転送で終わったものを「リンク切れ」として知らせる

確認済みのページは discover_known.yaml の pages: に足す（足せば止まる。実行時の状態は持たない）。
ops/collect.sh が毎月最初の月曜（JST の 1〜7 日）に `discover --pages --notify` を走らせる。
"""

from __future__ import annotations

import json
import re
import threading
import warnings
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

from .discover import ENV_URL, KNOWN_PATH, _send, env_links, load_known_pages, norm
from .fetch import Fetcher, FetchError, page_gone
from .registry import ROOT, Source, load_sources

# --- 定数（テストで固定する） -----------------------------------------------------------------
DELAY = 1.5              # 同じホストへの間隔（秒）。ホストごとに Fetcher を 1 つ持つ
MAX_WORKERS = 8          # ホストをまたいだ並列の数
MAX_FETCHES = 5000       # 1 回の実行の取得数の上限（環境省ページ・robots.txt は数えない）。超えたら打ち切って通知に書く
SEX_MIN = 4              # 性別の語（オス・メス…）がこの数以上なら「子の一覧らしい」
NOTIFY_MAX_ITEMS = 10    # 通知に載せる候補・リンク切れそれぞれの最大件数
NOTIFY_MAX_CHARS = 1900  # Discord の上限（2000）より少し下
NOTIFY_TITLE_CHARS = 40  # 候補 1 行に出すページの題名の長さ
NOTIFY_TAIL_ROOM = 60    # 「上限で残り N 行を省いた」の 1 行のために空けておく文字数

LATEST_PATH = ROOT / "data" / "latest.json"
RECIPES_DIR = ROOT / "recipes"
JST = timezone(timedelta(hours=9))

KW = re.compile(r"譲渡|里親|飼い?主(募集|探し|さがし|を探|を募集|が見つかる|のいない|のわからない|不明)|新しい(飼い?主|家族)"
                r"|家族を(探|募集|待)|保護(犬|猫|動物|して|中|情報|した|された)|収容|迷子|迷い(犬|猫)|行方不明|公示|ペット探し|飼主")
NG = re.compile(r"講習|講座|申込書|申請書|様式|要綱|条例|規則|統計|ボランティア|寄附|寄付|募金|イベント|啓発|飼い方|しつけ"
                r"|マイクロチップ|狂犬病|ふるさと納税|地域猫|不妊|去勢|苦情|多頭|災害|防災|野生|鳥獣|カラス|ハチ|蜂|事業者|動物取扱"
                r"|特定動物|引取り|引き取り|手数料|アンケート|パブリック|入札|採用|求人|お問い合わせ|サイトマップ|プライバシー|ふれあい|教室")
SEX = re.compile(r"オス|メス|♂|♀|雄|雌|去勢|避妊")
DATE = re.compile(r"収容日|保護日|保護した日|収容年月日|保護年月日|収容場所|保護場所|管理番号|譲渡番号|整理番号")
ZERO = re.compile(r"(現在|ただいま)[^。]{0,30}(いません|おりません|ありません)")
INDIVIDUAL = re.compile(r"\d+月\d+日|No\.?\s*\d|番号|\d{3,}|R\d+-\d+")
SKIP_EXT = (".pdf", ".xlsx", ".xls", ".doc", ".docx", ".jpg", ".jpeg", ".png", ".gif", ".zip")
SKIP_DOMAINS = ("env.go.jp", "youtube.com")
PHOTO_SKIP = re.compile(r"logo|icon|banner|btn|button|bnr|common|parts|arrow|spacer", re.IGNORECASE)
PHOTO_EXT = re.compile(r"\.(jpe?g|png|webp)", re.IGNORECASE)
READ_ERRORS = (FetchError, httpx.HTTPError, ValueError)   # 1 ページの失敗で全体を止めない（ValueError は文字コード）


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower().removeprefix("www.")


def parent(url: str) -> str | None:
    p = urlsplit(url)
    segs = p.path.rstrip("/").rsplit("/", 1)
    if len(segs) < 2 or not segs[0]:
        return None
    return urlunsplit((p.scheme, p.netloc, segs[0] + "/", "", ""))


def _soup(html: str) -> BeautifulSoup:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", XMLParsedAsHTMLWarning)
        return BeautifulSoup(html, "lxml")


def links_of(html: str, base: str) -> list[tuple[str, str]]:
    out = []
    for a in _soup(html).select("a[href]"):
        try:
            href = urljoin(base, str(a["href"]).strip())
        except ValueError:
            continue   # 壊れたリンク（「http://[bad」は urljoin が ValueError）。1 つのために全体を止めない
        if href.startswith(("http://", "https://")):
            out.append((href.split("#")[0], a.get_text(" ", strip=True)[:80]))
    return out


def score(html: str) -> dict[str, Any]:
    """gap_triage.py と同じ数え方。header・footer・nav・script・style は数えない。"""
    soup = _soup(html)
    for t in soup(["script", "style", "header", "footer", "nav"]):
        t.decompose()
    text = soup.get_text(" ", strip=True)
    photos = [i.get("src", "") for i in soup.select("img")]
    photos = [s for s in photos if PHOTO_EXT.search(s) and not PHOTO_SKIP.search(s)]
    return {"sex": len(SEX.findall(text)), "date": len(DATE.findall(text)), "photos": len(photos),
            "zero": bool(ZERO.search(text)), "title": (soup.title.get_text(strip=True) if soup.title else "")[:80]}


def _openable(href: str) -> bool:
    if urlsplit(href).path.lower().endswith(SKIP_EXT):
        return False
    host = _host(href)
    return not any(host == d or host.endswith("." + d) for d in SKIP_DOMAINS)


# --- 取得 ---------------------------------------------------------------------------------------

@dataclass
class PageInfo:
    final_url: str = ""
    links: list[tuple[str, str]] = field(default_factory=list)
    score: dict[str, Any] | None = None
    error: str = ""                  # 読めなかった理由（表示用）
    gone_status: int = 0             # HTTP 404・410 のとき、その番号
    moved_to: str = ""               # 別ホストへ転送された先（ホスト名。分からなければ「別のサイト」）


class _Crawler:
    """ホストごとに Fetcher を 1 つ持ち（間隔・robots はそれが守る）、ホストをまたいで最大 workers 本で取る。
    同じ URL は 1 回しか取らない。取得数が max_fetches に達したらそれ以上は取らない。"""

    def __init__(self, factory: Callable[[], Fetcher], max_fetches: int, workers: int) -> None:
        self._factory = factory
        self._max = max_fetches
        self._workers = workers
        self._lock = threading.Lock()
        self._fetchers: dict[str, Fetcher] = {}
        self.pages: dict[str, PageInfo] = {}
        self.fetched = 0
        self.truncated = False

    def _fetcher(self, host: str) -> Fetcher:
        with self._lock:
            if host not in self._fetchers:
                self._fetchers[host] = self._factory()
            return self._fetchers[host]

    def _reserve(self) -> bool:
        with self._lock:
            if self.fetched >= self._max:
                self.truncated = True
                return False
            self.fetched += 1
            return True

    def _one(self, url: str) -> PageInfo | None:
        if not self._reserve():
            return None
        try:
            fetcher = self._fetcher(urlsplit(url).netloc.lower())
            page = fetcher.get(url)
        except Exception as e:   # READ_ERRORS のほか、httpx.InvalidURL（ポートが数字でない URL など。ValueError でも HTTPError でもない）も 1 件の失敗にとどめる
            info = getattr(e, "info", None)
            moved = ""
            if info is not None and info.kind == "redirect":
                m = re.search(r"転送された（([^）]*)）", str(e))
                moved = m.group(1) if m else "別のサイト"
            gone = isinstance(e, FetchError) and page_gone(e)
            return PageInfo(error=f"{type(e).__name__}: {str(e)[:120]}", moved_to=moved,
                            gone_status=(info.status or 0) if gone and info is not None else 0)
        html = page.html or ""
        moved = _host(page.final_url) if _host(page.final_url) != _host(url) else ""
        try:
            return PageInfo(final_url=page.final_url, links=links_of(html, page.final_url), score=score(html), moved_to=moved)
        except Exception as e:   # 1 ページの読み解きの失敗（想定外の HTML）で月 1 回の実行を止めない
            return PageInfo(final_url=page.final_url, error=f"{type(e).__name__}: {str(e)[:120]}", moved_to=moved)

    def _run_host(self, urls: list[str]) -> None:
        for u in urls:
            info = self._one(u)
            if info is not None:
                self.pages[u] = info   # dict の代入は GIL 下で安全。キーは URL ごとに 1 つのスレッドだけが書く

    def fetch_all(self, urls: Iterable[str]) -> None:
        by_host: dict[str, list[str]] = {}
        for u in dict.fromkeys(urls):
            if u not in self.pages:
                by_host.setdefault(urlsplit(u).netloc.lower(), []).append(u)
        if not by_host:
            return
        with ThreadPoolExecutor(max_workers=self._workers) as ex:
            list(ex.map(self._run_host, by_host.values()))   # list() で例外を取りこぼさない

    def raw(self, url: str) -> str:
        """環境省リンク集用。取得数には数えない（上限は 1 ページ単位の礼儀のためで、これは 1 回だけ）。"""
        return self._fetcher(urlsplit(url).netloc.lower()).get(url).html or ""


# --- 結果 ---------------------------------------------------------------------------------------

@dataclass
class PagesResult:
    seeds: dict[str, str]                       # 起点 URL → 起点の種類（ledger:<slug> | parent:<slug> | env:<自治体名>）
    candidates: list[dict[str, Any]]            # 開けた候補（採点つき）
    targets: list[dict[str, Any]]               # 通知の対象（candidates のうち、子の一覧らしいもの）
    broken: list[dict[str, str]]                # リンク切れ（slug・url・reason）
    fetched: int = 0
    truncated: bool = False
    unopened: int = 0                           # 候補のうち開けなかった数（404・接続失敗・上限など）
    env_error: str = ""

    def to_json(self) -> dict[str, Any]:
        return {"seeds": len(self.seeds), "fetched": self.fetched, "truncated": self.truncated, "unopened": self.unopened,
                "env_error": self.env_error, "targets": self.targets, "candidates": self.candidates, "broken": self.broken}


def _latest_norms(path: Path) -> set[str]:
    if not path.exists():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    return {norm(a["source_url"]) for a in data.get("animals", []) if a.get("source_url")}


def _recipe_texts(recipes_dir: Path) -> list[str]:
    return [p.read_text(encoding="utf-8") for p in sorted(recipes_dir.glob("*.yaml"))]


_URL_IN_TEXT = re.compile(r"https?://[^\s\"'<>）)、。]+")
_ID_LIKE = re.compile(r"\d{4}")   # ページ ID らしい末尾（1020659.html・0000016441.html・p013242.html）


def _recipe_urls(texts: list[str]) -> set[str]:
    """レシピ本文にそのまま書かれている URL（steps の url・urls・コメント）を norm にかけたもの。"""
    out: set[str] = set()
    for t in texts:
        for u in _URL_IN_TEXT.findall(t):
            try:
                out.add(norm(u))
            except ValueError:
                continue
    return out


def find_pages(*, depth: int = 1, fetcher_factory: Callable[[], Fetcher] | None = None,
               sources: list[Source] | None = None, known_path: Path = KNOWN_PATH, latest_path: Path = LATEST_PATH,
               recipes_dir: Path = RECIPES_DIR, max_fetches: int = MAX_FETCHES, workers: int = MAX_WORKERS) -> PagesResult:
    sources = load_sources() if sources is None else sources
    factory = fetcher_factory or (lambda: Fetcher(delay=DELAY))
    crawler = _Crawler(factory, max_fetches, workers)

    seeds: dict[str, str] = {}
    ledger_slugs: dict[str, list[str]] = {}
    for s in sources:
        seeds.setdefault(s.url, f"ledger:{s.slug}")
        ledger_slugs.setdefault(s.url, []).append(s.slug)
    for s in sources:
        par = parent(s.url)
        if par:
            seeds.setdefault(par, f"parent:{s.slug}")
    env_error = ""
    try:
        for links in env_links(crawler.raw(ENV_URL)).values():
            for u, name in links:
                seeds.setdefault(u.split("#")[0], f"env:{name}")
    except READ_ERRORS as e:
        env_error = f"環境省リンク集を読めなかった（起点から外して続ける）: {e}"

    ledger = {norm(s.url) for s in sources}
    live = _latest_norms(latest_path)
    recipes = _recipe_texts(recipes_dir)
    recipe_urls = _recipe_urls(recipes)
    known = set(load_known_pages(known_path))

    def excluded(n: str, href: str) -> bool:
        if n in ledger or n in known or n in recipe_urls:
            return True
        if any(k == n or k.startswith(n.rstrip("/") + "/") for k in live):
            return True
        # レシピが follow で開くページ（a[href*='1020659'] のように末尾だけ書く）。部分一致で外すのはページ ID らしい末尾（数字 4 桁以上）
        # だけ。index.html・neko.html・animal のような一般的な末尾は、ほかの自治体のレシピやコメントにも出てくるので外さない
        # （2026-11-18 #131 のレビュー: 実レシピでは index.html が 23 本・animal が 66 本に当たり、本物の掲載漏れを黙って外していた）
        tail = urlsplit(href).path.rstrip("/").rsplit("/", 1)[-1]
        stem = re.sub(r"\.[A-Za-z0-9]{1,5}$", "", tail)   # 拡張子を除く（レシピは a[href*='1020659'] のように拡張子なしでも書く）
        return len(stem) > 4 and bool(_ID_LIKE.search(stem)) and any(stem in t for t in recipes)

    cands: dict[str, dict[str, Any]] = {}

    def harvest(origin: str, page: PageInfo) -> None:
        for href, text in page.links:
            if not KW.search(text) or NG.search(text) or not _openable(href):
                continue
            n = norm(href)
            if excluded(n, href):
                continue
            c = cands.setdefault(n, {"url": href, "texts": set(), "from": set()})
            c["texts"].add(text)
            c["from"].add(origin)

    crawler.fetch_all(seeds)
    for url, origin in seeds.items():
        if url in crawler.pages:
            harvest(origin, crawler.pages[url])
    if depth >= 2:
        frontier = [c["url"] for c in list(cands.values())]
        crawler.fetch_all(frontier)
        for u in frontier:
            if u in crawler.pages:
                harvest(f"page:{u}", crawler.pages[u])
    crawler.fetch_all(c["url"] for c in cands.values())

    rows: list[dict[str, Any]] = []
    unopened = 0
    for c in cands.values():
        page = crawler.pages.get(c["url"])
        if page is None or page.score is None:
            unopened += 1
            continue
        # 台帳のページからだけ来て、リンク文字が全部「個体番号風」= 子 1 頭のページ。一覧ではない
        individual = all(o.startswith("ledger:") for o in c["from"]) and all(INDIVIDUAL.search(t) for t in c["texts"])
        rows.append({"url": c["url"], **page.score, "texts": sorted(c["texts"]), "from": sorted(c["from"]),
                     "individual": individual})
    rows.sort(key=lambda r: (-r["sex"], r["url"]))
    targets = [r for r in rows if r["sex"] >= SEX_MIN and not r["individual"]]

    broken: list[dict[str, str]] = []
    for url, slugs in ledger_slugs.items():
        page = crawler.pages.get(url)
        if page is None:
            continue
        reason = f"HTTP {page.gone_status}" if page.gone_status else (f"別のホストへ転送: {page.moved_to}" if page.moved_to else "")
        if reason:
            broken.append({"slug": "・".join(slugs), "url": url, "reason": reason})
    return PagesResult(seeds, rows, targets, broken, crawler.fetched, crawler.truncated, unopened, env_error)


# --- 通知 ---------------------------------------------------------------------------------------

def message(res: PagesResult) -> str | None:
    """新しい候補・リンク切れ・取得上限での打ち切りのどれかがあるときだけ。無ければ None（送らない）。"""
    if not res.targets and not res.broken and not res.truncated:
        return None
    # 並べる順は、打ち切り → リンク切れ（台帳の URL の壊れ。公開中のリンクが切れている）→ 候補。文字数の上限では行の途中で切らず、
    # 入らない行は丸ごと省いて、省いた行数を最後に書く（2026-11-18 の試運転では 1900 文字で切れ、リンク切れ 9 件のうち 4 件が消えた）
    lines = [f"掲載漏れの候補 {len(res.targets)} 件・リンク切れ {len(res.broken)} 件（月 1 回の discover --pages）"]
    if res.truncated:
        lines.append(f"取得数が上限 {MAX_FETCHES} 件に達したので途中で打ち切った（起点 {len(res.seeds)} 件）")
    if res.broken:
        lines.append("リンク切れ（台帳の URL。移転なら台帳の url を直す）")
        for b in res.broken[:NOTIFY_MAX_ITEMS]:
            lines.append(f"- {b['slug']} {b['url']}（{b['reason']}）")
        if len(res.broken) > NOTIFY_MAX_ITEMS:
            lines.append(f"- ほか {len(res.broken) - NOTIFY_MAX_ITEMS} 件")
    if res.targets:
        lines.append("候補（子の一覧らしいページ。台帳に足すか、v2/registry/discover_known.yaml の pages: に足すと止まる）")
        for r in res.targets[:NOTIFY_MAX_ITEMS]:
            lines.append(f"- {(r['title'] or '(題名なし)')[:NOTIFY_TITLE_CHARS]} {r['url']} 性別{r['sex']}・日付{r['date']}・写真{r['photos']}")
        if len(res.targets) > NOTIFY_MAX_ITEMS:
            lines.append(f"- ほか {len(res.targets) - NOTIFY_MAX_ITEMS} 件（--out の JSON に全件）")
    out: list[str] = []
    used = 0
    for i, line in enumerate(lines):
        if used + len(line) + 1 > NOTIFY_MAX_CHARS - NOTIFY_TAIL_ROOM:
            out.append(f"（文字数の上限で残り {len(lines) - i} 行を省いた。全件は --out の JSON）")
            break
        out.append(line)
        used += len(line) + 1
    return "\n".join(out)


def _default_out() -> Path:
    import os

    log_dir = Path(os.environ.get("ONECO_LOG_DIR") or ROOT / "logs")
    return log_dir / f"discover-pages-{datetime.now(JST):%Y-%m-%d}.json"


def discover_pages(*, depth: int = 1, notify: bool = False, out: Path | None = None,
                   fetcher_factory: Callable[[], Fetcher] | None = None, sources: list[Source] | None = None,
                   known_path: Path = KNOWN_PATH, latest_path: Path = LATEST_PATH, recipes_dir: Path = RECIPES_DIR,
                   max_fetches: int = MAX_FETCHES) -> int:
    """0 = 実行できた（通知の有無は問わない）、1 = Discord に送れなかった、または途中で落ちた（--notify のとき。落ちたことを Discord に送る）。"""
    try:
        res = find_pages(depth=depth, fetcher_factory=fetcher_factory, sources=sources, known_path=known_path,
                         latest_path=latest_path, recipes_dir=recipes_dir, max_fetches=max_fetches)
    except Exception as e:   # 月 1 回の実行が黙って機能しなくなるのを防ぐ（collect.sh は失敗を日次の失敗に数えない）
        if not notify:
            raise
        print(f"discover --pages が途中で失敗した: {type(e).__name__}: {e}")
        _send(f"discover --pages（月 1 回の掲載漏れ・リンク切れの確認）が途中で失敗した: {type(e).__name__}: {str(e)[:300]}\n"
              "今月の確認はできていない。日次収集と公開には影響しない。logs/collect-<日付>.log を見る")
        return 1
    out_path = out or _default_out()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(res.to_json(), ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"起点 {len(res.seeds)} 件・取得 {res.fetched} 件・候補 {len(res.candidates)} 件（開けなかった {res.unopened} 件）"
          f"・通知対象 {len(res.targets)} 件・リンク切れ {len(res.broken)} 件{'・取得上限で打ち切り' if res.truncated else ''}")
    if res.env_error:
        print(res.env_error)
    print(f"全件: {out_path}")
    msg = message(res)
    if not notify:
        return 0
    if msg is None:
        print("通知すべきものなし。送らない")
        return 0
    print("\n---- 通知文 ----\n" + msg)
    return _send(msg)
