import os
import re
import time
import json
import requests
import cloudscraper
from datetime import datetime, timedelta

# === НАСТРОЙКИ ===
HIDENCLOUD = os.environ.get("HIDENCLOUD")
SERVER_ID = os.environ.get("SERVER_ID")  # Берём ID сервера из секрета (опционально)
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID")
PROXY = os.environ.get("PROXY_NODE")  # Прокси (если есть)

# === ФУНКЦИИ ОТПРАВКИ УВЕДОМЛЕНИЙ ===
def send_telegram(message):
    if TG_BOT_TOKEN and TG_CHAT_ID:
        url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
        try:
            requests.post(url, json={"chat_id": TG_CHAT_ID, "text": message}, timeout=10)
        except:
            pass

def log(msg, status="info"):
    """Выводит цветной лог в консоль и отправляет в Telegram (только ошибки и успех)"""
    print(msg)
    if status in ("error", "success"):
        send_telegram(msg)

# === ПРОВЕРКА ДАННЫХ ===
if not HIDENCLOUD:
    log("❌ Ошибка: не задан секрет HIDENCLOUD (email-----пароль)", "error")
    exit(1)

if "-----" not in HIDENCLOUD:
    log("❌ Ошибка: в HIDENCLOUD нет пяти дефисов -----. Формат: email-----password", "error")
    exit(1)

email, password = HIDENCLOUD.split("-----", 1)
log(f"🔐 Пользователь: {email}")

# === ИНИЦИАЛИЗАЦИЯ SCRAPER С ПРОКСИ ===
scraper = cloudscraper.create_scraper()
if PROXY:
    scraper.proxies = {"http": PROXY, "https": PROXY}
    log(f"🌐 Используется прокси: {PROXY}")

# === АВТОРИЗАЦИЯ НА ПАНЕЛИ ===
log("🟡 Выполняется вход в панель управления...")
login_url = "https://freepanel.hidencloud.com/auth/login"
session = requests.Session()
if PROXY:
    session.proxies = {"http": PROXY, "https": PROXY}

# Получаем CSRF-токен
try:
    r = session.get(login_url, timeout=30)
    if r.status_code != 200:
        log(f"❌ Не удалось загрузить страницу входа. HTTP {r.status_code}", "error")
        exit(1)
    match = re.search(r'name="_token" value="([^"]+)"', r.text)
    if not match:
        log("❌ Не найден CSRF-токен. Возможно, сайт изменил форму.", "error")
        exit(1)
    csrf = match.group(1)
except Exception as e:
    log(f"❌ Ошибка при получении CSRF: {e}", "error")
    exit(1)

# Отправляем логин
payload = {
    "_token": csrf,
    "email": email,
    "password": password
}
try:
    resp = session.post(login_url, data=payload, timeout=30)
    if "dashboard" not in resp.url:
        log("❌ Не удалось войти. Неверный email или пароль.", "error")
        exit(1)
    log("✅ Вход выполнен успешно!")
except Exception as e:
    log(f"❌ Ошибка входа: {e}", "error")
    exit(1)

# === ПОЛУЧЕНИЕ СПИСКА СЕРВЕРОВ ===
log("🟡 Получаем список серверов...")
servers_url = "https://freepanel.hidencloud.com/api/client/servers"
try:
    resp = session.get(servers_url, timeout=30)
    data = resp.json()
    servers = data.get("data", [])
    if not servers:
        log("❌ У вас нет ни одного сервера. Возможно, он был удалён.", "error")
        exit(1)
    log(f"📋 Найдено серверов: {len(servers)}")
except Exception as e:
    log(f"❌ Ошибка получения списка серверов: {e}", "error")
    exit(1)

# === ВЫБОР СЕРВЕРА ПО ID ИЛИ АВТОМАТИЧЕСКИ ===
target_server = None
if SERVER_ID:
    log(f"🔍 Ищем сервер с ID: {SERVER_ID}")
    for s in servers:
        if s.get("identifier") == SERVER_ID:
            target_server = s
            break
    if not target_server:
        log(f"❌ Сервер с ID {SERVER_ID} не найден. Проверьте правильность ID.", "error")
        exit(1)
else:
    log("🟡 SERVER_ID не задан, берём первый сервер из списка.")
    target_server = servers[0]

server_id = target_server["identifier"]
server_name = target_server.get("name", "Без имени")
log(f"✅ Выбран сервер: {server_name} (ID: {server_id})")

# === ПРОДЛЕНИЕ СЕРВЕРА ===
log("🟡 Пытаемся продлить сервер...")
renew_url = f"https://freepanel.hidencloud.com/api/client/servers/{server_id}/renew"
try:
    resp = session.post(renew_url, timeout=30)
    if resp.status_code == 200:
        result = resp.json()
        if result.get("success"):
            # Парсим новую дату истечения (если есть)
            new_expiry = result.get("expiry", "неизвестно")
            log(f"✅ Сервер успешно продлён! Новая дата: {new_expiry}", "success")
        else:
            error_msg = result.get("message", "Неизвестная ошибка")
            log(f"❌ Ошибка продления: {error_msg}", "error")
            exit(1)
    elif resp.status_code == 403:
        log("❌ Доступ запрещён (403). Возможно, сервер уже удалён или закончился срок бесплатного продления.", "error")
        exit(1)
    else:
        log(f"❌ Неожиданный ответ {resp.status_code}: {resp.text}", "error")
        exit(1)
except Exception as e:
    log(f"❌ Исключение при продлении: {e}", "error")
    exit(1)

log("🏁 Скрипт завершён.")
