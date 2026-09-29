"""一時解析スクリプト（作業後に削除）: 空表示の文言候補と他の一覧 URL、robots.txt。"""
import os
import re
import sys

from bs4 import BeautifulSoup

for f in ["zi_dog.html", "zi_cat.html"]:
    html = open(os.environ["TMPDIR"] + "/" + f, encoding="utf-8").read()
    soup = BeautifulSoup(html, "lxml")
    hrefs = sorted({a.get("href") for a in soup.select("a[href*='/omukae/']") if a.get("href")})
    print(f, [h for h in hrefs if not re.search(r"/omukae/\d+/$", h)])
    for tag in soup.find_all(string=re.compile(r"(見つかりません|ありません|いません|準備中|0件|該当)")):
        print("  HIDDEN?", repr(tag.strip()[:80]), tag.parent.name, tag.parent.get("class"))

if "--robots" in sys.argv:
    import httpx
    ua = "oneco-collector/2.0 (+https://github.com/9mak/oneco; stop/removal requests via GitHub Issues)"
    r = httpx.get("https://zuttoissho.com/robots.txt", headers={"User-Agent": ua}, timeout=30, follow_redirects=True)
    print("robots HTTP", r.status_code)
    print(r.text[:800])
