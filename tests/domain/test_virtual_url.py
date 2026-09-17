"""virtual_url の純関数テスト (T413)

1 ページに複数頭が載るサイトは `<list_url>#row=N` のような掲載位置の仮想 URL で
個体を区別していた。先頭に 1 頭増えるだけで全員の URL が 1 つずれ、同じ URL に
別の子が入る (町田市の迷子猫一覧で 2026-09-16 に 52 行)。PDF のファイル名を含む
`#pdf=0916cat.pdf&row=N` は、日付入りの PDF が差し替わるたびに全員の URL が変わる
(さぬき動物愛護センター)。収集後に管理番号か画像ファイル名で `#animal=<キー>` へ
付け替え、掲載順や PDF 名に左右されない URL にする。
"""

from __future__ import annotations

from datetime import date

from src.data_collector.domain.models import AnimalData
from src.data_collector.domain.virtual_url import (
    image_key,
    is_positional_virtual_url,
    management_key,
    stabilize_virtual_urls,
)

LIST = "https://www.city.example.lg.jp/pet/list.html"
IMG = "https://www.city.example.lg.jp/img"


def _animal(
    url: str,
    *,
    mgmt: str | None = None,
    images: tuple[str, ...] = (),
    species: str = "猫",
) -> AnimalData:
    return AnimalData(
        species=species,
        sex="女の子",
        breed="雑種",
        shelter_date=date(2026, 9, 16),
        location="東京都町田市",
        source_url=url,
        category="lost",
        management_number=mgmt,
        image_urls=list(images),
    )


def _urls(animals: list[AnimalData]) -> list[str]:
    return [str(a.source_url) for a in animals]


