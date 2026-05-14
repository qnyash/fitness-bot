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
    print("✅ Успешное подключение к Google Таблице!")
except Exception as e:
    print(f"🚨 Ошибка подключения к таблице: {e}")

# Инициализация вкладок в таблице
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

init_db()

# ================= ПАМЯТЬ БОТА (ДЛЯ ГАЛОЧЕК) =================
# Храним текущие тренировки: { user_id: {'day': 'Д1', 'program': [...], 'done': []} }
active_workouts = {}

def get_program_from_sheet(day):
    if not sh: return []
    try:
        ws = sh.worksheet("Program")
        records = ws.get_all_records()
        return [r for r in records if str(r.get('day', '')) == day]
    except:
        return []

# ================= КЛАВИАТУРЫ =================
def main_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.row("🏋️ Тренировка")
    markup.row("📏 Замеры", "📅 История")
    markup.row("🏋️‍♀️ Прогресс", "📚 Библиотека")
    return markup

def workout_keyboard(user_id):
    markup = types.InlineKeyboardMarkup(row_width=1)
    workout = active_workouts.get(user_id)
    
    if not workout: return markup
    
    program = workout['program']
    done = workout['done']
    
    for i, ex in enumerate(program):
        is_done = i in done
        icon = "✅" if is_done else "☐"
        name = ex.get('exercise', 'Упражнение')
        sets = ex.get('sets', '0')
        reps = ex.get('reps', '0')
        
        btn_text = f"{icon} {name} ({sets}x{reps})"
        markup.add(types.InlineKeyboardButton(btn_text, callback_data=f"ex_{i}"))
        
    markup.add(types.InlineKeyboardButton("🏁 Завершить тренировку", callback_data="finish"))
    return markup

# ================= ОБРАБОТЧИКИ =================
@bot.message_handler(commands=['start'])
def start(message):
    # Сохраняем пользователя в базу
    if sh:
        try:
            ws = sh.worksheet("Users")
            users = ws.col_values(1)
            if str(message.from_user.id) not in users:
                date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
                ws.append_row([str(message.from_user.id), message.from_user.first_name, date_str])
        except:
            pass

    bot.send_message(
        message.chat.id,
        f"Привет, {message.from_user.first_name}! 👋\nЯ твой фитнес-бот. Выбирай действие в меню ниже.",
        reply_markup=main_keyboard()
    )

@bot.message_handler(func=lambda m: True)
def handle_text(message):
    text = message.text.strip()
    
    if "Тренировка" in text or "🏋️" in text:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("Д1 — Ноги/ягодицы", callback_data="day_Д1"))
        markup.add(types.InlineKeyboardButton("Д2 — Спина/плечи", callback_data="day_Д2"))
        bot.send_message(message.chat.id, "Выбери день тренировки:", reply_markup=markup)
    else:
        bot.send_message(message.chat.id, "Раздел в разработке 🛠 Используй кнопки меню.", reply_markup=main_keyboard())

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    user_id = call.from_user.id
    
    # Пользователь выбрал день тренировки
    if call.data.startswith("day_"):
        day = call.data.replace("day_", "")
        program = get_program_from_sheet(day)
        
        if not program:
            bot.answer_callback_query(call.id, "Программа для этого дня пуста!")
            return
            
        active_workouts[user_id] = {'day': day, 'program': program, 'done': []}
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.id,
            text=f"🏋️ **Тренировка: {day}**\nОтмечай выполненные упражнения:",
            parse_mode="Markdown",
            reply_markup=workout_keyboard(user_id)
        )
        
    # Пользователь нажал на упражнение
    elif call.data.startswith("ex_"):
        if user_id not in active_workouts:
            bot.answer_callback_query(call.id, "Тренировка не найдена. Начни заново.")
            return
            
        ex_index = int(call.data.split("_")[1])
        done_list = active_workouts[user_id]['done']
        
        if ex_index in done_list:
            done_list.remove(ex_index) # Убрать галочку
        else:
            done_list.append(ex_index) # Поставить галочку
            
        active_workouts[user_id]['done'] = done_list
        
        # Обновляем кнопки
        day = active_workouts[user_id]['day']
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.id,
            text=f"🏋️ **Тренировка: {day}**\nОтмечай выполненные упражнения:",
            parse_mode="Markdown",
            reply_markup=workout_keyboard(user_id)
        )
        
    # Пользователь завершил тренировку
    elif call.data == "finish":
        if user_id not in active_workouts:
            bot.answer_callback_query(call.id, "Нет активной тренировки.")
            return
            
        workout = active_workouts.pop(user_id)
        day = workout['day']
        is_full = len(workout['done']) == len(workout['program'])
        status = "Полностью" if is_full else "Частично"
        
        # Запись в историю
        if sh:
            try:
                date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
                sh.worksheet("History").append_row([date_str, str(user_id), call.from_user.first_name, day, status])
            except Exception as e:
                print("Ошибка записи истории:", e)
        
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.id,
            text=f"🏁 **Тренировка {day} завершена!**\nСтатус: {status}\n\nРезультат записан в дневник. Ты молодец! 🔥",
            parse_mode="Markdown"
        )

# ================= WEBHOOK И СЕРВЕР =================
@app.route('/' + TOKEN, methods=['POST'])
def webhook():
    json_str = request.get_data().decode('UTF-8')
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return 'OK', 200

@app.route('/')
def index():
    return "Фитнес-бот успешно работает и подключен к таблицам! ✅"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
