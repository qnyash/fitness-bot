import os
import json
import telebot
from telebot import types
from flask import Flask, request
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

# ================= НАСТРОЙКИ =================
TOKEN = os.environ.get("BOT_TOKEN")
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

ADMIN_ID = 466924747  # Твой ID для админ-панели

# ================= ПОДКЛЮЧЕНИЕ К GOOGLE SHEETS =================
gc = None
sh = None
try:
    creds_json = os.environ.get('GOOGLE_CREDENTIALS')
    creds_dict = json.loads(creds_json)
    scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    credentials = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    gc = gspread.authorize(credentials)
    sh = gc.open_by_url(os.environ.get('SPREADSHEET_URL'))
except Exception as e:
    pass

def init_db():
    if not sh: return
    worksheets = [ws.title for ws in sh.worksheets()]
    
    if 'Users' not in worksheets:
        ws = sh.add_worksheet(title="Users", rows=100, cols=5)
        ws.append_row(['user_id', 'name', 'date_joined'])
        
    if 'Program' not in worksheets:
        ws = sh.add_worksheet(title="Program", rows=100, cols=5)
        ws.append_row(['day', 'exercise', 'sets', 'reps'])
        ws.append_rows([
            ['Д1', 'Присед', '4', '10'], ['Д1', 'Выпады', '3', '12'], ['Д1', 'Мост', '4', '15'],
            ['Д2', 'Тяга в наклоне', '3', '10'], ['Д2', 'Жим лёжа', '3', '12'], ['Д2', 'Планка', '3', '45']
        ])
        
    if 'History' not in worksheets:
        ws = sh.add_worksheet(title="History", rows=100, cols=5)
        ws.append_row(['date', 'user_id', 'name', 'day', 'status'])

    if 'Progress' not in worksheets:
        ws = sh.add_worksheet(title="Progress", rows=100, cols=3)
        ws.append_row(['date', 'user_id', 'note'])

init_db()

# ================= ПАМЯТЬ БОТА =================
active_workouts = {}
user_states = {}  # Для запоминания того, что вводит пользователь (например, заметки)

def get_program_from_sheet(day):
    if not sh: return []
    try:
        ws = sh.worksheet("Program")
        records = ws.get_all_records()
        return [r for r in records if str(r.get('day', '')) == day]
    except:
        return []

