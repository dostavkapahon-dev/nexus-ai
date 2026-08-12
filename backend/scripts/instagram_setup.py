"""
Помощник настройки Instagram Graph API.

Что делает: берёт токен из Graph API Explorer, проверяет права, находит
Facebook Page с привязанным Instagram Professional аккаунтом, достаёт
INSTAGRAM_ACCOUNT_ID и (если заданы app id/secret) меняет короткий токен
на долгоживущий Page-токен, который не протухает через час.

Запуск:
    python -m backend.scripts.instagram_setup --token EAA...
    python -m backend.scripts.instagram_setup --token EAA... \
        --app-id 123 --app-secret abc      # + долгоживущий токен
"""

import argparse
import os
import sys

import httpx

GRAPH_URL = "https://graph.facebook.com/v19.0"
REQUIRED_SCOPES = {
    "pages_show_list",
    "pages_read_engagement",
    "pages_manage_posts",
    "instagram_basic",
    "instagram_content_publish",
}


def _get(client: httpx.Client, path: str, **params) -> dict:
    try:
        r = client.get(f"{GRAPH_URL}{path}", params=params)
        data = r.json()
    except httpx.HTTPError as e:
        raise RuntimeError(f"сеть недоступна ({type(e).__name__}: {e})") from e
    except ValueError as e:
        raise RuntimeError(f"Graph API вернул не JSON: {e}") from e
    if "error" in data:
        raise RuntimeError(data["error"].get("message", str(data["error"])))
    return data


def check_scopes(client: httpx.Client, token: str) -> list[str]:
    """Возвращает список недостающих прав (пустой = всё выдано)."""
    data = _get(client, "/debug_token", input_token=token, access_token=token)
    granted = set(data.get("data", {}).get("scopes", []))
    return sorted(REQUIRED_SCOPES - granted)


def find_instagram_account(client: httpx.Client, token: str) -> list[dict]:
    """Все Page пользователя с их Instagram Business аккаунтами и page-токенами."""
    data = _get(
        client,
        "/me/accounts",
        access_token=token,
        fields="id,name,access_token,instagram_business_account{id,username}",
    )
    return data.get("data", [])


def exchange_long_lived(client: httpx.Client, token: str, app_id: str, app_secret: str) -> str:
    data = _get(
        client,
        "/oauth/access_token",
        grant_type="fb_exchange_token",
        client_id=app_id,
        client_secret=app_secret,
        fb_exchange_token=token,
    )
    return data["access_token"]


def main() -> int:
    p = argparse.ArgumentParser(description="Настройка Instagram Graph API для Nexus AI")
    p.add_argument("--token", default=os.getenv("INSTAGRAM_ACCESS_TOKEN"),
                   help="токен из Graph API Explorer (или переменная INSTAGRAM_ACCESS_TOKEN)")
    p.add_argument("--app-id", default=os.getenv("FACEBOOK_APP_ID"))
    p.add_argument("--app-secret", default=os.getenv("FACEBOOK_APP_SECRET"))
    args = p.parse_args()

    if not args.token:
        print("Нужен токен: --token EAA... (взять на developers.facebook.com/tools/explorer)")
        return 2

    token = args.token
    with httpx.Client(timeout=20) as client:
        try:
            missing = check_scopes(client, token)
        except RuntimeError as e:
            print(f"Токен нерабочий: {e}")
            return 1

        if missing:
            print("Не хватает прав, выдай их в Graph API Explorer и сгенерируй токен заново:")
            for s in missing:
                print(f"  - {s}")
            return 1
        print("Права: все нужные выданы ✓")

        if args.app_id and args.app_secret:
            try:
                token = exchange_long_lived(client, token, args.app_id, args.app_secret)
                print("Токен обменян на долгоживущий (~60 дней) ✓")
            except RuntimeError as e:
                print(f"Не удалось обменять токен, продолжаю с коротким: {e}")

        try:
            pages = find_instagram_account(client, token)
        except RuntimeError as e:
            print(f"Не удалось получить список Page: {e}")
            return 1

    linked = [pg for pg in pages if pg.get("instagram_business_account")]
    if not linked:
        print("Ни к одной Facebook Page не привязан Instagram Professional аккаунт.")
        print("Проверь: Page → Настройки → Связанные аккаунты → Instagram.")
        return 1

    print("\nНайдено:")
    for pg in linked:
        ig = pg["instagram_business_account"]
        print(f"  Page «{pg['name']}» (id {pg['id']}) → IG @{ig.get('username','?')} id {ig['id']}")

    best = linked[0]
    ig_id = best["instagram_business_account"]["id"]
    # Page-токен предпочтительнее user-токена: он не зависит от сессии человека.
    page_token = best.get("access_token") or token

    print("\nВпиши в .env (или в Настройки в интерфейсе):")
    print(f"INSTAGRAM_ACCESS_TOKEN={page_token}")
    print(f"INSTAGRAM_ACCOUNT_ID={ig_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
