"""HtmlPreprocessor のユニットテスト"""

import pytest

from src.data_collector.llm.html_preprocessor import HtmlPreprocessor


class TestPreprocess:
    def test_removes_script_tags(self):
        html = '<html><body><script>alert("hi")</script><p>Hello</p></body></html>'
        result = HtmlPreprocessor.preprocess(html, "https://example.com")
        assert "<script>" not in result
        assert "alert" not in result
        assert "Hello" in result

    def test_removes_style_tags(self):
        html = "<html><body><style>.x{color:red}</style><p>Content</p></body></html>"
        result = HtmlPreprocessor.preprocess(html, "https://example.com")
        assert "<style>" not in result
        assert "color:red" not in result
        assert "Content" in result

    def test_removes_nav_footer_header(self):
        html = """<html><body>
        <header>Header</header>
        <nav>Nav</nav>
        <main><p>Main Content</p></main>
        <footer>Footer</footer>
        </body></html>"""
        result = HtmlPreprocessor.preprocess(html, "https://example.com")
        assert "<header>" not in result
        assert "<nav>" not in result
        assert "<footer>" not in result
        assert "Main Content" in result

    def test_removes_iframe_noscript_svg_meta_link(self):
        html = """<html><head><meta charset="utf-8"><link rel="stylesheet" href="x.css"></head>
        <body><iframe src="x"></iframe><noscript>No JS</noscript>
        <svg><circle/></svg><p>Real</p></body></html>"""
        result = HtmlPreprocessor.preprocess(html, "https://example.com")
        assert "<iframe" not in result
        assert "<noscript>" not in result
        assert "<svg>" not in result
        assert "<meta" not in result
        assert "<link" not in result
        assert "Real" in result

    def test_preserves_img_tags(self):
        html = '<html><body><img src="photo.jpg" alt="dog"><p>Text</p></body></html>'
        result = HtmlPreprocessor.preprocess(html, "https://example.com")
        assert "<img" in result
        assert "photo.jpg" in result

    def test_converts_relative_img_urls(self):
        html = '<html><body><img src="/images/dog.jpg"></body></html>'
        result = HtmlPreprocessor.preprocess(
            html, "https://example.com/page/"
        )
        assert "https://example.com/images/dog.jpg" in result

    def test_converts_relative_link_urls(self):
        html = '<html><body><a href="detail/123">Link</a></body></html>'
        result = HtmlPreprocessor.preprocess(
            html, "https://example.com/list/"
        )
        assert "https://example.com/list/detail/123" in result

    def test_normalizes_whitespace(self):
        html = "<html><body><p>  a   b   c  </p>\n\n\n\n\n<p>d</p></body></html>"
        result = HtmlPreprocessor.preprocess(html, "https://example.com")
        assert "\n\n\n" not in result
        assert "  " not in result

    def test_handles_empty_html(self):
        result = HtmlPreprocessor.preprocess("", "https://example.com")
        assert result == ""

    def test_handles_plain_text(self):
        result = HtmlPreprocessor.preprocess(
            "Just plain text", "https://example.com"
        )
        assert "Just plain text" in result


class TestEstimateTokens:
    def test_empty_string(self):
        assert HtmlPreprocessor.estimate_tokens("") == 0

    def test_japanese_text(self):
        text = "これはテストです"  # 8 chars
        tokens = HtmlPreprocessor.estimate_tokens(text)
        assert tokens == 12  # 8 * 1.5

    def test_english_text(self):
        text = "hello world"  # 11 chars
        tokens = HtmlPreprocessor.estimate_tokens(text)
        assert tokens == 16  # int(11 * 1.5)

    def test_returns_int(self):
        result = HtmlPreprocessor.estimate_tokens("test")
        assert isinstance(result, int)
