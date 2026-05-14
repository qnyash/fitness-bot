import os
import json
import random
import telebot
from telebot import types
from flask import Flask, request
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

TOKEN = os.environ.get("BOT_TOKEN")
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

ADMIN_ID = 466924747
CHANNEL_ID = -1003457894028

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
        
    if 'History' not in worksheets:
        ws = sh.add_worksheet(title="History", rows=100, cols=5)
        ws.append_row(['date', 'user_id', 'name', 'day', 'status'])

    if 'Progress' not in worksheets:
        ws = sh.add_worksheet(title="Progress", rows=100, cols=3)
        ws.append_row(['date', 'user_id', 'note'])

    if 'Library' not in worksheets:
        ws = sh.add_worksheet(title="Library", rows=100, cols=4)
        ws.append_row(['category', 'name', 'description', 'image_url'])
        
    if 'Motivation' not in worksheets:
        ws = sh.add_worksheet(title="Motivation", rows=100, cols=1)
        ws.append_row(['text'])
        ws.append_row(['Хватит откладывать! Время действовать! 🔥'])
        ws.append_row(['Каждая тренировка делает тебя лучше! 🍑'])

init_db()

active_workouts = {}
user_states = {}

def get_program_from_sheet(day):
    if not sh: return []
    try:
        ws = sh.worksheet("Program")
        return [r for r in ws.get_all_records() if str(r.get('day', '')) == day]
    except: return []

def get_lib_categories():
    if not sh: return []
    try:
        ws = sh.worksheet("Library")
        cats = [str(r.get('category', '')) for r in ws.get_all_records() if r.get('category')]
        return list(set(cats))
    except: return []

def get_lib_exercises(cat):
    if not sh: return []
    try:
        ws = sh.worksheet("Library")
        return [r for r in ws.get_all_records() if str(r.get('category', '')) == cat]
    except: return []

# ================= КЛАВИАТУРЫ =================
def main_keyboard(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.row("🏋️ Тренировка")
    markup.row("📏 Замеры", "📅 История")
    markup.row("📈 Прогресс", "📚 Библиотека")
    markup.row("😩 Сегодня нет сил")
    if user_id == ADMIN_ID:
        markup.row("⚙️ Админ-панель")
    return markup

def workout_keyboard(user_id):
    markup = types.InlineKeyboardMarkup(row_width=1)
    workout = active_workouts.get(user_id)
    if not workout: return markup
    
    for i, ex in enumerate(workout['program']):
        icon = "✅" if i in workout['done'] else "☐"
        name = ex.get('exercise', 'Упр')
        sets, reps = ex.get('sets', '0'), ex.get('reps', '0')
        markup.add(types.InlineKeyboardButton(f"{icon} {name} ({sets}x{reps})", callback_data=f"ex_{i}"))
    markup.add(types.InlineKeyboardButton("🏁 Завершить тренировку", callback_data="finish"))
    return markup

# ================= ОБРАБОТЧИКИ СООБЩЕНИЙ =================
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
    
    welcome_text = f"Привет, {message.from_user.first_name}! 🤸‍♀️\nГотова растрясти булочки?"
    bot.send_message(message.chat.id, welcome_text, reply_markup=main_keyboard(user_id))

@bot.message_handler(func=lambda m: True)
def handle_text(message):
    text = message.text.strip()
    user_id = message.from_user.id
    
    if user_states.get(user_id) == 'waiting_progress':
        if "Отмена" in text:
            user_states[user_id] = None
            bot.send_message(message.chat.id, "Отменено.", reply_markup=main_keyboard(user_id))
            return
        if sh:
            try:
                sh.worksheet("Progress").append_row([datetime.now().strftime("%Y-%m-%d %H:%M"), str(user_id), text])
            except: pass
        user_states[user_id] = None
        bot.send_message(message.chat.id, "✅ Твой прогресс сохранён в таблицу!", reply_markup=main_keyboard(user_id))
        return

    if "Тренировка" in text or "🏋️" in text:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("Д1 — Ноги/ягодицы", callback_data="day_Д1"))
        markup.add(types.InlineKeyboardButton("Д2 — Спина/плечи", callback_data="day_Д2"))
        bot.send_message(message.chat.id, "Выбери день тренировки:", reply_markup=markup)
        
    elif "Прогресс" in text or "📈" in text:
        user_states[user_id] = 'waiting_progress'
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add("❌ Отмена")
        bot.send_message(message.chat.id, "📝 Напиши свой прогресс (например: 'Присед 50кг').", reply_markup=markup)

    elif "Библиотека" in text or "📚" in text:
        cats = get_lib_categories()
        if not cats:
            bot.send_message(message.chat.id, "Библиотека пуста. Добавь данные в таблицу!")
            return
        markup = types.InlineKeyboardMarkup()
        for cat in cats: markup.add(types.InlineKeyboardButton(cat, callback_data=f"libcat_{cat}"))
        bot.send_message(message.chat.id, "📚 Выбери категорию:", reply_markup=markup)
        
    elif "нет сил" in text:
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(types.InlineKeyboardButton("➡️ Перенести", callback_data="nopower_postpone"))
        markup.add(types.InlineKeyboardButton("❌ Пропустить", callback_data="nopower_skip"))
        markup.add(types.InlineKeyboardButton("💡 Легкая версия", callback_data="day_Легкая"))
        bot.send_message(message.chat.id, "Слушай своё тело. Что будем делать?", reply_markup=markup)
        
    elif "Админ" in text and user_id == ADMIN_ID:
        url = os.environ.get('SPREADSHEET_URL')
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(types.InlineKeyboardButton("📊 Открыть базу данных", url=url))
        markup.add(types.InlineKeyboardButton("📣 Отправить мотивацию в канал", callback_data="admin_motivate"))
        markup.add(types.InlineKeyboardButton("🔔 Пнуть лентяев (в личку)", callback_data="admin_remind"))
        bot.send_message(message.chat.id, "👑 **Пульт управления ботом:**", parse_mode="Markdown", reply_markup=markup)
    else:
        bot.send_message(message.chat.id, "Используй кнопки 👇", reply_markup=main_keyboard(user_id))

