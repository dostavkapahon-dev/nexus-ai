"""
Архив результатов в Google Drive: папки, загрузка файлов, честная проверка.

Почему отдельный модуль, а не правка старого. `core/google_drive.py` умеет
ровно одно — класть JSON в заранее известную папку. Картинку или видео им не
сохранить, структуру папок он не создаёт, а «подключено» там означает лишь
наличие токена. Ломать его нельзя: на нём работает сохранение памяти проекта.
Здесь — то, чего не хватало для архива готового контента.

Способ подключения — сервисный аккаунт (`GOOGLE_SERVICE_ACCOUNT_JSON`). Это
единственный вариант, который переживает перезапуск и не требует человека
рядом: пользовательский OAuth-токен живёт около часа, а refresh-токена в
профиле не хранится — статус «подключено» по такому токену через час
становится неправдой.

У сервисного аккаунта нет собственного места на Диске, поэтому папку создаёт
человек и делится ею с адресом аккаунта; её идентификатор кладётся в
`GOOGLE_DRIVE_FOLDER_ID`. Без этой папки загрузка отказывает с понятным
объяснением, а не с «Service Accounts do not have storage quota».
"""
import os
import asyncio
from io import BytesIO

ROOT_ENV = "GOOGLE_DRIVE_FOLDER_ID"
SA_ENV = "GOOGLE_SERVICE_ACCOUNT_JSON"

# Куда что складывается. Структура фиксированная: искать результат по дате
# проще, когда он всегда лежит в одном и том же месте.
FOLDERS = {
    "image": ("Generated", "Images"),
    "video": ("Generated", "Videos"),
    "reels": ("Generated", "Reels"),
    "script": ("Scripts",),
    "research": ("Research",),
    "report": ("Reports",),
}

_folder_cache: dict[str, str] = {}


def configured() -> dict:
    """Что задано, а чего не хватает — до всяких сетевых вызовов."""
    sa = (os.getenv(SA_ENV) or "").strip()
    root = (os.getenv(ROOT_ENV) or "").strip()
    if not sa:
        return {"ok": False, "why": f"не задан {SA_ENV} — ключ сервисного аккаунта"}
    if not root:
        return {"ok": False,
                "why": (f"не задан {ROOT_ENV}. У сервисного аккаунта нет своего "
                        "места на Диске: создайте папку сами, дайте к ней доступ "
                        "адресу аккаунта и вставьте её идентификатор")}
    return {"ok": True, "why": ""}


async def _service():
    import json
    from googleapiclient.discovery import build
    from google.oauth2 import service_account

    ready = configured()
    if not ready["ok"]:
        raise RuntimeError(ready["why"])
    info = json.loads(os.getenv(SA_ENV))
    creds = service_account.Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/drive"])
    return await asyncio.to_thread(build, "drive", "v3", credentials=creds)


def account_email() -> str:
    """Адрес сервисного аккаунта — его нужно указать в доступе к папке."""
    import json
    try:
        return json.loads(os.getenv(SA_ENV) or "{}").get("client_email", "")
    except Exception:
        return ""


async def _child(service, parent: str, name: str) -> str:
    """Найти или создать папку внутри родительской."""
    key = f"{parent}/{name}"
    if key in _folder_cache:
        return _folder_cache[key]
    q = (f"name = '{name}' and '{parent}' in parents and "
         "mimeType = 'application/vnd.google-apps.folder' and trashed = false")
    found = await asyncio.to_thread(
        lambda: service.files().list(q=q, fields="files(id)", pageSize=1).execute())
    items = found.get("files") or []
    if items:
        _folder_cache[key] = items[0]["id"]
        return items[0]["id"]
    created = await asyncio.to_thread(
        lambda: service.files().create(
            body={"name": name, "parents": [parent],
                  "mimeType": "application/vnd.google-apps.folder"},
            fields="id").execute())
    _folder_cache[key] = created["id"]
    return created["id"]


async def folder_for(kind: str) -> str:
    """Идентификатор папки под этот вид результата, создавая её при необходимости."""
    service = await _service()
    folder = os.getenv(ROOT_ENV).strip()
    for name in FOLDERS.get(kind, ("Generated", "Other")):
        folder = await _child(service, folder, name)
    return folder


