"""公開中の動物からランダム N 件を抜き、人が実サイトと突き合わせるためのシートを出す。

宣伝開始の可否を判定する 1 回きりの人手監査 (W001/T004) 用。全件目視は不可能なので
母数を絞り、慎重さは突き合わせの厳密さで担保する。判定対象は致命 8 フィールド:

    status / phone / source_url / location / prefecture / category / species / image_urls

母集団は「公開 API が返す全件」= 実際にサイトへ出ている個体。収集が止まっている
サイトの個体 (stale) も母集団に含める。そこを除外すると「もういない子を載せ続けて
いる」種類の誤りが監査をすり抜けるため。除外したい場合だけ --exclude-stale を使う。

使い方:
    python3 scripts/publication_audit.py                    # 50件・seed=今日の日付
    python3 scripts/publication_audit.py --n 20 --seed 7    # 件数と seed を指定
    python3 scripts/publication_audit.py --exclude-stale    # 直近収集ぶんだけを母集団に

出力 (既定 reports/):
    publication_audit_YYYYMMDD.html   人が突き合わせる判定シート (画像・両リンク付き)
    publication_audit_YYYYMMDD.json   seed と抽出 ID の記録 (再現・証跡用)
"""

from __future__ import annotations

import argparse
import html
import json
import random
import sys
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# 欠損の定義は本体と1つに保つ (別実装にすると "不明" 等のプレースホルダで食い違う)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.data_collector.domain.quality_metrics import is_missing_value

DEFAULT_API_BASE = "https://oneco-api-tvlsrcvyuq-an.a.run.app"
DEFAULT_SITE_BASE = "https://frontend-psi-ten-73.vercel.app"
DEFAULT_SAMPLE_SIZE = 50
MAX_THUMBNAILS = 3
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) oneco-publication-audit/1.0"

# 致命 8 フィールド。誤っていたら不合格にする対象 (PROJECT.md の品質ゲート)。
CRITICAL_FIELDS: dict[str, str] = {
    "status": "状態",
    "phone": "問い合わせ先",
    "source_url": "元ページURL",
    "location": "所在地",
    "prefecture": "都道府県",
    "category": "区分",
    "species": "種別",
    "image_urls": "画像",
}


def get_json(url: str) -> dict[str, Any]:
    """URL を GET して JSON を返す (テストではここを差し替える)。"""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as res:
        return json.load(res)


def fetch_animals(api_base: str, limit: int = 100) -> list[dict[str, Any]]:
    """公開 API から全件をページングして取得する。"""
    items: list[dict[str, Any]] = []
    offset = 0
    while True:
        page = get_json(f"{api_base.rstrip('/')}/animals?limit={limit}&offset={offset}")
        got = page.get("items") or []
        items.extend(got)
        if not page.get("meta", {}).get("has_next") or not got:
            # has_next が立ったまま空ページを返す API 不具合でも止まるようにする
            break
        offset += len(got)
    return items


def classify_freshness(animal: dict[str, Any], base_date: str) -> str:
    """基準日 (直近の収集日) に確認できた個体か。

    fresh   = 基準日以降に収集で確認できた
    stale   = 確認が基準日より前 (実サイトから消えている疑い)
    unknown = 収集記録なし
    """
    value = animal.get("last_collected_at")
    if not value:
        return "unknown"
    return "fresh" if value[:10] >= base_date else "stale"


def sample_animals(animals: list[dict[str, Any]], n: int, seed: int) -> list[dict[str, Any]]:
    """seed 固定でランダム N 件を抜く (母集団が少なければ全件)。"""
    if not animals:
        return []
    rng = random.Random(seed)
    return rng.sample(animals, min(n, len(animals)))


def _display(key: str, value: Any) -> str:
    if key == "image_urls":
        urls = value or []
        return f"{len(urls)}枚" + (f"（先頭: {urls[0]}）" if urls else "")
    return "" if value is None else str(value)


def _is_missing(value: Any) -> bool:
    """本体と同じ定義で欠損を判定する ("不明" 等のプレースホルダを含む)。"""
    return is_missing_value(value)