# ================= ОБРАБОТЧИКИ КНОПОК =================
@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    user_id = call.from_user.id
    
    # --- АДМИН ПАНЕЛЬ ---
    if call.data == "admin_motivate":
        if user_id != ADMIN_ID: return
        try:
            phrases = sh.worksheet("Motivation").col_values(1)[1:]
            if phrases:
                bot.send_message(CHANNEL_ID, random.choice(phrases))
                bot.answer_callback_query(call.id, "✅ Отправлено в канал!")
            else:
                bot.answer_callback_query(call.id, "❌ В таблице нет фраз!", show_alert=True)
        except Exception as e:
            bot.answer_callback_query(call.id, f"Ошибка: {e}")
            
    elif call.data == "admin_remind":
        if user_id != ADMIN_ID: return
        try:
            users = sh.worksheet("Users").col_values(1)[1:]
            history = sh.worksheet("History").get_all_records()
            last_workouts = {str(r.get('user_id', '')): str(r.get('date', '')) for r in history}
            
            sent_count = 0
            now = datetime.now()
            for uid in users:
                last_w = last_workouts.get(uid)
                send_ping = False
                if not last_w: send_ping = True
                else:
                    try:
                        last_d = datetime.strptime(last_w, "%Y-%m-%d %H:%M")
                        if (now - last_d).days >= 3: send_ping = True
                    except: pass
                
                if send_ping:
                    try:
                        bot.send_message(int(uid), "Хей! 🍑 Давно не было тренировок. Пора растрясти булочки!")
                        sent_count += 1
                    except: pass
            bot.answer_callback_query(call.id, f"✅ Разослано напоминаний: {sent_count}", show_alert=True)
        except Exception as e:
            bot.answer_callback_query(call.id, f"Ошибка: {e}")

    # --- ТРЕНИРОВКИ ---
    elif call.data == "nopower_postpone":
        bot.edit_message_text("🛋 Перенесено на завтра. Отдыхай!", call.message.chat.id, call.message.id)
    elif call.data == "nopower_skip":
        if sh:
            try: sh.worksheet("History").append_row([datetime.now().strftime("%Y-%m-%d %H:%M"), str(user_id), call.from_user.first_name, "Пропуск", "Нет сил"])
            except: pass
        bot.edit_message_text("❌ Пропущено. Записано в дневник.", call.message.chat.id, call.message.id)

    elif call.data.startswith("day_"):
        day = call.data.replace("day_", "")
        program = get_program_from_sheet(day)
        if not program:
            bot.answer_callback_query(call.id, f"Программа '{day}' пуста!")
            return
        active_workouts[user_id] = {'day': day, 'program': program, 'done': []}
        bot.edit_message_text(f"🏋️ **Тренировка: {day}**", call.message.chat.id, call.message.id, parse_mode="Markdown", reply_markup=workout_keyboard(user_id))
        
    elif call.data.startswith("ex_"):
        if user_id not in active_workouts: return
        ex_idx = int(call.data.split("_")[1])
        done = active_workouts[user_id]['done']
        if ex_idx in done: done.remove(ex_idx)
        else: done.append(ex_idx)
        bot.edit_message_text(f"🏋️ **Тренировка: {active_workouts[user_id]['day']}**", call.message.chat.id, call.message.id, parse_mode="Markdown", reply_markup=workout_keyboard(user_id))
        
    elif call.data == "finish":
        if user_id not in active_workouts: return
        workout = active_workouts.pop(user_id)
        day = workout['day']
        status = "Полностью" if len(workout['done']) == len(workout['program']) else "Частично"
        if sh:
            try: sh.worksheet("History").append_row([datetime.now().strftime("%Y-%m-%d %H:%M"), str(user_id), call.from_user.first_name, day, status])
            except: pass
        bot.edit_message_text(f"🏁 **{day} завершена!**\nСтатус: {status}\nЗаписано в дневник! 🔥", call.message.chat.id, call.message.id, parse_mode="Markdown")

    # --- БИБЛИОТЕКА ---
    elif call.data.startswith("libcat_"):
        cat = call.data.replace("libcat_", "")
        exs = get_lib_exercises(cat)
        markup = types.InlineKeyboardMarkup()
        for i, ex in enumerate(exs):
            markup.add(types.InlineKeyboardButton(ex.get('name', 'Упр'), callback_data=f"libex_{cat}_{i}"))
        markup.add(types.InlineKeyboardButton("↩️ Назад к категориями", callback_data="lib_back"))
        bot.edit_message_text(f"📚 **Категория: {cat}**\nВыбери упражнение:", call.message.chat.id, call.message.id, parse_mode="Markdown", reply_markup=markup)
        
    elif call.data.startswith("libex_"):
        parts = call.data.split("_")
        cat, idx = parts[1], int(parts[2])
        ex = get_lib_exercises(cat)[idx]
        
        name = ex.get('name', '')
        desc = ex.get('description', '')
        img = str(ex.get('image_url', '')).strip()
        text = f"🏋️ **{name}**\n\n{desc}"
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("↩️ Назад к списку", callback_data=f"libcat_{cat}"))
        bot.delete_message(call.message.chat.id, call.message.id)
        
        if img and img.startswith("http"):
            try: bot.send_photo(call.message.chat.id, img, caption=text, parse_mode="Markdown", reply_markup=markup)
            except: bot.send_message(call.message.chat.id, text, parse_mode="Markdown", reply_markup=markup)
        else:
            bot.send_message(call.message.chat.id, text, parse_mode="Markdown", reply_markup=markup)

    elif call.data == "lib_back":
        cats = get_lib_categories()
        markup = types.InlineKeyboardMarkup()
        for c in cats: markup.add(types.InlineKeyboardButton(c, callback_data=f"libcat_{c}"))
        bot.edit_message_text("📚 Выбери категорию:", call.message.chat.id, call.message.id, reply_markup=markup)


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
