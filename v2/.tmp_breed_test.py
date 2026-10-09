import os
import re

from bs4 import BeautifulSoup

pat = re.compile(r"^\S+\s+[○〇]?([^\s(（A-Za-z0-9\-○〇]+)")
for t in ["9/28　雑種(沖縄市)　C-1", "9/25　シェパード(沖縄市)　M-1", "9/18 　プードル系(名護市)　K-1", "9/28　雑種(沖縄市）　M-2", "9/4　O-11", "9/4　雑種　O-11", "9/20　○雑種(那覇市)　K-1", "9/7　ミニチュアダックスフンド(那覇市)　S-1"]:
    m = pat.search(t)
    print(repr(t), "->", m.group(1) if m else None)
p = os.path.join(os.environ["TMPDIR"], "aniwel_dog_detail2.html")
soup = BeautifulSoup(open(p, encoding="utf-8").read(), "lxml")
row = soup.select_one("div.animals_single")
el = row.select_one("div.title p")
print("div.title p ->", repr(el.get_text(" ", strip=True)) if el else None)
for cand in ["div.title", "div.list", ".page_title"]:
    e = row.select_one(cand)
    print(cand, "->", repr(e.get_text(" ", strip=True)[:80]) if e else None)
