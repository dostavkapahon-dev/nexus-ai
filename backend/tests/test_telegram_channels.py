"""
Подключение Telegram-канала и режимы автопубликации.

Настоящий Bot API в тестах не дёргаем: подменяем один транспорт (`tg.call`),
поэтому проверяется наша логика — а именно то, ради чего мастер и делался:
канал без прав нельзя «подключить», а площадка на подтверждении не публикуется
сама.
"""
import pytest

from core import telegram_channels as tc
from core import autopublish as ap
from core import publish_queue as pq
from publishers import telegram_pub as tg


def _fake_api(responses: dict, calls: list | None = None):
    """responses: {метод: результат Bot API}. Отсутствующий метод — отказ."""
    async def call(method, payload, *, token="", timeout=30):
        if calls is not None:
            calls.append((method, payload))
        if method not in responses:
            return {"ok": False, "error": f"нет ответа для {method}"}
        val = responses[method]
        return val if isinstance(val, dict) and "ok" in val else {"ok": True, "result": val}
    return call


ADMIN_CHANNEL = {
    "getChat": {"id": -1001, "title": "Мой канал", "username": "my_channel", "type": "channel"},
    "getMe": {"id": 42, "username": "nexus_bot", "first_name": "Nexus"},
    "getChatMember": {"status": "administrator", "can_post_messages": True,
                      "can_edit_messages": True},
}


@pytest.mark.asyncio
async def test_check_channel_reports_rights(client, monkeypatch):
    monkeypatch.setattr(tg, "call", _fake_api(ADMIN_CHANNEL))
    res = await tc.check_channel("@my_channel")
    assert res["ok"] and res["is_admin"] and res["can_publish"]
    assert res["chat"]["chat_id"] == "-1001"
    assert "can_post_messages" in res["rights"]


@pytest.mark.asyncio
async def test_channel_without_post_right_cannot_be_added(client, monkeypatch):
    """Главное, ради чего мастер: канал, куда бот не может писать, не должен
    оседать в списке «подключённых» и всплывать потерянным постом."""
    monkeypatch.setattr(tg, "call", _fake_api({
        **ADMIN_CHANNEL,
        "getChatMember": {"status": "administrator", "can_post_messages": False}}))

    check = await tc.check_channel("@my_channel")
    assert check["ok"] and check["can_publish"] is False
    assert "Публикация сообщений" in check["hint"]

    added = await tc.add_channel("@my_channel")
    assert added["ok"] is False
    assert await tc.list_channels() == []


@pytest.mark.asyncio
async def test_add_channel_sets_default_and_survives_in_db(client, monkeypatch):
    monkeypatch.setattr(tg, "call", _fake_api(ADMIN_CHANNEL))
    res = await tc.add_channel("@my_channel")
    assert res["ok"] and res["channel"]["default"] is True
    assert await tc.default_channel() == "-1001"

    items = await tc.list_channels()
    assert [c["chat_id"] for c in items] == ["-1001"]

    assert (await tc.remove_channel("-1001"))["ok"] is True
    assert await tc.list_channels() == []


@pytest.mark.asyncio
async def test_test_publish_removes_its_own_message(client, monkeypatch):
    """Тестовая публикация не должна оставлять мусор в канале пользователя."""
    calls = []
    monkeypatch.setattr(tg, "call", _fake_api({
        "sendMessage": {"message_id": 7, "chat": {"id": -1001, "username": "my_channel"}},
        "deleteMessage": True}, calls))

    res = await tc.test_publish("-1001")
    assert res["ok"] and res["deleted"] is True
    assert res["post_url"] == "https://t.me/my_channel/7"
    assert [m for m, _ in calls] == ["sendMessage", "deleteMessage"]


@pytest.mark.asyncio
async def test_test_publish_reports_refusal(client, monkeypatch):
    monkeypatch.setattr(tg, "call", _fake_api({
        "sendMessage": {"ok": False, "error": "CHAT_ADMIN_REQUIRED"}}))
    res = await tc.test_publish("-1001")
    assert res["ok"] is False and "CHAT_ADMIN_REQUIRED" in res["error"]


