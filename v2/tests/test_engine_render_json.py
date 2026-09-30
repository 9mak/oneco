"""render_json step（T509・愛知わんにゃんナビ）: 描画中に捕まえた JSON 応答から値を抜き、URL に差し込んで個体ページを辿る。"""

from collector.extract import build
from collector.fetch import FakeFetcher
from collector.recipe import Executor, Recipe, _json_values
from collector.registry import Source

LIST = "https://wannyan-navi.example.jp/?page=list_dc"
DETAIL = "https://wannyan-navi.example.jp/?page=list_dc_m&no={value}"


def _detail_html(no: str, sex: str, species_word: str) -> str:
    return f"""<html><body><div>掲載日：2026/08/27</div><div>譲渡可能</div>
    <img src="https://cdn.example.jp/cdn-cgi/image/w=1024,h=768,f=auto/f{no}/photo.jpg">
    <div>基本情報</div><div>No . 尾{no}</div><div>尾張支所(一宮市)</div><div>雑種</div><div>白黒</div><div>{sex}</div><div>4.20kg</div><div>10歳5ヵ月</div>
    <div>特徴</div><div>甘えん坊です。</div><div>管理番号　23</div>
    <div>譲渡をご希望の方</div><a href="#">{species_word}の飼い方講習会へ</a></body></html>"""


def test_json_values_path():
    obj = {"hits": {"total": 2, "hits": [{"_id": "a", "x": 1}, {"_id": "b"}]}}
    assert _json_values(obj, "hits.hits[]._id") == ["a", "b"]
    assert _json_values([obj, obj], "hits.total") == [2, 2]     # 捕まえた応答が複数でも平らに
    assert _json_values(obj, "nope.x") == []


def test_render_json_follows_ids_from_captured_response():
    fetcher = FakeFetcher({
        LIST: "<html><body>一覧（描画後も href 無し）</body></html>",
        DETAIL.replace("{value}", "1001"): _detail_html("1001", "オス", "猫"),
        DETAIL.replace("{value}", "1002"): _detail_html("1002", "メス", "犬"),
    }, captures={LIST: [{"hits": {"hits": [{"_id": "1001"}, {"_id": "1002"}, {"_id": "1001"}]}}]})
    recipe = Recipe.from_dict({
        "steps": [{"render_json": {"match": "elasticsearch/search", "path": "hits.hits[]._id", "follow": DETAIL}}],
        "rows": "body",
        "image": {"selector": "img[src*='w=1024']@src"},
        "fields": {"management_no": {"regex": "No\\s*\\.\\s*(\\S+)"}, "sex": {"regex": "(オス|メス)"},
                   "note": {"regex": "特徴\\s+(.*?)\\s+管理番号"}},
        "species": {"from": "text", "map": {"犬の飼い方講習会へ": "dog", "猫の飼い方講習会へ": "cat"}},
    })
    ex = Executor(fetcher, recipe)
    docs = ex.resolve(LIST)
    assert [d.url for d in docs] == [DETAIL.replace("{value}", "1001"), DETAIL.replace("{value}", "1002")]   # 重複 id は 1 回
    assert fetcher.render_calls[0] == (LIST, "elasticsearch/search")   # 入口は capture 付きで描画される
    src = Source(slug="aichi", name="愛知", municipality="愛知県動物愛護センター", prefecture="愛知県", url=LIST, kind="adoption", species="mixed")
    res = build(src, recipe, docs)
    assert [(a["management_no"], a["sex"], a["species"]) for a in res.animals] == [("尾1001", "オス", "cat"), ("尾1002", "メス", "dog")]
    assert res.animals[0]["note"] == "甘えん坊です。"
    assert res.animals[0]["image_url"].endswith("/f1001/photo.jpg")
    assert res.animals[0]["source_url"] == DETAIL.replace("{value}", "1001")
