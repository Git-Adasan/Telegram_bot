"""Совместимость: вход по коду с возможностью запросить звонок/SMS (команда r).
Старая версия сразу делала повторную отправку и сбивала доставку кода — теперь это по запросу."""
import asyncio

import create_telethon_string as t

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", action="store_true", default=True)
    ap.add_argument("--code", action="store_true", default=True)
    asyncio.run(t.main(ap.parse_args([])))
