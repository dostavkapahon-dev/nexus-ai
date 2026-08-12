# Подключение Instagram к Nexus AI

Автопубликация идёт через Instagram Graph API. Нужны две переменные:
`INSTAGRAM_ACCESS_TOKEN` и `INSTAGRAM_ACCOUNT_ID`.

Шаги 1–4 делаются руками в браузере под твоим аккаунтом — Facebook не даёт
получить токен иначе. Шаги 5–6 делает скрипт.

## 1. Instagram → Professional

В приложении Instagram: Настройки → Тип аккаунта → переключить на
Professional (Business или Creator). Личный аккаунт через API постить нельзя.

## 2. Facebook Page + привязка

Создай Facebook Page (facebook.com/pages/create), затем привяжи к ней
Instagram: Page → Настройки → Связанные аккаунты → Instagram → войти.
Без этой связки Graph API не увидит Instagram-аккаунт.

## 3. Приложение на developers.facebook.com

Создай приложение (тип «Business») и добавь продукты **Instagram Graph API**
и **Facebook Login**. Для своего аккаунта review проходить не нужно —
в режиме разработки токен уже работает.

## 4. Токен в Graph API Explorer

Открой [Graph API Explorer](https://developers.facebook.com/tools/explorer):

1. Выбери своё приложение.
2. В «User or Page» выбери свою Facebook Page.
3. Выдай права:
   - `pages_show_list`
   - `pages_read_engagement`
   - `pages_manage_posts`
   - `instagram_basic`
   - `instagram_content_publish`
4. Нажми **Generate Access Token**, скопируй его.

Такой токен живёт около часа — это нормально, скрипт ниже поменяет его на
долгоживущий.

## 5. Скрипт: проверка прав, account id, долгий токен

```bash
python -m backend.scripts.instagram_setup --token EAA...

# с обменом на 60-дневный токен (app id/secret — Настройки → Основное):
python -m backend.scripts.instagram_setup --token EAA... \
    --app-id 1234567890 --app-secret abcdef...
```

Скрипт проверит, что все права выданы, найдёт Page с привязанным Instagram,
достанет `instagram_business_account.id` и напечатает готовые строки для
`.env`. Если какого-то права нет — он назовёт его, вернись к шагу 4.

Предпочитается **Page-токен**, а не пользовательский: он не отваливается
вместе с сессией человека.

## 6. Вписать в .env

```
INSTAGRAM_ACCESS_TOKEN=<из вывода скрипта>
INSTAGRAM_ACCOUNT_ID=<из вывода скрипта>
```

Те же значения можно вбить в интерфейсе на странице Настройки — там есть
кнопка проверки ключей.

## Частые ошибки

| Сообщение | Причина |
|---|---|
| `Ни к одной Page не привязан Instagram` | шаг 2 не сделан, либо аккаунт остался личным |
| `(#10) requires instagram_content_publish` | право не выдано, перевыпусти токен (шаг 4) |
| `Session has expired` | истёк часовой токен — обменяй на долгий (шаг 5) |
| `Media upload failed` | `image_url` должен быть публичным HTTPS-URL, JPEG |

Даже 60-дневный токен когда-то истекает — раз в пару месяцев прогоняй шаг 5
заново. Альтернатива без ручных токенов — Ayrshare
(`backend/publishers/ayrshare_pub.py`), там OAuth держит сервис.