def parse_row_index(source_url: str | None) -> int | None:
    """一覧ページ内の行番号 (`#row=N`) を返す。個体ごとの URL なら None。

    1ページに複数個体が載るサイトでは adapter が `<list_url>#row=N` という
    仮想 URL を source_url にしている (single_page_table / pdf_table)。実ページに
    その id は無いのでブラウザは先頭を開くだけで、人は自力で該当行を探す必要がある。
    """
    if not source_url or "#row=" not in source_url:
        return None
    try:
        return int(source_url.rsplit("#row=", 1)[1])
    except ValueError:
        return None


# 一覧ページ内の該当個体を人が探し当てるための手がかり (致命8フィールド外)
MATCH_HINT_FIELDS: dict[str, str] = {
    "management_number": "管理番号",
    "shelter_date": "収容日",
    "sex": "性別",
    "breed": "品種",
    "color": "毛色",
    "name": "名前",
}


def extract_match_hints(animal: dict[str, Any]) -> list[tuple[str, str]]:
    """行を特定するための手がかりのうち、値があるものだけを返す。"""
    return [
        (label, str(animal[key]))
        for key, label in MATCH_HINT_FIELDS.items()
        if not is_missing_value(animal.get(key))
    ]


def extract_critical_fields(animal: dict[str, Any]) -> list[dict[str, Any]]:
    """致命 8 フィールドを表示用に整える。"""
    return [
        {
            "key": key,
            "label": label,
            "display": _display(key, animal.get(key)),
            "missing": _is_missing(animal.get(key)),
        }
        for key, label in CRITICAL_FIELDS.items()
    ]


def build_manifest(
    animals: list[dict[str, Any]], seed: int, base_date: str, population: int
) -> dict[str, Any]:
    """再現と証跡のための記録を作る。"""
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "seed": seed,
        "base_date": base_date,
        "population": population,
        "sample_size": len(animals),
        "sampled_ids": [a.get("id") for a in animals],
        "sampled": [
            {
                "id": a.get("id"),
                "source_url": a.get("source_url"),
                "freshness": classify_freshness(a, base_date),
                **{k: a.get(k) for k in CRITICAL_FIELDS},
            }
            for a in animals
        ],
    }


def _card(index: int, animal: dict[str, Any], base_date: str, site_base: str) -> str:
    e = html.escape
    animal_id = animal.get("id")
    fresh = classify_freshness(animal, base_date)
    last_seen = animal.get("last_collected_at") or "記録なし"

    rows = "".join(
        f'<tr class="{"missing" if f["missing"] else ""}">'
        f"<th>{e(f['label'])}<small>{e(f['key'])}</small></th>"
        f"<td>{e(f['display']) or '<span class=empty>（空）</span>'}</td>"
        f'<td class="judge">'
        f'<label><input type="radio" name="f{animal_id}_{f["key"]}" value="ok">合</label>'
        f'<label><input type="radio" name="f{animal_id}_{f["key"]}" value="ng">否</label>'
        f"</td></tr>"
        for f in extract_critical_fields(animal)
    )

    all_images = animal.get("image_urls") or []
    images = (
        "".join(
            f'<a href="{e(str(u))}" target="_blank" rel="noreferrer">'
            f'<img src="{e(str(u))}" loading="lazy" alt="" '
            f"onerror=\"this.classList.add('dead');this.alt='リンク切れ'\"></a>"
            for u in all_images[:MAX_THUMBNAILS]
        )
        or '<div class="noimg">画像なし</div>'
    ) + (
        f'<div class="more">ほか{len(all_images) - MAX_THUMBNAILS}枚は元ページで確認</div>'
        if len(all_images) > MAX_THUMBNAILS
        else ""
    )

    if fresh == "unknown":
        warn = (
            '<div class="warn">収集で一度も確認されていない個体 — '
            "実サイトから消えている可能性がある</div>"
        )
    elif fresh == "stale":
        warn = (
            f'<div class="warn">最終確認が古い（{e(str(last_seen)[:10])}）— '
            "実サイトから消えている可能性がある</div>"
        )
    else:
        warn = ""

    # 一覧ページ内の1行を指す仮想 URL は、リンクを開いても該当個体まで飛ばない
    row_index = parse_row_index(animal.get("source_url"))
    if row_index is None:
        rowhint = ""
    else:
        hints = extract_match_hints(animal)
        hint_html = (
            "".join(f"<span>{e(label)}: <b>{e(value)}</b></span>" for label, value in hints)
            or "<span>手がかりになる項目が無い（管理番号・収容日等がすべて空）</span>"
        )
        is_pdf = ".pdf" in str(animal.get("source_url") or "").lower()
        media = "PDF" if is_pdf else "一覧ページ"
        rowhint = (
            f'<div class="rowhint">この個体は{media}内の <b>{row_index + 1}番目</b>'
            f"（#row={row_index}）。リンクを開いても自動では移動しないので、"
            f"次の手がかりで該当行を探して突き合わせる。"
            f'<div class="hints">{hint_html}</div></div>'
        )

    return f"""
<article class="card" id="a{animal_id}" data-id="{animal_id}" data-freshness="{e(fresh)}">
  <header>
    <span class="no">{index}</span>
    <span class="meta">id={animal_id} / {e(str(animal.get("species") or ""))} /
      {e(str(animal.get("prefecture") or ""))}</span>
    <span class="links">
      <a href="{e(str(animal.get("source_url") or ""))}" target="_blank" rel="noreferrer">元ページ↗</a>
      <a href="{e(site_base.rstrip("/"))}/animals/{animal_id}" target="_blank" rel="noreferrer">oneco↗</a>
    </span>
  </header>
  {warn}{rowhint}
  <div class="body">
    <div class="images">{images}</div>
    <table>{rows}</table>
  </div>
  <footer>
    <label class="verdict"><input type="radio" name="v{animal_id}" value="ok">この個体は一致</label>
    <label class="verdict ng"><input type="radio" name="v{animal_id}" value="ng">誤りあり</label>
    <input class="note" name="n{animal_id}" placeholder="気づいたこと（任意）">
  </footer>
</article>"""


