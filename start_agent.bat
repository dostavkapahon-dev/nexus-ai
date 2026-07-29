@echo off
REM ============================================================
REM  PAKHON STUDIO — браузерный агент NEXUS AI (запуск в 1 клик)
REM  Скачайте этот файл, положите рядом desktop_agent.py,
REM  затем дважды кликните по нему.
REM ============================================================
setlocal
cd /d "%~dp0"

set SERVER=https://nexus-ai-emog.onrender.com
set TOKEN=pakhon2026

echo.
echo === PAKHON STUDIO — запуск браузерного агента ===
echo Server: %SERVER%
echo.

REM 1. Проверка Python
py --version >nul 2>&1
if errorlevel 1 (
  echo [ОШИБКА] Python не найден.
  echo Установите Python с https://python.org/downloads
  echo и при установке отметьте "Add Python to PATH".
  pause
  exit /b 1
)

REM 2. Скачать desktop_agent.py, если его нет рядом
if not exist desktop_agent.py (
  echo Скачиваю desktop_agent.py ...
  curl.exe -L -o desktop_agent.py https://raw.githubusercontent.com/dostavkapahon-dev/nexus-ai/master/desktop_agent.py
)

REM 3. Установить зависимости (быстро, если уже стоят)
echo Проверяю зависимости...
py -m pip install --upgrade pip
py -m pip install websockets playwright
if errorlevel 1 (
  echo.
  echo [ОШИБКА] Не удалось установить websockets/playwright.
  echo Смотри текст ошибки выше. Частые причины:
  echo   - нет интернета / блокирует антивирус или прокси
  echo   - нужен запуск от имени администратора
  echo Попробуй вручную:  py -m pip install websockets playwright
  pause
  exit /b 1
)
py -m playwright install chromium
if errorlevel 1 (
  echo.
  echo [ПРЕДУПРЕЖДЕНИЕ] Chromium не скачался — попробую системный Chrome/Edge.
)

REM 4. Запуск агента
echo.
echo === Запускаю агента. Откроется окно браузера ===
echo В нём войдите в Instagram (один раз). Не закрывайте это окно.
echo.
py desktop_agent.py --server %SERVER% --token %TOKEN%

pause