@pytest.mark.asyncio
async def test_discover_lists_channels_seen_by_bot(client, monkeypatch):
    """Каналы приходят из цикла бота, а не отдельным запросом: своё соединение
    мастер открыть не может — Telegram отдаёт токену только одно."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    tc._seen_chats.clear()
    tc.remember_chat({"id": -1001, "title": "Канал", "username": "ch", "type": "channel"})

    res = await tc.discover()
    assert [i["chat_id"] for i in res["items"]] == ["-1001"]
    assert res["items"][0]["username"] == "@ch"


@pytest.mark.asyncio
async def test_discover_without_seen_channels_explains_what_to_do(client, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    tc._seen_chats.clear()
    res = await tc.discover()
    assert res["ok"] and res["items"] == [] and "администратором" in res["hint"]


@pytest.mark.asyncio
async def test_discover_without_bot_says_so(client, monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    tc._seen_chats.clear()
    res = await tc.discover()
    assert res["ok"] is False and "не подключён" in res["error"]


# ─────────────────────────── автопубликация ───────────────────────────

@pytest.mark.asyncio
async def test_confirm_mode_holds_post_until_approved(client, monkeypatch):
    """Площадка «с подтверждением»: автоматика готовит пост, но не публикует."""
    await ap.set_settings(platforms={"instagram": ap.CONFIRM})

    published = []

    async def ok(platform, text, image_url, video_url=""):
        published.append(platform)
        return {"ok": True, "post_id": "p1"}

    from core.orchestrator import nexus_core
    monkeypatch.setattr(nexus_core, "_publish_one", ok)

    pub_id = await pq.enqueue("instagram", "пост", approved=False)
    assert await pq.due() == []            # очередь его не подхватывает
    assert published == []

    items = await pq.pending()
    assert [i["id"] for i in items] == [pub_id]

    res = await pq.approve(pub_id)
    assert res["ok"] and published == ["instagram"]


@pytest.mark.asyncio
async def test_auto_mode_publishes_without_human(client):
    await ap.set_settings(platforms={"telegram": ap.AUTO})
    assert await ap.may_autopublish("telegram") is True

    pub_id = await pq.enqueue("telegram", "пост", approved=False)
    assert pub_id in await pq.due()


@pytest.mark.asyncio
async def test_global_switch_overrides_platform(client):
    """Выключенная автопубликация сильнее площадки: иначе «выключить» ничего
    не выключало бы для площадок, про которые забыли."""
    await ap.set_settings(enabled=False, platforms={"telegram": ap.AUTO})
    assert await ap.mode_for("telegram") == ap.CONFIRM
    assert await ap.may_autopublish("telegram") is False

    await ap.set_settings(enabled=True)
    assert await ap.may_autopublish("telegram") is True


@pytest.mark.asyncio
async def test_api_autopublish_settings(auth_client):
    r = await auth_client.get("/api/publish/auto")
    assert r.status_code == 200
    assert "platforms" in r.json()

    r = await auth_client.post("/api/publish/auto",
                          json={"enabled": True, "platforms": {"tiktok": "confirm"}})
    assert r.json()["platforms"]["tiktok"] == "confirm"

    r = await auth_client.post("/api/publish/auto", json={"platforms": {"tiktok": "нет-такого"}})
    assert r.json()["ok"] is False


@pytest.mark.asyncio
async def test_api_telegram_flow(auth_client, monkeypatch):
    monkeypatch.setattr(tg, "call", _fake_api({
        **ADMIN_CHANNEL,
        "sendMessage": {"message_id": 9, "chat": {"id": -1001, "username": "my_channel"}},
        "deleteMessage": True}))

    r = await auth_client.post("/api/telegram/channels/check", json={"chat_id": "@my_channel"})
    assert r.json()["can_publish"] is True

    r = await auth_client.post("/api/telegram/channels/test", json={"chat_id": "@my_channel"})
    assert r.json()["ok"] is True

    r = await auth_client.post("/api/telegram/channels/add", json={"chat_id": "@my_channel"})
    assert r.json()["ok"] is True

    r = await auth_client.get("/api/telegram/channels")
    assert r.json()["default"] == "-1001"

    # Публикация без канала в теле уходит в канал по умолчанию.
    r = await auth_client.post("/api/telegram/publish", json={"text": "привет"})
    body = r.json()
    assert body["ok"] and body["message_id"] == 9

    await auth_client.post("/api/telegram/channels/remove", json={"chat_id": "-1001"})


@pytest.mark.asyncio
async def test_api_telegram_publish_without_channel(auth_client, monkeypatch):
    monkeypatch.delenv("TELEGRAM_POST_CHAT_ID", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    r = await auth_client.post("/api/telegram/publish", json={"text": "привет"})
    assert r.json()["ok"] is False
    assert "канал" in r.json()["error"]


@pytest.mark.asyncio
async def test_scheduled_telegram_publish_goes_to_shared_queue(auth_client, monkeypatch):
    """Запланированное из Telegram видно на сайте — очередь одна на обе «головы»."""
    monkeypatch.setattr(tg, "call", _fake_api(ADMIN_CHANNEL))
    await tc.add_channel("@my_channel")

    r = await auth_client.post("/api/telegram/publish",
                          json={"text": "потом", "when": "2030-01-01T10:00"})
    pub_id = r.json()["publication_id"]

    q = await auth_client.get("/api/publish/queue")
    assert pub_id in [i["id"] for i in q.json()["items"]]

    st = await auth_client.get(f"/api/telegram/publication/{pub_id}")
    assert st.json()["status"] == pq.SCHEDULED

    await tc.remove_channel("-1001")


# ─────────────── честные отказы и лимиты Telegram ───────────────

@pytest.mark.asyncio
async def test_no_rights_is_permanent_refusal(client, monkeypatch):
    """Бота выгнали из канала — повторять пять раз бессмысленно."""
    async def deny(method, payload, *, token="", timeout=30, retries=2):
        return await tg.call.__wrapped__(method, payload) if False else None

    def fake_post(*a, **kw):
        raise AssertionError("до сети доходить не должно")

    class _R:
        @staticmethod
        def json():
            return {"ok": False, "error_code": 403,
                    "description": "Forbidden: bot is not a member of the channel chat"}

    class _C:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, json=None): return _R()

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setattr(tg.httpx, "AsyncClient", lambda *a, **kw: _C())

    res = await tg.send_message("-1001", "привет")
    assert res["ok"] is False and res["blocked_by_api"] is True
    assert "удалили из канала" in res["error"]

    # Очередь обязана признать это окончательным отказом, а не сетевым сбоем.
    from core.publish_queue import _is_permanent
    assert _is_permanent(res) is True


@pytest.mark.asyncio
async def test_rate_limit_waits_and_retries(client, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    answers = [
        {"ok": False, "error_code": 429, "description": "Too Many Requests",
         "parameters": {"retry_after": 1}},
        {"ok": True, "result": {"message_id": 5, "chat": {"id": -1001}}},
    ]
    slept = []

    class _R:
        def __init__(self, payload): self._p = payload
        def json(self): return self._p

    class _C:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, json=None): return _R(answers.pop(0))

    async def fake_sleep(sec): slept.append(sec)

    monkeypatch.setattr(tg.httpx, "AsyncClient", lambda *a, **kw: _C())
    monkeypatch.setattr(tg.asyncio, "sleep", fake_sleep)

    res = await tg.send_message("-1001", "привет")
    assert res["ok"] and res["message_id"] == 5
    assert slept == [1], "ждать надо ровно столько, сколько просит Telegram"


@pytest.mark.asyncio
async def test_long_text_is_cut_but_reported(client, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    sent = {}

    class _R:
        @staticmethod
        def json(): return {"ok": True, "result": {"message_id": 7, "chat": {"id": -1001}}}

    class _C:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, json=None):
            sent.update(json)
            return _R()

    monkeypatch.setattr(tg.httpx, "AsyncClient", lambda *a, **kw: _C())

    res = await tg.send_photo("-1001", "https://img/1.png", "х" * 2000)
    assert res["ok"] and res["truncated"] is True and "сокращённым" in res["note"]
    assert len(sent["caption"]) <= tg.CAPTION_LIMIT


def test_escaping_protects_html_mode():
    """Символ < в тексте модели ломал отправку целиком."""
    assert tg.safe("цена < 100 & выгодно") == "цена &lt; 100 &amp; выгодно"
    short, cut = tg.fit("текст", 4096)
    assert short == "текст" and cut is False
