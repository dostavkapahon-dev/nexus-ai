# Деплой NEXUS AI на Oracle Cloud Always Free (24/7, бесплатно)

Oracle Always Free даёт настоящую виртуалку с большим объёмом памяти навсегда:
ARM Ampere A1 — **до 24 ГБ RAM и 4 ядра**. Этого с запасом хватает на FastAPI +
Telegram-бот + планировщик + серверный браузер (headless Chromium).

Ниже — весь путь от нуля до работающего сайта.

---

## 1. Создать виртуалку

1. Зарегистрируйся на https://cloud.oracle.com (нужна карта — **списаний нет**,
   это подтверждение личности; выбирай ресурсы с пометкой **Always Free**).
2. Menu → **Compute → Instances → Create instance**.
3. **Image and shape**:
   - Image: **Canonical Ubuntu 22.04** (или 24.04).
   - Shape: **Ampere / VM.Standard.A1.Flex** → поставь **4 OCPU и 24 GB RAM**
     (это всё в пределах Always Free). Если A1 «out of capacity» — попробуй
     другой регион/домен доступности или позже; как временный вариант подойдёт
     `VM.Standard.E2.1.Micro` (AMD, 1 ГБ — браузеру будет тесно).
4. **Add SSH keys**: сохрани приватный ключ (понадобится для входа).
5. **Create**. Через минуту у инстанса появится **Public IP** — запиши его.

## 2. Открыть порт 80 (два места!)

Порт нужно открыть и в облаке, и внутри Ubuntu.

**а) Security List (облако):**
Instance → Virtual Cloud Network → Security Lists → Default → **Add Ingress Rule**:
- Source CIDR: `0.0.0.0/0`
- IP Protocol: **TCP**, Destination Port: **80**

**б) Внутри VM (после входа по SSH, см. шаг 3):**
```bash
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
sudo netfilter-persistent save
```

## 3. Зайти на виртуалку по SSH

```bash
ssh -i /путь/к/приватному_ключу ubuntu@<PUBLIC_IP>
```

## 4. Установить Docker

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu
newgrp docker          # или переподключись по SSH
```

## 5. Забрать код и настроить ключи

```bash
git clone https://github.com/dostavkapahon-dev/nexus-ai.git
cd nexus-ai
cp .env.example .env
nano .env              # впиши свои ключи (см. ниже что обязательно)
```

Минимум для старта:
- `ADMIN_PASSWORD` — пароль входа в дашборд.
- `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` — бот и админ-чат.
- Хотя бы один ИИ-ключ (бесплатно): `GEMINI_API_KEY` или `GROQ_API_KEY` и т.п.
- Для **анализа** аккаунтов: `IG_HANDLE` / `TIKTOK_HANDLE` / `YOUTUBE_HANDLE`
  (Instagram — опц. `BRIGHTDATA_API_KEY`).
- Для **публикации без API**: ничего не нужно — работает серверный браузер.
  Вход в аккаунты см. шаг 7.

## 6. Запустить

```bash
docker compose up -d --build
```
Первая сборка качает Chromium — идёт несколько минут. Проверить:
```bash
docker compose logs -f        # смотреть логи (Ctrl+C для выхода)
docker compose ps             # статус
```
Открой в браузере: **http://<PUBLIC_IP>/** — это дашборд NEXUS AI.

## 7. Вход в соцсети для публикации без API (один раз)

Серверный браузер headless, поэтому логин переносится cookies-файлом:

1. На своём компьютере в обычном браузере войди в Instagram/TikTok/YouTube.
2. Экспортируй cookies в формат Playwright `storage_state` (расширение для
   экспорта cookies в JSON, либо запусти локально `desktop_agent.py` и войди —
   он сохранит профиль в папку `browser_session`).
3. Положи JSON на виртуалку и укажи путь в `.env`:
   ```
   NEXUS_BROWSER_STORAGE_STATE=/data/state.json
   ```
   (скопируй файл в том: `docker cp state.json nexus-ai:/data/state.json`)
4. Перезапусти: `docker compose restart`.

Без этого агент дойдёт до экрана логина и остановится с вопросом (`ask`).

## 8. Обновление после новых коммитов

```bash
cd ~/nexus-ai && git pull && docker compose up -d --build
```

## 9. (Опционально) свой домен и HTTPS

Направь A-запись домена на `<PUBLIC_IP>`, затем поставь Caddy/Nginx как reverse
proxy с автоматическим Let's Encrypt — или подключи Cloudflare (бесплатный SSL).

---

### Память и стабильность
- 24 ГБ RAM с большим запасом покрывают Chromium; инстанс не засыпает — бот и
  автопостинг работают круглосуточно.
- `restart: always` в docker-compose поднимает контейнер после перезагрузки VM.
- Данные (база, логины браузера) лежат в томе `nexus_data` (`/data`) и не
  теряются при пересборке образа.