# ================= КЛАВИАТУРЫ =================
def main_keyboard(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.row("🏋️ Тренировка")
    markup.row("📏 Замеры", "📅 История")
    markup.row("🏋️‍♀️ Прогресс", "📚 Библиотека")
    markup.row("😩 Сегодня нет сил")
    
    if user_id == ADMIN_ID:
        markup.row("⚙️ Админ-панель")
        
    return markup

def workout_keyboard(user_id):
    markup = types.InlineKeyboardMarkup(row_width=1)
    workout = active_workouts.get(user_id)
    if not workout: return markup
    
    for i, ex in enumerate(workout['program']):
        is_done = i in workout['done']
        icon = "✅" if is_done else "☐"
        name = ex.get('exercise', 'Упражнение')
        sets = ex.get('sets', '0')
        reps = ex.get('reps', '0')
        markup.add(types.InlineKeyboardButton(f"{icon} {name} ({sets}x{reps})", callback_data=f"ex_{i}"))
        
    markup.add(types.InlineKeyboardButton("🏁 Завершить тренировку", callback_data="finish"))
    return markup

# ================= ОБРАБОТЧИКИ =================
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    user_states[user_id] = None
    if sh:
        try:
            ws = sh.worksheet("Users")
            if str(user_id) not in ws.col_values(1):
                ws.append_row([str(user_id), message.from_user.first_name, datetime.now().strftime("%Y-%m-%d %H:%M")])
        except: pass

    bot.send_message(message.chat.id, f"Привет, {message.from_user.first_name}! 👋\nЯ твой фитнес-бот.", reply_markup=main_keyboard(user_id))

@bot.message_handler(func=lambda m: True)
def handle_text(message):
    text = message.text.strip()
    user_id = message.from_user.id
    
    # 1. Проверяем, не пишет ли пользователь сейчас заметку о прогрессе
    if user_states.get(user_id) == 'waiting_progress':
        if "Отмена" in text:
            user_states[user_id] = None
            bot.send_message(message.chat.id, "Ввод прогресса отменен.", reply_markup=main_keyboard(user_id))
            return
            
        if sh:
            try:
                date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
                sh.worksheet("Progress").append_row([date_str, str(user_id), text])
            except: pass
        user_states[user_id] = None
        bot.send_message(message.chat.id, "✅ Твой прогресс успешно сохранён в дневник!", reply_markup=main_keyboard(user_id))
        return

    # 2. Обработка обычного меню (Ищем только КЛЮЧЕВЫЕ слова, игнорируя смайлики)
    if "Тренировка" in text or "🏋️" in text:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("Д1 — Ноги/ягодицы", callback_data="day_Д1"))
        markup.add(types.InlineKeyboardButton("Д2 — Спина/плечи", callback_data="day_Д2"))
        bot.send_message(message.chat.id, "Выбери день тренировки:", reply_markup=markup)
        
    elif "Прогресс" in text:
        user_states[user_id] = 'waiting_progress'
        cancel_markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        cancel_markup.add("❌ Отмена")
        bot.send_message(message.chat.id, "📝 Напиши свои результаты (например: 'Присед 50кг 3х10').\nЯ сохраню это в дневник!", reply_markup=cancel_markup)
        
    elif "нет сил" in text:
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(types.InlineKeyboardButton("➡️ Перенести", callback_data="nopower_postpone"))
        markup.add(types.InlineKeyboardButton("❌ Пропустить", callback_data="nopower_skip"))
        markup.add(types.InlineKeyboardButton("💡 Легкая версия", callback_data="day_Легкая"))
        bot.send_message(message.chat.id, "Ничего страшного, слушай своё тело. Что будем делать?", reply_markup=markup)
        
    elif "Админ" in text and user_id == ADMIN_ID:
        sheet_url = os.environ.get('SPREADSHEET_URL')
        msg = "👑 **Админ-панель**\n\nСамый удобный способ управлять ботом — прямо в Google Таблице!\n\n💡 Чтобы добавить **Легкую версию**, просто перейди на вкладку `Program` и добавь упражнения, указав в колонке `day` слово `Легкая`."
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("📊 Открыть базу данных", url=sheet_url))
        bot.send_message(message.chat.id, msg, parse_mode="Markdown", reply_markup=main_keyboard(user_id))
        
    else:
        bot.send_message(message.chat.id, "Раздел в разработке 🛠 Используй кнопки меню.", reply_markup=main_keyboard(user_id))

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    user_id = call.from_user.id
    
    if call.data == "nopower_postpone":
        bot.edit_message_text("🛋 Тренировка перенесена на завтра. Отдыхай, набирайся сил!", call.message.chat.id, call.message.id)
    
    elif call.data == "nopower_skip":
        if sh:
            try:
                date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
                sh.worksheet("History").append_row([date_str, str(user_id), call.from_user.first_name, "Пропуск", "Нет сил"])
            except: pass
        bot.edit_message_text("❌ Тренировка пропущена. Записал в историю.", call.message.chat.id, call.message.id)

    elif call.data.startswith("day_"):
        day = call.data.replace("day_", "")
        program = get_program_from_sheet(day)
        
        if not program:
            bot.answer_callback_query(call.id, f"Программа '{day}' пока пуста. Добавь её в таблице!")
            return
            
        active_workouts[user_id] = {'day': day, 'program': program, 'done': []}
        bot.edit_message_text(f"🏋️ **Тренировка: {day}**\nОтмечай выполненные:", call.message.chat.id, call.message.id, parse_mode="Markdown", reply_markup=workout_keyboard(user_id))
        
    elif call.data.startswith("ex_"):
        if user_id not in active_workouts:
            bot.answer_callback_query(call.id, "Тренировка сброшена. Начни заново.")
            return
            
        ex_idx = int(call.data.split("_")[1])
        done = active_workouts[user_id]['done']
        if ex_idx in done: done.remove(ex_idx)
        else: done.append(ex_idx)
        
        day = active_workouts[user_id]['day']
        bot.edit_message_text(f"🏋️ **Тренировка: {day}**\nОтмечай выполненные:", call.message.chat.id, call.message.id, parse_mode="Markdown", reply_markup=workout_keyboard(user_id))
        
    elif call.data == "finish":
        if user_id not in active_workouts: return
        workout = active_workouts.pop(user_id)
        day = workout['day']
        status = "Полностью" if len(workout['done']) == len(workout['program']) else "Частично"
        
        if sh:
            try:
                date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
                sh.worksheet("History").append_row([date_str, str(user_id), call.from_user.first_name, day, status])
            except: pass
        bot.edit_message_text(f"🏁 **Тренировка {day} завершена!**\nСтатус: {status}\nРезультат записан в дневник. Ты молодец! 🔥", call.message.chat.id, call.message.id, parse_mode="Markdown")

# ================= WEBHOOK И СЕРВЕР =================
@app.route('/' + TOKEN, methods=['POST'])
def webhook():
    json_str = request.get_data().decode('UTF-8')
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return 'OK', 200

@app.route('/')
def index(): return "Бот работает на Render ✅"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
