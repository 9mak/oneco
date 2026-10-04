"""T514: steps の render が辞書なら wait_for / wait_ms を fetcher.render に渡す（高松市: 一覧を jQuery が後から組み立てる）。"""
from collector.fetch import FakeFetcher
from collector.recipe import Executor, Recipe

LIST = "https://example.jp/list"
HTML = """<html><body><div id="pagetitle"><h2>【犬】「保護しています」一覧</h2></div>
<table class="centar-table"><tr class="ttr"><th>保護日</th></tr>
<tr><td class="td1">2026/10/01</td><td class="td2">R8-10</td><td class="td3"><img src="/img/1.jpg"></td></tr></table></body></html>"""


def test_render_dict_passes_wait_for() -> None:
    recipe = Recipe.from_dict({
        "steps": [{"render": {"wait_for": "table.centar-table tr:not(.ttr)", "wait_ms": 500}}],
        "rows": "table.centar-table tr:not(.ttr)",
        "fields": {"management_no": {"selector": "td.td2"}},
    })
    fetcher = FakeFetcher({LIST: HTML})
    docs = Executor(fetcher, recipe).resolve(LIST)
    assert fetcher.render_calls == [(LIST, None, "table.centar-table tr:not(.ttr)")]
    assert docs[0].rendered and len(docs[0].soup.select("table.centar-table tr:not(.ttr)")) == 1


def test_render_true_keeps_old_signature() -> None:
    recipe = Recipe.from_dict({"steps": [{"render": True}], "rows": "tr"})
    fetcher = FakeFetcher({LIST: HTML})
    Executor(fetcher, recipe).resolve(LIST)
    assert fetcher.render_calls == [(LIST, None)]