async def upload_bytes(data: bytes, name: str, kind: str = "image",
                       mime: str = "application/octet-stream") -> dict:
    """Положить готовый файл в архив. Возвращает {'ok', 'id', 'link'} или причину."""
    from googleapiclient.http import MediaIoBaseUpload
    try:
        service = await _service()
        parent = await folder_for(kind)
        media = MediaIoBaseUpload(BytesIO(data), mimetype=mime, resumable=False)
        res = await asyncio.to_thread(
            lambda: service.files().create(
                body={"name": name, "parents": [parent]},
                media_body=media, fields="id,webViewLink").execute())
        return {"ok": True, "id": res.get("id", ""),
                "link": res.get("webViewLink", "")}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}


async def download(file_id: str) -> dict:
    """Забрать файл из архива байтами. {'ok', 'data'} либо причина.

    Архив нужен не для отчёта, а чтобы результат можно было отдать снова, когда
    ссылка провайдера истекла. `webViewLink` для этого не годится: это страница
    просмотра, а не файл, и Telegram по ней ничего не заберёт.
    """
    try:
        service = await _service()
        data = await asyncio.to_thread(
            lambda: service.files().get_media(fileId=file_id).execute())
        if not data:
            return {"ok": False, "error": "архив вернул пустой файл"}
        return {"ok": True, "data": data}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}


async def upload_url(url: str, name: str, kind: str = "image") -> dict:
    """Скачать результат по ссылке провайдера и положить в архив.

    Ссылки провайдеров живут недолго: без этого шага готовый кадр через сутки
    превращается в мёртвый адрес.
    """
    import httpx
    try:
        async with httpx.AsyncClient(timeout=120, follow_redirects=True) as c:
            r = await c.get(url)
        if r.status_code != 200 or not r.content:
            return {"ok": False,
                    "error": f"файл не скачался: HTTP {r.status_code}, "
                             f"{len(r.content)} байт"}
        mime = r.headers.get("content-type", "application/octet-stream").split(";")[0]
        return await upload_bytes(r.content, name, kind, mime)
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}


async def check() -> dict:
    """Настоящая проверка: записать файл, прочитать обратно, удалить.

    «Ключ задан» ничего не доказывает: у папки может не быть доступа, а у
    аккаунта — прав. Зелёным считается только пройденный круг.
    """
    ready = configured()
    if not ready["ok"]:
        return {"ok": False, "stage": "настройка", "error": ready["why"],
                "email": account_email()}
    try:
        service = await _service()
    except Exception as e:
        return {"ok": False, "stage": "ключ",
                "error": f"{type(e).__name__}: {str(e)[:200]}"}

    stamp = os.urandom(4).hex()
    put = await upload_bytes(f"nexus-check-{stamp}".encode(),
                             f"nexus_check_{stamp}.txt", "report", "text/plain")
    if not put["ok"]:
        hint = ""
        if "storageQuotaExceeded" in put["error"]:
            hint = (" — у сервисного аккаунта нет своего места на Диске: "
                    "папка должна быть создана вами и расшарена на "
                    + (account_email() or "адрес аккаунта"))
        elif "notFound" in put["error"] or "404" in put["error"]:
            hint = (" — папка не найдена или к ней нет доступа у "
                    + (account_email() or "сервисного аккаунта"))
        return {"ok": False, "stage": "запись", "error": put["error"] + hint,
                "email": account_email()}

    try:
        got = await asyncio.to_thread(
            lambda: service.files().get(fileId=put["id"], fields="id,name").execute())
        read_ok = got.get("id") == put["id"]
    except Exception as e:
        return {"ok": False, "stage": "чтение",
                "error": f"{type(e).__name__}: {str(e)[:200]}", "file": put["id"]}

    try:
        await asyncio.to_thread(
            lambda: service.files().delete(fileId=put["id"]).execute())
    except Exception:
        pass        # мусор в архиве неприятен, но проверку не проваливает

    return {"ok": read_ok, "stage": "готово", "email": account_email(),
            "link": put.get("link", ""),
            "error": "" if read_ok else "записанное не читается обратно"}
