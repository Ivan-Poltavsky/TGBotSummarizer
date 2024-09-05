import PyPDF2
from telegram import Update
import json
import requests
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext, ContextTypes
import sqlite3
import time
from langchain.text_splitter import RecursiveCharacterTextSplitter
import uuid


TELEGRAM_API_KEY = '7509563109:AAGV120-wsJsTVfXeSYSX-GPRFPTpN8AHHM'

MAX_MESSAGE_LENGTH = 4096

URL = 'https://llm.api.cloud.yandex.net/foundationModels/v1/completion'
YANDEX_API_KEY = 'AQVNzLPkZh1celYQt47GmTiYPuaJk8jiAIx287nU'

AVAILABLE_COMMANDS = [
    "start",
    "help",
    "stop",
    'get_summary'
]

def text_from_pdf(pdf_path):
    with open(pdf_path, 'rb') as pdf_file:
        text = ''
        reader = PyPDF2.PdfReader(pdf_file)
        for page in reader.pages:
            text += ' ' + page.extract_text()
    return text

def split_text_by_parts(text, chunk_size=10000, chunk_overlap=200):
    splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    parts = splitter.split_text(text)
    return parts

def gpt(t, path_json):
    with open(path_json, 'r', encoding='utf-8') as f:
        data = json.load(f)
    data['messages'][1]['text'] = data['messages'][1]['text'].format(t=t)
    headers = {
    "Content-Type": "application/json",
    "Authorization": "Api-Key AQVNzLPkZh1celYQt47GmTiYPuaJk8jiAIx287nU"
    }
    resp = requests.post(URL, headers=headers, data=json.dumps(data))
    summary_book = resp.json()
    return summary_book['result']['alternatives'][0]['message']['text']
    
async def start(update: Update, context: CallbackContext):
    conn = sqlite3.connect('books.db')
    cursor = conn.cursor()

    create_table_sql = '''
    CREATE TABLE IF NOT EXISTS books (
        id TEXT NOT NULL,
        summary TEXT NOT NULL,
        PRIMARY KEY (id)
    );
    '''

    cursor.execute(create_table_sql)
    context.user_data['db_connection'] = conn
    context.user_data['db_cursor'] = cursor
    context.user_data['stopped'] = False
    await update.message.reply_text('Привет! Я бот для анализа книги. Ты можешь отправить мне книгу в формате PDF и я сгенерирую краткий обзор. \n\n Список команд:\n /start - Начать взаимодействие с ботом\n /help - Показать информацию о доступных командах\n /get_summary - Получить описание книги по ФИО автора и название\n /stop - Прекратить взаимодействие с ботом')

async def stop(update: Update, context: CallbackContext):
    context.user_data['stopped'] = True
    conn = context.user_data.get('db_connection')
    if conn:
        conn.close()
    await update.message.reply_text('Спасибо за использование бота! Если понадобится еще помощь, то обращайтесь. До встречи!')

def command_exists(command):
    return command in AVAILABLE_COMMANDS

async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    command = update.message.text.lstrip('/')
    if not command_exists(command):
        await update.message.reply_text(f"Команда /{command} не распознана. Используйте /help, чтобы увидеть доступные команды.")

def check_stopped(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if context.user_data.get('stopped'):
            await update.message.reply_text("Бот остановлен. Введите /start, чтобы снова активировать команды.")
            return 
        await func(update, context) 
    return wrapper

@check_stopped
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Вот список доступных команд:\n\n"
        "/start - Начать взаимодействие с ботом\n"
        "/help - Показать информацию о доступных командах\n"
        "/get_summary - Получить описание книги по ФИО автора и название\n"
        "/stop - Прекратить взаимодействие с ботом\n"
    )

async def send_long_message(bot, chat_id, text):
    for i in range(0, len(text), MAX_MESSAGE_LENGTH):
        part = text[i:i + MAX_MESSAGE_LENGTH]
        await bot.send_message(chat_id=chat_id, text=part)

@check_stopped
async def process_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        pdf_file = await update.message.document.get_file()
        await pdf_file.download_to_drive('book.pdf')
        await update.message.reply_text('Книга загружена. Начинаю анализ книги...')
    except:
        await update.message.reply_text("Файл слишком большой, загрузите другой.")
        return
    text = text_from_pdf('book.pdf')
    parts = split_text_by_parts(text)
    await update.message.reply_text(f"Примерное время ожидания ответа - {len(parts)} мин.")
    book_summary = ''
    for i in range(len(parts)):
        try:
            book_summary += '\n' + gpt(parts[i], 'body.json')
        except:
            await update.message.reply_text("Произошла ошибка, операция прервана. Побробуйте загрузить другую книгу.")
            return
        time.sleep(60)
    book_summary = book_summary.replace('К сожалению, я не могу ничего сказать об этом. Давайте сменим тему?', ' ')
    book_id = uuid.uuid4()
    conn = context.user_data.get('db_connection')
    cursor = context.user_data.get('db_cursor')
    if conn and cursor:
        insert_sql = '''
        INSERT INTO books (id, summary)
        VALUES (?, ?)
        '''
        cursor.execute(insert_sql, (str(book_id), book_summary))
        conn.commit()
    await update.message.reply_text(f"ID данной книжки = {book_id}")
    await send_long_message(context.bot, update.message.chat_id, book_summary)

def get_summary_(book_id, update, context):
    conn = context.user_data.get('db_connection')
    cursor = context.user_data.get('db_cursor')
    select_sql = '''
    SELECT summary FROM books WHERE id = ? 
    '''
    cursor.execute(select_sql, (book_id,))
    result_select = cursor.fetchone()

    if result_select:
        return result_select[0]
    else:
        return "Не найдено описание книги"

@check_stopped
async def get_summary(update: Update, context: CallbackContext):
    full_text = ''.join(context.args)

    summary = get_summary_(full_text, update, context)
    await update.message.reply_text(summary)

def main():

    application = Application.builder().token(TELEGRAM_API_KEY).build()
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler('stop', stop))
    application.add_handler(CommandHandler('get_summary', get_summary))
    application.add_handler(MessageHandler(filters.Document.PDF, process_document))

    application.add_handler(MessageHandler(filters.COMMAND, unknown_command))

    application.run_polling()

if __name__ == '__main__':
    main()
