import asyncio
from telethon import TelegramClient
from telethon.tl.functions.auth import ResendCodeRequest

from dotenv import load_dotenv
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"), override=True)
API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]

async def main():
    client = TelegramClient("update_session", API_ID, API_HASH)
    await client.connect()

    phone = input("Введите номер телефона (с +7...): ").strip()

    sent = await client.send_code_request(phone)
    print(f"Код отправлен способом: {sent.type}")

    # Запрашиваем повторную отправку — обычно следующий способ это звонок
    sent = await client(ResendCodeRequest(
        phone_number=phone,
        phone_code_hash=sent.phone_code_hash
    ))
    print(f"Повторная отправка способом: {sent.type}")
    print("Если не позвонили за 1-2 минуты, подожди ещё немного.")

    code = input("Введите код, который получили: ").strip()

    try:
        await client.sign_in(phone=phone, code=code, phone_code_hash=sent.phone_code_hash)
    except Exception as e:
        print("Ошибка входа:", e)
        await client.disconnect()
        return

    me = await client.get_me()
    print("✅ Сессия создана:", me)
    await client.disconnect()

asyncio.run(main())
