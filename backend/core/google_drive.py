"""
Google Drive integration for caching niche analysis.
Uses a service account JSON stored in the Connection table (key: google_service_account_json).
"""
import os
import json
import asyncio
from io import BytesIO

async def _get_service():
    """Build Drive service from service account JSON stored in DB or env."""
    from googleapiclient.discovery import build
    from google.oauth2 import service_account

    sa_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    if not sa_json:
        raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON not configured")

    info = json.loads(sa_json)
    creds = service_account.Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/drive"]
    )
    return await asyncio.to_thread(build, "drive", "v3", credentials=creds)

async def find_file(folder_id: str, filename: str) -> dict | None:
    """Return file metadata if filename exists in folder, else None."""
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
    """Upload JSON data to Google Drive folder. Returns {id, webViewLink}."""
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
    # Make publicly viewable
    await asyncio.to_thread(
        lambda: service.permissions().create(
            fileId=result["id"],
            body={"type": "anyone", "role": "reader"}
        ).execute()
    )
    return result

async def read_json(file_id: str) -> dict:
    """Download and parse JSON file from Google Drive."""
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
