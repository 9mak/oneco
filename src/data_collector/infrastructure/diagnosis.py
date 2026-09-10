"""壊れサイトの半自動診断 (T406)

自己修復ループ Phase 2 (LLM 自動修復ワーカー `scripts/auto_fix_adapter.py`) は
48 run 動かして PR 0 件だった (project_self_healing memory, auto-merge も
2026-09-08 に既に撤去済み)。LLM に「直させる」代わりに、Phase 1 の検知結果
(broken_tracker / field_quality_tracker / site_baseline_tracker) が拾った
壊れサイトについて「どのセレクタ/ラベルが死んでいるか」を人が10分で読める
形に構造化して提示する診断に置き換える。

診断内容 (1 サイトにつき HTTP アクセスは 1 回だけ、politeness throttle 経由):
    - HTTP status / リダイレクト有無 / 文字コード
    - LIST_LINK_SELECTOR / ROW_SELECTOR / NEXT_PAGE_SELECTOR が現在の
      ページ上で何件マッチするか (`list_selector_resolution.py` で解決)
    - FIELD_SELECTORS / HEADER_FIELDS のラベルがページ上に見つかるか
    - 直前 snapshot にあった動物 URL が今回の一覧ページにまだ含まれているか
    - ページ上で見つかった候補ラベル/リンクパターン上位 5 件
      (adapter の定義が古くなっている場合に「次は何を指定すればいいか」を
      その場で示す)
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup, Tag

from ..adapters.politeness import ONECO_USER_AGENT, get_throttle_for_url
from ..adapters.rule_based.base import FieldSpec
from ..adapters.rule_based.registry import SiteAdapterRegistry
from ..llm.config import SiteConfig
from .list_selector_resolution import resolve_list_selector, resolve_pagination
from .snapshot_store import SnapshotStore

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_SEC = 30
_MAX_CANDIDATE_LABELS = 5
_MAX_SUMMARY_LINES = 15
_MAX_SITES_PER_RUN = 5

# th/dt 等、ラベル候補として拾う見出し系タグ
_LABEL_TAGS = ("th", "dt")


@dataclass
class SelectorCheck:
    """1 つの selector/label をページに対して評価した結果"""

    name: str  # "LIST_LINK_SELECTOR" / "FIELD_SELECTORS.location" 等
    selector_or_label: str
    match_count: int

    @property
    def ok(self) -> bool:
        return self.match_count > 0


@dataclass
class SiteDiagnosis:
    """1 サイト分の構造診断結果"""

    site_name: str
    diagnosed_at: str
    list_url: str
    http_status: int | None
    redirected: bool
    final_url: str | None
    charset: str | None
    fetch_error: str | None

    list_selector_source: str
    is_pdf: bool
    checks: list[SelectorCheck] = field(default_factory=list)

    previous_url_count: int | None = None
    previous_urls_still_present: int | None = None

    candidate_labels: list[str] = field(default_factory=list)
    candidate_href_patterns: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "site_name": self.site_name,
            "diagnosed_at": self.diagnosed_at,
            "list_url": self.list_url,
            "http_status": self.http_status,
            "redirected": self.redirected,
            "final_url": self.final_url,
            "charset": self.charset,
            "fetch_error": self.fetch_error,
            "list_selector_source": self.list_selector_source,
            "is_pdf": self.is_pdf,
            "checks": [
                {
                    "name": c.name,
                    "selector_or_label": c.selector_or_label,
                    "match_count": c.match_count,
                    "ok": c.ok,
                }
                for c in self.checks
            ],
            "previous_url_count": self.previous_url_count,
            "previous_urls_still_present": self.previous_urls_still_present,
            "candidate_labels": self.candidate_labels,
            "candidate_href_patterns": self.candidate_href_patterns,
        }

    def summary_lines(self, max_lines: int = _MAX_SUMMARY_LINES) -> list[str]:
        """Discord 通知向けのコンパクトな要約 (最大 max_lines 行)"""
        lines: list[str] = [f"**{self.site_name}**"]
        if self.fetch_error:
            lines.append(f"fetch失敗: {self.fetch_error}")
        else:
            redirect_note = " (redirected)" if self.redirected else ""
            lines.append(f"HTTP {self.http_status}{redirect_note} charset={self.charset}")
        if self.is_pdf:
            lines.append("list selector: PDF (比較対象外)")
        else:
            for c in self.checks:
                mark = "OK" if c.ok else "NG"
                lines.append(f"[{mark}] {c.name}: `{c.selector_or_label}` ({c.match_count}件)")
        if self.previous_url_count is not None:
            lines.append(
                f"前回掲載URL {self.previous_url_count}件中 "
                f"{self.previous_urls_still_present}件が今回のページにも残存"
            )
        if self.candidate_labels:
            lines.append("見出し候補: " + ", ".join(self.candidate_labels[:_MAX_CANDIDATE_LABELS]))
        if self.candidate_href_patterns:
            lines.append(
                "リンク候補: " + ", ".join(self.candidate_href_patterns[:_MAX_CANDIDATE_LABELS])
            )
        if len(lines) > max_lines:
            omitted = len(lines) - (max_lines - 1)
            lines = [*lines[: max_lines - 1], f"... (+{omitted} more)"]
        return lines


def _fetch_list_page(
    list_url: str, *, timeout: int = _DEFAULT_TIMEOUT_SEC
) -> tuple[int | None, bool, str | None, str | None, str | None]:
    """(status, redirected, final_url, charset, text_or_None) を返す

    例外は握りつぶさず fetch_error を呼び出し側で組み立てられるよう
    呼び出し元で捕捉する (raise する)。
    """
    get_throttle_for_url(list_url).wait(2.0)
    headers = {"User-Agent": ONECO_USER_AGENT}
    response = requests.get(list_url, headers=headers, timeout=timeout, allow_redirects=True)
    redirected = response.url != list_url
    if "charset=" not in response.headers.get("Content-Type", "").lower():
        response.encoding = response.apparent_encoding
    return response.status_code, redirected, response.url, response.encoding, response.text


def _evaluate_selector(soup: BeautifulSoup, name: str, selector: str) -> SelectorCheck:
    if not selector:
        return SelectorCheck(name=name, selector_or_label=selector, match_count=0)
    try:
        matches = soup.select(selector)
        return SelectorCheck(name=name, selector_or_label=selector, match_count=len(matches))
    except Exception as e:
        logger.warning(f"selector 評価に失敗 ({name}={selector!r}): {e}")
        return SelectorCheck(name=name, selector_or_label=selector, match_count=0)


def _evaluate_label(soup: BeautifulSoup, name: str, label: str) -> SelectorCheck:
    """label 文字列がページ内のテキストに存在するかを数える (dt/th/td/自由テキスト共通)"""
    if not label:
        return SelectorCheck(name=name, selector_or_label=label, match_count=0)
    count = soup.get_text().count(label)
    return SelectorCheck(name=name, selector_or_label=label, match_count=count)


def _field_checks(adapter_cls: type, soup: BeautifulSoup) -> list[SelectorCheck]:
    """FIELD_SELECTORS (dt/th ラベル or CSS selector) / HEADER_FIELDS の生存確認

    FIELD_SELECTORS は本来 detail ページ向けの定義だが、一覧ページに同種の
    ラベルが全く現れないサイトは高確率でラベル文言自体が変わっている
    (=一覧ページでも検知できる) ため、診断の一次シグナルとして使う。
    確定診断ではなく「疑わしい候補」の提示が目的。
    """
    checks: list[SelectorCheck] = []
    field_selectors: dict[str, FieldSpec] = getattr(adapter_cls, "FIELD_SELECTORS", {}) or {}
    for field_name, spec in field_selectors.items():
        if spec.selector:
            checks.append(_evaluate_selector(soup, f"FIELD_SELECTORS.{field_name}", spec.selector))
        elif spec.label:
            labels = spec.label if isinstance(spec.label, tuple) else (spec.label,)
            best = max(
                (_evaluate_label(soup, f"FIELD_SELECTORS.{field_name}", lbl) for lbl in labels),
                key=lambda c: c.match_count,
                default=SelectorCheck(
                    name=f"FIELD_SELECTORS.{field_name}", selector_or_label="", match_count=0
                ),
            )
            checks.append(best)

    header_fields: dict = getattr(adapter_cls, "HEADER_FIELDS", {}) or {}
    for label_spec, field_name in header_fields.items():
        labels = label_spec if isinstance(label_spec, tuple) else (label_spec,)
        best = max(
            (_evaluate_label(soup, f"HEADER_FIELDS.{field_name}", lbl) for lbl in labels),
            key=lambda c: c.match_count,
            default=SelectorCheck(
                name=f"HEADER_FIELDS.{field_name}", selector_or_label="", match_count=0
            ),
        )
        checks.append(best)
    return checks


def _candidate_labels(soup: BeautifulSoup, limit: int = _MAX_CANDIDATE_LABELS) -> list[str]:
    """<th>/<dt> のテキスト頻度上位を「次に指定すべきラベル候補」として返す"""
    texts = []
    for tag_name in _LABEL_TAGS:
        for tag in soup.find_all(tag_name):
            if isinstance(tag, Tag):
                text = tag.get_text(strip=True)
                if text:
                    texts.append(text)
    counted = Counter(texts)
    return [text for text, _ in counted.most_common(limit)]


def _candidate_href_patterns(soup: BeautifulSoup, limit: int = _MAX_CANDIDATE_LABELS) -> list[str]:
    """<a href> のパス構造 (末尾セグメントの拡張子/接頭辞) 上位を候補として返す"""
    patterns: Counter[str] = Counter()
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        if not isinstance(href, str) or not href or href.startswith("#"):
            continue
        path = urlparse(href).path
        segments = [s for s in path.split("/") if s]
        if not segments:
            continue
        last = segments[-1]
        if "." in last:
            pattern = "*." + last.rsplit(".", 1)[-1]
        else:
            pattern = "/".join(segments[:-1]) + "/*" if len(segments) > 1 else "/*"
        patterns[pattern] += 1
    return [p for p, _ in patterns.most_common(limit)]


def diagnose_site(
    site: SiteConfig,
    *,
    snapshot_store: SnapshotStore | None = None,
    timeout: int = _DEFAULT_TIMEOUT_SEC,
) -> SiteDiagnosis:
    """1 サイトの構造診断を行う。HTTP アクセスは 1 回のみ (politeness throttle 経由)。"""
    now = datetime.now(UTC).astimezone().isoformat(timespec="seconds")
    adapter_cls = SiteAdapterRegistry.get(site.name)
    raw_cfg = site.model_dump()
    list_selector, selector_source, is_pdf = resolve_list_selector(site.name, raw_cfg)
    next_page_selector, _max_pages = resolve_pagination(site.name)

    try:
        status, redirected, final_url, charset, text = _fetch_list_page(
            site.list_url, timeout=timeout
        )
    except Exception as e:
        logger.warning(f"[{site.name}] 診断用 fetch 失敗: {e}")
        return SiteDiagnosis(
            site_name=site.name,
            diagnosed_at=now,
            list_url=site.list_url,
            http_status=None,
            redirected=False,
            final_url=None,
            charset=None,
            fetch_error=str(e),
            list_selector_source=selector_source,
            is_pdf=is_pdf,
        )

    diagnosis = SiteDiagnosis(
        site_name=site.name,
        diagnosed_at=now,
        list_url=site.list_url,
        http_status=status,
        redirected=redirected,
        final_url=final_url,
        charset=charset,
        fetch_error=None,
        list_selector_source=selector_source,
        is_pdf=is_pdf,
    )

    if is_pdf or not text:
        return diagnosis

    soup = BeautifulSoup(text, "html.parser")

    checks: list[SelectorCheck] = []
    if list_selector:
        checks.append(_evaluate_selector(soup, "LIST_LINK_SELECTOR/ROW_SELECTOR", list_selector))
    if next_page_selector:
        checks.append(_evaluate_selector(soup, "NEXT_PAGE_SELECTOR", next_page_selector))
    if adapter_cls is not None:
        checks.extend(_field_checks(adapter_cls, soup))
    diagnosis.checks = checks

    # 前回 snapshot にあった動物 URL が今回のページにまだ含まれているか
    if snapshot_store is not None:
        try:
            animal_map = snapshot_store.load_animal_map()
            site_host = urlparse(site.list_url).netloc
            prev_urls = [
                str(a.source_url)
                for a in animal_map.values()
                if urlparse(str(a.source_url)).netloc == site_host
            ]
            if prev_urls:
                page_hrefs = {
                    a.get("href") for a in soup.find_all("a", href=True) if isinstance(a, Tag)
                }
                page_text = text
                still_present = sum(1 for url in prev_urls if url in page_hrefs or url in page_text)
                diagnosis.previous_url_count = len(prev_urls)
                diagnosis.previous_urls_still_present = still_present
        except Exception as e:
            logger.warning(f"[{site.name}] snapshot 比較に失敗: {e}")

    # いずれかのチェックが NG の場合のみ候補ラベル/リンクパターンを計算する
    # (コスト削減、全チェック OK の正常サイトでは不要)。
    if any(not c.ok for c in checks):
        diagnosis.candidate_labels = _candidate_labels(soup)
        diagnosis.candidate_href_patterns = _candidate_href_patterns(soup)

    return diagnosis


def diagnose_sites(
    site_names: list[str],
    sites_by_name: dict[str, SiteConfig],
    *,
    snapshot_store: SnapshotStore | None = None,
    max_sites: int = _MAX_SITES_PER_RUN,
) -> list[SiteDiagnosis]:
    """複数サイトの診断を行う (1 run あたり max_sites 件まで)。

    順序保持 dedup 後、先頭 max_sites 件のみ診断する (politeness / 実行時間の
    観点から 1 run で無制限に診断しない)。
    """
    seen: set[str] = set()
    uniq: list[str] = []
    for name in site_names:
        if name not in seen and name in sites_by_name:
            seen.add(name)
            uniq.append(name)

    results: list[SiteDiagnosis] = []
    for name in uniq[:max_sites]:
        try:
            results.append(diagnose_site(sites_by_name[name], snapshot_store=snapshot_store))
        except Exception as e:
            logger.warning(f"[{name}] 診断中に想定外エラー: {e}")
    return results
