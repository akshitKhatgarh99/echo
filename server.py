import sqlite3
import aiosqlite
from openai import AsyncOpenAI
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
import requests
# SQLite Setup
conn = sqlite3.connect('users.db')
cursor = conn.cursor()
cursor.execute("CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, phone_number TEXT, state TEXT)")
conn.commit()
conn.close()

# SQLite inmemory database for chat questions that have been asked
import random

# Create a connection to an in-memory database
# On application start
def backup_database(in_mem_conn, backup_file):
    # Connect to a database file
    file_conn = sqlite3.connect(backup_file)
    # Use the backup API
    with file_conn:
        in_mem_conn.backup(file_conn)
    file_conn.close()


def restore_database(backup_file):
    file_conn = sqlite3.connect(backup_file)
    mem_conn = sqlite3.connect(':memory:')
    with mem_conn:
        file_conn.backup(mem_conn)
    file_conn.close()
    return mem_conn



def periodic_backup(conn, interval, backup_file):
    while True:
        time.sleep(interval)  # Wait for the specified interval (in seconds)
        backup_database(conn, backup_file)  # Call your backup function


backup_file = 'inmembackup.db'
try:
    conn_mem = restore_database(backup_file)
except FileNotFoundError:
    # No backup found, start with a fresh database
    conn_mem = sqlite3.connect(':memory:')
    # Initialize your database tables here

# Periodically during application runtime
backup_database(conn_mem, backup_file)

# Use conn_mem as usual for your database operations

cursor = conn_mem.cursor()

# Create table for all questions
cursor.execute('''
CREATE TABLE all_questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question_string TEXT
);
''')

# Create table to track asked questions
cursor.execute('''
CREATE TABLE asked_questions (
    user_id TEXT,
    question_id INTEGER,
    FOREIGN KEY(question_id) REFERENCES all_questions(id)
);
''')


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

conn_mem.commit()



def insert_question(conn, question_string):
    cursor = conn.cursor()
    cursor.execute("INSERT INTO all_questions (question_string) VALUES (?)", (question_string,))
    conn.commit()



# define insert questions here so that we can take all the questions from a json and put them in the database.










