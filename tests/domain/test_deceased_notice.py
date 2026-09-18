"""deceased_notice のテスト (T424)

自治体ページの「備考」自由文が「その個体が死亡した」と書いているかを判定する。
公開を止める判断に使うため、
- 拾えないと死亡した子を収容中として公開し続ける
- 誤検知すると生きている子を公開から消す (迷子の飼い主が探せなくなる)
の両方が実害になる。実サイトで観測した表記と、紛らわしい表記の両方を検証する。
"""

from __future__ import annotations

import pytest

from data_collector.domain.deceased_notice import deceased_notice


class TestDeceasedNotice:
    @pytest.mark.parametrize(
        "text",
        [
            # 2026-09-18 越谷市（保護猫）の実データ
            "長尾 短毛 首輪なし 令和8年9月13日 死亡確認",
            "死亡確認",
            "令和8年9月13日死亡を確認",
            "収容後に死亡しました",
            "9月15日に死亡した",
            "死体で収容",
            "へい死",
            "斃死が確認された",
            "保護後に亡くなりました",
        ],
    )
    def test_animal_death_is_detected(self, text: str) -> None:
        assert deceased_notice(text) is not None

    @pytest.mark.parametrize(
        "text",
        [
            "",
            "人なつこい 首輪なし",
            # 飼い主・家族の死。動物は生きており譲渡対象
            "飼い主が死亡したため引き取り",
            "飼主死亡により保護",
            "所有者の死亡に伴い譲渡先を探しています",
            "ご家族が亡くなり飼えなくなった子です",
            # 制度・方針の文言
            "本市は殺処分ゼロを目指しています",
            "安楽死は行っていません",
            # 手続き・案内の定型文 (2026-09-18 に全 213 サイトを実測したところ、
            # 死亡の語を含む 33 ページのうち 32 ページがこの種のナビゲーション文だった)
            "犬が死亡した場合は届出が必要です",
            "死亡届の提出をお願いします",
            "ペットが死亡したとき",
            "万が一交通事故等で死亡した場合は委託業者により回収されている可能性があります",
            "犬の登録・変更・死亡届・狂犬病予防注射",
            "犬猫など動物死体の引き取り",
        ],
    )
    def test_not_detected(self, text: str) -> None:
        assert deceased_notice(text) is None

    def test_none_is_safe(self) -> None:
        assert deceased_notice(None) is None

    def test_returns_matched_phrase_for_logging(self) -> None:
        """どの語で判定したかをログに出せるよう、一致した語を返す"""
        assert deceased_notice("長尾 短毛 令和8年9月13日 死亡確認") == "死亡確認"
