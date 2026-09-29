#!/usr/bin/env python3
"""oneco v2 静的サイト生成。data/latest.json → site/dist/。

使い方（v2 ディレクトリで）:

    python site/build.py [--data data/latest.json] [--out site/dist] [--config site/config.json]

`python -m site.build` は使えない。`site` は Python 標準ライブラリのモジュール名で、
インタプリタ起動時に先に読み込まれるため、このディレクトリをパッケージとして解決できない。

標準ライブラリだけで動く。HTML に埋める値は全部 esc() を通し、href/src に入れる URL は
safe_url() で http(s) 以外を捨てる。

出力先は前回の build が作ったもの（目印 .oneco-build がある）か空のときだけ中身を消して作り直す。
それ以外のディレクトリを渡すと止まる（消してはいけない場所を消さないため）。

config.json:
    site_name   サイト名
    base_url    公開 URL（OG タグ・sitemap の絶対 URL に使う）
    issues_url  撤去依頼などの窓口（GitHub Issues）
    affiliate   「迎える準備」枠。[{"title": "…", "url": "https://…", "note": "…"}]。空なら枠ごと出さない
"""

from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA = ROOT / "data" / "latest.json"
DEFAULT_OUT = ROOT / "site" / "dist"
DEFAULT_CONFIG = ROOT / "site" / "config.json"
MARKER = ".oneco-build"

DEFAULT_CFG: dict[str, Any] = {
    "site_name": "oneco",
    "base_url": "https://oneco.pages.dev",
    "issues_url": "https://github.com/9mak/oneco/issues",
    "affiliate": [],
}

SPECIES = {"dog": "犬", "cat": "猫", "other": "その他"}
KINDS = {"adoption": "譲渡対象", "sheltered": "収容中", "stray": "迷子収容"}
KIND_HELP = {
    "adoption": "自治体が新しい飼い主を募集している子",
    "sheltered": "自治体に収容されている子（飼い主の迎えや譲渡を待っている）",
    "stray": "飼い主が分からないまま収容された子（心当たりがあれば自治体へ）",
}
KIND_ORDER = {"adoption": 0, "sheltered": 1, "stray": 2}
STATUS = {
    "ok": "確認済み",
    "empty": "本日は 0 頭",
    "failed": "本日は確認できませんでした",
    "link_only": "リンクのみ",
    "disabled": "停止中",
}
# 詳細ページに出す項目（取れているものだけ出す）
FIELDS = [
    ("name", "名前"),
    ("sex", "性別"),
    ("age", "年齢・生年月日"),
    ("breed", "種類"),
    ("color", "毛色"),
    ("size", "大きさ"),
    ("management_no", "管理番号"),
    ("shelter_date", "収容日"),
    ("location", "収容場所・発見場所"),
    ("note", "備考"),
]
PREF_ORDER = [
    "北海道", "青森県", "岩手県", "宮城県", "秋田県", "山形県", "福島県",
    "茨城県", "栃木県", "群馬県", "埼玉県", "千葉県", "東京都", "神奈川県",
    "新潟県", "富山県", "石川県", "福井県", "山梨県", "長野県", "岐阜県", "静岡県", "愛知県",
    "三重県", "滋賀県", "京都府", "大阪府", "兵庫県", "奈良県", "和歌山県",
    "鳥取県", "島根県", "岡山県", "広島県", "山口県",
    "徳島県", "香川県", "愛媛県", "高知県",
    "福岡県", "佐賀県", "長崎県", "熊本県", "大分県", "宮崎県", "鹿児島県", "沖縄県",
]
PREF_INDEX = {p: i for i, p in enumerate(PREF_ORDER)}
ID_RE = re.compile(r"[A-Za-z0-9_-]{1,64}")


# ---------------------------------------------------------------- helpers

def esc(v: Any) -> str:
    """HTML に埋める値は必ずこれを通す。"""
    return html.escape("" if v is None else str(v), quote=True)


def safe_url(u: Any) -> str:
    """href/src に入れてよい URL だけ返す（http/https 以外は空）。"""
    if not isinstance(u, str):
        return ""
    u = u.strip()
    return u if u.lower().startswith(("http://", "https://")) else ""


def tel_href(phone: str) -> str:
    digits = re.sub(r"[^0-9+]", "", phone)
    return f"tel:{digits}" if digits else ""


def pref_key(p: str) -> tuple[int, str]:
    return PREF_INDEX.get(p, len(PREF_ORDER)), p


def pref_path(p: str) -> str:
    return f"/pref/{quote(p)}/"


def animal_path(aid: str) -> str:
    return f"/animals/{quote(aid)}/"


def fmt_date(s: Any) -> str:
    """'2026-09-28' や '2026-09-28-saga' → '2026年9月28日'。読めなければそのまま。"""
    if not isinstance(s, str):
        return ""
    try:
        d = datetime.strptime(s[:10], "%Y-%m-%d").date()
    except ValueError:
        return s
    return f"{d.year}年{d.month}月{d.day}日"


def iso_date(s: Any) -> str:
    if isinstance(s, str):
        try:
            return datetime.strptime(s[:10], "%Y-%m-%d").date().isoformat()
        except ValueError:
            pass
    return date.today().isoformat()


