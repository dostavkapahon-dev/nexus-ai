"""
Единый слой доступа к Instagram: два разных API под одним интерфейсом.

У Meta два способа работать с Instagram, и они несовместимы по адресам и путям:

  • **Instagram Login** (токен `IGAA…`) — `graph.instagram.com`, аккаунт адресуется
    как `me`. Токен выдаётся прямо в панели приложения, Страница Facebook не нужна.
  • **Facebook Login** (токен `EAA…`) — `graph.facebook.com`, аккаунт адресуется
    числовым Instagram Account ID, привязанным к Странице.

Раньше весь код был жёстко зашит на `graph.facebook.com` и числовой id. С токеном
`IGAA…` это означало, что публикация, чтение и комментарии не работали вовсе —
Meta просто не знает такого адреса для этого токена. Здесь эта разница закрыта
в одном месте, чтобы коннектор, ридер и публикатор не расходились.
"""
import os

GRAPH_FB = "https://graph.facebook.com/v19.0"
GRAPH_IG = "https://graph.instagram.com/v21.0"

FACEBOOK, INSTAGRAM = "facebook", "instagram"


def token() -> str:
    return os.getenv("INSTAGRAM_ACCESS_TOKEN", "").strip()


def account_id() -> str:
    return os.getenv("INSTAGRAM_ACCOUNT_ID", "").strip()


def token_type() -> str:
    """Тип токена. Сохраняется при подключении; иначе определяем по префиксу.

    Префикс — надёжный признак: токены Instagram Login всегда начинаются с IGAA,
    токены Facebook — с EAA. Явно сохранённое значение имеет приоритет.
    """
    saved = os.getenv("INSTAGRAM_TOKEN_TYPE", "").strip().lower()
    if saved in (FACEBOOK, INSTAGRAM):
        return saved
    return INSTAGRAM if token().startswith("IGAA") else FACEBOOK


def is_instagram_login() -> bool:
    return token_type() == INSTAGRAM


def base() -> str:
    return GRAPH_IG if is_instagram_login() else GRAPH_FB


def node() -> str:
    """Как адресовать собственный аккаунт в путях запроса.

    В Instagram Login аккаунт — это владелец токена (`me`), числовой id там
    в путях не используется и подстановка его ломает запрос.
    """
    return "me" if is_instagram_login() else account_id()


def configured() -> bool:
    """Для Instagram Login достаточно токена: id аккаунта в запросах не нужен."""
    return bool(token()) and (is_instagram_login() or bool(account_id()))


def missing() -> list[str]:
    out = []
    if not token():
        out.append("INSTAGRAM_ACCESS_TOKEN")
    if not is_instagram_login() and not account_id():
        out.append("INSTAGRAM_ACCOUNT_ID")
    return out


def url(path: str) -> str:
    """Полный адрес запроса. `path` — уже готовый путь без ведущего слэша."""
    return f"{base()}/{path.lstrip('/')}"


def me_path(suffix: str = "") -> str:
    """Путь к собственному аккаунту: `me/media` или `17841…/media`."""
    return f"{node()}/{suffix.lstrip('/')}" if suffix else node()


# Поля профиля различаются: у Instagram Login нет `biography` в базовом наборе,
# запрос несуществующего поля Meta считает ошибкой и не отдаёт вообще ничего.
PROFILE_FIELDS_IG = "id,username,followers_count,media_count,account_type"
PROFILE_FIELDS_FB = "username,followers_count,media_count,biography"


def profile_fields() -> str:
    return PROFILE_FIELDS_IG if is_instagram_login() else PROFILE_FIELDS_FB
