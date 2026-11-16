"""
Вход Telethon в ваш личный аккаунт (для /update_books).

    python create_telethon_string.py            # QR-вход (рекомендуется, код не нужен)
    python create_telethon_string.py --code     # вход по коду из Telegram/SMS
    python create_telethon_string.py --file     # сохранить как update_session.session, а не строкой

Нужны API_ID и API_HASH в .env рядом со скриптом. Для QR в терминале: pip install qrcode
Результат (строка сессии) — секрет: даёт полный доступ к аккаунту. Никому не отправляйте.
В Render добавьте её как TELETHON_SESSION_STRING.

Почему «не приходит код»:
  * Если Telegram уже открыт на другом вашем устройстве, код приходит НЕ по SMS, а
    сообщением в чат «Telegram» (аккаунт 777000) в этом приложении.
  * SMS/звонок включаются только позже (кнопка повторной отправки, ~60+ секунд).
  * Частые запросы приводят к FloodWait — нужно просто подождать указанное время.
  * Вход с VPN/дата-центра Telegram часто блокирует. QR-вход эту проблему обходит.
"""
import argparse
import asyncio
import getpass
import os
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient, errors
from telethon.sessions import StringSession
from telethon.tl.functions.auth import ResendCodeRequest

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env", override=True)

SESSION_FILE = str(BASE_DIR / "update_session")

TYPE_HINTS = {
    "SentCodeTypeApp": "код отправлен СООБЩЕНИЕМ в приложение Telegram (чат «Telegram») на другом вашем устройстве",
    "SentCodeTypeSms": "код отправлен по SMS",
    "SentCodeTypeCall": "код продиктуют голосом по телефонному звонку",
    "SentCodeTypeFlashCall": "код — последние цифры номера, который позвонит",
    "SentCodeTypeMissedCall": "код — последние цифры номера пропущенного звонка",
    "SentCodeTypeEmailCode": "код отправлен на email, привязанный к аккаунту",
}


def get_api_credentials():
    api_id_raw = os.getenv("API_ID", "").strip()
    api_hash = os.getenv("API_HASH", "").strip()
    if not api_id_raw or not api_hash:
        raise RuntimeError("В .env не найдены API_ID или API_HASH.")
    try:
        return int(api_id_raw), api_hash
    except ValueError as exc:
        raise RuntimeError("API_ID должен быть числом.") from exc


def describe(sent) -> str:
    name = type(sent.type).__name__
    return TYPE_HINTS.get(name, name)


async def ask_2fa(client):
    for _ in range(3):
        password = getpass.getpass("Включена двухэтапная проверка. Введите пароль 2FA: ")
        try:
            await client.sign_in(password=password)
            return
        except errors.PasswordHashInvalidError:
            print("Неверный пароль 2FA, попробуйте ещё раз.")
    raise RuntimeError("Пароль 2FA введён неверно 3 раза.")


async def login_qr(client):
    try:
        import qrcode
    except ImportError:
        qrcode = None
        print("Подсказка: pip install qrcode — тогда QR нарисуется прямо в терминале.")

    qr = await client.qr_login()
    print("\nОткройте Telegram на телефоне → Настройки → Устройства → Подключить устройство")
    print("и наведите камеру на QR. Ждём до ~3 минут.\n")
    for _ in range(6):
        if qrcode:
            code = qrcode.QRCode(border=1)
            code.add_data(qr.url)
            code.print_ascii(invert=True)
        else:
            print("Ссылка для QR-генератора:", qr.url)
        try:
            await qr.wait(timeout=30)
            return
        except asyncio.TimeoutError:
            await qr.recreate()   # токен QR живёт ~30 с — обновляем
        except errors.SessionPasswordNeededError:
            await ask_2fa(client)
            return
    raise RuntimeError("QR не был отсканирован вовремя. Запустите скрипт снова.")


async def login_code(client):
    phone = input("Номер телефона в международном формате (+7...): ").strip().replace(" ", "")
    if not phone:
        raise RuntimeError("Номер телефона не введён.")
    try:
        sent = await client.send_code_request(phone)
    except errors.PhoneNumberInvalidError:
        raise RuntimeError("Telegram не принял номер. Формат: +77001234567.")
    except errors.FloodWaitError as exc:
        raise RuntimeError(f"Слишком много запросов кода. Подождите {exc.seconds} сек. и повторите.")

    print(f"\nСпособ доставки: {describe(sent)}.")
    print("Код придёт в течение минуты. Не пересылайте код никому и не вставляйте его в чаты —")
    print("Telegram аннулирует код, если он был отправлен через сам Telegram.\n")

    while True:
        raw = input("Введите код (или r — запросить другой способ, q — выход): ").strip().replace(" ", "")
        if raw.lower() == "q":
            raise RuntimeError("Отменено.")
        if raw.lower() == "r":
            try:
                sent = await client(ResendCodeRequest(phone_number=phone, phone_code_hash=sent.phone_code_hash))
                print(f"Способ доставки: {describe(sent)}.")
            except errors.FloodWaitError as exc:
                print(f"Подождите {exc.seconds} сек. перед повторной отправкой.")
            except Exception as exc:
                print("Повторная отправка недоступна:", exc)
            continue
        try:
            await client.sign_in(phone=phone, code=raw, phone_code_hash=sent.phone_code_hash)
            return
        except errors.SessionPasswordNeededError:
            await ask_2fa(client)
            return
        except errors.PhoneCodeInvalidError:
            print("Неверный код, попробуйте ещё раз.")
        except errors.PhoneCodeExpiredError:
            print("Код истёк. Запрашиваю новый.")
            sent = await client.send_code_request(phone)
            print(f"Способ доставки: {describe(sent)}.")


async def main(args):
    api_id, api_hash = get_api_credentials()
    session = SESSION_FILE if args.file else StringSession()
    client = TelegramClient(session, api_id, api_hash, lang_code="ru", system_lang_code="ru-RU")
    await client.connect()
    try:
        if not await client.is_user_authorized():
            if args.code:
                await login_code(client)
            else:
                await login_qr(client)

        me = await client.get_me()
        print(f"\n✅ Авторизация успешна: {me.first_name or ''} (ID: {me.id})")
        if args.file:
            print(f"Сессия сохранена в {SESSION_FILE}.session (не публикуйте и не добавляйте в git).")
        else:
            print("\nСкопируйте строку ниже целиком в TELETHON_SESSION_STRING (Render → Environment или .env):\n")
            print(client.session.save())
            print("\nВАЖНО: это секрет с полным доступом к аккаунту. Никому не отправляйте.")
    finally:
        await client.disconnect()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--code", action="store_true", help="вход по коду вместо QR")
    ap.add_argument("--file", action="store_true", help="сохранить update_session.session вместо строки")
    asyncio.run(main(ap.parse_args()))