class TestStabilizeVirtualUrls:
    def test_same_individual_keeps_url_when_list_order_shifts(self):
        """先頭に 1 頭増えて掲載位置がずれても、同じ子の URL は変わらない"""
        day1 = [
            _animal(f"{LIST}#h3=0", images=(f"{IMG}/210129mayoineko2.jpg",)),
            _animal(f"{LIST}#h3=1", images=(f"{IMG}/201005mayoineko.jpg",)),
        ]
        day2 = [
            _animal(f"{LIST}#h3=0", images=(f"{IMG}/260916mayoineko.jpg",)),
            _animal(f"{LIST}#h3=1", images=(f"{IMG}/210129mayoineko2.jpg",)),
            _animal(f"{LIST}#h3=2", images=(f"{IMG}/201005mayoineko.jpg",)),
        ]

        urls1 = _urls(stabilize_virtual_urls(day1))
        urls2 = _urls(stabilize_virtual_urls(day2))

        assert urls1 == [
            f"{LIST}#animal=210129mayoineko2.jpg",
            f"{LIST}#animal=201005mayoineko.jpg",
        ]
        assert urls2 == [f"{LIST}#animal=260916mayoineko.jpg", *urls1]

    def test_management_number_is_preferred_over_image(self):
        animals = [_animal(f"{LIST}#row=0", mgmt="C26031", images=(f"{IMG}/c26031.png",))]

        assert _urls(stabilize_virtual_urls(animals)) == [f"{LIST}#animal=C26031"]

    def test_pdf_filename_change_keeps_url(self):
        """日付入りの PDF が差し替わっても、管理番号が同じなら URL は変わらない"""
        before = [_animal(f"{LIST}#pdf=0915cat.pdf&row=0", mgmt="8中-C0046")]
        after = [
            _animal(f"{LIST}#pdf=0916cat.pdf&row=0", mgmt="8中-C0047"),
            _animal(f"{LIST}#pdf=0916cat.pdf&row=1", mgmt="8中-C0046"),
        ]

        assert _urls(stabilize_virtual_urls(before)) == _urls(stabilize_virtual_urls(after))[1:]

    def test_management_number_width_and_hyphen_variants_share_one_url(self):
        """「８中‐C0120」と「8中-C0120」は同じ番号として同じ URL になる (さぬきの PDF で混在)"""
        full_width = stabilize_virtual_urls(
            [_animal(f"{LIST}#pdf=0916cat.pdf&row=0", mgmt="８中‐C0120")]
        )
        half_width = stabilize_virtual_urls(
            [_animal(f"{LIST}#pdf=0917cat.pdf&row=5", mgmt="8中-C0120")]
        )

        assert _urls(full_width) == [f"{LIST}#animal=8%E4%B8%AD-C0120"]
        assert _urls(half_width) == _urls(full_width)

    def test_duplicate_keys_on_same_page_stay_positional(self):
        """同じページで同じキーになる子は区別できないので、位置の URL のまま残す"""
        animals = [
            _animal(f"{LIST}#row=0", images=("https://www.example.jp/a/photo.jpg",)),
            _animal(f"{LIST}#row=1", images=("https://www.example.jp/b/photo.jpg",)),
            _animal(f"{LIST}#row=2", images=("https://www.example.jp/c/unique.jpg",)),
        ]

        assert _urls(stabilize_virtual_urls(animals)) == [
            f"{LIST}#row=0",
            f"{LIST}#row=1",
            f"{LIST}#animal=unique.jpg",
        ]

    def test_placeholder_image_is_not_used_as_key(self):
        """「画像なし」の共通画像は個体を表さないのでキーに使わない"""
        animals = [
            _animal(f"{LIST}#row=0", images=(f"{IMG}/pic_noimage110_dgray.jpg",)),
            _animal(f"{LIST}#row=1", images=(f"{IMG}/no_photo.png",)),
            _animal(f"{LIST}#row=2", images=(f"{IMG}/nowprinting.gif",)),
        ]

        assert _urls(stabilize_virtual_urls(animals)) == _urls(animals)

    def test_without_management_number_or_image_stays_positional(self):
        animals = [_animal(f"{LIST}#row=0"), _animal(f"{LIST}#row=1", mgmt="  ")]

        assert _urls(stabilize_virtual_urls(animals)) == _urls(animals)

    def test_non_positional_urls_are_untouched(self):
        """個別ページの URL や、adapter が付けた安定キーの URL は触らない"""
        animals = [
            _animal("https://www.city.example.lg.jp/pet/detail/123", mgmt="A-1"),
            _animal(f"{LIST}#animal=2620073", mgmt="2620073"),
            _animal(
                "https://douai-tokushima.com/animalinfo/list1_1/#animal=photo2-17788280710",
                images=("https://douai-tokushima.com/animalinfo/photo/photo2-17788280710.JPG",),
            ),
        ]

        assert _urls(stabilize_virtual_urls(animals)) == _urls(animals)

    def test_same_key_on_different_pages_is_allowed(self):
        other = "https://www.city.example.lg.jp/pet/list_dog.html"
        animals = [
            _animal(f"{LIST}#row=0", images=("https://www.example.jp/cat/1.jpg",)),
            _animal(f"{other}#row=0", images=("https://www.example.jp/dog/1.jpg",)),
        ]

        assert _urls(stabilize_virtual_urls(animals)) == [
            f"{LIST}#animal=1.jpg",
            f"{other}#animal=1.jpg",
        ]

    def test_key_colliding_with_other_url_in_batch_stays_positional(self):
        """付け替え先が同じ回の別の子の URL と重なるときは付け替えない"""
        animals = [
            _animal(f"{LIST}#animal=A-1", mgmt="A-1"),
            _animal(f"{LIST}#row=1", mgmt="A-1"),
        ]

        assert _urls(stabilize_virtual_urls(animals)) == _urls(animals)

    def test_percent_encoded_image_name_is_not_double_encoded(self):
        image = (
            "https://nyantomo.jp/wp-content/uploads/2026/05/%E3%81%84%E3%82%8D%E3%81%AF-300x225.jpg"
        )
        animals = [_animal("https://nyantomo.jp/donanhakodate/#row=3", images=(image,))]

        assert _urls(stabilize_virtual_urls(animals)) == [
            "https://nyantomo.jp/donanhakodate/#animal=%E3%81%84%E3%82%8D%E3%81%AF-300x225.jpg"
        ]

    def test_only_source_url_changes_and_input_is_not_mutated(self):
        animal = _animal(f"{LIST}#row=0", mgmt="R8No.62", images=(f"{IMG}/inu.R8No.62.2.jpg",))

        (result,) = stabilize_virtual_urls([animal])

        assert str(animal.source_url) == f"{LIST}#row=0"
        assert str(result.source_url) == f"{LIST}#animal=R8No.62"
        assert result.model_dump(exclude={"source_url"}) == animal.model_dump(
            exclude={"source_url"}
        )
        assert AnimalData.model_validate(result.model_dump()).source_url == result.source_url


