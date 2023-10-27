import sqlite3
import aiosqlite
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CallbackContext, ContextTypes, MessageHandler, filters, ConversationHandler, CommandHandler
from logging.handlers import RotatingFileHandler
import logging

# SQLite Setup
conn = sqlite3.connect('users.db')
cursor = conn.cursor()
cursor.execute("CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, phone_number TEXT, state TEXT)")
conn.commit()
conn.close()

# Logging Setup
log_handler = RotatingFileHandler('your_log_file.log', maxBytes=1e6, backupCount=3)
log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log_handler.setFormatter(log_formatter)

logger = logging.getLogger()
logger.addHandler(log_handler)
logger.setLevel(logging.INFO)

# Define states
REQUEST_CONTACT, CHAT = range(2)


async def start(update: Update, context: CallbackContext) -> int:
    user_id = update.message.from_user.id
    async with aiosqlite.connect('users.db') as db:
        async with db.execute("SELECT * FROM users WHERE id=?", (user_id,)) as cursor:
            user = await cursor.fetchone()
            if user is None:
                # New user
                keyboard = [[
                    KeyboardButton("Share Contact", request_contact=True)
                ]]
                markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
                await update.message.reply_text('Please share your contact to proceed.', reply_markup=markup)
                await db.execute("INSERT INTO users (id, state) VALUES (?, ?)", (user_id, 'REQUEST_CONTACT'))
                await db.commit()
                return REQUEST_CONTACT
            else:
                # Existing user
                await update.message.reply_text('Welcome back.')
                state = user[2]  # get the state from database
                if state == 'REQUEST_CONTACT':
                    return REQUEST_CONTACT
                else:
                    return CHAT

async def handle_contact(update: Update, context: CallbackContext) -> int:
    user_id = update.message.from_user.id
    phone_number = update.message.contact.phone_number
    async with aiosqlite.connect('users.db') as db:
        await db.execute("UPDATE users SET phone_number = ?, state = ? WHERE id = ?", (phone_number, 'CHAT', user_id))
        await db.commit()
    await update.message.reply_text(f'Saved your phone number: {phone_number}')
    return CHAT

async def chat(update: Update, context: CallbackContext) -> int:
    if update.message.text:
        await update.message.reply_text(update.message.text)
    elif update.message.voice:
        voice_file_id = update.message.voice.file_id
        await update.message.reply_voice(voice_file_id)
    return CHAT


async def cancel(update: Update, context: CallbackContext) -> int:
    await update.message.reply_text('Goodbye!')
    return ConversationHandler.END

def main():
    application = Application.builder().token("6352196605:AAFdzmqpYgmn2kM00rNTI_vOrFO08BuVTFg").build()
    any_text_handler = MessageHandler(filters.TEXT & ~filters.COMMAND, start) 
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start), any_text_handler],
        states={
            REQUEST_CONTACT: [MessageHandler(filters.CONTACT, handle_contact)],
            CHAT: [MessageHandler(filters.TEXT | filters.COMMAND | filters.VOICE , chat)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    application.add_handler(conv_handler)
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
