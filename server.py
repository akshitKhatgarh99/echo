import sqlite3
import aiosqlite
import openai
from telegram.request import HTTPXRequest
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CallbackContext, ContextTypes, MessageHandler, filters, ConversationHandler, CommandHandler
from logging.handlers import RotatingFileHandler
import logging
from datetime import datetime, timezone
from io import BytesIO
from google.oauth2.service_account import Credentials
from google.cloud import texttospeech
import asyncio
import json
import os
#import boto3
import threading
import time
# SQLite Setup
conn = sqlite3.connect('users.db')
cursor = conn.cursor()
cursor.execute("CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, phone_number TEXT, state TEXT)")
conn.commit()
conn.close()

#google TTS

credentials = Credentials.from_service_account_file("credentials.json")
client = texttospeech.TextToSpeechClient(credentials=credentials)



async def synthesize_speech_async(input_text):
    voice = texttospeech.VoiceSelectionParams(
            language_code="en-IN",
            name="en-IN-Neural2-A"
        )
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.LINEAR16,
        effects_profile_id=["small-bluetooth-speaker-class-device"],
        pitch=0,
        speaking_rate=1
    )

    loop = asyncio.get_running_loop()
    request = texttospeech.SynthesizeSpeechRequest(
        input=input_text,
        voice=voice,
        audio_config=audio_config
    )
    return await loop.run_in_executor(
        None,
        client.synthesize_speech,
        request
    )

# SQLite Setup
conn = sqlite3.connect('data.db')
cursor = conn.cursor()

cursor.execute('''
CREATE TABLE IF NOT EXISTS chat_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT,
    timestamp TEXT,
    is_from_user BOOLEAN,
    is_audio BOOLEAN,
    message TEXT,
    audio_blob BLOB
);
''')

conn.commit()
conn.close()

# Logging Setup
log_handler = RotatingFileHandler('your_log_file.log', maxBytes=1e6, backupCount=3)
log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log_handler.setFormatter(log_formatter)

logger = logging.getLogger()
logger.addHandler(log_handler)
logger.setLevel(logging.INFO)   

# openai settings


openai.organization = "org-qCbrL6UwKFX7ZxBi7EkU5ziS"
openai.api_key = "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"



# # Initialize S3 client
# s3 = boto3.client('s3', aws_access_key_id='YOUR_ACCESS_KEY',
#                   aws_secret_access_key='YOUR_SECRET_KEY',
#                   region_name='YOUR_REGION')

# def upload_to_s3():
#     while True:
#         file_size = os.path.getsize('data.db')
        
#         if file_size >= 100 * 1024 * 1024:  # Check if file size >= 100MB
#             try:
#                 # Upload to S3
#                 s3.upload_file('data.db', 'your-bucket-name', 'data.db')
#                 logging.info("Successfully uploaded data.db to S3.")
#             except Exception as e:
#                 logging.error(f"Failed to upload data.db to S3: {e}")

#         # Wait for 1 hour before the next upload
#         time.sleep(3600)

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
    user_id = update.message.from_user.id
    timestamp = datetime.now(timezone.utc).isoformat()
    user_text = ""
    if 'last_10_turns' not in context.user_data:
        context.user_data['last_10_turns'] = []

    # Handle text message
    if update.message.text:
        user_text = update.message.text



        # Update user data for sent message
        context.user_data['last_10_turns'].append({
            'timestamp': timestamp,
            'is_from_user': False,
            'is_audio': True,
            'message': None,
            'audio_blob': response_prompt
        })
        
        

    # Handle audio message
    elif update.message.voice:
        voice_file_id = update.message.voice.file_id
        file_info = await context.bot.get_file(update.message.voice.file_id)

        url = file_info.file_path
        request = context.bot_data.get('request')
        # Download the actual audio file
        audio_data = await request.retrieve(url)
        audio_file = BytesIO(audio_data)
        audio_file.name = "audio.mp3"

        transcript_response = await openai.Audio.atranscribe("whisper-1", audio_file ,language = 'hi')
        transcript_text = transcript_response['text']

        # Reply with transcribed text

    # Update user data for received message
    context.user_data['last_10_turns'].append({
        'timestamp': timestamp,
        'is_from_user': True,
        'is_audio': False,
        'message': user_text,
        'audio_blob': None
    })

    # Call OpenAI with the entire history
    response = ""
    buffer = []
    buffer_size = 70
    message_history_object = [{'role': 'system', 'content': 'You are a helpful assistant.'}]
    message_history_object.extend([{'role': 'user', 'content': word} for word in words])
    
    async with openai.completions.create(
        model='gpt-3.5-turbo',
        messages=message_history_object,
        temperature=0.5,
        stream=True
    ) as response:
        async for chunk in response:
            if 'content' in chunk['choices'][0]['message']:
                content = chunk['choices'][0]['message']['content']
                buffer.append(content)
                if len(buffer) >= buffer_size:
                    message = "".join(buffer)
                    logger.info(f"Sending reply: {message}")
                    await update.message.reply_text(message)
                    buffer = []
                combine_conver_update.append(content)
    
    response += "".join(buffer)









    #await update.message.reply_text(transcript_text)


    input_text = texttospeech.SynthesisInput(text=transcript_text)
    
    response = await synthesize_speech_async(input_text)
    
    # Reply with the audio
    await update.message.reply_voice(voice=response.audio_content)
    
    # Update user data for sent message
    context.user_data['last_10_turns'].append({
        'timestamp': timestamp,
        'is_from_user': False,
        'is_audio': True,
        'message': None,
        'audio_blob': response.audio_content
    })
    
    # Update user data for received message
    context.user_data['last_10_turns'].append({
        'timestamp': timestamp,
        'is_from_user': True,
        'is_audio': False,
        'message': transcript_text,
        'audio_blob': None
    })

    # Keep only the last 10 turns


    if len(context.user_data['last_10_turns']) >= 20:
        async with aiosqlite.connect('data.db') as db:
            cursor = await db.cursor()
            # Write the first 10 turns to the database.
            for turn in context.user_data['last_10_turns'][:10]:
                await cursor.execute(
                    'INSERT INTO chat_history (user_id, timestamp, is_from_user, is_audio, message, audio_blob) VALUES (?, ?, ?, ?, ?, ?)',
                    (user_id, turn['timestamp'], turn['is_from_user'], turn['is_audio'], turn['message'], turn['audio_blob'])
                )
            await db.commit()
        # Keep the last 10 turns in the buffer.
        context.user_data['last_10_turns'] = context.user_data['last_10_turns'][10:]

    return CHAT

async def cancel(update: Update, context: CallbackContext) -> int:
    await update.message.reply_text('Goodbye!')
    return ConversationHandler.END

def main():
    request = HTTPXRequest(connection_pool_size=5, read_timeout=10)

    application = Application.builder().token("6352196605:AAFdzmqpYgmn2kM00rNTI_vOrFO08BuVTFg").request(request).build()
    application.bot_data['request'] = request
    any_text_handler = MessageHandler(filters.TEXT & ~filters.COMMAND, start) 
    any_voice_handler = MessageHandler(filters.VOICE, start)  # Add this line

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start), any_text_handler,any_voice_handler],
        states={
            REQUEST_CONTACT: [MessageHandler(filters.CONTACT, handle_contact)],
            CHAT: [MessageHandler(filters.TEXT | filters.COMMAND | filters.VOICE , chat)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    application.add_handler(conv_handler)
    application.run_polling(allowed_updates=Update.ALL_TYPES)
    # s3_thread = threading.Thread(target=upload_to_s3, daemon=True)
    # s3_thread.start()

if __name__ == '__main__':
    main()
