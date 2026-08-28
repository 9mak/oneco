"""image_urls が元ページ (source_url) に実在するかを機械照合する (W002/T102)。

背景: 熊本の別個体写真混入事故 (T020, PR #263) では、detail ページ下部の
「このページを見ている人はこちらのページも見ています」欄の他個体サムネイルを
`img` セレクタが拾い、公開個体の image_urls に別の子の写真が混入していた。
現状この種の混入・掲載変更を検知する自動手段が無く、おまえさんの目視監査に
依存している。本スクリプトは公開中の個体について、掲載元ページを実際に
fetch し、そのページ内に登録済み image_url が実在するかを機械的に照合する。

設計判断 (T102):

1. 検証方式は (a)(b) 両方を実装する。
   (a) source_url を fetch し、そのページの <img src> / 画像リンクの集合に
       登録済み image_url が含まれるか照合する (image_not_found_on_page)。
       T020 型の実害 (別個体の写真混入・掲載変更) を直接検知できる主眼の方式。
   (b) image_url 自体に直接 HTTP アクセスし、確定的な 4xx が返るリンク切れを
       検知する (image_broken_link)。(a) だけでは「image_url 自体が死んでいる」
       ケースを取りこぼす (ページ側は正常でも画像ファイルだけ消えている等)。
   限界: (a) は「ページ内に image_url が存在するか」の照合であり、T020 のように
   誤って拾われた別個体のサムネイルが同じページ内に実在する場合は検知できない
   (ページの構造まで見て「どの節が本人の写真か」を判定する処理は本スクリプトの
   スコープ外。selector 側の修正 (PR #263 のような) が根治策で、本スクリプトは
   それとは独立に「登録した image_url がそもそも実在するか」という下限の
   機械チェックを提供する位置づけ)。

2. サンプリング: 全件 (現状 1,100+ 件、日々増加) を毎回チェックすると自治体
   サイトへの負荷が大きいため、animal_id を鍵に 1 日 1/7 ずつ処理するローテーション
   (7 日で一巡) を既定にする。site_count_audit.py が一覧ページ 1 回 fetch で
   済むのに対し、本スクリプトは個体ごとに detail ページ + 画像 URL への fetch が
   必要で1件あたりのコストが高いため、より保守的な既定 (全数の毎日実行はしない)
   を選んだ。single_page 型サイト (一覧ページに複数個体が同居し、source_url が
   `#row=N` などの fragment だけで個体を区別する) では、fragment を除いた URL を
   キャッシュキーにしてページ fetch を再利用し、同一ページへの重複アクセスを避ける
   (T053 の source_url 設計と同じ前提)。
   --rotation-days 1 (毎日全件) や --shard/--limit で絞ることもできる。

3. 通知: DISCORD_WEBHOOK_URL (GitHub Actions secret) が設定されていれば
   data_collector.infrastructure.image_url_audit_notify 経由で Discord に通知する。
   通知対象は image_not_found_on_page / image_broken_link の確定的な異常のみ。
   ページ/画像取得の一時障害 (timeout/5xx) は誤通知疲労を避けるため通知しない
   (secret_health.py / uptime-check.yml と同じ思想)。未設定なら no-op でスキップ。

4. 礼儀的アクセス: site_count_audit.py と同じく同一ホストへの連続アクセスに
   スリープを挟む。JS 必須サイト (sites.yaml の requires_js: true) は
   requests での静的 fetch では正しく描画されないため (a) はスキップし、
   (b) の画像直接チェックのみ行う (画像ファイル自体への直接アクセスは
   JS レンダリングに依存しない)。

使い方:
    python3 scripts/image_url_audit.py                       # 本日分のシャード (既定 1/7)
    python3 scripts/image_url_audit.py --rotation-days 1      # 全件
    python3 scripts/image_url_audit.py --shard 2 --rotation-days 7
    python3 scripts/image_url_audit.py --limit 20             # デバッグ用に先頭 N 件

出力 (既定 reports/):
    image_url_audit_YYYYMMDD.json / .md
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.request
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote, urljoin, urlparse, urlunparse

import requests
import yaml
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from data_collector.infrastructure.image_url_audit_notify import maybe_notify  # noqa: E402
from data_collector.infrastructure.notification_client import NotificationClient  # noqa: E402

DEFAULT_API_BASE = "https://oneco-api-tvlsrcvyuq-an.a.run.app"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) oneco-image-url-audit/1.0"
PAGE_TIMEOUT = 20
IMAGE_TIMEOUT = 15
DEFAULT_ROTATION_DAYS = 7

# 画像ファイルへのリンクとみなす拡張子 (a href 経由の「拡大画像」リンク検出用)
IMAGE_EXT_RE = re.compile(r"\.(jpe?g|png|gif|webp|bmp)(?:[?#]|$)", re.IGNORECASE)

# 確定的にリンク切れとみなす HTTP status (secret_health.py の 401/403 判定と同じ思想:
# 5xx やネットワークエラーは一時障害の可能性があるため「壊れている」と断定しない)
_BROKEN_STATUSES = frozenset({404, 410})


# ---------------------------------------------------------------------------
# 純粋ロジック (単体テスト対象: tests/scripts/test_image_url_audit.py)
# ---------------------------------------------------------------------------


def normalize_image_url(url: str) -> str:
    """比較用に正規化する。

    - query string / fragment を落とす
    - ホストのみ小文字化する
    - パスの percent-encoding 有無を吸収する (unquote → quote で再エンコード)。
      自治体サイトによって日本語ファイル名等を生のまま HTML に書くところと
      percent-encode するところが混在し (例: 大分県 "タマ①.jpg" vs API 格納値の
      "%E3%82%BF%E3%83%9E%E2%91%A0.jpg")、単純な文字列比較では実在する画像を
      「見つからない」と誤検知するため (2026-08-29 dry-run で実発覚)。
    """
    parsed = urlparse(url)
    path = quote(unquote(parsed.path))
    return urlunparse((parsed.scheme, parsed.netloc.lower(), path, "", "", ""))


def page_cache_key(url: str) -> str:
    """ページ fetch のキャッシュキー。fragment (#row=N 等) を除いた URL。

    single_page 型サイトでは複数個体が同一ページを共有し fragment だけで
    行を区別するため (T053)、fragment を落として同一ページへの重複 fetch を防ぐ。
    """
    return url.split("#", maxsplit=1)[0]


def shard_for_today(total_shards: int, today: date | None = None) -> int:
    """本日担当するシャード番号を日付から決定論的に求める (連続実行で一巡する)。"""
    d = today or date.today()
    return d.toordinal() % total_shards


def in_shard(animal_id: int, shard: int, total_shards: int) -> bool:
    """この個体が本日のシャードの対象か。"""
    if total_shards <= 1:
        return True
    return animal_id % total_shards == shard


def extract_page_image_urls(soup: BeautifulSoup, page_url: str) -> set[str]:
    """ページ内の画像候補 URL 集合を返す (絶対URL・正規化済み)。

    <img src> に加え、拡大画像へのリンク (<a href="....jpg">) も拾う。
    サムネイル src とオリジナル画像 href が別 URL のサイトで
    偽陽性 (image_not_found_on_page の誤検知) を避けるため。
    """
    urls: set[str] = set()
    for img in soup.find_all("img"):
        src = str(img.get("src") or "")
        if not src or src.startswith("data:"):
            continue
        urls.add(normalize_image_url(urljoin(page_url, src)))
    for a in soup.find_all("a"):
        href = str(a.get("href") or "")
        if not href or href.startswith(("javascript:", "data:", "#")):
            continue
        if IMAGE_EXT_RE.search(href):
            urls.add(normalize_image_url(urljoin(page_url, href)))
    return urls


def image_found_on_page(image_url: str, page_images: set[str]) -> bool:
    """image_url がページ内画像集合に実在するか (双方を正規化してから比較)。"""
    normalized_page_images = {normalize_image_url(u) for u in page_images}
    return normalize_image_url(image_url) in normalized_page_images


def classify_image_status(status_code: int | None, content_type: str | None) -> str:
    """画像 URL への直接アクセス結果を分類する。

    content_type は将来の拡張余地として受け取るが、判定は status のみで行う
    (Content-Type ヘッダは自治体サイトでしばしば不正確/欠落しており、
    厳密照合すると誤検知の方が増える)。
    """
    del content_type  # 現状は status のみで判定 (将来の拡張点として引数だけ残す)
    if status_code is None:
        return "error"
    if status_code == 200:
        return "ok"
    if status_code in _BROKEN_STATUSES:
        return "broken"
    return "error"


def audit_animal_images(
    animal: dict[str, Any],
    *,
    page_status: str,
    page_images: set[str] | None,
    image_statuses: dict[str, str],
) -> dict[str, Any]:
    """1個体分の照合結果を組み立てる。

    Args:
        animal: {"id", "source_url", "image_urls"} を含む dict
        page_status: "ok" | "error" | "skipped_js" (source_url fetch の結果)
        page_images: page_status == "ok" のときのページ内画像 URL 集合
        image_statuses: image_url -> classify_image_status の結果
    """
    flags: list[str] = []
    image_urls = animal.get("image_urls") or []

    if page_status == "ok" and page_images is not None:
        for image_url in image_urls:
            if not image_found_on_page(image_url, page_images):
                flags.append("image_not_found_on_page")
                break
    elif page_status == "error":
        flags.append("page_fetch_error")
    # skipped_js: (a) は判定不能なので何もフラグを立てない (b) のみで判定する

    statuses = {image_statuses.get(u, "error") for u in image_urls}
    if "broken" in statuses:
        flags.append("image_broken_link")
    elif "error" in statuses and "ok" not in statuses and image_urls:
        # 全画像が error (未チェック含む) の場合のみ image_fetch_error を立てる。
        # 一部だけ ok なら残りは network の一時的揺れとみなし黙殺する。
        flags.append("image_fetch_error")

    return {
        "id": animal.get("id"),
        "source_url": animal.get("source_url"),
        "image_urls": image_urls,
        "page_status": page_status,
        "flags": flags,
    }


# ---------------------------------------------------------------------------
# HTTP I/O (単体テスト対象外。ローカル dry-run で動作確認する)
# ---------------------------------------------------------------------------


def load_sites_yaml() -> list[dict[str, Any]]:
    cfg = yaml.safe_load(open(ROOT / "src/data_collector/config/sites.yaml"))
    return cfg["sites"]


def js_required_hosts() -> set[str]:
    """requires_js: true なサイトのホスト集合 (list_url 由来)。"""
    hosts: set[str] = set()
    for raw in load_sites_yaml():
        if raw.get("requires_js"):
            host = urlparse(raw["list_url"]).hostname
            if host:
                hosts.add(host)
    return hosts


def get_json(url: str) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as res:
        return json.load(res)


def fetch_api_animals(api_base: str, limit: int = 100) -> list[dict[str, Any]]:
    """公開 API から全件をページングして取得する。"""
    items: list[dict[str, Any]] = []
    offset = 0
    while True:
        page = get_json(f"{api_base.rstrip('/')}/animals?limit={limit}&offset={offset}")
        got = page.get("items") or []
        items.extend(got)
        if not page.get("meta", {}).get("has_next") or not got:
            break
        offset += len(got)
    return items


class _PolitenessTracker:
    """同一ホストへの連続アクセスに待ち時間を挟む (site_count_audit.py と同じ方針)。"""

    def __init__(self) -> None:
        self._last_host: str | None = None

    def wait(self, url: str) -> None:
        host = urlparse(url).hostname or ""
        if self._last_host is not None:
            time.sleep(1.5 if host == self._last_host else 0.5)
        self._last_host = host


def fetch_page(url: str, tracker: _PolitenessTracker) -> tuple[str, set[str] | None]:
    """source_url を fetch し (status, ページ内画像URL集合) を返す。"""
    tracker.wait(url)
    try:
        res = requests.get(url, headers={"User-Agent": UA}, timeout=PAGE_TIMEOUT)
    except requests.RequestException:
        return "error", None
    if res.status_code != 200:
        return "error", None
    soup = BeautifulSoup(res.content, "html.parser")
    return "ok", extract_page_image_urls(soup, url)


def check_image_url(url: str, tracker: _PolitenessTracker) -> str:
    """image_url へ直接アクセスし classify_image_status の結果を返す。

    HEAD をまず試し、405 (Method Not Allowed) や例外時は GET にフォールバックする
    (自治体サイトの静的配信は HEAD 非対応のことがある)。GET 時も content は
    ストリームで開くだけで読み切らない (帯域節約)。
    """
    tracker.wait(url)
    try:
        res = requests.head(
            url, headers={"User-Agent": UA}, timeout=IMAGE_TIMEOUT, allow_redirects=True
        )
        if res.status_code == 405:
            raise requests.RequestException("HEAD not allowed, falling back to GET")
        return classify_image_status(res.status_code, res.headers.get("Content-Type"))
    except requests.RequestException:
        pass
    try:
        with requests.get(
            url,
            headers={"User-Agent": UA},
            timeout=IMAGE_TIMEOUT,
            stream=True,
            allow_redirects=True,
        ) as res:
            return classify_image_status(res.status_code, res.headers.get("Content-Type"))
    except requests.RequestException:
        return classify_image_status(None, None)


def run_audit(
    animals: list[dict[str, Any]],
    js_hosts: set[str],
) -> list[dict[str, Any]]:
    """対象個体すべてを照合する (ページキャッシュ・画像キャッシュ付き)。"""
    tracker = _PolitenessTracker()
    page_cache: dict[str, tuple[str, set[str] | None]] = {}
    image_cache: dict[str, str] = {}

    results: list[dict[str, Any]] = []
    for i, animal in enumerate(animals, 1):
        source_url = animal.get("source_url", "")
        host = urlparse(source_url).hostname or ""

        if host in js_hosts:
            page_status, page_images = "skipped_js", None
        else:
            key = page_cache_key(source_url)
            if key not in page_cache:
                page_cache[key] = fetch_page(source_url, tracker)
            page_status, page_images = page_cache[key]

        image_statuses: dict[str, str] = {}
        for image_url in animal.get("image_urls") or []:
            if image_url not in image_cache:
                image_cache[image_url] = check_image_url(image_url, tracker)
            image_statuses[image_url] = image_cache[image_url]

        r = audit_animal_images(
            animal,
            page_status=page_status,
            page_images=page_images,
            image_statuses=image_statuses,
        )
        marker = "!" if r["flags"] else "."
        print(
            f"  [{i}/{len(animals)}] {marker} id={r['id']} page={page_status} "
            f"flags={','.join(r['flags']) or '-'}",
            file=sys.stderr,
        )
        results.append(r)
    return results


def write_markdown(result: dict[str, Any], path: Path) -> None:
    lines: list[str] = []
    animal_results = result["animal_results"]
    flagged = [
        r
        for r in animal_results
        if "image_not_found_on_page" in r["flags"] or "image_broken_link" in r["flags"]
    ]
    lines.append(f"# 画像URL実在監査 (T102) {result['generated_at']}")
    lines.append("")
    lines.append(f"- 本日のシャード: {result['shard']} / {result['rotation_days']} (7日で一巡)")
    lines.append(f"- 対象個体: {len(animal_results)} 件")
    lines.append(f"- 乖離疑い: **{len(flagged)} 件**")
    lines.append("")
    lines.append(
        "image_not_found_on_page はサイト側の掲載入れ替わりでも起こりえます。"
        "この結果だけで別個体混入と確定させず、元ページ・元画像を目視確認してください。"
    )
    lines.append("")

    lines.append("## 乖離疑い一覧")
    lines.append("")
    lines.append("| ID | 元ページ | フラグ |")
    lines.append("| ---: | --- | --- |")
    for r in flagged:
        lines.append(f"| {r['id']} | {r['source_url']} | {', '.join(r['flags'])} |")
    if not flagged:
        lines.append("(なし)")
    lines.append("")

    error_results = [
        r
        for r in animal_results
        if "page_fetch_error" in r["flags"] or "image_fetch_error" in r["flags"]
    ]
    lines.append(f"## 取得エラー (一時障害の可能性・通知対象外): {len(error_results)} 件")
    lines.append("")
    for r in error_results[:30]:
        lines.append(f"- id={r['id']} {r['source_url']} [{', '.join(r['flags'])}]")
    if len(error_results) > 30:
        lines.append(f"... 他 {len(error_results) - 30} 件")
    lines.append("")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument(
        "--rotation-days",
        type=int,
        default=DEFAULT_ROTATION_DAYS,
        help="全体を何日で一巡させるか (既定7。1指定で全件毎回実行)",
    )
    parser.add_argument(
        "--shard", type=int, help="対象シャード番号を明示指定 (既定は本日の日付から自動決定)"
    )
    parser.add_argument("--limit", type=int, help="デバッグ用に先頭 N 件だけ処理")
    parser.add_argument("--out-dir", default=str(ROOT / "reports"))
    args = parser.parse_args()

    print(f"[image-url-audit] API: {args.api_base}", file=sys.stderr)
    api_animals = fetch_api_animals(args.api_base)
    print(f"[image-url-audit] API 公開中 {len(api_animals)} 件", file=sys.stderr)

    shard = args.shard if args.shard is not None else shard_for_today(args.rotation_days)
    target = [a for a in api_animals if in_shard(a["id"], shard, args.rotation_days)]
    if args.limit:
        target = target[: args.limit]
    print(
        f"[image-url-audit] シャード {shard}/{args.rotation_days} 対象 {len(target)} 件",
        file=sys.stderr,
    )

    js_hosts = js_required_hosts()
    animal_results = run_audit(target, js_hosts)

    result = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "api_base": args.api_base,
        "api_total": len(api_animals),
        "shard": shard,
        "rotation_days": args.rotation_days,
        "shard_total": len(target),
        "animal_results": animal_results,
    }

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = date.today().strftime("%Y%m%d")
    json_path = out_dir / f"image_url_audit_{stamp}.json"
    md_path = out_dir / f"image_url_audit_{stamp}.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    write_markdown(result, md_path)
    print(f"[image-url-audit] 出力: {json_path} / {md_path}", file=sys.stderr)

    # 乖離 (image_not_found_on_page/image_broken_link) があれば Discord 通知。
    # DISCORD_WEBHOOK_URL 未設定時は NotificationClient が no-op でログ警告のみ。
    notify_config: dict[str, str] = {}
    discord_webhook = os.environ.get("DISCORD_WEBHOOK_URL")
    if discord_webhook:
        notify_config["discord_webhook_url"] = discord_webhook
    notified = maybe_notify(result, NotificationClient(notify_config))
    print(
        f"[image-url-audit] Discord 通知: {'送信' if notified else '乖離なし/対象外'}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