def render_html(animals: list[dict[str, Any]], seed: int, base_date: str, site_base: str) -> str:
    """人が突き合わせるための判定シートを組み立てる。"""
    e = html.escape
    stale_n = sum(1 for a in animals if classify_freshness(a, base_date) != "fresh")
    cards = "\n".join(_card(i, a, base_date, site_base) for i, a in enumerate(animals, start=1))
    return f"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>oneco 掲載品質の突き合わせ（{len(animals)}件・seed={seed}）</title>
<style>
  :root {{ color-scheme: light dark; --line:#d8d8d8; --warn:#b45309; --ng:#b91c1c; --ok:#15803d;
          --warn-bg:#fef3c7; --ng-bg:#fee2e2; --muted:#666; --faint:#999;
          --hint-bg:#eef2ff; }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --line:#3a3a3a; --warn:#fbbf24; --ng:#f87171; --ok:#4ade80;
            --warn-bg:#3b2f0b; --ng-bg:#3b1414; --muted:#a3a3a3; --faint:#8a8a8a;
            --hint-bg:#1e2140; }}
  }}
  body {{ font-family: system-ui, -apple-system, "Hiragino Sans", sans-serif;
         margin:0 auto; padding:16px; max-width:940px; line-height:1.6; }}
  h1 {{ font-size:1.25rem; margin:0 0 4px; }}
  .lead {{ color:var(--muted); font-size:.9rem; margin:0 0 16px; }}
  .bar {{ position:sticky; top:0; background:Canvas; border-bottom:1px solid var(--line);
         padding:8px 0; margin-bottom:12px; display:flex; gap:12px; align-items:center;
         flex-wrap:wrap; z-index:5; }}
  .bar button {{ font:inherit; padding:6px 12px; border-radius:6px; border:1px solid var(--line);
                background:Canvas; color:inherit; cursor:pointer; }}
  .card {{ border:1px solid var(--line); border-radius:10px; margin:0 0 14px; overflow:hidden; }}
  .card header {{ display:flex; gap:10px; align-items:center; padding:8px 12px;
                 border-bottom:1px solid var(--line); flex-wrap:wrap; }}
  .no {{ font-weight:700; }}
  .meta {{ color:var(--muted); font-size:.85rem; }}
  .links {{ margin-left:auto; display:flex; gap:10px; }}
  .warn {{ background:var(--warn-bg); color:var(--warn); padding:6px 12px; font-size:.85rem; }}
  .body {{ display:flex; gap:12px; padding:12px; flex-wrap:wrap; }}
  .images {{ display:flex; gap:6px; flex-wrap:wrap; }}
  .images img {{ width:110px; height:110px; object-fit:cover; border-radius:6px;
                border:1px solid var(--line); }}
  .images img.dead {{ border:2px solid var(--ng); background:var(--ng-bg); object-fit:contain;
                     font-size:.75rem; color:var(--ng); }}
  .rowhint {{ background:var(--hint-bg); padding:6px 12px; font-size:.85rem; }}
  .rowhint .hints {{ display:flex; gap:10px; flex-wrap:wrap; margin-top:2px; color:var(--muted); }}
  .more {{ align-self:center; font-size:.78rem; color:var(--muted); }}
  .noimg {{ width:110px; height:110px; display:grid; place-items:center; color:var(--faint);
           border:1px dashed var(--line); border-radius:6px; font-size:.8rem; }}
  table {{ border-collapse:collapse; flex:1 1 380px; }}
  th, td {{ border-bottom:1px solid var(--line); padding:4px 8px; text-align:left;
           font-size:.9rem; vertical-align:top; }}
  th {{ width:120px; font-weight:600; }}
  th small {{ display:block; color:var(--faint); font-weight:400; font-size:.72rem; }}
  td {{ word-break:break-all; }}
  .judge {{ width:96px; white-space:nowrap; }}
  .judge label {{ margin-right:6px; font-size:.8rem; }}
  tr.missing td {{ background:var(--ng-bg); }}
  .empty {{ color:var(--faint); }}
  footer {{ display:flex; gap:12px; align-items:center; padding:8px 12px;
           border-top:1px solid var(--line); flex-wrap:wrap; }}
  .verdict {{ font-size:.9rem; color:var(--ok); }}
  .verdict.ng {{ color:var(--ng); }}
  .note {{ flex:1 1 220px; font:inherit; padding:4px 8px; border:1px solid var(--line);
          border-radius:6px; background:Canvas; color:inherit; }}
  .done {{ outline:2px solid var(--ok); }}
  .flagged {{ outline:2px solid var(--ng); }}
  @media print {{ .bar {{ display:none; }} .card {{ break-inside:avoid; }} }}