def select_unasked_question(conn, user_id):
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, question_string FROM all_questions
        WHERE id NOT IN (
            SELECT question_id FROM asked_questions WHERE user_id = ?
        )
    ''', (user_id,))
    unasked_questions = cursor.fetchall()

    if not unasked_questions:
        return None  # No more unasked questions available

    return random.choice(unasked_questions)


def mark_question_as_asked(conn, user_id, question_id):
    cursor = conn.cursor()
    cursor.execute("INSERT INTO asked_questions (user_id, question_id) VALUES (?, ?)", (user_id, question_id))
    conn.commit()


#google TTS

credentials = Credentials.from_service_account_file("credentials.json")
google_client = texttospeech.TextToSpeechClient(credentials=credentials)



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
        google_client.synthesize_speech,
        request
    )



# Logging Setup
log_handler = RotatingFileHandler('your_log_file.log', maxBytes=1e6, backupCount=3)
log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log_handler.setFormatter(log_formatter)

logger = logging.getLogger()
logger.addHandler(log_handler)
logger.setLevel(logging.INFO)   

# openai settings


client =AsyncOpenAI(api_key="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", organization="org-qCbrL6UwKFX7ZxBi7EkU5ziS")


# openai.organization = "org-qCbrL6UwKFX7ZxBi7EkU5ziS"
# openai.api_key = "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"



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





def get_question(user_id):
    # Get a question that has not been asked yet
    question = select_unasked_question(conn_mem, user_id)
    if question is None:
        # No more questions available, return None
        return None

    # Mark the question as asked
    mark_question_as_asked(conn_mem, user_id, question[0])

    return question[1]  # Return the question string

  


tools = [
    {
        "type": "function",
        "function": {
        "name": "get_question",
        "description": "Get the current weather in a given location",
        "parameters": {
            "type": "object",
            "properties": {
            "location": {
                "type": "string",
                "description": "The city and state, e.g. San Francisco, CA",
            },
            "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]},
            },
            "required": ["location"],
        },
        }
    }
    ]




async def handle_stream(client, message_history_object, tools,update: Update, context: CallbackContext):

    timestamp = datetime.now(timezone.utc).isoformat()
    buffer = []
    # we need to fix this buffer size thing. make sure if the final buffer is less than 30 you also give output.
    buffer_size_min = 30  # Minimum buffer size, we'll wait for a sentence ending
    buffer_size = 70  # Maximum buffer size, but we'll also look for natural breakpoints
    #below thing is going to be responsible to make the initial prompt to the chat bot.
    stream = await client.chat.completions.create(
        model='gpt-3.5-turbo',
        messages=message_history_object,
        tools=tools,
        tool_choice="auto",
        temperature=0.5,
        stream=True
    ) 
    async for chunk in stream:
        if  chunk.choices[0].delta.content != None:


            content = chunk.choices[0].delta.content
            buffer.append(content)


            # Check if the buffer has reached the size limit or contains a sentence ending
            if len(buffer)>= buffer_size_min and (len(buffer) >= buffer_size or any(punct in content for punct in ['.', ',',';', '?'])):
                message = "".join(buffer)
                logger.info(f"Sending reply: {message}")
                #await update.message.reply_text(message)
                buffer = []  # Reset buffer after sending message

                bot_response_text = texttospeech.SynthesisInput(text=message)
                
                response = await synthesize_speech_async(bot_response_text)

                
                # Reply with the audio
                await update.message.reply_voice(voice=response.audio_content)
                
                # Update user data for sent message
                context.user_data['last_10_turns'].append({
                    'timestamp': timestamp,
                    'is_from_user': False,
                    'is_audio': True,
                    'message': bot_response_text,
                    'audio_blob': response.audio_content
                })

        
        # the below two if satements have same body just different return values.
                
        if chunk.choices[0].finish_reason == "tool_calls":
            message = "".join(buffer)
            logger.info(f"Sending reply: {message}")
            #await update.message.reply_text(message)
            buffer = []  # Reset buffer after sending message

            bot_response_text = texttospeech.SynthesisInput(text=message)
            
            response = await synthesize_speech_async(bot_response_text)

            
            # Reply with the audio
            await update.message.reply_voice(voice=response.audio_content)
            
            # Update user data for sent message
            context.user_data['last_10_turns'].append({
                'timestamp': timestamp,
                'is_from_user': False,
                'is_audio': True,
                'message': bot_response_text,
                'audio_blob': response.audio_content
            })


            return True
        
        if chunk.choices[0].finish_reason == "stop":
            message = "".join(buffer)
            logger.info(f"Sending reply: {message}")
            #await update.message.reply_text(message)
            buffer = []  # Reset buffer after sending message

            bot_response_text = texttospeech.SynthesisInput(text=message)
            
            response = await synthesize_speech_async(bot_response_text)

            
            # Reply with the audio
            await update.message.reply_voice(voice=response.audio_content)
            
            # Update user data for sent message
            context.user_data['last_10_turns'].append({
                'timestamp': timestamp,
                'is_from_user': False,
                'is_audio': True,
                'message': bot_response_text,
                'audio_blob': response.audio_content
            })

            return False

   


async def chat(update: Update, context: CallbackContext) -> int:
    user_id = update.message.from_user.id
    timestamp = datetime.now(timezone.utc).isoformat()
    user_text = ""
    if 'last_10_turns' not in context.user_data:
        context.user_data['last_10_turns'] = []

    # Handle text message
    if update.message.text:
        user_text = update.message.text

        

    # Handle audio message
    elif update.message.voice:

        file_info = await context.bot.get_file(update.message.voice.file_id)

        url = file_info.file_path
        request = context.bot_data.get('request')
        # Download the actual audio file
        audio_data = await request.retrieve(url)
        audio_file = BytesIO(audio_data)
        audio_file.name = "audio.mp3"

        transcript_response = await client.audio.transcriptions.create(model ="whisper-1",file= audio_file ,language = 'hi')
        transcript_text = transcript_response.text
        print(transcript_text)

        user_text = transcript_text

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
    
    message_history_object = [{'role': 'system', 'content': 'You are a helpful assistant.'}]
    # we need to stuff our question and the history of messages here.

    for i in context.user_data['last_10_turns']:
        if i['is_from_user']:
            message_history_object.append({'role': 'user', 'content': str(i['message'])})
        else:
            message_history_object.append({'role': 'assitant', 'content': str(i['message'])})

    message_history_object.append({'role': 'user', 'content': str(user_text)})

    tool_called=await handle_stream(client, message_history_object, tools,update, context)

    if tool_called:
        # modify this above object to include the tool call.
        question = get_question(update.message.from_user.id)
        if question is not None:
            print("question should be asked, error line 434")
        

        # make sure that we have a smooth flow from one question to another, put that in the main prompt.
    
        new_que_prompt = ""    
        message_history_object.append({'role': 'assitant', 'content': new_que_prompt+ str(question)})


        await handle_stream(client, message_history_object, tools,update, context)
            
                
                

    # Keep only the last 10 turns


    if len(context.user_data['last_10_turns']) >= 20:

        cursor = conn_mem.cursor()
        # Write the first 10 turns to the database.
        for turn in context.user_data['last_10_turns'][:10]:
            cursor.execute(
                'INSERT INTO chat_history (user_id, timestamp, is_from_user, is_audio, message, audio_blob) VALUES (?, ?, ?, ?, ?, ?)',
                (user_id, turn['timestamp'], turn['is_from_user'], turn['is_audio'], turn['message'], turn['audio_blob'])
            )
        conn_mem.commit()
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
    backup_interval = 1000  # Backup every hour (3600 seconds)
    backup_file = 'inmembackup.db'


    # Start the backup thread
    backup_thread = threading.Thread(target=periodic_backup, args=(conn_mem, backup_interval, backup_file), daemon=True)
    backup_thread.start()
    # s3_thread = threading.Thread(target=upload_to_s3, daemon=True)
    # s3_thread.start()

if __name__ == '__main__':
    main()