def species_label(a: dict[str, Any]) -> str:
    return SPECIES.get(str(a.get("species")), SPECIES["other"])


def kind_label(a: dict[str, Any]) -> str:
    return KINDS.get(str(a.get("kind")), str(a.get("kind") or ""))


def headline(a: dict[str, Any]) -> str:
    """カード・詳細の見出し。名前があれば名前、無ければ種別。"""
    name = a.get("name")
    return str(name) if name else f"{kind_label(a)}の{species_label(a)}"


def subline(a: dict[str, Any]) -> str:
    parts = [str(a[k]) for k in ("breed", "sex", "age") if a.get(k)]
    return " / ".join(parts)


def shorten(s: Any, n: int) -> str:
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[: n - 1] + "…"


# ---------------------------------------------------------------- page shell

def page(cfg: dict[str, Any], *, title: str, desc: str, path: str, body: str,
         og_image: str = "", og_type: str = "website", extra_head: str = "", body_attrs: str = "",
         data_date: str = "") -> str:
    site = esc(cfg["site_name"])
    base = cfg["base_url"].rstrip("/")
    url = esc(base + path)
    og_img = f'\n<meta property="og:image" content="{esc(og_image)}">' if og_image else ""
    full_title = esc(title) if title == cfg["site_name"] else f"{esc(title)}｜{site}"
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{full_title}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{url}">
<meta property="og:type" content="{esc(og_type)}">
<meta property="og:site_name" content="{site}">
<meta property="og:title" content="{full_title}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{url}">{og_img}
<meta name="twitter:card" content="{'summary_large_image' if og_image else 'summary'}">
<meta name="theme-color" content="#1f3a5f">
<link rel="stylesheet" href="/style.css">{extra_head}
</head>
<body{body_attrs}>
<header class="site-head">
<a class="brand" href="/">{site}</a>
<nav class="nav"><a href="/">都道府県</a><a href="/sources/">情報源</a><a href="/about/">このサイトについて</a></nav>
</header>
<main class="wrap">
{body}
</main>
<footer class="site-foot">
<p>掲載しているのは各自治体が公開している情報です。{f'データ確認日: {esc(fmt_date(data_date))}。' if data_date else ''}最新の状況は自治体のページ・電話でご確認ください。</p>
<p><a href="/sources/">情報源の一覧</a> ・ <a href="/about/">運営方針・撤去依頼</a></p>
</footer>
</body>
</html>
"""


# ---------------------------------------------------------------- partials

def placeholder() -> str:
    """写真が無い子の枠。絵は CSS（.ph の疑似要素）だけで描く。"""
    return '<div class="ph" role="img" aria-label="写真はありません"><span>写真はありません</span></div>'


def media(a: dict[str, Any], *, big: bool = False) -> str:
    img = safe_url(a.get("image_url"))
    if not img:
        return f'<div class="media">{placeholder()}</div>'
    alt = esc(f"{headline(a)}（{a.get('municipality') or ''}）")
    attrs = 'loading="eager" fetchpriority="high"' if big else 'loading="lazy"'
    # 自治体サイトの写真を直接表示する。取れなかったときは JS でプレースホルダに差し替える
    return (f'<div class="media"><img src="{esc(img)}" alt="{alt}" referrerpolicy="no-referrer" {attrs} '
            f'onerror="this.parentNode.classList.add(\'noimg\');this.remove()">{placeholder()}</div>')


def badges(a: dict[str, Any]) -> str:
    sp, kd = str(a.get("species") or "other"), str(a.get("kind") or "")
    return (f'<span class="badge sp-{esc(sp)}">{esc(species_label(a))}</span>'
            f'<span class="badge kd-{esc(kd)}">{esc(kind_label(a))}</span>')


def card(a: dict[str, Any]) -> str:
    sub = subline(a)
    sub_html = f'<p class="sub">{esc(sub)}</p>' if sub else ""
    return f"""<a class="card" href="{esc(animal_path(a['id']))}" data-species="{esc(a.get('species') or 'other')}" data-kind="{esc(a.get('kind') or '')}">
{media(a)}
<div class="card-body">
<div class="badges">{badges(a)}</div>
<h3>{esc(headline(a))}</h3>
{sub_html}
<p class="muni">{esc(a.get('municipality'))}</p>
</div>
</a>"""


def filter_bar(name: str, options: list[tuple[str, str]]) -> str:
    btns = "".join(
        f'<button type="button" data-filter="{esc(name)}" data-value="{esc(v)}" aria-pressed="{"true" if v == "all" else "false"}">{esc(label)}</button>'
        for v, label in options)
    return f'<div class="chips" role="group">{btns}</div>'


# ---------------------------------------------------------------- pages

def build_index(cfg: dict[str, Any], data: dict[str, Any], animals: list[dict[str, Any]]) -> str:
    by_pref: dict[str, Counter[str]] = {}
    for a in animals:
        c = by_pref.setdefault(str(a.get("prefecture") or "不明"), Counter())
        c[str(a.get("species") or "other")] += 1
        c["total"] += 1
    total = Counter(str(a.get("species") or "other") for a in animals)
    ok_sources = sum(1 for s in data.get("sources", []) if s.get("status") == "ok")
    rows = []
    for p in sorted(by_pref, key=pref_key):
        c = by_pref[p]
        rows.append(
            f'<li data-pref="{esc(p)}" data-dog="{c["dog"]}" data-cat="{c["cat"]}" data-other="{c["other"]}" data-total="{c["total"]}">'
            f'<a href="{esc(pref_path(p))}"><span class="pref">{esc(p)}</span>'
            f'<span class="cnt"><b class="n">{c["total"]}</b> 頭</span></a></li>')
    body = f"""<section class="intro">