</style></head><body>
<h1>oneco 掲載品質の突き合わせ</h1>
<p class="lead">公開中からランダム{len(animals)}件（seed={seed} / 基準日 {e(base_date)}）。
各件で「元ページ↗」を開き、致命8フィールドが実際の掲載と一致するかを見る。
直近の収集で確認できていない個体 {stale_n} 件を含む。</p>
<div class="bar">
  <strong id="progress">0 / {len(animals)}</strong>
  <span id="ngcount" style="color:var(--ng)"></span>
  <button type="button" id="save">判定を保存してJSONを書き出す</button>
  <button type="button" id="clear">保存をクリア</button>
</div>
{cards}
<script>
const KEY = "oneco-audit-{seed}-{base_date}";
const cards = [...document.querySelectorAll(".card")];
const load = () => JSON.parse(localStorage.getItem(KEY) || "{{}}");
function paint() {{
  const s = load();
  let done = 0, ng = 0;
  for (const c of cards) {{
    const r = s[c.dataset.id];
    c.classList.toggle("done", r?.verdict === "ok");
    c.classList.toggle("flagged", r?.verdict === "ng");
    if (r?.verdict) done++;
    if (r?.verdict === "ng") ng++;
  }}
  document.getElementById("progress").textContent = done + " / " + cards.length;
  document.getElementById("ngcount").textContent = ng ? "誤りあり " + ng + "件" : "";
}}
function collect() {{
  const s = {{}};
  for (const c of cards) {{
    const id = c.dataset.id;
    const verdict = c.querySelector(`input[name="v${{id}}"]:checked`)?.value || null;
    const note = c.querySelector(`input[name="n${{id}}"]`).value || "";
    const fields = {{}};
    for (const el of c.querySelectorAll('input[type=radio]:checked')) {{
      if (el.name.startsWith("f")) fields[el.name.split("_").slice(1).join("_")] = el.value;
    }}
    if (verdict || note || Object.keys(fields).length) {{
      s[id] = {{ verdict, note, fields, freshness: c.dataset.freshness }};
    }}
  }}
  return s;
}}
function restore() {{
  const s = load();
  for (const c of cards) {{
    const r = s[c.dataset.id]; if (!r) continue;
    const id = c.dataset.id;
    if (r.verdict) c.querySelector(`input[name="v${{id}}"][value="${{r.verdict}}"]`).checked = true;
    if (r.note) c.querySelector(`input[name="n${{id}}"]`).value = r.note;
    for (const [k, v] of Object.entries(r.fields || {{}})) {{
      const el = c.querySelector(`input[name="f${{id}}_${{k}}"][value="${{v}}"]`);
      if (el) el.checked = true;
    }}
  }}
  paint();
}}
document.addEventListener("input", () => {{
  localStorage.setItem(KEY, JSON.stringify(collect())); paint();
}});
document.getElementById("save").addEventListener("click", () => {{
  const blob = new Blob([JSON.stringify(
    {{ key: KEY, seed: {seed}, base_date: "{base_date}", results: collect() }}, null, 1)],
    {{ type: "application/json" }});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `publication_audit_result_{seed}_{base_date}.json`;
  a.click();
}});
document.getElementById("clear").addEventListener("click", () => {{
  if (confirm("保存した判定を消す？")) {{ localStorage.removeItem(KEY); location.reload(); }}
}});
restore();
</script>
</body></html>"""


def resolve_base_date(animals: list[dict[str, Any]]) -> str:
    """母集団の中で最も新しい収集日を基準日にする。"""
    dates = [a["last_collected_at"][:10] for a in animals if a.get("last_collected_at")]
    return max(dates) if dates else datetime.now(UTC).date().isoformat()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--n", type=int, default=DEFAULT_SAMPLE_SIZE, help="抽出件数 (既定50)")
    p.add_argument("--seed", type=int, default=None, help="乱数シード (既定は今日の日付)")
    p.add_argument("--api-base", default=DEFAULT_API_BASE)
    p.add_argument("--site-base", default=DEFAULT_SITE_BASE)
    p.add_argument("--out-dir", default="reports")
    p.add_argument(
        "--exclude-stale",
        action="store_true",
        help="直近収集で確認できた個体だけを母集団にする (既定は公開中の全件)",
    )
    args = p.parse_args(argv)

    today = datetime.now(UTC).date()
    seed = args.seed if args.seed is not None else int(today.strftime("%Y%m%d"))

    print(f"公開 API から取得中: {args.api_base}")
    animals = fetch_animals(args.api_base)
    base_date = resolve_base_date(animals)
    counts: dict[str, int] = {}
    for a in animals:
        k = classify_freshness(a, base_date)
        counts[k] = counts.get(k, 0) + 1
    print(f"公開中 {len(animals)} 件 (基準日 {base_date}): {counts}")

    population = animals
    if args.exclude_stale:
        population = [a for a in animals if classify_freshness(a, base_date) == "fresh"]
        print(f"--exclude-stale: 母集団を {len(population)} 件に絞る")

    sampled = sample_animals(population, args.n, seed)
    if not sampled:
        print("母集団が空。抽出できない", file=sys.stderr)
        return 1

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = today.strftime("%Y%m%d")
    html_path = out_dir / f"publication_audit_{stamp}.html"
    json_path = out_dir / f"publication_audit_{stamp}.json"

    html_path.write_text(
        render_html(sampled, seed=seed, base_date=base_date, site_base=args.site_base),
        encoding="utf-8",
    )
    manifest = build_manifest(sampled, seed=seed, base_date=base_date, population=len(population))
    json_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")

    stale_n = sum(1 for a in sampled if classify_freshness(a, base_date) != "fresh")
    print(f"抽出 {len(sampled)} 件 (seed={seed}) — うち最終確認が古い個体 {stale_n} 件")
    print(f"  判定シート: {html_path}")
    print(f"  記録:       {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
