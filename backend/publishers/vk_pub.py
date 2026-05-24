"""
VKontakte publisher via VK API.
Requires VK_ACCESS_TOKEN and VK_GROUP_ID environment variables.
"""
import os
import httpx

VK_API = "https://api.vk.com/method"
VK_VERSION = "5.199"

async def publish_vk(text: str, image_url: str = None) -> dict:
    token = os.getenv("VK_ACCESS_TOKEN", "")
    group_id = os.getenv("VK_GROUP_ID", "")
    if not token or not group_id:
        raise ValueError("VK_ACCESS_TOKEN and VK_GROUP_ID not set")

    params = {
        "owner_id": f"-{group_id}",
        "from_group": 1,
        "message": text,
        "access_token": token,
        "v": VK_VERSION,
    }

    # Attach photo if image_url provided
    attachments = []
    if image_url:
        try:
            async with httpx.AsyncClient(timeout=20) as c:
                # Get upload server
                r = await c.get(f"{VK_API}/photos.getWallUploadServer",
                                params={"group_id": group_id, "access_token": token, "v": VK_VERSION})
                upload_url = r.json()["response"]["upload_url"]

                # Download image
                img_r = await c.get(image_url)
                img_bytes = img_r.content

                # Upload to VK
                up_r = await c.post(upload_url, files={"photo": ("image.jpg", img_bytes, "image/jpeg")})
                up_data = up_r.json()

                # Save photo
                save_r = await c.post(f"{VK_API}/photos.saveWallPhoto", params={
                    "group_id": group_id, "photo": up_data["photo"],
                    "server": up_data["server"], "hash": up_data["hash"],
                    "access_token": token, "v": VK_VERSION
                })
                photo = save_r.json()["response"][0]
                attachments.append(f"photo{photo['owner_id']}_{photo['id']}")
        except Exception:
            pass

    if attachments:
        params["attachments"] = ",".join(attachments)

    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(f"{VK_API}/wall.post", params=params)
        data = r.json()
        if "error" in data:
            raise RuntimeError(f"VK error: {data['error']['error_msg']}")
        return {"post_id": data["response"]["post_id"]}
