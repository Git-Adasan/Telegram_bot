# Adasan Library — Premium TOP-5 statistics

The `/popular` command now creates a Premium dark-blue PNG leaderboard with up to five books, rank numbers, cover images, per-book open counts, and the all-time total.

## What it uses

- Python + Pillow for drawing the image.
- Existing SQLite table `book_stats` for all-time open counts.
- Existing `books_db.json` entries and their `photo_message_id` values to locate real cover-photo posts in `@library_adasan`.
- Telethon (already present in this project) to cache those Telegram photos locally in `covers/cache/`.
- Aiogram to send the resulting PNG in Telegram.

No AI API, image-generation API, or paid image service is used.

## Install and run

From the project directory:

```bash
py -m pip install -r requirements.txt
py main.py
```

Then send `/popular` to the bot.

## Real cover photos

For automatic cover caching, the bot process needs an already-authorized Telethon session. Configure either:

- `TELETHON_SESSION_STRING`, or
- `TELETHON_SESSION_PATH` pointing to an existing authorized `.session` file.

`API_ID` and `API_HASH` must also be configured, as they already are for the existing `/update_books` workflow. The bot caches downloaded cover photos under `covers/cache/`, so it does not fetch them again on every `/popular` request. If no authorized session is available, the image still renders and uses a clearly marked `NO COVER` placeholder; it does not pretend a subject icon is a book cover.

Keep `.env` and `*.session` private. They are intentionally not included in the update archive. When applying this update to your existing project, do not delete your own `.env`, database, or Telethon session.

## Important statistics detail

The existing `book_stats.opens` counter is incremented when a user opens a book card in the bot. It does **not** measure whether the user subsequently downloads the file from the external Telegram link. For that reason, the image labels these figures as **открытий** (opens), not downloads. Actual download tracking would require a separate tracked redirect or an in-bot download flow.
