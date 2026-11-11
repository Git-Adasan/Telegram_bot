"""Совместимость: создаёт файл update_session.session (вход по QR). См. create_telethon_string.py"""
import argparse
import asyncio

import create_telethon_string as t

if __name__ == "__main__":
    asyncio.run(t.main(argparse.Namespace(code=False, file=True)))
