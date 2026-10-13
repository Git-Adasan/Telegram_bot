import asyncio
from telethon import TelegramClient

from dotenv import load_dotenv
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"), override=True)
API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]

async def main():
    async with TelegramClient("update_session", API_ID, API_HASH) as client:
        print("✅ Сессия создана:", await client.get_me())

asyncio.run(main())