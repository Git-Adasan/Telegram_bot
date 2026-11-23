"""Настройки и общие объекты: переменные окружения, логирование, бот (bot) и диспетчер (dp)."""

import asyncio
import logging
import os
from aiogram import Bot
from aiogram import Dispatcher
from dotenv import load_dotenv


_LOG_LEVEL = getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO)

logging.basicConfig(
    level=_LOG_LEVEL,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)

_telethon_lock = asyncio.Lock()      # один клиент Telethon за раз (общий файл сессии)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

ENV_PATH = os.path.join(BASE_DIR, ".env")

load_dotenv(ENV_PATH, override=False)

if os.name != "nt":
    os.umask(0o077)

BOT_TOKEN = os.getenv("BOT_TOKEN")

API_ID_RAW = os.getenv("API_ID")

API_HASH = os.getenv("API_HASH")

if not API_ID_RAW or not API_HASH:
    raise RuntimeError(
        f"API_ID или API_HASH не найдены. Проверь файл: {ENV_PATH}. "
        "В нём должны быть строки API_ID=... и API_HASH=... (имя файла именно .env, не .env.txt)."
    )

try:
    API_ID = int(API_ID_RAW.strip())
except ValueError as exc:
    raise RuntimeError("API_ID должен быть числом. Проверь строку API_ID в .env") from exc

# =========================
# ADMIN
# =========================
ADMIN_ID_RAW = os.getenv("ADMIN_ID", "6277436867").strip()

try:
    ADMIN_ID = int(ADMIN_ID_RAW)
    if ADMIN_ID <= 0:
        raise ValueError
except ValueError as exc:
    raise RuntimeError("ADMIN_ID должен быть положительным Telegram ID.") from exc

ADMIN_URL   = "https://t.me/Tg_Adasan"

ADMIN_NAME  = "@Tg_Adasan"

CHANNEL     = "@library_adasan"

# =========================
# БД
# =========================
DB_PATH = os.getenv("DB_PATH") or os.path.join(BASE_DIR, "adasan.db")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не задан!")

bot = Bot(token=BOT_TOKEN)

dp = Dispatcher()
