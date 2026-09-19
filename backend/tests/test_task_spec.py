"""Спецификация задачи: фраза человека разбирается один раз и не теряется.

Проверяем ровно то, что раньше пропадало по дороге: площадка, вид контента,
формат, длительность, режим качества и явный выбор модели/канала.
"""
from core import task_spec


def test_photo_for_instagram_is_an_image_in_platform_format():
    spec = task_spec.parse("Создай фотографию шашлыка для Instagram")
    assert spec["kind"] == "image"
    assert spec["platform"] == "instagram"
    assert spec["ratio"] == "4:5"          # требование ленты Instagram
    assert "шашлык" in spec["subject"]


def test_reels_keeps_seconds_and_quality_mode():
    spec = task_spec.parse("Создай Reels про шашлык на 20 секунд максимально качественно")
    assert spec["kind"] == "video"
    assert spec["platform"] == "instagram"
    assert spec["seconds"] == 20
    assert spec["quality"] == "quality"
    assert spec["subject"] == "шашлык"


def test_cheap_request_switches_to_economy():
    spec = task_spec.parse("сделай вертикальное фото шашлыка подешевле")
    assert spec["quality"] == "economy"
    assert spec["ratio"] == "9:16"


def test_explicit_model_and_channel_survive():
    spec = task_spec.parse("сделай видео приготовления шашлыка через браузер используй kling")
    assert spec["model"] == "kling"
    assert spec["channel"] == "browser"
    assert "kling" not in spec["subject"]
    assert "браузер" not in spec["subject"]


def test_youtube_cover_is_horizontal():
    spec = task_spec.parse("сделай обложку для youtube")
    assert spec["kind"] == "image"
    assert spec["ratio"] == "16:9"


def test_count_of_variants():
    assert task_spec.parse("сделай 5 вариантов кадра")["count"] == 5
    assert task_spec.parse("сделай кадр")["count"] == 1


def test_buttons_win_over_text():
    # Человек нажал «🖼 Изображение» — текст не должен это переопределять.
    spec = task_spec.parse("ролик про шашлык", kind="image", platform="youtube")
    assert spec["kind"] == "image"
    assert spec["platform"] == "youtube"


def test_subject_keeps_case_and_words_that_matter():
    spec = task_spec.parse("сделай фото шашлыка на мангале для Instagram")
    assert spec["subject"] == "шашлыка на мангале"


def test_nothing_is_invented_when_nothing_is_said():
    spec = task_spec.parse("шашлык на мангале")
    assert spec["platform"] is None
    assert spec["quality"] is None
    assert spec["model"] is None
    assert spec["channel"] is None


def test_as_text_shows_what_will_be_made():
    text = task_spec.as_text(task_spec.parse("фото шашлыка для Instagram подешевле"))
    assert "Изображение" in text and "Instagram" in text and "экономно" in text
