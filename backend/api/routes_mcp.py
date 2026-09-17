"""Адрес возврата после входа в Higgsfield.

Открыт без пароля намеренно: на него человека возвращает сама платформа, и
проверка входа здесь не наша — её делает `state`, выданный при старте. Чужой
запрос без совпадающего state отклоняется.

Ни код, ни токен в ответ не попадают: страницу видит браузер, а браузер бывает
чужой. Человеку показывается только «получилось» или причина отказа.
"""
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["mcp"])

_PAGE = """<!doctype html><meta charset="utf-8">
<title>Higgsfield</title>
<style>body{{font:16px/1.5 system-ui;margin:0;display:grid;place-items:center;
height:100vh;background:#0f1115;color:#e7e9ee}}div{{max-width:32rem;padding:2rem}}
b{{color:{color}}}</style>
<div><p><b>{head}</b></p><p>{text}</p></div>"""


@router.get("/api/mcp/higgsfield/callback", response_class=HTMLResponse)
async def higgsfield_callback(code: str = "", state: str = "", error: str = "",
                              error_description: str = ""):
    from core import mcp_oauth
    if error:
        return HTMLResponse(_PAGE.format(
            color="#ff6b6b", head="Вход не завершён",
            text=f"{error}: {error_description or 'платформа отклонила запрос'}"),
            status_code=400)
    res = await mcp_oauth.finish(code, state)
    if res.get("ok"):
        more = ("Доступ будет продлеваться сам."
                if res.get("refreshable")
                else "Когда доступ истечёт, войти нужно будет ещё раз.")
        return HTMLResponse(_PAGE.format(
            color="#51cf66", head="Higgsfield подключён",
            text=f"Можно закрыть вкладку и вернуться в Telegram. {more}"))
    return HTMLResponse(_PAGE.format(
        color="#ff6b6b", head="Вход не завершён", text=res.get("error", "")),
        status_code=400)
