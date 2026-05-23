"""
Google Drive integration.
Supports two auth modes:
1. OAuth access token (from user's Google Sign-In with drive.file scope) — stored in UserProfile
2. Service account JSON (legacy, env var GOOGLE_SERVICE_ACCOUNT_JSON)
"""
import os
import json
import asyncio
from io import BytesIO

async def _get_service():
    from googleapiclient.discovery import build

    # Mode 1: OAuth access token from UserProfile
    try:
        from database.db import AsyncSessionLocal
        from database.models import UserProfile
        from sqlalchemy import select
        from google.oauth2.credentials import Credentials

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(UserProfile).limit(1))
            prof = result.scalar_one_or_none()
            if prof and prof.google_drive_access_token:
                creds = Credentials(token=prof.google_drive_access_token)
                return await asyncio.to_thread(build, "drive", "v3", credentials=creds)
    except Exception:
        pass

    # Mode 2: Service account JSON
    sa_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    if sa_json:
        from google.oauth2 import service_account
        info = json.loads(sa_json)
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=["https://www.googleapis.com/auth/drive"]
        )
        return await asyncio.to_thread(build, "drive", "v3", credentials=creds)

    raise ValueError("Google Drive не подключён. Нажмите 'Подключить Google' на главной странице.")

async def find_file(folder_id: str, filename: str) -> dict | None:
    try:
        service = await _get_service()
        query = f"'{folder_id}' in parents and name='{filename}' and trashed=false"
        result = await asyncio.to_thread(
            lambda: service.files().list(q=query, fields="files(id,name,webViewLink)").execute()
        )
        files = result.get("files", [])
        return files[0] if files else None
    except Exception:
        return None

async def upload_json(folder_id: str, filename: str, data: dict) -> dict:
    from googleapiclient.http import MediaIoBaseUpload

    service = await _get_service()
    content = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    media = MediaIoBaseUpload(BytesIO(content), mimetype="application/json")
    file_meta = {"name": filename, "parents": [folder_id]}

    result = await asyncio.to_thread(
        lambda: service.files().create(
            body=file_meta, media_body=media, fields="id,webViewLink"
        ).execute()
    )
    try:
        await asyncio.to_thread(
            lambda: service.permissions().create(
                fileId=result["id"],
                body={"type": "anyone", "role": "reader"}
            ).execute()
        )
    except Exception:
        pass
    return result

async def read_json(file_id: str) -> dict:
    from googleapiclient.http import MediaIoBaseDownload

    service = await _get_service()
    buf = BytesIO()
    downloader = await asyncio.to_thread(
        lambda: service.files().get_media(fileId=file_id)
    )

    def _download():
        dl = MediaIoBaseDownload(buf, downloader)
        done = False
        while not done:
            _, done = dl.next_chunk()
        return buf.getvalue()

    raw = await asyncio.to_thread(_download)
    return json.loads(raw.decode("utf-8"))
