"""短いが中身のある実ページは「取得不能」にしない（W006 T604 の下限チェックの絞り込み）。
2026-10-15 の shadow 試運転で、堺（eonet、449 バイトの入口ページ。動物がいる日の形）と栃木（151 バイト、h1 だけ＝0 頭の日）が
`本文が短すぎる` で 3 日間 failed になっていた。下限は「本文テキストもリンクも無い殻」にだけ効かせる。
"""
import pytest
from collector import fetch as fetch_mod
from collector.fetch import Page, validate_response

URL = "https://city.example.lg.jp/animals/list.html"


def _page(body: str) -> Page:
    raw = body.encode()
    return Page(URL, URL, 200, raw, raw.decode("utf-8", "replace"), "text/html; charset=UTF-8")


SAKAI_MENU = ('<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.0 Transitional//EN">\n<html>\n<head>\n<title></title>\n'
              '<meta name="GENERATOR" content="Microsoft Visual Studio .NET 7.1">\n<meta name=ProgId content=VisualStudio.HTML>\n'
              '<meta name=Originator content="Microsoft Visual Studio .NET 7.1">\n'
              '<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=SHIFT_JIS">\n</head>\n<body>\n'
              "<h1>動物情報</h1>\n<hr>\n<a href='./stray/menu2.html'>迷子情報</a>\n\n</table>\n</body>\n</html>\n")
TOCHIGI_EMPTY = ('﻿<!DOCTYPE html>\n<html lang="ja">\n<head>\n<meta charset="UTF-8">\n<title></title>\n</head>\n<body>\n'
                 "<h1>引取動物収容情報</h1>\n<hr>\n</body>\n</html>\n")


def test_short_menu_page_with_link_passes():
    assert len(SAKAI_MENU.encode()) < fetch_mod.MIN_HTML_BYTES
    assert validate_response(_page(SAKAI_MENU)) is None


def test_short_heading_only_page_passes():
    assert len(TOCHIGI_EMPTY.encode()) < fetch_mod.MIN_HTML_BYTES
    assert validate_response(_page(TOCHIGI_EMPTY)) is None


@pytest.mark.parametrize("body", [
    "<html><body></body></html>",
    "<html><head><title></title></head><body>\n  \n</body></html>",
    "<html><body><script>var a=1;</script><style>p{}</style><div></div></body></html>",
])
def test_short_page_without_text_or_links_is_unavailable(body):
    info = validate_response(_page(body))
    assert info is not None and info.kind == "content"


def test_short_maintenance_page_is_still_flagged():
    info = validate_response(_page("<html><head><title>メンテナンス中</title></head><body><p>しばらくお待ちください</p></body></html>"))
    assert info is not None and info.kind == "content"
