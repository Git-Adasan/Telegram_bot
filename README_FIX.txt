Исправленная версия Adasan Telegram bot

1. Распакуйте архив в папку проекта.
2. Создайте файл .env рядом с main.py (имя строго .env, не .env.txt).
   Можно скопировать .env.example и переименовать копию в .env.
3. Заполните BOT_TOKEN, API_ID и API_HASH своими значениями.
   Так как прежний BOT_TOKEN был опубликован, сначала отзовите его через @BotFather (/revoke)
   и вставьте новый токен в .env.
4. Установите зависимости в PowerShell из папки проекта:
   py -m pip install -r requirements.txt
5. Запустите:
   py main.py

В main.py для команды /update_books Telethon-клиент создаётся с lang_code="ru"
и system_lang_code="ru-RU". Файл update_session.session намеренно не включён:
при первом запуске /update_books Telethon может попросить авторизацию и создать новую сессию.
Не передавайте никому файл .env или *.session.
