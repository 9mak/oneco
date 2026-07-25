"""0件検知の再検証 (段階的: rule-based → LLM 分類)

SiteBaselineTracker.detect_zero_count_regressions() は「過去≥1件のサイトが
threshold 回連続0件」を検知するが、baseline 1〜2件の薄いサイトは在庫の
自然な増減で 2 回連続 0 件になりやすく、誤検知が多い(2026-07-24 実データ:
検知15件中14件が baseline 1〜2件)。

一方で threshold を単純に引き上げる(様子見期間を延ばす)と、逆に「本サイト
には掲載されているのに oneco 側の収集が壊れて 0 件になっている」見逃しを
長引かせてしまう。

そこで threshold を弄る代わりに、baseline の大小に関係なく検知の都度、
段階的な再確認を挟む:
1. adapter でもう一度 fetch_animal_list() する (一時的なネットワーク/在庫の
   揺らぎを除外)
2. それでも 0 件なら、list ページの実 HTML にサイト側の明示的な「該当なし」
   メッセージがあるか確認する (あれば「本サイト側も0件」で正常と確定)
3. パターンで判定できない残りだけ、LLM 分類 (Groq/llama、既存 GROQ_API_KEY
   流用) に「ページに動物が掲載されているか」を LISTED/NONE/UNCLEAR の
   1 語で答えさせる。文言パターンの表現バリエーション (「いません」型・
   空テンプレート型等) を追いかけるいたちごっこを避けるため、表層の文言
   ではなく掲載有無そのものを判定する (2026-07-25 手動トリアージ: 検知
   8件中7件がパターン網羅漏れによる誤検知だったことから導入)。
   - LISTED: adapter は 0 件なのに実ページに動物がいる → 破損濃厚
   - NONE: ページ上も 0 件表示 → 正常
   - UNCLEAR (JS 必須・判定不能・API キー未設定・例外): 安全側で候補に残す

  この LLM 呼び出しは読み取り専用の分類であり、コード・収集データを
  一切変更しない (auto-fix の LLM 修復停止判断 [project_self_healing] とは
  役割が異なる)。呼び出しは step 1-2 で判定できなかった残りのみ
  (実測 3 件/日程度) で、Groq 無料枠に収まる。

判定に必要な情報が取れない(例外)場合は安全側に倒して True にする。
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from typing import Protocol

from bs4 import BeautifulSoup

_GROQ_BASE_URL = "https://api.groq.com/openai/v1"
_JUDGE_MODEL = "llama-3.3-70b-versatile"
# 分類プロンプトに含める HTML の上限 (Groq 無料枠 TPM 12000 に収める)。
# 動物一覧 or 0件メッセージは本文冒頭〜中盤に現れることが多く、分類目的
# なら全文は不要。
_JUDGE_MAX_HTML_CHARS = 8000
# 本文テキストがこれ未満なら LLM を呼ばず "unclear" とする。JS レンダリング
# 必須ページや、adapter が list_url とは別の内部ページ群から収集する構成
# (実測: 高知県は list_url の静的本文が 26 字しかなく、動物は別ページに
# 掲載) では、静的 HTML の本文だけで「0件だ」と誤断定する危険があるため。
_JUDGE_MIN_TEXT_CHARS = 200

_WHITESPACE_RE = re.compile(r"\s+")
# 本文テキスト抽出時に除去するタグ。head/script/style は当然として、
# header/nav/footer (巨大ナビメニュー: 実測で高知県は 40000 字超) も
# 動物掲載情報を持たないので落とす。regex ベースの除去は入れ子・閉じタグ
# 不整合で本文まで飲み込む事故があった (実測: 高知県で本文 24000 字が
# 消えて 901 字になった) ため、BeautifulSoup の DOM 処理で行う。
_STRIP_TAGS = ["script", "style", "noscript", "head", "meta", "link", "header", "nav", "footer"]

_ZERO_MESSAGE_PATTERNS = [
    # 「現在/只今/ただいま + (説明) + ありません/いません」
    # (2026-07-25 実サイト調査: 「対象となる犬はいません」等「いません」型が
    # 「ありません」型と同程度に多く、旧パターンは「ありません」のみだった)
    re.compile(r"(現在|只今|ただいま)[、,]?.{0,25}(ありません|いません)"),
    re.compile(r"該当する.{0,15}(情報|動物)?.{0,3}ありません"),
    re.compile(r"対象.{0,10}(動物|犬|猫).{0,5}いません"),
    re.compile(r"収容.{0,15}(動物|情報|犬|猫)?.{0,5}(ありません|いません)"),
]


class _ListFetchableAdapter(Protocol):
    def fetch_animal_list(self) -> list[tuple[str, str]]: ...

    def _http_get(self, url: str) -> str: ...


@dataclass
class ZeroCountVerification:
    """0件再検証の結果。

    should_flag=True: 壊れている疑いが濃厚。修理候補として残すべき。
    should_flag=False: 正常(在庫の一時的な揺らぎ、またはサイト側の明示的な0件)。
    """

    should_flag: bool
    reason: str


def _has_explicit_zero_message(html: str) -> bool:
    return any(pattern.search(html) for pattern in _ZERO_MESSAGE_PATTERNS)


def _compress_for_judge(html: str) -> str:
    """LLM 分類用にページ本文テキストを抽出する。

    「動物が掲載されているか」の判定にタグ構造は不要でテキストで足りる。
    BeautifulSoup で head/script/style/header/nav/footer を除去した上で
    本文テキストだけを渡すことで:
    - ヘッダー/ナビが長いサイトで動物データが切り詰め圏外に落ちるのを防ぐ
      (実測: 広島県はヘッダーだけで 10000 字超、高知県は nav が 40000 字超)
    - タグノイズが消えて同じ文字数枠に入る情報量が増える
    """
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(_STRIP_TAGS):
        tag.decompose()
    body = soup.body or soup
    text = _WHITESPACE_RE.sub(" ", body.get_text(separator=" ")).strip()
    return text[:_JUDGE_MAX_HTML_CHARS]


def _llm_judge_page_animals(html: str) -> str:
    """ページに動物が掲載されているかを LLM に分類させる。

    Returns:
        "listed": 個別の動物情報が 1 件以上掲載されている
        "none": ページ上も 0 件表示 (明示メッセージ or 空テンプレート)
        "unclear": 判定不能 (JS 必須・API キー未設定・呼び出し失敗含む)

    分類は読み取り専用でコード・データを変更しない。失敗はすべて
    "unclear" に丸め、呼び出し側が安全側 (修理候補に残す) に倒す。
    """
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return "unclear"
    compressed = _compress_for_judge(html)
    if len(compressed) < _JUDGE_MIN_TEXT_CHARS:
        # 本文がほぼ無い = 静的 HTML だけでは判定材料不足。安全側に倒す
        return "unclear"
    try:
        from openai import OpenAI  # 遅延 import (テストで mock しやすくするため)

        client = OpenAI(api_key=api_key, base_url=_GROQ_BASE_URL)
        response = client.chat.completions.create(
            model=_JUDGE_MODEL,
            max_tokens=10,
            temperature=0,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "あなたは自治体・保護団体の動物情報ページの本文テキストを読み、"
                        "動物の掲載状況を分類する分類器です。"
                        "LISTED / NONE / UNCLEAR のいずれか 1 語だけで答えてください。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "以下は保護動物情報ページの本文テキストです。現在、個別の動物"
                        "の掲載が 1 件以上ありますか？\n\n"
                        "- 個別の動物情報 (収容日・管理番号・品種等の値が実際に記入"
                        "されたエントリ)、または個別の動物詳細ページへのリンク一覧"
                        "(保護日+場所+名前 等) が 1 件以上ある → LISTED\n"
                        "- 「いません/ありません」等の明示がある、または"
                        "「収容日：」のようにラベルだけで値が空欄のテンプレートのみで"
                        "動物の掲載が無い → NONE\n"
                        "- 本文からは判断できない (本文がほぼ無い等) → UNCLEAR\n\n"
                        f"---\n{compressed}\n---\n\n回答(1語):"
                    ),
                },
            ],
        )
        text = (response.choices[0].message.content or "").upper()
    except Exception as e:
        print(f"zero_count_verifier: LLM 分類呼び出し失敗 ({e})", file=sys.stderr)
        return "unclear"
    # NONE は「正常」側に倒す唯一の判定なので最後に照合する (曖昧応答は
    # UNCLEAR/LISTED を優先し、安全側 = 修理候補に残す方向へ丸める)
    if "UNCLEAR" in text:
        return "unclear"
    if "LISTED" in text:
        return "listed"
    if "NONE" in text:
        return "none"
    return "unclear"


def verify_zero_count(adapter: _ListFetchableAdapter, list_url: str) -> ZeroCountVerification:
    """0件検知後に呼ぶ軽量再検証。LLM は使わない。"""
    try:
        urls = adapter.fetch_animal_list()
    except Exception as e:
        return ZeroCountVerification(
            should_flag=True, reason=f"再取得で例外が発生 ({type(e).__name__}: {e})"
        )
    if urls:
        return ZeroCountVerification(
            should_flag=False, reason=f"再取得したら{len(urls)}件あった(一時的な揺らぎ)"
        )

    try:
        html = adapter._http_get(list_url)
    except Exception as e:
        return ZeroCountVerification(
            should_flag=True,
            reason=f"0件確定後のHTML再取得で例外が発生 ({type(e).__name__}: {e})",
        )

    if _has_explicit_zero_message(html):
        return ZeroCountVerification(
            should_flag=False, reason="サイト側に明示的な0件メッセージあり"
        )

    # パターンで判定できない残りは LLM 分類にかける。NONE のみ正常扱いし、
    # LISTED (掲載があるのに adapter は 0 件 = 破損濃厚) / UNCLEAR は候補に残す。
    verdict = _llm_judge_page_animals(html)
    if verdict == "none":
        return ZeroCountVerification(
            should_flag=False, reason="LLM分類: ページ上も0件表示 (正常な0件)"
        )
    if verdict == "listed":
        return ZeroCountVerification(
            should_flag=True,
            reason="LLM分類: 実ページには動物の掲載があるのに adapter は0件 (破損濃厚)",
        )

    return ZeroCountVerification(
        should_flag=True, reason="再取得も0件で、0件メッセージも見当たらない"
    )
