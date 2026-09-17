"""Формат задаёт площадка, а не слово в задаче и не место в коде.

Эти три случая раньше были неверны: горизонтальный YouTube генерировался
вертикально, пост в Instagram — квадратом, а кадры фабрики всегда шли
в инстаграмном формате, что бы ни выбрали кнопкой.
"""
import pytest

from core import formats


def test_youtube_video_is_horizontal():
    assert formats.ratio_for("youtube", "video") == "16:9"
    assert formats.size_for("youtube", "video") == "1920x1080"


def test_shorts_is_vertical_even_though_it_is_youtube():
    assert formats.ratio_for("shorts", "video") == "9:16"
    assert formats.seconds_for("shorts", "video") > 0


def test_instagram_feed_post_is_four_by_five():
    assert formats.ratio_for("instagram", "image") == "4:5"


def test_instagram_reels_is_vertical():
    assert formats.ratio_for("instagram", "video") == "9:16"


def test_unknown_platform_falls_back_to_vertical():
    assert formats.ratio_for("мояплощадка", "video") == "9:16"


def test_carousel_counts_as_image():
    assert formats.ratio_for("instagram", "carousel") == formats.ratio_for("instagram", "image")


def test_description_names_format_and_length():
    text = formats.describe("tiktok", "video")
    assert "9:16" in text and "сек" in text


def test_image_description_has_no_duration():
    assert "сек" not in formats.describe("instagram", "image")


def test_every_spec_has_a_known_ratio():
    for key, s in formats.SPECS.items():
        assert s["ratio"] in formats.PIXELS, key


def test_buttons_cover_every_listed_platform():
    for code, _ in formats.PLATFORMS:
        assert f"{code}/video" in formats.SPECS
