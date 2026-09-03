# ARCHIE / AYRSHARE DEPENDENCIES

## Итог: зависимость УДАЛЕНА ✅

«Archie» в задаче = **Ayrshare** — сторонний платный сервис-посредник, через который
раньше шли и публикация, и аналитика соцсетей. От того, работает ли их сервис,
зависела вся система.

## Проверка (grep по репозиторию, без `node_modules` и `dist`)

Найдено 4 совпадения — **все в комментариях**, исполняемого кода нет:

| Файл | Строки | Что там |
|---|---|---|
| `backend/core/social_intel.py` | 2, 4, 15, 257 | docstring: «замена платного посредника Ayrshare», «интерфейс совместим со старым `ayrshare_pub`» |

Модуль `backend/publishers/ayrshare_pub.py` **удалён**.
Переменная `AYRSHARE_API_KEY` удалена из `.env.example`, `render.yaml` и UI.

## Где использовался и чем заменён

| Функция Ayrshare | Было | Стало |
|---|---|---|
| Публикация Instagram | `publish_ayrshare(["instagram"])` | `publishers/instagram_pub.py` (Graph API) + браузерный фолбэк |
| Публикация TikTok / YouTube / Threads / X | один REST-вызов | `publishers/*.py` нативные API + браузер |
| Аналитика профиля | `get_profile_analytics` | `core/instagram_reader.py`, `core/youtube_reader.py`, `core/social_intel.py` |
| Досье аккаунта | `get_account_intelligence` | `core/social_intel.get_account_intelligence` (интерфейс сохранён) |
| История постов | `get_recent_posts` | `core/social_intel.get_recent_posts` |
| Аналитика поста | `get_post_analytics` | `core/viral_research.fetch_meta` / `browser_reader.analyze_post` |
| OAuth-связь с соцсетями | держал Ayrshare | ⚪ **не реализовано** — токены вводятся руками (см. `SOCIAL_CONNECTORS.md`) |

## Что мы потеряли вместе с Ayrshare (честно)
1. **Готовый OAuth** — Ayrshare держал связь с соцсетями за нас. Теперь нужен свой
   OAuth-флоу либо ручной ввод токенов. Это главный оставшийся долг.
2. **Единый формат ответа** по всем площадкам — теперь у каждого коннектора свой.
3. **Обход ревью Meta** — их приложение было уже одобрено; нам нужно своё Meta App.

## Что мы выиграли
- Нет зависимости от доступности и тарифов стороннего сервиса.
- Нет платы; работает на бесплатных путях (официальные API + браузер).
- Полный контроль над данными — ничего не уходит третьей стороне.

## Осталось сделать
- [ ] Убрать 4 устаревших упоминания из комментариев `social_intel.py` (косметика).
- [ ] Реализовать OAuth-флоу вместо ручного ввода токенов (см. `TODO.md`, блок 5).
