import aiosqlite
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, CallbackContext

import sqlite3

conn = sqlite3.connect('users.db')
cursor = conn.cursor()
cursor.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY)")
conn.commit()
conn.close()

async def check_and_insert_user(user_id, update):
    async with aiosqlite.connect('users.db') as db:
        async with db.execute("SELECT * FROM users WHERE id=?", (user_id,)) as cursor:
            if await cursor.fetchone() is None:
                await update.message.reply_text('Bot started. Type any message and I will echo back.')
                await db.execute("INSERT INTO users (id) VALUES (?)", (user_id,))
                await db.commit()

async def echo(update: Update, _: CallbackContext) -> None:
    user_id = update.message.from_user.id
    await check_and_insert_user(user_id, update)
    await update.message.reply_text(update.message.text)

def main():

    application = Application.builder().token("6352196605:AAFdzmqpYgmn2kM00rNTI_vOrFO08BuVTFg").build()

    echo_handler = MessageHandler(filters.TEXT & ~filters.COMMAND, echo)
    application.add_handler(echo_handler)

    application.run_polling()

if __name__ == '__main__':
    main()