class TestIsPositionalVirtualUrl:
    def test_position_fragments(self):
        assert is_positional_virtual_url(f"{LIST}#row=0")
        assert is_positional_virtual_url(f"{LIST}#h3=12")
        assert is_positional_virtual_url(f"{LIST}#pdf=0916cat.pdf&row=3")

    def test_tokushima_fallback_key_is_positional(self):
        """徳島 (T135) は番号も写真も無い子に掲載順の `row{N}` をキーとして使う (PR レビュー)"""
        assert is_positional_virtual_url(
            "https://douai-tokushima.com/animalinfo/list1_1/#animal=row0"
        )
        assert not is_positional_virtual_url(
            "https://douai-tokushima.com/animalinfo/list1_1/#animal=photo2-17788280710"
        )

    def test_other_urls(self):
        assert not is_positional_virtual_url(LIST)
        assert not is_positional_virtual_url(f"{LIST}#animal=2620073")
        assert not is_positional_virtual_url(f"{LIST}#animal=photo2-1")
        assert not is_positional_virtual_url(f"{LIST}#row=abc")
        assert not is_positional_virtual_url(f"{LIST}#page=2")


class TestManagementKey:
    def test_empty_values(self):
        assert management_key(None) is None
        assert management_key("") is None
        assert management_key(" 　") is None

    def test_width_hyphen_and_space_variants_are_unified(self):
        assert management_key("８中‐C0120") == "8中-C0120"
        assert management_key("8－4－83") == "8-4-83"
        assert management_key("Ｃ２６０３１") == "C26031"
        assert management_key(" R8　No.62 ") == "R8 No.62"

    def test_inner_spaces_are_collapsed_not_removed(self):
        """空白の位置が違う番号は別の番号のまま (実データに空白の揺れは無く、消すと別番号が衝突する)"""
        assert management_key("R8  No.62") == "R8 No.62"
        assert management_key("A 12") != management_key("A1 2")

    def test_prolonged_sound_mark_is_not_treated_as_hyphen(self):
        """長音符「ー」は文字なのでハイフンとみなさない (「Aー12」と「A-12」を同じ番号にしない)

        さぬき「7西ーD0092」・栃木「９ー２」でハイフン代わりに使われているが、同じ子の番号が
        日によって「ー」と「-」で揺れた記録は無い (PR レビュー)。
        """
        assert management_key("7西ーD0092") == "7西ーD0092"
        assert management_key("９ー２") == "9ー2"
        assert management_key("Aー12") != management_key("A-12")


class TestImageKey:
    def test_first_image_file_name(self):
        assert image_key([f"{IMG}/cat.JPG", f"{IMG}/cat2.jpg"]) == "cat.JPG"

    def test_query_string_is_ignored(self):
        assert image_key([f"{IMG}/cat1.jpg?ver=20260916"]) == "cat1.jpg"

    def test_no_usable_image(self):
        assert image_key([]) is None
        assert image_key([f"{IMG}/"]) is None
        assert image_key([f"{IMG}/noimage.png"]) is None