<h1>保護犬・保護猫を、自治体から探す</h1>
<p>{esc(cfg['site_name'])} は、全国の自治体（動物愛護センター・保健所など）が公開している保護犬・保護猫の情報を 1 か所にまとめたサイトです。毎日それぞれの自治体のページを確認し、その日に掲載されている子だけを出典つきで載せています。気になる子がいたら、掲載元の自治体に直接ご連絡ください。</p>
<p class="stats">{esc(fmt_date(data.get('date')))} 時点: 犬 <b>{total['dog']}</b> 頭 ・ 猫 <b>{total['cat']}</b> 頭{f" ・ その他 <b>{total['other']}</b> 頭" if total['other'] else ''}（{len(by_pref)} 都道府県・{ok_sources} 自治体ページ）</p>
</section>
<section>
<h2>都道府県から探す</h2>
{filter_bar('species', [('all', 'すべて'), ('dog', '犬'), ('cat', '猫')])}
<ul class="pref-list" id="pref-list">
{chr(10).join(rows) if rows else '<li class="empty">本日の掲載はありません。</li>'}
</ul>
<p class="hint">区分の意味: 譲渡対象＝{esc(KIND_HELP['adoption'])}。収容中＝{esc(KIND_HELP['sheltered'])}。迷子収容＝{esc(KIND_HELP['stray'])}。</p>
</section>
<script>
(function(){{
  var list=document.getElementById('pref-list');
  var btns=document.querySelectorAll('[data-filter="species"]');
  function apply(v){{
    btns.forEach(function(b){{b.setAttribute('aria-pressed',b.dataset.value===v?'true':'false');}});
    list.querySelectorAll('li[data-pref]').forEach(function(li){{
      var n=Number(li.dataset[v==='all'?'total':v]||0);
      li.querySelector('.n').textContent=n;
      li.hidden=n===0;
      var a=li.querySelector('a');
      a.search=v==='all'?'':'?species='+v;
    }});
  }}
  btns.forEach(function(b){{b.addEventListener('click',function(){{apply(b.dataset.value);}});}});
}})();
</script>"""
    return page(cfg, title=cfg["site_name"], path="/", body=body, data_date=str(data.get("date") or ""),
                desc="全国の自治体が公開している保護犬・保護猫の情報を、都道府県ごとに 1 か所で探せます。毎日更新、出典つき。")


PREF_JS = """
(function(){
  var pref=document.body.dataset.pref;
  var grid=document.getElementById('grid');
  var count=document.getElementById('count');
  var empty=document.getElementById('empty');
  var SP={dog:'犬',cat:'猫',other:'その他'};
  var KD={adoption:'譲渡対象',sheltered:'収容中',stray:'迷子収容'};
  var q=new URLSearchParams(location.search);
  var state={species:q.get('species')||'all',kind:q.get('kind')||'all'};
  var cache=null;
  function ok(u){return typeof u==='string'&&/^https?:\\/\\//i.test(u);}
  function el(tag,cls,text){var e=document.createElement(tag);if(cls)e.className=cls;if(text!=null)e.textContent=text;return e;}
  function ph(){var d=el('div','ph');d.setAttribute('role','img');d.setAttribute('aria-label','写真はありません');d.appendChild(el('span',null,'写真はありません'));return d;}
  function card(a){
    var sp=a.species||'other', kd=a.kind||'';
    var c=el('a','card');c.href='/animals/'+encodeURIComponent(a.id)+'/';c.dataset.species=sp;c.dataset.kind=kd;
    var m=el('div','media');
    if(ok(a.image_url)){var img=el('img');img.src=a.image_url;img.alt=(a.name||((KD[kd]||kd)+'の'+(SP[sp]||sp)))+'（'+(a.municipality||'')+'）';img.loading='lazy';img.referrerPolicy='no-referrer';img.onerror=function(){m.classList.add('noimg');img.remove();};m.appendChild(img);}
    m.appendChild(ph());c.appendChild(m);
    var b=el('div','card-body');var bd=el('div','badges');
    bd.appendChild(el('span','badge sp-'+sp,SP[sp]||sp));bd.appendChild(el('span','badge kd-'+kd,KD[kd]||kd));b.appendChild(bd);
    b.appendChild(el('h3',null,a.name||((KD[kd]||kd)+'の'+(SP[sp]||sp))));
    var sub=[a.breed,a.sex,a.age].filter(Boolean).join(' / ');if(sub)b.appendChild(el('p','sub',sub));
    b.appendChild(el('p','muni',a.municipality||''));c.appendChild(b);return c;
  }
  function match(sp,kd){return (state.species==='all'||sp===state.species)&&(state.kind==='all'||kd===state.kind);}
  function syncButtons(){document.querySelectorAll('[data-filter]').forEach(function(b){b.setAttribute('aria-pressed',state[b.dataset.filter]===b.dataset.value?'true':'false');});}
  function apply(){
    syncButtons();var n=0;
    if(cache){grid.textContent='';cache.forEach(function(a){if(match(a.species||'other',a.kind||'')){grid.appendChild(card(a));n++;}});}
    else{grid.querySelectorAll('.card').forEach(function(c){var s=match(c.dataset.species,c.dataset.kind);c.hidden=!s;if(s)n++;});}
    count.textContent=n;empty.hidden=n!==0;
    var p=new URLSearchParams();if(state.species!=='all')p.set('species',state.species);if(state.kind!=='all')p.set('kind',state.kind);
    var qs=p.toString();history.replaceState(null,'',location.pathname+(qs?'?'+qs:''));
  }
  document.querySelectorAll('[data-filter]').forEach(function(b){b.addEventListener('click',function(){state[b.dataset.filter]=b.dataset.value;apply();});});
  if(state.species!=='all'||state.kind!=='all')apply();
  fetch('/data.json',{cache:'no-cache'}).then(function(r){return r.ok?r.json():null;}).then(function(d){
    if(!d||!Array.isArray(d.animals))return;
    cache=d.animals.filter(function(a){return a.prefecture===pref&&a.id;});
    if(state.species!=='all'||state.kind!=='all')apply();
  }).catch(function(){});
})();
"""


def build_pref(cfg: dict[str, Any], data: dict[str, Any], pref: str, animals: list[dict[str, Any]]) -> str:
    c = Counter(str(a.get("species") or "other") for a in animals)
    munis = sorted({str(a.get("municipality") or "") for a in animals})
    cards = "\n".join(card(a) for a in animals)
    body = f"""<nav class="crumbs"><a href="/">都道府県</a> › <span>{esc(pref)}</span></nav>
<h1>{esc(pref)}の保護犬・保護猫</h1>
<p class="stats">{esc(fmt_date(data.get('date')))} 時点: 犬 {c['dog']} 頭 ・ 猫 {c['cat']} 頭{f" ・ その他 {c['other']} 頭" if c['other'] else ''}。掲載元: {esc('、'.join(munis))}</p>
<div class="filters">
{filter_bar('species', [('all', 'すべて'), ('dog', '犬'), ('cat', '猫')])}
{filter_bar('kind', [('all', 'すべての区分'), ('adoption', '譲渡対象'), ('sheltered', '収容中'), ('stray', '迷子収容')])}
</div>
<p class="count"><b id="count">{len(animals)}</b> 頭</p>
<div class="grid" id="grid">
{cards}
</div>
<p class="empty" id="empty" hidden>この条件に当てはまる子はいません。</p>
<script>{PREF_JS}</script>"""
    return page(cfg, title=f"{pref}の保護犬・保護猫", path=pref_path(pref), body=body,
                body_attrs=f' data-pref="{esc(pref)}"', data_date=str(data.get("date") or ""),
                desc=f"{pref}の自治体が{fmt_date(data.get('date'))}に公開している保護犬 {c['dog']} 頭・保護猫 {c['cat']} 頭の一覧。出典つき。")


def build_animal(cfg: dict[str, Any], data: dict[str, Any], a: dict[str, Any]) -> str:
    pref = str(a.get("prefecture") or "")
    muni = str(a.get("municipality") or "")
    src = safe_url(a.get("source_url"))
    rows = []
    for key, label in FIELDS:
        v = a.get(key)
        if v is None or str(v).strip() == "":
            continue
        rows.append(f"<div><dt>{esc(label)}</dt><dd>{esc(v)}</dd></div>")
    phone = str(a.get("phone") or "").strip()
    addr = str(a.get("address") or "").strip()
    contact = [f"<div><dt>自治体</dt><dd>{esc(muni)}</dd></div>"]
    if phone:
        href = tel_href(phone)
        contact.append(f'<div><dt>電話</dt><dd><a href="{esc(href)}">{esc(phone)}</a></dd></div>' if href
                       else f"<div><dt>電話</dt><dd>{esc(phone)}</dd></div>")
    if addr:
        contact.append(f"<div><dt>所在地</dt><dd>{esc(addr)}</dd></div>")
    if not phone:
        contact.append("<div><dt>連絡先</dt><dd>電話番号は自治体のページでご確認ください。</dd></div>")
    cta = (f'<a class="cta" href="{esc(src)}" rel="noopener" target="_blank">自治体のページで詳細を見る<small>{esc(muni)}</small></a>'
           if src else f'<p class="cta cta-none">元ページの URL が取れていません。{esc(muni)}にお問い合わせください。</p>')
    aff = cfg.get("affiliate") or []
    aff_items = []
    for it in aff:
        if not isinstance(it, dict):
            continue
        u, t = safe_url(it.get("url")), str(it.get("title") or "").strip()
        if not u or not t:
            continue
        note = f'<small>{esc(it.get("note"))}</small>' if it.get("note") else ""
        aff_items.append(f'<li><a href="{esc(u)}" rel="sponsored noopener" target="_blank">{esc(t)}</a>{note}</li>')
    aff_html = (f'<aside class="prep"><h2>迎える準備</h2><p>迎えると決めたら、最初の数日に要るものをまとめました（広告リンクを含みます。運営費に充てています）。</p><ul>{"".join(aff_items)}</ul></aside>'
                if aff_items else "")
    desc = f"{muni}が{fmt_date(data.get('date'))}時点で公開している{kind_label(a)}の{species_label(a)}。"
    if subline(a):
        desc += subline(a) + "。"
    if a.get("note"):
        desc += shorten(a["note"], 80)
    body = f"""<nav class="crumbs"><a href="/">都道府県</a> › <a href="{esc(pref_path(pref))}">{esc(pref)}</a> › <span>{esc(headline(a))}</span></nav>
<article class="detail" data-id="{esc(a['id'])}">
{media(a, big=True)}
<div class="detail-body">
<div class="badges">{badges(a)}</div>
<h1>{esc(headline(a))}</h1>
<p class="muni">{esc(muni) if muni == pref else f"{esc(muni)}（{esc(pref)}）"}</p>
<p class="kind-help">{esc(KIND_HELP.get(str(a.get('kind')), ''))}</p>
{cta}
<h2>取れている情報</h2>
<dl class="facts">
{chr(10).join(rows) if rows else '<div><dd>写真以外の項目は取れていません。自治体のページをご覧ください。</dd></div>'}
</dl>
<h2>連絡先</h2>
<dl class="facts">
{chr(10).join(contact)}
</dl>
<p class="fine">この情報は {esc(fmt_date(data.get('date')))} に自治体のページから取得したものです。すでに譲渡・返還されている場合があります。ID: <code>{esc(a['id'])}</code></p>
</div>
</article>
{aff_html}"""
    return page(cfg, title=f"{headline(a)}（{muni}）", path=animal_path(a["id"]), body=body, og_type="article",
                og_image=safe_url(a.get("image_url")), data_date=str(data.get("date") or ""), desc=shorten(desc, 160))


def build_sources(cfg: dict[str, Any], data: dict[str, Any]) -> str:
    sources = [s for s in data.get("sources", []) if isinstance(s, dict)]
    by_pref: dict[str, list[dict[str, Any]]] = {}
    for s in sources:
        by_pref.setdefault(str(s.get("prefecture") or "不明"), []).append(s)
    st = Counter(str(s.get("status") or "") for s in sources)
    sections = []
    for p in sorted(by_pref, key=pref_key):
        items = []
        for s in by_pref[p]:
            status = str(s.get("status") or "")
            url = safe_url(s.get("url"))
            link = f'<a href="{esc(url)}" rel="noopener" target="_blank">自治体のページ</a>' if url else ""
            kind = KINDS.get(str(s.get("kind")), "")
            sp = SPECIES.get(str(s.get("species")), "犬・猫")
            if status == "ok":
                res = f'<b>{int(s.get("count") or 0)} 頭</b>'
            elif status == "link_only":
                res = "このページは一覧を読み取らず、リンクだけ載せています"
            else:
                res = esc(STATUS.get(status, status))
            items.append(
                f'<li class="src st-{esc(status)}"><span class="src-name">{esc(s.get("name"))}</span>'
                f'<span class="src-meta">{esc(s.get("municipality"))} ・ {esc(kind)} ・ {esc(sp)}</span>'
                f'<span class="src-status">{res}</span><span class="src-link">{link}</span></li>')
        sections.append(f'<h2 id="{esc(p)}">{esc(p)}</h2><ul class="src-list">{"".join(items)}</ul>')
    summary = f"確認済み {st['ok']} 件、本日 0 頭 {st['empty']} 件、確認できず {st['failed']} 件、リンクのみ {st['link_only']} 件"
    if st["disabled"]:
        summary += f"、停止中 {st['disabled']} 件"
    body = f"""<h1>情報源（自治体ページ）の一覧</h1>
<p>{esc(fmt_date(data.get('date')))} に確認した自治体ページ {len(sources)} 件の状況です（{summary}）。「本日は確認できませんでした」のページは、自治体側の更新やページ構造の変化で読み取れなかったものです。リンク先で直接ご確認ください。</p>
{chr(10).join(sections) if sections else '<p class="empty">情報源がありません。</p>'}"""
    return page(cfg, title="情報源の一覧", path="/sources/", body=body, data_date=str(data.get("date") or ""),
                desc="oneco が毎日確認している自治体の保護犬・保護猫ページの一覧と、本日の確認状況。")


def build_about(cfg: dict[str, Any], data: dict[str, Any]) -> str:
    issues = safe_url(cfg.get("issues_url")) or safe_url(DEFAULT_CFG["issues_url"])
    site = esc(cfg["site_name"])
    body = f"""<h1>このサイトについて</h1>
<section>
<h2>運営方針</h2>
<p>{site} は、全国の自治体（動物愛護センター・保健所・市区町村）が公開している保護犬・保護猫の情報を、出典を明示して 1 か所に集めたサイトです。個人や団体の掲載情報は扱いません。</p>
<ul>
<li>掲載するのは自治体の公開ページに載っている情報だけです。写真・項目は元ページのまま、電話番号と所在地は自治体の公式情報から転記しています。</li>
<li>毎日、各自治体のページを確認して当日の情報だけを載せます。個体を追跡したり、過去の情報を残したりはしません。</li>
<li>すべての子に「自治体のページで詳細を見る」リンクを付けています。譲渡の申し込みや迷子の問い合わせは、必ず自治体に直接行ってください。{site} は仲介をしません。</li>
<li>読み取りに失敗した自治体は<a href="/sources/">情報源の一覧</a>に「本日は確認できませんでした」と表示し、元ページへのリンクを残します。</li>
</ul>
</section>
<section>
<h2>掲載の取り下げ・訂正の依頼</h2>
<p>自治体のご担当者様で、掲載の取り下げ・訂正・リンク方法の変更をご希望の場合は、下記の窓口（GitHub Issues）にページの URL とご要望をお書きください。確認のうえ速やかに対応します。GitHub アカウントをお持ちでない場合も、同じページに記載の方法でご連絡いただけます。</p>
<p><a class="cta" href="{esc(issues)}" rel="noopener" target="_blank">撤去・訂正依頼の窓口（GitHub Issues）</a></p>
</section>
<section>
<h2>運営費について</h2>
<p>サーバー代などの運営費は、各ページの「迎える準備」枠に載せている広告（アフィリエイト）リンクでまかなっています。自治体や譲渡そのものにお金は関わりません。譲渡の条件や費用は各自治体の定めによります。</p>
</section>
<section>
<h2>免責</h2>
<p>掲載内容は取得時点の自治体ページに基づきます。すでに譲渡・返還されている場合や、元ページの更新が反映されていない場合があります。最終的な情報は必ず各自治体にご確認ください。</p>
</section>"""
    return page(cfg, title="このサイトについて", path="/about/", body=body, data_date=str(data.get("date") or ""),
                desc=f"{cfg['site_name']} の運営方針、掲載の取り下げ・訂正の窓口、運営費について。")


def build_404(cfg: dict[str, Any]) -> str:
    body = """<h1>ページが見つかりません</h1>
<p>この子の掲載は終了したか、URL が間違っています。掲載は当日の自治体ページに基づくため、譲渡・返還された子のページは翌日には無くなります。</p>
<p><a class="cta" href="/">都道府県の一覧へ戻る</a></p>"""
    return page(cfg, title="ページが見つかりません", path="/404.html", body=body, desc="ページが見つかりません。")


def build_sitemap(cfg: dict[str, Any], data: dict[str, Any], prefs: list[str], animals: list[dict[str, Any]]) -> str:
    base = cfg["base_url"].rstrip("/")
    lastmod = iso_date(data.get("date"))
    paths = ["/", "/sources/", "/about/"] + [pref_path(p) for p in prefs] + [animal_path(a["id"]) for a in animals]
    urls = "\n".join(f"<url><loc>{esc(base + p)}</loc><lastmod>{lastmod}</lastmod></url>" for p in paths)
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{urls}\n</urlset>\n'


def build_robots(cfg: dict[str, Any]) -> str:
    return f"User-agent: *\nAllow: /\nSitemap: {cfg['base_url'].rstrip('/')}/sitemap.xml\n"


# ---------------------------------------------------------------- CSS

CSS = """
:root{--bg:#f6f7f9;--card:#fff;--ink:#1c2430;--mute:#5b6775;--line:#dfe4ea;--accent:#1f3a5f;--accent-ink:#fff;--dog:#e8f0fa;--cat:#fbeee6;--adopt:#e3f4e8;--shelter:#fff4d6;--stray:#f3e8f7;--ph:#b3c0cc}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"Helvetica Neue","Hiragino Sans","Hiragino Kaku Gothic ProN","Noto Sans JP","Yu Gothic",Meiryo,sans-serif;line-height:1.6;font-size:16px}
a{color:var(--accent)}
img{max-width:100%;display:block}
h1{font-size:1.4rem;margin:.2em 0 .5em;line-height:1.35}
h2{font-size:1.1rem;margin:1.6em 0 .5em}
h3{font-size:1rem;margin:0}
p{margin:.4em 0}
code{font-size:.85em;background:#eef1f4;padding:.1em .3em;border-radius:4px}
.wrap{max-width:1040px;margin:0 auto;padding:16px}
.site-head{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 16px;background:var(--accent);color:var(--accent-ink)}
.brand{color:#fff;text-decoration:none;font-weight:700;font-size:1.25rem;letter-spacing:.02em}
.nav{display:flex;gap:14px;flex-wrap:wrap;font-size:.9rem}
.nav a{color:#fff;text-decoration:none;opacity:.92}
.nav a:hover{text-decoration:underline}
@media (max-width:520px){.site-head{flex-wrap:wrap;padding:10px 16px}.nav{flex:1 1 100%;gap:16px}}
.site-foot{max-width:1040px;margin:32px auto 0;padding:16px;color:var(--mute);font-size:.85rem;border-top:1px solid var(--line)}
.crumbs{font-size:.85rem;color:var(--mute);margin-bottom:8px;overflow-wrap:anywhere}
.intro p{max-width:70ch}
.stats{color:var(--mute);font-size:.95rem}
.hint,.fine{color:var(--mute);font-size:.85rem}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin:8px 0}
.chips button{appearance:none;border:1px solid var(--line);background:#fff;color:var(--ink);border-radius:999px;padding:6px 14px;font-size:.9rem;cursor:pointer;min-height:36px}
.chips button[aria-pressed="true"]{background:var(--accent);color:#fff;border-color:var(--accent)}
.filters{display:flex;flex-direction:column;gap:2px}
.count{margin:8px 0;color:var(--mute)}
.pref-list{list-style:none;padding:0;margin:8px 0;display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px}
.pref-list li a{display:flex;justify-content:space-between;align-items:baseline;gap:8px;background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px;text-decoration:none;color:var(--ink);min-height:48px}
.pref-list li a:hover{border-color:var(--accent)}
.pref-list .pref{font-weight:600}
.pref-list .cnt{color:var(--mute);font-size:.9rem;white-space:nowrap}
.pref-list .cnt b{color:var(--accent);font-size:1.1rem}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:12px}
@media (min-width:480px){.grid{grid-template-columns:repeat(auto-fill,minmax(200px,1fr))}}
.card{display:flex;flex-direction:column;background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden;text-decoration:none;color:var(--ink)}
.card:hover{border-color:var(--accent);box-shadow:0 2px 8px rgba(0,0,0,.06)}
.card-body{padding:10px 12px 12px;display:flex;flex-direction:column;gap:4px}
.card h3{font-size:.98rem;line-height:1.35}
.card .sub{font-size:.85rem;color:var(--mute);margin:0;overflow-wrap:anywhere}
.card .muni{font-size:.8rem;color:var(--mute);margin:0}
.badges{display:flex;gap:6px;flex-wrap:wrap}
.badge{display:inline-block;font-size:.75rem;padding:2px 8px;border-radius:999px;background:#eef1f4;color:var(--ink);line-height:1.5}
.badge.sp-dog{background:var(--dog)}.badge.sp-cat{background:var(--cat)}
.badge.kd-adoption{background:var(--adopt)}.badge.kd-sheltered{background:var(--shelter)}.badge.kd-stray{background:var(--stray)}
.media{position:relative;aspect-ratio:4/3;background:#e9edf1;overflow:hidden;container-type:inline-size}
.media img{width:100%;height:100%;object-fit:cover}
.media img+.ph{display:none}
.media.noimg .ph{display:flex}
.ph{position:absolute;inset:0;display:flex;align-items:flex-end;justify-content:center;padding-bottom:6%;background:linear-gradient(160deg,#e8edf2,#d3dbe3);color:#6b7a88;font-size:clamp(9px,7cqw,30px)}
.ph span{font-size:max(11px,.5em);letter-spacing:.05em}
.ph::before{content:"";position:absolute;left:50%;top:50%;width:2.8em;height:2.4em;margin:-.7em 0 0 -1.4em;background:var(--ph);border-radius:50%/55% 55% 45% 45%}
.ph::after{content:"";position:absolute;left:50%;top:50%;width:5em;height:2.2em;margin:-2.5em 0 0 -2.5em;background:radial-gradient(circle at .6em 1.6em,var(--ph) .55em,transparent .6em),radial-gradient(circle at 1.9em .6em,var(--ph) .6em,transparent .65em),radial-gradient(circle at 3.1em .6em,var(--ph) .6em,transparent .65em),radial-gradient(circle at 4.4em 1.6em,var(--ph) .55em,transparent .6em)}
.detail{display:grid;gap:16px;background:var(--card);border:1px solid var(--line);border-radius:14px;overflow:hidden}
@media (min-width:720px){.detail{grid-template-columns:minmax(0,5fr) minmax(0,6fr)}.detail .media{aspect-ratio:auto;min-height:320px;height:100%}}
.detail .media{border-radius:0}
.detail-body{padding:4px 16px 16px}
@media (min-width:720px){.detail-body{padding:20px 20px 20px 4px}}
.detail h1{font-size:1.45rem}
.detail .muni{color:var(--mute);margin:0}
.kind-help{color:var(--mute);font-size:.9rem}
.facts{margin:0;display:grid;gap:6px}
.facts>div{display:grid;grid-template-columns:7.5em 1fr;gap:8px;padding:6px 0;border-bottom:1px solid var(--line)}
.facts dt{color:var(--mute);font-size:.9rem}
.facts dd{margin:0;overflow-wrap:anywhere;white-space:pre-line}
.cta{display:block;background:var(--accent);color:#fff;text-decoration:none;text-align:center;font-weight:700;font-size:1.05rem;padding:14px 16px;border-radius:12px;margin:14px 0}
.cta small{display:block;font-weight:400;font-size:.8rem;opacity:.85;margin-top:2px}
.cta:hover{filter:brightness(1.1)}
.cta-none{background:#eef1f4;color:var(--ink);font-weight:400;font-size:.95rem}
.prep{margin-top:20px;background:#fffaf0;border:1px solid #f0e2c2;border-radius:14px;padding:12px 16px}
.prep h2{margin-top:.2em}
.prep ul{padding-left:1.2em;margin:.4em 0}
.prep li{margin:.3em 0}
.prep small{display:block;color:var(--mute)}
.src-list{list-style:none;padding:0;margin:0 0 8px;display:grid;gap:8px}
.src{display:grid;gap:2px;background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 12px}
@media (min-width:720px){.src{grid-template-columns:2fr 1.5fr 1.2fr auto;align-items:center;gap:12px}}
.src-name{font-weight:600}
.src-meta{color:var(--mute);font-size:.85rem}
.src-status{font-size:.9rem}
.src.st-failed .src-status{color:#a33}
.src.st-ok .src-status b{color:var(--accent)}
.src-link{font-size:.9rem}
.empty{color:var(--mute)}
[hidden]{display:none!important}
"""


# ---------------------------------------------------------------- driver

def load_config(path: Path | None) -> dict[str, Any]:
    cfg = dict(DEFAULT_CFG)
    if path and path.exists():
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            cfg.update(raw)
    if not safe_url(cfg.get("base_url")):
        sys.exit(f"config の base_url が http(s) で始まっていない: {cfg.get('base_url')!r}")
    return cfg


def prepare_out(out: Path) -> None:
    """出力先を空にする。前回の build 先か空ディレクトリのときだけ消す。"""
    if out.exists():
        if not out.is_dir():
            sys.exit(f"出力先がディレクトリではない: {out}")
        if any(out.iterdir()) and not (out / MARKER).exists():
            sys.exit(f"出力先 {out} は build が作ったものではないので消さない。空にするか別の --out を指定してください。")
        shutil.rmtree(out)
    out.mkdir(parents=True)


def write(out: Path, rel: str, text: str) -> None:
    p = out / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def build_site(data: dict[str, Any], cfg: dict[str, Any], out: Path, data_path: Path | None = None) -> dict[str, int]:
    """data（animals JSON の中身）から out/ を生成。data_path があれば data.json はそのファイルのコピー。"""
    cfg = {**DEFAULT_CFG, **cfg}
    prepare_out(out)
    raw_animals = [a for a in data.get("animals", []) if isinstance(a, dict)]
    seen: set[str] = set()
    animals: list[dict[str, Any]] = []
    skipped = 0
    for a in raw_animals:
        aid = str(a.get("id") or "")
        if not ID_RE.fullmatch(aid) or aid in seen or not a.get("prefecture"):
            skipped += 1
            continue
        seen.add(aid)
        animals.append(a)
    animals.sort(key=lambda a: KIND_ORDER.get(str(a.get("kind")), 9))   # stable: 譲渡対象→収容中→迷子。元の順は保つ

    by_pref: dict[str, list[dict[str, Any]]] = {}
    for a in animals:
        by_pref.setdefault(str(a["prefecture"]), []).append(a)
    prefs = sorted(by_pref, key=pref_key)

    write(out, "index.html", build_index(cfg, data, animals))
    for p in prefs:
        write(out, f"pref/{p}/index.html", build_pref(cfg, data, p, by_pref[p]))
    for a in animals:
        write(out, f"animals/{a['id']}/index.html", build_animal(cfg, data, a))
    write(out, "sources/index.html", build_sources(cfg, data))
    write(out, "about/index.html", build_about(cfg, data))
    write(out, "404.html", build_404(cfg))
    write(out, "sitemap.xml", build_sitemap(cfg, data, prefs, animals))
    write(out, "robots.txt", build_robots(cfg))
    write(out, "style.css", CSS.strip() + "\n")
    if data_path is not None:
        shutil.copyfile(data_path, out / "data.json")
    else:
        write(out, "data.json", json.dumps(data, ensure_ascii=False, indent=1))
    write(out, MARKER, f"{datetime.now().isoformat(timespec='seconds')} {data.get('date', '')}\n")
    return {"animals": len(animals), "prefectures": len(prefs), "sources": len(data.get("sources", [])), "skipped": skipped}


def build(data_path: Path, out: Path, cfg: dict[str, Any] | Path | None = None) -> dict[str, int]:
    """ファイルから読んで build_site。cfg は dict か config.json のパス（None なら既定）。"""
    if not isinstance(cfg, dict):
        cfg = load_config(cfg if isinstance(cfg, Path) else DEFAULT_CONFIG)
    try:
        data = json.loads(data_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        sys.exit(f"データが無い: {data_path}（先に `python -m collector run` を実行）")
    if not isinstance(data, dict) or not isinstance(data.get("animals"), list):
        sys.exit(f"データ形式が違う（animals 配列が無い）: {data_path}")
    return build_site(data, cfg, out, data_path=data_path)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="oneco v2 静的サイト生成: data/latest.json → site/dist/")
    ap.add_argument("--data", type=Path, default=DEFAULT_DATA, help="animals JSON（既定: data/latest.json）")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="出力先（既定: site/dist）")
    ap.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="設定（既定: site/config.json）")
    args = ap.parse_args(argv)
    n = build(args.data, args.out, args.config)
    print(f"{args.out}: {n['animals']} 頭・{n['prefectures']} 都道府県・情報源 {n['sources']} 件"
          + (f"（id 不正・重複で {n['skipped']} 件を除外）" if n["skipped"] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
