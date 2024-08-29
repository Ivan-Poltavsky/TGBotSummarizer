import PyPDF2
from telegram import Update
import json
import requests
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext, ContextTypes
import sqlite3
import time


TELEGRAM_API_KEY = '7509563109:AAGV120-wsJsTVfXeSYSX-GPRFPTpN8AHHM'

MAX_MESSAGE_LENGTH = 4096

URL = 'https://llm.api.cloud.yandex.net/foundationModels/v1/completion'
YANDEX_API_KEY = 'AQVNzLPkZh1celYQt47GmTiYPuaJk8jiAIx287nU'

AVAILABLE_COMMANDS = [
    "start",
    "help",
    "stop",
    'get_summary',
    'get_all_list'
]

def text_from_pdf(pdf_path):
    with open(pdf_path, 'rb') as pdf_file:
        text = ''
        reader = PyPDF2.PdfReader(pdf_file)
        for page in reader.pages:
            text += ' ' + page.extract_text()
    return text

def split_text_by_words(text, words_per_part=20000):
    return [text[i:i + words_per_part] for i in range(0, len(text), words_per_part)]

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
        author_name TEXT NOT NULL,
        book_title TEXT NOT NULL,
        summary TEXT NOT NULL,
        PRIMARY KEY (author_name, book_title)
    );
    '''

    cursor.execute(create_table_sql)
    context.user_data['db_connection'] = conn
    context.user_data['db_cursor'] = cursor
    context.user_data['stopped'] = False
    await update.message.reply_text('Привет! Я бот для анализа книги. Отправь мне книгу в формате PDF и я сгенерирую краткий обзор. \n\n Список команд:\n /start - Начать взаимодействие с ботом\n /help - Показать информацию о доступных командах\n /get_summary - Получить описание книги по ФИО автора и название\n  /get_all_list - Получить полный список названий книг с автором\n /stop - Прекратить взаимодействие с ботом')

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
        "/get_all_list - Получить полный список названий книг с автором"
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
    parts = split_text_by_words(text)
    try:
        book_summary = ''
        for i in range(len(parts)):
            try:
                time.sleep(10)
                book_summary += '----------------' + gpt(parts[i], 'body.json')
            except:
                parts_2 = split_text_by_words(parts[i], len(parts[i]) // 3)
                for j in range(len(parts_2)):
                    time.sleep(10)
                    book_summary += '----------------' + gpt(parts_2[j], 'body.json')
        try:
            book_summary = gpt(book_summary, 'body1.json')
        except:
            await update.message.reply_text("Из-за большого объёма книги невозможно объединить её частичные результаты.")
        book_summary = book_summary.replace('К сожалению, я не могу ничего сказать об этом. Давайте сменим тему?', ' ')
        book_summary = book_summary.replace('----------------', ' ')
        summary_response = gpt(book_summary[:500], 'body2.json')
        if " | " in summary_response:
            author_name, book_title = summary_response.split(" | ")
            conn = context.user_data.get('db_connection')
            cursor = context.user_data.get('db_cursor')
            if conn and cursor:
                insert_sql = '''
                INSERT INTO books (author_name, book_title, summary)
                VALUES (?, ?, ?)
                '''
                cursor.execute(insert_sql, (author_name, book_title, book_summary))
                conn.commit()
            await send_long_message(context.bot, update.message.chat_id, book_summary)
        else:
            await update.message.reply_text("Не удалось извлечь имя автора и название книги.")
            await send_long_message(context.bot, update.message.chat_id, book_summary)
    except:
        await update.message.reply_text("Произошла ошибка по анализу книги. Загрузите другую книгу.")

def get_summary_(author_name, book_title, update, context):
    conn = context.user_data.get('db_connection')
    cursor = context.user_data.get('db_cursor')
    select_sql = '''
    SELECT summary FROM books WHERE author_name = ? AND book_title = ?
    '''
    cursor.execute(select_sql, (author_name, book_title))
    result_select = cursor.fetchone()

    if result_select:
        return result_select[0]
    else:
        return "Не найдено описание книги"

@check_stopped
async def get_summary(update: Update, context: CallbackContext):
    if len(context.args) < 2:
        await update.message.reply_text("Пожалуйста, укажите ФИО автора и название книги. Пример: /get_summary Автор - Название книги")
        return
    
    full_text = ' '.join(context.args)
    
    split_index = full_text.find(' - ')
    if split_index == -1:
        await update.message.reply_text("Не удалось разделить ФИО автора и название книги. Используйте формат: /get_summary Автор - Название книги")
        return

    author_name = full_text[:split_index].strip()
    book_title = full_text[split_index + 3:].strip()

    summary = get_summary_(author_name, book_title, update, context)
    await update.message.reply_text(summary)

@check_stopped
async def get_all_list(update: Update, context: CallbackContext):
    conn = context.user_data.get('db_connection')
    cursor = context.user_data.get('db_cursor')
    select_sql = '''
    SELECT author_name, book_title FROM books
    '''
    cursor.execute(select_sql)
    result_select = cursor.fetchall()

    if result_select:
        result_message = "Список всех книг:\n\n"
        for author_name, book_title in result_select:
            result_message += f"Автор: {author_name}, Название: {book_title}\n"
        
        if len(result_message) > MAX_MESSAGE_LENGTH:
            await send_long_message(context.bot, update.message.chat_id, result_message)
        else:
            await update.message.reply_text(result_message)
    else:
        await update.message.reply_text("База данных пуста")

def main():

    application = Application.builder().token(TELEGRAM_API_KEY).build()
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler('stop', stop))
    application.add_handler(CommandHandler('get_all_list', get_all_list))
    application.add_handler(CommandHandler('get_summary', get_summary))
    application.add_handler(MessageHandler(filters.Document.PDF, process_document))

    application.add_handler(MessageHandler(filters.COMMAND, unknown_command))

    application.run_polling()

if __name__ == '__main__':
    main()
